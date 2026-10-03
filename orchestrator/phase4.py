"""Browse, synchronize private memories through SQLite, then drive one OASIS step per time slice."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

from browsing.worker import configuration_hash
from core.community import Disclosure, ExitAnswer, Withheld, allowed_actions, public_projection, validate_disclosure, validate_exit
from core.limits import concurrency_limits
from core.runtime import ROOT, require, require_capabilities, settings, write_json
from core.simulation import SimulationStore
from orchestrator.phase1 import draft_hash, require_approved
from orchestrator.personas import schedule_rows
from orchestrator.phase3 import peak_concurrency, run_timeline, summarize


async def wait_ready(store, process):
    async with asyncio.timeout(90):
        while store.metadata("community_state") != "ready":
            if process.returncode is not None:
                raise RuntimeError("OASIS process exited before initialization; see community.log")
            await asyncio.sleep(0.1)


async def command(store, process, kind, tick, logical_time):
    command_id = store.enqueue(kind, tick, logical_time.isoformat())
    async with asyncio.timeout(600):
        while True:
            result = store.command_result(command_id)
            if result["state"] in {"done", "failed"}:
                if result["state"] == "failed":
                    raise RuntimeError("Community command failed; see private errors.log")
                return json.loads(result["result_json"])
            if process.returncode is not None:
                raise RuntimeError("OASIS process exited before completing its command")
            await asyncio.sleep(0.1)


def audit_social(store, draft, oasis_path):
    violations, projection_errors, survey_errors = [], [], []
    with store.connect() as db:
        actions = [dict(row) for row in db.execute("SELECT * FROM actions")]
        disclosures = [dict(row) for row in db.execute("SELECT * FROM disclosures")]
        experiences = {row["persona_id"]: row["slice_index"] for row in db.execute("SELECT persona_id,slice_index FROM experiences")}
        read_count = db.execute("SELECT COUNT(*) FROM reads").fetchone()[0]
        before_count = db.execute("SELECT COUNT(*) FROM reads WHERE before_experience=1").fetchone()[0]
        surveys = {row["persona_id"]: row["answer_json"] for row in db.execute("SELECT persona_id,answer_json FROM surveys")}
    people = {p.persona_id: p for p in draft.personas}
    if set(surveys) != set(people):
        survey_errors.append("Questionnaire persona coverage does not match approved personas")
    for pid, answer in surveys.items():
        try:
            validate_exit(ExitAnswer.model_validate_json(answer), store.experience(pid), set(store.read_posts(pid)))
        except ValueError as error:
            survey_errors.append({"persona_id": pid, "reason": str(error)})
    for row in actions:
        experienced = row["persona_id"] in experiences and experiences[row["persona_id"]] <= row["slice_index"]
        if bool(row["experienced"]) != experienced or row["action"] not in allowed_actions(people[row["persona_id"]].participation, experienced, row["public_body"]):
            violations.append({"persona_id": row["persona_id"], "action": row["action"], "slice_index": row["slice_index"]})
    for row in disclosures:
        memory = store.experience(row["persona_id"])
        plan = Disclosure(shared=json.loads(row["shared_json"]), withheld=[Withheld.model_validate(item) for item in json.loads(row["withheld_json"])], tone="direct")
        try:
            validate_disclosure(plan, memory, people[row["persona_id"]].participation)
        except ValueError as error:
            projection_errors.append({"persona_id": row["persona_id"], "slice_index": row["slice_index"], "reason": str(error)})
            continue
        # Match an allowed renderer tone; no private field can enter through a free-form model reply.
        if row["public_body"] not in {public_projection(plan.model_copy(update={"tone": tone}), memory) for tone in ("direct", "soft", "brief")}:
            projection_errors.append({"persona_id": row["persona_id"], "slice_index": row["slice_index"]})
    for row in actions:
        if row["action"] in {"create_post", "create_comment"} and not any(
            item["persona_id"] == row["persona_id"] and item["slice_index"] == row["slice_index"]
            and item["public_body"] == row["public_body"] for item in disclosures):
            projection_errors.append({"persona_id": row["persona_id"], "reason": "Publication has no matching disclosure projection"})
    with sqlite3.connect(oasis_path) as db:
        public = [("create_post", row[0], row[1], row[2]) for row in db.execute("SELECT post_id,user_id,content FROM post")]
        public += [("create_comment", row[0], row[1], row[2]) for row in db.execute("SELECT comment_id,user_id,content FROM comment")]
        traces = db.execute("SELECT user_id,action FROM trace").fetchall()
    mapped = {index: persona for index, persona in enumerate(draft.personas)}
    for kind, identifier, user_id, content in public:
        persona = mapped[user_id]
        matches = [row for row in actions if row["persona_id"] == persona.persona_id and row["action"] == kind
                   and json.loads(row["result_json"]).get("post_id" if kind == "create_post" else "comment_id") == identifier]
        if len(matches) != 1 or matches[0]["public_body"] != content or persona.participation in {"lurker", "reactor"}:
            projection_errors.append({"persona_id": persona.persona_id, "public_id": identifier, "action": kind})
    for user_id, action in traces:
        if mapped[user_id].participation == "lurker" and action not in {"sign_up", "refresh", "do_nothing"}:
            violations.append({"persona_id": mapped[user_id].persona_id, "action": action})
    withheld = sum(len(json.loads(row["withheld_json"])) for row in disclosures)
    planner_log = Path(oasis_path).parent / "planner_rejections.jsonl"
    planner = [json.loads(line) for line in planner_log.read_text(encoding="utf-8").splitlines()] if planner_log.exists() else []
    return {"passed": not violations and not projection_errors and not survey_errors and len(public) > 0 and withheld > 0,
            "violations": violations, "public_projection_errors": projection_errors, "posts_and_comments": len(public),
            "read_records": read_count, "before_experience_read_records": before_count, "withheld_records": withheld,
            "survey_count": len(surveys), "survey_errors": survey_errors,
            "planner_rejected_attempts": sum("attempt" in item for item in planner),
            "planner_fallbacks_to_do_nothing": sum("fallback" in item for item in planner)}


def finalize(draft, root, store, timeline, config, context):
    browsing = summarize(draft, root, timeline, config)
    social = audit_social(store, draft, root / "community/oasis.db")
    usage = json.loads((root / "community/model_usage.json").read_text(encoding="utf-8"))
    intervals = []
    for ledger in [root / "community/model_usage.jsonl", *(root / p.persona_id / "model_usage.jsonl" for p in draft.personas)]:
        if ledger.exists():
            intervals.extend((item["started_at"], item["finished_at"]) for item in
                             (json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()))
    peak = peak_concurrency(intervals)
    write_json(root / "social_audit.json", social)
    result = {"passed": browsing["passed"] and social["passed"]
              and peak <= config["max_model_concurrency"] and store.metadata("community_state") == "closed",
              "context": context, "browsing": browsing, "social": social, "observed_peak_all_model_calls": peak,
              "discussion_model_usage": usage}
    write_json(root / "phase4_result.json", result)
    return result


async def execute(source_run, root):
    draft, _ = require_approved(source_run)
    config = settings()
    require(config, "steel_api_key")
    require_capabilities(source_run, config)
    root = Path(root).resolve()
    if root.exists():
        raise ValueError("Use a fresh phase4 directory")
    root.mkdir(parents=True)
    rows = schedule_rows(draft)
    limit = min(concurrency_limits(config)[1], draft.run_config.max_concurrency)
    store = SimulationStore(root / "run.db")
    store.initialize(draft, rows)
    context = {"source_run": str(Path(source_run).resolve()), "approved_draft_sha256": draft_hash(source_run),
        "configuration_sha256": configuration_hash(config), "schedule": rows, "effective_agent_concurrency": limit,
        "simulation_database": str(store.path.resolve()),
        "configuration": {key: config[key] for key in ("provider", "model", "api", "thinking_type", "max_model_concurrency", "max_browser_concurrency")}}
    write_json(root / "run_context.json", context)
    python = ROOT / ".venv-oasis" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    print(f"阶段 4 产物：{root}", flush=True)
    with (root / "community.log").open("w", encoding="utf-8") as log:
        process = await asyncio.create_subprocess_exec(str(python), "-m", "discussion.service", "--context", str(root / "run_context.json"),
            cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdout=log, stderr=asyncio.subprocess.STDOUT)
        try:
            await wait_ready(store, process)

            async def after_slice(tick, logical_time, group, timeline):
                for row in group:
                    pid = row["persona_id"]
                    if timeline["jobs"][pid]["state"] == "completed":
                        store.publish_experience(pid, tick, root / pid)
                result = await command(store, process, "step", tick, logical_time)
                print(f"时间片 {tick} 讨论完成；活跃={len(result['active_personas'])}", flush=True)

            timeline = await run_timeline(draft, rows, root, limit, on_slice_end=after_slice)
            await command(store, process, "finish", len(timeline["slices"]), draft.run_config.start_time)
            await asyncio.wait_for(process.wait(), 45)
            if process.returncode != 0 or store.metadata("community_state") != "closed":
                raise RuntimeError("OASIS did not close cleanly")
        except BaseException:
            if process.returncode is None:
                store.enqueue("close", -1, draft.run_config.start_time.isoformat())
                try:
                    await asyncio.wait_for(process.wait(), 30)
                except TimeoutError:
                    process.kill()
                    await process.wait()
            write_json(root / "phase4_result.json", {"passed": False, "status": "interrupted_or_failed"})
            raise
    return finalize(draft, root, store, timeline, config, context)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_run", type=Path)
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    root = args.run_dir or ROOT / "runs" / datetime.now(timezone.utc).strftime("phase4-%Y%m%dT%H%M%S%fZ")
    result = asyncio.run(execute(args.source_run, root))
    print(f"阶段 4：{'PASS' if result['passed'] else 'FAIL'}；{Path(root).resolve() / 'phase4_result.json'}")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
