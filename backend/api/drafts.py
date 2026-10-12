"""Manual check, persona drafts and their human review, and starting a simulation, for the Web UI.

The review rules are the CLI's (orchestrator.phase1.approve / reject / require_approved): the UI approves exactly
the draft version it displayed, and a changed cohort distribution needs an explicit override.
"""

import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from api.jobs import Jobs, read_json, stamp
from api.runs import NotFound, RUN_ID, matching_capabilities, sibling
from core.persona import MAX_DAYS, MAX_PERSONAS, MIN_PERSONAS, Draft
from core.runtime import require, require_capabilities, sees_images, settings, write_json
from orchestrator.manual import material, read_manual
from orchestrator.personas import distribution_issues, minimum_count, schedule_rows, validate_draft, validation_message
from orchestrator.phase1 import (OverrideRequired, approve, distribution_summary, draft_hash, load_draft, reject, require_approved,
                                 save_review)

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
            "test_accounts": [account.role for account in metadata.test_accounts], "forbidden_actions": metadata.forbidden_actions,
            "flows": [{"name": flow.name, "account_role": flow.account_role} for flow in manual["flows"]],
            "sections": list(manual["sections"]), "known_issues": "已知问题" in manual["sections"], "defaults": manual["defaults"],
            "material": material(manual), "minimum_personas": minimum_count(len(manual["flows"]))}


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
    running = [job["kind"] for job in jobs if job["kind"] in {"prepare", "generate"} and job["draft"] == path.name and job["state"] == "running"]
    if running:
        status = "analyzing" if running[0] == "prepare" else "generating"
    elif result is None or not result.get("passed"):
        status = "failed" if result else "incomplete"
    elif result.get("stage") == "text_only":
        status = "text_only"  # the user accepts the limited reference value of a model that cannot read images, or stops here
    elif result.get("stage") == "analyzed":
        status = "configuring"  # the user confirms the recommended cohort size and timeline length
    else:
        status = approval_state(path)["status"]
    name = ((read_json(path / "product_model.json", {}) or {}).get("metadata") or {}).get("name")
    if name is None:  # before personas exist (analyzing, configuring) only the manual names the product
        try:
            name = read_manual(path / "manual.md")["metadata"].name
        except (ValueError, OSError):
            name = None
    return {"id": path.name, "status": status, "product": name,
            "created_at": datetime.fromtimestamp((path / "manual.md").stat().st_mtime, timezone.utc).isoformat(),
            "error": (result or {}).get("error"), "text_only": text_only(path)}


def text_only(path):
    capability = read_json(path / "capability_profile.json")
    return capability is not None and not sees_images(capability)


def list_drafts(root, jobs):
    paths = [path for path in Path(root).glob("phase1-*") if RUN_ID.fullmatch(path.name) and (path / "manual.md").is_file()]
    # "simulated": the runs list shows approved drafts that still wait for "开始模拟" as a next step. A starting
    # simulation names its draft before phase 4 writes run_context.json; a failed one leaves the draft waiting again.
    started = {job["draft"] for job in jobs if job["kind"] == "simulate" and job["state"] != "failed"}
    return sorted(({**summary(root, path, jobs), "simulated": path.name in started or bool(simulations_of(root, path.name))} for path in paths),
                  key=lambda item: item["created_at"], reverse=True)


