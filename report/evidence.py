"""Index verified local artifacts; SQLite inputs are always opened read-only."""

import json
from pathlib import Path
import sqlite3
from contextlib import closing

from core.community import Disclosure, ExitAnswer, public_projection, validate_disclosure, validate_exit
from core.experience import ExperienceMemory, load_experience


CATEGORIES = ("experience", "withheld", "discussion", "reads", "surveys", "media", "coverage")


def read_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []


def rows(path, table, optional=False):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        if optional and not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            return None
        return [dict(row) for row in db.execute(f"SELECT * FROM {table}")]


class EvidenceStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.records, self.memories, self.survey_flags = {}, {}, {}
        self.people = {row["persona_id"]: row for row in rows(self.root / "run.db", "personas")}
        self.experiences = {row["persona_id"]: row for row in rows(self.root / "run.db", "experiences")}
        self.surveys = {row["persona_id"]: row for row in rows(self.root / "run.db", "surveys")}
        self.reads = rows(self.root / "run.db", "reads")
        self.disclosures = rows(self.root / "run.db", "disclosures")
        self.assessment_rejections = {}
        for pid, row in self.people.items():
            row["persona"] = json.loads(row["persona_json"])
            self.add(f"{pid}:persona", "coverage", "run.db", {"persona_id": pid, **row["persona"]}, pid)
            if pid not in self.experiences:
                continue
            directory = self.root / pid
            memory = load_experience(directory)
            if memory.persona_id != pid or memory != ExperienceMemory.model_validate_json(self.experiences[pid]["memory_json"]):
                raise ValueError(f"Experience file/database mismatch: {pid}")
            self.memories[pid] = memory
            trace = read_lines(directory / "raw_trace.jsonl")
            events = {event["event_id"]: event for event in trace}
            if len(events) != len(trace):
                raise ValueError(f"Duplicate trace event_id: {pid}")
            for event in trace:
                self.add(f"{pid}:trace:{event['event_id']}", "media", f"{pid}/raw_trace.jsonl", event, pid)
            for snapshot in memory.snapshots:
                self.local_file(f"{pid}/{snapshot.screenshot}")
                self.add(f"{pid}:snapshot:{snapshot.evidence_id}", "media", f"{pid}/experience.json",
                         snapshot.model_dump(), pid, evidence_id=snapshot.evidence_id,
                         screenshot=f"{pid}/{snapshot.screenshot}", video_seconds=snapshot.video_seconds,
                         video=self.video(memory, {snapshot.evidence_id}))
            for step in memory.steps:
                self.add(f"{pid}:step:{step.step}", "experience", f"{pid}/experience.json", step.model_dump(), pid,
                         steps=[step.step], review_flags=self.degraded(memory, {step.before, step.after}))
            self.add(f"{pid}:outcome", "experience", f"{pid}/experience.json",
                     {key: getattr(memory, key) for key in ("outcome", "reason", "outcome_source", "state_at_browse", "assignment", "expectations")}, pid)
            for index, finding in enumerate(memory.assessment.findings if memory.assessment else []):
                if any(eid not in events for eid in finding.technical_event_ids):
                    raise ValueError(f"Missing trace evidence: {pid}")
                ids = set(finding.evidence_ids)
                self.add(f"{pid}:f{index + 1:03d}", "experience", f"{pid}/experience.json", finding.model_dump(), pid,
                         kind=finding.kind, evidence_ids=finding.evidence_ids, trace_event_ids=finding.technical_event_ids,
                         steps=[step.step for step in memory.steps if ids & {step.before, step.after}],
                         screenshots=[f"{pid}/{s.screenshot}" for s in memory.snapshots if s.evidence_id in ids],
                         video=self.video(memory, ids), review_flags=self.degraded(memory, ids))
            rejected = read_json(directory / "assessment_rejections.json", [])
            if rejected:
                self.assessment_rejections[pid] = rejected
                self.add(f"{pid}:assessment_rejections", "coverage", f"{pid}/assessment_rejections.json", rejected, pid)
        # A finding counts as public only when the platform accepted the matching post or comment.
        action_rows = rows(self.root / "run.db", "actions", optional=True)
        self.has_actions = action_rows is not None
        accepted = {(row["persona_id"], row["slice_index"], row["public_body"]) for row in action_rows or []
                    if row["action"] in {"create_post", "create_comment"} and json.loads(row["result_json"]).get("success")}
        self.published = set()
        for row in self.disclosures:
            data = {"slice_index": row["slice_index"], "shared": json.loads(row["shared_json"]),
                    "withheld": json.loads(row["withheld_json"]), "public_body": row["public_body"]}
            pid = row["persona_id"]
            if pid not in self.people:
                raise ValueError(f"Disclosure {row['disclosure_id']} references an unknown persona")
            memory = self.memories.get(pid)
            if memory and row["slice_index"] < self.experiences[pid]["slice_index"]:
                memory = None
            try:
                plan = Disclosure(shared=data["shared"], withheld=data["withheld"], tone="direct")
                validate_disclosure(plan, memory, self.people[pid]["persona"]["participation"])
                if row["public_body"] not in {public_projection(plan.model_copy(update={"tone": tone}), memory)
                                             for tone in ("direct", "soft", "brief")}:
                    raise ValueError("Public text differs from the shared-only projection")
            except ValueError as error:
                raise ValueError(f"Disclosure {row['disclosure_id']} violates its persona's disclosure contract") from error
            data["shared"] = plan.shared
            data["withheld"] = [item.model_dump() for item in plan.withheld]
            if row["public_body"] and (not self.has_actions or (row["persona_id"], row["slice_index"], row["public_body"]) in accepted):
                self.published.update((row["persona_id"], key) for key in data["shared"])
            self.add(f"disclosure:{row['disclosure_id']}", "withheld", "run.db", data, row["persona_id"])
        for row in self.reads:
            self.add(f"read:{row['read_id']}", "reads", "run.db", {**row, "post": json.loads(row["post_json"])}, row["persona_id"])
        people = list(self.people)
        for table, key in [("post", "post_id"), ("comment", "comment_id")]:
            for row in rows(self.root / "community/oasis.db", table):
                user = int(row["user_id"])
                if not 0 <= user < len(people):
                    raise ValueError("Unknown OASIS user_id")
                data = {field: row[field] for field in (key, "post_id", "user_id", "content", "created_at") if field in row}
                self.add(f"{table}:{row[key]}", "discussion", "community/oasis.db", data, people[user])
        for pid, row in self.surveys.items():
            answer = ExitAnswer.model_validate_json(row["answer_json"])
            validate_exit(answer, self.memories.get(pid), {r["post_id"] for r in self.reads if r["persona_id"] == pid})
            self.survey_flags[pid] = json.loads(row["flags_json"])
            row["answer"] = answer.model_dump()
            for field, value in row["answer"].items():
                self.add(f"{pid}:survey:{field}", "surveys", "run.db", {field: value}, pid, survey_field=field)
            self.add(f"{pid}:survey:flags", "surveys", "run.db", {"flags": self.survey_flags[pid]}, pid, survey_field="flags")
        audit = read_json(self.root / "social_audit.json", {})
        self.audit = {key: audit[key] for key in ("passed", "violations", "public_projection_errors", "posts_and_comments",
            "read_records", "before_experience_read_records", "withheld_records", "survey_count", "survey_errors",
            "planner_rejected_attempts", "planner_fallbacks_to_do_nothing") if key in audit}
        self.add("social_audit", "coverage", "social_audit.json", self.audit)
        planner = read_lines(self.root / "community/planner_rejections.jsonl")
        self.planner = {"rejected_attempts": sum("attempt" in item for item in planner),
                        "fallbacks_to_do_nothing": sum("fallback" in item for item in planner),
                        "available": (self.root / "community/planner_rejections.jsonl").exists()}
        if self.planner["available"]:
            self.add("planner_rejections", "coverage", "community/planner_rejections.jsonl", self.planner)
        self.late = [pid for pid, row in self.experiences.items() if row["slice_index"] > self.people[pid]["browse_slice"]]
        self.recoveries = [path.name for path in self.root.glob("*_survey_recovery") if path.is_dir()]
        self.missing_experiences = sorted(set(self.people) - set(self.memories))
        self.missing_surveys = sorted(set(self.people) - set(self.surveys))

    def local_file(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ValueError("Evidence path missing or outside source run: " + relative)
        return path

    def add(self, ref_id, category, path, data, pid=None, **locator):
        self.local_file(path)
        self.records[ref_id] = {"ref_id": ref_id, "category": category, "path": path,
                                "persona_id": pid, "data": data, **locator}

    @staticmethod
    def video(memory, ids):
        """Steel replay link with the estimated offset of each cited snapshot."""
        url = memory.session.get("viewer_url")
        return [{"evidence_id": s.evidence_id, "seconds": s.video_seconds, "viewer_url": url,
                 "offset_basis": memory.session.get("recording_offset_basis")}
                for s in memory.snapshots if s.evidence_id in ids]

    @staticmethod
    def degraded(memory, ids):
        return [f"page_structure_degraded=true: step {step.step}，需复核"
                for step in memory.steps if step.page_structure_degraded and ids & {step.before, step.after}]

    def query(self, category, persona_id=None, offset=0, limit=30):
        if category not in CATEGORIES or offset < 0 or not 1 <= limit <= 50:
            raise ValueError("Unknown read-only tool or invalid pagination")
        return [record for record in self.records.values() if record["category"] == category
                and (persona_id is None or record["persona_id"] == persona_id)][offset:offset + limit]

    def inventory(self):
        return {"personas": list(self.people), "tools": {name: sum(r["category"] == name for r in self.records.values()) for name in CATEGORIES},
                "late_verified_experiences": self.late, "survey_recoveries": self.recoveries,
                "missing_experiences": self.missing_experiences, "missing_surveys": self.missing_surveys}
