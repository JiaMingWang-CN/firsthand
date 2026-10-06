"""Regression coverage for the whole-project audit; no model or Steel calls."""

import asyncio
import gc
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from api import drafts
from api.jobs import Busy, Jobs, process_started
from api.service import Reader
from core.community import Disclosure, Withheld, finding_map
from core.persona import ProductSummary
from core.runtime import ROOT, write_json
from core.simulation import SimulationStore
from orchestrator import personas, phase1, phase4
from orchestrator.manual import read_manual
from report.agent import Claim, agent_prompt, describe
from test_phase1 import CAPABILITY, CONFIG, PRODUCT, SAMPLE, draft  # noqa: F401
from test_phase7 import cohort, mock_model
from test_pipeline import SETTINGS, configured  # noqa: F401
from tests.test_phase3 import save_fake_experience
from tests.test_phase4 import survey
from tests.verify_phase2 import fixture_persona


def approved_source(root, draft):
    path = root / "phase1-audit"
    path.mkdir(parents=True)
    (path / "manual.md").write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    write_json(path / "draft.json", draft.model_dump(mode="json"))
    write_json(path / "capability_profile.json", CAPABILITY)
    write_json(path / "phase1_result.json", {"passed": True, "stage": "drafted"})
    phase1.approve(path, phase1.draft_hash(path))
    return path


def test_runner_survives_api_exit_and_finishes_the_pipeline(tmp_path):
    gate, first, second = (tmp_path / name for name in ("gate", "first", "report"))
    script = """
import sys
from api.jobs import Jobs
root, gate, first, second = sys.argv[1:]
job = Jobs(root).start('simulate', [
    {'name': 'browse', 'module': 'tests.fixtures.job_step', 'args': [gate, first]},
    {'name': 'report', 'module': 'tests.fixtures.job_step', 'args': [gate, second]},
], simulation='phase4-audit', report='phase5-audit')
print(job['id'], flush=True)
"""
    starter = subprocess.run([sys.executable, "-c", script, str(tmp_path), str(gate), str(first), str(second)],
                             cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert starter.returncode == 0, starter.stderr
    job_id = starter.stdout.strip()
    jobs = Jobs(tmp_path)
    try:
        assert jobs.view(job_id)["state"] == "running"
        with pytest.raises(Busy):
            jobs.start("simulate", [], simulation="other", report="other-report")
    finally:
        gate.touch()
    deadline = time.monotonic() + 15
    while jobs.view(job_id)["state"] == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
    assert jobs.view(job_id)["state"] == "succeeded"
    assert first.is_file() and second.is_file()
    assert all(step["state"] == "succeeded" for step in jobs.view(job_id)["steps"])
    assert "_commands" not in jobs.view(job_id)
    replay = subprocess.run([sys.executable, "-m", "api.job_runner", str(tmp_path), job_id],
                            cwd=ROOT, capture_output=True, timeout=15)
    assert replay.returncode != 0
    assert jobs.view(job_id)["state"] == "succeeded"


def test_completion_during_the_pid_check_does_not_look_detached(tmp_path, monkeypatch):
    job = {"id": "simulate-finish", "kind": "simulate", "state": "running", "simulation": "run", "report": "report",
           "created_at": "2026-10-04T00:00:00+00:00", "runner_pid": 123, "steps": []}
    path = tmp_path / "_jobs" / "simulate-finish.json"
    write_json(path, job)

    def finished(pid, started):
        write_json(path, {**job, "state": "succeeded"})
        return False

    monkeypatch.setattr("api.jobs.process_running", finished)
    assert Jobs(tmp_path).view(job["id"])["state"] == "succeeded"


def test_unknown_detached_simulation_still_blocks_paid_work(tmp_path):
    write_json(tmp_path / "_jobs" / "simulate-old.json", {
        "id": "simulate-old", "kind": "simulate", "state": "running", "simulation": "old", "report": "report",
        "created_at": "2026-10-04T00:00:00+00:00", "steps": []})
    jobs = Jobs(tmp_path)
    assert jobs.view("simulate-old")["state"] == "detached"
    with pytest.raises(Busy):
        jobs.start("simulate", [], simulation="new", report="new-report")


def test_reused_runner_pid_is_not_mistaken_for_the_coordinator(tmp_path):
    # This test process stands in for an unrelated process that later received the dead coordinator's PID.
    write_json(tmp_path / "_jobs" / "simulate-reused.json", {
        "id": "simulate-reused", "kind": "simulate", "state": "running", "simulation": "run", "report": "report",
        "created_at": "2026-10-04T00:00:00+00:00", "runner_pid": os.getpid(),
        "runner_started": process_started(os.getpid()) - 3600, "steps": []})
    assert Jobs(tmp_path).view("simulate-reused")["state"] == "detached"


def detached_job(root, **fields):
    job = {"id": "simulate-lost", "kind": "simulate", "state": "running", "simulation": "lost", "report": "report",
           "created_at": "2026-10-04T00:00:00+00:00", "runner_pid": 1, "runner_started": 0,
           "steps": [{"name": "browse", "state": "running"}, {"name": "report", "state": "pending"}], **fields}
    write_json(root / "_jobs" / f"{job['id']}.json", job)
    return job


def test_detached_job_is_released_once_its_child_has_ended(tmp_path):
    finished = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True)
    detached_job(tmp_path, child_pid=int(finished.stdout), child_started=0)
    jobs = Jobs(tmp_path)
    with pytest.raises(Busy):
        jobs.start("simulate", [], simulation="new", report="new-report")
    released = jobs.abandon("simulate-lost")
    assert released["state"] == "failed" and released["abandoned_at"]
    assert [step["state"] for step in jobs.view("simulate-lost")["steps"]] == ["failed", "pending"]
    assert "释放占用" in jobs.log_tail("simulate-lost")[-1]
    # Released: a new simulation may reserve again (no steps, so the injected popen is never called).
    Jobs(tmp_path, popen=None).start("simulate", [], simulation="new", report="new-report")


