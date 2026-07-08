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


class FakeSeatEngine:
    def __init__(self):
        self.calls = []

    def assign(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "task": kwargs["task"],
            "selected_skill": "business.offer_creation",
            "mode": "PANEL",
            "connectors": ["openrouter", "local_filesystem"],
            "seat_assignments": [
                {"seat": "planner", "model": "claude-sonnet", "reason": "planning"},
                {"seat": "builder", "model": "gpt-4.1-mini", "reason": "build"},
                {"seat": "judge", "model": "claude-fable-5", "reason": "final judge"},
            ],
            "estimated_cost_tier": "balanced",
            "confidence": 0.91,
            "warnings": [],
        }


class FakeExecutionEngine:
    def __init__(self, fail_fable=False, soft_refuse_fable=False):
        self.calls = []
        self.fail_fable = fail_fable
        self.soft_refuse_fable = soft_refuse_fable

    def execute(self, *, task, plan, memory_context=None):
        self.calls.append({"task": task, "plan": plan, "memory_context": memory_context})
        if plan.get("strict_preferred_models"):
            attempts = []
            for model in plan.get("preferred_models", []):
                provider_model = {
                    "claude-fable-5": "anthropic/claude-fable-5",
                    "gpt-4.1": "openai/gpt-4o",
                    "gemini-2.0-flash": "google/gemini-2.0-flash-001",
                    "deepseek-chat": "deepseek/deepseek-chat",
                    "gpt-4.1-mini": "openai/gpt-4o-mini",
                }[model]
                if self.fail_fable and model == "claude-fable-5":
                    attempts.append({"connector": "openrouter", "model": provider_model, "ok": False})
                    continue
                attempts.append({"connector": "openrouter", "model": provider_model, "ok": True})
                if self.soft_refuse_fable and model == "claude-fable-5":
                    return {
                        "ok": True,
                        "message": "I can't assist with that arbitration.",
                        "answer": "I can't assist with that arbitration.",
                        "execution": {
                            "connector": "openrouter",
                            "model": provider_model,
                            "attempts": attempts,
                            "fallback_used": False,
                            "stop_reason": "refusal",
                        },
                    }
                return {
                    "ok": True,
                    "message": f"judge answer from {provider_model}",
                    "answer": f"judge answer from {provider_model}",
                    "execution": {
                        "connector": "openrouter",
                        "model": provider_model,
                        "attempts": attempts,
                        "fallback_used": len(attempts) > 1,
                    },
                }
        model = "openai/gpt-4o-mini"
        return {
            "ok": True,
            "message": f"draft answer from {model}",
            "answer": f"draft answer from {model}",
            "execution": {
                "connector": "openrouter",
                "model": model,
                "attempts": [{"connector": "openrouter", "model": model, "ok": True}],
                "fallback_used": False,
            },
        }


def test_mission_creation_has_required_shape(tmp_path):
    mission = runtime(tmp_path).create_mission("Build a FusionDesk mission center")

    assert mission["id"]
    assert mission["user_goal"] == "Build a FusionDesk mission center"
    assert mission["status"] == "created"
    assert mission["created_at"].endswith("Z")
    assert mission["tasks"] == []
    assert mission["assigned_seats"] == {}
    assert mission["workflow"] == []
    assert mission["seat_plan"] is None
    assert mission["execution"] is None
    assert mission["final_answer"] == ""
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


