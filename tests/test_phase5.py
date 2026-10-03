import asyncio
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest

from report.evidence import EvidenceStore
from report.agent import Claim, Citation, accept_claims, build_report


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    with sqlite3.connect(root / "run.db") as db:
        db.executescript("""
            CREATE TABLE personas(persona_id, persona_json, browse_slice);
            CREATE TABLE experiences(persona_id, slice_index, directory, memory_json);
            CREATE TABLE disclosures(disclosure_id, persona_id, slice_index, shared_json, withheld_json, public_body);
            CREATE TABLE reads(read_id, persona_id, slice_index, post_id, before_experience, post_json);
            CREATE TABLE surveys(persona_id, answer_json, flags_json);
        """)
        for pid, role in [("p01", "poster"), ("p02", "lurker")]:
            person = {"persona_id": pid, "participation": role, "schedule": {"browse_slot": "23:00"}}
            db.execute("INSERT INTO personas VALUES(?,?,0)", (pid, json.dumps(person)))
            directory = root / pid
            shots = []
            for eid, seconds in [("before", 1), ("after", 2)]:
                path = directory / "screenshots" / f"{eid}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture image")
                shots.append({"evidence_id": eid, "url": "https://example.com", "title": "", "text": "生成清单",
                    "screenshot": f"screenshots/{eid}.png", "screenshot_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "scroll_x": 0, "scroll_y": 0, "video_seconds": seconds})
            memory = {"persona_id": pid, "state_at_browse": "困", "assignment": {"type": "task"}, "expectations": [],
                "outcome": "abandoned", "reason": "按钮无反馈", "outcome_source": "runtime_limit", "session": {},
                "snapshots": shots, "steps": [{"step": 1, "before": "before", "after": "after", "seconds": 1,
                    "actions": [], "results": [], "agent_observation": "无反馈", "stalled": True, "page_structure_degraded": True}],
                "observed_technical_events": [], "infrastructure_errors": [], "assessment": {
                    "summary": "放弃", "emotions": [{"step": 1, "satisfaction": 1, "confusion": 5, "reason": "无反馈"}],
                    "findings": [{"kind": "pain", "title": "按钮无反馈", "description": "生成失败", "evidence_ids": ["before", "after"],
                        "technical_event_ids": [], "observed_quote": "生成清单"}]}}
            save_json(directory / "experience.json", memory)
            (directory / "raw_trace.jsonl").write_text(json.dumps({"event_id": "t1", "event": "snapshot", "data": {}}) + "\n", encoding="utf-8")
            db.execute("INSERT INTO experiences VALUES(?,0,?,?)", (pid, str(directory), json.dumps(memory)))
            answer = {"has_experience": True, "nps": 5, "continue_using": "no", "would_pay": "no", "biggest_issue": f"{pid}:f001",
                "favorite": None, "unsaid": [], "opinion_changed": False, "influencing_post_ids": [], "explanation": "无反馈"}
            db.execute("INSERT INTO surveys VALUES(?,?,?)", (pid, json.dumps(answer), json.dumps(["unsaid_item_was_publicly_expressed_requires_review"])))
        db.execute("INSERT INTO disclosures VALUES(1,'p01',1,'[]',?, '')", (json.dumps([{"finding_id": "p01:f001", "reason": "怕显得不会用"}]),))
    (root / "community").mkdir()
    with sqlite3.connect(root / "community/oasis.db") as db:
        db.executescript("CREATE TABLE post(post_id,user_id,content,num_likes); CREATE TABLE comment(comment_id,post_id,user_id,content);")
        db.execute("INSERT INTO post VALUES(1,0,'无反馈',10000)")
    save_json(root / "social_audit.json", {"passed": True, "planner_fallbacks_to_do_nothing": 2})
    return root


def claim(refs, title="按钮无反馈", severity=3):
    return Claim(title=title, detail="按钮无反馈", severity=severity,
                 citations=[Citation(ref_id=ref, quote="按钮无反馈") for ref in refs])


def test_unbacked_and_forged_claims_are_rejected(source):
    store = EvidenceStore(source)
    accepted, rejected = accept_claims([claim([]), claim(["p01:f999"]), claim(["p01:f001"])], store, "issues")
    assert len(accepted) == 1 and len(rejected) == 2
    assert all(item["reason"] for item in rejected)
    assert "page_structure_degraded" in accepted[0]["review_flags"][0]


def test_ranking_counts_unique_people_and_ignores_likes(source):
    store = EvidenceStore(source)
    claims = [claim(["p01:f001"], "热门", 3), claim(["p01:f001", "p02:f001"], "影响两人", 3)]
    report = build_report(store, {"issues": claims})
    assert report["sections"]["issues"][0]["title"] == "影响两人"
    assert report["sections"]["issues"][0]["affected_personas"] == ["p01", "p02"]


def test_silence_uses_withheld_and_lurker_and_preserves_flags(source):
    store = EvidenceStore(source)
    report = build_report(store, {})
    signals = report["silence_signals"]
    assert any(item["reason"] == "怕显得不会用" and item["persona_id"] == "p01" for item in signals)
    assert any(item["source"] == "lurker" and item["persona_id"] == "p02" for item in signals)
    assert report["survey_flags"]["p01"] == ["unsaid_item_was_publicly_expressed_requires_review"]
    assert report["overview"]["nps"] == -100


def test_tools_are_read_only_and_return_trace_and_video(source):
    before = (source / "run.db").read_bytes()
    store = EvidenceStore(source)
    assert store.query("media", "p01")
    assert store.query("withheld", "p01")
    assert store.query("surveys", "p02")
    with pytest.raises(ValueError):
        store.query("delete", "p01")
    assert (source / "run.db").read_bytes() == before


def test_forged_quote_and_wrong_issue_kind_are_rejected(source):
    store = EvidenceStore(source)
    forged = claim(["p01:f001"])
    forged.citations[0].quote = "不存在的原文"
    assert not accept_claims([forged], store, "issues")[0]
    assert not accept_claims([claim(["p01:f001"])], store, "highlights")[0]


def add_actions(source, success):
    with sqlite3.connect(source / "run.db") as db:
        db.execute("CREATE TABLE actions(persona_id, slice_index, action, public_body, result_json)")
        db.execute("UPDATE disclosures SET shared_json='[\"p01:f001\"]', withheld_json='[]', public_body='公开正文'")
        db.execute("INSERT INTO actions VALUES('p01',1,'create_post','公开正文',?)", (json.dumps({"success": success}),))


def test_a_rejected_publication_does_not_count_as_public(source):
    add_actions(source, False)
    assert any(item["persona_id"] == "p01" and item["source"] == "unshared" for item in build_report(EvidenceStore(source), {})["silence_signals"])
    add_actions_ok = sqlite3.connect(source / "run.db")
    add_actions_ok.execute("UPDATE actions SET result_json='{\"success\": true}'")
    add_actions_ok.commit()
    add_actions_ok.close()
    assert not any(item["persona_id"] == "p01" for item in build_report(EvidenceStore(source), {})["silence_signals"])


def test_report_has_no_likes_and_every_conclusion_resolves(source):
    from report.agent import verify_report
    store = EvidenceStore(source)
    report = build_report(store, {"issues": [claim(["p01:f001", "p02:f001"])]})
    assert "num_likes" not in json.dumps(report, ensure_ascii=False) and "10000" not in json.dumps(report)
    assert verify_report(report, store) == []
    report["sections"]["issues"][0]["evidence"] = []
    assert verify_report(report, store)


def test_investigation_repairs_rejected_claims_then_stops(source, monkeypatch):
    from report import agent
    store = EvidenceStore(source)
    forged = claim(["p01:f001"])
    forged.citations[0].quote = "编造的原文"
    steps = iter([
        agent.Step(action="query", category="experience", persona_id="p01", offset=0, limit=5, issues=[], highlights=[]),
        agent.Step(action="final", category=None, persona_id=None, offset=None, limit=None, issues=[forged], highlights=[]),
        agent.Step(action="final", category=None, persona_id=None, offset=None, limit=None, issues=[claim(["p01:f001"])], highlights=[]),
    ])
    prompts = []

    async def fake(client, config, capability, schema, prompt, validate=None, label=None, max_tokens=4096):
        prompts.append(prompt)
        step = next(steps)
        validate(step)
        return step
    monkeypatch.setattr(agent, "request_json", fake)
    step, trace = asyncio.run(agent.investigate(None, {}, {}, store))
    assert [item["action"] for item in trace] == ["query", "final", "final"]
    assert "被证据门禁退回" in prompts[2] and "p01:f001" in prompts[1]
    assert not agent.accept_claims(step.issues, store, "issues")[1]


def test_command_line_report_leaves_source_untouched(source, tmp_path):
    from orchestrator.phase5 import execute
    (source / "phase4_result.json").write_text("{}", encoding="utf-8")
    (source / "run_context.json").write_text(json.dumps({"source_run": str(tmp_path), "configuration": {"provider": "x"}}), encoding="utf-8")
    before = {path: path.read_bytes() for path in source.rglob("*") if path.is_file()}
    result = asyncio.run(execute(source, tmp_path / "out", None, False))
    assert result["passed"] and result["source_files_unchanged"] and not result["model_used"]
    assert (tmp_path / "out" / "report.md").read_text(encoding="utf-8").count("p01:f001") >= 1
    assert before == {path: path.read_bytes() for path in source.rglob("*") if path.is_file()}


def test_prose_cannot_name_personas_without_citing_their_evidence(source):
    store = EvidenceStore(source)
    overclaim = claim(["p01:f001"])
    overclaim.detail = "p01、p02 都遇到按钮无反馈"
    accepted, rejected = accept_claims([overclaim], store, "issues")
    assert not accepted and "p02" in rejected[0]["reason"]
    overclaim.citations.append(Citation(ref_id="p02:f001", quote="按钮无反馈"))
    assert accept_claims([overclaim], store, "issues")[0]


def test_unrelated_records_do_not_count_as_affected_people(source):
    store = EvidenceStore(source)
    padded = claim(["p01:f001"])
    padded.citations.append(Citation(ref_id="p02:outcome", quote="abandoned"))
    accepted, _ = accept_claims([padded], store, "issues")
    assert accepted[0]["affected_personas"] == ["p01"]


def test_naming_a_persona_requires_their_matching_finding(source):
    store = EvidenceStore(source)
    overclaim = claim(["p01:f001"])
    overclaim.detail = "p01、p02 都遇到按钮无反馈"
    overclaim.citations.append(Citation(ref_id="p02:outcome", quote="按钮无反馈"))
    accepted, rejected = accept_claims([overclaim], store, "issues")
    assert not accepted and "p02" in rejected[0]["reason"]


def test_time_slot_without_verified_experience_still_verifies(source):
    from report.agent import verify_report
    with sqlite3.connect(source / "run.db") as db:
        db.execute("DELETE FROM experiences WHERE persona_id='p02'")
        db.execute("DELETE FROM surveys WHERE persona_id='p02'")
        db.execute("UPDATE personas SET persona_json=? WHERE persona_id='p02'",
                   (json.dumps({"persona_id": "p02", "participation": "lurker", "schedule": {"browse_slot": "08:00"}}),))
    store = EvidenceStore(source)
    report = build_report(store, {})
    assert any(row["personas"] == ["p02"] for row in report["time_slots"])
    assert verify_report(report, store) == []


def test_links_fall_back_to_absolute_uri_across_drives(tmp_path, monkeypatch):
    from report import render
    def other_drive(*args):
        raise ValueError("path is on mount 'C:', start on mount 'D:'")
    monkeypatch.setattr(render.os.path, "relpath", other_drive)
    assert render.link(tmp_path, tmp_path / "out", "p01/experience.json").endswith((tmp_path / "p01/experience.json").as_uri() + ")")


def test_failed_phase4_run_is_called_out(source, tmp_path):
    from orchestrator.phase5 import execute
    (source / "phase4_result.json").write_text(json.dumps({"passed": False, "status": "interrupted_or_failed"}), encoding="utf-8")
    (source / "run_context.json").write_text(json.dumps({"source_run": str(tmp_path), "configuration": {"provider": "x"}}), encoding="utf-8")
    result = asyncio.run(execute(source, tmp_path / "out", None, False))
    assert result["source_phase4_passed"] is False
    report = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
    assert "阶段 4 验收未通过" in report["overview"]["coverage_notes"][0]
