"""Run one approved persona; leave timeline and discussion for later phases."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import asyncio
import os
from pathlib import Path

from core.runtime import ROOT, require_capabilities, settings, write_json
from orchestrator.phase1 import draft_hash, require_approved


async def execute(source_run, persona_id, run_dir):
    draft, manual = require_approved(source_run)
    config = settings()
    capability = require_capabilities(source_run, config)
    approved_hash = draft_hash(source_run)
    persona = next((persona for persona in draft.personas if persona.persona_id == persona_id), None)
    if persona is None:
        raise ValueError("Persona id is not present in the approved draft")
    from browsing.experience import run_experience
    result = await run_experience(config, capability, manual, persona, run_dir)
    write_json(Path(run_dir) / "phase2_result.json", {"source_run": str(Path(source_run).resolve()),
               "approved_draft_sha256": approved_hash, **result})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_run", type=Path, help="阶段 1 已审批的运行目录")
    parser.add_argument("--persona", required=True, help="例如 p01")
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    run_dir = (args.run_dir or ROOT / "runs" / datetime.now(timezone.utc).strftime("phase2-%Y%m%dT%H%M%S%fZ")).resolve()
    # Validate approval before any browser connection, model request or artifact creation.
    try:
        require_approved(args.source_run)
        require_capabilities(args.source_run, settings())
        if run_dir.exists():
            raise ValueError("运行目录已存在，请使用新目录")
        os.environ.update(ANONYMIZED_TELEMETRY="false", BROWSER_USE_LOGGING_LEVEL="error")
        log_dir = run_dir.parent / (run_dir.name + "-logs")
        log_dir.mkdir(parents=True, exist_ok=False)
        with (log_dir / "browser.log").open("w", encoding="utf-8") as log, redirect_stdout(log), redirect_stderr(log):
            result = asyncio.run(execute(args.source_run, args.persona, run_dir))
        print(f"阶段 2：{'PASS' if result['passed'] else 'FAIL'}；任务结果={result['outcome']}；证据：{run_dir / 'experience.json'}")
    except (ValueError, OSError) as error:
        print("不能执行：" + str(error))
        raise SystemExit(1)
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
