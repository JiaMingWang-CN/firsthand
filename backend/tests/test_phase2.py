import asyncio
from datetime import datetime, timezone
import hashlib
import json
import time
from types import SimpleNamespace

import pytest
from browser_use import ActionResult, Tools
from pydantic import ValidationError

from browsing import experience, policy
from browsing.evidence import EvidenceCollector, redact
from core import limits
from core.experience import ExperienceMemory, Snapshot, load_experience
from orchestrator import phase2
from tests.verify_phase2 import fixture_manual, fixture_persona


@pytest.fixture(autouse=True)
def isolate_slots(tmp_path, monkeypatch):
    monkeypatch.setattr(limits, "LOCK_DIR", tmp_path / "locks")


def snapshot(eid, text="生成清单", seconds=1):
    return Snapshot(evidence_id=eid, url="https://example.com", title="工具", text=text,
        screenshot=f"screenshots/{eid}.png", screenshot_sha256="a" * 64, scroll_x=0, scroll_y=0, video_seconds=seconds)


def memory_data():
    return {"persona_id": "p01", "state_at_browse": "很困", "assignment": {"type": "task", "flow": "生成清单"},
        "expectations": [], "outcome": "abandoned", "reason": "按钮无反馈", "outcome_source": "agent_self_report", "session": {},
        "snapshots": [snapshot("before", seconds=1).model_dump(), snapshot("after", seconds=2).model_dump()],
        "steps": [{"step": 1, "before": "before", "after": "after", "seconds": 1,
                   "actions": [{"click": {"index": 1}}], "results": [], "agent_observation": "按钮没有反馈", "stalled": True}],
        "observed_technical_events": [], "infrastructure_errors": [],
        "assessment": {"emotions": [{"step": 1, "satisfaction": 1, "confusion": 4, "reason": "没有反馈"}],
            "findings": [{"kind": "pain", "title": "没有反馈", "description": "点按钮后页面未变",
                          "evidence_ids": ["before", "after"], "technical_event_ids": [], "observed_quote": "生成清单"}], "summary": "放弃"}}


def test_valid_private_memory_retains_lurker_pain():
    memory = ExperienceMemory.model_validate(memory_data())
    assert memory.assessment.findings[0].kind == "pain"


@pytest.mark.parametrize("mutation", ["missing_snapshot", "invented_quote", "missing_emotion", "technical_leak", "reverse_time", "escape_path"])
def test_invalid_evidence_is_rejected(mutation):
    data = memory_data()
    if mutation == "missing_snapshot":
        data["assessment"]["findings"][0]["evidence_ids"] = ["invented"]
    elif mutation == "invented_quote":
        data["assessment"]["findings"][0]["observed_quote"] = "并不存在的产品错误"
    elif mutation == "missing_emotion":
        data["assessment"]["emotions"] = []
    elif mutation == "technical_leak":
        data["assessment"]["findings"][0]["technical_event_ids"] = ["t00001"]
    elif mutation == "reverse_time":
        data["snapshots"][1]["video_seconds"] = 0
    else:
        data["snapshots"][0]["screenshot"] = "../secret.png"
    with pytest.raises(ValidationError):
        ExperienceMemory.model_validate(data)


class FakeCollector:
    secrets = ["secret-value"]

    def __init__(self, text="生成清单"):
        self.text, self.events = text, []

    async def snapshot(self, persona, eid):
        return snapshot(eid, self.text)

    def record(self, event, data):
        self.events.append({"event": event, "data": data})

    def console(self):
        return [{"event_id": "t00001", "data": {"message": "formatter unavailable"}}]

    def failed_requests(self):
        return []


class FakeHistory:
    def __init__(self):
        self.history = []

    def is_done(self):
        return False


def action(values):
    return SimpleNamespace(model_dump=lambda **kwargs: values)


def record_action(agent, values):
    agent.history.history.append(SimpleNamespace(model_output=SimpleNamespace(action=[action(values)], evaluation_previous_goal="无反馈"), result=[]))


