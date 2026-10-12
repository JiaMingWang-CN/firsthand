"""Phase 9: Scout checks the manual against the real site, with evidence, without touching personas."""

import asyncio
import hashlib
import json
import shutil

import pytest

from browsing import scout
from browsing.experience import session_seconds
from browsing.observations import ObservationGateway
from browsing.policy import account_secrets
from core.experience import ExperienceMemory, Snapshot
from core.persona import ProductSummary, TestAccount as Account
from core.runtime import write_json
from orchestrator import phase1
from orchestrator.manual import read_manual
from tests.verify_phase2 import fixture_manual
from test_phase1 import CAPABILITY, CONFIG, SAMPLE, draft  # noqa: F401  (draft is a fixture)
from test_pipeline import configured  # noqa: F401  (a fixture)
from test_phase7 import cohort, mock_model

PRODUCT = ProductSummary(positioning="清单工具", target_users="项目经理", features=["生成项目清单", "导出 PDF"], assumptions=[],
                         target_age_min=None, target_age_max=None)
STEEL = {**CONFIG, "steel_api_key": "test"}


def snapshot(eid, text, seconds):
    return Snapshot(evidence_id=eid, url="https://example.com", title="工具", text=text, screenshot=f"screenshots/{eid}.png",
                    screenshot_sha256="a" * 64, scroll_x=0, scroll_y=0, video_seconds=seconds)


def memory():
    return ExperienceMemory(persona_id="scout", state_at_browse="核对", assignment={"type": "explore", "flow": None}, expectations=[],
        outcome="success", reason="清单已看完", outcome_source="agent_self_report", session={},
        snapshots=[snapshot("s001_before", "首页\n生成清单", 1), snapshot("s001_after", "清单已生成：项目 A", 2)],
        steps=[{"step": 1, "before": "s001_before", "after": "s001_after", "seconds": 1, "actions": [{"click": {"index": 1}}],
                "results": [], "agent_observation": "", "stalled": False}],
        observed_technical_events=[], assessment=None, infrastructure_errors=[])


def check(claim_id, verdict, evidence=(), quote=""):
    return scout.Check(claim_id=claim_id, verdict=verdict, observed="看到的情况", evidence_ids=list(evidence), observed_quote=quote)


def snapshots():
    return {item.evidence_id: item for item in memory().snapshots}


def test_the_checklist_comes_from_the_manual_and_marks_what_the_agent_inferred():
    manual = fixture_manual()
    manual["metadata"].test_accounts.append(Account(role="free_user", description="免费账号"))
    claims = scout.plan(manual, PRODUCT)
    assert [claim["claim_id"] for claim in claims] == ["flow:1:entry", "flow:1:steps", "feature:1", "feature:2", "account:login"]
    assert {claim["source"] for claim in claims if claim["claim_id"].startswith("feature")} == {scout.SOURCE_AGENT}
    assert "free_user" in claims[-1]["says"] and "new_visitor" not in claims[-1]["says"]
    prompt = scout.task(manual, claims)
    assert "formatter unavailable" not in prompt  # the known issues stay a calibration set


def test_a_flow_that_needs_an_account_is_checked_only_up_to_the_login():
    manual = read_manual(SAMPLE)
    claims = {claim["claim_id"]: claim for claim in scout.plan(manual, PRODUCT)}
    for index, flow in enumerate(manual["flows"], 1):
        assert claims[f"flow:{index}:entry"]["needs_login"] is False
        assert claims[f"flow:{index}:steps"]["needs_login"] is (flow.account_role != "new_visitor")


def test_the_inspector_browses_as_a_visitor_without_technical_tools():
    inspector = scout.Inspector()
    assert account_secrets(inspector, fixture_manual()) == ({}, [])
    assert ObservationGateway(inspector, None).allowed == set()
    assert session_seconds(inspector) == 900  # 40 steps are capped at the Steel session limit


