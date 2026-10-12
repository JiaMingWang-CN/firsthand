"""Validate a manual, prepare a reviewable draft, and record human approval."""

import argparse
import asyncio
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from openai import APIError, AsyncOpenAI

from core.persona import MAX_DAYS, MAX_PERSONAS, MIN_PERSONAS, Draft, ProductSummary
from core.runtime import ROOT, TEXT_ONLY_NOTE, error_summary, require, require_capabilities, sees_images, settings, write_json
from orchestrator.manual import material, read_manual
from orchestrator.personas import (distribution_issues, generate_draft, minimum_count, period, recommend, schedule_rows,
                                   summarize_product, validate_draft, validation_message, with_site)
from orchestrator.site import read_site
from browsing.scout import run_scout, scout_rows, scout_status, skip as skip_scout
from probe.model import probe_model


def draft_hash(run_dir):
    digest = hashlib.sha256()
    for name in ["manual.md", "draft.json", "capability_profile.json"]:
        content = (Path(run_dir) / name).read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def load_draft(run_dir):
    run_dir = Path(run_dir)
    manual = read_manual(run_dir / "manual.md")
    draft = Draft.model_validate_json((run_dir / "draft.json").read_text(encoding="utf-8"))
    capability = json.loads((run_dir / "capability_profile.json").read_text(encoding="utf-8"))
    validate_draft(draft, manual, capability)
    return draft, manual


