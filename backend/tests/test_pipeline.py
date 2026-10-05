"""New runs from the Web UI: manual check, draft generation, review, simulation jobs.

Child processes are replaced by a fake that writes what each CLI step would write, so no model, Steel session or
OASIS process is involved; the review rules themselves are the real orchestrator.phase1 ones.
"""

import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import drafts
from api.app import create_app
from api.jobs import Jobs
from core.runtime import write_json
from orchestrator import phase1
from test_phase1 import CAPABILITY, CONFIG, SAMPLE, draft  # noqa: F401  (draft is a fixture)

SETTINGS = {**CONFIG, "steel_api_key": "STEEL-SECRET", "api_key": "MODEL-SECRET"}


class FakeProcess:
    def __init__(self, code):
        self.code = code

    def wait(self):
        return self.code


class FakePipeline:
    """Stands in for subprocess.Popen: records each step and writes the files that CLI step would write."""

    def __init__(self, draft, codes=None, gate=None):
        self.draft, self.codes, self.gate, self.calls = draft, codes or {}, gate, []

    def __call__(self, argv, cwd, env, stdout, stderr):
        module, args = argv[2], [str(arg) for arg in argv[3:]]
        self.calls.append((module, args))
        stdout.write(f"{module} 使用密钥 MODEL-SECRET 与 STEEL-SECRET\n")
        if self.gate:
            self.gate.wait(10)
        code = self.codes.get(module, 0)
        if module == "orchestrator.phase1" and code == 0:
            run = Path(args[args.index("--run-dir") + 1])
            run.mkdir(parents=True)
            (run / "manual.md").write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
            write_json(run / "capability_profile.json", CAPABILITY)
            write_json(run / "draft.json", self.draft.model_dump(mode="json"))
            write_json(run / "product_model.json", {"metadata": {"name": "王佳明个人作品网站"}})
            write_json(run / "phase1_result.json", {"passed": True})
        if module == "orchestrator.phase4":
            run = Path(args[args.index("--run-dir") + 1])
            run.mkdir(parents=True)
            write_json(run / "timeline.json", {"slices": [{"state": "completed"}] * 3, "jobs": {"p01": {"state": "completed"}, "p02": {"state": "failed"}}})
            write_json(run / "phase4_result.json", {"passed": code == 0})
        if module == "orchestrator.phase5":
            run = Path(args[args.index("--run-dir") + 1])
            run.mkdir(parents=True)
            write_json(run / "phase5_result.json", {"passed": True})
        return FakeProcess(code)


@pytest.fixture
def configured(monkeypatch):
    for module in (drafts, phase1):
        monkeypatch.setattr(module, "settings", lambda: SETTINGS)
    monkeypatch.setattr("core.runtime.settings", lambda: SETTINGS)


def wait_for(client, job_id, state="succeeded"):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] != "running":
            assert job["state"] == state, job
            return job
        time.sleep(0.02)
    pytest.fail("job did not finish")


def app(tmp_path, pipeline):
    root = tmp_path / "runs"
    root.mkdir(exist_ok=True)
    return root, TestClient(create_app(root, jobs=Jobs(root, python="python", popen=pipeline)))


def test_manual_check_matches_phase1_parsing(tmp_path):
    _, client = app(tmp_path, None)
    body = client.post("/api/manuals/check", json={"text": SAMPLE.read_text(encoding="utf-8")}).json()
    assert body["name"] == "JiaMingWang-CN 个人作品网站" and [flow["name"] for flow in body["flows"]] == ["了解开发者背景与方向", "浏览项目并评估相关性"]
    template = (SAMPLE.parent.parent / "product_manual_template.md").read_text(encoding="utf-8")
    response = client.post("/api/manuals/check", json={"text": template})
    assert response.status_code == 422 and response.json()["detail"]
    assert client.post("/api/manuals/check", json={"text": ""}).status_code == 422


@pytest.mark.parametrize("headers, status", [({"origin": "https://evil.example"}, 403), ({"content-type": "text/plain"}, 415),
                                             ({"origin": "http://localhost:5180"}, 200)])
def test_writes_only_from_this_machine_and_only_json(tmp_path, headers, status):
    """POSTs start paid work; another site must not trigger them through the user's browser (no form posts either)."""
    _, client = app(tmp_path, None)
    body = json.dumps({"text": SAMPLE.read_text(encoding="utf-8")})
    response = client.post("/api/manuals/check", content=body, headers={"content-type": "application/json", **headers})
    assert response.status_code == status


