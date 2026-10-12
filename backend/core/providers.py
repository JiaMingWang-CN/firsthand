"""Provider-specific wire parameters and output capabilities live here."""

from dataclasses import dataclass


JSON_OBJECT_WARNING = "DeepSeek Chat 不支持严格 JSON Schema 输出；JSON Object 仅保证 JSON 格式，需提示词约束、本地校验和修正重试"


class OpenAICompatibleAdapter:
    name = "openai_compatible"
    json_schema_limitation = None
    honors_forced_tool_choice = True
    # tool_choice="required" (OASIS planner); a provider may enforce a named function yet not "required".
    supports_required_tool_choice = True
    context_window = None
    warned = False

    def warn_json_object(self):
        # Once per process: the limitation is static, repeating it per request only buries real log lines.
        if not self.warned:
            print(self.json_schema_limitation, flush=True)
            self.warned = True

    def usage_tokens(self, usage):
        input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
        details = usage.get("input_tokens_details", usage.get("prompt_tokens_details")) or {}
        cached = details.get("cached_tokens", 0)
        return {"input_tokens": input_tokens, "cached_input_tokens": cached,
                "uncached_input_tokens": input_tokens - cached, "output_tokens": output_tokens}

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


class ThinkingTypeChatAdapter(OpenAICompatibleAdapter):
    """Chat sends the vendor's thinking.type; Responses keeps reasoning.effort."""

    def thinking_options(self, api, mode):
        if api == "responses":
            return super().thinking_options(api, mode)
        return {"extra_body": {"thinking": {"type": mode}}} if mode else {}


class DeepSeekAdapter(ThinkingTypeChatAdapter):
    name = "deepseek"
    json_schema_limitation = JSON_OBJECT_WARNING

    def usage_tokens(self, usage):
        tokens = super().usage_tokens(usage)
        cached = usage.get("prompt_cache_hit_tokens", tokens["cached_input_tokens"])
        return {**tokens, "cached_input_tokens": cached, "uncached_input_tokens": tokens["input_tokens"] - cached}

    def supports_json_schema(self, api):
        return api == "responses"

    def output_options(self, api, json_schema=None, json_object=False):
        if api == "chat_completions" and (json_schema or json_object):
            self.warn_json_object()
            return {"response_format": {"type": "json_object"}}
        return super().output_options(api, json_schema, json_object)


class MiMoAdapter(ThinkingTypeChatAdapter):
    name = "mimo"
    json_schema_limitation = "MiMo 未提供严格 JSON Schema 输出保证；使用 JSON Object，需提示词约束、本地校验和修正重试"
    # MiMo documents that non-auto tool_choice values are ignored.
    honors_forced_tool_choice = False
    supports_required_tool_choice = False
    context_window = {"minimum_tokens": 256_000, "maximum_tokens": 1_000_000, "source": "用户确认的 MiMo 模型上下文范围（2026-10-03）"}

    def supports_json_schema(self, api):
        return False

    def output_options(self, api, json_schema=None, json_object=False):
        if json_schema:
            self.warn_json_object()
        return super().output_options(api, json_object=bool(json_schema or json_object))


class BailianAdapter(OpenAICompatibleAdapter):
    """Alibaba Cloud Model Studio (百炼), OpenAI-compatible mode.

    Thinking is the vendor's enable_thinking on both APIs. Chat json_schema holds only on the models the vendor lists
    and is silently downgraded to json_object elsewhere (and with image input), so local validation still applies.
    Qwen enforces a named tool_choice but not "required".
    """
    name = "bailian"
    json_schema_limitation = "百炼 Responses 接口未写明结构化输出；使用 JSON Object 或提示词 JSON，需本地校验和修正重试"
    supports_required_tool_choice = False

    def supports_json_schema(self, api):
        return api == "chat_completions"

    def thinking_options(self, api, mode):
        return {"extra_body": {"enable_thinking": mode == "enabled"}} if mode else {}

    def output_options(self, api, json_schema=None, json_object=False):
        if api == "responses" and json_schema:
            self.warn_json_object()
            return super().output_options(api, json_object=True)
        return super().output_options(api, json_schema, json_object)


ADAPTERS = {adapter.name: adapter() for adapter in (OpenAICompatibleAdapter, DeepSeekAdapter, MiMoAdapter, BailianAdapter)}


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