def test_stall_limit_stops_repeated_failed_interactions():
    persona = fixture_persona(False)
    collector = FakeCollector()
    recorder = experience.StepRecorder(collector, persona)
    agent = SimpleNamespace(history=FakeHistory(), state=SimpleNamespace(stopped=False, last_result=[]))

    async def run():
        for _ in range(10):
            await recorder.before(agent)
            record_action(agent, {"click": {"index": 1}})
            await recorder.after(agent)
            if await recorder.should_stop():
                break
    asyncio.run(run())
    assert len(recorder.steps) == 2 and agent.state.stopped
    assert "stall_limit" in recorder.stop_reason
    assert sum(event["event"] == "experience_step" for event in collector.events) == 2


def test_policy_denial_does_not_count_as_consecutive_failure():
    # Browser Use counts every single-action error; a rule denial is a coverage limit, not a model/browser failure.
    recorder = experience.StepRecorder(FakeCollector(), fixture_persona(False))
    agent = SimpleNamespace(history=FakeHistory(), state=SimpleNamespace(stopped=False, last_result=[], consecutive_failures=0))
    async def step(error):
        await recorder.before(agent)
        agent.state.consecutive_failures += 1
        agent.history.history.append(SimpleNamespace(result=[ActionResult(error=error)],
            model_output=SimpleNamespace(action=[action({"click": {"index": 1}})], evaluation_previous_goal="")))
        await recorder.after(agent)
    async def run():
        await step("Model output was truncated")
        await step(policy.DENIED_PREFIX + "禁止外发消息")
    asyncio.run(run())
    assert agent.state.consecutive_failures == 1


def test_click_check_sees_text_typed_on_the_same_page(monkeypatch):
    tools = policy.GuardedTools(fixture_persona(False), fixture_manual(), FakeCollector(), None, {}, {}, experience.Completion)
    prompts = []
    async def forward(*args, **kwargs):
        return ActionResult(extracted_content="ok")
    async def decide(client, config, capability, schema, prompt, **kwargs):
        prompts.append(prompt)
        return policy.ActionDecision(allowed=True, reason="站内问答")
    page = {"url": "https://example.com/contact"}
    async def url():
        return page["url"]
    async def node(index):
        return SimpleNamespace(node_name="TEXTAREA" if index == 1 else "BUTTON", attributes={},
                               get_all_children_text=lambda: "发送", parent_node=None)
    monkeypatch.setattr(Tools, "act", forward)
    monkeypatch.setattr(policy, "request_json", decide)
    session = SimpleNamespace(get_current_page_url=url, get_dom_element_by_index=node)
    async def run():
        await tools.act(action({"input": {"index": 1, "text": "这个项目怎么部署？"}}), session)
        await tools.act(action({"click": {"index": 2}}), session)
        page["url"] = "https://example.com/other"
        await tools.act(action({"click": {"index": 2}}), session)
    asyncio.run(run())
    assert "这个项目怎么部署？" in prompts[1] and "这个项目怎么部署？" not in prompts[2]


def test_new_page_state_and_first_technical_read_count_as_progress():
    collector = FakeCollector()
    recorder = experience.StepRecorder(collector, fixture_persona(True))
    agent = SimpleNamespace(history=FakeHistory(), state=SimpleNamespace(stopped=False, last_result=[]))
    async def run():
        await recorder.before(agent)
        record_action(agent, {"read_console": {}})
        await recorder.after(agent)
        assert recorder.stalls == 0
        await recorder.before(agent)
        record_action(agent, {"read_console": {}})
        await recorder.after(agent)
        assert recorder.stalls == 1
        await recorder.before(agent)
        collector.text = "清单已生成"
        record_action(agent, {"click": {"index": 2}})
        await recorder.after(agent)
        assert recorder.stalls == 0
    asyncio.run(run())


def test_captcha_requests_stop_before_actions():
    collector = FakeCollector("Verify you are human")
    recorder = experience.StepRecorder(collector, fixture_persona(False))
    agent = SimpleNamespace(history=FakeHistory())
    asyncio.run(recorder.before(agent))
    assert asyncio.run(recorder.should_stop())
    assert collector.events[0]["event"] == "captcha_detected"


