import asyncio
import json

import httpx
import pytest
from openai import AsyncOpenAI

from core.llm import create
from core.persona import ProductSummary
from core.runtime import chat_completions_fallback, llm_api, require_capabilities, write_json
from orchestrator.personas import request_json

CONFIG = {"model": "custom", "base_url": "https://test.invalid/v1", "api_key": "test", "thinking_type": "disabled", "api": "responses"}
CAPABILITY = {"checks": {"json_schema": {"supported": True}, "json_prompt": {"supported": True}}}


def run(respond, request):
    paths = []

    def handler(http_request):
        paths.append(http_request.url.path)
        return respond(json.loads(http_request.content))

    async def main():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
            async with AsyncOpenAI(api_key="test", base_url=CONFIG["base_url"], http_client=transport) as client:
                return await request(client)

    return asyncio.run(main()), paths


def response(*output):
    return httpx.Response(200, json={"id": "r", "object": "response", "created_at": 0, "model": "custom", "status": "completed",
                                     "output": list(output), "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5,
                                     "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}}})


def text(value):
    return {"type": "message", "id": "m", "status": "completed", "role": "assistant",
            "content": [{"type": "output_text", "text": value, "annotations": []}]}


def test_responses_request_shape_and_tool_calls():
    bodies = []
    tool = {"type": "function", "function": {"name": "echo", "description": "Echo", "parameters": {"type": "object", "properties": {}}}}
    messages = [{"role": "user", "content": [{"type": "text", "text": "Read"},
                                            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}}]}]

    def respond(body):
        bodies.append(body)
        return response({"type": "function_call", "id": "f", "call_id": "c", "name": "echo", "arguments": '{"token": "t"}',
                         "status": "completed"})

    (message, usage), paths = run(respond, lambda client: create(
        client, CONFIG, messages, 512, 5, "tool_call", tools=[tool],
        tool_choice={"type": "function", "function": {"name": "echo"}}, parallel_tool_calls=True))
    body = bodies[0]
    assert paths == ["/v1/responses"]
    assert body["input"][0]["content"] == [{"type": "input_text", "text": "Read"},
                                           {"type": "input_image", "image_url": "data:image/png;base64,AA==", "detail": "auto"}]
    assert body["tools"] == [{"type": "function", "name": "echo", "description": "Echo",
                              "parameters": {"type": "object", "properties": {}}, "strict": False}]
    assert body["tool_choice"] == {"type": "function", "name": "echo"} and body["parallel_tool_calls"] is True
    assert body["max_output_tokens"] == 512 and body["reasoning"] == {"effort": "none"} and "thinking" not in body
    assert [(call.function.name, call.function.arguments) for call in message.tool_calls] == [("echo", '{"token": "t"}')]
    assert usage["total_tokens"] == 5


def test_structured_generation_uses_responses_text_format():
    bodies = []
    summary = {"positioning": "作品展示", "target_users": "招聘方", "features": ["项目列表"], "assumptions": [],
               "target_age_min": None, "target_age_max": None}

    def respond(body):
        bodies.append(body)
        return response(text(json.dumps(summary, ensure_ascii=False)))

    result, paths = run(respond, lambda client: request_json(client, CONFIG, CAPABILITY, ProductSummary, "Extract product"))
    assert result.positioning == "作品展示" and paths == ["/v1/responses"]
    assert bodies[0]["text"]["format"]["type"] == "json_schema" and bodies[0]["text"]["format"]["name"] == "ProductSummary"
    assert [item["role"] for item in bodies[0]["input"]] == ["system", "user"]


