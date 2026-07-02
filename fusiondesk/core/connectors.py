"""Common connector interface used by FusionDesk orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ConnectorRequest:
    connector_id: str
    capability: str
    action: str
    input: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConnectorResponse:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    evidence: list[Any] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cost: dict[str, Any] = field(default_factory=dict)


class Connector(Protocol):
    """All external tools must be wrapped behind this protocol."""

    connector_id: str

    def health(self) -> ConnectorResponse:
        """Return readiness, missing config, or degradation notes."""

    def capabilities(self) -> ConnectorResponse:
        """Return capabilities supported by this connector implementation."""

    def invoke(self, request: ConnectorRequest) -> ConnectorResponse:
        """Run one normalized connector action."""

