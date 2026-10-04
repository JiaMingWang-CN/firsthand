"""Builds the JSON the UI reads from a validated EvidenceStore. Nothing here writes to a run directory."""

import json
import threading
from concurrent.futures import Future
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from api.media import RecordingUnavailable, by_step, media_position, segments, summarize
from api.runs import NotFound, RunInvalid, SERVED_FILE, job_span, read_json, report_index, run_path, sibling
from report.evidence import EvidenceStore


def file_url(run_id, relative):
    return f"/api/runs/{run_id}/files/{quote(relative, safe='/')}"


TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens")


def model_usage(run):
    """Requests and tokens per model from the run's request ledgers. Prices are deliberately not exposed."""
    models = {}
    for ledger in [run / "model_usage.jsonl", *sorted(run.glob("*/model_usage.jsonl"))]:
        if not ledger.is_file():
            continue
        for line in ledger.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            row = models.setdefault(entry["model"], {"model": entry["model"], "requests": 0, "failed_requests": 0,
                                                     **{field: 0 for field in TOKEN_FIELDS}})
            row["requests"] += 1
            row["failed_requests"] += entry["error_type"] is not None
            for field in TOKEN_FIELDS:
                row[field] += (entry["usage"] or {}).get(field, 0)
    rows = sorted(models.values(), key=lambda row: -row["requests"])
    return {"models": rows, "total": {key: sum(row[key] for row in rows) for key in ("requests", "failed_requests", *TOKEN_FIELDS)},
            "scope": "浏览、讨论与问卷阶段的模型请求；不含人设生成"}


