"""Run directories on disk: discovery and safe path resolution."""

import json
import re
from pathlib import Path, PureWindowsPath

RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# Only screenshots leave the server as files; traces, sessions and databases hold private connection data.
SERVED_FILE = re.compile(r"^p\d{2}/screenshots/[A-Za-z0-9._-]+\.png$")


class NotFound(LookupError):
    pass


class RunInvalid(ValueError):
    """The run exists but its evidence fails validation."""


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def is_simulation(path):
    return (path / "phase4_result.json").is_file() and (path / "run.db").is_file()


def run_path(root, run_id):
    if not RUN_ID.fullmatch(run_id or "") or not is_simulation(root / run_id):
        raise NotFound(f"Unknown run: {run_id}")
    return root / run_id


def sibling(root, recorded):
    """Run contexts store absolute paths from the machine that made them; resolve by directory name."""
    name = PureWindowsPath(recorded or "").name
    return root / name if name else None


def interview_dir(run):
    """Interviews of a run keep their own ledger beside, not inside, the run directory: the run stays read-only
    and its own totals stay those of the simulation."""
    return run.parent / "_interviews" / run.name


def report_index(root):
    """Phase-5 directories grouped by the simulation run they read, newest first."""
    found = {}
    for path in root.iterdir():
        result = read_json(path / "phase5_result.json") if path.is_dir() else None
        if result is None or not (path / "report.json").is_file():
            continue
        source = PureWindowsPath(result.get("source_run", "")).name
        found.setdefault(source, []).append({
            "id": path.name, "passed": result.get("passed"), "model_used": result.get("model_used"),
            "issues": result.get("issues"), "highlights": result.get("highlights"),
            "_mtime": (path / "report.json").stat().st_mtime_ns})
    return {source: [{k: v for k, v in item.items() if k != "_mtime"}
                     for item in sorted(items, key=lambda item: -item["_mtime"])] for source, items in found.items()}


def job_span(path):
    """First start and last finish of the browsing jobs recorded in timeline.json."""
    jobs = (read_json(path / "timeline.json", {}) or {}).get("jobs", {}).values()
    return (min((job["started_at"] for job in jobs if job.get("started_at")), default=None),
            max((job["finished_at"] for job in jobs if job.get("finished_at")), default=None))


def list_runs(root):
    reports = report_index(root)
    runs = []
    for path in sorted(root.iterdir(), key=lambda item: item.name, reverse=True):
        if not path.is_dir() or not is_simulation(path):
            continue
        result = read_json(path / "phase4_result.json", {})
        context = read_json(path / "run_context.json", {})
        phase1 = sibling(root, context.get("source_run"))
        product = read_json(phase1 / "product_model.json", {}) if phase1 else {}
        started, finished = job_span(path)
        configuration = context.get("configuration", {})
        runs.append({
            "id": path.name, "passed": result.get("passed"), "status": result.get("status"),
            "product": product.get("metadata", {}).get("name"),
            "provider": configuration.get("provider"), "model": configuration.get("model"),
            "personas": len(context.get("schedule", [])),
            "started_at": started, "finished_at": finished,
            "reports": reports.get(path.name, [])})
    return runs
