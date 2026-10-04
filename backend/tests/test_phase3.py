import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import time

import httpx
import pytest
from openai import AsyncOpenAI

from browsing.worker import configuration_hash, execute as execute_worker
from browsing.policy import GuardedTools
from core.llm import create
from core.experience import Assessment, Completion, ExperienceMemory
from core.usage import UsageRecorder
from orchestrator import phase3
from tests.test_phase2 import FakeCollector, memory_data
from tests.verify_phase2 import fixture_manual, fixture_persona


def timeline_draft():
    return SimpleNamespace(run_config=SimpleNamespace(start_time=datetime(2026, 10, 3, tzinfo=timezone.utc),
        duration_days=1, time_slice_minutes=60, max_concurrency=2))


WORK_SECONDS = 0.05


@pytest.mark.parametrize("limit", [1, 2, 5])
def test_timeline_queues_peers_and_waits_before_advancing_clock(tmp_path, limit):
    rows = [{"persona_id": f"p{i:02d}", "slice_index": 0 if i <= 6 else 1, "utc_time": "2026-10-03T00:00:00+00:00"}
            for i in range(1, 11)]
    active, peak, completed_first, calls = 0, 0, set(), []
    async def worker(root, pid):
        nonlocal active, peak
        number = int(pid[1:])
        if number > 6:
            assert completed_first == {f"p{i:02d}" for i in range(1, 7)}
        active += 1
        peak = max(peak, active)
        calls.append(pid)
        await asyncio.sleep(WORK_SECONDS)
        active -= 1
        if number <= 6:
            completed_first.add(pid)
        return 0
    result = asyncio.run(phase3.run_timeline(timeline_draft(), rows, tmp_path, limit, worker))
    assert len(calls) == 10 and len(set(calls)) == 10
    assert peak == limit and result["peak_workers"] == limit
    assert all(job["state"] == "completed" for job in result["jobs"].values())
    # asyncio treats a timer as due within one clock resolution (15.625 ms on Windows), so a queued
    # persona's measured wait for a full worker run can fall short of WORK_SECONDS by at most that much.
    assert max(job["queue_seconds"] for job in result["jobs"].values()) >= WORK_SECONDS - time.get_clock_info("monotonic").resolution
    assert len(result["slices"]) == 24 and all(item["state"] == "completed" for item in result["slices"])


def test_failed_persona_does_not_cancel_remaining_cohort(tmp_path):
    rows = [{"persona_id": f"p{i:02d}", "slice_index": 0} for i in range(1, 11)]
    called = []
    async def worker(root, pid):
        called.append(pid)
        if pid == "p03":
            raise RuntimeError("worker failed")
        return 1 if pid == "p04" else 0
    result = asyncio.run(phase3.run_timeline(timeline_draft(), rows, tmp_path, 2, worker))
    assert len(called) == 10
    assert result["jobs"]["p03"]["state"] == result["jobs"]["p04"]["state"] == "failed"
    assert result["jobs"]["p10"]["state"] == "completed"


def test_cancellation_stops_workers_and_preserves_queue_state(tmp_path):
    rows = [{"persona_id": f"p{i:02d}", "slice_index": 0} for i in range(1, 11)]
    stopped = []
    async def worker(root, pid):
        try:
            await asyncio.sleep(10)
        finally:
            stopped.append(pid)
    async def run():
        task = asyncio.create_task(phase3.run_timeline(timeline_draft(), rows, tmp_path, 2, worker))
        await asyncio.sleep(0.03)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    saved = json.loads((tmp_path / "timeline.json").read_text(encoding="utf-8"))
    assert len(stopped) == 2 and all(job["state"] == "cancelled" for job in saved["jobs"].values())


def test_runtime_gateway_rejects_forged_non_developer_tool_list():
    persona = fixture_persona(False).model_copy(deep=True)
    persona.browsing_profile.tools = ["read_console", "list_failed_requests"]
    tools = GuardedTools(persona, fixture_manual(), FakeCollector(), None, {}, {}, Completion)
    assert not {"read_console", "list_failed_requests"} & tools.registry.registry.actions.keys()
    assert tools.technical_result("read_console", FakeCollector().console()).error
    assert tools.collector.events[-1]["event"] == "technical_access_denied"


def test_quote_repair_feedback_identifies_all_bad_findings():
    data = memory_data()
    data["assessment"]["findings"][0]["observed_quote"] = "invented first quote"
    data["assessment"]["findings"].append({**data["assessment"]["findings"][0], "title": "second finding", "observed_quote": "invented second quote"})
    with pytest.raises(ValueError) as error:
        ExperienceMemory.model_validate(data)
    assert "findings[0]" in str(error.value) and "findings[1]" in str(error.value)
    assert "invented first quote" in str(error.value) and "invented second quote" in str(error.value)


