import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import ValidationError

from core.persona import Draft, PersonaDetails, ProductSummary, RunConfig
from core.runtime import ROOT, write_json
from orchestrator import phase1
from orchestrator.manual import read_manual
from orchestrator.personas import build_persona, dimension_matrix, distribution_issues, request_json, schedule_rows, validate_draft

SAMPLE = ROOT / "docs/examples/wjm_product_manual.md"
CONFIG = {"model": "custom", "base_url": "https://test.invalid/v1", "api_key": "test", "thinking_type": "disabled"}
CAPABILITY = {"model": "custom", "base_url": CONFIG["base_url"], "thinking_type": "disabled", "ready": True,
              "recommended_concurrency": 10, "checks": {"json_schema": {"supported": True}, "json_prompt": {"supported": False}}}


@pytest.fixture
def draft():
    manual = read_manual(SAMPLE)
    people = []
    for index, seed in enumerate(dimension_matrix(manual)):
        night = int(seed["browse_slot"][:2]) < 6
        details = PersonaDetails.model_validate({
            "realname": f"测试用户{index}", "username": f"test_{index}", "gender": "女" if index % 2 else "男",
            "age": 22 + index * 3, "city": "上海", "timezone": "Asia/Shanghai", "profession": "开发者" if index < 2 else "招聘人员",
            "industry": "软件", "education": "本科", "income_level": "中", "life_context": "在职，利用休息时间评估作品",
            "product_history": "未使用过待测网站，有阅读其他作品的经历", "bio": "合成测试角色", "persona": "根据既有经历评估开发者作品",
            "mbti": "INTJ", "big_five": {key: "中" for key in ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]},
            "communication_style": "直接", "interested_topics": ["项目交付"], "wake": "10:00" if night else "06:00",
            "sleep": "03:00" if night else "23:50", "activity": [{"hour": 12, "probability": 0.5}],
            "state_at_browse": "有明确评估目的", "motivation": "评估作品", "candor": "中", "withhold_reasons": ["怕显得自己不懂技术"],
        })
        people.append(build_persona(details, seed))
    return Draft(product=ProductSummary(positioning="展示开发者作品", target_users="招聘方和合作方", features=["首页介绍", "项目列表"], assumptions=[]),
                 personas=people, run_config=RunConfig(start_time=datetime(2026, 10, 2, tzinfo=timezone.utc), duration_days=1,
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
        read_manual(ROOT / "docs/product_manual_template.md")


def test_invalid_manual_does_not_make_paid_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(phase1, "settings", lambda: pytest.fail("Invalid input must be rejected before configuration/API calls"))
    with pytest.raises(ValueError):
        asyncio.run(phase1.prepare(ROOT / "docs/product_manual_template.md", tmp_path / "run"))
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
    assert phase1.require_approved(tmp_path)[0].personas[0].realname == "测试用户0"
    if edit_manual:
        path = tmp_path / "manual.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n调整关注点\n", encoding="utf-8")
    else:
        data = draft.model_dump(mode="json")
        data["personas"][0]["realname"] = "新名字"
        write_json(tmp_path / "draft.json", data)
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
        content = '{}' if len(bodies) == 1 else json.dumps({"positioning": "作品展示", "target_users": "招聘方", "features": ["项目列表"], "assumptions": []})
        return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 0, "model": "custom",
                                       "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            async with AsyncOpenAI(api_key="test", base_url=CONFIG["base_url"], http_client=transport) as client:
                return await request_json(client, CONFIG, CAPABILITY, ProductSummary, "Extract product")

    assert asyncio.run(run()).positioning == "作品展示"
    assert len(bodies) == 2
    assert all(body["thinking"] == {"type": "disabled"} and body["response_format"]["type"] == "json_schema" for body in bodies)


def test_failed_prompt_json_capability_cannot_be_used_as_fallback():
    capability = dict(CAPABILITY, checks={"json_schema": {"supported": False}, "json_prompt": {"supported": False}})
    with pytest.raises(ValueError, match="未通过提示词 JSON"):
        asyncio.run(request_json(None, CONFIG, capability, ProductSummary, "Extract product"))
