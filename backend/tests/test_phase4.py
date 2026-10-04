import asyncio
import json
import logging
import sqlite3
from types import SimpleNamespace

import pytest

from core.community import (Disclosure, ExitAnswer, Withheld, allowed_actions, finding_map, public_projection,
                            validate_disclosure, validate_exit, consistency_flags)
from core.experience import ExperienceMemory
from core.simulation import SimulationStore
from tests.test_phase2 import memory_data
from tests.test_phase3 import save_fake_experience, timeline_draft
from tests.verify_phase2 import fixture_persona
from orchestrator import phase3, phase4


def private_memory():
    data = memory_data()
    for snapshot in data["snapshots"]:
        snapshot["text"] += "\nPRIVATE_SENTINEL"
    data["assessment"]["findings"].append({"kind": "pain", "title": "私人痛点", "description": "PRIVATE_SENTINEL",
        "evidence_ids": ["before"], "technical_event_ids": [], "observed_quote": "PRIVATE_SENTINEL"})
    return ExperienceMemory.model_validate(data)


def test_shared_projection_cannot_publish_withheld_material():
    memory = private_memory()
    keys = list(finding_map(memory))
    plan = Disclosure(shared=[keys[0]], withheld=[Withheld(finding_id=keys[1], reason="不想暴露困难")], tone="soft")
    validate_disclosure(plan, memory, "poster")
    body = public_projection(plan, memory)
    assert "生成清单" in body and "PRIVATE_SENTINEL" not in body and "私人痛点" not in body


@pytest.mark.parametrize("bad", ["missing", "overlap", "foreign", "lurker"])
def test_disclosure_partition_and_participation_are_locally_validated(bad):
    memory = private_memory()
    keys = list(finding_map(memory))
    plan = Disclosure(shared=[keys[0]], withheld=[Withheld(finding_id=keys[1], reason="私下保留")], tone="direct")
    if bad == "missing":
        plan.withheld = []
    elif bad == "overlap":
        plan.shared.append(keys[1])
    elif bad == "foreign":
        plan.shared = ["another-person:f001"]
    with pytest.raises(ValueError):
        validate_disclosure(plan, memory, "lurker" if bad == "lurker" else "poster")


@pytest.mark.parametrize("role", ["poster", "commenter", "reactor", "lurker"])
def test_before_experience_every_role_is_read_only(role):
    assert allowed_actions(role, False, "body") == {"refresh", "do_nothing"}
    if role in {"reactor", "lurker"}:
        assert not {"create_post", "create_comment"} & allowed_actions(role, True, "body")


def test_sqlite_exchange_preserves_reads_and_publishes_only_verified_memories(tmp_path):
    person = fixture_persona(False)
    store = SimulationStore(tmp_path / "run.db")
    store.initialize(SimpleNamespace(personas=[person]), [{"persona_id": person.persona_id, "slice_index": 2}])
    assert store.experience(person.persona_id) is None
    store.record_reads(person.persona_id, 1, [{"post_id": 7, "content": "有人说按钮没有反馈", "comments": []}], False)
    expectations = store.expectations(person.persona_id)
    assert "#7" in expectations[0] and "尚非我的亲身体验" in expectations[0]
    save_fake_experience(tmp_path, person)
    result = tmp_path / person.persona_id / "result.json"
    content = json.loads(result.read_text(encoding="utf-8"))
    content["passed"] = False
    result.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError, match="verified experience"):
        store.publish_experience(person.persona_id, 2, tmp_path / person.persona_id)
    content["passed"] = True
    result.write_text(json.dumps(content), encoding="utf-8")
    store.publish_experience(person.persona_id, 2, tmp_path / person.persona_id)
    assert store.experience(person.persona_id).persona_id == person.persona_id
    assert store.read_posts(person.persona_id)[7]["content"] == "有人说按钮没有反馈"


def survey(**changes):
    data = {"has_experience": True, "nps": 9, "continue_using": "yes", "would_pay": "unsure", "biggest_issue": "p01:f001",
            "favorite": None, "unsaid": [], "opinion_changed": False, "influencing_post_ids": [], "explanation": "私下回答"}
    return ExitAnswer.model_validate({**data, **changes})


