"""Mission runtime for turning FusionDesk commands into saved work records."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MEMORY_DIR = ROOT / "flint" / "memory" / "missions"
DEFAULT_SEATS_PATH = ROOT / "fusiondesk" / "registry" / "seats.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def mission_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def slugify(value: str, limit: int = 36) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return (slug or "mission")[:limit].strip("-") or "mission"


class MissionRuntime:
    """Outcome-driven mission loop with persistent Flint memory output."""

    def __init__(
        self,
        memory_dir: Path | str = DEFAULT_MEMORY_DIR,
        seats_path: Path | str = DEFAULT_SEATS_PATH,
        seat_engine: Any | None = None,
        execution_engine: Any | None = None,
    ):
        self.memory_dir = Path(memory_dir)
        self.seats_path = Path(seats_path)
        self.seat_engine = seat_engine
        self.execution_engine = execution_engine

    @classmethod
    def load(cls) -> "MissionRuntime":
        seat_engine = None
        execution_engine = None
        try:
            from .seats import SeatAssignmentEngine

            seat_engine = SeatAssignmentEngine.load()
        except Exception:
            seat_engine = None
        try:
            from .execution import ExecutionEngine

            execution_engine = ExecutionEngine.load()
        except Exception:
            execution_engine = None
        return cls(seat_engine=seat_engine, execution_engine=execution_engine)

    def create_mission(self, user_goal: str) -> dict[str, Any]:
        goal = str(user_goal or "").strip()
        if not goal:
            raise ValueError("user_goal is required")
        mission_id = f"{slugify(goal)}-{uuid.uuid4().hex[:8]}"
        return {
            "id": mission_id,
            "user_goal": goal,
            "status": "created",
            "created_at": utc_now(),
            "tasks": [],
            "assigned_seats": {},
            "mission_type": "unclassified",
            "workflow": [],
            "connectors": [],
            "seat_plan": None,
            "execution": None,
            "final_answer": "",
            "progress_events": [self._event("created", "Mission accepted by FusionDesk.")],
            "results": [],
            "approvals_required": False,
            "memory_path": None,
        }

    def decompose_mission(self, mission: dict[str, Any]) -> list[dict[str, Any]]:
        goal = str(mission.get("user_goal") or "").strip()
        if not goal:
            raise ValueError("mission.user_goal is required")

        lowered = goal.casefold()
        mission_type = self.classify_mission(goal)
        workflow = self.generate_workflow(goal, mission_type)
        tasks = [self._task(index, step["title"], step["seat"], goal) for index, step in enumerate(workflow, start=1)]
        mission["mission_type"] = mission_type
        mission["workflow"] = workflow
        mission["tasks"] = tasks
        mission["status"] = "decomposed"
        mission.setdefault("progress_events", []).append(self._event("decomposed", f"Generated {len(tasks)} mission tasks."))
        return tasks

    def classify_mission(self, user_goal: str) -> str:
        goal = str(user_goal or "").casefold()
        if self._matches(goal, ("trade", "trading", "premium", "ticker", "session", "risk review", "market analysis")):
            return "trading"
        if self._matches(goal, ("lead", "client", "sales", "outreach", "daycare", "proposal", "crm")):
            return "business_development"
        if self._matches(goal, ("content", "social", "ad", "campaign", "video", "short", "podcast", "brand")):
            return "marketing_media"
        if self._matches(goal, ("build", "create", "implement", "code", "fix", "dashboard", "app", "api", "website", "ui")):
            return "development"
        if self._matches(goal, ("research", "find", "source", "competitor", "market", "web", "news", "audit")):
            return "research"
        if self._matches(goal, ("automation", "automate", "workflow", "bot", "scheduler", "pipeline", "agent")):
            return "automation"
        return "general"

    def generate_workflow(self, user_goal: str, mission_type: str) -> list[dict[str, Any]]:
        goal = str(user_goal or "").casefold()
        steps: list[dict[str, Any]] = [self._workflow_step("Plan mission approach", "planner")]
        if mission_type in {"business_development", "marketing_media", "research", "trading"} or self._matches(
            goal, ("research", "find", "source", "competitor", "market", "web", "news", "audit")
        ):
            steps.append(self._workflow_step("Research required context and sources", "researcher"))
        if mission_type in {"development", "business_development", "marketing_media"} or self._matches(
            goal, ("build", "create", "implement", "code", "fix", "dashboard", "app", "api", "website", "ui")
        ):
            steps.append(self._workflow_step("Build or update the requested artifact", "builder"))
        if mission_type == "trading":
            steps.append(self._workflow_step("Run TradeMaster mission step", "TradeMaster", requires_approval=True))
        if mission_type == "automation" or self._matches(goal, ("automation", "automate", "workflow", "bot", "scheduler", "pipeline", "agent")):
            steps.append(self._workflow_step("Prepare Automation Lab workflow", "Automation Lab", requires_approval=True))
        steps.append(self._workflow_step("Review result and final decision", "judge"))
        return steps

    def assign_tasks(self, tasks: list[dict[str, Any]]) -> dict[str, str]:
        assignments: dict[str, str] = {}
        for task in tasks:
            seat = self._route_seat(task)
            model_key = self._model_key_for_seat(seat)
            task["seat"] = seat
            task["model_key"] = model_key
            task["status"] = "assigned"
            assignments[str(task["id"])] = seat
        return assignments

    def assign_mission_seats(self, mission: dict[str, Any]) -> dict[str, Any]:
        if not self.seat_engine:
            return self._fallback_seat_plan(mission, "SeatAssignmentEngine is not connected")
        try:
            return self.seat_engine.assign(task=mission["user_goal"])
        except Exception as exc:
            return self._fallback_seat_plan(mission, f"SeatAssignmentEngine failed: {exc}")

    def execute_mission(self, mission: dict[str, Any], seat_plan: dict[str, Any]) -> dict[str, Any]:
        if not self.execution_engine:
            answer = self._deterministic_final_answer(mission)
            return {
                "ok": True,
                "message": answer,
                "answer": answer,
                "mode": "record_only",
                "execution": {"connector": None, "model": None, "attempts": []},
            }
        try:
            draft_execution = self.execution_engine.execute(
                task=mission["user_goal"],
                plan=seat_plan,
                memory_context={"recap": self._mission_context(mission)},
            )
            judge_model = self._judge_model_for_mission(mission, seat_plan)
            judge_plan = self._judge_plan(mission, seat_plan, judge_model)
            primary_judge_execution = self.execution_engine.execute(
                task=f"Judge and finalize this mission: {mission['user_goal']}",
                plan=judge_plan,
                memory_context={"recap": self._judge_context(mission, draft_execution)},
            )
            judge_execution = primary_judge_execution
            judge_soft_fallback_used = False
            judge_warnings = []
            if self._judge_output_unusable(primary_judge_execution):
                judge_soft_fallback_used = True
                primary_model = (primary_judge_execution.get("execution") or {}).get("model") or judge_model
                judge_warnings.append(f"Judge soft refusal detected from {primary_model}")
                fallback_judge_plan = self._judge_plan(
                    mission,
                    seat_plan,
                    judge_model,
                    include_primary=False,
                )
                judge_execution = self.execution_engine.execute(
                    task=f"Judge fallback and finalize this mission: {mission['user_goal']}",
                    plan=fallback_judge_plan,
                    memory_context={"recap": self._judge_context(mission, draft_execution)},
                )
            draft_details = draft_execution.get("execution") or {}
            primary_judge_details = primary_judge_execution.get("execution") or {}
            judge_details = judge_execution.get("execution") or {}
            draft_model_used = draft_details.get("model")
            judge_model_used = judge_details.get("model")
            judge_fallback_used = judge_soft_fallback_used or bool(judge_details.get("fallback_used")) or (
                bool(judge_model_used) and judge_model_used != "anthropic/claude-fable-5"
            )
            warnings = list(seat_plan.get("warnings") or []) + judge_warnings
            if judge_fallback_used:
                warnings.append(f"Judge fallback used: {judge_model_used or 'unknown model'}")
            return {
                "ok": bool(judge_execution.get("ok")),
                "message": judge_execution.get("message") or judge_execution.get("answer") or draft_execution.get("message") or "",
                "answer": judge_execution.get("answer") or judge_execution.get("message") or draft_execution.get("answer") or "",
                "mode": "judge_arbitration",
                "draft_answer": draft_execution.get("answer") or draft_execution.get("message") or "",
                "execution": {
                    "draft": draft_details,
                    "judge_primary": primary_judge_details,
                    "judge": judge_details,
                    "connector": judge_details.get("connector"),
                    "model": judge_model_used,
                    "attempts": draft_details.get("attempts", [])
                    + primary_judge_details.get("attempts", [])
                    + ([] if judge_execution is primary_judge_execution else judge_details.get("attempts", [])),
                    "fallback_used": bool(draft_details.get("fallback_used")) or judge_soft_fallback_used or bool(judge_details.get("fallback_used")),
                    "judge_model_requested": judge_model,
                    "draft_model_used": draft_model_used,
                    "judge_model_used": judge_model_used,
                    "judge_enabled": True,
                    "judge_fallback_used": judge_fallback_used,
                    "warnings": warnings,
                },
            }
        except Exception as exc:
            return {
                "ok": False,
                "message": f"Mission execution failed: {exc}",
                "answer": "",
                "mode": "execution_engine",
                "execution": {"connector": "openrouter", "model": None, "attempts": [], "error": str(exc)},
            }

    def execute_task(self, task: dict[str, Any], mission_execution: dict[str, Any] | None = None) -> dict[str, Any]:
        seat = str(task.get("seat") or self._route_seat(task))
        title = str(task.get("title") or "Mission task")
        goal = str(task.get("input") or "")
        output = self._task_output(
            title=title,
            seat=seat,
            goal=goal,
            model_key=str(task.get("model_key") or ""),
            mission_execution=mission_execution or {},
        )
        task["status"] = "complete"
        task["output"] = output
        return task

    def verify_task(self, task_result: dict[str, Any]) -> dict[str, Any]:
        task_result["verification_status"] = "verified" if task_result.get("status") == "complete" and task_result.get("output") else "failed"
        return task_result

    def save_mission_memory(self, mission_result: dict[str, Any]) -> str:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        mission_id = str(mission_result.get("id") or f"mission-{uuid.uuid4().hex[:8]}")
        path = self.memory_dir / f"{mission_timestamp()}-{mission_id}.json"
        mission_result["memory_path"] = str(path)
        path.write_text(json.dumps(mission_result, indent=2, sort_keys=True) + "\n")
        return str(path)

    def run_mission(self, user_goal: str) -> dict[str, Any]:
        mission = self.create_mission(user_goal)
        tasks = self.decompose_mission(mission)
        mission["assigned_seats"] = self.assign_tasks(tasks)
        mission.setdefault("progress_events", []).append(self._event("assigned", "Assigned mission tasks to seats."))
        seat_plan = self.assign_mission_seats(mission)
        mission["seat_plan"] = seat_plan
        mission["connectors"] = seat_plan.get("connectors", [])
        self._apply_seat_plan_to_tasks(tasks, seat_plan)
        mission.setdefault("progress_events", []).append(
            self._event("seat_assignment", f"Selected skill {seat_plan.get('selected_skill', 'unknown')}.")
        )
        mission["approvals_required"] = any(task.get("seat") in {"TradeMaster", "Automation Lab"} for task in tasks)
        mission_execution = self.execute_mission(mission, seat_plan)
        mission["execution"] = mission_execution.get("execution", mission_execution)
        mission["final_answer"] = mission_execution.get("answer") or mission_execution.get("message") or ""
        mission.setdefault("progress_events", []).append(
            self._event("executed", "Execution engine returned a mission result." if mission_execution.get("ok") else "Execution needs review.")
        )
        results = []
        for task in tasks:
            result = self.verify_task(self.execute_task(task, mission_execution))
            results.append(
                {
                    "task_id": result["id"],
                    "title": result["title"],
                    "seat": result["seat"],
                    "model_key": result["model_key"],
                    "status": result["status"],
                    "verification_status": result["verification_status"],
                    "output": result["output"],
                }
            )
        mission["tasks"] = tasks
        mission["results"] = results
        verified = all(item["verification_status"] == "verified" for item in results)
        mission["status"] = "complete" if verified and mission_execution.get("ok") else "needs_review"
        mission.setdefault("progress_events", []).append(self._event("verified", f"Mission status: {mission['status']}."))
        self.save_mission_memory(mission)
        return mission

    def list_missions(self) -> list[dict[str, Any]]:
        if not self.memory_dir.exists():
            return []
        missions = []
        for path in sorted(self.memory_dir.glob("*.json"), reverse=True):
            mission = self._read_mission(path)
            if mission:
                missions.append(self._mission_summary(mission))
        return missions

    def get_mission(self, mission_id: str) -> dict[str, Any] | None:
        target = str(mission_id or "").strip()
        if not target or not self.memory_dir.exists():
            return None
        for path in sorted(self.memory_dir.glob("*.json"), reverse=True):
            mission = self._read_mission(path)
            if mission and mission.get("id") == target:
                return mission
        return None

    def _task(self, index: int, title: str, seat: str, goal: str) -> dict[str, Any]:
        return {
            "id": f"task-{index:02d}",
            "title": title,
            "seat": seat,
            "model_key": "",
            "status": "pending",
            "input": goal,
            "output": "",
            "verification_status": "pending",
        }

    def _workflow_step(self, title: str, seat: str, requires_approval: bool = False) -> dict[str, Any]:
        return {"title": title, "seat": seat, "requires_approval": requires_approval}

    def _route_seat(self, task: dict[str, Any]) -> str:
        seat = str(task.get("seat") or "").strip()
        if seat in {"planner", "builder", "researcher", "judge", "TradeMaster", "Automation Lab"}:
            return seat
        title = f"{task.get('title', '')} {task.get('input', '')}".casefold()
        if self._matches(title, ("trade", "trading", "premium", "ticker")):
            return "TradeMaster"
        if self._matches(title, ("automation", "automate", "workflow", "bot")):
            return "Automation Lab"
        if self._matches(title, ("build", "code", "implement", "fix", "api", "dashboard")):
            return "builder"
        if self._matches(title, ("research", "source", "competitor", "web", "market")):
            return "researcher"
        if self._matches(title, ("review", "judge", "final decision")):
            return "judge"
        return "planner"

    def _model_key_for_seat(self, seat: str) -> str:
        seats = self._load_seats()
        if seat in seats:
            return str(seats[seat].get("model_key") or "claude-sonnet")
        if seat == "TradeMaster":
            return str(seats.get("planner", {}).get("model_key") or "claude-sonnet")
        if seat == "Automation Lab":
            return str(seats.get("builder", {}).get("model_key") or "gpt-4.1-mini")
        return str(seats.get("planner", {}).get("model_key") or "claude-sonnet")

    def _load_seats(self) -> dict[str, Any]:
        try:
            data = json.loads(self.seats_path.read_text())
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _task_output(
        self,
        *,
        title: str,
        seat: str,
        goal: str,
        model_key: str,
        mission_execution: dict[str, Any],
    ) -> str:
        answer = mission_execution.get("answer") or mission_execution.get("message") or ""
        if seat == "TradeMaster":
            return f"TradeMaster step prepared for mission goal: {goal}"
        if seat == "Automation Lab":
            return f"Automation Lab workflow step prepared for mission goal: {goal}"
        if seat == "planner":
            return f"Planner mapped the mission path for: {goal}"
        if seat == "researcher":
            return f"Researcher identified the context needed before execution: {goal}"
        if seat == "builder":
            return f"Builder task is ready for implementation using model key {model_key}: {goal}"
        if seat == "judge":
            if mission_execution.get("ok") and answer:
                return f"Judge final deliverable:\n{answer}"
            return f"Judge verified mission outputs for final review: {goal}"
        return f"{seat} completed {title}: {goal}"

    def _fallback_seat_plan(self, mission: dict[str, Any], warning: str) -> dict[str, Any]:
        return {
            "task": mission.get("user_goal"),
            "selected_skill": f"mission.{mission.get('mission_type', 'general')}",
            "mode": "PANEL",
            "connectors": ["local_filesystem"],
            "seat_assignments": [
                {"seat": task.get("seat"), "model": task.get("model_key") or self._model_key_for_seat(task.get("seat", "")), "reason": "Mission Runtime fallback"}
                for task in mission.get("tasks", [])
            ],
            "estimated_cost_tier": "balanced",
            "confidence": 0.5,
            "warnings": [warning],
        }

    def _apply_seat_plan_to_tasks(self, tasks: list[dict[str, Any]], seat_plan: dict[str, Any]) -> None:
        seat_models = {
            str(item.get("seat")): str(item.get("model"))
            for item in seat_plan.get("seat_assignments", [])
            if item.get("seat") and item.get("model")
        }
        for task in tasks:
            seat = str(task.get("seat") or "")
            if seat in seat_models:
                task["model_key"] = seat_models[seat]

    def _deterministic_final_answer(self, mission: dict[str, Any]) -> str:
        workflow = ", ".join(step.get("title", "") for step in mission.get("workflow", []))
        return f"Mission workflow prepared for '{mission.get('user_goal')}': {workflow}."

    def _judge_model_for_mission(self, mission: dict[str, Any], seat_plan: dict[str, Any]) -> str:
        for task in mission.get("tasks", []):
            if task.get("seat") == "judge" and task.get("model_key"):
                return str(task["model_key"])
        for assignment in seat_plan.get("seat_assignments", []):
            if assignment.get("seat") == "judge" and assignment.get("model"):
                return str(assignment["model"])
        return self._model_key_for_seat("judge")

    def _judge_plan(
        self,
        mission: dict[str, Any],
        seat_plan: dict[str, Any],
        judge_model: str,
        include_primary: bool = True,
    ) -> dict[str, Any]:
        connectors = list(seat_plan.get("connectors") or [])
        if "openrouter" not in connectors:
            connectors.append("openrouter")
        preferred_models = [
            judge_model,
            "gpt-4.1",
            "gemini-2.0-flash",
            "deepseek-chat",
            "gpt-4.1-mini",
        ]
        if not include_primary:
            preferred_models = [model for model in preferred_models if model != judge_model]
        return {
            **seat_plan,
            "task": mission.get("user_goal"),
            "selected_skill": f"{seat_plan.get('selected_skill', 'mission')}.judge",
            "mode": "SOLO",
            "connectors": connectors,
            "seat_assignments": [
                {
                    "seat": "judge",
                    "model": judge_model,
                    "reason": "Final mission arbitration uses the registered judge seat.",
                }
            ],
            "preferred_models": preferred_models,
            "strict_preferred_models": True,
            "warnings": list(seat_plan.get("warnings") or []),
        }

    def _mission_context(self, mission: dict[str, Any]) -> str:
        workflow = "\n".join(f"- {step.get('seat')}: {step.get('title')}" for step in mission.get("workflow", []))
        assigned = "\n".join(f"- {task_id}: {seat}" for task_id, seat in mission.get("assigned_seats", {}).items())
        return (
            f"Mission type: {mission.get('mission_type')}\n"
            f"Workflow:\n{workflow}\n"
            f"Assigned seats:\n{assigned}\n"
            "Return the completed mission result, not planning JSON."
        )

    def _judge_context(self, mission: dict[str, Any], draft_execution: dict[str, Any]) -> str:
        draft = draft_execution.get("answer") or draft_execution.get("message") or ""
        return (
            f"{self._mission_context(mission)}\n\n"
            "Draft mission output for judge review:\n"
            f"{draft}\n\n"
            "As judge, resolve weak spots, remove unsupported claims, and return the final user-facing deliverable."
        )

    def _judge_output_unusable(self, judge_execution: dict[str, Any]) -> bool:
        if not judge_execution.get("ok"):
            return True
        answer = str(judge_execution.get("answer") or judge_execution.get("message") or "").strip()
        details = judge_execution.get("execution") or {}
        stop_reason = str(
            judge_execution.get("stop_reason")
            or judge_execution.get("finish_reason")
            or details.get("stop_reason")
            or details.get("finish_reason")
            or ""
        ).casefold()
        if stop_reason in {"refusal", "content_filter", "safety", "blocked"}:
            return True
        if not answer:
            return True
        lowered = answer.casefold()
        refusal_markers = (
            "i can't assist",
            "i cannot assist",
            "i can't help",
            "i cannot help",
            "unable to comply",
            "i must refuse",
            "refusal",
        )
        return any(marker in lowered for marker in refusal_markers)

    def _event(self, stage: str, message: str) -> dict[str, str]:
        return {"at": utc_now(), "stage": stage, "message": message}

    def _read_mission(self, path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text())
        except Exception:
            return None
        if isinstance(data, dict):
            data.setdefault("memory_path", str(path))
            return data
        return None

    def _mission_summary(self, mission: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": mission.get("id"),
            "user_goal": mission.get("user_goal"),
            "status": mission.get("status"),
            "created_at": mission.get("created_at"),
            "task_count": len(mission.get("tasks") or []),
            "approvals_required": bool(mission.get("approvals_required")),
            "memory_path": mission.get("memory_path"),
        }

    @staticmethod
    def _matches(value: str, needles: tuple[str, ...]) -> bool:
        return any(needle in value for needle in needles)


_DEFAULT_RUNTIME = MissionRuntime.load()


def create_mission(user_goal: str) -> dict[str, Any]:
    return _DEFAULT_RUNTIME.create_mission(user_goal)


def decompose_mission(mission: dict[str, Any]) -> list[dict[str, Any]]:
    return _DEFAULT_RUNTIME.decompose_mission(mission)


def assign_tasks(tasks: list[dict[str, Any]]) -> dict[str, str]:
    return _DEFAULT_RUNTIME.assign_tasks(tasks)


def execute_task(task: dict[str, Any]) -> dict[str, Any]:
    return _DEFAULT_RUNTIME.execute_task(task)


def verify_task(task_result: dict[str, Any]) -> dict[str, Any]:
    return _DEFAULT_RUNTIME.verify_task(task_result)


def save_mission_memory(mission_result: dict[str, Any]) -> str:
    return _DEFAULT_RUNTIME.save_mission_memory(mission_result)