def review(root, draft_id, jobs):
    """Everything the reviewer must see before approving, plus the hash of exactly this version."""
    started = next((job for job in jobs if job["kind"] == "prepare" and job["draft"] == draft_id), None)
    if started and not (Path(root) / draft_id / "manual.md").is_file():
        # The UI opens this page as soon as the analysis job starts, before the job has written the run directory.
        return {"id": draft_id, "status": "analyzing" if started["state"] == "running" else "failed", "product": None,
                "created_at": started["created_at"], "error": None, "valid": False}
    path = draft_path(root, draft_id)
    head = summary(root, path, jobs)
    result = read_json(path / "phase1_result.json", {}) or {}
    site = read_json(path / "site.json")
    analysis = {"material": result.get("material"), "recommendation": result.get("recommendation"),
                "minimum_personas": result.get("minimum_personas"), "generation_error": result.get("generation_error"),
                "site": None if site is None else {key: site.get(key) for key in ("status", "url", "title", "reason", "note")},
                "limits": {"personas": [MIN_PERSONAS, MAX_PERSONAS], "days": [1, MAX_DAYS]}, "scout": scout_view(path)}
    if head["status"] in {"analyzing", "generating", "configuring"} and (path / "product.json").is_file():
        # As on a drafted review, "product" is the product model; the product's name is under "manual".
        analysis.update(product=read_json(path / "product.json"), manual={"name": head["product"]})
    if head["status"] in {"analyzing", "text_only", "generating", "configuring", "failed", "incomplete"}:
        return {**head, **analysis, "valid": False}
    displayed = draft_hash(path)
    try:
        draft, manual = load_draft(path)
    except (ValueError, OSError) as error:
        # Edited by hand into an invalid state: show why, and offer nothing to approve.
        return {**head, "valid": False, "draft_sha256": displayed, "error": validation_message(error)}
    capability = read_json(path / "capability_profile.json", {}) or {}
    checks = capability.get("checks", {})
    try:  # approve() checks the same thing; say so now rather than after the reviewer has read everything
        require_capabilities(path, settings())
        blocked = None
    except (ValueError, KeyError, OSError) as error:
        blocked = f"这份草稿生成时用的模型能力文件与当前模型配置不符或已过期，批准会被拒绝。请重新新建运行（重新探测模型能力）。原因：{error}"
    return {**head, **analysis, "valid": True, "draft_sha256": displayed, "approval": approval_state(path), "blocked": blocked,
            "manual": {"name": manual["metadata"].name, "url": manual["metadata"].url, "flows": [flow.name for flow in manual["flows"]]},
            "product": draft.product.model_dump(mode="json"), "run_config": draft.run_config.model_dump(mode="json"),
            "cohort_rationale": draft.cohort_rationale, "personas": [persona.model_dump(mode="json") for persona in draft.personas],
            "schedule": schedule_rows(draft), "distribution": distribution_summary(draft), "issues": distribution_issues(draft, manual),
            "capability": {key: capability.get(key) for key in ("provider", "model", "api", "thinking_type", "recommended_concurrency")},
            # Persona-voiced calls run on Chat (frameworks) and on the configured API (questionnaire, interview).
            "sampling": {"probed": "sampling" in checks, "chat": bool(checks.get("chat_completions_sampling" if capability.get("api") == "responses"
                         else "sampling", {}).get("supported")), "configured_api": bool(checks.get("sampling", {}).get("supported")),
                         "thinking": capability.get("thinking_type")},
            "simulations": simulations_of(root, draft_id)}


def scout_view(path):
    """Scout's verdicts for the reviewer, each cited page as a screenshot URL; None before analysis writes it."""
    scout = read_json(path / "scout.json")
    if scout is None:
        return None
    url = f"/api/drafts/{quote(path.name)}/scout/"
    return {"status": scout["status"], "reason": scout.get("reason"), "counts": scout.get("counts"),
            "checks": [{**{key: row[key] for key in ("claim_id", "source", "area", "says", "verdict", "observed", "observed_quote")},
                        "screenshots": [url + f"{eid}.png" for eid in row["evidence_ids"]]} for row in scout.get("checks", [])]}


SCOUT_SHOT = re.compile(r"^[A-Za-z0-9._-]+\.png$")


def scout_screenshot(root, draft_id, name):
    path = draft_path(root, draft_id) / "scout" / "screenshots"
    target = (path / name).resolve()
    if not SCOUT_SHOT.fullmatch(name) or not target.is_relative_to(path.resolve()) or not target.is_file():
        raise NotFound("No such file")
    return target


def decide(root, draft_id, decision, draft_sha256, accept_overrides=False):
    jobs = Jobs(root)
    with jobs.transaction():
        jobs.assert_draft_idle(draft_id)
        return _decide(root, draft_id, decision, draft_sha256, accept_overrides)


def _decide(root, draft_id, decision, draft_sha256, accept_overrides):
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
    return jobs.start("prepare", [{"name": "分析资料并推荐人数与天数", "module": "orchestrator.phase1",
                                   "args": ["analyze", manual, "--run-dir", Path(root) / draft_id, *args]}], draft=draft_id)