def test_detached_job_with_a_live_child_is_not_released(tmp_path):
    detached_job(tmp_path, child_pid=os.getpid(), child_started=process_started(os.getpid()))
    with pytest.raises(Busy, match=str(os.getpid())):
        Jobs(tmp_path).abandon("simulate-lost")
    assert Jobs(tmp_path).view("simulate-lost")["state"] == "detached"


def test_legacy_or_tracked_jobs_need_the_right_release(tmp_path):
    write_json(tmp_path / "_jobs" / "simulate-old.json", {
        "id": "simulate-old", "kind": "simulate", "state": "running", "simulation": "old", "report": "report",
        "created_at": "2026-10-04T00:00:00+00:00", "steps": []})
    jobs = Jobs(tmp_path)
    with pytest.raises(Busy, match="--force"):
        jobs.abandon("simulate-old")
    command = [sys.executable, "-m", "api.abandon_job", "simulate-old", "--runs", str(tmp_path), "--force"]
    released = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert released.returncode == 0, released.stderr
    assert jobs.view("simulate-old")["state"] == "failed"
    with pytest.raises(Busy, match="failed"):
        jobs.abandon("simulate-old")


def test_concurrent_generation_reserves_the_draft_once(tmp_path, monkeypatch, configured):
    path = tmp_path / "phase1-audit"
    path.mkdir()
    (path / "manual.md").write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    write_json(path / "phase1_result.json", {"passed": True, "stage": "analyzed", "minimum_personas": 3})
    gate, barrier = threading.Event(), threading.Barrier(2)

    class Process:
        pid = os.getpid()

        def wait(self):
            gate.wait(10)
            return 0

    jobs = [Jobs(tmp_path, popen=lambda *args, **kwargs: Process()) for _ in range(2)]
    original = drafts.summary

    def simultaneous(*args):
        result = original(*args)
        barrier.wait(5)
        return result

    monkeypatch.setattr(drafts, "summary", simultaneous)

    def start(manager):
        try:
            return drafts.start_generate(tmp_path, manager, path.name, 10, 1)
        except Busy:
            return None

    try:
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(start, jobs))
        assert sum(result is not None for result in results) == 1
    finally:
        gate.set()
        for manager in jobs:
            for thread in list(manager._live.values()):
                thread.join(3)


def test_wrong_cohort_size_is_repaired_before_identity_requests(monkeypatch):
    manual = read_manual(SAMPLE)
    bodies = []
    mock_model(monkeypatch, cohort(10, manual), bodies)
    with pytest.raises(ValueError, match="槽位数量"):
        asyncio.run(personas.generate_draft(CONFIG, CAPABILITY, manual, count=3, days=50))
    assert all(body["response_format"]["json_schema"]["name"] in {"ProductSummary", "CohortPlan"} for body in bodies)


@pytest.mark.parametrize("bad_batch", [0, 1, 2])
def test_each_batch_must_have_the_exact_requested_size(monkeypatch, bad_batch):
    manual = read_manual(SAMPLE)
    slots = cohort(23, manual)
    calls = []

    async def model(client, config, capability, schema, prompt, validate, **kwargs):
        batch = len(calls)
        selected = slots[batch * 10:(batch + 1) * 10]
        if batch == bad_batch:
            selected = selected[:-1]
        data = {"slots": [slot.model_dump() for slot in selected]}
        if batch == 0:
            data["rationale"] = "测试分布"
        calls.append(batch)
        plan = schema.model_validate(data)
        validate(plan)
        return plan

    monkeypatch.setattr(personas, "request_json", model)
    with pytest.raises(ValueError, match="槽位数量"):
        asyncio.run(personas.plan_cohort(None, CONFIG, CAPABILITY, manual,
                                        ProductSummary.model_validate(PRODUCT), count=23, days=50))
    assert len(calls) == bad_batch + 1