def test_cited_verdicts_must_hold_and_every_claim_gets_exactly_one():
    claims = scout.plan(fixture_manual(), PRODUCT)
    checks, rejected = scout.gate([
        check("flow:1:entry", "consistent", ["s001_before"], "生成清单"),
        check("flow:1:steps", "inconsistent", ["s001_after"], "并不存在的文字"),  # invented quote
        check("feature:1", "consistent", ["s999"], "生成清单"),  # missing snapshot
        check("feature:1", "unverified"),  # duplicate
        check("feature:9", "inconsistent", ["s001_before"], "首页"),  # not on the checklist
        check("account:login", "consistent", [], ""),  # no evidence
    ], claims, snapshots())
    verdicts = {item.claim_id: item for item in checks}
    assert list(verdicts) == [claim["claim_id"] for claim in claims]
    assert verdicts["flow:1:entry"].verdict == "consistent"
    assert verdicts["flow:1:steps"].verdict == "unverified" and verdicts["flow:1:steps"].observed.startswith("证据不足")
    assert verdicts["feature:1"].verdict == "unverified"
    assert verdicts["feature:2"].observed == "浏览中没有走到"
    assert len(rejected) == 5  # account:login is off this checklist too: the fixture has no login account


def fake_browse(monkeypatch, calls, conclude_runs=True, passed=True, error=None):
    async def run_experience(config, capability, manual, persona, run_dir, prompt=None, conclude=None):
        calls.append({"persona": persona, "prompt": prompt, "run_dir": run_dir})
        if error:
            raise error
        run_dir.mkdir(parents=True)
        write_json(run_dir / "experience.json", memory().model_dump())
        if conclude_runs:
            assert await conclude(None, config, capability, persona, memory(), run_dir) is None
        return {"passed": passed, "steps": 1, "reason": "清单已看完"}
    monkeypatch.setattr("browsing.experience.run_experience", run_experience)


def fake_judge(monkeypatch, results):
    async def request_json(client, config, capability, schema, prompt, validate=None, **kwargs):
        assert schema is scout.Checks and "formatter unavailable" not in prompt
        for result in results:
            try:
                validate(result)
                return result
            except ValueError:
                pass
        raise ValueError("3 次尝试后仍不合法")
    monkeypatch.setattr(scout, "request_json", request_json)


def test_scout_records_verdicts_with_evidence(tmp_path, monkeypatch):
    calls = []
    fake_browse(monkeypatch, calls)
    good = scout.Checks(checks=[check("flow:1:entry", "consistent", ["s001_before"], "生成清单"),
                                check("flow:1:steps", "inconsistent", ["s001_after"], "清单已生成"),
                                check("feature:1", "unverified"), check("feature:2", "unverified")])
    fake_judge(monkeypatch, [good])
    result = asyncio.run(scout.run_scout(STEEL, CAPABILITY, fixture_manual(), PRODUCT, tmp_path))
    assert result["status"] == "completed" and result["counts"] == {"consistent": 1, "inconsistent": 1, "unverified": 2}
    saved = json.loads((tmp_path / "scout.json").read_text(encoding="utf-8"))
    row = next(item for item in saved["checks"] if item["verdict"] == "inconsistent")
    assert row["evidence_ids"] == ["s001_after"] and row["says"] and row["source"] == scout.SOURCE_MANUAL
    assert saved["evidence_dir"] == "scout" and calls[0]["run_dir"] == tmp_path / "scout"
    assert isinstance(calls[0]["persona"], scout.Inspector) and "formatter unavailable" not in calls[0]["prompt"]
    assert len(json.loads((tmp_path / "scout_plan.json").read_text(encoding="utf-8"))) == 4


def test_after_repairs_run_out_unsupported_verdicts_are_downgraded_and_kept_on_record(tmp_path, monkeypatch):
    fake_browse(monkeypatch, [])
    bad = scout.Checks(checks=[check("flow:1:entry", "consistent", ["s001_before"], "生成清单"),
                               check("flow:1:steps", "inconsistent", ["s001_after"], "编造的引文")])
    fake_judge(monkeypatch, [bad, bad, bad])
    result = asyncio.run(scout.run_scout(STEEL, CAPABILITY, fixture_manual(), PRODUCT, tmp_path))
    assert result["status"] == "completed" and result["counts"]["inconsistent"] == 0 and result["counts"]["consistent"] == 1
    assert json.loads((tmp_path / "scout_rejections.json").read_text(encoding="utf-8"))[0]["check"]["claim_id"] == "flow:1:steps"


