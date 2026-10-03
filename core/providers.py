"""Provider-specific wire parameters and output capabilities live here."""

from dataclasses import dataclass


JSON_OBJECT_WARNING = "DeepSeek Chat 不支持严格 JSON Schema 输出；JSON Object 仅保证 JSON 格式，需提示词约束、本地校验和修正重试"


class OpenAICompatibleAdapter:
    name = "openai_compatible"
    json_schema_limitation = None

    def supports_json_schema(self, api):
        return True

    def thinking_options(self, api, mode):
        if mode is None:
            return {}
        effort = "none" if mode == "disabled" else "high"
        return {"reasoning": {"effort": effort}} if api == "responses" else {"reasoning_effort": effort}

    def output_options(self, api, json_schema=None, json_object=False):
        if json_schema:
            return ({"text": {"format": {"type": "json_schema", **json_schema}}} if api == "responses"
                    else {"response_format": {"type": "json_schema", "json_schema": json_schema}})
        if json_object:
            return {"text": {"format": {"type": "json_object"}}} if api == "responses" else {"response_format": {"type": "json_object"}}
        return {}


class DeepSeekAdapter(OpenAICompatibleAdapter):
    name = "deepseek"
    json_schema_limitation = JSON_OBJECT_WARNING

    def supports_json_schema(self, api):
        return api == "responses"

    def thinking_options(self, api, mode):
        if api == "responses":
            return super().thinking_options(api, mode)
        return {"extra_body": {"thinking": {"type": mode}}} if mode else {}

    def output_options(self, api, json_schema=None, json_object=False):
        if api == "chat_completions" and (json_schema or json_object):
            print(JSON_OBJECT_WARNING, flush=True)
            return {"response_format": {"type": "json_object"}}
        return super().output_options(api, json_schema, json_object)


ADAPTERS = {adapter.name: adapter() for adapter in (OpenAICompatibleAdapter, DeepSeekAdapter)}


def get_adapter(config):
    provider = config.get("provider", "openai_compatible")
    if provider not in ADAPTERS:
        raise ValueError("LLM_PROVIDER must be one of: " + ", ".join(ADAPTERS))
    if config.get("thinking_type") not in {None, "enabled", "disabled"}:
        raise ValueError("LLM_THINKING_TYPE must be enabled, disabled or empty")
    return ADAPTERS[provider]


def llm_api(config):
    api = config.get("api", "chat_completions")
    if api not in {"chat_completions", "responses"}:
        raise ValueError("LLM_API must be chat_completions or responses")
    return api


@dataclass
class ModuleRoute:
    config: dict
    metadata: dict


def module_route(config, module, supports_responses=True):
    """Copy the configuration; only a module's unsupported protocol may change."""
    adapter = get_adapter(config)
    requested = llm_api(config)
    effective = requested if supports_responses else "chat_completions"
    metadata = {"provider": adapter.name, "model": config["model"], "base_url": config["base_url"],
                "thinking_type": config.get("thinking_type"), "llm_api": effective,
                "max_model_concurrency": config.get("max_model_concurrency", 10),
                "max_browser_concurrency": config.get("max_browser_concurrency", 1)}
    if requested != effective:
        reason = f"{module} 不支持 Responses API，降级为 Chat Completions"
        metadata.update(fallback_from=requested, fallback_reason=reason)
        print(f"{reason}；提供商={adapter.name}，模型={config['model']}，思考={config.get('thinking_type')}，"
              f"模型并发={metadata['max_model_concurrency']}，浏览器并发={metadata['max_browser_concurrency']}", flush=True)
    return ModuleRoute(dict(config, api=effective), metadata)