def test_snapshot_remains_approved_after_the_original_is_edited(tmp_path, configured, draft):
    source = approved_source(tmp_path, draft)
    run = tmp_path / "phase4-audit"
    run.mkdir()
    snapshot, _ = phase4.snapshot_source(source, run)
    original_hash = phase1.draft_hash(snapshot)
    data = draft.model_dump(mode="json")
    data["run_config"]["duration_days"] = 50
    write_json(source / "draft.json", data)
    assert phase1.require_approved(snapshot)[0].run_config.duration_days == 1
    assert phase1.draft_hash(snapshot) == original_hash
    assert (snapshot / "product_model.json").is_file()


def test_history_uses_the_run_snapshot_not_the_current_draft(runs_root):
    run = runs_root / "phase4-x"
    snapshot = run / "approved_source"
    write_json(snapshot / "draft.json", {"run_config": {"duration_days": 1, "time_slice_minutes": 60}})
    write_json(snapshot / "product_model.json", {"metadata": {"name": "Original product"}})
    write_json(runs_root / "phase1-x" / "draft.json", {"run_config": {"duration_days": 50}})
    write_json(runs_root / "phase1-x" / "product_model.json", {"metadata": {"name": "Changed product"}})
    overview = Reader(runs_root).overview(run.name)
    assert overview["run_config"]["duration_days"] == 1
    assert overview["product"]["metadata"]["name"] == "Original product"


def test_a_draft_in_use_cannot_be_edited_or_rejected(tmp_path, configured, draft):
    source = approved_source(tmp_path, draft)
    displayed = phase1.draft_hash(source)
    write_json(tmp_path / "_jobs" / "simulate-active.json", {
        "id": "simulate-active", "kind": "simulate", "state": "running", "draft": source.name,
        "simulation": "phase4-active", "report": "phase5-active", "created_at": "2026-10-04T00:00:00+00:00", "steps": []})
    with pytest.raises(Busy):
        drafts.update_draft(tmp_path, source.name, displayed, duration_days=50)
    with pytest.raises(Busy):
        drafts.decide(tmp_path, source.name, "reject", displayed)
    assert phase1.draft_hash(source) == displayed
    assert phase1.require_approved(source)


def test_legacy_history_is_not_silently_changed_by_a_draft_edit(tmp_path, configured, draft):
    source = approved_source(tmp_path, draft)
    write_json(tmp_path / "phase4-legacy" / "run_context.json", {"source_run": str(source)})
    displayed = phase1.draft_hash(source)
    with pytest.raises(drafts.Invalid, match="旧运行"):
        drafts.update_draft(tmp_path, source.name, displayed, duration_days=50)
    assert phase1.draft_hash(source) == displayed


def test_community_deadline_accounts_for_cohort_and_model_queue():
    assert phase4.community_timeout(40, 1) >= 40 * personas.GENERATION_DEADLINE * 6
    assert phase4.community_timeout(40, 1) > phase4.community_timeout(40, 10)
    assert phase4.community_timeout(2, 10) >= 600


def test_scaled_deadline_is_used_for_both_steps_and_surveys(tmp_path, monkeypatch, configured, draft):
    source = approved_source(tmp_path, draft)
    config = {**SETTINGS, "provider": "openai_compatible", "api": "chat_completions",
              "max_model_concurrency": 1, "max_browser_concurrency": 1}
    monkeypatch.setattr(phase4, "settings", lambda: config)
    monkeypatch.setattr(phase4, "require_capabilities", lambda *args: CAPABILITY)
    calls = []

    class Process:
        returncode = 0

        async def wait(self):
            return 0

    async def process(*args, **kwargs):
        return Process()

    async def ready(store, process):
        store.set_metadata("community_state", "ready")

    async def command(store, process, kind, tick, logical, timeout):
        calls.append((kind, timeout))
        if kind == "finish":
            store.set_metadata("community_state", "closed")
        return {"active_personas": []}

    async def timeline(draft, rows, root, limit, on_slice_end):
        result = {"slices": [{"state": "completed"}], "jobs": {}}
        await on_slice_end(0, draft.run_config.start_time, [], result)
        return result

    monkeypatch.setattr(phase4.asyncio, "create_subprocess_exec", process)
    monkeypatch.setattr(phase4, "wait_ready", ready)
    monkeypatch.setattr(phase4, "command", command)
    monkeypatch.setattr(phase4, "run_timeline", timeline)
    monkeypatch.setattr(phase4, "finalize", lambda *args: {"passed": True})
    root = tmp_path / "phase4-audit"
    assert asyncio.run(phase4.execute(source, root))["passed"]
    budget = phase4.community_timeout(len(draft.personas), 1)
    assert calls == [("step", budget), ("finish", budget)]
    assert json.loads((root / "run_context.json").read_text(encoding="utf-8"))["source_snapshot"] == "approved_source"


