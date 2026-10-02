"""Shared configuration and run artifacts for the phase-zero probes."""

import asyncio
import json
import os
import re
import traceback
from pathlib import Path

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError

ROOT = Path(__file__).resolve().parents[1]


def settings():
    # config/.env is the single source of truth. Libraries such as browser-use call
    # load_dotenv() on import, so a stray .env could otherwise win (Windows env names
    # are case-insensitive, e.g. Steel_API_Key would shadow STEEL_API_KEY).
    load_dotenv(ROOT / "config" / ".env", override=True)
    return {
        "base_url": os.getenv("LLM_BASE_URL", ""),
        "api_key": os.getenv("LLM_API_KEY", ""),
        "model": os.getenv("LLM_MODEL", ""),
        "thinking_type": os.getenv("LLM_THINKING_TYPE", "").strip().lower() or None,
        "api": os.getenv("LLM_API", "").strip().lower() or "chat_completions",
        "steel_api_key": os.getenv("STEEL_API_KEY", ""),
        "url": os.getenv("PROBE_URL", "https://example.com"),
        "timezone": os.getenv("PROBE_TIMEZONE", "Asia/Shanghai"),
    }


def require(config, *names):
    missing = [name for name in names if not config[name]]
    if missing:
        raise ValueError("Missing configuration: " + ", ".join(missing))


def thinking_body(config):
    thinking_type = config.get("thinking_type")
    if thinking_type is None:
        return {}
    if thinking_type not in {"enabled", "disabled"}:
        raise ValueError("LLM_THINKING_TYPE must be enabled, disabled or empty")
    return {"thinking": {"type": thinking_type}}


def llm_api(config):
    api = config.get("api", "chat_completions")
    if api not in {"chat_completions", "responses"}:
        raise ValueError("LLM_API must be chat_completions or responses")
    return api


def chat_completions_fallback(config, framework):
    # Browser Use and CAMEL/OASIS only call Chat Completions; record the downgrade instead of hiding it.
    if llm_api(config) == "responses":
        print(f"{framework} 不支持 Responses API，降级为 Chat Completions", flush=True)
        return {"llm_api": "chat_completions", "fallback_from": "responses"}
    return {"llm_api": "chat_completions"}


def chat_json_schema_supported(profile):
    # Frameworks always use Chat Completions; a Responses profile measures that path separately.
    checks = profile["checks"]
    return checks.get("chat_completions_json_schema", checks["json_schema"])["supported"]


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


def error_summary(error, run_dir):
    # Provider errors can contain request URLs and credentials. Result files keep only
    # type/status; the redacted traceback goes to the private run directory for diagnosis.
    text = "".join(traceback.format_exception(error))
    config = settings()
    for secret in [config["api_key"], config["steel_api_key"]]:
        if secret:
            text = text.replace(secret, "REDACTED")
    text = re.sub(r"(apiKey=|token=|Bearer )[^&\s'\"]+", r"\1REDACTED", text)
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    with (Path(run_dir) / "errors.log").open("a", encoding="utf-8") as log:
        log.write(text + "\n")
    return {"type": type(error).__name__, "status_code": getattr(error, "status_code", None)}


def require_capabilities(run_dir, config):
    profile = json.loads((Path(run_dir) / "capability_profile.json").read_text(encoding="utf-8"))
    if not profile["ready"]:
        raise ValueError("Model must pass conversation, tool calling and vision probes first")
    if profile["model"] != config["model"] or profile["base_url"] != config["base_url"]:
        raise ValueError("Capability profile belongs to a different model endpoint")
    if profile.get("thinking_type") != config.get("thinking_type"):
        raise ValueError("Thinking mode changed; rerun the model capability probe")
    if profile.get("api", "chat_completions") != llm_api(config):
        raise ValueError("LLM_API changed; rerun the model capability probe")
    return profile
