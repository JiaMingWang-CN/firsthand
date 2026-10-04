"""Builds the JSON the UI reads from a validated EvidenceStore. Nothing here writes to a run directory."""

from pathlib import Path
from urllib.parse import quote

from api.runs import NotFound, RunInvalid, SERVED_FILE, read_json, report_index, run_path, sibling
from report.evidence import EvidenceStore


def file_url(run_id, relative):
    return f"/api/runs/{run_id}/files/{quote(relative, safe='/')}"


class Reader:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self._stores = {}

    def store(self, run_id):
        path = run_path(self.root, run_id)
        stamp = tuple((path / name).stat().st_mtime_ns for name in ("run.db", "run_context.json") if (path / name).exists())
        cached = self._stores.get(run_id)
        if cached and cached[0] == stamp:
            return cached[1]
        try:
            store = EvidenceStore(path)
        except (ValueError, KeyError, OSError) as error:
            raise RunInvalid(f"{run_id}: {error}") from error
        self._stores[run_id] = (stamp, store)
        return store

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
            "limitations": result.get("limitations", []), "acceptance_scope": result.get("acceptance_scope"),
            "product": read_json(phase1 / "product_model.json") if phase1 else None,
            "run_config": (read_json(phase1 / "draft.json", {}) or {}).get("run_config") if phase1 else None,
            "configuration": {key: configuration.get(key) for key in (
                "provider", "model", "api", "thinking_type", "max_model_concurrency", "max_browser_concurrency")},
            "personas": len(store.people),
            "timeline": {"slices": len(timeline.get("slices", [])), "peak_workers": timeline.get("peak_workers")},
            "usage": read_json(path / "cost.json"), "audit": store.audit, "coverage": store.inventory(),
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
        for step in data["steps"]:
            step["ref_id"] = f"{pid}:step:{step['step']}"
        if data["assessment"]:
            for index, finding in enumerate(data["assessment"]["findings"]):
                finding["ref_id"] = f"{pid}:f{index + 1:03d}"
        return {"persona_id": pid, "persona": store.people[pid]["persona"], "replay": replay, **data}

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
        chosen = report_id or reports[0]["id"]
        if chosen not in {item["id"] for item in reports}:
            raise NotFound(f"Unknown report: {chosen}")
        folder = self.root / chosen
        return {"id": chosen, "result": read_json(folder / "phase5_result.json"), "report": read_json(folder / "report.json")}

    def evidence(self, run_id, ref):
        record = self.store(run_id).records.get(ref)
        if record is None:
            raise NotFound(f"Unknown evidence: {ref}")
        files = [record.get("screenshot"), *record.get("screenshots", [])]
        return {**record, "files": [file_url(run_id, path) for path in files if path]}

    def file(self, run_id, relative):
        base = run_path(self.root, run_id).resolve()
        target = (base / relative).resolve()
        if not SERVED_FILE.fullmatch(relative) or not target.is_relative_to(base) or not target.is_file():
            raise NotFound("No such file")
        return target
