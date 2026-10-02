"""Pass the configured provider thinking parameter through Browser Use's SDK client."""

from dataclasses import dataclass
from functools import partial

from browser_use import ChatOpenAI

from core.runtime import thinking_body


@dataclass
class ProviderChatOpenAI(ChatOpenAI):
    thinking_type: str | None = None

    def __post_init__(self):
        if thinking_body({"thinking_type": self.thinking_type}):
            # Do not infer OpenAI reasoning_effort from a custom provider's model name.
            self.reasoning_models = []

    def get_client(self):
        client = super().get_client()
        body = thinking_body({"thinking_type": self.thinking_type})
        if body:
            # Browser Use 0.13.10 omits extra_body from ainvoke. Bind it only on
            # this new client; keep upstream serialization and response validation.
            client.chat.completions.create = partial(client.chat.completions.create, extra_body=body)
        return client