@pytest.mark.parametrize("developer", [False, True])
def test_technical_tools_enforce_persona_permission(developer):
    tools = policy.GuardedTools(fixture_persona(developer), fixture_manual(), FakeCollector(), None, {}, {}, experience.Completion)
    assert ("read_console" in tools.registry.registry.actions) is developer
    assert ("list_failed_requests" in tools.registry.registry.actions) is developer
    assert not {"evaluate", "upload_file", "write_file", "search", "send_keys"} & tools.registry.registry.actions.keys()
    result = tools.technical_result("read_console", FakeCollector().console())
    assert bool(result.error) is (not developer)
    assert bool(tools.observed_technical_events) is developer


@pytest.mark.parametrize("operation", [{"navigate": {"url": "https://example.com.attacker.invalid"}},
    {"navigate": {"url": "javascript:alert(1)"}}, {"evaluate": {"code": "fetch('/pay')"}},
    {"click": {"coordinate_x": 5, "coordinate_y": 5}}, {"read_console": {}}])
def test_disallowed_operations_never_reach_browser(monkeypatch, operation):
    tools = policy.GuardedTools(fixture_persona(False), fixture_manual(), FakeCollector(), None, {}, {}, experience.Completion)
    async def url():
        return "https://example.com"
    async def forbidden(*args, **kwargs):
        pytest.fail("Operation must be blocked before browser execution")
    monkeypatch.setattr(Tools, "act", forbidden)
    result = asyncio.run(tools.act(action(operation), SimpleNamespace(get_current_page_url=url)))
    assert result.error and tools.collector.events[-1]["event"] == "action_blocked"


@pytest.mark.parametrize("decision", [False, "unavailable", True])
def test_natural_language_forbidden_rule_is_checked_before_click(monkeypatch, decision):
    collector = FakeCollector()
    tools = policy.GuardedTools(fixture_persona(False), fixture_manual(), collector, None, {}, {}, experience.Completion)
    calls = []
    async def forward(*args, **kwargs):
        calls.append(1)
        return ActionResult(extracted_content="clicked")
    async def decide(*args, **kwargs):
        if decision == "unavailable":
            raise TimeoutError
        return policy.ActionDecision(allowed=decision, reason="禁止外发消息" if not decision else "站内普通按钮")
    async def url():
        return "https://example.com"
    async def node(index):
        return SimpleNamespace(node_name="BUTTON", attributes={}, get_all_children_text=lambda: "生成清单", parent_node=None)
    monkeypatch.setattr(Tools, "act", forward)
    monkeypatch.setattr(policy, "request_json", decide)
    result = asyncio.run(tools.act(action({"click": {"index": 1}}), SimpleNamespace(get_current_page_url=url, get_dom_element_by_index=node)))
    assert bool(calls) is (decision is True)
    assert bool(result.error) is (decision is not True)


@pytest.mark.parametrize("operation,tag,attributes,parent", [
    ({"navigate": {"url": "https://example.com/projects"}}, None, {}, None),
    ({"navigate": {"url": "https://example.com/account/delete?confirm=1"}}, None, {}, None),
    ({"click": {"index": 1}}, "A", {"href": "/projects"}, None),
    ({"click": {"index": 1}}, "A", {"href": "/account/delete?confirm=1"}, None),
    ({"click": {"index": 1}}, "A", {"href": "#send"}, None),
    ({"click": {"index": 1}}, "A", {"href": "/next"}, "FORM"),
    ({"click": {"index": 1}}, "BUTTON", {}, None),
    ({"input": {"index": 1, "text": "hello"}}, "INPUT", {}, None)])
