"""Pipeline jobs started from the Web UI.

Each job runs the same CLI modules an operator would run (orchestrator.phase1 / phase4 / phase5) as child
processes, one step after another. The pipeline never runs inside the API process, so the CLI and the UI share
one code path, and the API restarting does not kill a simulation in progress. Job records and logs live in
runs/_jobs/, outside every run directory.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import psutil

from core.limits import try_slot
from core.runtime import ROOT, redact

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


def process_started(pid):
    """Creation time identifies a process across PID reuse; None once it has exited."""
    try:
        return psutil.Process(pid).create_time()
    except psutil.Error:
        return None


def process_running(pid, started):
    if not pid or started is None:
        return False
    try:
        process = psutil.Process(pid)
        # Separately computed creation times can differ by rounding; a reused PID starts much later.
        return abs(process.create_time() - started) < 1 and process.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def public_job(job):
    return {key: value for key, value in job.items() if not key.startswith("_")}


class Jobs:
    def __init__(self, runs_root, python=sys.executable, popen=subprocess.Popen):
        self.root = Path(runs_root).resolve()
        self.dir = self.root / "_jobs"
        self.python, self.popen = python, popen
        self._lock = threading.Lock()  # job records and the live table
        self._start_lock = threading.RLock()
        self._transaction = threading.local()
        self._lock_name = "jobs-" + hashlib.sha256(os.path.normcase(str(self.root)).encode()).hexdigest()
        self._live = {}  # injected test runners; production liveness is the persisted runner PID

    def record(self, job_id):
        with self._lock:  # runner threads rewrite records; never read one half-written
            return read_json(self.dir / f"{job_id}.json")

    @contextmanager
    def transaction(self):
        """Serialize reservations and draft edits across threads and API processes."""
        with self._start_lock:
            if getattr(self._transaction, "active", False):
                yield
                return
            handle = None
            while handle is None:
                handle = try_slot(self._lock_name, 1)
                if handle is None:
                    time.sleep(0.02)
            self._transaction.active = True
            try:
                yield
            finally:
                self._transaction.active = False
                handle.close()

    def assert_draft_idle(self, draft_id):
        if any(job.get("draft") == draft_id and job["state"] in {"running", "detached"} for job in self.all()):
            raise Busy("这份草稿正在用于生成或模拟，结束前不能修改或重新批准")

    def _save(self, job):
        # Other API/runner processes read these records too: never expose a truncated JSON file.
        with self._lock:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.dir, suffix=".tmp", delete=False) as file:
                temporary = Path(file.name)
                json.dump(job, file, ensure_ascii=False, indent=2)
            try:
                for attempt in range(10):
                    try:
                        temporary.replace(self.dir / f"{job['id']}.json")
                        break
                    except PermissionError:  # Windows readers can briefly deny replacement.
                        if attempt == 9:
                            raise
                        time.sleep(0.01)
            finally:
                temporary.unlink(missing_ok=True)

    def start(self, kind, steps, **links):
        """steps: [{"name", "module", "args"}]; links name the run directories the job creates or reads."""
        with self.transaction():
            if kind == "simulate" and any(job["kind"] == "simulate" and job["state"] in {"running", "detached"} for job in self.all()):
                raise Busy("已有一个模拟在运行或尚未确认结束；请等它结束，失联任务需先核实子进程状态")
            if kind == "generate":
                self.assert_draft_idle(links["draft"])
                if (self.root / links["draft"] / "draft.json").exists():
                    raise Busy("这份草稿已经生成人物，请重新加载")
            job = {"id": stamp(kind), "kind": kind, "state": "running", "step": 0, "created_at": now().isoformat(),
                   "finished_at": None, "returncode": None, "steps": [{"name": step["name"], "state": "pending"} for step in steps],
                   **links}
            self.dir.mkdir(parents=True, exist_ok=True)
            if self.popen is subprocess.Popen:
                job["_commands"] = [{**step, "args": list(map(str, step["args"]))} for step in steps]
                job["_python"] = str(self.python)
                self._save(job)
                try:
                    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS} if os.name == "nt" else {"start_new_session": True}
                    with (self.dir / f"{job['id']}.log").open("a", encoding="utf-8") as log:
                        process = self.popen([self.python, "-m", "api.job_runner", str(self.root), job["id"]], cwd=ROOT,
                            env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT, **options)
                    job["runner_pid"], job["runner_started"] = process.pid, process_started(process.pid)
                    self._save(job)
                    # Reap on POSIX without making pipeline execution depend on this API thread.
                    threading.Thread(target=process.wait, daemon=True).start()
                except Exception:
                    job.update(state="failed", finished_at=now().isoformat())
                    self._save(job)
                    raise
            else:
                thread = threading.Thread(target=self._run, args=(job, steps), daemon=True, name=job["id"])
                with self._lock:
                    self._live[job["id"]] = thread
                self._save(job)
                thread.start()
        return public_job(job)

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
                    # Paid work runs in this child: an operator releasing a detached job must know it has ended.
                    job["child_pid"], job["child_started"] = process.pid, process_started(process.pid)
                    self._save(job)
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
        if job["state"] == "running" and not live and not process_running(job.get("runner_pid"), job.get("runner_started")):
            # A coordinator may save its final record and exit between the record read and PID check.
            job = self.record(job_id)
            if job["state"] == "running":
                # Legacy/failed coordinators may have paid children alive. Keep their reservations until verified.
                job = {**job, "state": "detached"}
        return {**public_job(job), "progress": self.progress(job)}

    def abandon(self, job_id, force=False):
        """Release a detached job's reservation once nothing it started can still be doing paid work."""
        with self.transaction():
            job = self.view(job_id)
            if job is None:
                raise KeyError(job_id)
            if job["state"] != "detached":
                raise Busy(f"任务状态为 {job['state']}，只有失联任务可以释放")
            record = self.record(job_id)
            if process_running(record.get("child_pid"), record.get("child_started")):
                raise Busy(f"任务的子进程 {record['child_pid']} 仍在运行；请等它结束或先手动终止")
            if "runner_pid" not in record and not force:
                raise Busy("旧版本任务没有记录子进程；请手动确认它的阶段进程都已结束，再加 --force 释放")
            for step in record["steps"]:
                if step["state"] == "running":
                    step["state"] = "failed"
            record.update(state="failed", finished_at=now().isoformat(), abandoned_at=now().isoformat())
            self._save(record)
            with (self.dir / f"{job_id}.log").open("a", encoding="utf-8") as log:
                log.write("任务失联，操作者确认后已释放占用；运行目录保持原样\n")
            return public_job(record)

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
                    "scout": (read_json(run / "scout.json") or {}).get("status", "pending") != "pending",
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
