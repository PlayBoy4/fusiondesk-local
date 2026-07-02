from fusiondesk.core import SeatAssignmentEngine, SkillRegistry


def test_paid_ads_audit_skill_definition():
    skill = SkillRegistry.load().get("paid_ads_audit")

    assert skill["category"] == "Marketing"
    assert skill["default_mode"] == "PANEL"
    assert skill["status"] == "definition_only"
    assert skill["connectors"]["required"] == ["local_filesystem"]
    assert skill["connectors"]["optional"] == ["openrouter", "browser_automation", "agent_reach"]
    assert skill["required_seats"] == [
        "planner",
        "ads_auditor",
        "data_analyst",
        "copywriter",
        "reviewer",
        "judge",
    ]
    assert skill["optional_seats"] == ["creative_director", "seo_optimizer", "brand_guard"]
    assert skill["preferred_model_traits"] == ["reasoning", "marketing", "analysis", "writing"]


def test_paid_ads_audit_panel_assignment():
    result = SeatAssignmentEngine.load().assign(
        task="paid ads audit for Google Ads wasted spend detection",
        selected_skill="paid_ads_audit",
    )

    seats = [assignment["seat"] for assignment in result["seat_assignments"]]
    assert result["selected_skill"] == "paid_ads_audit"
    assert result["mode"] == "PANEL"
    assert "local_filesystem" in result["connectors"]
    assert seats == [
        "planner",
        "ads_auditor",
        "data_analyst",
        "copywriter",
        "reviewer",
        "judge",
    ]