@pytest.mark.parametrize("allowed", [True, False])
def test_every_navigation_and_click_passes_the_model_rule_check(monkeypatch, operation, tag, attributes, parent, allowed):
    # In-domain GET links and script-handled anchors can still delete or change data.
    collector = FakeCollector()
    tools = policy.GuardedTools(fixture_persona(False), fixture_manual(), collector, None, {}, {}, experience.Completion)
    prompts, executed = [], []
    async def forward(*args, **kwargs):
        executed.append(1)
        return ActionResult(extracted_content="ok")
    async def decide(client, config, capability, schema, prompt, **kwargs):
        prompts.append(prompt)
        return policy.ActionDecision(allowed=allowed, reason="站内操作" if allowed else "删除账号属于禁止操作")
    async def url():
        return "https://example.com"
    form = SimpleNamespace(node_name=parent, attributes={}, get_all_children_text=lambda: "表单", parent_node=None) if parent else None
    async def node(index):
        return SimpleNamespace(node_name=tag, attributes=attributes, get_all_children_text=lambda: "链接", parent_node=form)
    monkeypatch.setattr(Tools, "act", forward)
    monkeypatch.setattr(policy, "request_json", decide)
    result = asyncio.run(tools.act(action(operation), SimpleNamespace(get_current_page_url=url, get_dom_element_by_index=node)))
    assert len(prompts) == 1 and bool(executed) is allowed and bool(result.error) is (not allowed)
    target = operation.get("navigate", {}).get("url") or attributes.get("href")
    assert not target or target in prompts[0]
    assert not any(event["event"] == "action_auto_allowed" for event in collector.events)


@pytest.mark.parametrize("parent_tag,attributes", [("A", {"href": "https://outside.invalid"}),
                                                  ("FORM", {"action": "https://outside.invalid"})])
def test_ancestor_links_and_external_forms_are_denied_before_policy_or_browser(monkeypatch, parent_tag, attributes):
    tools = policy.GuardedTools(fixture_persona(False), fixture_manual(), FakeCollector(), None, {}, {}, experience.Completion)
    async def forbidden(*args, **kwargs):
        pytest.fail("An external link/form must be rejected before a model request or browser action")
    async def url():
        return "https://example.com"
    parent = SimpleNamespace(node_name=parent_tag, attributes=attributes, get_all_children_text=lambda: "Continue", parent_node=None)
    async def node(index):
        return SimpleNamespace(node_name="BUTTON", attributes={}, get_all_children_text=lambda: "Continue", parent_node=parent)
    monkeypatch.setattr(Tools, "act", forbidden)
    monkeypatch.setattr(policy, "request_json", forbidden)
    result = asyncio.run(tools.act(action({"click": {"index": 1}}), SimpleNamespace(get_current_page_url=url, get_dom_element_by_index=node)))
    assert result.error and tools.collector.events[-1]["event"] == "action_blocked"


def test_each_step_reuses_previous_after_snapshot_as_before_state():
    collector = FakeCollector()
    taken = []
    original = collector.snapshot
    async def snapshot(persona, eid):
        taken.append(eid)
        return await original(persona, eid)
    collector.snapshot = snapshot
    recorder = experience.StepRecorder(collector, fixture_persona(True))
    agent = SimpleNamespace(history=FakeHistory(), state=SimpleNamespace(stopped=False, last_result=[]))
    async def run():
        for index in range(3):
            await recorder.before(agent)
            collector.text = f"页面 {index}"
            record_action(agent, {"click": {"index": index}})
            await recorder.after(agent)
    asyncio.run(run())
    assert taken == ["s001_before", "s001_after", "s002_after", "s003_after"]
    assert [(step.before, step.after) for step in recorder.steps] == [
        ("s001_before", "s001_after"), ("s001_after", "s002_after"), ("s002_after", "s003_after")]


def test_redaction_removes_account_and_transport_secrets():
    data = {"headers": {"Authorization": "Bearer key", "Cookie": "session=abc"}, "postData": "password=secret",
            "url": "https://example.com?token=another-key", "message": "secret-value"}
    output = json.dumps(redact(data, ["secret-value"]))
    assert all(secret not in output for secret in ["Bearer key", "session=abc", "another-key", "secret-value", "password=secret"])


