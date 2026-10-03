"""Per-run request ledger. No prompts, responses, credentials or shared-account balance guesses."""

from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time

from core.providers import get_adapter
from core.runtime import write_json

CURRENT_USAGE = ContextVar("muchhuman_usage", default=None)


class UsageRecorder:
    def __init__(self, config, run_dir):
        self.config, self.run_dir, self.entries = config, Path(run_dir), []

    def __enter__(self):
        ledger = self.run_dir / "model_usage.jsonl"
        if ledger.exists():
            self.entries = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        self.token = CURRENT_USAGE.set(self)
        return self

    def __exit__(self, *args):
        CURRENT_USAGE.reset(self.token)
        if self.run_dir.exists():
            write_json(self.run_dir / "model_usage.json", self.summary())

    def record(self, api, model, started, response=None, error=None):
        usage = getattr(response, "usage", None)
        raw = usage.model_dump() if hasattr(usage, "model_dump") else usage
        tokens = get_adapter(self.config).usage_tokens(raw) if raw else None
        price = get_adapter(self.config).price_range(model, tokens) if tokens else None
        seconds = time.monotonic() - started
        finished = datetime.now(timezone.utc)
        entry = {"request": len(self.entries) + 1, "api": api, "model": model,
                 "started_at": (finished - timedelta(seconds=seconds)).isoformat(),
                 "finished_at": finished.isoformat(), "seconds": round(seconds, 3),
                 "error_type": type(error).__name__ if error else None, "usage": tokens, "price_range": price}
        self.entries.append(entry)
        with (self.run_dir / "model_usage.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def summary(self):
        tokens = {key: sum((item["usage"] or {}).get(key, 0) for item in self.entries)
                  for key in ("input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens")}
        prices = [item["price_range"] for item in self.entries if item["price_range"]]
        complete = all(item["usage"] and item["price_range"] for item in self.entries)
        return {"requests": len(self.entries), "failed_requests": sum(item["error_type"] is not None for item in self.entries),
                "requests_without_usage": sum(item["usage"] is None for item in self.entries), "tokens": tokens,
                "estimate_complete": complete, "usd_min": sum(item["usd_min"] for item in prices),
                "usd_max": sum(item["usd_max"] for item in prices), "billing_basis": "usage-based estimate; unreported failed attempts may still be billed"}


async def measured_request(request, api, model):
    recorder = CURRENT_USAGE.get()
    if recorder is None:
        return await request()
    started = time.monotonic()
    try:
        response = await request()
    except BaseException as error:
        recorder.record(api, model, started, error=error)
        raise
    recorder.record(api, model, started, response=response)
    return response
