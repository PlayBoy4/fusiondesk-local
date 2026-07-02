"""Load FusionDesk skill and connector manifests without provider coupling."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILL_REGISTRY = ROOT / "skills" / "registry.json"
DEFAULT_CONNECTOR_REGISTRY = ROOT / "connectors" / "registry.json"
DEFAULT_MODEL_PROFILES = ROOT / "models" / "profiles.json"


@dataclass(frozen=True)
class SkillRegistry:
    data: dict[str, Any]

    @classmethod
    def load(cls, path: Path | None = None) -> "SkillRegistry":
        return cls(_load_json(path or DEFAULT_SKILL_REGISTRY))

    @property
    def skills(self) -> list[dict[str, Any]]:
        return list(self.data.get("skills", []))

    def get(self, skill_id: str) -> dict[str, Any]:
        for skill in self.skills:
            if skill.get("id") == skill_id:
                return skill
        raise KeyError(f"Unknown FusionDesk skill: {skill_id}")

    def by_module(self, module: str) -> list[dict[str, Any]]:
        return [skill for skill in self.skills if skill.get("module") == module]

    def by_category(self, category: str) -> list[dict[str, Any]]:
        return [skill for skill in self.skills if skill.get("category") == category]

    def match_triggers(self, text: str) -> list[dict[str, Any]]:
        query = text.casefold()
        matches = []
        for skill in self.skills:
            phrases = skill.get("trigger_phrases", [])
            if any(phrase.casefold() in query for phrase in phrases):
                matches.append(skill)
        return matches


@dataclass(frozen=True)
class ConnectorCatalog:
    data: dict[str, Any]

    @classmethod
    def load(cls, path: Path | None = None) -> "ConnectorCatalog":
        return cls(_load_json(path or DEFAULT_CONNECTOR_REGISTRY))

    @property
    def connectors(self) -> list[dict[str, Any]]:
        return list(self.data.get("connectors", []))

    def get(self, connector_id: str) -> dict[str, Any]:
        for connector in self.connectors:
            if connector.get("id") == connector_id:
                return connector
        raise KeyError(f"Unknown FusionDesk connector: {connector_id}")

    def supports(self, connector_id: str, capability: str) -> bool:
        connector = self.get(connector_id)
        return capability in connector.get("capabilities", [])


@dataclass(frozen=True)
class ModelCatalog:
    data: dict[str, Any]

    @classmethod
    def load(cls, path: Path | None = None) -> "ModelCatalog":
        return cls(_load_json(path or DEFAULT_MODEL_PROFILES))

    @property
    def profiles(self) -> list[dict[str, Any]]:
        return list(self.data.get("profiles", []))

    def get(self, model_id: str) -> dict[str, Any]:
        for profile in self.profiles:
            if profile.get("id") == model_id:
                return profile
        raise KeyError(f"Unknown FusionDesk model profile: {model_id}")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