def test_unrepairable_claim_is_rejected_without_changing_evidence(tmp_path, monkeypatch):
    from browsing import experience
    memory = ExperienceMemory.model_validate(memory_data())
    assessment = memory.assessment.model_copy(deep=True)
    assessment.findings.append(assessment.findings[0].model_copy(update={"observed_quote": "invented quote"}))
    async def exhausted(*args, validate, **kwargs):
        with pytest.raises(ValueError):
            validate(assessment)
        raise ValueError("repair exhausted")
    monkeypatch.setattr(experience, "request_json", exhausted)
    result = asyncio.run(experience.assess_memory(None, {}, {}, fixture_persona(False), memory, tmp_path))
    assert len(result.findings) == 1 and result.findings[0].observed_quote == "生成清单"
    assert memory.snapshots[0].text == "生成清单"
    rejected = json.loads((tmp_path / "assessment_rejections.json").read_text(encoding="utf-8"))
    assert rejected[0]["finding"]["observed_quote"] == "invented quote" and rejected[0]["reason"]


@pytest.mark.parametrize("api", ["chat_completions", "responses"])
def test_usage_ledger_counts_repairs_and_uses_provider_cache_semantics(tmp_path, api):
    bodies = []
    def respond(request):
        bodies.append(json.loads(request.content))
        usage = {"prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1100,
                 "prompt_cache_hit_tokens": 600, "prompt_tokens_details": {"cached_tokens": 0}}
        if api == "responses":
            return httpx.Response(200, json={"id": "r", "object": "response", "created_at": 0, "model": "custom", "status": "completed",
                "output": [], "usage": {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100,
                "input_tokens_details": {"cached_tokens": 600}, "output_tokens_details": {"reasoning_tokens": 0}}})
        return httpx.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": "custom",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}], "usage": usage})
    config = {"provider": "deepseek", "model": "deepseek-flash", "api": api, "thinking_type": "disabled"}
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            async with AsyncOpenAI(api_key="secret", base_url="https://test.invalid/v1", http_client=transport) as client:
                with UsageRecorder(config, tmp_path):
                    for _ in range(2):
                        await create(client, config, [{"role": "user", "content": "private product data"}], 128, 5, "repair")
    asyncio.run(run())
    summary = json.loads((tmp_path / "model_usage.json").read_text(encoding="utf-8"))
    assert summary["requests"] == 2 and summary["tokens"]["cached_input_tokens"] == 1200
    assert summary["tokens"]["uncached_input_tokens"] == 800
    assert not any("usd" in key or "price" in key for key in summary)
    ledger = (tmp_path / "model_usage.jsonl").read_text(encoding="utf-8")
    assert "secret" not in ledger and "private product data" not in ledger


def test_failed_request_is_counted_without_usage(tmp_path):
    with UsageRecorder({"provider": "openai_compatible", "model": "custom"}, tmp_path) as recorder:
        recorder.record("chat_completions", "custom", time.monotonic(), error=TimeoutError())
    summary = json.loads((tmp_path / "model_usage.json").read_text(encoding="utf-8"))
    assert summary["failed_requests"] == summary["requests_without_usage"] == 1


def test_repair_metering_appends_without_discarding_initial_attempt_usage(tmp_path):
    config = {"provider": "deepseek", "model": "deepseek-flash"}
    response = SimpleNamespace(usage={"prompt_tokens": 100, "completion_tokens": 10})
    for _ in range(2):
        with UsageRecorder(config, tmp_path) as recorder:
            recorder.record("chat_completions", "deepseek-flash", time.monotonic(), response=response)
    summary = json.loads((tmp_path / "model_usage.json").read_text(encoding="utf-8"))
    entries = [json.loads(line) for line in (tmp_path / "model_usage.jsonl").read_text(encoding="utf-8").splitlines()]
    assert summary["requests"] == 2 and summary["tokens"]["input_tokens"] == 200
    assert [entry["request"] for entry in entries] == [1, 2]


def test_reusing_experience_directory_cannot_overwrite_existing_usage_record(tmp_path):
    from browsing.experience import run_experience
    record = tmp_path / "model_usage.json"
    record.write_text('{"requests":87}', encoding="utf-8")
    with pytest.raises(ValueError, match="fresh experience directory"):
        asyncio.run(run_experience({}, {}, fixture_manual(), fixture_persona(False), tmp_path))
    assert record.read_text(encoding="utf-8") == '{"requests":87}'


def test_approval_gate_prevents_any_phase3_artifacts(tmp_path, monkeypatch):
    def unapproved(path):
        raise ValueError("not approved")
    monkeypatch.setattr(phase3, "require_approved", unapproved)
    with pytest.raises(ValueError, match="not approved"):
        asyncio.run(phase3.execute(tmp_path / "source", tmp_path / "output"))
    assert not (tmp_path / "output").exists()


