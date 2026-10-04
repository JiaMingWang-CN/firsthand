import asyncio
import json
from collections import Counter
from datetime import datetime, timezone

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import ValidationError

from core.persona import CohortSlot, Draft, PersonaDetails, ProductSummary, RunConfig
from core.runtime import ROOT, write_json
from orchestrator import personas, phase1
from orchestrator.manual import read_manual
from orchestrator.personas import (assignment_errors, build_persona, cohort_issues, distribution_issues, request_json,
                                   schedule_rows, validate_draft)

SAMPLE = ROOT.parent / "docs/examples/wjm_product_manual.md"
CONFIG = {"model": "custom", "base_url": "https://test.invalid/v1", "api_key": "test", "thinking_type": "disabled"}
CAPABILITY = {"model": "custom", "base_url": CONFIG["base_url"], "thinking_type": "disabled", "ready": True,
              "recommended_concurrency": 10, "checks": {"json_schema": {"supported": True}, "json_prompt": {"supported": False}}}
PRODUCT = {"positioning": "展示开发者作品", "target_users": "招聘方和合作方", "features": ["首页介绍", "项目列表"], "assumptions": [],
           "target_age_min": 20, "target_age_max": 55}
ROWS = [
    ("developer", "desktop", "normal", "poster", "中", "21:10"),
    ("developer", "desktop", "high", "commenter", "低", "12:30"),
    ("novice", "mobile", "low", "poster", "高", "07:30"),
    ("normal", "mobile", "low", "commenter", "中", "21:40"),
    ("novice", "mobile", "low", "reactor", "中", "00:30"),
    ("normal", "desktop", "normal", "poster", "低", "13:10"),
    ("normal", "desktop", "high", "commenter", "中", "09:30"),
    ("novice", "mobile", "normal", "reactor", "中", "23:10"),
    ("normal", "desktop", "normal", "lurker", "高", "08:10"),
    ("normal", "desktop", "high", "lurker", "中", "02:10"),
]


def plan_slots(manual):
    """A cohort plan satisfying every constraint, standing in for the main agent's output."""
    slots = []
    for index, (tech, device, patience, participation, withholding, slot) in enumerate(ROWS):
        flow = manual["flows"][index % len(manual["flows"])] if index < 7 else None
        slots.append(CohortSlot(persona_id=f"p{index + 1:02d}", realname=f"测试用户{index + 1}", profession=f"职业{index + 1}", gender="女" if index % 2 else "男", age=22 + index * 3,
                                tech_level=tech, device=device, patience=patience, motivation="有明确任务" if flow else "随便看看",
                                participation=participation, withhold_tendency=withholding, browse_slot=slot,
                                account_role="new_visitor", assignment={"type": "task" if flow else "explore", "flow": flow.name if flow else None},
                                reason="测试槽位"))
    return slots


@pytest.fixture
def draft():
    manual = read_manual(SAMPLE)
    people = []
    for index, slot in enumerate(plan_slots(manual)):
        night = int(slot.browse_slot[:2]) < 6
        details = PersonaDetails.model_validate({
            "realname": slot.realname, "username": f"test_{index}", "gender": slot.gender,
            "age": slot.age, "city": "上海", "timezone": "Asia/Shanghai", "profession": slot.profession,
            "industry": "软件", "education": "本科", "income_level": "中", "life_context": "在职，利用休息时间评估作品",
            "product_history": "未使用过待测网站，有阅读其他作品的经历", "bio": "合成测试角色", "persona": "根据既有经历评估开发者作品",
            "mbti": "INTJ", "big_five": {key: "中" for key in ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]},
            "communication_style": "直接", "interested_topics": ["项目交付"], "wake": "10:00" if night else "06:00",
            "sleep": "03:00" if night else "23:50", "activity": [{"hour": 12, "probability": 0.5}],
            "state_at_browse": "有明确评估目的", "motivation": "评估作品", "candor": "中", "withhold_reasons": ["怕显得自己不懂技术"],
        })
        people.append(build_persona(details, slot.model_dump()))
    return Draft(product=ProductSummary(**PRODUCT), cohort_rationale="测试分布", personas=people, run_config=RunConfig(start_time=datetime(2026, 10, 2, tzinfo=timezone.utc), duration_days=1,
                                                       time_slice_minutes=60, max_concurrency=1))


@pytest.mark.parametrize("section", ["产品定位", "目标用户", "核心功能", "关键流程"])
def test_missing_required_sections_rejected(tmp_path, section):
    text = SAMPLE.read_text(encoding="utf-8")
    text = text.replace("# " + section + "\n", "# 被改名章节\n")
    path = tmp_path / "manual.md"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        read_manual(path)


