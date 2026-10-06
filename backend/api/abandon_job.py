"""Release a detached job after its coordinator was lost: python -m api.abandon_job <job_id> [--force]."""

import argparse
import json
import sys
from pathlib import Path

from api.jobs import Busy, Jobs
from core.runtime import ROOT


def main():
    parser = argparse.ArgumentParser(description="Mark a detached job failed so its simulation/draft reservation is released.")
    parser.add_argument("job_id")
    parser.add_argument("--runs", type=Path, default=ROOT / "runs")
    parser.add_argument("--force", action="store_true", help="Legacy jobs only: you checked that none of its stage processes is still running.")
    args = parser.parse_args()
    try:
        job = Jobs(args.runs).abandon(args.job_id, args.force)
    except KeyError:
        sys.exit(f"找不到任务 {args.job_id}")
    except Busy as error:
        sys.exit(str(error))
    print(json.dumps({key: job[key] for key in ("id", "state", "abandoned_at")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