def test_phase3_uses_environment_minimum_and_keeps_keys_out_of_context(tmp_path, monkeypatch):
    draft = timeline_draft()
    draft.run_config.max_concurrency = 5
    config = {"provider": "deepseek", "model": "deepseek-flash", "api": "responses", "thinking_type": "disabled",
              "base_url": "https://test.invalid", "api_key": "private-model-key", "steel_api_key": "private-steel-key",
              "max_model_concurrency": 2, "max_browser_concurrency": 8}
    observed = []
    async def timeline(d, rows, root, limit):
        observed.append(limit)
        return {}
    monkeypatch.setattr(phase3, "require_approved", lambda path: (draft, None))
    monkeypatch.setattr(phase3, "settings", lambda: config)
    monkeypatch.setattr(phase3, "require_capabilities", lambda *args: {})
    monkeypatch.setattr(phase3, "draft_hash", lambda path: "approved-hash")
    monkeypatch.setattr(phase3, "schedule_rows", lambda d: [])
    monkeypatch.setattr(phase3, "run_timeline", timeline)
    monkeypatch.setattr(phase3, "summarize", lambda *args: {"passed": True})
    output = tmp_path / "output"
    assert asyncio.run(phase3.execute(tmp_path / "source", output))["passed"]
    context = (output / "run_context.json").read_text(encoding="utf-8")
    assert observed == [2] and "private-model-key" not in context and "private-steel-key" not in context


def test_worker_refuses_configuration_drift_before_loading_personas(tmp_path, monkeypatch):
    from browsing import worker
    config = {key: "value" for key in ("provider", "model", "api", "base_url", "api_key", "steel_api_key", "thinking_type",
              "max_model_concurrency", "max_browser_concurrency")}
    context = {"configuration_sha256": configuration_hash(config)}
    (tmp_path / "run_context.json").write_text(json.dumps(context), encoding="utf-8")
    monkeypatch.setattr(worker, "settings", lambda: dict(config, max_browser_concurrency=1))
    with pytest.raises(ValueError, match="Configuration changed"):
        asyncio.run(execute_worker(tmp_path / "run_context.json", "p01"))


def save_fake_experience(root, persona, grant=False):
    pid = persona.persona_id
    directory = root / pid
    directory.mkdir()
    data = memory_data()
    data["persona_id"] = pid
    data["session"]["simulation"] = {"slice_index": 0}
    (directory / "screenshots").mkdir()
    import hashlib
    for snapshot in data["snapshots"]:
        (directory / snapshot["screenshot"]).write_bytes(b"evidence")
        snapshot["screenshot_sha256"] = hashlib.sha256(b"evidence").hexdigest()
    (directory / "experience.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result = {"passed": True, "released": True}
    (directory / "result.json").write_text(json.dumps(result), encoding="utf-8")
    usage = {"requests": 1, "requests_without_usage": 0,
             "tokens": {"input_tokens": 100, "cached_input_tokens": 20, "uncached_input_tokens": 80, "output_tokens": 10}}
    (directory / "model_usage.json").write_text(json.dumps(usage), encoding="utf-8")
    (directory / "model_usage.jsonl").write_text(json.dumps({"started_at": "2026-10-03T00:00:00+00:00", "finished_at": "2026-10-03T00:00:01+00:00"}), encoding="utf-8")
    rows = [{"event": "technical_tool_access", "data": {"tool": "read_console"}}] if grant else []
    (directory / "raw_trace.jsonl").write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


@pytest.mark.parametrize("violation", [False, True])
@pytest.mark.parametrize("size", [10, 12])
def test_cohort_audit_and_usage_aggregate_actual_persona_artifacts(tmp_path, violation, size):
    people = [fixture_persona(False).model_copy(update={"persona_id": f"p{i:02d}"}) for i in range(1, size + 1)]
    for person in people:
        save_fake_experience(tmp_path, person, grant=violation and person.persona_id == "p04")
    timeline = {"jobs": {p.persona_id: {"state": "completed"} for p in people}, "peak_workers": 2}
    result = phase3.summarize(SimpleNamespace(personas=people), tmp_path, timeline,
                            {"max_model_concurrency": 30, "max_browser_concurrency": 5})
    # Pass/fail depends on evidence and permissions, not on the cohort being exactly ten or on known prices.
    assert result["passed"] is (not violation)
    assert result["usage"]["model_requests"] == size and result["usage"]["model_tokens"]["input_tokens"] == 100 * size
    audit = json.loads((tmp_path / "permission_audit.json").read_text(encoding="utf-8"))
    assert audit["complete"] and len(audit["audited_personas"]) == size
    assert not (tmp_path / "cost.json").exists()
    assert bool(result["permission_violations"]) is violation
