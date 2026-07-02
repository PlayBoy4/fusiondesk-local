from fusiondesk.core.execution import ExecutionEngine, MODEL_PRIORITY, model_status


PLAN = {
    "task": "write a campaign",
    "selected_skill": "marketing.campaign_planning",
    "mode": "PANEL",
    "connectors": ["openrouter", "agent_reach"],
    "seat_assignments": [
        {"seat": "planner", "model": "claude-sonnet", "reason": "primary"},
        {"seat": "reviewer", "model": "gpt-4.1", "reason": "fallback"},
    ],
    "confidence": 0.9,
    "warnings": [],
}


class SuccessfulConnector:
    def __init__(self):
        self.calls = []

    def generate(self, *, model, messages, timeout):
        self.calls.append(model)
        return f"answer from {model}"

    def stream_generate(self, *, model, messages, timeout):
        yield "answer "
        yield f"from {model}"


class FallbackConnector:
    def __init__(self):
        self.calls = []

    def generate(self, *, model, messages, timeout):
        self.calls.append(model)
        if model == "anthropic/claude-sonnet-4":
            error = RuntimeError("OpenRouter HTTP 404: No endpoints found")
            error.code = 404
            raise error
        return f"answer from {model}"

    def stream_generate(self, *, model, messages, timeout):
        self.calls.append(model)
        if model == "anthropic/claude-sonnet-4":
            error = RuntimeError("OpenRouter HTTP 404: No endpoints found")
            error.code = 404
            raise error
        yield "answer "
        yield f"from {model}"


def test_execution_engine_uses_primary_model_first_without_fallback():
    connector = SuccessfulConnector()
    engine = ExecutionEngine(connectors={"openrouter": connector})

    result = engine.execute(task="write a campaign", plan=PLAN)

    assert result["ok"] is True
    assert result["message"] == "answer from anthropic/claude-sonnet-4"
    assert result["execution"]["model"] == "anthropic/claude-sonnet-4"
    assert result["execution"]["fallback_used"] is False
    assert connector.calls == ["anthropic/claude-sonnet-4"]
    assert model_status()["active_model"] == "anthropic/claude-sonnet-4"


def test_execution_engine_falls_back_only_after_primary_failure():
    connector = FallbackConnector()
    engine = ExecutionEngine(connectors={"openrouter": connector})

    result = engine.execute(task="write a campaign", plan=PLAN)

    assert result["ok"] is True
    assert result["message"] == "answer from openai/gpt-4o"
    assert result["execution"]["model"] == "openai/gpt-4o"
    assert result["execution"]["fallback_used"] is True
    assert connector.calls == ["anthropic/claude-sonnet-4", "openai/gpt-4o"]
    assert model_status()["failed_models"] == ["anthropic/claude-sonnet-4"]
    assert model_status()["fallback_chain"] == ["anthropic/claude-sonnet-4", "openai/gpt-4o"]


def test_execution_engine_streams_tokens_and_falls_back():
    connector = FallbackConnector()
    engine = ExecutionEngine(connectors={"openrouter": connector})

    events = list(engine.execute_stream(task="write a campaign", plan=PLAN))

    assert [event["type"] for event in events] == [
        "start",
        "fallback",
        "start",
        "token",
        "token",
        "done",
    ]
    assert events[-1]["message"] == "answer from openai/gpt-4o"
    assert events[-1]["execution"]["fallback_used"] is True


def test_model_priority_uses_current_openrouter_models():
    assert MODEL_PRIORITY == [
        "anthropic/claude-sonnet-4",
        "openai/gpt-4o",
        "google/gemini-2.5-flash",
        "openai/gpt-4o-mini",
    ]


def test_model_status_shape():
    status = model_status()

    assert status["available_models"] == MODEL_PRIORITY
    assert "active_model" in status
    assert "failed_models" in status
    assert "fallback_chain" in status
