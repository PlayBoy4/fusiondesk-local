import json
from pathlib import Path

from fusiondesk.core import ConnectorCatalog, SeatAssignmentEngine, SkillRegistry


ROOT = Path(__file__).resolve().parents[1]


def test_social_studio_manifest_is_definition_only():
    manifest = json.loads((ROOT / "fusiondesk" / "modules" / "social_studio" / "manifest.json").read_text())

    assert manifest["module_id"] == "social_studio"
    assert manifest["status"] == "definition_only"
    assert len(manifest["skill_ids"]) == 15
    assert "client" in manifest["approval_modes"]
    assert "memory_feedback" in manifest["analytics_loop"]


def test_social_connectors_are_registered_as_planned():
    catalog = ConnectorCatalog.load()
    connector_ids = {connector["id"] for connector in catalog.connectors}

    expected = {
        "social_instagram",
        "social_facebook",
        "social_linkedin",
        "social_threads",
        "social_youtube",
        "social_tiktok",
    }
    assert expected <= connector_ids
    assert catalog.get("social_instagram")["category"] == "social_publishing"


def test_social_studio_skills_are_registered():
    registry = SkillRegistry.load()
    skills = registry.by_module("social_studio")

    assert len(skills) == 15
    assert registry.get("social_studio.social_strategy")["default_mode"] == "PANEL"
    assert registry.get("social_studio.approval_workflow")["status"] == "definition_only"
    assert "social_youtube" in registry.get("social_studio.short_video_generation")["optional_tools"]


def test_social_strategy_assignment_uses_panel_and_connectors():
    result = SeatAssignmentEngine.load().assign(
        task="social strategy for daycare marketing with competitor research",
        selected_skill="social_studio.social_strategy",
    )

    seats = {assignment["seat"] for assignment in result["seat_assignments"]}
    assert result["selected_skill"] == "social_studio.social_strategy"
    assert result["mode"] == "PANEL"
    assert {"planner", "researcher", "brand_guard"} <= seats
    assert "agent_reach" in result["connectors"]
    assert "openrouter" in result["connectors"]


def test_social_analytics_assignment_keeps_feedback_loop_seats():
    result = SeatAssignmentEngine.load().assign(
        task="social analytics report with views CTR watch time comments followers and conversions",
        selected_skill="social_studio.social_analytics",
    )

    seats = {assignment["seat"] for assignment in result["seat_assignments"]}
    assert result["selected_skill"] == "social_studio.social_analytics"
    assert "data_analyst" in seats
    assert "judge" in seats

