import json
from pathlib import Path

from dashboard.server import mission_response
from fusiondesk.core import MissionRuntime


def runtime(tmp_path) -> MissionRuntime:
    seats_path = tmp_path / "seats.json"
    seats_path.write_text(json.dumps({
        "planner": {"model_key": "claude-sonnet"},
        "researcher": {"model_key": "gemini-flash"},
        "builder": {"model_key": "gpt-builder"},
        "judge": {"model_key": "claude-judge"},
    }))
    return MissionRuntime(memory_dir=tmp_path / "missions", seats_path=seats_path)


def test_mission_creation_has_required_shape(tmp_path):
    mission = runtime(tmp_path).create_mission("Build a FusionDesk mission center")

    assert mission["id"]
    assert mission["user_goal"] == "Build a FusionDesk mission center"
    assert mission["status"] == "created"
    assert mission["created_at"].endswith("Z")
    assert mission["tasks"] == []
    assert mission["assigned_seats"] == {}
    assert mission["results"] == []
    assert mission["approvals_required"] is False
    assert mission["memory_path"] is None


def test_task_decomposition_routes_mission_work(tmp_path):
    engine = runtime(tmp_path)
    mission = engine.create_mission("Research markets, fix dashboard code, run TradeMaster, and automate reports")

    tasks = engine.decompose_mission(mission)
    seats = [task["seat"] for task in tasks]

    assert seats[0] == "planner"
    assert "researcher" in seats
    assert "builder" in seats
    assert "TradeMaster" in seats
    assert "Automation Lab" in seats
    assert seats[-1] == "judge"


def test_seat_assignment_uses_existing_seat_registry(tmp_path):
    engine = runtime(tmp_path)
    mission = engine.create_mission("Implement dashboard code and review it")
    tasks = engine.decompose_mission(mission)

    assignments = engine.assign_tasks(tasks)
    by_seat = {task["seat"]: task["model_key"] for task in tasks}

    assert assignments["task-01"] == "planner"
    assert by_seat["planner"] == "claude-sonnet"
    assert by_seat["builder"] == "gpt-builder"
    assert by_seat["judge"] == "claude-judge"


def test_memory_save_writes_real_mission_record(tmp_path):
    engine = runtime(tmp_path)
    mission = engine.run_mission("Create an automation workflow for lead follow-up")
    saved = mission["memory_path"]

    data = json.loads(Path(saved).read_text())

    assert data["id"] == mission["id"]
    assert data["status"] == "complete"
    assert data["approvals_required"] is True
    assert data["tasks"]
    assert data["results"]
    assert "flint" not in saved


def test_mission_api_response_shape(tmp_path):
    result = mission_response(
        {"user_goal": "Use FusionDesk to research competitors and create a plan"},
        runtime=runtime(tmp_path),
    )

    assert result["ok"] is True
    mission = result["mission"]
    assert mission["id"]
    assert mission["status"] == "complete"
    assert mission["memory_path"]
    assert isinstance(mission["tasks"], list)
    assert isinstance(mission["assigned_seats"], dict)
    assert isinstance(mission["results"], list)


def test_mission_api_rejects_missing_goal(tmp_path):
    result = mission_response({}, runtime=runtime(tmp_path))

    assert result == {"ok": False, "message": "user_goal is required."}
