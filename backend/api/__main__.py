import argparse
from pathlib import Path

import uvicorn

from api.app import create_app
from api.interview import Interviewer, llm_generate
from core.runtime import ROOT


def main():
    parser = argparse.ArgumentParser(description="Serve finished runs to the Web UI (read-only).")
    parser.add_argument("--runs", type=Path, default=ROOT / "runs")
    parser.add_argument("--capability-run", type=Path, help="Directory with capability_profile.json; required for interviews.")
    parser.add_argument("--host", default="127.0.0.1", help="Run data is private; keep this on localhost.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(args.runs, Interviewer(llm_generate(args.capability_run))), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