@pytest.mark.parametrize("before,after", [
    ("allowed_domains:\n  - wjm.dpdns.org", "allowed_domains:\n  - other.example"),
    ("- 适用账号：新访客", "- 适用账号：unknown_role"),
    ("- 成功标准：首页相关文本可读，能基于实际页面找到姓名、开发方向和经历的证据", "- 成功标准："),
    ("name: JiaMingWang-CN 个人作品网站", "name: first\nname: second"),
    ("description: 无需登录，访问公开页面的新访客", "description: visitor\n    password: must-not-go-to-model"),
])
def test_invalid_manual_fields_rejected(tmp_path, before, after):
    path = tmp_path / "manual.md"
    path.write_text(SAMPLE.read_text(encoding="utf-8").replace(before, after), encoding="utf-8")
    with pytest.raises(ValueError):
        read_manual(path)


def test_template_comments_do_not_count_as_content():
    with pytest.raises(ValueError, match="缺少必填章节"):
        read_manual(ROOT.parent / "docs/product_manual_template.md")


def test_invalid_manual_does_not_make_paid_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(phase1, "settings", lambda: pytest.fail("Invalid input must be rejected before configuration/API calls"))
    with pytest.raises(ValueError):
        asyncio.run(phase1.prepare(ROOT.parent / "docs/product_manual_template.md", tmp_path / "run"))
    assert not (tmp_path / "run").exists()


def test_cohort_coverage_and_local_time_alignment(draft):
    manual = read_manual(SAMPLE)
    validate_draft(draft, manual, CAPABILITY)
    assert distribution_issues(draft, manual) == []
    morning = next(row for row in schedule_rows(draft) if row["persona_id"] == "p03")
    assert morning["local_time"] == "2026-10-03T07:30:00+08:00"
    assert morning["utc_time"] == "2026-10-02T23:30:00+00:00"
    assert morning["slice_index"] == 23


def test_non_developer_cannot_receive_technical_tools(draft):
    data = draft.model_dump(mode="json")
    data["personas"][2]["browsing_profile"]["tools"] = ["read_console"]
    with pytest.raises(ValidationError, match="Only developers"):
        Draft.model_validate(data)


def test_asleep_browse_slot_rejected(draft):
    data = draft.model_dump(mode="json")
    data["personas"][0]["schedule"].update(wake="08:00", sleep="20:00")
    with pytest.raises(ValidationError, match="awake hours"):
        Draft.model_validate(data)


def test_incoherent_single_sleep_window_rejected(draft):
    data = draft.model_dump(mode="json")
    data["personas"][9]["schedule"].update(wake="06:50", sleep="04:30")
    with pytest.raises(ValidationError, match="sleep window"):
        Draft.model_validate(data)


@pytest.mark.parametrize("edit_manual", [False, True])
def test_approval_required_and_invalidated_by_edits(tmp_path, monkeypatch, draft, edit_manual):
    (tmp_path / "manual.md").write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    write_json(tmp_path / "draft.json", draft.model_dump(mode="json"))
    write_json(tmp_path / "capability_profile.json", CAPABILITY)
    monkeypatch.setattr(phase1, "settings", lambda: CONFIG)
    with pytest.raises(ValueError, match="尚未通过人工审核"):
        phase1.require_approved(tmp_path)
    phase1.review(tmp_path, input_fn=lambda prompt: "approve")
    assert phase1.require_approved(tmp_path)[0].personas[0].realname == "测试用户1"
    if edit_manual:
        path = tmp_path / "manual.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n调整关注点\n", encoding="utf-8")
    else:
        data = draft.model_dump(mode="json")
        data["personas"][0]["realname"] = "新名字"
        write_json(tmp_path / "draft.json", data)
    with pytest.raises(ValueError, match="审批已失效"):
        phase1.require_approved(tmp_path)


def test_capability_change_invalidates_approval(tmp_path, monkeypatch, draft):
    (tmp_path / "manual.md").write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    write_json(tmp_path / "draft.json", draft.model_dump(mode="json"))
    write_json(tmp_path / "capability_profile.json", CAPABILITY)
    monkeypatch.setattr(phase1, "settings", lambda: CONFIG)
    phase1.review(tmp_path, input_fn=lambda prompt: "approve")
    write_json(tmp_path / "capability_profile.json", dict(CAPABILITY, recommended_concurrency=5))
    with pytest.raises(ValueError, match="审批已失效"):
        phase1.require_approved(tmp_path)


