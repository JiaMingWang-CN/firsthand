"""Text-only models: a model that cannot read images still runs, after the user accepts the limited reference value."""

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from core.runtime import TEXT_ONLY_NOTE, require_capabilities, write_json
from orchestrator import phase1
from orchestrator.manual import read_manual
from test_phase1 import CAPABILITY, CONFIG, SAMPLE, draft  # noqa: F401  (draft is a fixture)
from test_phase7 import URL_ONLY, cohort, mock_model
from test_pipeline import FakePipeline, app, configured, wait_for  # noqa: F401  (configured is a fixture)

TEXT_ONLY = {**CAPABILITY, "vision": False}


def test_old_profiles_were_probed_with_vision_and_text_only_profiles_still_pass(tmp_path):
    write_json(tmp_path / "capability_profile.json", TEXT_ONLY)
    assert require_capabilities(tmp_path, CONFIG)["vision"] is False


def test_analysis_waits_for_the_user_then_resumes(tmp_path, monkeypatch):
    manual_path = tmp_path / "in.md"
    manual_path.write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(phase1, "settings", lambda: dict(CONFIG))
    sites = []

    async def probe(config, run_dir):
        write_json(Path(run_dir) / "capability_profile.json", TEXT_ONLY)
        return TEXT_ONLY

    async def no_site(url, domains):
        sites.append(url)
        return {"status": "failed", "url": url, "reason": "测试"}
    monkeypatch.setattr(phase1, "probe_model", probe)
    monkeypatch.setattr(phase1, "read_site", no_site)
    mock_model(monkeypatch, cohort(12, read_manual(SAMPLE)), bodies := [])
    run = tmp_path / "run"
    assert asyncio.run(phase1.analyze(manual_path, run))["stage"] == "text_only"
    assert not sites and not bodies and not (run / "product.json").exists()  # nothing more is paid for before the user accepts
    assert asyncio.run(phase1.resume(run))["stage"] == "analyzed" and sites
    with pytest.raises(ValueError, match="纯文本"):
        asyncio.run(phase1.resume(run))
    asyncio.run(phase1.generate(run, 12, 50))
    assert TEXT_ONLY_NOTE in (run / "review.md").read_text(encoding="utf-8")


class TextOnlyPipeline(FakePipeline):
    """The analysis stops after a probe that found no vision; resume continues it."""

    def __call__(self, argv, cwd, env, stdout, stderr):
        args = [str(arg) for arg in argv[3:]]
        process = super().__call__(argv, cwd, env, stdout, stderr)
        if argv[2] == "orchestrator.phase1" and args[0] == "analyze":
            run = Path(args[args.index("--run-dir") + 1])
            write_json(run / "capability_profile.json", TEXT_ONLY)
            write_json(run / "phase1_result.json", {"stage": "text_only", "passed": True})
        if argv[2] == "orchestrator.phase1" and args[0] == "resume":
            write_json(Path(args[1]) / "phase1_result.json", {"stage": "analyzed", "passed": True, "minimum_personas": 3,
                       "recommendation": {"persona_count": 40, "duration_days": 50, "reason": "测试推荐"}})
        return process


def test_the_ui_confirms_a_text_only_model_before_the_analysis_goes_on(tmp_path, configured, draft):
    pipeline = TextOnlyPipeline(draft)
    root, client = app(tmp_path, pipeline)
    write_json(root / "phase0-text" / "capability_profile.json", TEXT_ONLY)
    assert client.get("/api/capabilities").json()[0]["vision"] is False
    started = client.post("/api/drafts", json={"manual": SAMPLE.read_text(encoding="utf-8")}).json()
    wait_for(client, started["id"])
    waiting = client.get(f"/api/drafts/{started['draft']}").json()
    assert waiting["status"] == "text_only" and waiting["text_only"] is True and waiting["valid"] is False
    listed = client.get("/api/drafts").json()[0]
    assert listed["status"] == "text_only" and listed["text_only"] is True
    assert client.post(f"/api/drafts/{started['draft']}/analysis", json={"confirm": False}).status_code == 422
    resumed = client.post(f"/api/drafts/{started['draft']}/analysis", json={"confirm": True}).json()
    wait_for(client, resumed["id"])
    assert pipeline.calls[-1] == ("orchestrator.phase1", ["resume", str(root / started["draft"])])
    configuring = client.get(f"/api/drafts/{started['draft']}").json()
    assert configuring["status"] == "configuring" and configuring["text_only"] is True
    assert client.post(f"/api/drafts/{started['draft']}/analysis", json={"confirm": True}).status_code == 422


def test_runs_and_report_say_a_run_was_text_only(source, tmp_path):
    from orchestrator.phase5 import execute
    run, draft_dir = tmp_path / "phase4-text", tmp_path / "phase1-text"
    shutil.copytree(source, run)
    write_json(run / "phase4_result.json", {"passed": True})
    write_json(run / "run_context.json", {"source_run": str(draft_dir), "configuration": {"provider": "fixture"}})
    draft_dir.mkdir()
    (draft_dir / "manual.md").write_text(URL_ONLY, encoding="utf-8")
    write_json(draft_dir / "capability_profile.json", TEXT_ONLY)
    asyncio.run(execute(run, tmp_path / "phase5-text", None, False))
    notes = json.loads((tmp_path / "phase5-text" / "report.json").read_text(encoding="utf-8"))["overview"]["coverage_notes"]
    assert any(TEXT_ONLY_NOTE in note for note in notes)
    from api.runs import list_runs
    assert next(item for item in list_runs(tmp_path) if item["id"] == "phase4-text")["text_only"] is True
    write_json(draft_dir / "capability_profile.json", CAPABILITY)
    assert next(item for item in list_runs(tmp_path) if item["id"] == "phase4-text")["text_only"] is False
