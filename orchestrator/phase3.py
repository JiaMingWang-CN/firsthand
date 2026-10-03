"""Advance a logical clock; browse each approved persona once, with per-slice queues."""

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time

from browsing.worker import configuration_hash
from core.experience import load_experience
from core.limits import concurrency_limits
from core.runtime import ROOT, require, require_capabilities, settings, write_json
from orchestrator.phase1 import draft_hash, require_approved
from orchestrator.personas import schedule_rows

TECHNICAL_TOOLS = {"read_console", "list_failed_requests"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


async def run_worker(root, persona_id):
    with (root / f"{persona_id}.log").open("w", encoding="utf-8") as log:
        process = await asyncio.create_subprocess_exec(sys.executable, "-m", "browsing.worker", "--context",
            str(root / "run_context.json"), "--persona", persona_id, cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
            stdout=log, stderr=asyncio.subprocess.STDOUT)
        try:
            return await process.wait()
        except asyncio.CancelledError:
            (root / f"{persona_id}.cancel").write_text("cancel", encoding="utf-8")
            try:
                await asyncio.wait_for(process.wait(), 45)
            except TimeoutError:
                process.kill()
                await process.wait()
                # A killed worker cannot run its finally block. Release its known session explicitly.
                session_file = root / persona_id / "session.json"
                if session_file.exists():
                    from steel import AsyncSteel
                    session = json.loads(session_file.read_text(encoding="utf-8"))
                    async with AsyncSteel(steel_api_key=settings()["steel_api_key"], timeout=20, max_retries=0) as steel:
                        await steel.sessions.release(session["id"])
            raise


async def run_timeline(draft, rows, root, limit, worker=run_worker, on_slice_end=None):
    semaphore = asyncio.Semaphore(limit)
    timeline = {"slices": [], "jobs": {}, "peak_workers": 0}
    active = 0

    async def browse(row, queued_at, queued_monotonic):
        nonlocal active
        pid = row["persona_id"]
        job = {**row, "state": "queued", "queued_at": queued_at}
        timeline["jobs"][pid] = job
        write_json(root / "timeline.json", timeline)
        try:
            async with semaphore:
                active += 1
                timeline["peak_workers"] = max(timeline["peak_workers"], active)
                job.update(state="running", started_at=utc_now(), queue_seconds=time.monotonic() - queued_monotonic)
                write_json(root / "timeline.json", timeline)
                print(f"时间片 {row['slice_index']}：{pid} 开始浏览", flush=True)
                try:
                    code = await worker(root, pid)
                    job.update(state="completed" if code == 0 else "failed", exit_code=code)
                except asyncio.CancelledError:
                    job["state"] = "cancelled"
                    raise
                except Exception as error:
                    job.update(state="failed", error_type=type(error).__name__)
                finally:
                    active -= 1
                    job["finished_at"] = utc_now()
                    write_json(root / "timeline.json", timeline)
                print(f"{pid}：{job['state']}", flush=True)
        except asyncio.CancelledError:
            job["state"] = "cancelled"
            write_json(root / "timeline.json", timeline)
            raise

    count = draft.run_config.duration_days * 1440 // draft.run_config.time_slice_minutes
    try:
        for index in range(count):
            group = [row for row in rows if row["slice_index"] == index]
            logical_time = draft.run_config.start_time + timedelta(minutes=index * draft.run_config.time_slice_minutes)
            state = {"slice_index": index, "logical_time": logical_time.isoformat(), "personas": [row["persona_id"] for row in group],
                     "state": "running"}
            timeline["slices"].append(state)
            write_json(root / "timeline.json", timeline)
            # Failed personas do not cancel peers; the clock advances only when this slice drains.
            async with asyncio.TaskGroup() as tasks:
                queued_at, queued_monotonic = utc_now(), time.monotonic()
                for row in group:
                    tasks.create_task(browse(row, queued_at, queued_monotonic))
            if on_slice_end is not None:
                await on_slice_end(index, logical_time, group, timeline)
            state["state"] = "completed"
            write_json(root / "timeline.json", timeline)
    finally:
        write_json(root / "timeline.json", timeline)
    return timeline


def peak_concurrency(intervals):
    events = []
    for start, end in intervals:
        if start and end:
            events.extend([(start, 1), (end, -1)])
    active, peak = 0, 0
    for _, delta in sorted(events):
        active += delta
        peak = max(peak, active)
    return peak


async def reconcile_billing(draft, root, config):
    """Cost can be zero immediately after release while Steel's usage meter is still updating."""
    from steel import AsyncSteel
    async with AsyncSteel(steel_api_key=config["steel_api_key"], timeout=30, max_retries=0) as steel:
        for persona in draft.personas:
            result_file = root / persona.persona_id / "result.json"
            session_file = root / persona.persona_id / "session.json"
            if not result_file.exists() or not session_file.exists():
                continue
            result = json.loads(result_file.read_text(encoding="utf-8"))
            session_id = json.loads(session_file.read_text(encoding="utf-8"))["id"]
            try:
                session = await steel.sessions.retrieve(session_id)
                bill = await steel.get(f"/v1/sessions/{session_id}/cost", cast_to=dict[str, object])
                for _ in range(3):
                    if session.status != "released" or not session.duration or bill["usage"]["browser"]["value"]:
                        break
                    await asyncio.sleep(5)
                    bill = await steel.get(f"/v1/sessions/{session_id}/cost", cast_to=dict[str, object])
                available = (session.status == "released" and bill.get("currency") == "usd" and bill.get("unit") == "dollar"
                             and not (session.duration and not bill["usage"]["browser"]["value"]))
                result["browser_billing"] = {"available": bool(available), **bill, "reconciled_after_cohort": True,
                    "initial_totalCost": result.get("browser_billing", {}).get("totalCost"),
                    "reason": None if available else "Lifecycle or usage metering still pending",
                    "source": "Steel GET /v1/sessions/{id}/cost"}
            except Exception as error:
                result["browser_billing"] = {"available": False, "error_type": type(error).__name__}
            write_json(result_file, result)


def summarize(draft, root, timeline, config):
    details, violations, usages, bills, request_intervals, browser_intervals = {}, [], [], [], [], []
    audited = []
    for persona in draft.personas:
        pid = persona.persona_id
        directory = root / pid
        try:
            memory = load_experience(directory)
            result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
            usage = json.loads((directory / "model_usage.json").read_text(encoding="utf-8"))
            records = [json.loads(line) for line in (directory / "raw_trace.jsonl").read_text(encoding="utf-8").splitlines()]
            attempted = [action for step in memory.steps for action in step.actions if TECHNICAL_TOOLS & action.keys()]
            granted = [item for item in records if item["event"] == "technical_tool_access"]
            if persona.browsing_profile.tech_level != "developer" and (attempted or granted or memory.observed_technical_events):
                violations.append({"persona_id": pid, "reason": "Non-developer used or observed technical data"})
            if any(item["data"]["tool"] not in persona.browsing_profile.tools for item in granted):
                violations.append({"persona_id": pid, "reason": "Undeclared technical permission"})
            audited.append(pid)
            details[pid] = {"passed": result["passed"], "outcome": memory.outcome, "steps": len(memory.steps),
                           "technical_calls": len(granted), "evidence_file": f"{pid}/experience.json", "released": result.get("released", False)}
            rejected = directory / "assessment_rejections.json"
            details[pid]["rejected_findings"] = len(json.loads(rejected.read_text(encoding="utf-8"))) if rejected.exists() else 0
            usages.append(usage)
            bills.append(result.get("browser_billing", {"available": False}))
            browser_intervals.append((result.get("browser_slot_acquired_at"), result.get("browser_released_at")))
            ledger = directory / "model_usage.jsonl"
            if ledger.exists():
                request_intervals.extend((item["started_at"], item["finished_at"]) for item in
                                         (json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()))
        except (ValueError, OSError, KeyError) as error:
            details[pid] = {"passed": False, "error_type": type(error).__name__}
    cost = {"model_requests": sum(item["requests"] for item in usages),
            "model_tokens": {key: sum(item["tokens"][key] for item in usages) for key in
                             ("input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens")},
            "model_usd_min": sum(item["usd_min"] for item in usages), "model_usd_max": sum(item["usd_max"] for item in usages),
            "model_estimate_complete": len(usages) == len(draft.personas) and all(item["estimate_complete"] for item in usages),
            "steel_usd_billed": sum(item.get("totalCost", 0) for item in bills),
            "steel_billing_complete": len(bills) == len(draft.personas) and all(item["available"] for item in bills),
            "scope": "This run's browsing, policy checks, repair retries and memory generation; excludes earlier persona generation and plan subscriptions"}
    cost["total_usd_min"] = cost["model_usd_min"] + cost["steel_usd_billed"]
    cost["total_usd_max"] = cost["model_usd_max"] + cost["steel_usd_billed"]
    model_peak, browser_peak = peak_concurrency(request_intervals), peak_concurrency(browser_intervals)
    passed = (len(details) == 10 and all(item["passed"] for item in details.values()) and not violations
              and all(job["state"] == "completed" for job in timeline["jobs"].values())
              and model_peak <= config["max_model_concurrency"] and browser_peak <= concurrency_limits(config)[1]
              and cost["model_estimate_complete"] and cost["steel_billing_complete"])
    write_json(root / "permission_audit.json", {"passed": len(audited) == 10 and not violations,
               "audited_personas": audited, "complete": len(audited) == 10, "violations": violations})
    write_json(root / "cost.json", cost)
    return {"passed": passed, "personas": details, "outcomes": dict(Counter(item.get("outcome", "unavailable") for item in details.values())),
            "peak_workers": timeline["peak_workers"], "observed_peak_model_calls": model_peak, "observed_peak_browser_slots": browser_peak,
            "permission_violations": violations, "cost": cost}


async def execute(source_run, root):
    draft, _ = require_approved(source_run)
    config = settings()
    require(config, "steel_api_key")
    require_capabilities(source_run, config)
    rows = schedule_rows(draft)
    limit = min(concurrency_limits(config)[1], draft.run_config.max_concurrency)
    root = Path(root).resolve()
    if root.exists():
        raise ValueError("Use a fresh run directory to preserve artifacts")
    root.mkdir(parents=True)
    context = {"source_run": str(Path(source_run).resolve()), "approved_draft_sha256": draft_hash(source_run),
               "configuration_sha256": configuration_hash(config), "schedule": rows, "effective_agent_concurrency": limit,
               "configuration": {key: config[key] for key in ("provider", "model", "api", "thinking_type", "max_model_concurrency", "max_browser_concurrency")}}
    write_json(root / "run_context.json", context)
    print(f"阶段 3 产物：{root}；浏览 Agent 上限={limit}", flush=True)
    try:
        timeline = await run_timeline(draft, rows, root, limit)
        await reconcile_billing(draft, root, config)
    except asyncio.CancelledError:
        write_json(root / "phase3_result.json", {"passed": False, "status": "cancelled"})
        raise
    result = summarize(draft, root, timeline, config)
    write_json(root / "phase3_result.json", {**context, **result})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_run", type=Path)
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    root = args.run_dir or ROOT / "runs" / datetime.now(timezone.utc).strftime("phase3-%Y%m%dT%H%M%S%fZ")
    try:
        result = asyncio.run(execute(args.source_run, root))
    except (ValueError, OSError) as error:
        print("不能执行：" + str(error))
        raise SystemExit(1)
    print(f"阶段 3：{'PASS' if result['passed'] else 'FAIL'}；结果：{Path(root).resolve() / 'phase3_result.json'}")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
