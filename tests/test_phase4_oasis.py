import asyncio
import importlib.util
import json
import hashlib
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import httpx
import pytest

if importlib.util.find_spec("oasis") is None:
    pytest.skip("OASIS runs in its separate environment", allow_module_level=True)


def test_real_oasis_tools_block_pre_experience_lurker_and_private_text(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from oasis import ActionType, ManualAction
    from discussion.community import Community
    from core.community import Disclosure, Withheld, finding_map, public_projection
    from core.simulation import SimulationStore
    from tests.verify_phase2 import fixture_persona
    from core.experience import ExperienceMemory
    def save_memory(directory, persona):
        directory.mkdir()
        (directory / "screenshots").mkdir()
        for name in ("before", "after"):
            (directory / "screenshots" / f"{name}.png").write_bytes(b"evidence")
        memory = ExperienceMemory.model_validate({"persona_id": persona.persona_id, "state_at_browse": "fixture",
            "assignment": persona.browsing_profile.assignment.model_dump(), "expectations": [], "outcome": "success", "reason": "fixture",
            "outcome_source": "agent_self_report", "session": {}, "infrastructure_errors": [], "observed_technical_events": [],
            "snapshots": [{"evidence_id": name, "url": "https://example.com", "title": "fixture", "text": "PUBLIC_ONLY",
                "screenshot": f"screenshots/{name}.png", "screenshot_sha256": hashlib.sha256(b"evidence").hexdigest(),
                "scroll_x": 0, "scroll_y": 0, "video_seconds": i} for i, name in enumerate(("before", "after"))],
            "steps": [], "assessment": {"emotions": [], "summary": "fixture", "findings": [{"kind": "highlight", "title": "公开体验",
                "description": "fixture", "evidence_ids": ["before"], "technical_event_ids": [], "observed_quote": "PUBLIC_ONLY"}]}})
        (directory / "experience.json").write_text(memory.model_dump_json(), encoding="utf-8")
        (directory / "result.json").write_text('{"passed":true}', encoding="utf-8")
    poster = fixture_persona(False).model_copy(update={"participation": "poster"})
    lurker = fixture_persona(True).model_copy(update={"participation": "lurker"})
    draft = SimpleNamespace(personas=[poster, lurker], run_config=SimpleNamespace(start_time=__import__('datetime').datetime(2026, 10, 3, tzinfo=__import__('datetime').timezone.utc)))
    store = SimulationStore(tmp_path / "run.db")
    store.initialize(draft, [{"persona_id": p.persona_id, "slice_index": 1} for p in draft.personas])
    root = tmp_path / "community"
    root.mkdir()
    config = {"provider": "deepseek", "model": "custom", "base_url": "https://test.invalid/v1", "api_key": "test",
              "thinking_type": "disabled", "api": "responses", "max_model_concurrency": 2, "max_browser_concurrency": 1}

    async def run():
        community = Community(draft, store, root, config, {}, "test-seed")
        await community.start()
        try:
            actor = community.agents[poster.persona_id]
            actor.configure(poster, store, 0, "public")
            with pytest.raises(PermissionError):
                await community.env.step({actor: ManualAction(ActionType.CREATE_POST, {"content": "public"})})
            save_memory(tmp_path / poster.persona_id, poster)
            store.publish_experience(poster.persona_id, 1, tmp_path / poster.persona_id)
            memory = store.experience(poster.persona_id)
            plan = Disclosure(shared=list(finding_map(memory)), withheld=[], tone="direct")
            body = public_projection(plan, memory)
            store.record_disclosure(poster.persona_id, 1, plan, body)
            actor.configure(poster, store, 1, body)
            create = next(tool.func for tool in actor.action_tools if tool.func.__name__ == "create_post")
            with pytest.raises(PermissionError):
                await create("PRIVATE_SENTINEL")
            await community.env.step({actor: ManualAction(ActionType.CREATE_POST, {"content": body})})
            hidden = community.agents[lurker.persona_id]
            hidden.configure(lurker, store, 1, "")
            await community.env.step({hidden: ManualAction(ActionType.REFRESH, {})})
            assert hidden.last_feed and store.expectations(lurker.persona_id)
            with pytest.raises(PermissionError):
                await hidden.perform_action_by_data("create_comment", post_id=1, content=body)
            with pytest.raises(PermissionError):
                await hidden.perform_action_by_llm()
            with sqlite3.connect(root / "oasis.db") as db:
                posts = db.execute("SELECT content FROM post").fetchall()
                assert posts == [(body,)] and "PRIVATE_SENTINEL" not in posts[0][0]
        finally:
            await community.close()
    asyncio.run(run())


def test_camel_planner_receives_public_only_context_and_correct_chat_thinking(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from discussion.community import choose_action
    from discussion.model import ProviderModel
    from openai import AsyncOpenAI
    from tests.verify_phase2 import fixture_persona
    bodies = []
    def respond(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": "custom",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": None, "tool_calls": [{"id": "a", "type": "function",
                "function": {"name": "create_post", "arguments": "{}"}}]}, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            config = {"provider": "deepseek", "model": "custom", "base_url": "https://test.invalid/v1", "api_key": "test", "thinking_type": "disabled"}
            backend = ProviderModel(config)
            backend._async_client = AsyncOpenAI(api_key="test", base_url=config["base_url"], http_client=transport)
            action, args = await choose_action(backend, fixture_persona(False), [], "PUBLIC_ONLY", {"create_post", "do_nothing"})
            assert action == "create_post" and args == {"content": "PUBLIC_ONLY"}
    asyncio.run(run())
    body = bodies[0]
    assert body["thinking"] == {"type": "disabled"} and "reasoning" not in body
    assert "PRIVATE_SENTINEL" not in json.dumps(body)
    post_tool = next(tool for tool in body["tools"] if tool["function"]["name"] == "create_post")
    assert "content" not in post_tool["function"]["parameters"]["properties"]


def test_invalid_planner_calls_never_execute_and_fall_back_to_no_action(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from discussion.community import choose_action
    from tests.verify_phase2 import fixture_persona
    calls = []
    class Backend:
        async def _arun(self, *args, **kwargs):
            calls.append(1)
            tool = SimpleNamespace(function=SimpleNamespace(name="create_post", arguments='{"content":"PRIVATE_SENTINEL"}'))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[tool]))])
    path = tmp_path / "rejections.jsonl"
    result = asyncio.run(choose_action(Backend(), fixture_persona(False), [], "PUBLIC_ONLY", {"create_post", "do_nothing"}, path))
    assert result == ("do_nothing", {}) and len(calls) == 3
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3