def save_review(run_dir, draft, manual):
    run_dir = Path(run_dir)
    rows = schedule_rows(draft)
    about = material(manual)
    write_json(run_dir / "schedule.json", rows)
    write_json(run_dir / "product_model.json", {"metadata": manual["metadata"].model_dump(),
               "summary": draft.product.model_dump(), "flows": [flow.model_dump() for flow in manual["flows"]],
               "sections": manual["sections"]})
    lines = [f"# {manual['metadata'].name}：阶段 1 人工审核", "",
             "此文件是展示副本；修改 draft.json 后，在 CLI 中 reload。审批状态以与当前草稿匹配的 approval.json 为准。",
             *scout_rows(run_dir), "",
             f"资料充分程度：{about['summary']}", *[f"- 缺少 {gap['item']}：{gap['effect']}" for gap in about["gaps"]], "",
             *([TEXT_ONLY_NOTE, ""] if not sees_images(json.loads((run_dir / "capability_profile.json").read_text(encoding="utf-8"))) else []),
             "## 产品模型", "", json.dumps(draft.product.model_dump(), ensure_ascii=False, indent=2), "",
             "## 模拟配置", "", "```json", draft.run_config.model_dump_json(indent=2), "```", "",
             "浏览并发同时受环境中的模型上限、浏览器上限和能力探测建议值限制；Steel 套餐需匹配该配置。", "",
             "## 主 Agent 的分布方案", "", draft.cohort_rationale, "",
             "按当前草稿统计：", "", *distribution_summary(draft), "",
             "## Persona 与时间表", "", "| ID | 姓名 | 年龄/性别 | 设备/技术/耐心 | 动机 | 参与 | 本地体验时间 | UTC时间片 | 任务 | 温度/top_p |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    people = {persona.persona_id: persona for persona in draft.personas}
    for row in rows:
        p = people[row["persona_id"]]
        profile = p.browsing_profile
        values = [p.persona_id, p.realname, f"{p.age}/{p.gender}", f"{profile.device}/{profile.tech_level}/{profile.patience}",
                  profile.motivation, p.participation, row["local_time"], str(row["slice_index"]), profile.assignment.flow or "自由探索",
                  f"{p.sampling.temperature}/{p.sampling.top_p}" if p.sampling else "默认"]
        lines.append("| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in values) + " |")
    issues = distribution_issues(draft, manual)
    lines.extend(["", "分布校验：" + ("；".join(issues) if issues else "全部通过"), ""])
    for p in draft.personas:
        lines.extend([f"## {p.persona_id} · {p.realname}", "", "```json", p.model_dump_json(indent=2), "```", ""])
    (run_dir / "review.md").write_text("\n".join(lines), encoding="utf-8")


def distribution_summary(draft):
    # Counts come from the slots themselves, never from the model's own description of them.
    dimensions = {
        "性别": lambda p: p.gender, "年代": lambda p: f"{p.age // 10 * 10}s",
        "技术": lambda p: p.browsing_profile.tech_level, "设备": lambda p: p.browsing_profile.device,
        "耐心": lambda p: p.browsing_profile.patience, "动机": lambda p: p.browsing_profile.motivation,
        "参与": lambda p: p.participation, "隐瞒倾向": lambda p: p.disclosure.withhold_tendency,
        "时段": lambda p: period(p.schedule.browse_slot), "任务": lambda p: p.browsing_profile.assignment.flow or "自由探索",
    }
    return [f"- {name}：" + "，".join(f"{value} {count}" for value, count in sorted(Counter(map(key, draft.personas)).items()))
            for name, key in dimensions.items()]


def require_approved(run_dir):
    run_dir = Path(run_dir)
    draft, manual = load_draft(run_dir)
    path = run_dir / "approval.json"
    if not path.exists():
        raise ValueError("Persona 和配置尚未通过人工审核")
    approval = json.loads(path.read_text(encoding="utf-8"))
    if approval.get("status") != "approved" or approval.get("draft_sha256") != draft_hash(run_dir):
        raise ValueError("审批已失效：说明书、草稿或能力文件有修改，需重新审核")
    issues = distribution_issues(draft, manual)
    if issues != approval.get("distribution_overrides", []):
        raise ValueError("审批没有覆盖当前的人群分布变更")
    return draft, manual


class OverrideRequired(ValueError):
    """The draft's cohort no longer matches the planned distribution; approving needs explicit confirmation."""

    def __init__(self, issues):
        super().__init__("分布已改变：" + "；".join(issues))
        self.issues = issues


def approve(run_dir, displayed_hash, accept_overrides=False):
    """Approve exactly the draft the reviewer was shown (CLI and Web UI share this). Returns accepted overrides."""
    run_dir = Path(run_dir)
    # Reload after the decision: do not approve a version edited while the reviewer was reading.
    if draft_hash(run_dir) != displayed_hash:
        raise ValueError("草稿与刚才展示的版本不同，请先重新加载后再批准")
    draft, manual = load_draft(run_dir)
    require_capabilities(run_dir, settings())
    issues = distribution_issues(draft, manual)
    if issues and not accept_overrides:
        raise OverrideRequired(issues)
    save_review(run_dir, draft, manual)
    if draft_hash(run_dir) != displayed_hash:
        raise ValueError("审核过程中草稿有修改，请重新审核")
    write_json(run_dir / "approval.json", {"status": "approved", "draft_sha256": displayed_hash,
               "approved_at": datetime.now(timezone.utc).isoformat(), "distribution_overrides": issues})
    return issues


def reject(run_dir):
    write_json(Path(run_dir) / "approval.json", {"status": "rejected", "draft_sha256": draft_hash(run_dir)})


def review(run_dir, input_fn=input):
    run_dir = Path(run_dir)
    print(f"编辑文件：{run_dir / 'draft.json'}")
    print("命令：show（完整展示）、reload（重新校验）、approve（批准）、reject（拒绝）、quit（暂存退出）")
    while True:
        try:
            displayed_hash = draft_hash(run_dir)
            draft, manual = load_draft(run_dir)
            issues = distribution_issues(draft, manual)
            save_review(run_dir, draft, manual)
            for p in draft.personas:
                print(f"{p.persona_id} {p.realname} {p.age}/{p.gender} {p.profession} "
                      f"{p.browsing_profile.device}/{p.browsing_profile.tech_level}/{p.browsing_profile.patience} "
                      f"{p.browsing_profile.motivation} {p.participation} {p.timezone} {p.schedule.browse_slot}")
            print("分布校验：" + ("；".join(issues) if issues else "通过"))
            if draft_hash(run_dir) != displayed_hash:
                raise ValueError("展示过程中草稿有修改，请重新加载")
        except (ValueError, OSError) as error:
            draft = None
            print("草稿校验失败：" + validation_message(error))
        try:
            command = input_fn("review> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("已保留草稿，未批准执行。")
            return
        if command == "quit":
            return
        if command == "reject":
            reject(run_dir)
            print("已拒绝。")
            return
        if command == "show":
            if draft:
                print((run_dir / "review.md").read_text(encoding="utf-8"))
            continue
        if command in {"approve", "approve overrides"}:
            try:
                if draft is None:
                    raise ValueError("草稿与刚才展示的版本不同，请先重新加载后再批准")
                approve(run_dir, displayed_hash, accept_overrides=command == "approve overrides")
                print("已批准当前草稿。阶段 1 不会启动浏览或讨论执行。")
                return
            except OverrideRequired as error:
                print(f"{error}。确认这些变更时输入 approve overrides。")
            except (ValueError, OSError) as error:
                print("不能批准：" + validation_message(error))
        elif command != "reload":
            print("未知命令。")


async def analyze(manual_path, run_dir, capability_run=None, scout=True):
    """Manual → capability profile, start-page excerpt, product model and the main agent's cohort recommendation.

    Nothing about people is generated yet: the user confirms or changes the recommended size and length first."""
    # Validation precedes configuration, run creation and all paid API requests.
    manual = read_manual(manual_path)
    config = settings()
    require(config, "base_url", "api_key", "model")
    run_dir = Path(run_dir)
    if run_dir.exists():
        raise ValueError("运行目录已存在，请使用新目录以保留历史产物")
    run_dir.mkdir(parents=True)
    print(f"运行产物：{run_dir}", flush=True)
    (run_dir / "manual.md").write_text(manual["source"], encoding="utf-8")
    write_json(run_dir / "scout.json", {"status": "pending", "findings": [],
               "reason": "阶段 1 尚未运行 Scout 侦察；此处不推断网站实测结果"})
    try:
        if capability_run:
            capability = require_capabilities(capability_run, config)
            write_json(run_dir / "capability_profile.json", capability)
        else:
            capability = await probe_model(config, run_dir)
            if not capability["ready"]:
                raise ValueError("模型能力未通过；中止生成人设")
            if not sees_images(capability):
                # Nothing more is paid for until the user accepts the limited reference value (resume).
                result = {"stage": "text_only", "passed": True, "review_status": "pending", "scout": scout}
                write_json(run_dir / "phase1_result.json", result)
                return result
        return await analyze_product(run_dir, manual, config, capability, scout)
    except Exception as error:
        write_json(run_dir / "phase1_result.json", {"passed": False, "review_status": "pending", "error": error_summary(error, run_dir)})
        raise


async def resume(run_dir):
    """Continue an analysis paused because the model cannot read images, once the user has accepted that."""
    run_dir = Path(run_dir)
    paused = json.loads((run_dir / "phase1_result.json").read_text(encoding="utf-8"))
    if paused.get("stage") != "text_only":
        raise ValueError("只有等待确认纯文本模型的运行可以继续分析")
    manual = read_manual(run_dir / "manual.md")
    config = settings()
    require(config, "base_url", "api_key", "model")
    try:
        return await analyze_product(run_dir, manual, config, require_capabilities(run_dir, config), paused.get("scout", True))
    except Exception as error:
        write_json(run_dir / "phase1_result.json", {"passed": False, "review_status": "pending", "error": error_summary(error, run_dir)})
        raise


async def analyze_product(run_dir, manual, config, capability, scout=True):
    """Start-page excerpt, product model, then Scout alongside the main agent's cohort recommendation."""
    if not sees_images(capability):
        print(TEXT_ONLY_NOTE, flush=True)
    site = await read_site(manual["metadata"].url, manual["metadata"].allowed_domains)
    write_json(run_dir / "site.json", site)
    print("首页摘录：" + (f"已读取 {len(site['text'])} 字" if site["status"] == "ok" else f"未读取（{site['reason']}）"), flush=True)
    source = with_site(manual, site)
    about = material(manual)
    async with AsyncOpenAI(base_url=config["base_url"], api_key=config["api_key"], timeout=120, max_retries=0) as client:
        product = await summarize_product(client, config, capability, source)
        write_json(run_dir / "product.json", product.model_dump(mode="json"))
        # Scout records its own failures; a failed recommendation cancels Scout and releases its browser.
        try:
            async with asyncio.TaskGroup() as group:
                recommendation = group.create_task(recommend(client, config, capability, source, product, about))
                if scout:
                    group.create_task(run_scout(config, capability, manual, product, run_dir))
        except ExceptionGroup as failure:
            raise failure.exceptions[0]
        suggestion = recommendation.result()
    if not scout:
        skip_scout(run_dir, manual, product, "按要求跳过侦察")
    result = {"stage": "analyzed", "passed": True, "review_status": "pending", "material": about,
              "recommendation": suggestion.model_dump(), "minimum_personas": minimum_count(len(manual["flows"]))}
    write_json(run_dir / "recommendation.json", result["recommendation"])
    write_json(run_dir / "phase1_result.json", result)
    print(f"推荐：{suggestion.persona_count} 人，{suggestion.duration_days} 天。{suggestion.reason}", flush=True)
    return result


async def generate(run_dir, persona_count=None, duration_days=None):
    """Personas and run configuration for an analyzed run, with the user's (or the recommended) size and length."""
    run_dir = Path(run_dir)
    analyzed = json.loads((run_dir / "phase1_result.json").read_text(encoding="utf-8"))
    if analyzed.get("stage") != "analyzed" or (run_dir / "draft.json").exists():
        raise ValueError("只能为已分析、尚未生成人物的运行生成人物")
    count = persona_count or analyzed["recommendation"]["persona_count"]
    days = duration_days or analyzed["recommendation"]["duration_days"]
    if not MIN_PERSONAS <= count <= MAX_PERSONAS or not 1 <= days <= MAX_DAYS:
        raise ValueError(f"人数须在 {MIN_PERSONAS}–{MAX_PERSONAS}，天数须在 1–{MAX_DAYS}")
    manual = read_manual(run_dir / "manual.md")
    config = settings()
    require(config, "base_url", "api_key", "model")
    capability = require_capabilities(run_dir, config)
    site = json.loads((run_dir / "site.json").read_text(encoding="utf-8")) if (run_dir / "site.json").exists() else None
    product = ProductSummary.model_validate_json((run_dir / "product.json").read_text(encoding="utf-8"))
    print(f"生成 {count} 人，{days} 天", flush=True)
    try:
        draft = await generate_draft(config, capability, with_site(manual, site), product, count, days)
        write_json(run_dir / "draft.json", draft.model_dump(mode="json"))
        save_review(run_dir, draft, manual)
        write_json(run_dir / "phase1_result.json", {**analyzed, "stage": "drafted", "persona_count": count, "duration_days": days,
                   "distribution_issues": [], "scout_status": scout_status(run_dir)})
        return draft
    except Exception as error:
        # The analysis stays usable: the user may retry, with the same or other numbers.
        write_json(run_dir / "phase1_result.json", {**analyzed, "generation_error": error_summary(error, run_dir)})
        raise


async def prepare(manual_path, run_dir, capability_run=None, persona_count=None, duration_days=None, scout=True):
    """analyze + generate in one go, for the command line; stops where analyze waits for a text-only confirmation."""
    if (await analyze(manual_path, run_dir, capability_run, scout))["stage"] == "text_only":
        return None
    return await generate(run_dir, persona_count, duration_days)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate")
    check.add_argument("manual", type=Path)
    for name in ["analyze", "prepare"]:
        command = commands.add_parser(name)
        command.add_argument("manual", type=Path)
        command.add_argument("--run-dir", type=Path)
        command.add_argument("--capability-run", type=Path, help="显式复用同模型、同思考模式的能力探测结果")
        command.add_argument("--no-scout", action="store_true", help="跳过 Scout 侦察（不核对说明书与实际网站）")
    commands.add_parser("resume", help="接受纯文本模型参考性有限后继续分析").add_argument("run_dir", type=Path)
    build = commands.add_parser("generate")
    build.add_argument("run_dir", type=Path)
    for command in [commands.choices["prepare"], build]:
        command.add_argument("--personas", type=int, help="人数；不给时用主 Agent 的推荐")
        command.add_argument("--days", type=int, help="模拟天数；不给时用主 Agent 的推荐")
    approval = commands.add_parser("review")
    approval.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            manual = read_manual(args.manual)
            about = material(manual)
            print(f"说明书校验通过：{manual['metadata'].name}，{len(manual['flows'])} 个关键流程；{about['summary']}")
        elif args.command == "review":
            review(args.run_dir.resolve())
        elif args.command == "resume":
            asyncio.run(resume(args.run_dir.resolve()))
            print(f"已分析，确认人数和天数后生成人物：python -m orchestrator.phase1 generate {args.run_dir.resolve()} --personas N --days D")
        elif args.command == "generate":
            asyncio.run(generate(args.run_dir.resolve(), args.personas, args.days))
            print(f"阶段 1 草稿已生成，等待人工审核：{args.run_dir.resolve() / 'review.md'}")
        else:
            run_dir = (args.run_dir or ROOT / "runs" / datetime.now(timezone.utc).strftime("phase1-%Y%m%dT%H%M%S%fZ")).resolve()
            if args.command == "analyze":
                done = asyncio.run(analyze(args.manual, run_dir, args.capability_run, not args.no_scout))["stage"] == "analyzed"
            else:
                done = asyncio.run(prepare(args.manual, run_dir, args.capability_run, args.personas, args.days, not args.no_scout)) is not None
            if not done:
                print(f"{TEXT_ONLY_NOTE}。接受后继续分析：python -m orchestrator.phase1 resume {run_dir}")
            elif args.command == "analyze":
                print(f"已分析，确认人数和天数后生成人物：python -m orchestrator.phase1 generate {run_dir} --personas N --days D")
            else:
                print(f"阶段 1 草稿已生成，等待人工审核：{run_dir / 'review.md'}")
    except (ValueError, OSError) as error:
        print("错误：" + validation_message(error))
        raise SystemExit(1)
    except APIError as error:
        print(f"模型 API 调用失败：{type(error).__name__}；请查看运行目录的 errors.log")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