@pytest.mark.parametrize("case", ["incomplete", "error", "no_steel"])
def test_scout_failures_are_recorded_not_raised(tmp_path, monkeypatch, case):
    calls = []
    fake_browse(monkeypatch, calls, conclude_runs=False, passed=False, error=RuntimeError("steel down") if case == "error" else None)
    result = asyncio.run(scout.run_scout(CONFIG if case == "no_steel" else STEEL, CAPABILITY, fixture_manual(), PRODUCT, tmp_path))
    assert result["status"] == ("skipped" if case == "no_steel" else "failed")
    assert result["counts"]["unverified"] == 4 and not result["counts"]["inconsistent"]
    assert bool(calls) is (case != "no_steel")


def analyze(tmp_path, monkeypatch, run_scout, scout_enabled=True):
    manual_path = tmp_path / "in.md"
    manual_path.write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    write_json(tmp_path / "cap" / "capability_profile.json", {**CAPABILITY, "ready": True})
    monkeypatch.setattr(phase1, "settings", lambda: dict(STEEL))
    monkeypatch.setattr(phase1, "require_capabilities", lambda run_dir, config: {**CAPABILITY, "ready": True})

    async def no_site(url, domains):
        return {"status": "failed", "url": url, "reason": "测试"}
    monkeypatch.setattr(phase1, "read_site", no_site)
    monkeypatch.setattr(phase1, "run_scout", run_scout)
    mock_model(monkeypatch, cohort(12, read_manual(SAMPLE)), bodies := [])
    run = tmp_path / "run"
    return asyncio.run(phase1.analyze(manual_path, run, tmp_path / "cap", scout_enabled)), run, bodies


MARKER = "侦察看到首页没有注册按钮"


async def scouted(config, capability, manual, product, run_dir):
    claims = scout.plan(manual, product)
    return scout.save(run_dir, claims, "completed", "", "t", [scout.Check(claim_id=claims[0]["claim_id"], verdict="inconsistent",
                      observed=MARKER, evidence_ids=["s001_after"], observed_quote="x")], {"steps": 3})


def test_analysis_runs_scout_and_the_review_shows_it_but_personas_never_hear_of_it(tmp_path, monkeypatch):
    result, run, bodies = analyze(tmp_path, monkeypatch, scouted)
    assert result["stage"] == "analyzed"
    asyncio.run(phase1.generate(run, 12, 50))
    review = (run / "review.md").read_text(encoding="utf-8")
    assert "Scout 侦察（已完成）" in review and MARKER in review and "Scout 尚未执行" not in review
    assert json.loads((run / "phase1_result.json").read_text(encoding="utf-8"))["scout_status"] == "completed"
    assert bodies and not any(MARKER in json.dumps(body, ensure_ascii=False) for body in bodies)


def test_no_scout_is_recorded_as_skipped(tmp_path, monkeypatch):
    async def must_not_run(*args):
        raise AssertionError("Scout ran although it was skipped")
    result, run, _ = analyze(tmp_path, monkeypatch, must_not_run, scout_enabled=False)
    saved = json.loads((run / "scout.json").read_text(encoding="utf-8"))
    assert result["stage"] == "analyzed" and saved["status"] == "skipped" and saved["reason"] == "按要求跳过侦察"


def test_a_failed_recommendation_cancels_scout(tmp_path, monkeypatch):
    cancelled = []

    async def slow(*args):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    async def broken(*args, **kwargs):
        await asyncio.sleep(0.05)
        raise ValueError("推荐不合法")
    monkeypatch.setattr(phase1, "recommend", broken)
    with pytest.raises(ValueError, match="推荐不合法"):
        analyze(tmp_path, monkeypatch, slow)
    assert cancelled
    assert json.loads((tmp_path / "run" / "scout.json").read_text(encoding="utf-8"))["status"] == "pending"


def add_scout(source, quote="清单已生成"):
    """A completed Scout in the approved snapshot: one inconsistency with a real page, one unverified claim."""
    folder = source / "approved_source" / "scout"
    shot = folder / "screenshots" / "s001_after.png"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(b"scout image")
    data = memory().model_dump()
    data["snapshots"] = [{**item, "screenshot_sha256": hashlib.sha256(b"scout image").hexdigest()} for item in data["snapshots"]]
    (folder / "screenshots" / "s001_before.png").write_bytes(b"scout image")
    write_json(folder / "experience.json", data)
    claims = scout.plan(fixture_manual(), PRODUCT)
    scout.save(source / "approved_source", claims, "completed", "", "t",
               [check("flow:1:entry", "inconsistent", ["s001_after"], quote)], {"steps": 1})


