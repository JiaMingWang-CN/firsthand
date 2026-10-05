"""Manual check, persona drafts and their human review, and starting a simulation, for the Web UI.

The review rules are the CLI's (orchestrator.phase1.approve / reject / require_approved): the UI approves exactly
the draft version it displayed, and a changed cohort distribution needs an explicit override.
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from api.jobs import read_json, stamp
from api.runs import NotFound, RUN_ID, matching_capabilities, sibling
from core.persona import Draft
from core.runtime import require, require_capabilities, settings
from orchestrator.manual import read_manual
from orchestrator.personas import distribution_issues, schedule_rows, validation_message
from orchestrator.phase1 import OverrideRequired, approve, distribution_summary, draft_hash, load_draft, reject, require_approved

# Same bound as the interview question: a manual is a page or two of Markdown.
MAX_MANUAL = 200_000


class Invalid(ValueError):
    """The request cannot be carried out as given (422)."""


class Unconfigured(RuntimeError):
    """The server lacks configuration the step needs (503)."""


def check_manual(text):
    """Parse a manual exactly as phase 1 will; nothing is written and no model is called."""
    if not text or len(text) > MAX_MANUAL:
        raise Invalid(f"说明书为空或超过 {MAX_MANUAL} 字")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "manual.md"
        path.write_text(text, encoding="utf-8")
        try:
            manual = read_manual(path)
        except ValueError as error:
            raise Invalid(validation_message(error)) from error
    metadata = manual["metadata"]
    return {"name": metadata.name, "url": metadata.url, "allowed_domains": metadata.allowed_domains,
            "test_accounts": [account.role for account in metadata.test_accounts], "forbidden_actions": len(metadata.forbidden_actions),
            "flows": [{"name": flow.name, "account_role": flow.account_role} for flow in manual["flows"]],
            "sections": list(manual["sections"]), "known_issues": "已知问题" in manual["sections"]}


def capabilities(root):
    """Directories whose capability profile matches the current model configuration, newest first."""
    return matching_capabilities(root, settings())


def draft_path(root, draft_id):
    path = Path(root) / (draft_id or "")
    if not RUN_ID.fullmatch(draft_id or "") or not (path / "manual.md").is_file() or not draft_id.startswith("phase1-"):
        raise NotFound(f"Unknown draft: {draft_id}")
    return path


def approval_state(path):
    approval = read_json(path / "approval.json")
    if approval is None:
        return {"status": "pending"}
    if approval.get("status") == "rejected":
        return {"status": "rejected"}
    try:
        require_approved(path)
    except (ValueError, OSError, KeyError) as error:
        return {"status": "stale", "reason": validation_message(error)}
    return {"status": "approved", "approved_at": approval.get("approved_at"), "overrides": approval.get("distribution_overrides", [])}


def simulations_of(root, draft_id):
    """Phase-4 runs made from this draft (their run_context names it, by directory name)."""
    runs = []
    for path in Path(root).glob("phase4-*"):
        context = read_json(path / "run_context.json", {}) or {}
        if sibling(Path(root), context.get("source_run")) == Path(root) / draft_id:
            runs.append(path.name)
    return sorted(runs, reverse=True)


def summary(root, path, jobs):
    result = read_json(path / "phase1_result.json")
    generating = any(job["kind"] == "prepare" and job["draft"] == path.name and job["state"] == "running" for job in jobs)
    if generating:
        status = "generating"
    elif result is None or not result.get("passed"):
        status = "failed" if result else "incomplete"
    else:
        status = approval_state(path)["status"]
    manual = read_json(path / "product_model.json", {}) or {}
    return {"id": path.name, "status": status, "product": (manual.get("metadata") or {}).get("name"),
            "created_at": datetime.fromtimestamp((path / "manual.md").stat().st_mtime, timezone.utc).isoformat(),
            "error": (result or {}).get("error")}


def list_drafts(root, jobs):
    paths = [path for path in Path(root).glob("phase1-*") if RUN_ID.fullmatch(path.name) and (path / "manual.md").is_file()]
    return sorted((summary(root, path, jobs) for path in paths), key=lambda item: item["created_at"], reverse=True)


def review(root, draft_id, jobs):
    """Everything the reviewer must see before approving, plus the hash of exactly this version."""
    path = draft_path(root, draft_id)
    head = summary(root, path, jobs)
    if head["status"] in {"generating", "failed", "incomplete"}:
        return {**head, "valid": False}
    displayed = draft_hash(path)
    try:
        draft, manual = load_draft(path)
    except (ValueError, OSError) as error:
        # Edited by hand into an invalid state: show why, and offer nothing to approve.
        return {**head, "valid": False, "draft_sha256": displayed, "error": validation_message(error)}
    capability = read_json(path / "capability_profile.json", {}) or {}
    try:  # approve() checks the same thing; say so now rather than after the reviewer has read everything
        require_capabilities(path, settings())
        blocked = None
    except (ValueError, KeyError, OSError) as error:
        blocked = f"这份草稿生成时用的模型能力文件与当前模型配置不符或已过期，批准会被拒绝。请重新新建运行（重新探测模型能力）。原因：{error}"
    return {**head, "valid": True, "draft_sha256": displayed, "approval": approval_state(path), "blocked": blocked,
            "manual": {"name": manual["metadata"].name, "url": manual["metadata"].url, "flows": [flow.name for flow in manual["flows"]]},
            "product": draft.product.model_dump(mode="json"), "run_config": draft.run_config.model_dump(mode="json"),
            "cohort_rationale": draft.cohort_rationale, "personas": [persona.model_dump(mode="json") for persona in draft.personas],
            "schedule": schedule_rows(draft), "distribution": distribution_summary(draft), "issues": distribution_issues(draft, manual),
            "capability": {key: capability.get(key) for key in ("provider", "model", "api", "thinking_type", "recommended_concurrency")},
            "simulations": simulations_of(root, draft_id)}


def decide(root, draft_id, decision, draft_sha256, accept_overrides=False):
    path = draft_path(root, draft_id)
    if decision == "reject":
        reject(path)
        return approval_state(path)
    try:
        approve(path, draft_sha256, accept_overrides)
    except OverrideRequired as error:
        raise Invalid(f"{error}。确认这些变更后再批准（accept_overrides）") from error
    except (ValueError, OSError) as error:
        raise Invalid(validation_message(error)) from error
    return approval_state(path)


def start_prepare(root, jobs, text, capability_run=None):
    check_manual(text)  # invalid manuals are rejected before any configuration check or paid request
    config = settings()
    try:
        require(config, "base_url", "api_key", "model")
    except ValueError as error:
        raise Unconfigured(str(error)) from error
    args = []
    if capability_run:
        source = Path(root) / capability_run
        if not RUN_ID.fullmatch(capability_run) or not (source / "capability_profile.json").is_file():
            raise Invalid(f"没有这个能力文件目录：{capability_run}")
        try:
            require_capabilities(source, config)
        except (ValueError, KeyError) as error:
            raise Invalid(f"能力文件与当前模型配置不匹配：{validation_message(error)}") from error
        args = ["--capability-run", source]
    draft_id = stamp("phase1")
    manual = jobs.dir / f"{draft_id}.manual.md"
    manual.parent.mkdir(parents=True, exist_ok=True)
    manual.write_text(text, encoding="utf-8")
    return jobs.start("prepare", [{"name": "生成产品模型与人物草稿", "module": "orchestrator.phase1",
                                   "args": ["prepare", manual, "--run-dir", Path(root) / draft_id, *args]}], draft=draft_id)


def start_simulation(root, jobs, draft_id):
    path = draft_path(root, draft_id)
    try:
        draft, _ = require_approved(path)  # the CLI checks again; failing here spares the user a dead job
    except (ValueError, OSError) as error:
        raise Invalid(validation_message(error)) from error
    try:
        require(settings(), "steel_api_key", "base_url", "api_key", "model")
    except ValueError as error:
        raise Unconfigured(str(error)) from error
    simulation, report = stamp("phase4"), stamp("phase5")
    run_config = draft.run_config
    expected = {"slices": run_config.duration_days * 1440 // run_config.time_slice_minutes, "personas": len(draft.personas)}
    return jobs.start("simulate", [
        {"name": "体验与社区讨论（阶段 4）", "module": "orchestrator.phase4", "args": [path, "--run-dir", Path(root) / simulation]},
        {"name": "生成报告（阶段 5）", "module": "orchestrator.phase5",
         "args": [Path(root) / simulation, "--run-dir", Path(root) / report, "--capability-run", path]},
    ], draft=draft_id, simulation=simulation, report=report, expected=expected)
