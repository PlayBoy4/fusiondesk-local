#!/usr/bin/env python3
"""Validate FusionDesk registry manifests with stdlib checks."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_PATH = ROOT / "fusiondesk" / "skills" / "registry.json"
CONNECTORS_PATH = ROOT / "fusiondesk" / "connectors" / "registry.json"
MODELS_PATH = ROOT / "fusiondesk" / "models" / "profiles.json"
TRADEMASTER_PATH = ROOT / "fusiondesk" / "modules" / "trademaster" / "manifest.json"
SOCIAL_STUDIO_PATH = ROOT / "fusiondesk" / "modules" / "social_studio" / "manifest.json"
NOTES_PATH = ROOT / "fusiondesk" / "references" / "tool-notes.json"

REQUIRED_SKILL_FIELDS = {
    "name",
    "category",
    "description",
    "trigger_phrases",
    "required_tools",
    "input_schema",
    "output_schema",
    "default_mode",
    "required_seats",
    "optional_seats",
    "preferred_model_traits",
    "recommended_model_seats",
    "safety_risk_notes",
    "examples",
}
VALID_MODES = {"SOLO", "RELAY", "PANEL", "TRINITY"}
VALID_SEATS = {
    "planner",
    "researcher",
    "builder",
    "reviewer",
    "risk_checker",
    "clarity_writer",
    "judge",
    "memory",
    "evidence_checker",
    "media_analyzer",
    "copywriter",
    "ads_auditor",
    "data_analyst",
    "creative_director",
    "seo_optimizer",
    "brand_guard",
    "knowledge_architect",
}
MODEL_PROFILE_TRAITS = {
    "coding_strength",
    "reasoning_strength",
    "research_strength",
    "writing_strength",
    "speed",
    "cost_tier",
    "context_length",
    "reliability",
}
VALID_MODEL_TRAITS = MODEL_PROFILE_TRAITS | {"reasoning", "marketing", "analysis", "writing"}
REQUIRED_CONNECTOR_FIELDS = {
    "id",
    "name",
    "category",
    "status",
    "description",
    "required_config",
    "capabilities",
    "risk_notes",
}
REQUIRED_MODEL_FIELDS = {
    "id",
    "display_name",
    "coding_strength",
    "reasoning_strength",
    "research_strength",
    "writing_strength",
    "speed",
    "cost_tier",
    "context_length",
    "reliability",
    "preferred_use_cases",
}


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_skills() -> tuple[set[str], set[str]]:
    data = load_json(SKILLS_PATH)
    skills = data.get("skills", [])
    if not skills:
        raise SystemExit("No skills found")

    skill_ids: set[str] = set()
    connector_refs: set[str] = set()

    for skill in skills:
        skill_id = skill.get("id")
        if not skill_id:
            raise SystemExit(f"Skill missing id: {skill}")
        if skill_id in skill_ids:
            raise SystemExit(f"Duplicate skill id: {skill_id}")
        skill_ids.add(skill_id)

        missing = REQUIRED_SKILL_FIELDS - skill.keys()
        if missing:
            raise SystemExit(f"{skill_id} missing fields: {sorted(missing)}")

        if skill["default_mode"] not in VALID_MODES:
            raise SystemExit(f"{skill_id} has invalid mode: {skill['default_mode']}")
        if not set(skill["required_seats"]) <= VALID_SEATS:
            raise SystemExit(f"{skill_id} has invalid required seats: {skill['required_seats']}")
        if not set(skill["optional_seats"]) <= VALID_SEATS:
            raise SystemExit(f"{skill_id} has invalid optional seats: {skill['optional_seats']}")
        if not set(skill["preferred_model_traits"]) <= VALID_MODEL_TRAITS:
            raise SystemExit(f"{skill_id} has invalid preferred model traits: {skill['preferred_model_traits']}")
        if not skill["trigger_phrases"]:
            raise SystemExit(f"{skill_id} has no trigger phrases")
        if not skill["required_seats"]:
            raise SystemExit(f"{skill_id} has no required seats")
        if not skill["preferred_model_traits"]:
            raise SystemExit(f"{skill_id} has no preferred model traits")
        if not skill["recommended_model_seats"]:
            raise SystemExit(f"{skill_id} has no model seats")
        if not skill["examples"]:
            raise SystemExit(f"{skill_id} has no examples")

        connector_refs.update(skill.get("required_tools", []))
        connector_refs.update(skill.get("optional_tools", []))

    return skill_ids, connector_refs


def validate_connectors(connector_refs: set[str]) -> set[str]:
    data = load_json(CONNECTORS_PATH)
    connectors = data.get("connectors", [])
    if not connectors:
        raise SystemExit("No connectors found")

    connector_ids: set[str] = set()
    for connector in connectors:
        connector_id = connector.get("id")
        if not connector_id:
            raise SystemExit(f"Connector missing id: {connector}")
        if connector_id in connector_ids:
            raise SystemExit(f"Duplicate connector id: {connector_id}")
        connector_ids.add(connector_id)

        missing = REQUIRED_CONNECTOR_FIELDS - connector.keys()
        if missing:
            raise SystemExit(f"{connector_id} missing fields: {sorted(missing)}")
        if not connector["capabilities"]:
            raise SystemExit(f"{connector_id} has no capabilities")

    missing_refs = connector_refs - connector_ids
    if missing_refs:
        raise SystemExit(f"Skills reference undefined connectors: {sorted(missing_refs)}")

    return connector_ids


def validate_models() -> set[str]:
    data = load_json(MODELS_PATH)
    models = data.get("profiles", [])
    if not models:
        raise SystemExit("No model profiles found")

    model_ids: set[str] = set()
    for model in models:
        model_id = model.get("id")
        if not model_id:
            raise SystemExit(f"Model missing id: {model}")
        if model_id in model_ids:
            raise SystemExit(f"Duplicate model id: {model_id}")
        model_ids.add(model_id)

        missing = REQUIRED_MODEL_FIELDS - model.keys()
        if missing:
            raise SystemExit(f"{model_id} missing fields: {sorted(missing)}")
        if model["cost_tier"] not in {"cheap", "balanced", "premium"}:
            raise SystemExit(f"{model_id} has invalid cost tier: {model['cost_tier']}")
        for trait in MODEL_PROFILE_TRAITS - {"cost_tier"}:
            value = model[trait]
            if not isinstance(value, int | float) or value < 1 or value > 10:
                raise SystemExit(f"{model_id} has invalid {trait}: {value}")

    return model_ids


def validate_trademaster(skill_ids: set[str]) -> None:
    manifest = load_json(TRADEMASTER_PATH)
    missing = set(manifest.get("skill_ids", [])) - skill_ids
    if missing:
        raise SystemExit(f"TradeMaster manifest references missing skills: {sorted(missing)}")
    if manifest.get("status") != "definition_only":
        raise SystemExit("TradeMaster should remain definition_only until integration is explicit")


def validate_social_studio(skill_ids: set[str], connector_ids: set[str]) -> None:
    manifest = load_json(SOCIAL_STUDIO_PATH)
    missing_skills = set(manifest.get("skill_ids", [])) - skill_ids
    if missing_skills:
        raise SystemExit(f"Social Studio manifest references missing skills: {sorted(missing_skills)}")
    missing_connectors = set(manifest.get("connector_dependencies", [])) - connector_ids
    if missing_connectors:
        raise SystemExit(f"Social Studio manifest references missing connectors: {sorted(missing_connectors)}")
    if manifest.get("status") != "definition_only":
        raise SystemExit("Social Studio should remain definition_only until integration is explicit")


def validate_notes() -> None:
    notes = load_json(NOTES_PATH)
    names = {item["name"] for item in notes.get("tools_and_repos", [])}
    required = {"G0DM0D3", "FLUX Fusion", "Ponytail", "Wan2GP", "VoxCPM2", "OBLITERATUS", "OpenRouter", "RunPod"}
    missing = required - names
    if missing:
        raise SystemExit(f"Missing reference notes: {sorted(missing)}")


def main() -> None:
    skill_ids, connector_refs = validate_skills()
    connector_ids = validate_connectors(connector_refs)
    model_ids = validate_models()
    validate_trademaster(skill_ids)
    validate_social_studio(skill_ids, connector_ids)
    validate_notes()
    print(f"FusionDesk registry OK: {len(skill_ids)} skills, {len(connector_ids)} connectors, {len(model_ids)} model profiles")


if __name__ == "__main__":
    main()
