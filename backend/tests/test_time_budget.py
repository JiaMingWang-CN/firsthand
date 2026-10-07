"""Browsing time follows the step limit, within the Steel plan's session cap; running out of time is a runtime limit."""

import asyncio
import json
import shutil
import time
from datetime import datetime, timezone
from types import SimpleNamespace

from browsing import experience
from core.experience import ExperienceMemory
from core.persona import GENERATED_STEPS, LIMITS, Persona
from core.runtime import write_json
from tests.test_phase2 import FakeCollector, FakeHistory, record_action
from tests.verify_phase2 import fixture_manual, fixture_persona


def with_steps(patience, steps):
    persona = fixture_persona(False).model_dump()
    persona["browsing_profile"].update(patience=patience, max_steps=steps, stall_limit=min(LIMITS[patience][1], steps))
    return Persona.model_validate(persona)


def test_session_length_follows_the_step_limit_up_to_the_plan_cap():
    assert experience.session_seconds(with_steps("low", 15)) == 15 * 25 + 90
    assert experience.session_seconds(with_steps("normal", 25)) == 25 * 25 + 90
    assert experience.session_seconds(with_steps("normal", 40)) == 900  # drafts made before the change keep 40 steps
    assert experience.session_seconds(with_steps("high", 80)) == 900


def test_new_personas_get_fewer_steps_at_normal_patience():
    from orchestrator import personas
    assert GENERATED_STEPS["normal"] == 25 and LIMITS["normal"][0] == 40
    assert personas.GENERATED_STEPS is GENERATED_STEPS


def test_running_out_of_time_stops_between_steps_like_a_step_limit():
    recorder = experience.StepRecorder(FakeCollector(), fixture_persona(True))  # stall_limit 6: only time stops it
    recorder.deadline = time.monotonic() + 2 * experience.STEP_SECONDS + 5
    agent = SimpleNamespace(history=FakeHistory(), state=SimpleNamespace(stopped=False, last_result=[]))

    async def run():
        await recorder.before(agent)
        record_action(agent, {"click": {"index": 1}})
        await recorder.after(agent)
        assert not await recorder.should_stop()  # enough time left for one more step
        recorder.deadline -= 10
        await recorder.before(agent)
        record_action(agent, {"scroll": {"down": True}})
        await recorder.after(agent)
    asyncio.run(run())
    assert agent.state.stopped and recorder.time_limited and "时间" in recorder.stop_reason and len(recorder.steps) == 2


def test_a_step_that_overruns_the_time_left_is_a_runtime_limit_not_an_infrastructure_failure(tmp_path, monkeypatch):
    created = []

    class Steel:
        def __init__(self, **kwargs):
            self.sessions = self
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def create(self, **kwargs):
            created.append(kwargs)
            return SimpleNamespace(id="session", websocket_url="wss://test.invalid", session_viewer_url="https://viewer.invalid",
                                   created_at=datetime.now(timezone.utc))
        async def release(self, sid):
            pass

    class Browser:
        def __init__(self, **kwargs):
            pass
        async def start(self):
            pass
        async def navigate_to(self, url):
            pass
        async def kill(self):
            pass

    class Collector:
        snapshots, events = [], []
        def __init__(self, *args):
            pass
        async def attach(self):
            pass
        async def prepare(self, persona):
            pass
        def record(self, *args):
            pass
        def close(self):
            pass

    class Guard:
        def __init__(self, *args):
            pass
        async def attach(self):
            pass
        def check(self):
            pass
        async def close(self):
            pass

    class Agent:
        def __init__(self, **kwargs):
            self.settings = SimpleNamespace()
        async def run(self, **kwargs):
            await asyncio.sleep(60)  # a step that never ends in time

    for name, value in {"AsyncSteel": Steel, "BrowserSession": Browser, "EvidenceCollector": Collector, "NavigationGuard": Guard,
                        "Agent": Agent, "GuardedTools": lambda *args: SimpleNamespace(observed_technical_events={}),
                        "ProviderChatOpenAI": lambda **kwargs: SimpleNamespace(requests_sent=0, requests_with_images=0),
                        "session_seconds": lambda persona: 21}.items():
        monkeypatch.setattr(experience, name, value)
    config = {"provider": "deepseek", "model": "custom", "base_url": "https://test.invalid/v1", "api_key": "test",
              "steel_api_key": "test", "api": "chat_completions", "thinking_type": "disabled"}
    output = tmp_path / "experience"
    result = asyncio.run(experience.run_experience(config, {"vision": False, "checks": {"json_schema": {"supported": True}}}, fixture_manual(), fixture_persona(False), output))
    assert created[0]["api_timeout"] == 21_000
    assert result["time_limited"] is True and result["session_seconds"] == 21
    memory = ExperienceMemory.model_validate_json((output / "experience.json").read_text(encoding="utf-8"))
    assert memory.outcome == "abandoned" and memory.outcome_source == "runtime_limit" and not memory.infrastructure_errors


def test_the_report_names_people_who_ran_out_of_time(source, tmp_path):
    from orchestrator.phase5 import execute
    run = tmp_path / "phase4-slow"
    shutil.copytree(source, run)
    write_json(run / "phase4_result.json", {"passed": True})
    write_json(run / "run_context.json", {"source_run": str(tmp_path / "phase1-slow"), "configuration": {"provider": "fixture"}})
    write_json(run / "p02" / "result.json", {"time_limited": True})
    write_json(run / "p01" / "result.json", {"time_limited": False})
    asyncio.run(execute(run, tmp_path / "phase5-slow", None, False))
    notes = json.loads((tmp_path / "phase5-slow" / "report.json").read_text(encoding="utf-8"))["overview"]["coverage_notes"]
    assert any("1 人（p02）浏览时间达到上限" in note for note in notes)
