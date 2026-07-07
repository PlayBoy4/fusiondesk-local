from fusiondesk.core.execution import ExecutionEngine, MODEL_PRIORITY, model_orchestrator_metrics, model_registry_for_api, model_status


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
        if model == "openai/gpt-4o-mini":
            error = RuntimeError("OpenRouter HTTP 404: No endpoints found")
            error.code = 404
            raise error
        return f"answer from {model}"

    def stream_generate(self, *, model, messages, timeout):
        self.calls.append(model)
        if model == "openai/gpt-4o-mini":
            error = RuntimeError("OpenRouter HTTP 404: No endpoints found")
            error.code = 404
            raise error
        yield "answer "
        yield f"from {model}"


class MultiFailureConnector:
    def __init__(self):
        self.calls = []

    def generate(self, *, model, messages, timeout):
        self.calls.append(model)
        if model == "openai/gpt-4o-mini":
            error = RuntimeError("OpenRouter HTTP 429: rate limited")
            error.code = 429
            raise error
        if model == "google/gemini-2.0-flash-001":
            error = TimeoutError("timed out")
            error.code = "timeout"
            raise error
        return f"answer from {model}"

    def stream_generate(self, *, model, messages, timeout):
        yield from ()


def test_execution_engine_uses_primary_model_first_without_fallback():
    connector = SuccessfulConnector()
    engine = ExecutionEngine(connectors={"openrouter": connector})

    result = engine.execute(task="write a campaign", plan=PLAN)

    assert result["ok"] is True
    assert result["message"] == "answer from openai/gpt-4o-mini"
    assert result["execution"]["model"] == "openai/gpt-4o-mini"
    assert result["execution"]["fallback_used"] is False
    assert connector.calls == ["openai/gpt-4o-mini"]
    assert model_status()["active_model"] == "openai/gpt-4o-mini"


def test_execution_engine_falls_back_only_after_primary_failure():
    connector = FallbackConnector()
    engine = ExecutionEngine(connectors={"openrouter": connector})

    result = engine.execute(task="write a campaign", plan=PLAN)

    assert result["ok"] is True
    assert result["message"] == "answer from google/gemini-2.0-flash-001"
    assert result["execution"]["model"] == "google/gemini-2.0-flash-001"
    assert result["execution"]["fallback_used"] is True
    assert connector.calls == ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"]
    assert model_status()["failed_models"] == ["openai/gpt-4o-mini"]
    assert model_status()["fallback_chain"] == ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"]


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
    assert events[-1]["message"] == "answer from google/gemini-2.0-flash-001"
    assert events[-1]["execution"]["fallback_used"] is True


def test_execution_engine_fails_over_on_429_and_timeout():
    connector = MultiFailureConnector()
    engine = ExecutionEngine(connectors={"openrouter": connector})

    result = engine.execute(task="write a campaign", plan=PLAN)

    assert result["ok"] is True
    assert result["execution"]["model"] == "deepseek/deepseek-chat"
    assert connector.calls == [
        "openai/gpt-4o-mini",
        "google/gemini-2.0-flash-001",
        "deepseek/deepseek-chat",
    ]
    assert model_status()["failed_models"] == ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"]


def test_model_priority_uses_current_openrouter_models():
    assert MODEL_PRIORITY == [
        "openai/gpt-4o-mini",
        "google/gemini-2.0-flash-001",
        "deepseek/deepseek-chat",
        "anthropic/claude-3.5-sonnet:beta",
    ]


def test_model_status_shape():
    status = model_status()

    assert status["available_models"] == MODEL_PRIORITY
    assert "active_model" in status
    assert "failed_models" in status
    assert "fallback_chain" in status
    assert "last_execution" in status
    assert "models" in status


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
    assert connector.calls == ["openai/gpt-4o-mini"]
    assert "anthropic/claude-fable-5" not in connector.calls
    assert "openai/gpt-5" not in connector.calls
    assert model_status()["skipped_models"] == ["anthropic/claude-fable-5", "openai/gpt-5"]


def test_inactive_models_fall_back_safely():
    plan = {
        **PLAN,
        "seat_assignments": [
            {"seat": "legacy", "model": "anthropic/claude-3.5-sonnet", "reason": "missing beta suffix"},
            {"seat": "local", "model": "qwen-local", "reason": "offline"},
            {"seat": "nuclear", "model": "claude-opus", "reason": "needs health check"},
        ],
    }
    connector = SuccessfulConnector()
    engine = ExecutionEngine(connectors={"openrouter": connector})

    result = engine.execute(task="write a campaign", plan=plan)

    assert result["ok"] is True
    assert connector.calls == ["openai/gpt-4o-mini"]
    assert set(model_status()["skipped_models"]) == {"anthropic/claude-3.5-sonnet", "qwen-local", "claude-opus"}


def test_active_models_remain_executable_when_requested():
    plan = {
        **PLAN,
        "seat_assignments": [
            {"seat": "reviewer", "model": "claude-sonnet", "reason": "active beta alias"},
        ],
    }
    connector = FallbackConnector()
    engine = ExecutionEngine(connectors={"openrouter": connector})

    result = engine.execute(task="write a campaign", plan=plan)

    assert result["ok"] is True
    assert result["execution"]["model"] == "google/gemini-2.0-flash-001"
    assert connector.calls == ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"]


def test_model_registry_api_shape():
    registry = model_registry_for_api()
    rows = registry["models"]

    assert {"label", "seat", "provider_model", "status", "connector"} <= set(rows[0])
    assert [model for model in registry["fallback_chain"] if model not in MODEL_PRIORITY] == []
    assert any(row["provider_model"] == "anthropic/claude-3.5-sonnet:beta" and row["status"] == "active" for row in rows)
    assert not any(row["provider_model"] == "anthropic/claude-3.5-sonnet" for row in rows)
    assert any(row["provider_model"] == "openai/gpt-5" and row["status"] == "unsupported" for row in rows)
    assert any(row["seat"] == "qwen-local" and row["status"] == "offline" for row in rows)


def test_model_orchestrator_metrics_records_attempts():
    connector = FallbackConnector()
    engine = ExecutionEngine(connectors={"openrouter": connector})

    result = engine.execute(task="write a campaign", plan=PLAN)
    rows = {row["model_id"]: row for row in model_orchestrator_metrics()}

    assert result["ok"] is True
    assert rows["openai/gpt-4o-mini"]["failure_count"] >= 1
    assert rows["openai/gpt-4o-mini"]["last_error"]
    assert rows["google/gemini-2.0-flash-001"]["success_count"] >= 1
    assert rows["google/gemini-2.0-flash-001"]["latency_ms"] is not None
    assert rows["google/gemini-2.0-flash-001"]["token_usage"]["total"] > 0
    assert rows["google/gemini-2.0-flash-001"]["cost_estimate"] == "Not Connected"
