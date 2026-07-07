import json
from pathlib import Path

from dashboard.server import executive_command_response
from fusiondesk.core import ExecutiveCommandCenter, MissionRuntime


def runtime(tmp_path) -> MissionRuntime:
    seats_path = tmp_path / "seats.json"
    seats_path.write_text(json.dumps({
        "planner": {"model_key": "claude-sonnet"},
        "researcher": {"model_key": "gemini-flash"},
        "builder": {"model_key": "gpt-builder"},
        "judge": {"model_key": "claude-judge"},
    }))
    return MissionRuntime(memory_dir=tmp_path / "missions", seats_path=seats_path)


def command_center(tmp_path) -> ExecutiveCommandCenter:
    return ExecutiveCommandCenter(
        mission_runtime=runtime(tmp_path),
        memory_dir=tmp_path / "executive",
        seats_path=tmp_path / "seats.json",
    )


def test_executive_command_runs_ceo_loop_and_saves_memory(tmp_path):
    center = command_center(tmp_path)

    command = center.run_command("Find me 10 daycare clients and prepare outreach")

    assert command["id"].startswith("exec-")
    assert command["status"] == "complete"
    assert command["mission"]["status"] == "complete"
    assert command["approvals_required"] is False
    assert [step["stage"] for step in command["loop"]] == [
        "observe",
        "decide",
        "delegate",
        "execute",
        "verify",
        "learn",
    ]
    assert Path(command["memory_path"]).exists()
    assert Path(command["mission"]["memory_path"]).exists()
    assert "Executive Command Center completed mission" in command["report"]


def test_executive_command_detects_trading_and_automation_approval(tmp_path):
    center = command_center(tmp_path)

    command = center.run_command("Run TradeMaster market review and automate follow-up")

    seats = {task["seat"] for task in command["mission"]["tasks"]}
    assert "TradeMaster" in seats
    assert "Automation Lab" in seats
    assert command["approvals_required"] is True


def test_executive_dashboard_snapshot_uses_real_counts(tmp_path):
    center = command_center(tmp_path)
    center.run_command("Build a dashboard UI")

    snapshot = center.dashboard_snapshot(
        {
            "router_status": "Ready",
            "seat_assignment_status": "Ready",
            "streaming_status": "Ready",
            "execution_engine_status": "Configured",
            "memory_health": {"session_store": "Connected"},
        }
    )

    assert snapshot["ok"] is True
    assert snapshot["health"] == 100
    assert snapshot["completed_tasks"] > 0
    assert snapshot["cost_today"] == "Not Connected"
    assert snapshot["revenue_generated"] == "Not Connected"
    assert snapshot["last_mission"]
    assert snapshot["last_command"]
    assert snapshot["ceo_loop"] == ["Observe", "Decide", "Delegate", "Execute", "Verify", "Learn", "Report"]


def test_executive_api_response_shape(tmp_path):
    result = executive_command_response(
        {"user_goal": "Create a content campaign workflow"},
        command_center=command_center(tmp_path),
    )

    assert result["ok"] is True
    assert result["command"]["mission"]
    assert result["command"]["services"]["mission_planner"] == "Connected"
    assert result["command"]["memory_path"]


def test_executive_api_rejects_missing_goal(tmp_path):
    result = executive_command_response({}, command_center=command_center(tmp_path))

    assert result == {"ok": False, "message": "user_goal is required."}


def test_dashboard_has_executive_view():
    html = Path("dashboard/static/index.html").read_text()
    app = Path("dashboard/static/app.js").read_text()

    assert 'data-view="executive"' in html
    assert 'id="executive"' in html
    assert "/api/executive" in app
    assert "/api/executive/commands" in app
