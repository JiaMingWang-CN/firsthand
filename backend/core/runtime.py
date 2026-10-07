"""Shared configuration and run artifacts for the phase-zero probes."""

import asyncio
import json
import os
import re
import traceback
from pathlib import Path

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError

from core.limits import concurrency_limits
from core.providers import get_adapter, llm_api, module_route

ROOT = Path(__file__).resolve().parents[1]
CHAT_RUNTIME_CHECKS = ("chat_completions_conversation", "chat_completions_tool_call")
CHAT_VISION_CHECKS = ("chat_completions_vision_0", "chat_completions_vision_1")
TEXT_ONLY_NOTE = "模型不支持图像识别：人物只能读取页面的文字和结构，看不到布局、图片和样式，本次结果参考性有限"


def settings():
    # config/.env is the single source of truth. Libraries such as browser-use call
    # load_dotenv() on import, so a stray .env could otherwise win (Windows env names
    # are case-insensitive, e.g. Steel_API_Key would shadow STEEL_API_KEY).
    load_dotenv(ROOT / "config" / ".env", override=True)
    config = {
        "provider": os.getenv("LLM_PROVIDER", "").strip().lower() or "openai_compatible",
        "base_url": os.getenv("LLM_BASE_URL", ""),
        "api_key": os.getenv("LLM_API_KEY", ""),
        "model": os.getenv("LLM_MODEL", ""),
        "thinking_type": os.getenv("LLM_THINKING_TYPE", "").strip().lower() or None,
        "api": os.getenv("LLM_API", "").strip().lower() or "chat_completions",
        "max_model_concurrency": int(os.getenv("LLM_MAX_CONCURRENCY", "10")),
        "max_browser_concurrency": int(os.getenv("BROWSER_MAX_CONCURRENCY", "1")),
        "steel_api_key": os.getenv("STEEL_API_KEY", ""),
        "url": os.getenv("PROBE_URL", "https://example.com"),
        "timezone": os.getenv("PROBE_TIMEZONE", "Asia/Shanghai"),
    }
    get_adapter(config)
    llm_api(config)
    concurrency_limits(config)
    return config


def require(config, *names):
    missing = [name for name in names if not config[name]]
    if missing:
        raise ValueError("Missing configuration: " + ", ".join(missing))


def chat_completions_fallback(config, framework):
    return module_route(config, framework, supports_responses=False).metadata


def chat_json_schema_supported(profile):
    # Frameworks always use Chat Completions; a Responses profile measures that path separately.
    checks = profile["checks"]
    return (get_adapter(profile).supports_json_schema("chat_completions")
            and checks.get("chat_completions_json_schema", checks["json_schema"])["supported"])


async def with_deadline(request, seconds, label, attempts=2):
    # The client timeout bounds each socket read, not the whole response, so a stalled
    # provider stream can hang indefinitely. Bound the whole call and retry transport stalls.
    for attempt in range(1, attempts + 1):
        try:
            return await asyncio.wait_for(request(), seconds)
        except (TimeoutError, APITimeoutError, APIConnectionError) as error:
            reason = f"超过 {seconds}s 未完成" if isinstance(error, TimeoutError) else type(error).__name__
            if attempt == attempts:
                raise TimeoutError(f"{label} {reason}，已尝试 {attempts} 次") from error
            print(f"{label} {reason}，重试（第 {attempt + 1} 次）", flush=True)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def redact(text):
    """Remove configured credentials and token-looking values from text that may leave the process."""
    config = settings()
    for secret in [config["api_key"], config["steel_api_key"]]:
        if secret:
            text = text.replace(secret, "REDACTED")
    return re.sub(r"(apiKey=|token=|Bearer )[^&\s'\"]+", r"\1REDACTED", text)


def error_summary(error, run_dir):
    # Provider errors can contain request URLs and credentials. Result files keep only
    # type/status; the redacted traceback goes to the private run directory for diagnosis.
    text = redact("".join(traceback.format_exception(error)))
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    with (Path(run_dir) / "errors.log").open("a", encoding="utf-8") as log:
        log.write(text + "\n")
    return {"type": type(error).__name__, "status_code": getattr(error, "status_code", None)}


def sees_images(profile):
    """Whether screenshots go to the model. Profiles from before text-only models were ready only with vision."""
    return profile.get("vision", True)


def require_capabilities(run_dir, config):
    profile = json.loads((Path(run_dir) / "capability_profile.json").read_text(encoding="utf-8"))
    if not profile["ready"]:
        raise ValueError("Model must pass conversation and tool calling probes first")
    if profile.get("provider", "openai_compatible") != get_adapter(config).name:
        raise ValueError("LLM_PROVIDER changed; rerun the model capability probe")
    if profile["model"] != config["model"] or profile["base_url"] != config["base_url"]:
        raise ValueError("Capability profile belongs to a different model endpoint")
    if profile.get("thinking_type") != config.get("thinking_type"):
        raise ValueError("Thinking mode changed; rerun the model capability probe")
    if profile.get("api", "chat_completions") != llm_api(config):
        raise ValueError("LLM_API changed; rerun the model capability probe")
    if llm_api(config) == "responses" and not all(
            profile.get("checks", {}).get(name, {}).get("supported") is True for name in CHAT_RUNTIME_CHECKS):
        raise ValueError("Chat Completions runtime conversation and tool calling probes must pass; rerun the model capability probe")
    return profile