def test_questionnaire_references_actual_experience_and_actual_reads():
    memory = private_memory()
    validate_exit(survey(), memory, {7})
    with pytest.raises(ValueError, match="actually read"):
        validate_exit(survey(opinion_changed=True, influencing_post_ids=[99]), memory, {7})
    with pytest.raises(ValueError, match="did not experience"):
        validate_exit(survey(biggest_issue="other:f001"), memory, {7})
    with pytest.raises(ValueError, match="no fabricated NPS"):
        validate_exit(survey(), None, {7})
    assert "high_nps_after_unsuccessful_task_requires_review" in consistency_flags(survey(), memory)
    answer = survey(unsaid=[Withheld(finding_id="p01:f001", reason="没说出来")])
    assert "unsaid_item_was_publicly_expressed_requires_review" in consistency_flags(answer, memory, {"p01:f001"})


def test_missing_experience_is_marked_without_fabricated_questionnaire(tmp_path):
    from discussion.survey import answer_exit
    person = fixture_persona(False)
    store = SimulationStore(tmp_path / "run.db")
    store.initialize(SimpleNamespace(personas=[person]), [{"persona_id": person.persona_id, "slice_index": 2}])
    asyncio.run(answer_exit(None, {}, {}, person, store))
    # A partial retry preserves the original answer and does not call the model again.
    asyncio.run(answer_exit(None, {}, {}, person, store))
    with store.connect() as db:
        rows = db.execute("SELECT answer_json FROM surveys").fetchall()
    assert len(rows) == 1
    answer = ExitAnswer.model_validate_json(rows[0][0])
    validate_exit(answer, None, set())
    assert answer.nps is None and "系统缺失标记" in answer.explanation


def test_questionnaire_retry_only_fills_missing_persona(tmp_path, monkeypatch):
    from discussion import survey as module
    person = fixture_persona(False)
    store = SimulationStore(tmp_path / "run.db")
    store.initialize(SimpleNamespace(personas=[person]), [{"persona_id": person.persona_id, "slice_index": 2}])
    save_fake_experience(tmp_path, person)
    store.publish_experience(person.persona_id, 2, tmp_path / person.persona_id)
    calls = []

    async def request(*args, **kwargs):
        calls.append(args[4])
        result = survey()
        kwargs["validate"](result)
        return result

    monkeypatch.setattr(module, "request_json", request)
    asyncio.run(module.answer_exit(None, {}, {}, person, store))
    asyncio.run(module.answer_exit(None, {}, {}, person, store))
    assert len(calls) == 1
    assert '"session"' not in calls[0]


def test_social_audit_rejects_questionnaire_without_real_experience(tmp_path):
    person = fixture_persona(False).model_copy(update={"participation": "poster"})
    draft = SimpleNamespace(personas=[person])
    store = SimulationStore(tmp_path / "run.db")
    store.initialize(draft, [{"persona_id": person.persona_id, "slice_index": 2}])
    save_fake_experience(tmp_path, person)
    store.publish_experience(person.persona_id, 2, tmp_path / person.persona_id)
    memory = store.experience(person.persona_id)
    plan = Disclosure(shared=[], withheld=[Withheld(finding_id=key, reason="私下保留") for key in finding_map(memory)], tone="brief")
    store.record_disclosure(person.persona_id, 2, plan, "")
    with sqlite3.connect(tmp_path / "oasis.db") as db:
        db.executescript("CREATE TABLE post(post_id,user_id,content); CREATE TABLE comment(comment_id,user_id,content); "
                         "CREATE TABLE trace(user_id,action);")
    store.survey(person.persona_id, survey(has_experience=False, nps=None), [])
    audit = phase4.audit_social(store, draft, tmp_path / "oasis.db")
    assert not audit["passed"]
    assert "no fabricated NPS" in audit["survey_errors"][0]["reason"]


def test_social_audit_records_invalid_disclosure_instead_of_crashing(tmp_path):
    person = fixture_persona(False).model_copy(update={"participation": "poster"})
    draft = SimpleNamespace(personas=[person])
    store = SimulationStore(tmp_path / "run.db")
    store.initialize(draft, [{"persona_id": person.persona_id, "slice_index": 2}])
    save_fake_experience(tmp_path, person)
    store.publish_experience(person.persona_id, 2, tmp_path / person.persona_id)
    # Covers no finding id: not a partition of this persona's experience.
    store.record_disclosure(person.persona_id, 2, Disclosure(shared=[], withheld=[], tone="brief"), "")
    with sqlite3.connect(tmp_path / "oasis.db") as db:
        db.executescript("CREATE TABLE post(post_id,user_id,content); CREATE TABLE comment(comment_id,user_id,content); "
                         "CREATE TABLE trace(user_id,action);")
    (tmp_path / "planner_rejections.jsonl").write_text(
        '{"persona_id":"p01","attempt":1,"reason":"x"}\n{"persona_id":"p01","fallback":"do_nothing"}\n', encoding="utf-8")
    audit = phase4.audit_social(store, draft, tmp_path / "oasis.db")
    assert not audit["passed"] and "partition" in audit["public_projection_errors"][0]["reason"]
    assert audit["planner_rejected_attempts"] == 1 and audit["planner_fallbacks_to_do_nothing"] == 1