def test_credentials_are_domain_scoped_and_not_in_persona_prompt(monkeypatch):
    persona = fixture_persona(False).model_copy(deep=True)
    persona.browsing_profile.account_role = "free_user"
    manual = fixture_manual()
    from core.persona import TestAccount
    manual["metadata"].test_accounts.append(TestAccount(role="free_user", description="测试账号"))
    manual["flows"][0].account_role = "free_user"
    monkeypatch.setenv("TEST_ACCOUNT_FREE_USER_USERNAME", "private-user")
    monkeypatch.setenv("TEST_ACCOUNT_FREE_USER_PASSWORD", "private-password")
    scoped, secrets = policy.account_secrets(persona, manual)
    assert scoped == {"https://example.com": {"test_username": "private-user", "test_password": "private-password"}}
    prompt = experience.task_prompt(persona, manual, [])
    assert all(secret not in prompt for secret in secrets)
    assert "formatter unavailable" not in prompt


def test_approval_gate_precedes_configuration_and_browser_calls(tmp_path, monkeypatch):
    def unapproved(path):
        raise ValueError("Persona 和配置尚未通过人工审核")
    def no_config():
        pytest.fail("Unapproved cohort must not reach configuration or model calls")
    monkeypatch.setattr(phase2, "require_approved", unapproved)
    monkeypatch.setattr(phase2, "settings", no_config)
    with pytest.raises(ValueError, match="尚未通过人工审核"):
        asyncio.run(phase2.execute(tmp_path / "draft", "p01", tmp_path / "experience"))
    assert not (tmp_path / "experience").exists()


def test_approved_entry_runs_selected_persona_and_records_approval_provenance(tmp_path, monkeypatch):
    personas = [fixture_persona(False), fixture_persona(True)]
    manual = fixture_manual()
    capability = {"ready": True}
    config = {"provider": "deepseek"}
    calls = []
    async def run(config_arg, capability_arg, manual_arg, persona_arg, output):
        calls.append((config_arg, capability_arg, manual_arg, persona_arg, output))
        return {"passed": True, "persona_id": persona_arg.persona_id}
    monkeypatch.setattr(phase2, "require_approved", lambda source: (SimpleNamespace(personas=personas), manual))
    monkeypatch.setattr(phase2, "settings", lambda: config)
    monkeypatch.setattr(phase2, "require_capabilities", lambda source, config: capability)
    monkeypatch.setattr(phase2, "draft_hash", lambda source: "approved-draft-hash")
    monkeypatch.setattr(experience, "run_experience", run)
    output = tmp_path / "experience"
    assert asyncio.run(phase2.execute(tmp_path / "source", "p02", output))["passed"]
    assert calls == [(config, capability, manual, personas[1], output)]
    result = json.loads((output / "phase2_result.json").read_text(encoding="utf-8"))
    assert result["approved_draft_sha256"] == "approved-draft-hash" and result["persona_id"] == "p02"


