import asyncio
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from conftest import save_json
from orchestrator.phase5 import execute


@pytest.fixture
def runs_root(source, tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    run = root / "phase4-x"
    shutil.copytree(source, run)
    save_json(run / "phase4_result.json", {"passed": True, "status": "completed", "limitations": ["样本很小"]})
    # Contexts keep the absolute path of the machine that wrote them; the API must resolve it by directory name.
    save_json(run / "run_context.json", {
        "source_run": "C:\\old-checkout\\runs\\phase1-x",
        "schedule": [{"persona_id": "p01", "local_time": "2026-10-03T09:40:00+08:00", "slice_index": 1},
                     {"persona_id": "p02", "local_time": "2026-10-03T10:55:00+08:00", "slice_index": 2}],
        "configuration": {"provider": "fixture", "model": "m", "api": "chat_completions", "api_key": "SECRET-KEY"}})
    save_json(root / "phase1-x" / "product_model.json", {"metadata": {"name": "演示产品"}})
    save_json(root / "phase1-x" / "draft.json", {"run_config": {"duration_days": 1, "time_slice_minutes": 60}})
    save_json(run / "p01" / "session.json", {"viewer_url": "https://viewer.example/SECRET-SESSION"})
    save_json(run / "cost.json", {"model_usd_min": 0.09, "total_usd_max": 0.23, "steel_usd_billed": 0.05})
    ledger = lambda model, usage, error=None: json.dumps({"request": 1, "api": "chat_completions", "model": model, "error_type": error, "usage": usage})
    full = {"input_tokens": 100, "cached_input_tokens": 40, "uncached_input_tokens": 60, "output_tokens": 10}
    (run / "p01" / "model_usage.jsonl").write_text("\n".join([ledger("model-a", full), ledger("model-a", None, "TimeoutError")]) + "\n", encoding="utf-8")
    (run / "community").mkdir(exist_ok=True)
    (run / "community" / "model_usage.jsonl").write_text("\n".join([ledger("model-a", full), ledger("model-b", full)]) + "\n", encoding="utf-8")
    asyncio.run(execute(run, root / "phase5-x", None, False))
    return root


@pytest.fixture
def client(runs_root):
    return TestClient(create_app(runs_root))


def test_runs_list_resolves_product_despite_stale_absolute_path(client):
    runs = client.get("/api/runs").json()
    assert [run["id"] for run in runs] == ["phase4-x"]
    run = runs[0]
    assert run["product"] == "演示产品" and run["personas"] == 2 and run["passed"] is True
    assert [report["id"] for report in run["reports"]] == ["phase5-x"]


def test_overview_has_no_credentials(client):
    response = client.get("/api/runs/phase4-x")
    body = response.json()
    assert body["configuration"]["provider"] == "fixture" and body["run_config"]["time_slice_minutes"] == 60
    assert body["limitations"] == ["样本很小"] and body["personas"] == 2
    assert "SECRET" not in response.text


def test_usage_is_tokens_per_model_and_never_a_price(client):
    response = client.get("/api/runs/phase4-x")
    usage = response.json()["usage"]
    assert usage["models"] == [
        {"model": "model-a", "requests": 3, "failed_requests": 1, "input_tokens": 200, "cached_input_tokens": 80, "output_tokens": 20},
        {"model": "model-b", "requests": 1, "failed_requests": 0, "input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 10}]
    assert usage["total"] == {"requests": 4, "failed_requests": 1, "input_tokens": 300, "cached_input_tokens": 120, "output_tokens": 30}
    assert not any(word in response.text.lower() for word in ("usd", "price", "cny", "steel_usd"))


def test_personas_summarise_experience_and_survey(client):
    rows = {row["persona_id"]: row for row in client.get("/api/runs/phase4-x/personas").json()}
    assert rows["p01"]["scheduled_at"] == "2026-10-03T09:40:00+08:00"
    assert rows["p01"]["experience"]["pains"] == 1 and rows["p01"]["experience"]["steps"] == 1
    assert rows["p01"]["survey"]["nps"] == 5 and rows["p01"]["survey"]["flags"]
    assert rows["p02"]["persona"]["participation"] == "lurker"


def test_experience_screenshots_are_served_and_session_is_not(client):
    body = client.get("/api/runs/phase4-x/personas/p01/experience").json()
    assert "session" not in body and body["replay"]["viewer_url"] is None
    assert body["steps"][0]["ref_id"] == "p01:step:1"
    assert body["assessment"]["findings"][0]["ref_id"] == "p01:f001"
    image = client.get(body["snapshots"][0]["screenshot_url"])
    assert image.status_code == 200 and image.content == b"fixture image"
    assert client.get("/api/runs/phase4-x/personas/p99/experience").status_code == 404


@pytest.mark.parametrize("path", ["p01/session.json", "p01/raw_trace.jsonl", "run.db", "../phase1-x/product_model.json",
                                  "p01/screenshots/../session.json", "p01%2Fscreenshots%2F..%2Fsession.json",
                                  "p01/screenshots/missing.png", "p01\\screenshots\\before.png"])
def test_only_screenshots_leave_the_server(client, path):
    response = client.get(f"/api/runs/phase4-x/files/{path}")
    assert response.status_code == 404 and "SECRET" not in response.text


def test_community_separates_public_posts_from_private_records(client):
    body = client.get("/api/runs/phase4-x/community").json()
    assert [(post["ref_id"], post["persona_id"], post["content"]) for post in body["posts"]] == [("post:1", "p01", "无反馈")]
    assert "num_likes" not in json.dumps(body)
    assert body["withheld"][0]["withheld"][0] == {"finding_id": "p01:f001", "reason": "怕显得不会用"}
    assert {item["persona_id"] for item in body["surveys"]} == {"p01", "p02"}


def test_report_and_evidence_resolve(client):
    body = client.get("/api/runs/phase4-x/report").json()
    assert body["id"] == "phase5-x" and body["report"]["overview"]["personas"] == 2
    evidence = client.get("/api/runs/phase4-x/evidence/p01:f001").json()
    assert evidence["category"] == "experience" and len(evidence["files"]) == 2
    assert client.get(evidence["files"][0]).status_code == 200
    assert client.get("/api/runs/phase4-x/evidence/p01:f999").status_code == 404
    assert client.get("/api/runs/phase4-x/report?report_id=phase4-x").status_code == 404


def test_unknown_or_non_simulation_runs_are_not_found(client):
    for run_id in ["nope", "phase1-x", "phase5-x", "..", "%2e%2e"]:
        assert client.get(f"/api/runs/{run_id}").status_code == 404, run_id


def test_run_without_report_is_not_found(runs_root):
    shutil.rmtree(runs_root / "phase5-x")
    assert TestClient(create_app(runs_root)).get("/api/runs/phase4-x/report").status_code == 404


def test_corrupt_evidence_is_reported_as_unprocessable(runs_root):
    (runs_root / "phase4-x" / "p01" / "experience.json").write_text("{}", encoding="utf-8")
    client = TestClient(create_app(runs_root))
    assert client.get("/api/runs/phase4-x/personas").status_code == 422
    assert client.get("/api/runs").status_code == 200
