"""Long-lived OASIS process; SQLite commands are the only orchestration channel."""

import argparse
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path

from core.runtime import error_summary, require_capabilities, settings
from core.simulation import SimulationStore
from core.usage import UsageRecorder
from orchestrator.phase1 import draft_hash, require_approved
from browsing.worker import configuration_hash


async def serve(context_path):
    context_path = Path(context_path).resolve()
    root = context_path.parent
    context = json.loads(context_path.read_text(encoding="utf-8"))
    config = settings()
    if configuration_hash(config) != context["configuration_sha256"]:
        raise ValueError("Configuration changed before starting discussion")
    draft, _ = require_approved(context["source_run"])
    capability = require_capabilities(context["source_run"], config)
    if draft_hash(context["source_run"]) != context["approved_draft_sha256"]:
        raise ValueError("Approved plan changed before discussion")
    store = SimulationStore(root / "run.db")
    community_root = root / "community"
    community_root.mkdir()
    # OASIS import creates ./log: isolate it, never change the browser/orchestrator process cwd.
    os.chdir(community_root)
    from discussion.community import Community
    community = Community(draft, store, community_root, config, capability, context["approved_draft_sha256"])
    with UsageRecorder(config, community_root):
        try:
            await community.start()
            store.set_metadata("community_state", "ready")
            while True:
                command = store.next_command()
                if command is None:
                    await asyncio.sleep(0.1)
                    continue
                try:
                    if command["kind"] == "step":
                        result = await community.step(command["slice_index"], datetime.fromisoformat(command["logical_time"]))
                    elif command["kind"] == "finish":
                        result = await community.finish()
                    elif command["kind"] == "close":
                        store.complete_command(command["command_id"], {"closed": True})
                        break
                    else:
                        raise ValueError("Unknown community command")
                    store.complete_command(command["command_id"], result)
                    if command["kind"] == "finish":
                        break
                except Exception as error:
                    store.complete_command(command["command_id"], error_summary(error, community_root), failed=True)
                    raise
        finally:
            await community.close()
            store.set_metadata("community_state", "closed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", type=Path, required=True)
    args = parser.parse_args()
    os.environ.update(ANONYMIZED_TELEMETRY="false", BROWSER_USE_LOGGING_LEVEL="error")
    asyncio.run(serve(args.context))


if __name__ == "__main__":
    main()
