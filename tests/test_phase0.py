"""Regression checks for the gates that prevent unsupported-model runs."""

import asyncio
import json
import re
from types import SimpleNamespace

import pytest

from core.runtime import require_capabilities
from probe import model
from orchestrator import phase0


@pytest.mark.parametrize("unsupported", ["vision", "tools", None])
def test_model_probe_gate_and_json_fallback(tmp_path, monkeypatch, unsupported):
    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def create(self, **kwargs):
            assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
            content = kwargs["messages"][0]["content"]
            calls = None
            if isinstance(content, list):
                answer = "Cannot see images" if unsupported == "vision" else "123 456 789"
            else:
                token = re.search(r"[a-f0-9]{16}", content).group()
                answer = token
                if "response_format" in kwargs:
                    assert kwargs["response_format"] == {"type": "json_object"}
                if "tools" in kwargs and unsupported != "tools":
                    calls = [SimpleNamespace(function=SimpleNamespace(
                        name=tool["function"]["name"], arguments=json.dumps({"token": token})
                    )) for tool in kwargs["tools"]]
                if "JSON" in content:
                    answer = json.dumps({"token": token})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer, tool_calls=calls))], usage=None)

    monkeypatch.setattr(model, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(model, "image_challenge", lambda: ("123 456 789", b"test-image"))
    config = {"provider": "deepseek", "model": "custom", "base_url": "http://test.invalid/v1", "api_key": "test-secret", "thinking_type": "disabled"}
    profile = asyncio.run(model.probe_model(config, tmp_path))
    assert profile["ready"] is (unsupported is None)
    assert profile["structured_output"] == "json_object_with_validation"
    assert profile["checks"]["json_schema"]["status"] == "unsupported"
    assert profile["thinking_type"] == "disabled"
    assert "test-secret" not in (tmp_path / "capability_profile.json").read_text(encoding="utf-8")
    if unsupported:
        with pytest.raises(ValueError):
            require_capabilities(tmp_path, config)
    else:
        assert require_capabilities(tmp_path, config)["ready"]


def test_orchestrator_stops_before_browsing_on_failed_model(tmp_path, monkeypatch):
    calls = []

    def failing_model(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(phase0, "settings", lambda: {
        "base_url": "http://test.invalid/v1", "api_key": "test", "model": "custom", "steel_api_key": "test",
    })
    monkeypatch.setattr(phase0.subprocess, "run", failing_model)
    run_dir = tmp_path / "run"
    monkeypatch.setattr("sys.argv", ["phase0", "--run-dir", str(run_dir)])
    with pytest.raises(SystemExit) as error:
        phase0.main()
    assert error.value.code == 1
    assert len(calls) == 1 and calls[0][2] == "probe.model"
    result = json.loads((run_dir / "phase0_result.json").read_text())
    assert not result["passed"] and set(result["checks"]) == {"model"}


def test_error_log_redacts_credentials(tmp_path):
    from core.runtime import error_summary

    summary = error_summary(ConnectionError("wss://connect.example?sessionId=1&apiKey=sk-live-123 closed"), tmp_path)
    log = (tmp_path / "errors.log").read_text(encoding="utf-8")
    assert summary == {"type": "ConnectionError", "status_code": None}
    assert "sk-live-123" not in log and "apiKey=REDACTED" in log and "Traceback" not in summary


def test_stalled_request_hits_deadline_and_retries(capsys):
    from core.runtime import with_deadline
    calls = []

    async def stalls_once():
        calls.append(1)
        if len(calls) == 1:
            await asyncio.sleep(10)
        return "ok"

    async def always_stalls():
        await asyncio.sleep(10)

    assert asyncio.run(with_deadline(stalls_once, 0.05, "vision_0")) == "ok" and len(calls) == 2
    assert "vision_0 超过 0.05s 未完成，重试（第 2 次）" in capsys.readouterr().out
    with pytest.raises(TimeoutError, match="已尝试 2 次"):
        asyncio.run(with_deadline(always_stalls, 0.05, "vision_1"))
