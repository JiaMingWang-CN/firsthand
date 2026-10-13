"""Phase 7: URL-only manuals, cohort size and timeline length chosen by the user, per-persona sampling."""

import asyncio
import json
import re
from collections import Counter
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from pydantic import ValidationError

from api.app import create_app
from api.jobs import Jobs
from core.persona import CohortSlot, Draft, Sampling
from core.runtime import write_json
from orchestrator import personas, phase1
from orchestrator.manual import material, read_manual
from orchestrator.personas import (assign_sampling, cohort_issues, constraints_text, distribution_issues, minimum_count, quotas,
                                   request_json, sampling_options, schedule_rows, targets, validate_draft)
from orchestrator.site import read_site
from test_phase1 import CAPABILITY, CONFIG, PRODUCT, SAMPLE, draft  # noqa: F401  (draft is a fixture)
from test_pipeline import SETTINGS, FakePipeline, configured, make_draft  # noqa: F401  (configured is a fixture)

URL_ONLY = "---\nurl: https://wjm.dpdns.org\nallowed_domains:\n  - wjm.dpdns.org\n---\n"


def manual_from(tmp_path, text):
    path = tmp_path / "manual.md"
    path.write_text(text, encoding="utf-8")
    return read_manual(path)


def test_a_url_and_allowed_domains_are_enough(tmp_path):
    manual = manual_from(tmp_path, URL_ONLY)
    metadata = manual["metadata"]
    assert metadata.name == "wjm.dpdns.org" and metadata.test_accounts == [] and "真实支付或下单" in metadata.forbidden_actions
    assert manual["flows"] == [] and manual["sections"] == {}
    assert set(manual["defaults"]) == {"name", "test_accounts", "forbidden_actions"}
    assert "真实支付或下单" in manual["generation_source"]  # the model sees the defaults it must respect
    about = material(manual)
    assert about["level"] == "limited" and "参考性有限" in about["summary"]
    assert {gap["item"] for gap in about["gaps"]} == {"产品定位", "目标用户", "核心功能", "关键流程", "test_accounts", "forbidden_actions"}


def test_material_levels(tmp_path):
    assert material(read_manual(SAMPLE))["level"] == "complete"
    partial = manual_from(tmp_path, URL_ONLY + "\n# 产品定位\n\n个人作品网站\n")
    assert material(partial)["level"] == "partial"


@pytest.mark.parametrize("text, message", [
    ("---\nurl: https://wjm.dpdns.org\n---\n", "allowed_domains"),
    ("---\nallowed_domains: [wjm.dpdns.org]\n---\n", "url"),
    (URL_ONLY + "\n# 随便写的章节\n\n内容\n", "未知章节"),
    (URL_ONLY + "\n# 关键流程\n\n只有一句话\n", "流程：名称"),
    ("---\nurl: https://wjm.dpdns.org\nallowed_domains: [wjm.dpdns.org]\nforbidden_actions: []\n---\n", "forbidden_actions"),
])
def test_what_is_still_rejected(tmp_path, text, message):
    with pytest.raises(ValueError, match=message):
        manual_from(tmp_path, text)


def test_ten_people_keep_the_original_constraints():
    goal = targets(10, 2)
    assert (goal["developer"], goal["mobile"], goal["low_patience"], goal["withhold_high"], goal["explore"]) == (2, 4, 3, 2, 3)
    assert goal["participation"] == {"poster": 3, "commenter": 3, "reactor": 2, "lurker": 2} and goal["tolerance"] == 0
    assert goal["per_flow"] == 2 and goal["browse_days"] == 1


@pytest.mark.parametrize("count", [2, 3, 7, 23, 40, 50, 99])
def test_constraints_scale_with_the_cohort(count):
    goal = targets(count, 2, 50)
    assert sum(goal["participation"].values()) == count and goal["explore"] + goal["tasks"] == count
    assert goal["tolerance"] == count // 20 and goal["browse_days"] == min(3, count)
    assert "全部自由探索" in constraints_text(count, 0, 1) and targets(count, 0)["explore"] == count  # no flows: everyone explores
    assert sum(quotas(count, {"a": 0.5, "b": 0.5}).values()) == count


