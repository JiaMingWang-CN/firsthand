"""Markdown view of report.json; links are relative to the report directory so they open from there."""

import os
from pathlib import Path

from report.agent import FLAG_TEXT

SOURCE_LABEL = {"withheld": "本人选择不公开", "lurker": "潜水者", "reactor": "点赞者", "unshared": "未公开", "survey_unsaid": "问卷自述没说出口"}


def link(source, out, relative, label=None):
    target = Path(source) / relative
    try:
        href = Path(os.path.relpath(target, out)).as_posix()
    except ValueError:  # Windows: source and report on different drives
        href = target.resolve().as_uri()
    return f"[{label or relative}]({href})"


def evidence_line(item, source, out):
    parts = [f"`{item['ref_id']}`", link(source, out, item["path"])]
    parts += [link(source, out, shot, "截图") for shot in item["screenshots"]]
    for video in item["video"]:
        if video.get("viewer_url"):
            parts.append(f"[录像 ≈{video['seconds']:.0f}s]({video['viewer_url']})")
    if item["trace_event_ids"]:
        parts.append("技术事件 " + "、".join(item["trace_event_ids"]))
    return f"  - {' · '.join(parts)}：“{item['quote']}”"


def claim_block(index, item, source, out):
    flags = f" ⚠ {'；'.join(item['review_flags'])}" if item["review_flags"] else ""
    lines = [f"{index}. **{item['title']}**（严重度 {item['severity']}，影响 {len(item['affected_personas'])} 人："
             f"{'、'.join(item['affected_personas'])}；证据强度 {item['evidence_strength']:g}）{flags}", f"   {item['detail']}"]
    return lines + [evidence_line(e, source, out) for e in item["evidence"]]


def render(report, source, out, product="产品"):
    o = report["overview"]
    lines = [f"# {product}体验报告", "", f"证据来源：`{Path(source).name}`（只读）。每条结论都附带可追溯的证据编号、原文和链接。", "",
             "## 1. 总览", "",
             f"- 任务结果：{o['task_outcomes']}；无已校验体验 {o['no_experience']} 人；成功率 {o['success_rate']:.0%}",
             f"- NPS：{o['nps']}（推荐者 {o['nps_counts']['promoters']}，中立 {o['nps_counts']['passives']}，贬损者 {o['nps_counts']['detractors']}）",
             f"- 继续使用：{o['continue_using']}；付费意愿：{o['would_pay']}", "", "**覆盖说明**", ""]
    lines += [f"- {note}" for note in o["coverage_notes"]]
    for number, (key, title) in enumerate([("issues", "问题清单"), ("highlights", "亮点")], start=2):
        lines += ["", f"## {number}. {title}", "", "按“影响人数 × 严重度 × 证据强度”排序，不按社区点赞。", ""]
        items = report["sections"][key]
        for index, item in enumerate(items, start=1):
            lines += claim_block(index, item, source, out)
        if not items:
            lines.append("本次没有通过证据门禁的结论。")
    lines += ["", "## 4. 公开声音与沉默信号", "", "### 4.1 社区里说出来的", ""]
    voice = report["public_voice"]
    lines.append(f"共 {len(voice['items'])} 条帖子和评论，发言者 {len(voice['counts'])} 人。")
    lines.append("下列内容截取前 120 字，完整文本见 report.json。")
    lines += [f"- `{item['ref_id']}` {item['persona_id']}（{item['participation']}）：{item['content'].replace(chr(10), ' ')[:120]}" for item in voice["items"]]
    lines += ["", "### 4.2 体验了但没说的", ""]
    lines += [f"- `{s['finding_id']}` {s['persona_id']}（{s['participation']}，{SOURCE_LABEL[s['source']]}）{s['kind']}：{s['title']} —— 原因：{'；'.join(s['reasons'])}"
              + ("（其他场合公开过）" if s["also_public"] else "") + (" ⚠ " + "；".join(s["review_flags"]) if s["review_flags"] else "")
              + f"；证据 {'、'.join(s['refs'])}" for s in report["silence_signals"]]
    lines += ["", "### 4.3 公开讨论与私下问卷是否一致", "", "| Persona | 任务 | NPS | 继续用 | 付费 | 公开发言数 | 待复核 |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {c['persona_id']} | {c['outcome']} | {c['nps']} | {c['continue_using']} | {c['would_pay']} | {c['public_items']} | "
              f"{'；'.join(c['flag_notes']) or '—'} |" for c in report["consistency"]]
    dynamics = report["opinion_dynamics"]
    lines += ["", "## 5. 舆论动态", "", f"共 {dynamics['read_records']} 条看帖记录。", "", "| Persona | 体验前看帖 | 体验后看帖 |", "|---|---|---|"]
    lines += [f"| {pid} | {v['before_experience']} | {v['after_experience']} |" for pid, v in sorted(dynamics["by_persona"].items())]
    lines += ["", "**自述观点被改变**", ""]
    lines += [f"- {c['persona_id']} ← 帖子 {c['post_ids']}（{'、'.join(c['refs'])}）" for c in dynamics["opinion_changes"]] or ["- 无"]
    lines += ["", "**触达人数最多的帖子（触达量，不是点赞）**", ""]
    lines += [f"- 帖子 {p['post_id']}：{len(p['readers'])} 人看过，其中 {len(p['read_before_own_experience'])} 人在自己体验之前看过" for p in dynamics["post_reach"]]
    lines += ["", "## 6. 分时段的体验差异", "", "样本很小且时段与人设混杂，只能作为线索。", "",
              "| 时段 | Persona | 结果 | 平均满意 | 平均困惑 |", "|---|---|---|---|---|"]
    lines += [f"| {t['period']} | {'、'.join(t['personas']) or '—'} | {t['outcomes']} | {t['mean_satisfaction']} | {t['mean_confusion']} |" for t in report["time_slots"]]
    lines += ["", "## 7. 说明书与实际产品的不一致（Scout）", "", report["scout"]["note"]]
    if report["rejected_claims"]:
        lines += ["", "## 附：被证据门禁退回的结论", ""]
        lines += [f"- [{r['section']}] {r['title']}：{r['reason']}" for r in report["rejected_claims"]]
    lines += ["", "## 附：问卷一致性标记说明", ""] + [f"- `{key}`：{text}" for key, text in FLAG_TEXT.items()]
    return "\n".join(lines) + "\n"
