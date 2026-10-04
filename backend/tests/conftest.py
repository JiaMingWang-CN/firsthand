import hashlib
import json
import sqlite3

import pytest


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