def test_minimum_cohort_covers_every_flow():
    assert minimum_count(0) == 2
    assert all(targets(minimum_count(flows), flows)["tasks"] >= flows for flows in range(1, 8))
    assert targets(minimum_count(5) - 1, 5)["tasks"] < 5


def test_later_browse_days_land_on_later_slices(draft):
    data = draft.model_dump(mode="json")
    data["run_config"]["duration_days"] = 3
    data["personas"][2]["schedule"]["browse_day"] = 3  # p03 browses at 07:30 local
    later = Draft.model_validate(data)
    row = next(row for row in schedule_rows(later) if row["persona_id"] == "p03")
    assert row["local_time"] == "2026-10-05T07:30:00+08:00" and row["slice_index"] == 23 + 48
    data["run_config"]["duration_days"] = 2
    with pytest.raises(ValueError, match="browse_day 超出"):
        validate_draft(Draft.model_validate(data), read_manual(SAMPLE), CAPABILITY)


def test_browse_days_must_spread_on_a_multi_day_timeline(draft):
    manual = read_manual(SAMPLE)
    slots = [personas.slot_of(persona) for persona in draft.personas]
    assert "体验日至少分布在 3 个不同的日子（当前 1 个）" in cohort_issues(slots, draft.product, manual, days=50)
    for index, slot in enumerate(slots):
        slot.browse_day = 1 + (index % 3) * 20
    assert cohort_issues(slots, draft.product, manual, days=50) == []


def cohort(count, manual):
    """A cohort of any size satisfying every scaled constraint, standing in for the main agent."""
    goal = targets(count, len(manual["flows"]), 50)
    roles = [role for role, number in goal["participation"].items() for _ in range(number)]
    slots = []
    for index in range(count):
        explore = index >= goal["tasks"]
        flow = None if explore else manual["flows"][index % len(manual["flows"])]
        slots.append(CohortSlot(
            persona_id=f"p{index + 1:02d}", realname=f"测试{index + 1}号", profession=f"职业{index + 1}", gender="女" if index % 2 else "男",
            age=20 + index * 7 % 35, tech_level="developer" if index < goal["developer"] else "normal",
            device="mobile" if index < goal["mobile"] else "desktop", patience="low" if index < goal["low_patience"] else "normal",
            motivation="随便看看" if explore else "有明确任务", participation=roles[index],
            withhold_tendency="高" if index < goal["withhold_high"] else "中", browse_slot=["07:30", "13:10", "21:10", "02:10"][index % 4],
            browse_day=1 + (index % 3) * 20, account_role="new_visitor",
            assignment={"type": "explore", "flow": None} if explore else {"type": "task", "flow": flow.name}, reason="测试槽位"))
    return slots


def details_for(slot):
    night = int(slot["browse_slot"][:2]) < 6
    return {"realname": slot["realname"], "username": f"user_{slot['persona_id']}", "gender": slot["gender"], "age": slot["age"],
            "city": "上海", "timezone": "Asia/Shanghai", "profession": slot["profession"], "industry": "软件", "education": "本科",
            "income_level": "中", "life_context": "在职", "product_history": "未使用过", "bio": "合成测试角色", "persona": "评估作品",
            "mbti": "INTJ", "big_five": {key: "中" for key in ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]},
            "communication_style": "直接", "interested_topics": ["项目交付"], "wake": "10:00" if night else "06:00",
            "sleep": "03:00" if night else "23:50", "activity": [{"hour": 12, "probability": 0.5}], "state_at_browse": "有空",
            "motivation": "评估作品", "candor": "中", "withhold_reasons": ["怕显得不懂技术"]}