def test_distribution_changes_need_explicit_human_override(tmp_path, monkeypatch, draft):
    draft.personas[0].participation = "lurker"
    (tmp_path / "manual.md").write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    write_json(tmp_path / "draft.json", draft.model_dump(mode="json"))
    write_json(tmp_path / "capability_profile.json", CAPABILITY)
    monkeypatch.setattr(phase1, "settings", lambda: CONFIG)
    commands = iter(["approve", "quit"])
    phase1.review(tmp_path, input_fn=lambda prompt: next(commands))
    assert not (tmp_path / "approval.json").exists()
    phase1.review(tmp_path, input_fn=lambda prompt: "approve overrides")
    assert phase1.require_approved(tmp_path)[0].personas[0].participation == "lurker"


def test_review_does_not_approve_an_unseen_edit(tmp_path, monkeypatch, draft):
    (tmp_path / "manual.md").write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    write_json(tmp_path / "draft.json", draft.model_dump(mode="json"))
    write_json(tmp_path / "capability_profile.json", CAPABILITY)
    monkeypatch.setattr(phase1, "settings", lambda: CONFIG)
    commands = iter(["approve", "quit"])

    def edit_during_prompt(prompt):
        command = next(commands)
        if command == "approve":
            draft.personas[0].realname = "刚修改的名字"
            write_json(tmp_path / "draft.json", draft.model_dump(mode="json"))
        return command

    phase1.review(tmp_path, input_fn=edit_during_prompt)
    assert not (tmp_path / "approval.json").exists()


def test_json_validation_retry_keeps_schema_and_thinking():
    bodies = []

    def respond(request):
        body = json.loads(request.content)
        bodies.append(body)
        content = '{}' if len(bodies) == 1 else json.dumps({"positioning": "作品展示", "target_users": "招聘方", "features": ["项目列表"], "assumptions": [],
                                                              "target_age_min": None, "target_age_max": None})
        return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 0, "model": "custom",
                                       "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            async with AsyncOpenAI(api_key="test", base_url=CONFIG["base_url"], http_client=transport) as client:
                return await request_json(client, CONFIG, CAPABILITY, ProductSummary, "Extract product")

    assert asyncio.run(run()).positioning == "作品展示"
    assert len(bodies) == 2
    assert all(body["reasoning_effort"] == "none" and body["response_format"]["type"] == "json_schema" for body in bodies)


def test_failed_prompt_json_capability_cannot_be_used_as_fallback():
    capability = dict(CAPABILITY, checks={"json_schema": {"supported": False}, "json_prompt": {"supported": False}})
    with pytest.raises(ValueError, match="未通过 JSON Object 或提示词 JSON"):
        asyncio.run(request_json(None, CONFIG, capability, ProductSummary, "Extract product"))


def test_activity_while_fully_asleep_rejected(draft):
    data = draft.model_dump(mode="json")
    # p01 sleeps 23:50-06:00; 03:00-04:00 lies entirely inside that window.
    data["personas"][0]["schedule"]["activity_by_hour"]["3"] = 0.1
    with pytest.raises(ValidationError, match="asleep"):
        Draft.model_validate(data)
    # The partially awake boundary hour stays allowed.
    data["personas"][0]["schedule"]["activity_by_hour"] = {"12": 0.5, "23": 0.2}
    Draft.model_validate(data)


def test_generated_activity_is_cleared_while_asleep(draft):
    seed = plan_slots(read_manual(SAMPLE))[0].model_dump()
    details = PersonaDetails.model_validate({**draft.personas[0].model_dump(include=set(PersonaDetails.model_fields)),
        "wake": "06:00", "sleep": "23:50", "activity": [{"hour": 2, "probability": 0.05}, {"hour": 21, "probability": 0.9}],
        "state_at_browse": "晚饭后有空", "motivation": "评估作品", "candor": "中", "withhold_reasons": []})
    assert build_persona(details, seed).schedule.activity_by_hour == {21: 0.9}


@pytest.mark.parametrize("state", ["本地时间周六02:10，睡不着", "星期三午休时打开", "周末早上有空", "10月2日晚上"])
def test_state_at_browse_cannot_name_a_calendar_day(draft, state):
    data = draft.model_dump(mode="json")
    data["personas"][0]["schedule"]["state_at_browse"] = state
    with pytest.raises(ValidationError, match="calendar"):
        Draft.model_validate(data)


