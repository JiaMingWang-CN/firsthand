import argparse
from pathlib import Path

import uvicorn

from api.app import create_app
from api.interview import Interviewer, llm_generate
from api.media import SteelRecordings
from core.runtime import ROOT, settings


def main():
    parser = argparse.ArgumentParser(description="Serve finished runs to the Web UI (read-only).")
    parser.add_argument("--runs", type=Path, default=ROOT / "runs")
    parser.add_argument("--capability-run", type=Path, help="Directory with capability_profile.json for interviews; default: the newest matching one under --runs.")
    parser.add_argument("--host", default="127.0.0.1", help="Run data is private; keep this on localhost.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    app = create_app(args.runs, Interviewer(llm_generate(args.capability_run, args.runs)), SteelRecordings(settings()["steel_api_key"]))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
