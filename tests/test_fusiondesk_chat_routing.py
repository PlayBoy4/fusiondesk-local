import time
from pathlib import Path

from dashboard.server import chat, fusiondesk_chat, is_fusiondesk_chat, route_chat, seat_assignment


class FakeExecutionEngine:
    def execute(self, *, task, plan, memory_context=None):
        self.memory_context = memory_context or {}
        return {
            "ok": True,
            "message": f"Executed: {task}",
            "execution": {
                "connector": "openrouter",
                "model": plan["seat_assignments"][0]["model"],
                "attempts": [{"connector": "openrouter", "model": plan["seat_assignments"][0]["model"], "ok": True}],
                "fallback_used": False,
            },
        }


def mock_execution(monkeypatch):
    monkeypatch.setattr("dashboard.server.ExecutionEngine.load", lambda: FakeExecutionEngine())


def test_detects_use_fusiondesk_prefix():
    assert is_fusiondesk_chat("Use FusionDesk research competitors")
    assert is_fusiondesk_chat("use fusiondesk: make a marketing plan")
    assert is_fusiondesk_chat("please assign seats for this research task")
    assert is_fusiondesk_chat("TradeMaster risk review")
    assert is_fusiondesk_chat("build a marketing campaign for a daycare")
    assert is_fusiondesk_chat("what should FusionDesk do here")
    assert not is_fusiondesk_chat("research competitors")


def test_normal_hello_routes_to_qwen_when_enabled(monkeypatch):
    calls = []

    def fake_chat(prompt, history):
        calls.append((prompt, history))
        return {"ok": True, "message": "hello", "route": "local_model"}

    monkeypatch.setattr("dashboard.server.DEFAULT_CHAT_ROUTE", "qwen")
    monkeypatch.setattr("dashboard.server.LOCAL_CHAT_ENABLED", True)
    monkeypatch.setattr("dashboard.server.chat", fake_chat)

    result = route_chat("hello", [])

    assert result["route"] == "local_model"
    assert calls == [("hello", [])]


def test_plain_chat_disabled(monkeypatch):
    def fail_if_qwen_called(prompt, history):
        raise AssertionError("Disabled plain chat called local_model_generation")

    monkeypatch.setattr("dashboard.server.DEFAULT_CHAT_ROUTE", "qwen")
    monkeypatch.setattr("dashboard.server.LOCAL_CHAT_ENABLED", False)
    monkeypatch.setattr("dashboard.server.chat", fail_if_qwen_called)

    result = route_chat("hello", [])

    assert result["ok"] is False
    assert result["message"] == "Local chat is disabled. Use FusionDesk commands or enable local model."
    assert result["route"] == "disabled"
    assert result["local_model_status"] == "Disabled"


def test_default_route_fusiondesk(monkeypatch):
    def fail_if_qwen_called(prompt, history):
        raise AssertionError("Default FusionDesk route called local_model_generation")

    monkeypatch.setattr("dashboard.server.DEFAULT_CHAT_ROUTE", "fusiondesk")
    monkeypatch.setattr("dashboard.server.LOCAL_CHAT_ENABLED", False)
    monkeypatch.setattr("dashboard.server.chat", fail_if_qwen_called)
    mock_execution(monkeypatch)

    result = route_chat("hello", [])

    assert result["ok"] is True
    assert result["route"] == "fusiondesk"
    assert result["local_model_status"] == "Bypassed"


def test_fusiondesk_chat_returns_without_model_call(monkeypatch):
    mock_execution(monkeypatch)
    result = fusiondesk_chat("Use FusionDesk web research competitor AI dashboards with sources")

    assert result["ok"] is True
    assert result["fusiondesk"]["selected_skill"] == "research.web_research"
    assert "agent_reach" in result["fusiondesk"]["connectors"]
    assert result["message"] == "Executed: web research competitor AI dashboards with sources"
    assert result["execution"]["connector"] == "openrouter"
    assert result["local_model_status"] == "Bypassed"
    assert "memory_context" in result


def test_use_fusiondesk_assign_seats_routes_to_fusiondesk_without_qwen(monkeypatch):
    def fail_if_qwen_called(prompt, history):
        raise AssertionError("FusionDesk route called local_model_generation")

    monkeypatch.setattr("dashboard.server.chat", fail_if_qwen_called)
    mock_execution(monkeypatch)

    result = route_chat("Use FusionDesk to assign seats for a marketing campaign", [])

    assert result["ok"] is True
    assert result["route"] == "fusiondesk"
    assert result["local_model_status"] == "Bypassed"
    assert result["seat_engine_status"] == "Executed"
    assert result["message"] == "Executed: to assign seats for a marketing campaign"


def test_fusiondesk_route_returns_under_one_second(monkeypatch):
    def fail_if_qwen_called(prompt, history):
        raise AssertionError("FusionDesk route called local_model_generation")

    monkeypatch.setattr("dashboard.server.chat", fail_if_qwen_called)
    mock_execution(monkeypatch)

    started = time.perf_counter()
    result = route_chat("assign seats for TradeMaster risk review", [])
    elapsed = time.perf_counter() - started

    assert result["ok"] is True
    assert result["route"] == "fusiondesk"
    assert elapsed < 1


def test_normal_chat_returns_unavailable_when_qwen_offline(monkeypatch):
    monkeypatch.setattr("dashboard.server.health", lambda: {"status": "offline"})

    result = chat("normal local chat", [])

    assert result["ok"] is False
    assert result["message"] == "Local model unavailable at stage: local_model_health"
    assert result["error_stage"] == "local_model_health"
    assert result["local_model_status"] == "Unavailable: local_model_health"
    assert result["seat_engine_status"] == "Bypassed"


def test_qwen_request_timeout_is_30_seconds():
    source = Path("dashboard/server.py").read_text()

    assert "STAGE_TIMEOUT_SECONDS = 30" in source
    assert "urllib.request.urlopen(req, timeout=STAGE_TIMEOUT_SECONDS)" in source


def test_qwen_generation_timeout_reports_exact_stage(monkeypatch):
    def timeout_urlopen(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("dashboard.server.health", lambda: {"status": "ok"})
    monkeypatch.setattr("dashboard.server.urllib.request.urlopen", timeout_urlopen)

    result = chat("normal local chat", [])

    assert result["ok"] is False
    assert result["message"] == "Local Qwen is taking too long. Use FusionDesk commands or try again after restarting the local model."
    assert result["error_stage"] == "local_model_generation"
    assert result["local_model_status"] == "Online but slow"
    assert result["friendly_fallback"] is True


def test_seat_assignment_timeout_reports_exact_stage(monkeypatch):
    def never_returns():
        import time

        time.sleep(0.05)
        return {"selected_skill": "research.web_research"}

    monkeypatch.setattr("dashboard.server.STAGE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr("dashboard.server.SeatAssignmentEngine.load", lambda: type("Engine", (), {"assign": lambda self, **kwargs: never_returns()})())

    result = seat_assignment({"task": "research competitors"})

    assert result["ok"] is False
    assert result["message"] == "Timed out at stage: seat_assignment.engine"
    assert result["error_stage"] == "seat_assignment.engine"


def test_ui_routes_fusiondesk_commands_to_assign_endpoint():
    source = Path("dashboard/static/app.js").read_text()

    assert "isFusionDeskCommand(prompt)" in source
    assert 'fetch("/api/chat/stream"' in source
    assert '"assign seats"' in source
    assert '"trademaster"' in source
