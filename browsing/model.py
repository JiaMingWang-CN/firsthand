"""Pass the configured provider thinking parameter through Browser Use's SDK client."""

from dataclasses import dataclass, field

from browser_use import ChatOpenAI

from core.runtime import thinking_body


def has_image(messages):
    return any(isinstance(message.get("content"), list) and any(part.get("type") == "image_url" for part in message["content"])
               for message in messages)


@dataclass
class ProviderChatOpenAI(ChatOpenAI):
    thinking_type: str | None = None
    # Counted at the SDK boundary: proof that screenshots actually reach the model.
    requests_sent: int = field(default=0, init=False)
    requests_with_images: int = field(default=0, init=False)

    def __post_init__(self):
        if thinking_body({"thinking_type": self.thinking_type}):
            # Do not infer OpenAI reasoning_effort from a custom provider's model name.
            self.reasoning_models = []

    def get_client(self):
        client = super().get_client()
        body = thinking_body({"thinking_type": self.thinking_type})
        create = client.chat.completions.create

        async def counted_create(*args, **kwargs):
            self.requests_sent += 1
            self.requests_with_images += has_image(kwargs.get("messages", []))
            # Browser Use 0.13.10 omits extra_body from ainvoke. Bind it only on
            # this new client; keep upstream serialization and response validation.
            return await create(*args, **({"extra_body": body} if body else {}), **kwargs)

        client.chat.completions.create = counted_create
        return client