def test_capabilities_only_lists_profiles_for_the_current_model(tmp_path, configured):
    root, client = app(tmp_path, None)
    write_json(root / "phase0-match" / "capability_profile.json", CAPABILITY)
    write_json(root / "phase0-other" / "capability_profile.json", {**CAPABILITY, "model": "another"})
    write_json(root / "_jobs" / "capability_profile.json", CAPABILITY)
    assert [item["id"] for item in client.get("/api/capabilities").json()] == ["phase0-match"]


def test_from_manual_to_approved_draft_to_report(tmp_path, configured, draft):
    pipeline = FakePipeline(draft)
    root, client = app(tmp_path, pipeline)
    write_json(root / "phase0-match" / "capability_profile.json", CAPABILITY)
    started = client.post("/api/drafts", json={"manual": SAMPLE.read_text(encoding="utf-8"), "capability_run": "phase0-match"}).json()
    draft_id = started["draft"]
    wait_for(client, started["id"])
    module, args = pipeline.calls[0]
    assert module == "orchestrator.phase1" and args[0] == "prepare" and args[-2:] == ["--capability-run", str(root / "phase0-match")]

    listed = client.get("/api/drafts").json()
    assert [(item["id"], item["status"]) for item in listed] == [(draft_id, "pending")]
    review = client.get(f"/api/drafts/{draft_id}").json()
    assert review["valid"] and len(review["personas"]) == 10 and review["issues"] == [] and review["distribution"]
    assert client.post(f"/api/drafts/{draft_id}/simulations", json={"confirm": True}).status_code == 422  # not approved yet

    stale = client.post(f"/api/drafts/{draft_id}/decision", json={"decision": "approve", "draft_sha256": "0" * 64})
    assert stale.status_code == 422 and "不同" in stale.json()["detail"]
    approved = client.post(f"/api/drafts/{draft_id}/decision", json={"decision": "approve", "draft_sha256": review["draft_sha256"]})
    assert approved.json()["status"] == "approved"
    assert phase1.require_approved(root / draft_id)  # the CLI accepts the UI's approval as its own

    job = client.post(f"/api/drafts/{draft_id}/simulations", json={"confirm": True}).json()
    done = wait_for(client, job["id"])
    assert [module for module, _ in pipeline.calls[1:]] == ["orchestrator.phase4", "orchestrator.phase5"]
    phase5 = pipeline.calls[2][1]
    assert phase5[0] == str(root / job["simulation"]) and phase5[-2:] == ["--capability-run", str(root / draft_id)]
    assert done["progress"] == {"slices_done": 3, "slices": 24, "personas": 10, "personas_done": 1, "personas_failed": 1,
                                "phase4_passed": True, "report_passed": True}
    assert [step["state"] for step in done["steps"]] == ["succeeded", "succeeded"]
    log = client.get(f"/api/jobs/{job['id']}").json()["log"]
    assert log and not any("SECRET" in line for line in log)


def test_a_failed_simulation_does_not_write_a_report(tmp_path, configured, draft):
    pipeline = FakePipeline(draft, codes={"orchestrator.phase4": 1})
    root, client = app(tmp_path, pipeline)
    started = client.post("/api/drafts", json={"manual": SAMPLE.read_text(encoding="utf-8")}).json()
    wait_for(client, started["id"])
    review = client.get(f"/api/drafts/{started['draft']}").json()
    client.post(f"/api/drafts/{started['draft']}/decision", json={"decision": "approve", "draft_sha256": review["draft_sha256"]})
    job = client.post(f"/api/drafts/{started['draft']}/simulations", json={"confirm": True}).json()
    done = wait_for(client, job["id"], "failed")
    assert [step["state"] for step in done["steps"]] == ["failed", "pending"]
    assert [module for module, _ in pipeline.calls] == ["orchestrator.phase1", "orchestrator.phase4"]


def test_only_one_simulation_at_a_time(tmp_path, configured, draft):
    gate = threading.Event()
    root, client = app(tmp_path, FakePipeline(draft))
    started = client.post("/api/drafts", json={"manual": SAMPLE.read_text(encoding="utf-8")}).json()
    wait_for(client, started["id"])
    review = client.get(f"/api/drafts/{started['draft']}").json()
    client.post(f"/api/drafts/{started['draft']}/decision", json={"decision": "approve", "draft_sha256": review["draft_sha256"]})
    jobs = Jobs(root, python="python", popen=FakePipeline(draft, gate=gate))
    client = TestClient(create_app(root, jobs=jobs))
    first = client.post(f"/api/drafts/{started['draft']}/simulations", json={"confirm": True})
    second = client.post(f"/api/drafts/{started['draft']}/simulations", json={"confirm": True})
    assert first.status_code == 200 and second.status_code == 409
    gate.set()
    wait_for(client, first.json()["id"])


