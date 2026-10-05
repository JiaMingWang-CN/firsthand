"""Pipeline jobs started from the Web UI.

Each job runs the same CLI modules an operator would run (orchestrator.phase1 / phase4 / phase5) as child
processes, one step after another. The pipeline never runs inside the API process, so the CLI and the UI share
one code path, and the API restarting does not kill a simulation in progress. Job records and logs live in
runs/_jobs/, outside every run directory.
"""

import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from core.runtime import ROOT, redact, write_json

LOG_TAIL = 40


class Busy(RuntimeError):
    """Another simulation is already running."""


def now():
    return datetime.now(timezone.utc)


def stamp(prefix):
    return now().strftime(f"{prefix}-%Y%m%dT%H%M%S%fZ")


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class Jobs:
    def __init__(self, runs_root, python=sys.executable, popen=subprocess.Popen):
        self.root = Path(runs_root).resolve()
        self.dir = self.root / "_jobs"
        self.python, self.popen = python, popen
        self._lock = threading.Lock()  # job records and the live table
        self._start_lock = threading.Lock()  # the one-simulation check and the start it guards
        self._live = {}  # job id -> runner thread, for jobs started by this API process

    def record(self, job_id):
        with self._lock:  # runner threads rewrite records; never read one half-written
            return read_json(self.dir / f"{job_id}.json")

    def _save(self, job):
        with self._lock:
            write_json(self.dir / f"{job['id']}.json", job)

    def start(self, kind, steps, **links):
        """steps: [{"name", "module", "args"}]; links name the run directories the job creates or reads."""
        with self._start_lock:
            if kind == "simulate" and any(job["kind"] == "simulate" and job["state"] == "running" for job in self.all()):
                raise Busy("已有一个模拟在运行；Steel 并发与费用按单次运行估算，请等它结束")
            job = {"id": stamp(kind), "kind": kind, "state": "running", "step": 0, "created_at": now().isoformat(),
                   "finished_at": None, "returncode": None, "steps": [{"name": step["name"], "state": "pending"} for step in steps],
                   **links}
            self.dir.mkdir(parents=True, exist_ok=True)
            thread = threading.Thread(target=self._run, args=(job, steps), daemon=True, name=job["id"])
            with self._lock:  # live before its record exists, so it is never seen as detached
                self._live[job["id"]] = thread
            self._save(job)
            thread.start()
        return job

    def _run(self, job, steps):
        log_path = self.dir / f"{job['id']}.log"
        try:
            for index, step in enumerate(steps):
                job["step"] = index
                job["steps"][index]["state"] = "running"
                self._save(job)
                with log_path.open("a", encoding="utf-8") as log:
                    log.write(f"== {step['name']} ==\n")
                    log.flush()
                    process = self.popen([self.python, "-m", step["module"], *map(str, step["args"])], cwd=ROOT,
                                         env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdout=log, stderr=subprocess.STDOUT)
                    code = process.wait()
                job["steps"][index]["state"] = "succeeded" if code == 0 else "failed"
                job["returncode"] = code
                if code != 0:
                    break
            job["state"] = "succeeded" if job["returncode"] == 0 else "failed"
        except Exception as error:  # a job that cannot even start must not stay "running" forever
            job["state"] = "failed"
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"任务无法执行：{type(error).__name__}\n")
        finally:
            job["finished_at"] = now().isoformat()
            self._save(job)
            with self._lock:
                self._live.pop(job["id"], None)

    def all(self):
        jobs = [self.view(path.stem) for path in self.dir.glob("*.json")] if self.dir.is_dir() else []
        return sorted((job for job in jobs if job), key=lambda job: job["created_at"], reverse=True)

    def view(self, job_id):
        # Liveness first: a runner saves its final record before leaving _live, so a record read afterwards that still
        # says "running" really belongs to no thread here (read the other way round, a job finishing in between looks detached).
        with self._lock:
            live = job_id in self._live
        job = self.record(job_id)
        if job is None:
            return None
        if job["state"] == "running" and not live:
            # Started by an earlier API process: its children may still be running, but nothing here waits on them.
            job = {**job, "state": "detached"}
        return {**job, "progress": self.progress(job)}

    def log_tail(self, job_id, lines=LOG_TAIL):
        path = self.dir / f"{job_id}.log"
        if not path.is_file():
            return []
        return [redact(line) for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]]

    def progress(self, job):
        """What the job's run directories say so far; read-only, works for detached jobs too."""
        if job["kind"] in {"prepare", "generate"}:
            run = self.root / job["draft"]
            result = read_json(run / "phase1_result.json")
            return {"capability": (run / "capability_profile.json").is_file(), "site": (run / "site.json").is_file(),
                    "product": (run / "product.json").is_file(), "draft": (run / "draft.json").is_file(),
                    "passed": None if result is None else result.get("passed")}
        run = self.root / job["simulation"]
        timeline = read_json(run / "timeline.json", {}) or {}
        slices = timeline.get("slices", [])
        states = [item.get("state") for item in timeline.get("jobs", {}).values()]
        result = read_json(run / "phase4_result.json")
        report = read_json(self.root / job["report"] / "phase5_result.json")
        # timeline.json only grows as slices start; the totals come from the approved draft (job["expected"]).
        expected = job.get("expected", {})
        return {"slices_done": sum(item.get("state") == "completed" for item in slices), "slices": expected.get("slices", len(slices)),
                "personas": expected.get("personas", len(states)), "personas_done": states.count("completed"),
                "personas_failed": states.count("failed") + states.count("cancelled"),
                "phase4_passed": None if result is None else result.get("passed"),
                "report_passed": None if report is None else report.get("passed")}
