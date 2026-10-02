"""Validate a manual, prepare a reviewable draft, and record human approval."""

import argparse
import asyncio
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from openai import APIError

from core.persona import Draft
from core.runtime import ROOT, error_summary, require, require_capabilities, settings, write_json
from orchestrator.manual import read_manual
from orchestrator.personas import distribution_issues, generate_draft, period, schedule_rows, validate_draft, validation_message
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
    write_json(run_dir / "schedule.json", rows)
    write_json(run_dir / "product_model.json", {"metadata": manual["metadata"].model_dump(),
               "summary": draft.product.model_dump(), "flows": [flow.model_dump() for flow in manual["flows"]],
               "sections": manual["sections"]})
    lines = [f"# {manual['metadata'].name}：阶段 1 人工审核", "",
             "此文件是展示副本；修改 draft.json 后，在 CLI 中 reload。审批状态以与当前草稿匹配的 approval.json 为准。",
             "阶段 0 浏览验证待解决，Scout 尚未执行；本文件不包含真实产品体验结论。", "",
             "## 产品模型", "", json.dumps(draft.product.model_dump(), ensure_ascii=False, indent=2), "",
             "## 模拟配置", "", "```json", draft.run_config.model_dump_json(indent=2), "```", "",
             "默认并发为 1；Steel 套餐并发上限尚未验证。", "",
             "## 主 Agent 的分布方案", "", draft.cohort_rationale, "",
             "按当前草稿统计：", "", *distribution_summary(draft), "",
             "## Persona 与时间表", "", "| ID | 姓名 | 年龄/性别 | 设备/技术/耐心 | 动机 | 参与 | 本地体验时间 | UTC时间片 | 任务 |",
             "|---|---|---|---|---|---|---|---|---|"]
    people = {persona.persona_id: persona for persona in draft.personas}
    for row in rows:
        p = people[row["persona_id"]]
        profile = p.browsing_profile
        values = [p.persona_id, p.realname, f"{p.age}/{p.gender}", f"{profile.device}/{profile.tech_level}/{profile.patience}",
                  profile.motivation, p.participation, row["local_time"], str(row["slice_index"]), profile.assignment.flow or "自由探索"]
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
            write_json(run_dir / "approval.json", {"status": "rejected", "draft_sha256": draft_hash(run_dir)})
            print("已拒绝。")
            return
        if command == "show":
            if draft:
                print((run_dir / "review.md").read_text(encoding="utf-8"))
            continue
        if command in {"approve", "approve overrides"}:
            # Reload after the command: do not approve a version edited during the prompt.
            try:
                if draft is None or draft_hash(run_dir) != displayed_hash:
                    raise ValueError("草稿与刚才展示的版本不同，请先重新加载后再批准")
                snapshot_hash = displayed_hash
                draft, manual = load_draft(run_dir)
                require_capabilities(run_dir, settings())
                issues = distribution_issues(draft, manual)
                if issues and command != "approve overrides":
                    print("分布已改变：" + "；".join(issues) + "。确认这些变更时输入 approve overrides。")
                    continue
                save_review(run_dir, draft, manual)
                if draft_hash(run_dir) != snapshot_hash:
                    raise ValueError("审核过程中草稿有修改，请重新审核")
                write_json(run_dir / "approval.json", {"status": "approved", "draft_sha256": snapshot_hash,
                           "approved_at": datetime.now(timezone.utc).isoformat(), "distribution_overrides": issues})
                print("已批准当前草稿。阶段 1 不会启动浏览或讨论执行。")
                return
            except (ValueError, OSError) as error:
                print("不能批准：" + validation_message(error))
        elif command != "reload":
            print("未知命令。")


async def prepare(manual_path, run_dir, capability_run=None):
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
               "reason": "阶段 0 浏览验证尚未通过；阶段 1 继续生成，未运行 Scout，也不推断网站实测结果"})
    try:
        if capability_run:
            capability = require_capabilities(capability_run, config)
            write_json(run_dir / "capability_profile.json", capability)
        else:
            capability = await probe_model(config, run_dir)
            if not capability["ready"]:
                raise ValueError("模型能力未通过；中止生成人设")
        draft = await generate_draft(config, capability, manual)
        write_json(run_dir / "draft.json", draft.model_dump(mode="json"))
        save_review(run_dir, draft, manual)
        write_json(run_dir / "phase1_result.json", {"passed": True, "review_status": "pending",
                   "persona_count": 10, "distribution_issues": [], "scout_status": "pending"})
        return draft
    except Exception as error:
        write_json(run_dir / "phase1_result.json", {"passed": False, "review_status": "pending", "error": error_summary(error, run_dir)})
        raise


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate")
    check.add_argument("manual", type=Path)
    generate = commands.add_parser("prepare")
    generate.add_argument("manual", type=Path)
    generate.add_argument("--run-dir", type=Path)
    generate.add_argument("--capability-run", type=Path, help="显式复用同模型、同思考模式的能力探测结果")
    approval = commands.add_parser("review")
    approval.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            manual = read_manual(args.manual)
            print(f"说明书校验通过：{manual['metadata'].name}，{len(manual['flows'])} 个关键流程")
        elif args.command == "review":
            review(args.run_dir.resolve())
        else:
            run_dir = (args.run_dir or ROOT / "runs" / datetime.now(timezone.utc).strftime("phase1-%Y%m%dT%H%M%S%fZ")).resolve()
            asyncio.run(prepare(args.manual, run_dir, args.capability_run))
            print(f"阶段 1 草稿已生成，等待人工审核：{run_dir / 'review.md'}")
    except (ValueError, OSError) as error:
        print("错误：" + validation_message(error))
        raise SystemExit(1)
    except APIError as error:
        print(f"模型 API 调用失败：{type(error).__name__}；请查看运行目录的 errors.log")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
