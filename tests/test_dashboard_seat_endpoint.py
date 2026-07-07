from dashboard.server import model_generate_response, seat_assignment


def test_dashboard_seat_assignment_smoke():
    result = seat_assignment(
        {
            "task": "research competitor AI dashboards with sources",
            "skill": "research.web_research",
            "mode": "PANEL",
            "costPreference": "balanced",
            "qualityPreference": "highest_quality",
        }
    )

    assert result["ok"] is True
    assert result["selected_skill"] == "research.web_research"
    assert result["mode"] == "PANEL"
    assert "agent_reach" in result["connectors"]
    assert result["seat_assignments"]
    assert "confidence" in result


def test_dashboard_seat_assignment_rejects_missing_task():
    assert seat_assignment({}) == {"ok": False, "message": "Task is required."}


def test_model_generate_response_uses_requested_openrouter_model(monkeypatch):
    calls = []

    class FakeOpenRouterConnector:
        def generate(self, *, model, messages, timeout):
            calls.append({"model": model, "messages": messages, "timeout": timeout})
            return "OK"

    monkeypatch.setattr("dashboard.server.OpenRouterConnector", FakeOpenRouterConnector)

    result = model_generate_response({"model": "anthropic/claude-fable-5", "prompt": "Say OK"})

    assert result["ok"] is True
    assert result["model"] == "anthropic/claude-fable-5"
    assert result["text"] == "OK"
    assert result["error"] == ""
    assert result["status"] == "ok"
    assert calls[0]["model"] == "anthropic/claude-fable-5"
    assert calls[0]["messages"] == [{"role": "user", "content": "Say OK"}]


def test_model_generate_response_returns_json_error(monkeypatch):
    class FakeOpenRouterConnector:
        def generate(self, *, model, messages, timeout):
            error = RuntimeError("OpenRouter HTTP 404: No endpoints found")
            error.code = 404
            raise error

    monkeypatch.setattr("dashboard.server.OpenRouterConnector", FakeOpenRouterConnector)

    result = model_generate_response({"model": "anthropic/claude-fable-5", "prompt": "Say OK"})

    assert result["ok"] is False
    assert result["model"] == "anthropic/claude-fable-5"
    assert result["text"] == ""
    assert "OpenRouter HTTP 404" in result["error"]
    assert result["status"] == 404
    assert result["raw"] == result["error"]
