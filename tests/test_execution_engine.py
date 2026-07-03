from fusiondesk.core.execution import ExecutionEngine, MODEL_PRIORITY, model_registry_for_api, model_status


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


def test_fake_model_ids_are_not_executed():
    plan = {
        **PLAN,
        "seat_assignments": [
            {"seat": "judge", "model": "anthropic/claude-fable-5", "reason": "not verified"},
            {"seat": "strategist", "model": "openai/gpt-5", "reason": "not verified"},
        ],
    }
    connector = SuccessfulConnector()
    engine = ExecutionEngine(connectors={"openrouter": connector})

    result = engine.execute(task="write a campaign", plan=plan)

    assert result["ok"] is True
    assert connector.calls == ["anthropic/claude-sonnet-4"]
    assert "anthropic/claude-fable-5" not in connector.calls
    assert "openai/gpt-5" not in connector.calls
    assert model_status()["skipped_models"] == ["anthropic/claude-fable-5", "openai/gpt-5"]


def test_inactive_models_fall_back_safely():
    plan = {
        **PLAN,
        "seat_assignments": [
            {"seat": "scout", "model": "deepseek-chat", "reason": "needs health check"},
            {"seat": "local", "model": "qwen-local", "reason": "offline"},
            {"seat": "nuclear", "model": "claude-opus", "reason": "needs health check"},
        ],
    }
    connector = SuccessfulConnector()
    engine = ExecutionEngine(connectors={"openrouter": connector})

    result = engine.execute(task="write a campaign", plan=plan)

    assert result["ok"] is True
    assert connector.calls == ["anthropic/claude-sonnet-4"]
    assert set(model_status()["skipped_models"]) == {"deepseek-chat", "qwen-local", "claude-opus"}


def test_active_models_remain_executable_when_requested():
    plan = {
        **PLAN,
        "seat_assignments": [
            {"seat": "reviewer", "model": "gpt-4.1", "reason": "active alias"},
        ],
    }
    connector = FallbackConnector()
    engine = ExecutionEngine(connectors={"openrouter": connector})

    result = engine.execute(task="write a campaign", plan=plan)

    assert result["ok"] is True
    assert result["execution"]["model"] == "openai/gpt-4o"
    assert connector.calls == ["anthropic/claude-sonnet-4", "openai/gpt-4o"]


def test_model_registry_api_shape():
    registry = model_registry_for_api()
    rows = registry["models"]

    assert {"label", "seat", "provider_model", "status", "connector"} <= set(rows[0])
    assert [model for model in registry["fallback_chain"] if model not in MODEL_PRIORITY] == []
    assert any(row["provider_model"] == "anthropic/claude-sonnet-4" and row["status"] == "active" for row in rows)
    assert any(row["provider_model"] == "openai/gpt-5" and row["status"] == "needs_health_check" for row in rows)
    assert any(row["seat"] == "qwen-local" and row["status"] == "offline" for row in rows)
