from pathlib import Path

from dashboard.server import (
    SessionStore,
    backend_health,
    build_fusiondesk_memory_context,
    extract_user_facts,
    normalize_session_id,
    route_remote_command,
    tool_state_for_plan,
)


def test_session_store_persists_messages(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")

    user = store.append_message("browser-test", "user", "Use FusionDesk test")
    assistant = store.append_message("browser-test", "assistant", "Thinking...", status="running")
    store.update_message("browser-test", assistant["id"], content="Done.", status="done")

    restored = SessionStore(tmp_path / "sessions.json").get("browser-test")

    assert restored["messages"][0]["id"] == user["id"]
    assert restored["messages"][0]["content"] == "Use FusionDesk test"
    assert restored["messages"][1]["content"] == "Done."
    assert restored["messages"][1]["status"] == "done"


def test_normalize_session_id_strips_unsafe_characters():
    assert normalize_session_id("../phone secret!") == "..phonesecret"


def test_backend_health_reports_persistent_routes():
    health = backend_health()

    assert health["ok"] is True
    assert health["status"] == "ok"
    assert "fusiondesk" in health["routes"]
    assert "trademaster" in health["routes"]
    assert "claude_code" in health["routes"]
    assert "codex" in health["routes"]
    assert health["sessionStoreReady"] is True


def test_remote_trademaster_routes_to_fusiondesk(monkeypatch):
    calls = []

    def fake_fusiondesk(prompt, history=None):
        calls.append(prompt)
        return {"ok": True, "message": "TradeMaster plan", "route": "fusiondesk"}

    monkeypatch.setattr("dashboard.server.fusiondesk_chat", fake_fusiondesk)

    result = route_remote_command("/trademaster risk review ES futures", [])

    assert result["ok"] is True
    assert result["message"] == "TradeMaster plan"
    assert calls == ["Use FusionDesk risk review ES futures"]


def test_claude_and_codex_routes_are_guarded(monkeypatch):
    monkeypatch.setattr("dashboard.server.FUSIONDESK_AGENT_CLI_ENABLED", False)

    claude = route_remote_command("/claude explain this repo", [])
    codex = route_remote_command("/codex audit this repo", [])

    assert claude["ok"] is False
    assert claude["route"] == "claude_code"
    assert "disabled" in claude["message"]
    assert codex["ok"] is False
    assert codex["route"] == "codex"
    assert "disabled" in codex["message"]


def test_frontend_uses_backend_session_endpoint():
    source = Path("dashboard/static/app.js").read_text()

    assert "/api/session?session_id=" in source
    assert "localStorage.getItem(key)" in source
    assert "Connection lost while FusionDesk was answering" in source


def test_extracts_name_and_birthday_from_session_memory():
    messages = [
        {"role": "user", "content": "My name is Tatum."},
        {"role": "assistant", "content": "Got it."},
        {"role": "user", "content": "My birthday is July 3, 1990."},
    ]

    assert extract_user_facts(messages) == {"name": "Tatum", "birthday": "July 3, 1990"}


def test_tool_state_does_not_claim_internet_when_agent_reach_inactive(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.delenv("AGENT_REACH_ENABLED", raising=False)

    state = tool_state_for_plan({"connectors": ["openrouter", "agent_reach"]})

    assert state["openrouter"] == "active"
    assert state["internet_access"] == "inactive for this response"
    assert state["agent_reach"] == "registered only; not active"


def test_memory_context_contains_recap_facts_and_tool_state(monkeypatch):
    monkeypatch.delenv("AGENT_REACH_ENABLED", raising=False)
    messages = [{"role": "user", "content": "I'm Tatum and my bday is July 3."}]

    context = build_fusiondesk_memory_context(messages, {"connectors": ["agent_reach"]})

    assert context["facts"]["name"] == "Tatum"
    assert context["facts"]["birthday"] == "July 3"
    assert "Known facts" in context["recap"]
    assert context["tool_state"]["internet_access"] == "inactive for this response"


def test_frontend_surfaces_context_recap_and_trademaster_tab():
    app = Path("dashboard/static/app.js").read_text()
    html = Path("dashboard/static/index.html").read_text()

    assert "Context recap:" in app
    assert "/api/trademaster/status" in app
    assert "/api/capabilities" in app
    assert 'data-view="trademaster"' in html
    assert 'data-view="capabilities"' in html