def test_chat_completions_remains_default():
    def respond(body):
        return httpx.Response(200, json={"id": "t", "object": "chat.completion", "created": 0, "model": "custom", "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]})

    config = {key: value for key, value in CONFIG.items() if key != "api"}
    (message, _), paths = run(respond, lambda client: create(client, config, [{"role": "user", "content": "hi"}], 16, 5, "conversation"))
    assert message.content == "ok" and paths == ["/v1/chat/completions"]


def test_api_setting_is_validated_and_bound_to_capability(tmp_path, capsys):
    with pytest.raises(ValueError, match="LLM_API"):
        llm_api({"api": "completions"})
    write_json(tmp_path / "capability_profile.json", {"ready": True, "model": "custom", "base_url": CONFIG["base_url"],
                                                      "thinking_type": "disabled", "api": "chat_completions"})
    with pytest.raises(ValueError, match="LLM_API changed"):
        require_capabilities(tmp_path, CONFIG)
    fallback = chat_completions_fallback(CONFIG, "Browser Use")
    assert fallback["llm_api"] == "chat_completions" and fallback["fallback_from"] == "responses"
    assert fallback["fallback_reason"] == "Browser Use 不支持 Responses API，降级为 Chat Completions"
    assert "Browser Use 不支持 Responses API，降级为 Chat Completions" in capsys.readouterr().out


def test_responses_probe_measures_chat_fallback_schema_separately(tmp_path, monkeypatch):
    import re
    from types import SimpleNamespace
    from probe import model

    def token_of(text):
        return re.search(r"[a-f0-9]{16}", text).group()

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.chat_create))
            self.responses = SimpleNamespace(create=self.responses_create)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def chat_create(self, **kwargs):
            # DeepSeek's Chat Completions rejects json_schema; this request comes from the fallback check.
            assert "response_format" in kwargs
            raise ValueError("This response_format type is unavailable now")

        async def responses_create(self, **kwargs):
            assert kwargs["reasoning"] == {"effort": "none"}
            content = kwargs["input"][0]["content"]
            if isinstance(content, list):
                return SimpleNamespace(output_text="123 456 789", output=[], usage=None)
            token = token_of(content)
            if "tools" in kwargs:
                calls = [SimpleNamespace(type="function_call", name=tool["name"], arguments=json.dumps({"token": token}))
                         for tool in kwargs["tools"]]
                return SimpleNamespace(output_text="", output=calls, usage=None)
            text = json.dumps({"token": token}) if "JSON" in content else token
            return SimpleNamespace(output_text=text, output=[], usage=None)

    monkeypatch.setattr(model, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(model, "image_challenge", lambda: ("123 456 789", b"test-image"))
    profile = asyncio.run(model.probe_model(CONFIG, tmp_path))
    assert not profile["ready"] and profile["api"] == "responses"
    assert profile["checks"]["json_schema"]["supported"] is True
    assert profile["checks"]["chat_completions_json_schema"]["supported"] is False
    from core.runtime import chat_json_schema_supported
    assert chat_json_schema_supported(profile) is False
    assert chat_json_schema_supported({"checks": {"json_schema": {"supported": True}}}) is True


@pytest.mark.parametrize("unsupported", ["conversation", "tools", "vision", None])
def test_responses_readiness_requires_chat_runtime_capabilities(tmp_path, monkeypatch, unsupported):
    import re
    from types import SimpleNamespace
    from probe import model

    requests = []

    async def fake_create(client, config, messages, *args, **kwargs):
        content = messages[0]["content"]
        chat = config["api"] == "chat_completions"
        requests.append((chat, isinstance(content, list), bool(kwargs.get("tools"))))
        calls = None
        if isinstance(content, list):
            answer = "cannot see" if chat and unsupported == "vision" else "123 456 789"
        else:
            token = re.search(r"[a-f0-9]{16}", content).group()
            answer = token
            if kwargs.get("tools") and not (chat and unsupported == "tools"):
                calls = [SimpleNamespace(function=SimpleNamespace(name=tool["function"]["name"],
                         arguments=json.dumps({"token": token}))) for tool in kwargs["tools"]]
            if "JSON" in content:
                answer = json.dumps({"token": token})
            elif chat and unsupported == "conversation" and not kwargs.get("tools"):
                answer = "wrong token"
        return SimpleNamespace(content=answer, tool_calls=calls), None

    monkeypatch.setattr(model, "create", fake_create)
    monkeypatch.setattr(model, "image_challenge", lambda: ("123 456 789", b"fixture"))
    config = dict(CONFIG, provider="mimo")
    profile = asyncio.run(model.probe_model(config, tmp_path))
    # A model that cannot read images still runs, as text-only.
    assert profile["ready"] is (unsupported in {None, "vision"})
    assert profile["vision"] is (unsupported != "vision")
    assert any(chat and tools for chat, _, tools in requests)
    assert sum(chat and images for chat, images, _ in requests) == 2
    if unsupported != "vision" and unsupported:
        with pytest.raises(ValueError):
            require_capabilities(tmp_path, config)
    else:
        assert require_capabilities(tmp_path, config)["ready"]


@pytest.mark.parametrize("missing", ["chat_completions_conversation", "chat_completions_tool_call"])
def test_saved_responses_profile_cannot_skip_failed_or_missing_chat_probe(tmp_path, missing):
    checks = {name: {"supported": True} for name in ("chat_completions_conversation",
              "chat_completions_tool_call", "chat_completions_vision_0", "chat_completions_vision_1")}
    for value in (None, {"supported": False}):
        if value is None:
            checks.pop(missing, None)
        else:
            checks[missing] = value
        write_json(tmp_path / "capability_profile.json", {**CONFIG, "ready": True, "checks": checks})
        with pytest.raises(ValueError, match="Chat Completions"):
            require_capabilities(tmp_path, CONFIG)
