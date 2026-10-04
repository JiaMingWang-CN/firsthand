"""Explicit live development acceptance; does not approve or run a user's cohort."""

import argparse
import asyncio
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from unittest.mock import patch

from core.persona import Flow, ManualMetadata, Persona
from core.experience import load_experience
from core.runtime import ROOT, require_capabilities, settings, write_json


def fixture_persona(developer):
    return Persona.model_validate({
        "persona_id": "p02" if developer else "p01", "realname": "白天开发者" if developer else "深夜小白",
        "username": "dev_day" if developer else "novice_night", "gender": "女", "age": 30,
        "city": "上海", "timezone": "Asia/Shanghai", "profession": "软件开发者" if developer else "行政人员",
        "industry": "软件" if developer else "服务", "education": "本科", "income_level": "中", "life_context": "开发验收合成人设",
        "product_history": "未使用此工具", "bio": "开发验收角色", "persona":
        "熟悉网页，遇到错误愿意查看 Console 并寻找替代路径。" if developer else "不懂技术，很困，只想用默认按钮快速完成，不愿尝试高级设置。",
        "mbti": "INTJ", "big_five": {key: "中" for key in ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]},
        "communication_style": "直接", "interested_topics": ["项目清单"],
        "browsing_profile": {"device": "desktop" if developer else "mobile", "tech_level": "developer" if developer else "novice",
            "patience": "high" if developer else "low", "max_steps": 20 if developer else 8, "stall_limit": 6 if developer else 2,
            "motivation": "有明确任务", "motivation_detail": "生成项目清单", "account_role": "new_visitor",
            "tools": ["read_console", "list_failed_requests"] if developer else [], "assignment": {"type": "task", "flow": "生成项目清单"}},
        "schedule": {"wake": "06:30" if developer else "10:00", "sleep": "23:00" if developer else "03:00",
            "activity_by_hour": {12: 0.5}, "browse_slot": "10:00" if developer else "01:00",
            "state_at_browse": "白天精力充足，愿意排查问题" if developer else "深夜很困，疲惫，不愿尝试更多设置，默认操作没有反馈就放弃"},
        "participation": "lurker", "disclosure": {"candor": "低", "withhold_tendency": "高", "withhold_reasons": ["怕显得自己不会用"]},
    })


def fixture_manual():
    flow = Flow(name="生成项目清单", account_role="new_visitor", entry="页面生成清单按钮", steps="阅读项目 → 生成清单",
                expected_result="展示项目清单", success_criteria="页面可见‘清单已生成’及项目 A、项目 B")
    return {"metadata": ManualMetadata(name="开发验收故障夹具", url="https://example.com", allowed_domains=["example.com"],
                test_accounts=[{"role": "new_visitor", "description": "无登录"}],
                forbidden_actions=["向外发送消息", "支付、注册或修改真实账号", "访问 example.com 以外的站点"]),
            "sections": {"产品定位": "生成项目清单的本地浏览器验收夹具", "核心功能": "默认生成和文本生成",
                "已知问题": "默认生成按钮没有页面反馈，Console 记录 formatter unavailable，文本路径可以完成。"}, "flows": [flow]}


async def verify(capability_run, run_dir):
    from browser_use import BrowserSession
    from browsing.experience import run_experience
    config = settings()
    capability = require_capabilities(capability_run, config)
    manual = fixture_manual()
    html = (ROOT / "tests/fixtures/phase2.html").read_text(encoding="utf-8")
    navigate = BrowserSession.navigate_to

    async def install_fixture(browser, url, *args, **kwargs):
        await navigate(browser, url, *args, **kwargs)
        session = await browser.get_or_create_cdp_session()
        tree = await browser.cdp_client.send.Page.getFrameTree(session_id=session.session_id)
        await browser.cdp_client.send.Page.setDocumentContent(params={"frameId": tree["frameTree"]["frame"]["id"], "html": html},
                                                            session_id=session.session_id)

    results = {}
    with patch.object(BrowserSession, "navigate_to", install_fixture):
        for name, developer in [("novice_night", False), ("developer_day", True)]:
            results[name] = await run_experience(config, capability, manual, fixture_persona(developer), run_dir / name)
    memories = {name: load_experience(run_dir / name).model_dump() for name in results}
    pains = {name: [finding for finding in memory["assessment"]["findings"] if finding["kind"] == "pain"]
             for name, memory in memories.items() if memory["assessment"]}
    developer_actions = [action for step in memories["developer_day"]["steps"] for action in step["actions"]]
    checks = {"both_experiences_valid": all(result["passed"] for result in results.values()),
              "both_find_known_failure": all(pains.get(name) for name in results),
              "novice_did_not_complete": memories["novice_night"]["outcome"] in {"failed", "abandoned"},
              "developer_completed": memories["developer_day"]["outcome"] == "success",
              "developer_completion_visible": any("清单已生成：项目 A" in item["text"] for item in memories["developer_day"]["snapshots"]),
              "developer_queried_console": any("read_console" in action for action in developer_actions),
              "novice_no_technical_access": not memories["novice_night"]["observed_technical_events"],
              "released_both_sessions": all(result.get("released") for result in results.values())}
    summary = {"passed": all(checks.values()), "scope": "synthetic development fixture; not the user's product findings",
               "checks": checks, "results": results}
    write_json(run_dir / "phase2_validation.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capability-run", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    run_dir = (args.run_dir or ROOT / "runs" / datetime.now(timezone.utc).strftime("phase2-validation-%Y%m%dT%H%M%S%fZ")).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    os.environ.update(ANONYMIZED_TELEMETRY="false", BROWSER_USE_LOGGING_LEVEL="error")
    with (run_dir / "browser.log").open("w", encoding="utf-8") as log, redirect_stdout(log), redirect_stderr(log):
        summary = asyncio.run(verify(args.capability_run, run_dir))
    print(json.dumps({"passed": summary["passed"], "checks": summary["checks"], "run_dir": str(run_dir)}, ensure_ascii=False))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