def test_the_report_lists_inconsistencies_with_their_screenshots(source, tmp_path):
    from report.agent import build_report, verify_report
    from report.evidence import CATEGORIES, EvidenceStore
    from report.render import render
    add_scout(source)
    store = EvidenceStore(source)
    report = build_report(store, {})
    section = report["scout"]
    assert section["executed"] and len(section["discrepancies"]) == 1 and len(section["unverified"]) == 3
    row = section["discrepancies"][0]
    assert row["refs"] == ["scout:flow:1:entry", "scout:snapshot:s001_after"]
    assert row["screenshots"] == ["approved_source/scout/screenshots/s001_after.png"]
    assert "不一致 1" in section["note"] and section["note"] in report["overview"]["coverage_notes"]
    assert verify_report(report, store) == []
    assert "scout" not in CATEGORIES  # the Report Agent cannot query or cite the inspector
    markdown = render(report, source, tmp_path / "out", evidence_index=store.records)
    assert "| 位置 | 来源 |" in markdown and "s001_after.png" in markdown and "**未核对**" in markdown


def test_a_scout_verdict_that_no_longer_matches_its_page_is_refused(source):
    from report.evidence import EvidenceStore
    add_scout(source, quote="页面上没有的文字")
    with pytest.raises(ValueError, match="Scout verdict"):
        EvidenceStore(source)


def test_runs_without_scout_keep_the_old_note(source):
    from report.agent import build_report
    from report.evidence import EvidenceStore
    report = build_report(EvidenceStore(source), {})
    assert report["scout"]["note"] == "Scout 未执行，无法列出说明书与实际产品的不一致。" and not report["scout"]["discrepancies"]


def test_the_simulation_snapshot_carries_scout_as_the_reviewer_saw_it(tmp_path, configured, draft):
    from orchestrator import phase4
    from test_audit import approved_source
    source = approved_source(tmp_path, draft)
    add_scout(tmp_path / "scouted")
    shutil.copytree(tmp_path / "scouted" / "approved_source", source, dirs_exist_ok=True)
    hash_before = phase1.draft_hash(source)
    run = tmp_path / "phase4-x"
    run.mkdir()
    snapshot, _ = phase4.snapshot_source(source, run)
    assert phase1.draft_hash(source) == hash_before  # Scout is outside the approval hash
    assert (snapshot / "scout.json").is_file() and (snapshot / "scout" / "screenshots" / "s001_after.png").is_file()
    assert "Scout 侦察（已完成）" in (snapshot / "review.md").read_text(encoding="utf-8")


def test_the_reviewer_sees_scout_with_its_screenshots_and_nothing_else_leaves(tmp_path):
    from fastapi.testclient import TestClient
    from api.app import create_app
    root = tmp_path / "runs"
    add_scout(tmp_path / "scouted")
    draft = root / "phase1-20261012T000000000000Z"
    shutil.copytree(tmp_path / "scouted" / "approved_source", draft)
    (draft / "manual.md").write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    write_json(draft / "phase1_result.json", {"stage": "analyzed", "passed": True, "recommendation": {"persona_count": 10,
               "duration_days": 1, "reason": "测试"}, "minimum_personas": 3})
    client = TestClient(create_app(root), base_url="http://localhost")
    body = client.get(f"/api/drafts/{draft.name}").json()
    assert body["status"] == "configuring" and body["scout"]["counts"]["inconsistent"] == 1
    shot = next(row for row in body["scout"]["checks"] if row["verdict"] == "inconsistent")["screenshots"][0]
    assert client.get(shot).content == b"scout image"
    for name in ["..%2Fexperience.json", "missing.png", "raw_trace.jsonl"]:
        assert client.get(f"/api/drafts/{draft.name}/scout/{name}").status_code == 404


def test_report_screenshots_of_scout_are_served_from_the_snapshot(runs_root):
    from fastapi.testclient import TestClient
    from api.app import create_app
    add_scout(runs_root / "phase4-x")
    client = TestClient(create_app(runs_root), base_url="http://localhost")
    assert client.get("/api/runs/phase4-x/files/approved_source/scout/screenshots/s001_after.png").content == b"scout image"
    for path in ["approved_source/scout/experience.json", "approved_source/scout.json", "approved_source/manual.md"]:
        assert client.get(f"/api/runs/phase4-x/files/{path}").status_code == 404
