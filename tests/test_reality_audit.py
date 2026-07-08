from pathlib import Path

from dashboard.server import run_reality_smoke, runtime_reality_audit


class FakeExecutionEngine:
    def execute(self, *, task, plan, memory_context=None):
        return {
            "ok": True,
            "message": "Smoke test completed with a real execution path.",
            "answer": "Smoke test completed with a real execution path.",
            "execution": {
                "connector": "openrouter",
                "model": "openai/gpt-4o-mini",
                "attempts": [{"ok": True, "model": "openai/gpt-4o-mini"}],
                "fallback_used": False,
            },
        }


def test_reality_audit_labels_placeholder_surfaces():
    audit = runtime_reality_audit()

    components = {item["component"]: item for item in audit["components"]}

    assert audit["ok"] is True
    assert components["Brain"]["status"] == "Not Connected"
    assert components["Agent List / Active Agents"]["status"] == "Not Connected"
    assert components["TradeMaster"]["status"] == "Partial"
    assert "hardcoded" not in components["Missions"]["real"].casefold()


def test_reality_smoke_writes_visible_file(tmp_path):
    result = run_reality_smoke(
        {"task": "Write one line proving the smoke path works."},
        execution_engine=FakeExecutionEngine(),
        output_dir=tmp_path,
    )

    assert result["ok"] is True
    assert result["status"] == "complete"
    assert result["model"] == "openai/gpt-4o-mini"
    output_path = Path(result["output_path"])
    assert output_path.exists()
    text = output_path.read_text()
    assert "FusionDesk Reality Smoke Test" in text
    assert "Smoke test completed with a real execution path." in text


def test_reality_smoke_rejects_empty_task(tmp_path):
    result = run_reality_smoke({"task": ""}, execution_engine=FakeExecutionEngine(), output_dir=tmp_path)

    assert result["ok"] is False
    assert result["status"] == "bad_request"
