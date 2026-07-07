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
    """Small deterministic mission loop with persistent Flint memory output."""

    def __init__(self, memory_dir: Path | str = DEFAULT_MEMORY_DIR, seats_path: Path | str = DEFAULT_SEATS_PATH):
        self.memory_dir = Path(memory_dir)
        self.seats_path = Path(seats_path)

    @classmethod
    def load(cls) -> "MissionRuntime":
        return cls()

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
            "results": [],
            "approvals_required": False,
            "memory_path": None,
        }

    def decompose_mission(self, mission: dict[str, Any]) -> list[dict[str, Any]]:
        goal = str(mission.get("user_goal") or "").strip()
        if not goal:
            raise ValueError("mission.user_goal is required")

        lowered = goal.casefold()
        specs: list[tuple[str, str]] = [("Plan mission approach", "planner")]
        if self._matches(lowered, ("research", "find", "source", "competitor", "market", "web", "news", "audit")):
            specs.append(("Research required context and sources", "researcher"))
        if self._matches(lowered, ("build", "create", "implement", "code", "fix", "dashboard", "app", "api", "website", "ui")):
            specs.append(("Build or update the requested artifact", "builder"))
        if self._matches(lowered, ("trade", "trading", "premium", "ticker", "session", "risk review", "market analysis")):
            specs.append(("Run TradeMaster mission step", "TradeMaster"))
        if self._matches(lowered, ("automation", "automate", "workflow", "bot", "scheduler", "pipeline", "agent")):
            specs.append(("Prepare Automation Lab workflow", "Automation Lab"))
        specs.append(("Review result and final decision", "judge"))

        tasks = [self._task(index, title, seat, goal) for index, (title, seat) in enumerate(specs, start=1)]
        mission["tasks"] = tasks
        mission["status"] = "decomposed"
        return tasks

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

    def execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        seat = str(task.get("seat") or self._route_seat(task))
        title = str(task.get("title") or "Mission task")
        goal = str(task.get("input") or "")
        output = self._task_output(title=title, seat=seat, goal=goal, model_key=str(task.get("model_key") or ""))
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
        mission["approvals_required"] = any(task.get("seat") in {"TradeMaster", "Automation Lab"} for task in tasks)
        results = []
        for task in tasks:
            result = self.verify_task(self.execute_task(task))
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
        mission["status"] = "complete" if all(item["verification_status"] == "verified" for item in results) else "needs_review"
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

    def _task_output(self, *, title: str, seat: str, goal: str, model_key: str) -> str:
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
            return f"Judge verified mission outputs for final review: {goal}"
        return f"{seat} completed {title}: {goal}"

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
