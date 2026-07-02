import json
from pathlib import Path

from fusiondesk.core import SeatAssignmentEngine, SkillRegistry


ROOT = Path(__file__).resolve().parents[1]


def test_autoshorts_reference_is_reference_only():
    notes = json.loads((ROOT / "fusiondesk" / "references" / "tool-notes.json").read_text())
    item = next(entry for entry in notes["tools_and_repos"] if entry["name"] == "JayWebtech/autoshorts")

    assert item["category"] == "AI Media"
    assert item["purpose"] == "Long-form video/audio to short-form clips"
    assert item["stack"] == ["Tauri 2", "React", "TSX", "Rust", "SQLite"]
    assert item["integration_status"] == "reference_only"


def test_auto_short_clip_generation_skill_is_registered():
    skill = SkillRegistry.load().get("ai_media.auto_short_clip_generation")

    assert skill["default_mode"] == "RELAY"
    assert skill["required_tools"] == ["local_filesystem"]
    assert skill["optional_tools"] == ["runpod", "openrouter"]
    assert skill["required_seats"] == ["planner", "media_analyzer"]
    assert skill["optional_seats"] == ["copywriter", "reviewer", "judge"]


def test_auto_short_clip_generation_assignment():
    result = SeatAssignmentEngine.load().assign(
        task="auto short clip generation for a TradeMaster recap clip",
        selected_skill="ai_media.auto_short_clip_generation",
    )

    seats = {assignment["seat"] for assignment in result["seat_assignments"]}
    assert result["selected_skill"] == "ai_media.auto_short_clip_generation"
    assert result["mode"] == "RELAY"
    assert "local_filesystem" in result["connectors"]
    assert "runpod" in result["connectors"]
    assert seats == {"planner", "media_analyzer"}