def test_mission_engine_calls_seat_assignment_and_execution(tmp_path):
    seat_engine = FakeSeatEngine()
    execution_engine = FakeExecutionEngine()
    engine = MissionRuntime(
        memory_dir=tmp_path / "missions",
        seats_path=tmp_path / "seats.json",
        seat_engine=seat_engine,
        execution_engine=execution_engine,
    )

    mission = engine.run_mission("Build a landing page for my daycare")

    assert mission["status"] == "complete"
    assert mission["mission_type"] == "business_development"
    assert mission["seat_plan"]["selected_skill"] == "business.offer_creation"
    assert mission["connectors"] == ["openrouter", "local_filesystem"]
    assert mission["final_answer"] == "judge answer from anthropic/claude-fable-5"
    assert seat_engine.calls[0]["task"] == "Build a landing page for my daycare"
    assert len(execution_engine.calls) == 2
    assert execution_engine.calls[0]["task"] == "Build a landing page for my daycare"
    assert execution_engine.calls[1]["task"] == "Judge and finalize this mission: Build a landing page for my daycare"
    assert execution_engine.calls[1]["plan"]["seat_assignments"] == [
        {
            "seat": "judge",
            "model": "claude-fable-5",
            "reason": "Final mission arbitration uses the registered judge seat.",
        }
    ]
    assert execution_engine.calls[1]["plan"]["preferred_models"] == [
        "claude-fable-5",
        "gpt-4.1",
        "gemini-2.0-flash",
        "deepseek-chat",
        "gpt-4.1-mini",
    ]
    assert execution_engine.calls[1]["plan"]["strict_preferred_models"] is True
    assert mission["execution"]["judge_model_requested"] == "claude-fable-5"
    assert mission["execution"]["draft_model_used"] == "openai/gpt-4o-mini"
    assert mission["execution"]["judge_model_used"] == "anthropic/claude-fable-5"
    assert mission["execution"]["judge_enabled"] is True
    assert mission["execution"]["judge_fallback_used"] is False
    assert any("judge answer from anthropic/claude-fable-5" in task["output"] for task in mission["tasks"] if task["seat"] == "judge")
    assert Path(mission["memory_path"]).exists()


def test_mission_judge_falls_back_if_fable_fails(tmp_path):
    engine = MissionRuntime(
        memory_dir=tmp_path / "missions",
        seats_path=tmp_path / "seats.json",
        seat_engine=FakeSeatEngine(),
        execution_engine=FakeExecutionEngine(fail_fable=True),
    )

    mission = engine.run_mission("Build a landing page for my daycare")

    assert mission["status"] == "complete"
    assert mission["final_answer"] == "judge answer from openai/gpt-4o"
    assert mission["execution"]["draft_model_used"] == "openai/gpt-4o-mini"
    assert mission["execution"]["judge_model_used"] == "openai/gpt-4o"
    assert mission["execution"]["judge_enabled"] is True
    assert mission["execution"]["judge_fallback_used"] is True
    assert "Judge fallback used: openai/gpt-4o" in mission["execution"]["warnings"]


def test_mission_judge_falls_back_on_soft_refusal(tmp_path):
    execution_engine = FakeExecutionEngine(soft_refuse_fable=True)
    engine = MissionRuntime(
        memory_dir=tmp_path / "missions",
        seats_path=tmp_path / "seats.json",
        seat_engine=FakeSeatEngine(),
        execution_engine=execution_engine,
    )

    mission = engine.run_mission("Build a landing page for my daycare")

    assert mission["status"] == "complete"
    assert len(execution_engine.calls) == 3
    assert execution_engine.calls[1]["plan"]["preferred_models"][0] == "claude-fable-5"
    assert execution_engine.calls[2]["plan"]["preferred_models"][0] == "gpt-4.1"
    assert "claude-fable-5" not in execution_engine.calls[2]["plan"]["preferred_models"]
    assert mission["final_answer"] == "judge answer from openai/gpt-4o"
    assert mission["execution"]["draft_model_used"] == "openai/gpt-4o-mini"
    assert mission["execution"]["judge_model_used"] == "openai/gpt-4o"
    assert mission["execution"]["judge_enabled"] is True
    assert mission["execution"]["judge_fallback_used"] is True
    assert "Judge soft refusal detected from anthropic/claude-fable-5" in mission["execution"]["warnings"]
    assert "Judge fallback used: openai/gpt-4o" in mission["execution"]["warnings"]


def test_mission_engine_marks_execution_failure_needs_review(tmp_path):
    class FailingExecutionEngine(FakeExecutionEngine):
        def execute(self, *, task, plan, memory_context=None):
            return {"ok": False, "message": "OpenRouter unavailable", "answer": "", "execution": {"attempts": []}}

    engine = MissionRuntime(
        memory_dir=tmp_path / "missions",
        seats_path=tmp_path / "seats.json",
        seat_engine=FakeSeatEngine(),
        execution_engine=FailingExecutionEngine(),
    )

    mission = engine.run_mission("Build a landing page for my daycare")

    assert mission["status"] == "needs_review"
    assert mission["final_answer"] == "OpenRouter unavailable"
    assert Path(mission["memory_path"]).exists()


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
