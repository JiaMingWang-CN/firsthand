"""Run the phase-zero probes in their separate Python environments."""

import argparse
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from core.runtime import ROOT, require, settings, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    config = settings()
    try:
        require(config, "base_url", "api_key", "model", "steel_api_key")
    except ValueError as error:
        print(error)
        raise SystemExit(2)
    run_dir = (args.run_dir or ROOT / "runs" / datetime.now(timezone.utc).strftime("phase0-%Y%m%dT%H%M%S%fZ")).resolve()
    if run_dir.exists():
        print("Use a fresh run directory to preserve existing artifacts.")
        raise SystemExit(2)
    run_dir.mkdir(parents=True)
    environment = dict(os.environ, ANONYMIZED_TELEMETRY="false", BROWSER_USE_LOGGING_LEVEL="error", PYTHONIOENCODING="utf-8")
    checks = {}
    for name, venv, module in [
        ("model", ".venv-browsing", "probe.model"),
        ("browser", ".venv-browsing", "browsing.probe"),
        ("oasis", ".venv-oasis", "discussion.probe"),
    ]:
        python = ROOT / venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        print(f"Running {name}; artifacts: {run_dir}", flush=True)
        # Framework logs may include signed browser URLs. Keep them in the ignored
        # private run directory instead of streaming credentials to the terminal.
        with (run_dir / f"{name}.log").open("w", encoding="utf-8") as log:
            process = subprocess.run([str(python), "-m", module, "--run-dir", str(run_dir)],
                                     cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
        print(f"{name}: {'PASS' if process.returncode == 0 else 'FAIL'}", flush=True)
        checks[name] = {"exit_code": process.returncode, "passed": process.returncode == 0}
        if name == "model" and process.returncode:
            # Neither browsing nor social simulation may run on a failed model.
            break
    passed = len(checks) == 3 and all(check["passed"] for check in checks.values())
    write_json(run_dir / "phase0_result.json", {"passed": passed, "checks": checks})
    print("Phase 0: " + ("PASS" if passed else "FAIL") + f"; results: {run_dir}")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