def start_resume(root, jobs, draft_id):
    """Continue an analysis that waits for the user to accept a model that cannot read images."""
    path = draft_path(root, draft_id)
    if summary(root, path, jobs.all())["status"] != "text_only":
        raise Invalid("只有等待确认纯文本模型的运行可以继续分析")
    try:
        require(settings(), "base_url", "api_key", "model")
    except ValueError as error:
        raise Unconfigured(str(error)) from error
    return jobs.start("prepare", [{"name": "分析资料并推荐人数与天数（纯文本模型）", "module": "orchestrator.phase1",
                                   "args": ["resume", path]}], draft=draft_id)


def check_size(persona_count, duration_days, minimum):
    if not MIN_PERSONAS <= persona_count <= MAX_PERSONAS:
        raise Invalid(f"人数须在 {MIN_PERSONAS}–{MAX_PERSONAS} 之间")
    if persona_count < minimum:
        raise Invalid(f"说明书里的关键流程至少需要 {minimum} 人，每条流程才有人走")
    if not 1 <= duration_days <= MAX_DAYS:
        raise Invalid(f"天数须在 1–{MAX_DAYS} 之间")


def start_generate(root, jobs, draft_id, persona_count, duration_days):
    """Personas for an analyzed draft, with the size and length the user confirmed."""
    path = draft_path(root, draft_id)
    if summary(root, path, jobs.all())["status"] != "configuring" or (path / "draft.json").exists():
        raise Invalid("只有分析完成、尚未生成人物的运行可以生成人物")
    check_size(persona_count, duration_days, (read_json(path / "phase1_result.json", {}) or {}).get("minimum_personas", MIN_PERSONAS))
    try:
        require(settings(), "base_url", "api_key", "model")
    except ValueError as error:
        raise Unconfigured(str(error)) from error
    return jobs.start("generate", [{"name": f"生成 {persona_count} 名人物（{duration_days} 天）", "module": "orchestrator.phase1",
                                    "args": ["generate", path, "--personas", persona_count, "--days", duration_days]}], draft=draft_id)


def update_draft(root, draft_id, draft_sha256, duration_days=None, sampling=None):
    """Edits and simulation reservations share the same cross-process transaction."""
    jobs = Jobs(root)
    with jobs.transaction():
        jobs.assert_draft_idle(draft_id)
        return _update_draft(root, draft_id, draft_sha256, duration_days, sampling)


def _update_draft(root, draft_id, draft_sha256, duration_days, sampling):
    path = draft_path(root, draft_id)
    if draft_hash(path) != draft_sha256:
        raise Invalid("草稿与刚才展示的版本不同，请先重新加载")
    draft, manual = load_draft(path)
    legacy = [run_id for run_id in simulations_of(root, draft_id)
              if not (Path(root) / run_id / "approved_source" / "draft.json").is_file()]
    if legacy:
        raise Invalid("这份草稿是没有输入快照的旧运行的来源，修改会改变历史展示。请新建草稿；旧运行保持原样")
    data = draft.model_dump(mode="json")
    if duration_days is not None:
        if not 1 <= duration_days <= MAX_DAYS:
            raise Invalid(f"天数须在 1–{MAX_DAYS} 之间")
        latest = max(persona.schedule.browse_day for persona in draft.personas)
        if duration_days < latest:
            raise Invalid(f"有人物排在第 {latest} 天首次体验，天数不能少于 {latest}")
        data["run_config"]["duration_days"] = duration_days
    for persona in data["personas"]:
        if sampling and persona["persona_id"] in sampling:
            persona["sampling"] = sampling[persona["persona_id"]]  # validated with the whole draft below
    if sampling and set(sampling) - {persona["persona_id"] for persona in data["personas"]}:
        raise Invalid("采样参数里有不存在的人物")
    try:
        edited = Draft.model_validate(data)
        validate_draft(edited, manual, read_json(path / "capability_profile.json", {}))
    except ValueError as error:
        raise Invalid(validation_message(error)) from error
    write_json(path / "draft.json", edited.model_dump(mode="json"))
    save_review(path, edited, manual)
    return {"draft_sha256": draft_hash(path)}


def start_simulation(root, jobs, draft_id):
    with jobs.transaction():
        return _start_simulation(root, jobs, draft_id)


def _start_simulation(root, jobs, draft_id):
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
         "args": [Path(root) / simulation, "--run-dir", Path(root) / report, "--capability-run", Path(root) / simulation / "approved_source"]},
    ], draft=draft_id, simulation=simulation, report=report, expected=expected)
