"""Core registry and connector interfaces for FusionDesk AI."""

from .connectors import Connector, ConnectorRequest, ConnectorResponse
from .executive_command_center import ExecutiveCommandCenter
from .execution import ExecutionEngine
from .mission_runtime import MissionRuntime
from .registry import ConnectorCatalog, ModelCatalog, SkillRegistry
from .seats import SeatAssignmentEngine

__all__ = [
    "Connector",
    "ConnectorCatalog",
    "ConnectorRequest",
    "ConnectorResponse",
    "ExecutiveCommandCenter",
    "ExecutionEngine",
    "MissionRuntime",
    "ModelCatalog",
    "SeatAssignmentEngine",
    "SkillRegistry",
]
