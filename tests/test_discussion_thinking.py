import asyncio
import json

import httpx
import pytest

pytest.importorskip("camel")
from camel.models import openai_compatible_model
from openai import AsyncOpenAI

from discussion.probe import probe_discussion


@pytest.mark.parametrize("mode", ["enabled", "disabled", None])
@pytest.mark.parametrize("provider", ["deepseek", "openai_compatible"])
def test_oasis_thinking_on_wire(tmp_path, monkeypatch, mode, provider):
    captured = []

    def respond(request):
        body = json.loads(request.content)
        captured.append(body)
        after_tool = body["messages"][-1]["role"] == "tool"
        message = {"role": "assistant", "content": "Done" if after_tool else None}
        if not after_tool:
            message["tool_calls"] = [{"id": "test-call", "type": "function", "function": {
                "name": "do_nothing", "arguments": "{}",
            }}]
        return httpx.Response(200, json={
            "id": "test", "object": "chat.completion", "created": 0, "model": "custom",
            "choices": [{"index": 0, "finish_reason": "stop" if after_tool else "tool_calls", "message": message}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            monkeypatch.setattr(openai_compatible_model, "AsyncOpenAI", lambda **kwargs: AsyncOpenAI(http_client=client, **kwargs))
            return await probe_discussion({"provider": provider, "model": "custom", "base_url": "https://test.invalid/v1",
                                           "api_key": "test", "thinking_type": mode, "api": "responses",
                                           "max_model_concurrency": 2, "max_browser_concurrency": 1}, tmp_path)

    result = asyncio.run(run())
    assert result["passed"], result
    assert result["llm_api"] == "chat_completions" and result["fallback_from"] == "responses"
    assert result["provider"] == provider and result["thinking_type"] == mode
    assert result["max_model_concurrency"] == 2 and result["max_browser_concurrency"] == 1
    assert captured
    for body in captured:
        if mode and provider == "deepseek":
            assert body["thinking"] == {"type": mode}
            assert "reasoning_effort" not in body
        elif mode:
            assert body["reasoning_effort"] == ("none" if mode == "disabled" else "high")
            assert "thinking" not in body
        else:
            assert "thinking" not in body and "reasoning_effort" not in body
        assert "extra_body" not in body
