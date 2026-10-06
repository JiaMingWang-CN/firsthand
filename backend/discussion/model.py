"""CAMEL's Chat backend with provider translation and shared request limits."""

from camel.models import OpenAICompatibleModel

from core.limits import async_slot, sync_slot
from core.providers import get_adapter
from core.usage import measured_request


class ProviderModel(OpenAICompatibleModel):
    def __init__(self, config, sampling=None):
        """sampling: the persona's wire-ready parameters (orchestrator.personas.sampling_options); none keeps temperature 0."""
        self.provider_config = config
        options = {"temperature": 0, "max_tokens": 512, **(sampling or {}),
                   **get_adapter(config).thinking_options("chat_completions", config.get("thinking_type"))}
        super().__init__(model_type=config["model"], url=config["base_url"], api_key=config["api_key"],
                         model_config_dict=options, timeout=60, max_retries=0)

    @property
    def token_limit(self):
        # CAMEL would otherwise take max_tokens (the output cap) as the agent's context window.
        return self.model_type.token_limit

    def _run(self, *args, **kwargs):
        with sync_slot(self.provider_config):
            return super()._run(*args, **kwargs)

    async def _arun(self, *args, **kwargs):
        async with async_slot(self.provider_config):
            request = super()._arun
            return await measured_request(lambda: request(*args, **kwargs), "chat_completions", self.provider_config["model"])
