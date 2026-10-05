import json
import os
import shutil
import time

import pytest
from fastapi.testclient import TestClient

from api.app import create_app


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


def test_runs_report_their_browsing_span(client):
    assert client.get("/api/runs").json()[0]["started_at"] == "2026-10-03T07:16:26+00:00"
    overview = client.get("/api/runs/phase4-x").json()
    assert (overview["started_at"], overview["finished_at"]) == ("2026-10-03T07:16:26+00:00", "2026-10-03T07:20:18+00:00")


def test_default_report_prefers_a_passed_model_report_over_a_newer_check_run(runs_root):
    written = runs_root / "phase5-model"
    shutil.copytree(runs_root / "phase5-x", written)
    result = json.loads((written / "phase5_result.json").read_text(encoding="utf-8"))
    (written / "phase5_result.json").write_text(json.dumps({**result, "model_used": True, "passed": True}), encoding="utf-8")
    newer = runs_root / "phase5-newer-check"
    shutil.copytree(runs_root / "phase5-x", newer)  # model_used is false here and it is the newest report
    later = time.time_ns() + 10**10
    os.utime(newer / "report.json", ns=(later, later))
    client = TestClient(create_app(runs_root))
    assert [item["id"] for item in client.get("/api/runs/phase4-x").json()["reports"]][0] == "phase5-newer-check"
    assert client.get("/api/runs/phase4-x/report").json()["id"] == "phase5-model"
    assert client.get("/api/runs/phase4-x/report?report_id=phase5-newer-check").json()["id"] == "phase5-newer-check"


def test_first_open_builds_the_evidence_store_once_however_many_requests_race(runs_root, monkeypatch):
    """The UI opens a run with a dozen parallel requests; each used to miss the cache and rebuild the store."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from api import service
    built = []

    class Counting(service.EvidenceStore):
        def __init__(self, root):
            built.append(threading.get_ident())
            time.sleep(0.2)  # long enough for every other request to arrive while this one builds
            super().__init__(root)

    monkeypatch.setattr(service, "EvidenceStore", Counting)
    reader = service.Reader(runs_root)
    with ThreadPoolExecutor(12) as pool:
        stores = list(pool.map(lambda _: reader.store("phase4-x"), range(12)))
    assert len(built) == 1 and all(store is stores[0] for store in stores)


def test_a_failed_build_is_shared_by_concurrent_requests_but_not_cached(runs_root, monkeypatch):
    """A broken run used to be rebuilt once per waiting request, one after another."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from api import service
    (runs_root / "phase4-x" / "p01" / "experience.json").write_text("{}", encoding="utf-8")
    built = []

    class Counting(service.EvidenceStore):
        def __init__(self, root):
            built.append(threading.get_ident())
            time.sleep(0.2)
            super().__init__(root)

    monkeypatch.setattr(service, "EvidenceStore", Counting)
    reader = service.Reader(runs_root)

    def attempt(_):
        with pytest.raises(service.RunInvalid, match="phase4-x"):
            reader.store("phase4-x")

    with ThreadPoolExecutor(12) as pool:
        list(pool.map(attempt, range(12)))
    assert len(built) == 1
    attempt(None)  # not cached: once the run is repaired, the next request rebuilds it
    assert len(built) == 2


def test_an_unexpected_build_error_still_releases_waiting_requests(runs_root, monkeypatch):
    import threading
    from api import service

    class Broken:
        def __init__(self, root):
            time.sleep(0.2)
            raise TypeError("bug in the store")

    monkeypatch.setattr(service, "EvidenceStore", Broken)
    reader = service.Reader(runs_root)

    errors = []

    def attempt():
        try:
            reader.store("phase4-x")
        except TypeError as error:
            errors.append(error)

    threads = [threading.Thread(target=attempt, daemon=True) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not any(thread.is_alive() for thread in threads), "requests waiting on a failed build were never released"
    assert len(errors) == 4


def test_repairing_any_evidence_file_invalidates_the_cache(runs_root):
    """The cache used to key on run.db and run_context.json only, so a repaired experience.json stayed rejected."""
    from api import service
    experience = runs_root / "phase4-x" / "p01" / "experience.json"
    original = experience.read_text(encoding="utf-8")
    reader = service.Reader(runs_root)
    store = reader.store("phase4-x")
    assert reader.store("phase4-x") is store  # unchanged files: served from the cache, even after read-only opens
    experience.write_text("{}", encoding="utf-8")
    with pytest.raises(service.RunInvalid):
        reader.store("phase4-x")
    experience.write_text(original, encoding="utf-8")
    assert reader.store("phase4-x") is not store


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
