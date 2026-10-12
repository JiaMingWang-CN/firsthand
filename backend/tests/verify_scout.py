"""Explicit live acceptance for Scout on the phase-2 fixture page: one manual claim is true, one is invented.

Uses the configured model and one Steel session (paid). Not a finding about the user's product.
"""

import argparse
import asyncio
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from unittest.mock import patch

from core.persona import Flow, ProductSummary
from core.runtime import ROOT, require_capabilities, settings, write_json
from tests.verify_phase2 import fixture_manual


def scout_manual():
    manual = fixture_manual()
    manual["flows"].append(Flow(name="导出 PDF", account_role="new_visitor", entry="页面右上角的“导出 PDF”按钮",
                                steps="点击导出 PDF → 下载文件", expected_result="浏览器下载项目清单 PDF", success_criteria="得到 PDF 文件"))
    return manual


PRODUCT = ProductSummary(positioning="生成项目清单的工具", target_users="需要整理项目的人", features=["生成项目清单", "导出 PDF"],
                         assumptions=[], target_age_min=None, target_age_max=None)


async def verify(capability_run, run_dir):
    from browser_use import BrowserSession
    from browsing.scout import run_scout
    config = settings()
    capability = require_capabilities(capability_run, config)
    html = (ROOT / "tests/fixtures/phase2.html").read_text(encoding="utf-8")
    navigate = BrowserSession.navigate_to

    async def install_fixture(browser, url, *args, **kwargs):
        await navigate(browser, url, *args, **kwargs)
        session = await browser.get_or_create_cdp_session()
        tree = await browser.cdp_client.send.Page.getFrameTree(session_id=session.session_id)
        await browser.cdp_client.send.Page.setDocumentContent(params={"frameId": tree["frameTree"]["frame"]["id"], "html": html},
                                                            session_id=session.session_id)

    with patch.object(BrowserSession, "navigate_to", install_fixture):
        scout = await run_scout(config, capability, scout_manual(), PRODUCT, run_dir)
    verdicts = {row["claim_id"]: row for row in scout["checks"]}
    trace = (run_dir / "scout" / "raw_trace.jsonl").read_text(encoding="utf-8") if (run_dir / "scout" / "raw_trace.jsonl").exists() else ""
    checks = {"completed": scout["status"] == "completed",
              "real_entry_consistent": verdicts["flow:1:entry"]["verdict"] == "consistent",
              "invented_entry_inconsistent": verdicts["flow:2:entry"]["verdict"] == "inconsistent",
              "inconsistency_cites_a_page": bool(verdicts["flow:2:entry"]["evidence_ids"]),
              "known_issues_not_in_prompt": "formatter unavailable" not in json.dumps(scout_manual_prompt(), ensure_ascii=False),
              "no_technical_tools": "technical_tool_access" not in trace}
    summary = {"passed": all(checks.values()), "scope": "synthetic development fixture; not the user's product findings",
               "checks": checks, "counts": scout["counts"]}
    write_json(run_dir / "scout_validation.json", summary)
    return summary


def scout_manual_prompt():
    from browsing.scout import plan, task
    manual = scout_manual()
    return task(manual, plan(manual, PRODUCT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capability-run", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    run_dir = (args.run_dir or ROOT / "runs" / datetime.now(timezone.utc).strftime("scout-validation-%Y%m%dT%H%M%S%fZ")).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    os.environ.update(ANONYMIZED_TELEMETRY="false", BROWSER_USE_LOGGING_LEVEL="error")
    with (run_dir / "browser.log").open("w", encoding="utf-8") as log, redirect_stdout(log), redirect_stderr(log):
        summary = asyncio.run(verify(args.capability_run, run_dir))
    print(json.dumps({"passed": summary["passed"], "checks": summary["checks"], "run_dir": str(run_dir)}, ensure_ascii=False))
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
