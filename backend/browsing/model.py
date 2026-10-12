"""Pass the configured provider thinking parameter through Browser Use's SDK client."""

import json
from dataclasses import dataclass, field

from browser_use import ChatOpenAI
from browser_use.llm.exceptions import ModelProviderError
from browser_use.llm.messages import UserMessage
from pydantic import ValidationError

from core.limits import async_slot
from core.providers import get_adapter
from core.usage import measured_request


def browser_schema_enforced(adapter):
    """Browser Use requests carry screenshots: a schema the provider drops for image input is not enforced."""
    return adapter.supports_json_schema("chat_completions") and not adapter.images_downgrade_json_schema


def has_image(messages):
    return any(isinstance(message.get("content"), list) and any(part.get("type") == "image_url" for part in message["content"])
               for message in messages)


@dataclass
class ProviderChatOpenAI(ChatOpenAI):
    provider: str = "openai_compatible"
    thinking_type: str | None = None
    max_model_concurrency: int = 10
    max_browser_concurrency: int = 1
    # The persona's own sampling (already filtered by the capability probe); replaces Browser Use's temperature default.
    sampling: dict = field(default_factory=dict)
    # Counted at the SDK boundary: proof that screenshots actually reach the model.
    requests_sent: int = field(default=0, init=False)
    requests_with_images: int = field(default=0, init=False)

    def __post_init__(self):
        adapter = get_adapter(self.provider_config())
        # The adapter owns thinking, including the empty setting (provider default).
        self.reasoning_models = []
        if not browser_schema_enforced(adapter):
            self.dont_force_structured_output = False
            self.add_schema_to_system_prompt = True

    def provider_config(self):
        return {"provider": self.provider, "thinking_type": self.thinking_type,
                "max_model_concurrency": self.max_model_concurrency, "max_browser_concurrency": self.max_browser_concurrency}

    async def ainvoke(self, messages, output_format=None, **kwargs):
        if output_format is None or browser_schema_enforced(get_adapter(self.provider_config())):
            return await super().ainvoke(messages, output_format, **kwargs)
        # Upstream validates with Pydantic; invalid JSON Object output gets explicit repair feedback.
        messages = list(messages) + [UserMessage(content="只返回满足 schema 的完整 JSON，不要 Markdown。schema："
                                               + json.dumps(output_format.model_json_schema(), ensure_ascii=False))]
        for attempt in range(3):
            try:
                return await super().ainvoke(messages, output_format, **kwargs)
            except ModelProviderError as error:
                if not isinstance(error.__cause__, ValidationError) or attempt == 2:
                    raise
                print(f"Browser Use JSON 本地校验失败，修正重试（第 {attempt + 2} 次）", flush=True)
                messages.append(UserMessage(content="修正以下校验错误并返回完整 JSON：" + str(error.__cause__)))

    def get_client(self):
        client = super().get_client()
        config = self.provider_config()
        adapter = get_adapter(config)
        create = client.chat.completions.create

        async def counted_create(*args, **kwargs):
            kwargs.update(adapter.thinking_options("chat_completions", self.thinking_type))
            kwargs.update(self.sampling)
            schema = kwargs.get("response_format", {}).get("json_schema")
            if schema:
                downgraded = adapter.images_downgrade_json_schema
                kwargs.update(adapter.output_options("chat_completions", None if downgraded else schema, json_object=downgraded))
            async with async_slot(config):
                self.requests_sent += 1
                self.requests_with_images += has_image(kwargs.get("messages", []))
                return await measured_request(lambda: create(*args, **kwargs), "chat_completions", self.model)

        client.chat.completions.create = counted_create
        return client
