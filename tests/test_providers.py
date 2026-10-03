import asyncio
import json
import subprocess
import sys

import httpx
import pytest
from openai import AsyncOpenAI

from core import limits, runtime
from core.llm import create
from core.providers import get_adapter, module_route


CONFIG = {"provider": "deepseek", "model": "custom", "base_url": "https://test.invalid/v1", "api_key": "test",
          "thinking_type": "disabled", "api": "responses", "max_model_concurrency": 2, "max_browser_concurrency": 1}
SCHEMA = {"name": "answer", "strict": True, "schema": {"type": "object", "properties": {"answer": {"type": "string"}},
          "required": ["answer"], "additionalProperties": False}}


@pytest.mark.parametrize("provider", ["deepseek", "openai_compatible", "mimo"])
@pytest.mark.parametrize("api", ["responses", "chat_completions"])
@pytest.mark.parametrize("mode", ["enabled", "disabled", None])
def test_provider_parameters_on_wire(provider, api, mode, capsys):
    captured = []

    def respond(request):
        captured.append(json.loads(request.content))
        if api == "responses":
            return httpx.Response(200, json={"id": "r", "object": "response", "created_at": 0, "model": "custom",
                "status": "completed", "output": [{"type": "message", "id": "m", "status": "completed", "role": "assistant",
                "content": [{"type": "output_text", "text": '{"answer":"ok"}', "annotations": []}]}]})
        return httpx.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": "custom",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": '{"answer":"ok"}'}}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            async with AsyncOpenAI(api_key="test", base_url=CONFIG["base_url"], http_client=transport) as client:
                return await create(client, dict(CONFIG, provider=provider, api=api, thinking_type=mode),
                                    [{"role": "user", "content": "Return JSON"}], 64, 5, "answer", json_schema=SCHEMA)

    message, _ = asyncio.run(run())
    assert json.loads(message.content) == {"answer": "ok"}
    body = captured[0]
    assert body["model"] == CONFIG["model"]
    effort = "none" if mode == "disabled" else "high"
    if mode is None:
        assert not {"thinking", "reasoning", "reasoning_effort"} & body.keys()
    elif api == "responses":
        assert body["reasoning"] == {"effort": effort} and "thinking" not in body
    elif provider in {"deepseek", "mimo"}:
        assert body["thinking"] == {"type": mode} and "reasoning_effort" not in body
    else:
        assert body["reasoning_effort"] == effort and "thinking" not in body
    if provider == "mimo":
        output = body["text"]["format"] if api == "responses" else body["response_format"]
        assert output == {"type": "json_object"}
        assert "schema" in body["input" if api == "responses" else "messages"][0]["content"]
        assert "MiMo" in capsys.readouterr().out
    elif api == "responses":
        assert body["text"]["format"]["type"] == "json_schema"
    elif provider == "deepseek":
        assert body["response_format"] == {"type": "json_object"}
        assert "schema" in body["messages"][0]["content"]
        assert "不支持严格 JSON Schema" in capsys.readouterr().out
    else:
        assert body["response_format"]["type"] == "json_schema"


@pytest.mark.parametrize("provider", ["deepseek", "mimo"])
def test_module_downgrade_keeps_identity_and_limits(tmp_path, provider):
    config = dict(CONFIG, provider=provider)
    preferred = module_route(config, "Persona")
    downgraded = module_route(config, "Browser Use", supports_responses=False)
    assert preferred.config == config
    assert downgraded.config == dict(config, api="chat_completions")
    assert config["api"] == "responses"
    assert "fallback_reason" not in preferred.metadata
    assert downgraded.metadata["fallback_reason"]
    runtime.write_json(tmp_path / "capability_profile.json", dict(config, ready=True))
    with pytest.raises(ValueError, match="LLM_PROVIDER changed"):
        runtime.require_capabilities(tmp_path, dict(config, provider="openai_compatible"))


