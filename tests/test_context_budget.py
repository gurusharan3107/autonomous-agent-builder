from __future__ import annotations

import json

from autonomous_agent_builder.services.context_budget import (
    build_agent_context_budget,
    build_realtime_tool_context_budget,
    summarize_context_budgets,
)


def test_agent_context_budget_estimates_components_without_raw_prompt_content():
    payload = build_agent_context_budget(
        agent_name="agent-chat",
        prompt="SYSTEM PROMPT secret-owner-detail\nUser: why is observability missing context?",
        user_message="why is observability missing context?",
        recent_context="recent assistant trace",
        documentation_context={"doc": "REFERENCE", "content": "single owner map"},
        observability_context="missing signal context_budget",
        runtime_metadata={
            "runtime_sdk": "codex_sdk",
            "provider": "codex_subscription",
            "model": "gpt-5.5",
            "effort": "medium",
        },
        resume_session="session-1",
        specialist_active=True,
    )

    serialized = json.dumps(payload, sort_keys=True)

    assert payload["lane"] == "sdk_agent"
    assert payload["stage"] == "agent_prompt_assembly"
    assert payload["total_estimated_tokens"] == sum(
        item["estimated_tokens"] for item in payload["component_estimates"]
    )
    assert payload["signal_category"] in {"high", "mixed"}
    assert payload["privacy_policy"] == "local_estimates_no_raw_prompt_or_tool_content"
    assert "secret-owner-detail" not in serialized
    assert "why is observability missing context?" not in serialized
    assert any(item["name"] == "final_prompt" for item in payload["component_estimates"])


def test_context_budget_summary_groups_lanes_stages_signals_and_components():
    runtime = {
        "runtime_sdk": "codex_sdk",
        "provider": "codex_subscription",
        "model": "gpt-5.5",
        "effort": "medium",
    }
    agent_budget = build_agent_context_budget(
        agent_name="agent-chat",
        prompt="summarize status",
        user_message="summarize status",
        recent_context="recent event",
        documentation_context=None,
        observability_context="bounded observability facts",
        runtime_metadata=runtime,
        resume_session=None,
        specialist_active=False,
    )
    realtime_budget = build_realtime_tool_context_budget(
        call_id="rtc-1",
        tool_call={
            "name": "get_builder_agent_update",
            "call_id": "tool-1",
            "arguments": json.dumps({"status_prompt": "current sprint status"}),
        },
        output={"ok": True, "result": {"voice_digest": "Ready"}},
        runtime_metadata=runtime,
    )

    summary = summarize_context_budgets([agent_budget, realtime_budget])

    assert summary["available"] is True
    assert summary["event_count"] == 2
    assert summary["total_estimated_tokens"] == (
        agent_budget["total_estimated_tokens"] + realtime_budget["total_estimated_tokens"]
    )
    assert {item["lane"] for item in summary["by_lane"]} == {"sdk_agent", "realtime_voice"}
    assert {item["stage"] for item in summary["by_stage"]} == {
        "agent_prompt_assembly",
        "realtime_tool_exchange",
    }
    assert any(item["signal_category"] == "useful_tool_result" for item in summary["signal_counts"])
    assert (
        summary["top_components"][0]["estimated_tokens"]
        >= summary["top_components"][-1]["estimated_tokens"]
    )
    assert summary["latest"]["correlation_id"] == "tool-1"