def test_ages_follow_target_range_and_spread(draft):
    manual = read_manual(SAMPLE)
    draft.personas[0].age = 60
    assert "年龄超出目标用户范围 20–55" in distribution_issues(draft, manual)
    for persona in draft.personas:
        persona.age = 30 + persona.age % 2 * 10
    assert "年龄至少覆盖 3 个年代" in distribution_issues(draft, manual)


def test_schedule_across_timezones_and_dst(draft):
    for index, (zone, slot) in enumerate([("America/Los_Angeles", "08:00"), ("Europe/London", "12:30"), ("Asia/Kolkata", "07:30")]):
        draft.personas[index].timezone = zone
        draft.personas[index].schedule.browse_slot = slot
    # US daylight saving ends on 2026-11-01: the LA slot falls after the switch to UTC-8.
    draft.run_config.start_time = datetime(2026, 11, 1, tzinfo=timezone.utc)
    rows = {row["persona_id"]: (row["local_time"], row["utc_time"], row["slice_index"]) for row in schedule_rows(draft)}
    assert rows["p01"] == ("2026-11-01T08:00:00-08:00", "2026-11-01T16:00:00+00:00", 16)
    assert rows["p02"] == ("2026-11-01T12:30:00+00:00", "2026-11-01T12:30:00+00:00", 12)
    assert rows["p03"] == ("2026-11-01T07:30:00+05:30", "2026-11-01T02:00:00+00:00", 2)


def test_cohort_plan_hard_errors_and_distribution(draft):
    manual = read_manual(SAMPLE)
    slots = plan_slots(manual)
    assert assignment_errors(slots, manual) == [] and cohort_issues(slots, draft.product, manual) == []
    slots[0].account_role = "paid_user"
    slots[1].tech_level = "normal"
    assert assignment_errors(slots, manual) == ["p01 使用了未知账号角色"]
    assert cohort_issues(slots, draft.product, manual) == ["至少 2 名开发者"]


def test_reviewer_cannot_override_assignment_errors(draft):
    draft.personas[0].browsing_profile.account_role = "paid_user"
    with pytest.raises(ValueError, match="未知账号角色"):
        validate_draft(draft, read_manual(SAMPLE), CAPABILITY)


@pytest.mark.parametrize("model_limit,browser_limit", [(1, 1), (3, 1), (2, 5), (10, 1)])
def test_main_agent_plans_cohort_then_slots_fill_in_parallel(monkeypatch, capsys, model_limit, browser_limit):
    manual = read_manual(SAMPLE)
    slots = {slot.persona_id: slot for slot in plan_slots(manual)}
    in_flight, peak, calls = 0, 0, Counter()

    def plan(attempt):
        rows = [slot.model_dump() for slot in slots.values()]
        if attempt == 1:
            rows[1]["tech_level"] = "normal"  # first draft of the matrix misses the developer minimum
            rows[2]["realname"] = rows[0]["realname"]
        return {"rationale": "按目标用户分布", "slots": rows}

    def details(slot, repaired):
        index = int(slot.persona_id[1:])
        # p02 copies p01's username in the parallel round; only the repair sees accepted names.
        username = "user_1" if slot.persona_id == "p02" and not repaired else f"user_{index}"
        night = int(slot.browse_slot[:2]) < 6
        return {"realname": slot.realname, "username": username, "gender": slot.gender, "age": slot.age,
                "city": "上海", "timezone": "Asia/Shanghai", "profession": slot.profession, "industry": "软件", "education": "本科",
                "income_level": "中", "life_context": "在职", "product_history": "未使用过", "bio": "合成测试角色", "persona": "评估作品",
                "mbti": "INTJ", "big_five": {key: "中" for key in ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]},
                "communication_style": "直接", "interested_topics": ["项目交付"], "wake": "10:00" if night else "06:00",
                "sleep": "03:00" if night else "23:50", "activity": [{"hour": 12, "probability": 0.5}], "state_at_browse": "有空",
                "motivation": "评估作品", "candor": "中", "withhold_reasons": ["怕显得不懂技术"]}

    async def respond(request):
        nonlocal in_flight, peak
        body = json.loads(request.content)
        name = body["response_format"]["json_schema"]["name"]
        attempt = (len(body["messages"]) - 2) // 2 + 1
        if name == "ProductSummary":
            content = PRODUCT
        elif name == "CohortPlan":
            content = plan(attempt)
        else:
            prompt = body["messages"][1]["content"]
            payload = json.loads(prompt[prompt.index("\n") + 1:prompt.index("\n输出 schema")])
            slot = slots[payload["seed"]["persona_id"]]
            calls[slot.persona_id] += 1
            content = details(slot, bool(payload["previous"]))
            if slot.persona_id == "p03" and attempt == 1:
                content = dict(content, age=slot.age + 1)
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, json={"id": "t", "object": "chat.completion", "created": 0, "model": "custom", "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(content, ensure_ascii=False)}}]})

    real_client = AsyncOpenAI

    def client(**kwargs):
        return real_client(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))

    monkeypatch.setattr(personas, "AsyncOpenAI", client)
    config = dict(CONFIG, max_model_concurrency=model_limit, max_browser_concurrency=browser_limit)
    draft = asyncio.run(personas.generate_draft(config, CAPABILITY, manual))
    output = capsys.readouterr().out
    assert draft.cohort_rationale == "按目标用户分布"
    assert [(p.gender, p.age, p.browsing_profile.motivation) for p in draft.personas] == [
        (s.gender, s.age, s.motivation) for s in slots.values()]
    assert len({p.username for p in draft.personas}) == 10 and draft.personas[1].username == "user_2"
    assert peak == model_limit and calls["p02"] == 2 and calls["p03"] == 2
    assert draft.run_config.max_concurrency == min(model_limit, browser_limit)
    assert "维度矩阵 第 1 次不合法" in output and "至少 2 名开发者" in output and "姓名不能重复" in output and "维度矩阵 第 2 次通过" in output
    assert "Persona p03 第 1 次不合法" in output and "realname/profession/gender/age 必须与维度矩阵一致" in output
    assert "Persona p02 需重新生成：username 与已有角色重复" in output


