import asyncio
import json

import httpx
import pytest
from openai import AsyncOpenAI

from core.persona import ProductSummary
from orchestrator.personas import request_json


CONFIG = {"provider": "deepseek", "model": "custom", "base_url": "https://test.invalid/v1", "api_key": "test",
          "api": "chat_completions", "thinking_type": "disabled", "max_model_concurrency": 2, "max_browser_concurrency": 1}
CAPABILITY = {"checks": {"json_schema": {"supported": False}, "json_object": {"supported": True}, "json_prompt": {"supported": False}}}
PRODUCT = {"positioning": "作品展示", "target_users": "招聘方", "features": ["项目列表"], "assumptions": [],
           "target_age_min": None, "target_age_max": None}


@pytest.mark.parametrize("provider", ["deepseek", "openai_compatible", "mimo"])
@pytest.mark.parametrize("valid", [True, False])
def test_json_object_generation_checks_and_repairs_without_strict_schema(provider, valid):
    bodies = []
    def respond(request):
        body = json.loads(request.content)
        bodies.append(body)
        content = json.dumps(PRODUCT, ensure_ascii=False) if valid and len(bodies) == 2 else '{}'
        return httpx.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": "custom",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            async with AsyncOpenAI(api_key="test", base_url=CONFIG["base_url"], http_client=transport) as client:
                return await request_json(client, dict(CONFIG, provider=provider), CAPABILITY, ProductSummary, "Extract product")
    if valid:
        assert asyncio.run(run()).positioning == PRODUCT["positioning"]
        assert len(bodies) == 2
    else:
        with pytest.raises(ValueError, match="3 次尝试"):
            asyncio.run(run())
        assert len(bodies) == 3
    for body in bodies:
        assert body["model"] == "custom" and body["response_format"] == {"type": "json_object"}
        assert "schema" in body["messages"][1]["content"]
        if provider in {"deepseek", "mimo"}:
            assert body["thinking"] == {"type": "disabled"}
        else:
            assert body["reasoning_effort"] == "none"
    assert bodies[1]["messages"][-2] == {"role": "assistant", "content": "{}"}
    assert "修正下列校验错误" in bodies[1]["messages"][-1]["content"]


@pytest.mark.parametrize("provider", ["deepseek", "mimo"])
def test_chat_cannot_use_stale_schema_or_unverified_json_object(provider):
    capability = {"checks": {"json_schema": {"supported": True}, "json_prompt": {"supported": True}}}
    with pytest.raises(ValueError, match="JSON Object 能力探测通过"):
        asyncio.run(request_json(None, dict(CONFIG, provider=provider), capability, ProductSummary, "Extract product"))