def test_browse_then_social_callback_drains_each_slice_before_advancing(tmp_path):
    rows = [{"persona_id": "p01", "slice_index": 0}, {"persona_id": "p02", "slice_index": 1}]
    calls = []
    async def worker(root, pid):
        calls.append(("browse", pid))
        return 0
    async def social(tick, logical, group, timeline):
        assert all(timeline["jobs"][row["persona_id"]]["state"] == "completed" for row in group)
        calls.append(("social", tick))
    asyncio.run(phase3.run_timeline(timeline_draft(), rows, tmp_path, 2, worker, social))
    assert calls[:4] == [("browse", "p01"), ("social", 0), ("browse", "p02"), ("social", 1)]


def test_phase4_approval_gate_precedes_creating_database_or_process(tmp_path, monkeypatch):
    def unapproved(path):
        raise ValueError("not approved")
    monkeypatch.setattr(phase4, "require_approved", unapproved)
    with pytest.raises(ValueError, match="not approved"):
        asyncio.run(phase4.execute(tmp_path / "source", tmp_path / "output"))
    assert not (tmp_path / "output").exists()


def test_command_failure_and_completion_are_visible_across_connections(tmp_path):
    store = SimulationStore(tmp_path / "run.db")
    store.initialize(SimpleNamespace(personas=[]), [])
    identifier = store.enqueue("step", 1, "2026-10-03T01:00:00+00:00")
    second = SimulationStore(store.path)
    assert second.next_command()["command_id"] == identifier
    assert store.command_result(identifier)["state"] == "running"
    second.complete_command(identifier, {"error_type": "ValueError"}, failed=True)
    assert store.command_result(identifier)["state"] == "failed"


def test_input_action_timeout_is_not_misclassified_as_dom_failure():
    from browsing.probe import LogCounter
    counter = LogCounter()
    message = "TypeTextEvent handler timed out after 60.0s"
    counter.emit(logging.LogRecord("browser_use", logging.ERROR, "", 0, message, (), None))
    assert counter.dom_failures == 0
    counter.emit(logging.LogRecord("browser_use", logging.ERROR, "", 0, "DOM build failed: snapshot unavailable", (), None))
    assert counter.dom_failures == 1


def test_browser_worker_receives_third_party_expectations_from_shared_database(tmp_path, monkeypatch):
    from browsing import worker, experience
    person = fixture_persona(False)
    store = SimulationStore(tmp_path / "run.db")
    store.initialize(SimpleNamespace(personas=[person]), [{"persona_id": person.persona_id, "slice_index": 2}])
    store.record_reads(person.persona_id, 1, [{"post_id": 11, "content": "有人说页面很清楚"}], False)
    context = {"source_run": "source", "configuration_sha256": "config", "approved_draft_sha256": "approved",
               "simulation_database": str(store.path), "schedule": [{"persona_id": person.persona_id, "slice_index": 2}]}
    (tmp_path / "run_context.json").write_text(json.dumps(context), encoding="utf-8")
    received = []
    async def run(config, capability, manual, persona, directory, expectations):
        received.extend(expectations)
        save_fake_experience(tmp_path, persona)
        return {"passed": True}
    monkeypatch.setattr(worker, "settings", lambda: {})
    monkeypatch.setattr(worker, "configuration_hash", lambda config: "config")
    monkeypatch.setattr(worker, "require_approved", lambda path: (SimpleNamespace(personas=[person]), None))
    monkeypatch.setattr(worker, "require_capabilities", lambda *args: {})
    monkeypatch.setattr(worker, "draft_hash", lambda path: "approved")
    monkeypatch.setattr(experience, "run_experience", run)
    assert asyncio.run(worker.execute(tmp_path / "run_context.json", person.persona_id))["passed"]
    assert len(received) == 1 and "#11" in received[0] and "尚非我的亲身体验" in received[0]
