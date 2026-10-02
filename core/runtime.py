"""Shared configuration and run artifacts for the phase-zero probes."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def settings():
    load_dotenv(ROOT / "config" / ".env", override=False)
    return {
        "base_url": os.getenv("LLM_BASE_URL", ""),
        "api_key": os.getenv("LLM_API_KEY", ""),
        "model": os.getenv("LLM_MODEL", ""),
        "steel_api_key": os.getenv("STEEL_API_KEY", ""),
        "url": os.getenv("PROBE_URL", "https://example.com"),
        "timezone": os.getenv("PROBE_TIMEZONE", "Asia/Shanghai"),
    }


def require(config, *names):
    missing = [name for name in names if not config[name]]
    if missing:
        raise ValueError("Missing configuration: " + ", ".join(missing))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def error_summary(error):
    # Provider errors can contain request URLs and credentials. Keep only type/status.
    return {"type": type(error).__name__, "status_code": getattr(error, "status_code", None)}


def require_capabilities(run_dir, config):
    profile = json.loads((Path(run_dir) / "capability_profile.json").read_text(encoding="utf-8"))
    if not profile["ready"]:
        raise ValueError("Model must pass conversation, tool calling and vision probes first")
    if profile["model"] != config["model"] or profile["base_url"] != config["base_url"]:
        raise ValueError("Capability profile belongs to a different model endpoint")
    return profile