class Reader:
    def __init__(self, root, recordings=None):
        self.root = Path(root).resolve()
        self.recordings = recordings
        self._stores = {}
        self._building = {}
        self._guard = threading.Lock()

    def store(self, run_id):
        path = run_path(self.root, run_id)
        stamp = tuple((path / name).stat().st_mtime_ns for name in ("run.db", "run_context.json") if (path / name).exists())
        # Opening a run fires a dozen requests at once and building re-hashes every screenshot, so concurrent
        # requests share one build and its outcome. A failure is shared but not cached: the next request retries.
        with self._guard:
            cached = self._stores.get(run_id)
            if cached and cached[0] == stamp:
                return cached[1]
            build = self._building.get(run_id)
            owner = build is None
            if owner:
                build = self._building[run_id] = Future()
        if owner:
            try:
                store = EvidenceStore(path)
                self._stores[run_id] = (stamp, store)
                build.set_result(store)
            except (ValueError, KeyError, OSError) as error:
                failure = RunInvalid(f"{run_id}: {error}")
                failure.__cause__ = error
                build.set_exception(failure)
            except BaseException as error:  # anything else must still release the waiters
                build.set_exception(error)
            finally:
                with self._guard:
                    del self._building[run_id]
        return build.result()

    def context(self, run_id):
        return read_json(run_path(self.root, run_id) / "run_context.json", {})

    def overview(self, run_id):
        path = run_path(self.root, run_id)
        store = self.store(run_id)
        result, context = read_json(path / "phase4_result.json", {}), self.context(run_id)
        phase1 = sibling(self.root, context.get("source_run"))
        configuration = context.get("configuration", {})
        timeline = read_json(path / "timeline.json", {}) or {}
        return {
            "id": run_id, "passed": result.get("passed"), "status": result.get("status"),
            "started_at": job_span(path)[0], "finished_at": job_span(path)[1],
            "limitations": result.get("limitations", []), "acceptance_scope": result.get("acceptance_scope"),
            "product": read_json(phase1 / "product_model.json") if phase1 else None,
            "run_config": (read_json(phase1 / "draft.json", {}) or {}).get("run_config") if phase1 else None,
            "configuration": {key: configuration.get(key) for key in (
                "provider", "model", "api", "thinking_type", "max_model_concurrency", "max_browser_concurrency")},
            "personas": len(store.people),
            "timeline": {"slices": len(timeline.get("slices", [])), "peak_workers": timeline.get("peak_workers")},
            "usage": model_usage(path), "audit": store.audit, "coverage": store.inventory(),
            "reports": report_index(self.root).get(run_id, [])}

    def personas(self, run_id):
        store, context = self.store(run_id), self.context(run_id)
        schedule = {item["persona_id"]: item for item in context.get("schedule", [])}
        jobs = (read_json(run_path(self.root, run_id) / "timeline.json", {}) or {}).get("jobs", {})
        rows = []
        for pid, row in store.people.items():
            memory, survey = store.memories.get(pid), store.surveys.get(pid)
            findings = memory.assessment.findings if memory and memory.assessment else []
            rows.append({
                "persona_id": pid, "persona": row["persona"], "browse_slice": row["browse_slice"],
                "scheduled_at": schedule.get(pid, {}).get("local_time"), "job_state": jobs.get(pid, {}).get("state"),
                "experience": None if memory is None else {
                    "outcome": memory.outcome, "outcome_source": memory.outcome_source, "reason": memory.reason,
                    "state_at_browse": memory.state_at_browse, "assignment": memory.assignment, "steps": len(memory.steps),
                    "pains": sum(item.kind == "pain" for item in findings),
                    "highlights": sum(item.kind == "highlight" for item in findings), "late_verified": pid in store.late},
                "survey": None if survey is None else {
                    **{key: survey["answer"][key] for key in ("nps", "continue_using", "would_pay")},
                    "flags": store.survey_flags[pid]}})
        return rows

    def experience(self, run_id, pid):
        store = self.store(run_id)
        memory = store.memories.get(pid)
        if memory is None:
            raise NotFound(f"{pid} has no verified experience in {run_id}")
        data = memory.model_dump(exclude={"session"})
        replay = {"viewer_url": memory.session.get("viewer_url"), "offset_basis": memory.session.get("recording_offset_basis")}
        for snapshot in data["snapshots"]:
            snapshot["ref_id"] = f"{pid}:snapshot:{snapshot['evidence_id']}"
            snapshot["screenshot_url"] = file_url(run_id, f"{pid}/{snapshot['screenshot']}")
        trace = by_step(data["steps"], {s["evidence_id"]: s for s in data["snapshots"]}, summarize(self.trace_events(store, pid)))
        for step in data["steps"]:
            step["ref_id"] = f"{pid}:step:{step['step']}"
            step["trace"] = trace[step["step"]]
        if data["assessment"]:
            for index, finding in enumerate(data["assessment"]["findings"]):
                finding["ref_id"] = f"{pid}:f{index + 1:03d}"
        return {"persona_id": pid, "persona": store.people[pid]["persona"], "replay": replay, **data}

    @staticmethod
    def trace_events(store, pid):
        return [record["data"] for ref, record in store.records.items() if ref.startswith(f"{pid}:trace:")]

    def recording(self, run_id, pid):
        """Steel playlist plus each snapshot's position in the played video, from the playlist's own clock."""
        memory = self.store(run_id).memories.get(pid)
        if memory is None or not memory.session.get("id") or not memory.session.get("created_at"):
            raise NotFound(f"{pid} has no recorded session in {run_id}")
        if self.recordings is None:
            raise RecordingUnavailable("recordings are not configured on the API server")
        playlist = self.recordings.playlist(memory.session["id"])
        parts, created = segments(playlist), datetime.fromisoformat(memory.session["created_at"])
        seek = {s.evidence_id: media_position(parts, created + timedelta(seconds=s.video_seconds)) for s in memory.snapshots}
        return playlist, {"playlist_url": f"/api/runs/{run_id}/personas/{pid}/recording.m3u8", "seek": seek,
                          "basis": "Steel 录像的 PROGRAM-DATE-TIME 对齐；截图时刻取会话创建时间加本地计时"}

    def community(self, run_id):
        store = self.store(run_id)
        comments = {}
        for ref, record in store.records.items():
            if ref.startswith("comment:"):
                comments.setdefault(record["data"]["post_id"], []).append(
                    {**record["data"], "ref_id": ref, "persona_id": record["persona_id"]})
        posts = [{**record["data"], "ref_id": ref, "persona_id": record["persona_id"],
                  "comments": comments.get(record["data"]["post_id"], [])}
                 for ref, record in store.records.items() if ref.startswith("post:")]
        reads = [{"ref_id": ref, "persona_id": record["persona_id"], "slice_index": record["data"]["slice_index"],
                  "post_id": record["data"]["post_id"], "before_experience": bool(record["data"]["before_experience"]),
                  "content": record["data"]["post"].get("content")}
                 for ref, record in store.records.items() if record["category"] == "reads"]
        withheld = [{"ref_id": ref, "persona_id": record["persona_id"], **record["data"]}
                    for ref, record in store.records.items() if record["category"] == "withheld"]
        surveys = [{"persona_id": pid, **row["answer"], "flags": store.survey_flags[pid]} for pid, row in store.surveys.items()]
        return {"posts": posts, "reads": reads, "withheld": withheld, "surveys": surveys}

    def report(self, run_id, report_id=None):
        reports = report_index(self.root).get(run_id, [])
        if not reports:
            raise NotFound(f"{run_id} has no report")
        # Newest first, but a report the model wrote and that passed beats a newer model-less check run.
        chosen = report_id or next((item["id"] for item in reports if item["passed"] and item["model_used"]), reports[0]["id"])
        if chosen not in {item["id"] for item in reports}:
            raise NotFound(f"Unknown report: {chosen}")
        folder = self.root / chosen
        return {"id": chosen, "result": read_json(folder / "phase5_result.json"), "report": read_json(folder / "report.json")}

    def evidence(self, run_id, ref):
        record = self.store(run_id).records.get(ref)
        if record is None:
            raise NotFound(f"Unknown evidence: {ref}")
        if ":trace:" in ref:  # raw CDP events carry headers and cookies; only the summary leaves the server
            record = {**record, "data": (summarize([record["data"]]) or [None])[0]}
        files = [record.get("screenshot"), *record.get("screenshots", [])]
        return {**record, "files": [file_url(run_id, path) for path in files if path]}

    def file(self, run_id, relative):
        base = run_path(self.root, run_id).resolve()
        target = (base / relative).resolve()
        if not SERVED_FILE.fullmatch(relative) or not target.is_relative_to(base) or not target.is_file():
            raise NotFound("No such file")
        return target
