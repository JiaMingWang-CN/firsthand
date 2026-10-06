"""Independent pipeline coordinator: API restarts do not interrupt later stages or final records."""

import argparse
import os

from api.jobs import Jobs, process_started


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("runs_root")
    parser.add_argument("job_id")
    args = parser.parse_args()
    jobs = Jobs(args.runs_root)
    # The API saves the coordinator PID while holding the same cross-process transaction.
    with jobs.transaction():
        job = jobs.record(args.job_id)
        if job is None or job["state"] != "running" or job.get("_claimed") or "_commands" not in job:
            raise SystemExit("任务已被协调进程领取或已经结束，拒绝重复执行")
        # Windows venv redirectors have a different Popen PID from the actual interpreter.
        # Claim once under the transaction and persist the actual coordinator PID.
        job["_claimed"] = True
        job["runner_pid"] = os.getpid()
        job["runner_started"] = process_started(os.getpid())
        jobs._save(job)
    jobs.python = job["_python"]
    jobs._run(job, job["_commands"])


if __name__ == "__main__":
    main()