def mock_model(monkeypatch, slots, bodies):
    def respond(request):
        body = json.loads(request.content)
        bodies.append(body)
        name = body["response_format"]["json_schema"]["name"]
        prompt = body["messages"][1]["content"]
        if name in {"CohortPlan", "CohortBatch"}:
            batch = re.search(r"本次只输出 (p\d+)–(p\d+)", prompt)
            first, last = (int(batch[1][1:]), int(batch[2][1:])) if batch else (1, len(slots))
            content = {"slots": [slot.model_dump() for slot in slots[first - 1:last]]}
            if name == "CohortPlan":
                content["rationale"] = "按目标用户分布"
        elif name == "Recommendation":
            content = {"persona_count": 40, "duration_days": 50, "reason": "流程较少，取中间值"}
        elif name == "ProductSummary":
            content = PRODUCT
        else:
            payload = json.loads(prompt[prompt.index("\n") + 1:prompt.index("\n输出 schema")])
            content = details_for(payload["seed"])
        return httpx.Response(200, json={"id": "t", "object": "chat.completion", "created": 0, "model": "custom", "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(content, ensure_ascii=False)}}]})

    real_client = AsyncOpenAI
    client = lambda **kwargs: real_client(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))  # noqa: E731
    monkeypatch.setattr(personas, "AsyncOpenAI", client)
    monkeypatch.setattr(phase1, "AsyncOpenAI", client)


def test_a_large_cohort_is_planned_in_batches_over_a_long_timeline(monkeypatch):
    manual = read_manual(SAMPLE)
    slots, bodies = cohort(23, manual), []
    mock_model(monkeypatch, slots, bodies)
    capability = {**CAPABILITY, "checks": {**CAPABILITY["checks"], "sampling": {"supported": True}}}
    config = dict(CONFIG, max_model_concurrency=4, max_browser_concurrency=1)
    draft = asyncio.run(personas.generate_draft(config, capability, manual, count=23, days=50))
    plans = [body for body in bodies if body["response_format"]["json_schema"]["name"] in {"CohortPlan", "CohortBatch"}]
    assert [body["response_format"]["json_schema"]["name"] for body in plans] == ["CohortPlan", "CohortBatch", "CohortBatch"]
    assert "p11–p20" in plans[1]["messages"][1]["content"] and '"previous"' in plans[1]["messages"][1]["content"]
    assert [p.persona_id for p in draft.personas] == [f"p{i:02d}" for i in range(1, 24)]
    assert draft.run_config.duration_days == 50 and draft.cohort_rationale == "按目标用户分布"
    assert {p.schedule.browse_day for p in draft.personas} == {1, 21, 41}
    pairs = [(p.sampling.temperature, p.sampling.top_p) for p in draft.personas]
    assert len(set(pairs)) == 23  # same personality, still a different voice each
    assert all("temperature" not in body for body in bodies)  # the main agent's own calls keep the default sampling
    assert distribution_issues(draft, manual) == []


def test_a_batch_may_not_overfill_an_exact_quota(monkeypatch):
    manual = read_manual(SAMPLE)
    slots = cohort(23, manual)
    for slot in slots[:10]:
        slot.participation = "poster"  # 10 posters already exceed the cohort's 7 (±1)
    mock_model(monkeypatch, slots, [])
    with pytest.raises(ValueError, match="poster 已超过全体配额"):
        asyncio.run(personas.generate_draft(CONFIG, CAPABILITY, manual, count=23, days=50))


def test_too_few_people_for_the_flows_is_refused_before_any_request():
    manual = read_manual(SAMPLE)
    with pytest.raises(ValueError, match="至少需要"):
        asyncio.run(personas.generate_draft(CONFIG, CAPABILITY, manual, count=minimum_count(len(manual["flows"])) - 1, days=1))


def test_analyze_then_generate(tmp_path, monkeypatch):
    manual_path = tmp_path / "in.md"
    manual_path.write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    write_json(tmp_path / "cap" / "capability_profile.json", {**CAPABILITY, "ready": True})
    monkeypatch.setattr(phase1, "settings", lambda: dict(CONFIG))
    monkeypatch.setattr(phase1, "require_capabilities", lambda run_dir, config: {**CAPABILITY, "ready": True})

    async def no_site(url, domains):
        return {"status": "failed", "url": url, "reason": "测试"}
    monkeypatch.setattr(phase1, "read_site", no_site)
    manual = read_manual(SAMPLE)
    mock_model(monkeypatch, cohort(12, manual), [])
    run = tmp_path / "run"
    result = asyncio.run(phase1.analyze(manual_path, run, tmp_path / "cap"))
    assert result["stage"] == "analyzed" and result["recommendation"]["persona_count"] == 40 and not (run / "draft.json").exists()
    assert json.loads((run / "site.json").read_text(encoding="utf-8"))["status"] == "failed"
    draft = asyncio.run(phase1.generate(run, 12, 50))
    assert len(draft.personas) == 12 and draft.run_config.duration_days == 50
    assert json.loads((run / "phase1_result.json").read_text(encoding="utf-8"))["stage"] == "drafted"
    assert "温度/top_p" in (run / "review.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="尚未生成人物"):
        asyncio.run(phase1.generate(run, 12, 50))


def test_sampling_reaches_the_wire_only_where_the_probe_saw_it_accepted():
    sampling = Sampling(temperature=0.8, top_p=0.9, presence_penalty=0.2)
    chat = {"api": "chat_completions", "checks": {"sampling": {"supported": True}}}
    assert sampling_options(chat, sampling, "chat_completions") == {"temperature": 0.8, "top_p": 0.9, "presence_penalty": 0.2}
    assert sampling_options({"checks": {}}, sampling, "chat_completions") == {}  # profiles probed before phase 7
    assert sampling_options(chat, None, "chat_completions") == {}
    responses = {"api": "responses", "checks": {"sampling": {"supported": True}, "chat_completions_sampling": {"supported": False}}}
    assert sampling_options(responses, sampling.model_dump(), "responses") == {"temperature": 0.8, "top_p": 0.9}
    assert sampling_options(responses, sampling, "chat_completions") == {}


@pytest.mark.parametrize("api", ["chat_completions", "responses"])
def test_persona_voiced_requests_carry_the_persona_sampling(api):
    bodies = []
    summary = json.dumps(PRODUCT, ensure_ascii=False)

    def respond(request):
        bodies.append(json.loads(request.content))
        if api == "responses":
            return httpx.Response(200, json={"id": "r", "object": "response", "created_at": 0, "model": "custom", "status": "completed",
                "output": [{"type": "message", "id": "m", "status": "completed", "role": "assistant",
                            "content": [{"type": "output_text", "text": summary, "annotations": []}]}]})
        return httpx.Response(200, json={"id": "t", "object": "chat.completion", "created": 0, "model": "custom", "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": summary}}]})

    async def main():
        async with AsyncOpenAI(api_key="t", base_url=CONFIG["base_url"],
                               http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
            capability = {"api": api, "checks": {"json_schema": {"supported": True}, "sampling": {"supported": True}}}
            config = dict(CONFIG, api=api)
            await request_json(client, config, capability, personas.ProductSummary, "x",
                               sampling={"temperature": 0.73, "top_p": 0.91, "presence_penalty": 0.1})
            await request_json(client, config, capability, personas.ProductSummary, "x")
    asyncio.run(main())
    assert bodies[0]["temperature"] == 0.73 and bodies[0]["top_p"] == 0.91
    assert ("presence_penalty" in bodies[0]) == (api == "chat_completions")
    assert "temperature" not in bodies[1]


def test_browser_use_requests_carry_the_persona_sampling():
    from browsing.model import ProviderChatOpenAI
    from browser_use.llm.messages import UserMessage
    bodies = []

    def respond(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "t", "object": "chat.completion", "created": 0, "model": "custom", "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    llm = ProviderChatOpenAI(model="custom", base_url=CONFIG["base_url"], api_key="t", provider="openai_compatible", max_retries=0,
                             http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
                             sampling={"temperature": 0.61, "top_p": 0.88, "presence_penalty": 0.3})
    asyncio.run(llm.ainvoke([UserMessage(content="hi")]))
    assert (bodies[0]["temperature"], bodies[0]["top_p"], bodies[0]["presence_penalty"]) == (0.61, 0.88, 0.3)


def test_equal_sampling_is_a_distribution_issue_and_derivation_follows_personality(draft):
    manual = read_manual(SAMPLE)
    assign_sampling(draft.personas)
    assert distribution_issues(draft, manual) == []
    open_person, closed_person = draft.personas[0], draft.personas[1]
    open_person.big_five.openness, closed_person.big_five.openness = "高", "低"
    assert personas.derived_sampling(open_person).temperature > personas.derived_sampling(closed_person).temperature
    draft.personas[1].sampling = draft.personas[0].sampling.model_copy()
    assert "采样参数（temperature、top_p）完全相同" in "；".join(distribution_issues(draft, manual))
    with pytest.raises(ValidationError):
        Sampling(temperature=2.5, top_p=0.9, presence_penalty=0)


def site(handler):
    return asyncio.run(read_site("https://wjm.dpdns.org/", ["wjm.dpdns.org"], transport=httpx.MockTransport(handler)))


def test_the_start_page_is_read_within_the_allowed_domains():
    page = "<html><head><title>作品集</title><meta name='description' content='个人作品'><script>secret()</script></head><body><h1>王佳明</h1>" + "项目经历 " * 60 + "</body></html>"
    result = site(lambda request: httpx.Response(200, html=page))
    assert result["status"] == "ok" and result["title"] == "作品集" and result["description"] == "个人作品"
    assert "王佳明" in result["text"] and "secret" not in result["text"] and "note" not in result
    away = site(lambda request: httpx.Response(302, headers={"location": "https://elsewhere.example/"}))
    assert away["status"] == "failed" and "allowed_domains" in away["reason"]
    empty = site(lambda request: httpx.Response(200, html="<div id=app></div><script src=app.js></script>"))
    assert empty["status"] == "ok" and "脚本渲染" in empty["note"]
    assert site(lambda request: httpx.Response(503))["reason"] == "HTTP 503"


def test_the_reviewer_edits_days_and_sampling_and_must_approve_again(tmp_path, configured, draft):
    root = tmp_path / "runs"
    root.mkdir()
    assign_sampling(draft.personas)
    client = TestClient(create_app(root, jobs=Jobs(root, python="python", popen=FakePipeline(draft))), base_url="http://localhost")
    draft_id = make_draft(client)["draft"]
    review = client.get(f"/api/drafts/{draft_id}").json()
    assert review["personas"][0]["sampling"]["temperature"] > 0 and review["sampling"]["probed"] is False
    client.post(f"/api/drafts/{draft_id}/decision", json={"decision": "approve", "draft_sha256": review["draft_sha256"]})
    stale = client.post(f"/api/drafts/{draft_id}/edits", json={"draft_sha256": "0" * 64, "duration_days": 7})
    assert stale.status_code == 422 and "不同" in stale.json()["detail"]
    edited = client.post(f"/api/drafts/{draft_id}/edits", json={"draft_sha256": review["draft_sha256"], "duration_days": 7,
                         "sampling": {"p01": {"temperature": 1.2, "top_p": 0.8, "presence_penalty": 0.5}}})
    assert edited.status_code == 200
    after = client.get(f"/api/drafts/{draft_id}").json()
    assert after["run_config"]["duration_days"] == 7 and after["personas"][0]["sampling"]["temperature"] == 1.2
    assert after["status"] == "stale" and after["draft_sha256"] == edited.json()["draft_sha256"]
    bad = {"draft_sha256": after["draft_sha256"], "sampling": {"p01": {"temperature": 3, "top_p": 0.8, "presence_penalty": 0}}}
    assert client.post(f"/api/drafts/{draft_id}/edits", json=bad).status_code == 422
    ghost = {"draft_sha256": after["draft_sha256"], "sampling": {"p77": {"temperature": 1, "top_p": 0.8, "presence_penalty": 0}}}
    assert client.post(f"/api/drafts/{draft_id}/edits", json=ghost).status_code == 422


def test_shortening_the_timeline_below_a_browse_day_is_refused(tmp_path, configured, draft):
    root = tmp_path / "runs"
    root.mkdir()
    data = draft.model_dump(mode="json")
    data["run_config"]["duration_days"] = 30
    data["personas"][4]["schedule"]["browse_day"] = 20
    client = TestClient(create_app(root, jobs=Jobs(root, python="python", popen=FakePipeline(Draft.model_validate(data)))), base_url="http://localhost")
    draft_id = make_draft(client)["draft"]
    review = client.get(f"/api/drafts/{draft_id}").json()
    refused = client.post(f"/api/drafts/{draft_id}/edits", json={"draft_sha256": review["draft_sha256"], "duration_days": 10})
    assert refused.status_code == 422 and "第 20 天" in refused.json()["detail"]


def test_manual_check_reports_material_and_defaults(tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    client = TestClient(create_app(root), base_url="http://localhost")
    body = client.post("/api/manuals/check", json={"text": URL_ONLY}).json()
    assert body["name"] == "wjm.dpdns.org" and body["material"]["level"] == "limited" and body["minimum_personas"] == 2
    assert "forbidden_actions" in body["defaults"] and body["forbidden_actions"][0] == "真实支付或下单"
    full = client.post("/api/manuals/check", json={"text": SAMPLE.read_text(encoding="utf-8")}).json()
    assert full["material"]["level"] == "complete" and full["minimum_personas"] == minimum_count(2)


def test_the_report_says_when_the_material_was_thin(source, tmp_path):
    import shutil
    from orchestrator.phase5 import execute
    run, draft_dir = tmp_path / "phase4-thin", tmp_path / "phase1-thin"
    shutil.copytree(source, run)
    write_json(run / "phase4_result.json", {"passed": True})
    write_json(run / "run_context.json", {"source_run": str(draft_dir), "configuration": {"provider": "fixture"}})
    draft_dir.mkdir()
    (draft_dir / "manual.md").write_text(URL_ONLY, encoding="utf-8")
    asyncio.run(execute(run, tmp_path / "phase5-thin", None, False))
    notes = json.loads((tmp_path / "phase5-thin" / "report.json").read_text(encoding="utf-8"))["overview"]["coverage_notes"]
    assert any("参考性有限" in note and "缺少 关键流程" in note for note in notes)


def test_the_review_page_opened_before_the_analysis_writes_anything_shows_it_is_analyzing(tmp_path, configured, draft):
    import threading
    from test_pipeline import SAMPLE, wait_for
    root = tmp_path / "runs"
    root.mkdir()
    gate = threading.Event()
    client = TestClient(create_app(root, jobs=Jobs(root, python="python", popen=FakePipeline(draft, gate=gate))), base_url="http://localhost")
    started = client.post("/api/drafts", json={"manual": SAMPLE.read_text(encoding="utf-8")}).json()
    early = client.get(f"/api/drafts/{started['draft']}")
    assert early.status_code == 200 and early.json()["status"] == "analyzing" and early.json()["valid"] is False
    gate.set()
    wait_for(client, started["id"])
    assert client.get(f"/api/drafts/{started['draft']}").json()["status"] == "configuring"
    failing = TestClient(create_app(root, jobs=Jobs(root, python="python", popen=FakePipeline(draft, codes={"orchestrator.phase1": 1}))), base_url="http://localhost")
    broken = failing.post("/api/drafts", json={"manual": SAMPLE.read_text(encoding="utf-8")}).json()
    wait_for(failing, broken["id"], "failed")
    assert failing.get(f"/api/drafts/{broken['draft']}").json()["status"] == "failed"
    assert failing.get("/api/drafts/phase1-20990101T000000000000Z").status_code == 404
