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


def test_output_cap_is_not_used_as_agent_context_window():
    # CAMEL reads max_tokens as the context limit; 512 made it slice every feed into ~30-token memory chunks.
    from discussion.model import ProviderModel
    backend = ProviderModel({"provider": "deepseek", "model": "deepseek-chat", "base_url": "https://test.invalid/v1",
                             "api_key": "test", "thinking_type": "disabled"})
    assert backend.model_config_dict["max_tokens"] == 512 and backend.token_limit > 8192


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
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [item.get("attempt") for item in entries[:3]] == [1, 2, 3] and entries[3]["fallback"] == "do_nothing"


@pytest.mark.parametrize("provider", ["deepseek", "mimo", "bailian"])
def test_forced_tool_choice_is_sent_only_to_providers_that_enforce_it(tmp_path, monkeypatch, provider):
    monkeypatch.chdir(tmp_path)
    from datetime import datetime, timezone
    from discussion.community import Community
    from core.simulation import SimulationStore
    from tests.verify_phase2 import fixture_persona
    person = fixture_persona(False)
    draft = SimpleNamespace(personas=[person], run_config=SimpleNamespace(start_time=datetime(2026, 10, 3, tzinfo=timezone.utc)))
    store = SimulationStore(tmp_path / "run.db")
    store.initialize(draft, [{"persona_id": person.persona_id, "slice_index": 1}])
    (tmp_path / "community").mkdir()
    config = {"provider": provider, "model": "custom", "base_url": "https://test.invalid/v1", "api_key": "test",
              "thinking_type": "disabled", "api": "responses", "max_model_concurrency": 2, "max_browser_concurrency": 1}

    async def run():
        community = Community(draft, store, tmp_path / "community", config, {}, "seed")
        try:
            return dict(community.backends[person.persona_id].model_config_dict)
        finally:
            await community.client.close()
    options = asyncio.run(run())
    assert options.get("tool_choice") == ("required" if provider == "deepseek" else None)
    assert options["parallel_tool_calls"] is False
    if provider == "bailian":  # thinking reaches CAMEL's requests as the vendor's own switch
        assert options["extra_body"] == {"enable_thinking": False}


def test_one_failed_questionnaire_does_not_cancel_the_others(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from discussion import community as module
    people = [SimpleNamespace(persona_id=f"p{i:02d}") for i in range(1, 4)]
    answered = []

    async def answer(client, config, capability, persona, store):
        if persona.persona_id == "p02":
            raise ValueError("invalid questionnaire")
        await asyncio.sleep(0.01)
        answered.append(persona.persona_id)
    monkeypatch.setattr(module, "answer_exit", answer)
    fake = SimpleNamespace(draft=SimpleNamespace(personas=people), client=None, config={}, capability={}, store=None, root=tmp_path)
    result = asyncio.run(module.Community.finish(fake))
    assert answered == ["p01", "p03"] and result["survey_count"] == 2
    assert result["survey_failures"][0]["persona_id"] == "p02"
    assert json.loads((tmp_path / "survey_failures.json").read_text(encoding="utf-8"))[0]["error_type"] == "ValueError"


def test_each_persona_speaks_with_its_own_sampling(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from datetime import datetime, timezone
    from core.persona import Sampling
    from discussion.community import Community
    from core.simulation import SimulationStore
    from tests.verify_phase2 import fixture_persona
    people = [fixture_persona(False), fixture_persona(True)]
    people[0].sampling = Sampling(temperature=0.95, top_p=0.9, presence_penalty=0.3)
    draft = SimpleNamespace(personas=people, run_config=SimpleNamespace(start_time=datetime(2026, 10, 3, tzinfo=timezone.utc)))
    store = SimulationStore(tmp_path / "run.db")
    store.initialize(draft, [{"persona_id": p.persona_id, "slice_index": 1} for p in people])
    (tmp_path / "community").mkdir()
    config = {"provider": "deepseek", "model": "custom", "base_url": "https://test.invalid/v1", "api_key": "test",
              "thinking_type": "disabled", "api": "responses", "max_model_concurrency": 2, "max_browser_concurrency": 1}
    capability = {"api": "responses", "checks": {"chat_completions_sampling": {"supported": True}}}

    async def run():
        community = Community(draft, store, tmp_path / "community", config, capability, "seed")
        try:
            return {pid: dict(backend.model_config_dict) for pid, backend in community.backends.items()}
        finally:
            await community.client.close()
    options = asyncio.run(run())
    assert (options["p01"]["temperature"], options["p01"]["top_p"], options["p01"]["presence_penalty"]) == (0.95, 0.9, 0.3)
    assert options["p02"]["temperature"] == 0 and "top_p" not in options["p02"]  # no sampling: the old deterministic planner
