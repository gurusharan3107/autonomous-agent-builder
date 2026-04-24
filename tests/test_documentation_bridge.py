from __future__ import annotations

from pathlib import Path

import pytest

from autonomous_agent_builder.agents.documentation_bridge import (
    run_documentation_refresh_bridge,
)


@pytest.mark.asyncio
async def test_bridge_returns_manual_attention_without_invoking_runner(monkeypatch, tmp_path: Path):
    payload = {
        "passed": False,
        "summary": "validation failed",
        "checks": [{"name": "claim_validation", "passed": False, "details": {}}],
        "freshness_report": [],
    }

    async def _unexpected(*args, **kwargs):
        raise AssertionError("runner should not be invoked")

    monkeypatch.setattr(
        "autonomous_agent_builder.agents.documentation_bridge._run_bridge_agent",
        _unexpected,
    )

    result = await run_documentation_refresh_bridge(payload, project_root=tmp_path)

    assert result["status"] == "manual_attention"
    assert result["bridge_invoked"] is False


@pytest.mark.asyncio
async def test_bridge_invokes_documentation_agent_and_parses_json(monkeypatch, tmp_path: Path):
    payload = {
        "passed": False,
        "summary": "1 freshness issue detected",
        "checks": [{"name": "freshness", "passed": False, "details": {}}],
        "freshness_report": [
            {
                "doc_id": "feature-onboarding",
                "doc_type": "feature",
                "status": "stale",
                "blocking": True,
                "stale_reason": "owned_paths changed on main since documented baseline",
                "owned_paths": ["src/onboarding"],
                "matched_changed_paths": ["src/onboarding/service.py"],
                "documented_against_commit": "abc123",
                "current_main_commit": "def456",
            }
        ],
    }

    class _FakeResult:
        session_id = "sdk-session-doc-bridge"
        cost_usd = 0.02
        tokens_input = 12
        tokens_output = 9
        num_turns = 2
        duration_ms = 120
        stop_reason = "stop_sequence"
        error = None
        output_text = (
            '{"status":"updated_and_verified","task_id":"","feature_id":"","system_doc_refresh":"not_needed",'
            '"created_doc_ids":[],"updated_doc_ids":["feature-onboarding"],"retrieval_verified":true,'
            '"validation_status":"pass","remaining_gap":"","summary":"Updated onboarding doc."}'
        )

    captured: dict[str, object] = {}

    async def _fake_run(plan, *, project_root):
        captured["mode"] = plan.mode
        captured["project_root"] = project_root
        return _FakeResult()

    monkeypatch.setattr(
        "autonomous_agent_builder.agents.documentation_bridge._run_bridge_agent",
        _fake_run,
    )

    result = await run_documentation_refresh_bridge(payload, project_root=tmp_path)

    assert captured["mode"] == "run_agent"
    assert captured["project_root"] == tmp_path
    assert result["status"] == "updated_and_verified"
    assert result["bridge_invoked"] is True
    assert result["result"]["updated_doc_ids"] == ["feature-onboarding"]