def test_rejecting_and_override_rules_follow_the_cli(tmp_path, configured, draft):
    draft.personas[0].participation = "lurker"  # changes the planned distribution
    root, client = app(tmp_path, FakePipeline(draft))
    started = client.post("/api/drafts", json={"manual": SAMPLE.read_text(encoding="utf-8")}).json()
    wait_for(client, started["id"])
    draft_id = started["draft"]
    review = client.get(f"/api/drafts/{draft_id}").json()
    assert review["issues"]
    body = {"decision": "approve", "draft_sha256": review["draft_sha256"]}
    needs = client.post(f"/api/drafts/{draft_id}/decision", json=body)
    assert needs.status_code == 422 and "分布已改变" in needs.json()["detail"]
    assert client.post(f"/api/drafts/{draft_id}/decision", json={**body, "accept_overrides": True}).json()["status"] == "approved"
    assert client.post(f"/api/drafts/{draft_id}/decision", json={**body, "decision": "reject"}).json()["status"] == "rejected"
    assert client.get("/api/drafts").json()[0]["status"] == "rejected"


def test_a_hand_edited_invalid_draft_offers_nothing_to_approve(tmp_path, configured, draft):
    root, client = app(tmp_path, FakePipeline(draft))
    started = client.post("/api/drafts", json={"manual": SAMPLE.read_text(encoding="utf-8")}).json()
    wait_for(client, started["id"])
    data = json.loads((root / started["draft"] / "draft.json").read_text(encoding="utf-8"))
    data["personas"][2]["browsing_profile"]["tools"] = ["read_console"]  # non-developers cannot get technical tools
    write_json(root / started["draft"] / "draft.json", data)
    review = client.get(f"/api/drafts/{started['draft']}").json()
    assert review["valid"] is False and "developer" in review["error"].lower() and "personas" not in review


def test_a_draft_whose_capability_profile_no_longer_matches_says_so_before_approval(tmp_path, monkeypatch, configured, draft):
    root, client = app(tmp_path, FakePipeline(draft))
    started = client.post("/api/drafts", json={"manual": SAMPLE.read_text(encoding="utf-8")}).json()
    wait_for(client, started["id"])
    assert client.get(f"/api/drafts/{started['draft']}").json()["blocked"] is None
    changed = {**SETTINGS, "model": "another-model"}  # the model configuration changed after the draft was made
    for module in (drafts, phase1):
        monkeypatch.setattr(module, "settings", lambda: changed)
    review = client.get(f"/api/drafts/{started['draft']}").json()
    assert review["valid"] is True and "重新新建运行" in review["blocked"]
    refused = client.post(f"/api/drafts/{started['draft']}/decision", json={"decision": "approve", "draft_sha256": review["draft_sha256"]})
    assert refused.status_code == 422


def test_invalid_input_never_starts_a_job(tmp_path, configured, draft):
    pipeline = FakePipeline(draft)
    root, client = app(tmp_path, pipeline)
    template = (SAMPLE.parent.parent / "product_manual_template.md").read_text(encoding="utf-8")
    assert client.post("/api/drafts", json={"manual": template}).status_code == 422
    assert client.post("/api/drafts", json={"manual": SAMPLE.read_text(encoding="utf-8"), "capability_run": "../x"}).status_code == 422
    assert client.post("/api/drafts/phase1-nope/simulations", json={"confirm": True}).status_code == 404
    assert client.post("/api/drafts/../simulations", json={"confirm": True}).status_code in {404, 405}
    assert client.post("/api/drafts/phase1-nope/simulations", json={"confirm": False}).status_code == 422
    assert pipeline.calls == [] and client.get("/api/jobs").json() == []


def test_a_job_from_an_earlier_api_process_is_reported_as_detached(tmp_path):
    root = tmp_path / "runs"
    write_json(root / "_jobs" / "prepare-x.json", {"id": "prepare-x", "kind": "prepare", "state": "running", "draft": "phase1-x",
                                                   "created_at": "2026-10-04T00:00:00+00:00", "steps": []})
    client = TestClient(create_app(root))
    assert client.get("/api/jobs/prepare-x").json()["state"] == "detached"
