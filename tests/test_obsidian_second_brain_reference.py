import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def test_obsidian_second_brain_reference_is_definition_only():
    notes = load_json("fusiondesk/references/tool-notes.json")
    item = next(
        note for note in notes["tools_and_repos"] if note["name"] == "eugeniughelbur/obsidian-second-brain"
    )

    assert item["category"] == "Knowledge / Memory"
    assert item["license"] == "MIT"
    assert item["version"] == "v0.10 The Architect"
    assert item["integration_status"] == "reference_only"
    assert item["install_status"] == "not_installed"
    assert item["repo"] == "https://github.com/eugeniughelbur/obsidian-second-brain"
    assert any("Back up" in note or "back up" in note for note in item["notes"])


def test_obsidian_skills_are_definition_only_with_knowledge_architect_seat():
    registry = load_json("fusiondesk/skills/registry.json")
    skills = {skill["id"]: skill for skill in registry["skills"]}
    expected = {
        "obsidian_save_session",
        "obsidian_ingest_source",
        "obsidian_reconcile_notes",
        "obsidian_synthesize_patterns",
        "obsidian_project_architect",
        "obsidian_daily_review",
    }

    assert expected <= set(skills)
    for skill_id in expected:
        skill = skills[skill_id]
        assert skill["category"] == "Knowledge"
        assert skill["default_mode"] == "PANEL"
        assert skill["status"] == "definition_only"
        assert skill["required_tools"] == ["local_filesystem"]
        assert skill["optional_tools"] == ["agent_reach", "openrouter"]
        assert skill["required_seats"] == ["planner", "knowledge_architect", "reviewer", "judge"]
        assert skill["optional_seats"] == []
