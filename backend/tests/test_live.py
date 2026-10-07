"""Watching a simulation while it runs: the files exist before phase 4 ends, the run-reading endpoints cannot serve them."""

import json

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.jobs import Jobs
from core.runtime import write_json

LOG = """INFO     [Agent] 🎯 Task: 你正在以这位合成用户的身份真实使用产品 PERSONA-DOSSIER-SECRET
INFO     [Agent] \x1b[34m📍 Step 1:\x1b[0m
INFO     [Agent]   ❔ Eval: 首页加载成功。
INFO     [Agent]   🧠 Memory: 读到姓名与方向，apiKey=sk-live-123。
INFO     [Agent]   🎯 Next goal: 点击“全部项目”。
INFO     [Agent]   ▶️   click: index: 26
INFO     [tools] 🖱️ Clicked a "全部项目 →"
INFO     [Agent]

INFO     [Agent] 📍 Step 2:
INFO     [Agent]   👍 Eval: 进入列表页。Verdict: Success
INFO     [Agent]   🎯 Next goal: 向下滚动。
INFO     [Agent]   ▶️   scroll: down: True, pages: 2.0, index: None
"""


def build(root, finished=False):
    run = root / "phase4-live"
    states = {"p01": {"state": "completed", "started_at": "2026-10-05T02:00:00+00:00", "local_time": "2026-10-05T09:20:00+08:00"},
              "p02": {"state": "running", "started_at": "2026-10-05T02:10:00+00:00", "local_time": "2026-10-05T10:10:00+08:00"}}
    write_json(run / "timeline.json", {"slices": [], "jobs": states})
    for pid, name in (("p01", "甲"), ("p02", "乙")):
        write_json(run / pid / "persona.json", {"realname": name, "age": 30, "profession": "设计师", "city": "上海", "life_context": "SECRET-DOSSIER"})
        write_json(run / pid / "session.json", {"id": f"id-{pid}", "viewer_url": f"https://app.steel.dev/sessions/id-{pid}", "debug_url": "wss://secret"})
        (run / pid / "screenshots").mkdir(parents=True)
    (run / "p02.log").write_text(LOG, encoding="utf-8")
    (run / "p01.log").write_text("INFO     [Agent] 📍 Step 1:\nINFO     [Agent]   🎯 Next goal: 看首页\n", encoding="utf-8")
    (run / "p02" / "screenshots" / "s001_before.png").write_bytes(b"PNG1")
    (run / "p02" / "screenshots" / "s001_after.png").write_bytes(b"PNG2")
    (root / "_jobs").mkdir()
    write_json(root / "_jobs" / "simulate-x.json", {"id": "simulate-x", "kind": "simulate", "state": "running", "step": 0, "created_at": "2026-10-05T02:00:00+00:00",
               "finished_at": None, "returncode": None, "steps": [{"name": "s", "state": "running"}], "draft": "phase1-x", "simulation": "phase4-live", "report": "phase5-live"})
    write_json(root / "_jobs" / "prepare-x.json", {"id": "prepare-x", "kind": "prepare", "state": "running", "step": 0, "created_at": "2026-10-05T02:00:00+00:00",
               "finished_at": None, "returncode": None, "steps": [], "draft": "phase1-x"})
    return run


@pytest.fixture
def client(tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    build(root)
    app = create_app(root, jobs=Jobs(root))
    app.state.root = root
    return TestClient(app, base_url="http://localhost")


def test_the_running_persona_is_selected_with_its_steps_and_live_link(client):
    view = client.get("/api/jobs/simulate-x/live").json()
    assert [p["id"] for p in view["personas"]] == ["p01", "p02"]
    selected = view["selected"]
    assert selected["id"] == "p02" and selected["name"] == "乙" and selected["viewer_url"] == "https://app.steel.dev/sessions/id-p02"
    first, second = selected["steps"]
    assert first["goal"] == "点击“全部项目”。" and first["actions"] == ["click index: 26"] and first["results"] == ['🖱️ Clicked a "全部项目 →"']
    assert first["screenshot"] == "s001_after.png" and second["screenshot"] is None  # step 2 has no screenshot yet
    assert second["eval"].endswith("Success") and second["actions"] == ["scroll down: True, pages: 2.0, index: None"]


def test_finished_personas_can_be_selected_but_have_no_live_link(client):
    selected = client.get("/api/jobs/simulate-x/live", params={"persona": "p01"}).json()["selected"]
    assert selected["id"] == "p01" and selected["viewer_url"] is None and selected["steps"][0]["goal"] == "看首页"


def test_nothing_private_leaves_the_job_endpoints(client):
    body = client.get("/api/jobs/simulate-x/live").text
    for secret in ("PERSONA-DOSSIER-SECRET", "SECRET-DOSSIER", "sk-live-123", "wss://secret", "debug_url"):
        assert secret not in body
    assert "apiKey=REDACTED" in body


def test_screenshots_are_served_by_job_with_strict_names(client):
    assert client.get("/api/jobs/simulate-x/shots/p02/s001_after.png").content == b"PNG2"
    for path in ("p02/session.json", "p02/s001_after.png.bak", "p99/s001_after.png", "..%2Fp02/s001_after.png", "p02/..%2Fsession.json", "p02/s002_after.png"):
        assert client.get(f"/api/jobs/simulate-x/shots/{path}").status_code == 404, path


def test_only_screenshot_files_are_served_even_from_the_screenshots_folder(client, tmp_path):
    folder = tmp_path / "runs" / "phase4-live" / "p02" / "screenshots"
    (folder / "notes.json").write_text("{}", encoding="utf-8")
    assert client.get("/api/jobs/simulate-x/shots/p02/notes.json").status_code == 404


def test_unknown_jobs_unknown_personas_and_prepare_jobs_are_refused(client):
    assert client.get("/api/jobs/nope/live").status_code == 404
    assert client.get("/api/jobs/prepare-x/live").status_code == 404  # a draft job has no run to watch
    assert client.get("/api/jobs/simulate-x/live", params={"persona": "p77"}).status_code == 404
    assert client.get("/api/jobs/simulate-x/live", params={"persona": "../p01"}).status_code == 404


def test_a_job_whose_run_directory_does_not_exist_yet_is_empty(client, tmp_path):
    root = tmp_path / "runs"
    write_json(root / "_jobs" / "simulate-y.json", {"id": "simulate-y", "kind": "simulate", "state": "running", "step": 0, "created_at": "2026-10-05T02:00:00+00:00",
               "finished_at": None, "returncode": None, "steps": [], "draft": "phase1-x", "simulation": "phase4-none", "report": "phase5-none"})
    assert client.get("/api/jobs/simulate-y/live").json() == {"personas": [], "selected": None}