@pytest.mark.parametrize("empty_findings", [False, True])
def test_quiet_or_finding_free_community_is_valid(tmp_path, empty_findings):
    person = fixture_persona(False).model_copy(update={"participation": "lurker"})
    draft = SimpleNamespace(personas=[person])
    store = SimulationStore(tmp_path / "run.db")
    store.initialize(draft, [{"persona_id": person.persona_id, "slice_index": 2}])
    save_fake_experience(tmp_path, person)
    if empty_findings:
        path = tmp_path / person.persona_id / "experience.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["assessment"]["findings"] = []
        write_json(path, data)
    store.publish_experience(person.persona_id, 2, tmp_path / person.persona_id)
    memory = store.experience(person.persona_id)
    store.record_disclosure(person.persona_id, 2, Disclosure(shared=[], withheld=[
        Withheld(finding_id=key, reason="私下保留") for key in finding_map(memory)], tone="brief"), "")
    store.survey(person.persona_id, survey(biggest_issue=None) if empty_findings else survey(), [])
    db = sqlite3.connect(tmp_path / "oasis.db")
    db.executescript("CREATE TABLE post(post_id,user_id,content); CREATE TABLE comment(comment_id,user_id,content); CREATE TABLE trace(user_id,action);")
    db.close()
    audit = phase4.audit_social(store, draft, tmp_path / "oasis.db")
    gc.collect()
    assert audit["passed"], audit


def test_finding_free_run_can_finish_a_model_report(runs_root, tmp_path, monkeypatch):
    from orchestrator import phase5
    from report.agent import Step

    run = runs_root / "phase4-x"
    db = sqlite3.connect(run / "run.db")
    for pid, text in db.execute("SELECT persona_id, memory_json FROM experiences").fetchall():
        memory = json.loads(text)
        memory["assessment"]["findings"] = []
        write_json(run / pid / "experience.json", memory)
        db.execute("UPDATE experiences SET memory_json=? WHERE persona_id=?", (json.dumps(memory), pid))
        answer = json.loads(db.execute("SELECT answer_json FROM surveys WHERE persona_id=?", (pid,)).fetchone()[0])
        answer["biggest_issue"] = None
        db.execute("UPDATE surveys SET answer_json=? WHERE persona_id=?", (json.dumps(answer), pid))
    db.execute("UPDATE disclosures SET withheld_json='[]'")
    db.commit()
    db.close()

    async def investigate(*args):
        return Step(action="final", category=None, persona_id=None, offset=None, limit=None, issues=[], highlights=[]), []

    monkeypatch.setattr(phase5, "settings", lambda: {**CONFIG, "provider": "openai_compatible"})
    monkeypatch.setattr(phase5, "require_capabilities", lambda *args: CAPABILITY)
    monkeypatch.setattr(phase5, "investigate", investigate)
    result = asyncio.run(phase5.execute(run, tmp_path / "empty-report", tmp_path, True))
    assert result["passed"] and result["issues"] == result["highlights"] == 0


def test_all_cited_personas_count_even_when_there_are_more_than_four():
    records, people = {}, {}
    for index in range(1, 7):
        pid = f"p{index:02d}"
        people[pid] = {"persona": {"participation": "poster"}}
        records[f"{pid}:f001"] = {"ref_id": f"{pid}:f001", "persona_id": pid, "category": "experience", "kind": "pain",
                                    "path": "run.db", "data": {"title": "按钮无反馈", "observed_quote": "生成清单"}}
    store = SimpleNamespace(records=records, people=people, memories={})
    prompt = agent_prompt(store, [], True, {"personas": 6, "task_outcomes": {}, "nps": None, "coverage_notes": []})
    assert "最多引用 4 条" not in prompt
    claim = Claim(title="按钮无反馈", detail="同一问题影响多人", severity=4,
                  citations=[{"ref_id": ref, "quote": "生成清单"} for ref in records])
    result = describe(claim, store, "pain")
    assert len(result["affected_personas"]) == 6 and len(result["evidence"]) == 6
    assert result["score"] == 24