@pytest.mark.parametrize("provider", ["deepseek", "mimo"])
@pytest.mark.parametrize("repairable", [True, False])
def test_browser_json_object_is_locally_validated_and_repaired(provider, repairable):
    from browser_use.llm.exceptions import ModelProviderError
    from browser_use.llm.messages import UserMessage
    from browsing.model import ProviderChatOpenAI
    from pydantic import BaseModel

    class Answer(BaseModel):
        answer: str

    bodies = []
    def respond(request):
        body = json.loads(request.content)
        bodies.append(body)
        content = '{"answer":"ok"}' if repairable and len(bodies) == 2 else '{"wrong":true}'
        return httpx.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": "custom",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            browser = ProviderChatOpenAI(model="custom", api_key="test", base_url=CONFIG["base_url"],
                                        provider=provider, http_client=transport)
            return await browser.ainvoke([UserMessage(content="Answer")], Answer)
    if repairable:
        assert asyncio.run(run()).completion.answer == "ok"
        assert len(bodies) == 2
    else:
        with pytest.raises(ModelProviderError):
            asyncio.run(run())
        assert len(bodies) == 3
    assert all(body["response_format"] == {"type": "json_object"} for body in bodies)
    assert "校验错误" in bodies[1]["messages"][-1]["content"]


@pytest.mark.parametrize("provider", ["DeepSeek", "MiMo"])
def test_settings_validate_all_configuration(monkeypatch, provider):
    monkeypatch.setattr(runtime, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("LLM_PROVIDER", f" {provider} ")
    monkeypatch.setenv("LLM_MAX_CONCURRENCY", "3")
    monkeypatch.setenv("BROWSER_MAX_CONCURRENCY", "8")
    config = runtime.settings()
    assert config["provider"] == provider.lower() and limits.concurrency_limits(config) == (3, 3)
    monkeypatch.setenv("LLM_MAX_CONCURRENCY", "0")
    with pytest.raises(ValueError, match="LLM_MAX_CONCURRENCY"):
        runtime.settings()
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        get_adapter({"provider": "unknown"})


def test_core_and_browser_share_model_limit_without_browser_throttling(tmp_path, monkeypatch):
    from browser_use.llm.messages import UserMessage
    from browsing.model import ProviderChatOpenAI

    monkeypatch.setattr(limits, "LOCK_DIR", tmp_path / "locks")
    active, peak = 0, 0

    async def respond(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.03)
            return httpx.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": "custom",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]})
        finally:
            active -= 1

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            async with AsyncOpenAI(api_key="test", base_url=CONFIG["base_url"], http_client=transport) as client:
                browser = ProviderChatOpenAI(model="custom", api_key="test", base_url=CONFIG["base_url"],
                                            provider="deepseek", max_model_concurrency=2, http_client=transport)
                await asyncio.gather(*(create(client, dict(CONFIG, api="chat_completions"),
                    [{"role": "user", "content": "hi"}], 16, 5, "persona") for _ in range(5)),
                    *(browser.ainvoke([UserMessage(content="hi")]) for _ in range(5)))

    asyncio.run(run())
    assert peak == 2 and active == 0


def test_browser_slots_use_minimum_and_release_on_cancellation(tmp_path, monkeypatch):
    monkeypatch.setattr(limits, "LOCK_DIR", tmp_path / "locks")
    async def run():
        async with limits.async_slot(CONFIG, "browser"):
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.05):
                    async with limits.async_slot(CONFIG, "browser"):
                        pytest.fail("Browser limit ignored")
            # Non-browser requests can use both model slots while a browser slot is held.
            async with limits.async_slot(CONFIG), limits.async_slot(CONFIG):
                pass
        async with limits.async_slot(CONFIG, "browser"):
            pass
    asyncio.run(run())


def test_model_limit_shared_across_processes_and_crash_releases_slot(tmp_path, monkeypatch):
    lock_dir = tmp_path / "locks"
    monkeypatch.setattr(limits, "LOCK_DIR", lock_dir)
    child_code = """import sys
from pathlib import Path
from core import limits
limits.LOCK_DIR = Path(sys.argv[1])
with limits.sync_slot({'max_model_concurrency': 1}):
    print('acquired', flush=True)
    sys.stdin.readline()
"""
    child = subprocess.Popen([sys.executable, "-c", child_code, str(lock_dir)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "acquired"
        async def blocked():
            async with asyncio.timeout(0.05):
                async with limits.async_slot({"max_model_concurrency": 1}):
                    pytest.fail("Process exceeded shared limit")
        with pytest.raises(TimeoutError):
            asyncio.run(blocked())
        child.kill()
        child.wait(timeout=5)
        async def available():
            async with asyncio.timeout(1):
                async with limits.async_slot({"max_model_concurrency": 1}):
                    pass
        asyncio.run(available())
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)
