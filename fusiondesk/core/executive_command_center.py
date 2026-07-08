"""Executive Command Center for FusionDesk outcome-driven missions."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .mission_runtime import MissionRuntime, mission_timestamp


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXECUTIVE_MEMORY_DIR = ROOT / "flint" / "memory" / "executive"
DEFAULT_SEATS_PATH = ROOT / "fusiondesk" / "registry" / "seats.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str, limit: int = 34) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return (slug or "command")[:limit].strip("-") or "command"


class ExecutiveCommandCenter:
    """Top-level executive loop that owns FusionDesk workflow orchestration."""

    def __init__(
        self,
        mission_runtime: MissionRuntime | None = None,
        memory_dir: Path | str = DEFAULT_EXECUTIVE_MEMORY_DIR,
        seats_path: Path | str = DEFAULT_SEATS_PATH,
    ):
        self.mission_runtime = mission_runtime or MissionRuntime.load()
        self.memory_dir = Path(memory_dir)
        self.seats_path = Path(seats_path)

    @classmethod
    def load(cls) -> "ExecutiveCommandCenter":
        return cls()

    def run_command(self, user_goal: str) -> dict[str, Any]:
        command = self.create_command(user_goal)
        observed = self.observe(command)
        decision = self.decide(command, observed)
        delegated = self.delegate(command, decision)
        executed = self.execute(command, delegated)
        verified = self.verify(command, executed)
        learned = self.learn(command, verified)
        report = self.report(command, learned)
        command["status"] = "complete" if verified.get("ok") else "needs_review"
        command["report"] = report
        command["memory_path"] = self.save_command_memory(command)
        return command

    def create_command(self, user_goal: str) -> dict[str, Any]:
        goal = str(user_goal or "").strip()
        if not goal:
            raise ValueError("user_goal is required")
        command_id = f"exec-{slugify(goal)}-{uuid.uuid4().hex[:8]}"
        return {
            "id": command_id,
            "user_goal": goal,
            "status": "created",
            "created_at": utc_now(),
            "loop": [],
            "services": {},
            "mission": None,
            "workflow": [],
            "results": [],
            "approvals_required": False,
            "memory_path": None,
            "report": "",
        }

    def observe(self, command: dict[str, Any]) -> dict[str, Any]:
        goal = command["user_goal"]
        lowered = goal.casefold()
        outcome_type = "general"
        if self._matches(lowered, ("website", "app", "build", "code", "fix")):
            outcome_type = "development"
        elif self._matches(lowered, ("lead", "client", "sales", "outreach", "daycare")):
            outcome_type = "business_development"
        elif self._matches(lowered, ("trade", "trading", "premium", "ticker", "market")):
            outcome_type = "trading"
        elif self._matches(lowered, ("content", "social", "ad", "campaign", "video")):
            outcome_type = "marketing_media"
        observation = {
            "stage": "observe",
            "status": "complete",
            "outcome_type": outcome_type,
            "summary": f"Observed user outcome: {goal}",
        }
        command["loop"].append(observation)
        command["status"] = "observed"
        return observation

    def decide(self, command: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
        goal = command["user_goal"].casefold()
        services = {
            "mission_planner": "Connected",
            "seat_engine": "Connected",
            "workflow_engine": "MissionRuntime built-in; no standalone DAG engine",
            "memory_engine": "Connected",
            "model_orchestrator": "Partial: OpenRouter registry/failover only",
            "execution_engine": "Partial: OpenRouter execution only",
            "connector_layer": "Partial",
        }
        needed_connectors = ["local_filesystem"]
        if self._matches(goal, ("research", "find", "lead", "client", "competitor", "web")):
            needed_connectors.append("agent_reach")
        if self._matches(goal, ("trade", "trading", "market", "ticker")):
            needed_connectors.append("polygon_io")
        if self._matches(goal, ("video", "image", "voice", "runpod")):
            needed_connectors.append("runpod")
        decision = {
            "stage": "decide",
            "status": "complete",
            "outcome_type": observation["outcome_type"],
            "services": services,
            "needed_connectors": needed_connectors,
            "notes": "Executive Command Center delegates to Mission Runtime. Unwired connectors are requirements, not live workers.",
        }
        command["services"] = services
        command["workflow"] = [
            "Observe goal",
            "Decide service requirements",
            "Delegate mission tasks",
            "Execute through Mission Runtime",
            "Verify saved outputs",
            "Learn into Flint memory",
            "Report executive summary",
        ]
        command["loop"].append(decision)
        command["status"] = "decided"
        return decision

    def delegate(self, command: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        mission = self.mission_runtime.run_mission(command["user_goal"])
        command["mission"] = mission
        command["approvals_required"] = bool(mission.get("approvals_required"))
        delegated = {
            "stage": "delegate",
            "status": "complete",
            "mission_id": mission.get("id"),
            "task_count": len(mission.get("tasks") or []),
            "assigned_seats": mission.get("assigned_seats") or {},
            "needed_connectors": decision.get("needed_connectors") or [],
        }
        command["loop"].append(delegated)
        command["status"] = "delegated"
        return delegated

    def execute(self, command: dict[str, Any], delegated: dict[str, Any]) -> dict[str, Any]:
        mission = command.get("mission") or {}
        results = mission.get("results") or []
        executed = {
            "stage": "execute",
            "status": "complete" if mission.get("status") == "complete" else "needs_review",
            "mission_status": mission.get("status"),
            "completed_tasks": sum(1 for result in results if result.get("status") == "complete"),
            "result_count": len(results),
        }
        command["results"] = results
        command["loop"].append(executed)
        command["status"] = "executed"
        return executed

    def verify(self, command: dict[str, Any], executed: dict[str, Any]) -> dict[str, Any]:
        mission = command.get("mission") or {}
        tasks = mission.get("tasks") or []
        verified = {
            "stage": "verify",
            "status": "complete",
            "ok": bool(tasks) and all(task.get("verification_status") == "verified" for task in tasks),
            "verified_tasks": sum(1 for task in tasks if task.get("verification_status") == "verified"),
            "task_count": len(tasks),
            "approvals_required": command.get("approvals_required", False),
        }
        command["loop"].append(verified)
        command["status"] = "verified" if verified["ok"] else "needs_review"
        return verified

    def learn(self, command: dict[str, Any], verified: dict[str, Any]) -> dict[str, Any]:
        learned = {
            "stage": "learn",
            "status": "complete",
            "memory_engine": "Connected",
            "mission_memory_path": (command.get("mission") or {}).get("memory_path"),
            "executive_memory_pending": True,
        }
        command["loop"].append(learned)
        command["status"] = "learned"
        return learned

    def report(self, command: dict[str, Any], learned: dict[str, Any]) -> str:
        mission = command.get("mission") or {}
        task_count = len(mission.get("tasks") or [])
        approvals = "approval required" if command.get("approvals_required") else "no approval required"
        return f"Executive Command Center completed mission {mission.get('id')} with {task_count} tasks; {approvals}."

    def save_command_memory(self, command: dict[str, Any]) -> str:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        path = self.memory_dir / f"{mission_timestamp()}-{command['id']}.json"
        command["memory_path"] = str(path)
        path.write_text(json.dumps(command, indent=2, sort_keys=True) + "\n")
        return str(path)

    def list_commands(self) -> list[dict[str, Any]]:
        if not self.memory_dir.exists():
            return []
        rows = []
        for path in sorted(self.memory_dir.glob("*.json"), reverse=True):
            command = self._read_command(path)
            if command:
                rows.append(
                    {
                        "id": command.get("id"),
                        "user_goal": command.get("user_goal"),
                        "status": command.get("status"),
                        "created_at": command.get("created_at"),
                        "mission_id": (command.get("mission") or {}).get("id"),
                        "task_count": len((command.get("mission") or {}).get("tasks") or []),
                        "approvals_required": bool(command.get("approvals_required")),
                        "memory_path": command.get("memory_path") or str(path),
                    }
                )
        return rows

    def get_command(self, command_id: str) -> dict[str, Any] | None:
        target = str(command_id or "").strip()
        if not target or not self.memory_dir.exists():
            return None
        for path in sorted(self.memory_dir.glob("*.json"), reverse=True):
            command = self._read_command(path)
            if command and command.get("id") == target:
                return command
        return None

    def dashboard_snapshot(self, system_health: dict[str, Any] | None = None) -> dict[str, Any]:
        missions = self.mission_runtime.list_missions()
        commands = self.list_commands()
        full_missions = [self.mission_runtime.get_mission(row["id"]) for row in missions[:25]]
        full_missions = [mission for mission in full_missions if mission]
        task_rows = [task for mission in full_missions for task in mission.get("tasks", [])]
        completed_tasks = sum(1 for task in task_rows if task.get("status") == "complete")
        failed_tasks = sum(1 for task in task_rows if task.get("verification_status") == "failed")
        running_tasks = sum(1 for task in task_rows if task.get("status") not in {"complete", "failed"})
        active_agents = 0
        registered_seats = len(self._load_seats())
        health_score = self._health_score(system_health or {})
        return {
            "ok": True,
            "health": health_score,
            "running_jobs": running_tasks,
            "active_missions": sum(1 for row in missions if row.get("status") not in {"complete", "failed"}),
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "cost_today": "Not Connected",
            "revenue_generated": "Not Connected",
            "active_agents": active_agents,
            "registered_agents": registered_seats,
            "registered_seats": registered_seats,
            "agent_status_note": "No persistent worker/agent runtime is connected. These counts come from saved mission task records and registered seats.",
            "last_mission": missions[0] if missions else None,
            "last_command": commands[0] if commands else None,
            "ceo_loop": ["Observe", "Decide", "Delegate", "Execute", "Verify", "Learn", "Report"],
            "services": {
                "mission_planner": "Connected",
                "seat_engine": "Connected",
                "workflow_engine": "MissionRuntime built-in; no standalone DAG engine",
                "memory_engine": "Connected",
                "model_orchestrator": "Partial: OpenRouter registry/failover only",
                "connector_layer": "Partial",
                "execution_engine": (system_health or {}).get("execution_engine_status", "Not Connected"),
            },
            "commands": commands[:8],
        }

    def _read_command(self, path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text())
        except Exception:
            return None
        if isinstance(data, dict):
            data.setdefault("memory_path", str(path))
            return data
        return None

    def _load_seats(self) -> dict[str, Any]:
        try:
            data = json.loads(self.seats_path.read_text())
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _health_score(system_health: dict[str, Any]) -> int:
        if not system_health:
            return 0
        checks = [
            system_health.get("router_status") == "Ready",
            system_health.get("seat_assignment_status") == "Ready",
            system_health.get("streaming_status") == "Ready",
            system_health.get("execution_engine_status") in {"Configured", "Ready", "Connected"},
            (system_health.get("memory_health") or {}).get("session_store") == "Connected",
        ]
        return round((sum(1 for check in checks if check) / len(checks)) * 100)

    @staticmethod
    def _matches(value: str, needles: tuple[str, ...]) -> bool:
        return any(needle in value for needle in needles)
