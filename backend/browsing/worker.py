"""Isolated Browser Use worker, with approval/configuration pinning and cooperative cancellation."""

import argparse
import asyncio
from contextlib import suppress
import hashlib
import json
import os
from pathlib import Path

from core.runtime import require_capabilities, settings, write_json
from orchestrator.phase1 import draft_hash, require_approved


def configuration_hash(config):
    keys = ("provider", "model", "api", "base_url", "api_key", "steel_api_key", "thinking_type",
            "max_model_concurrency", "max_browser_concurrency")
    return hashlib.sha256(json.dumps({key: config[key] for key in keys}, sort_keys=True).encode()).hexdigest()


async def watch_cancel(path):
    while not path.exists():
        await asyncio.sleep(0.1)


async def execute(context_path, persona_id):
    context = json.loads(Path(context_path).read_text(encoding="utf-8"))
    config = settings()
    if configuration_hash(config) != context["configuration_sha256"]:
        raise ValueError("Configuration changed during the run; worker will not execute")
    source = Path(context_path).parent / "approved_source" if context.get("source_snapshot") else context["source_run"]
    draft, manual = require_approved(source)
    capability = require_capabilities(source, config)
    if draft_hash(source) != context["approved_draft_sha256"]:
        raise ValueError("Approved source changed during the run")
    persona = next(persona for persona in draft.personas if persona.persona_id == persona_id)
    root = Path(context_path).parent
    from browsing.experience import run_experience
    from core.experience import load_experience
    expectations = []
    if context.get("simulation_database"):
        from core.simulation import SimulationStore
        expectations = SimulationStore(context["simulation_database"]).expectations(persona_id)
    operation = asyncio.create_task(run_experience(config, capability, manual, persona, root / persona_id, expectations))
    cancellation = asyncio.create_task(watch_cancel(root / f"{persona_id}.cancel"))
    try:
        completed, _ = await asyncio.wait({operation, cancellation}, return_when=asyncio.FIRST_COMPLETED)
        if cancellation in completed and not operation.done():
            operation.cancel()
        result = await operation
        memory = load_experience(root / persona_id)
        row = next(row for row in context["schedule"] if row["persona_id"] == persona_id)
        memory.session["simulation"] = row
        write_json(root / persona_id / "experience.json", memory.model_dump())
        return result
    finally:
        cancellation.cancel()
        with suppress(asyncio.CancelledError):
            await cancellation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--persona", required=True)
    args = parser.parse_args()
    os.environ.update(ANONYMIZED_TELEMETRY="false", BROWSER_USE_LOGGING_LEVEL="error")
    try:
        result = asyncio.run(execute(args.context, args.persona))
    except asyncio.CancelledError:
        raise SystemExit(130)
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
