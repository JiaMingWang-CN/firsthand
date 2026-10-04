import asyncio
import json

import httpx
import pytest
from browser_use.llm.messages import UserMessage
from pydantic import BaseModel

from browsing.model import ProviderChatOpenAI
from core import runtime


@pytest.mark.parametrize("mode", ["enabled", "disabled", None])
@pytest.mark.parametrize("structured", [False, True])
@pytest.mark.parametrize("provider", ["deepseek", "mimo"])
def test_browser_thinking_on_wire(mode, structured, provider):
    captured = []

    class Answer(BaseModel):
        answer: str

    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "test", "object": "chat.completion", "created": 0, "model": "gpt-5",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": '{"answer":"ok"}' if structured else "ok",
            }}],
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            llm = ProviderChatOpenAI(model="gpt-5", api_key="test", base_url="https://test.invalid/v1",
                                    provider=provider, thinking_type=mode, http_client=client)
            result = await llm.ainvoke([UserMessage(content="Reply ok")], Answer if structured else None)
            assert (result.completion.answer if structured else result.completion) == "ok"

    asyncio.run(run())
    body = captured[0]
    if mode:
        assert body["thinking"] == {"type": mode}
        assert "reasoning_effort" not in body
    else:
        assert "thinking" not in body
    assert "extra_body" not in body


def test_settings_reads_thinking_switch(monkeypatch):
    monkeypatch.setattr(runtime, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("LLM_THINKING_TYPE", " ENABLED ")
    assert runtime.settings()["thinking_type"] == "enabled"
    monkeypatch.setenv("LLM_THINKING_TYPE", "")
    assert runtime.settings()["thinking_type"] is None
    with pytest.raises(ValueError, match="LLM_THINKING_TYPE"):
        runtime.get_adapter({"thinking_type": "wrong"})


def test_capability_profile_rejected_after_thinking_change(tmp_path):
    config = {"model": "custom", "base_url": "https://test.invalid/v1", "thinking_type": "enabled"}
    runtime.write_json(tmp_path / "capability_profile.json", dict(config, ready=True))
    assert runtime.require_capabilities(tmp_path, config)["ready"]
    with pytest.raises(ValueError, match="Thinking mode changed"):
        runtime.require_capabilities(tmp_path, dict(config, thinking_type="disabled"))


def test_browser_requests_record_attached_screenshots():
    from browser_use.llm.messages import ContentPartImageParam, ContentPartTextParam, ImageURL

    def respond(request):
        return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 0, "model": "custom", "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            llm = ProviderChatOpenAI(model="deepseek-flash", api_key="test", base_url="https://test.invalid/v1", http_client=client)
            await llm.ainvoke([UserMessage(content="Text only")])
            await llm.ainvoke([UserMessage(content=[ContentPartTextParam(text="Page"),
                                                    ContentPartImageParam(image_url=ImageURL(url="data:image/png;base64,AA=="))])])
            return llm

    llm = asyncio.run(run())
    assert (llm.requests_sent, llm.requests_with_images) == (2, 1)
