from dashboard.server import seat_assignment


def test_dashboard_seat_assignment_smoke():
    result = seat_assignment(
        {
            "task": "research competitor AI dashboards with sources",
            "skill": "research.web_research",
            "mode": "PANEL",
            "costPreference": "balanced",
            "qualityPreference": "highest_quality",
        }
    )

    assert result["ok"] is True
    assert result["selected_skill"] == "research.web_research"
    assert result["mode"] == "PANEL"
    assert "agent_reach" in result["connectors"]
    assert result["seat_assignments"]
    assert "confidence" in result


def test_dashboard_seat_assignment_rejects_missing_task():
    assert seat_assignment({}) == {"ok": False, "message": "Task is required."}