def test_saved_memory_detects_missing_or_altered_screenshot(tmp_path):
    data = memory_data()
    (tmp_path / "screenshots").mkdir()
    for item in data["snapshots"]:
        (tmp_path / item["screenshot"]).write_bytes(b"image evidence")
        item["screenshot_sha256"] = hashlib.sha256(b"image evidence").hexdigest()
    (tmp_path / "experience.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert load_experience(tmp_path).persona_id == "p01"
    (tmp_path / data["snapshots"][0]["screenshot"]).write_bytes(b"altered evidence")
    with pytest.raises(ValueError, match="missing or changed"):
        load_experience(tmp_path)


def test_collector_refuses_to_replace_browser_use_handler(tmp_path):
    collector = EvidenceCollector(SimpleNamespace(cdp_client=SimpleNamespace(_event_registry=SimpleNamespace(
        get_registered_methods=lambda: ["Network.requestWillBeSent"]))), tmp_path, 0)
    try:
        with pytest.raises(RuntimeError, match="already owned"):
            asyncio.run(collector.attach())
    finally:
        collector.close()


@pytest.mark.parametrize("cancelled", [False, True])
def test_session_released_and_partial_memory_saved_on_failure(tmp_path, monkeypatch, cancelled):
    releases = []
    class Steel:
        def __init__(self, **kwargs):
            self.sessions = self
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def create(self, **kwargs):
            return SimpleNamespace(id="session", websocket_url="wss://test.invalid", session_viewer_url="https://viewer.invalid",
                                   created_at=datetime.now(timezone.utc))
        async def release(self, sid):
            releases.append(sid)
    class Browser:
        def __init__(self, **kwargs):
            pass
        async def start(self):
            raise asyncio.CancelledError if cancelled else ConnectionError("CDP disconnected")
        async def kill(self):
            pass
    monkeypatch.setattr(experience, "AsyncSteel", Steel)
    monkeypatch.setattr(experience, "BrowserSession", Browser)
    monkeypatch.setattr(experience, "error_summary", lambda error, path: {"type": type(error).__name__})
    config = {"provider": "deepseek", "model": "custom", "base_url": "https://test.invalid/v1", "api_key": "test",
              "steel_api_key": "test", "api": "responses", "thinking_type": "disabled"}
    output = tmp_path / "experience"
    coroutine = experience.run_experience(config, {}, fixture_manual(), fixture_persona(False), output)
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(coroutine)
    else:
        assert not asyncio.run(coroutine)["passed"]
    assert releases == ["session"]
    memory = ExperienceMemory.model_validate_json((output / "experience.json").read_text(encoding="utf-8"))
    assert memory.assessment is None and not memory.steps
    assert memory.outcome == ("abandoned" if cancelled else "failed")


def test_late_cdp_reply_is_counted_and_its_cancelled_request_is_named(tmp_path):
    import logging
    import browser_use  # noqa: F401 - applies Browser Use's logging setup, where cdp_use.client does not propagate
    from websockets.exceptions import ConnectionClosed
    from cdp_use.client import CDPClient
    from browsing.probe import LogCounter

    class LateSocket:
        def __init__(self):
            self.sent, self.cancelled = [], asyncio.Event()
            self.replies = 0

        async def send(self, message):
            self.sent.append(json.loads(message))

        async def recv(self):
            await self.cancelled.wait()
            self.replies += 1
            if self.replies == 1:
                return json.dumps({"id": self.sent[0]["id"], "result": {}})
            raise ConnectionClosed(None, None)

    async def run():
        client = CDPClient("ws://test.invalid")
        client.ws = socket = LateSocket()
        collector = EvidenceCollector(SimpleNamespace(cdp_client=client), tmp_path, time.monotonic())
        counter = LogCounter()
        counter.attach()
        try:
            await collector.attach()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(client.send.Page.captureScreenshot(params={}), 0.01)
            socket.cancelled.set()
            await client._handle_messages()
        finally:
            counter.detach()
            collector.close()
        return counter, collector
    counter, collector = asyncio.run(run())
    assert counter.late_cdp_responses == 1
    cancelled = [item for item in collector.events if item["event"] == "cdp_request_cancelled"]
    assert [item["data"]["method"] for item in cancelled] == ["Page.captureScreenshot"]


def test_dropped_accessibility_tree_marks_only_the_affected_step():
    import logging
    from browsing.probe import LogCounter
    counter = LogCounter()
    collector = FakeCollector()
    recorder = experience.StepRecorder(collector, fixture_persona(True), counter)
    agent = SimpleNamespace(history=FakeHistory(), state=SimpleNamespace(stopped=False, last_result=[]))
    async def run():
        for index in range(3):
            await recorder.before(agent)
            if index == 1:
                counter.emit(logging.LogRecord("browser_use", logging.WARNING, "", 0, "CDP request ax_tree timed out", (), None))
            collector.text = f"页面 {index}"
            record_action(agent, {"click": {"index": index}})
            await recorder.after(agent)
    asyncio.run(run())
    assert [step.page_structure_degraded for step in recorder.steps] == [False, True, False]
    assert counter.dom_failures == 0 and counter.ax_tree_dropped == 1

