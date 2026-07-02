from fusiondesk.core import SeatAssignmentEngine


def engine() -> SeatAssignmentEngine:
    return SeatAssignmentEngine.load()


def test_coding_task_assignment():
    result = engine().assign(
        task="fix bug in this repo and add tests",
        selected_skill="development.bug_fixing",
        mode="TRINITY",
        cost_preference="balanced",
    )

    seats = {assignment["seat"]: assignment["model"] for assignment in result["seat_assignments"]}
    assert result["selected_skill"] == "development.bug_fixing"
    assert result["mode"] == "TRINITY"
    assert "github" in result["connectors"]
    assert "local_filesystem" in result["connectors"]
    assert "builder" in seats
    assert seats["builder"] in {"claude-sonnet", "gpt-4.1"}


def test_trading_task_assignment():
    result = engine().assign(
        task="live market analysis for SPY premium into premarket",
        selected_skill="trademaster.live_market_analysis",
    )

    seats = {assignment["seat"] for assignment in result["seat_assignments"]}
    assert result["selected_skill"] == "trademaster.live_market_analysis"
    assert result["mode"] == "TRINITY"
    assert "polygon_io" in result["connectors"]
    assert "agent_reach" in result["connectors"]
    assert {"researcher", "risk_checker", "judge"} <= seats


def test_marketing_task_assignment():
    result = engine().assign(
        task="write ad copy for a FusionDesk AI dashboard launch",
        selected_skill="marketing.ad_copy",
    )

    seats = {assignment["seat"] for assignment in result["seat_assignments"]}
    assert result["selected_skill"] == "marketing.ad_copy"
    assert "clarity_writer" in seats
    assert "reviewer" in seats
    assert "openrouter" in result["connectors"]


def test_research_task_assignment():
    result = engine().assign(
        task="web research on competitor AI dashboards with sources",
        selected_skill="research.web_research",
    )

    seats = {assignment["seat"] for assignment in result["seat_assignments"]}
    assert result["selected_skill"] == "research.web_research"
    assert "agent_reach" in result["connectors"]
    assert {"researcher", "evidence_checker"} <= seats


def test_connector_aware_routing():
    result = engine().assign(
        task="compare repo code, live market data, and video generation workflow",
        selected_skill="orchestration.panel",
        connector_requirements=["browser_automation"],
    )

    assert "github" in result["connectors"]
    assert "local_filesystem" in result["connectors"]
    assert "polygon_io" in result["connectors"]
    assert "runpod" in result["connectors"]
    assert "browser_automation" in result["connectors"]
    assert "openrouter" in result["connectors"]


def test_cheapest_mode():
    result = engine().assign(
        task="code review this small diff",
        selected_skill="development.code_review",
        cost_preference="cheapest",
        quality_preference="cheapest",
    )

    models = {assignment["model"] for assignment in result["seat_assignments"]}
    assert result["estimated_cost_tier"] == "cheapest"
    assert models <= {"claude-haiku", "gpt-4.1-mini", "deepseek-chat", "qwen-local"}


def test_premium_mode():
    result = engine().assign(
        task="high-stakes risk review and judge this architecture",
        selected_skill="development.repo_architecture_analysis",
        cost_preference="premium",
        quality_preference="highest_quality",
    )

    models = {assignment["model"] for assignment in result["seat_assignments"]}
    assert result["estimated_cost_tier"] == "premium"
    assert models & {"claude-opus", "gemini-2.5-pro"}


def test_missing_model_fallback():
    result = engine().assign(
        task="summarize this note",
        selected_skill="orchestration.solo",
        available_models=["unknown-local-model"],
    )

    assert result["seat_assignments"][0]["model"] == "unknown-local-model"
    assert result["confidence"] < 0.97
    assert result["warnings"]


def test_unsupported_skill_fallback():
    result = engine().assign(
        task="do something simple",
        selected_skill="not.a.real.skill",
    )

    assert result["selected_skill"] == "orchestration.solo"
    assert result["mode"] == "SOLO"
    assert result["confidence"] < 0.6
    assert result["warnings"]