def test_review_counts_distribution_from_draft(tmp_path, monkeypatch, draft):
    (tmp_path / "manual.md").write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    write_json(tmp_path / "draft.json", draft.model_dump(mode="json"))
    write_json(tmp_path / "capability_profile.json", CAPABILITY)
    phase1.review(tmp_path, input_fn=lambda prompt: "quit")
    text = (tmp_path / "review.md").read_text(encoding="utf-8")
    assert "测试分布" in text and "- 性别：女 5，男 5" in text and "- 时段：午 2，早 3，晚 3，深夜 2" in text


def test_known_issues_never_reach_generation_prompts(tmp_path, monkeypatch):
    # The calibration set must not prime personas, whose text later enters the browsing prompt.
    sentinel = "校准哨兵：导出按钮藏在二级菜单"
    text = SAMPLE.read_text(encoding="utf-8")
    start = text.index("# 已知问题")
    end = text.index("\n# ", start + 1)
    path = tmp_path / "manual.md"
    path.write_text(text[:start] + "# 已知问题\n\n" + sentinel + "\n" + text[end:], encoding="utf-8")
    manual = read_manual(path)
    assert sentinel in manual["source"]
    slots = plan_slots(manual)
    prompts = []

    async def fake(client, config, capability, schema, prompt, validate=None, label=None, **kwargs):
        prompts.append(prompt)
        if schema is ProductSummary:
            return ProductSummary.model_validate(PRODUCT)
        if schema.__name__ == "CohortPlan":
            return schema.model_validate({"rationale": "按目标用户分布", "slots": [slot.model_dump() for slot in slots]})
        seed = json.loads(prompt[prompt.index("\n") + 1:])["seed"]
        night = int(seed["browse_slot"][:2]) < 6
        return PersonaDetails.model_validate({
            "realname": seed["realname"], "username": "u_" + seed["persona_id"], "gender": seed["gender"], "age": seed["age"],
            "city": "上海", "timezone": "Asia/Shanghai", "profession": seed["profession"], "industry": "软件", "education": "本科",
            "income_level": "中", "life_context": "在职", "product_history": "未使用过", "bio": "合成测试角色", "persona": "评估作品",
            "mbti": "INTJ", "big_five": {key: "中" for key in ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]},
            "communication_style": "直接", "interested_topics": ["项目交付"], "wake": "10:00" if night else "06:00",
            "sleep": "03:00" if night else "23:50", "activity": [{"hour": 12, "probability": 0.5}], "state_at_browse": "有空",
            "motivation": "评估作品", "candor": "中", "withhold_reasons": ["怕显得不懂技术"]})

    monkeypatch.setattr(personas, "request_json", fake)
    asyncio.run(personas.generate_draft(dict(CONFIG, max_model_concurrency=2, max_browser_concurrency=1), CAPABILITY, manual))
    assert len(prompts) == 12
    assert all(sentinel not in prompt and "已知问题" not in prompt for prompt in prompts)
    assert all(manual["sections"]["产品定位"][:20] in prompt for prompt in prompts)
