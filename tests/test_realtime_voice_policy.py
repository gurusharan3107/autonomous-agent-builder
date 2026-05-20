"""Realtime voice policy and tool-description contract tests."""

from __future__ import annotations

from autonomous_agent_builder.embedded.server.routes import realtime
from autonomous_agent_builder.services.realtime_voice_policy import (
    DEFAULT_REALTIME_VOICE_POLICY,
    VOICE_OPERATOR_INSTRUCTIONS,
)


def test_realtime_voice_policy_defaults_to_cost_efficient_model():
    assert DEFAULT_REALTIME_VOICE_POLICY.model == "gpt-realtime-mini"
    assert DEFAULT_REALTIME_VOICE_POLICY.noise_reduction_type == "far_field"
    assert DEFAULT_REALTIME_VOICE_POLICY.turn_detection_type == "server_vad"
    assert DEFAULT_REALTIME_VOICE_POLICY.turn_detection_create_response is True
    assert DEFAULT_REALTIME_VOICE_POLICY.turn_detection_threshold == 0.5
    assert DEFAULT_REALTIME_VOICE_POLICY.turn_detection_prefix_padding_ms == 300
    assert DEFAULT_REALTIME_VOICE_POLICY.turn_detection_silence_duration_ms == 500
    assert DEFAULT_REALTIME_VOICE_POLICY.retention_ratio == 0.8


def test_realtime_voice_policy_instructions_route_operator_requests_to_tools():
    assert "You are Samantha" in VOICE_OPERATOR_INSTRUCTIONS
    assert "Address yourself as Samantha" in VOICE_OPERATOR_INSTRUCTIONS
    assert "Do not call yourself a generic Realtime voice AI" in VOICE_OPERATOR_INSTRUCTIONS
    assert "Do not require\ndesignated phrases" in VOICE_OPERATOR_INSTRUCTIONS
    assert "infer intent" in VOICE_OPERATOR_INSTRUCTIONS
    assert "ordinary speech" in VOICE_OPERATOR_INSTRUCTIONS
    assert "Use wait_for_user silently only for silence" in VOICE_OPERATOR_INSTRUCTIONS
    assert "Do not use Realtime to do heavy lifting." in VOICE_OPERATOR_INSTRUCTIONS
    assert "current runtime" in VOICE_OPERATOR_INSTRUCTIONS
    assert "provider-limit run status" in VOICE_OPERATOR_INSTRUCTIONS
    assert "Treat every Board/status utterance as fresh" in VOICE_OPERATOR_INSTRUCTIONS
    assert "Do not call a task active just because its status is implementation" in (
        VOICE_OPERATOR_INSTRUCTIONS
    )
    assert "use those lane names exactly" in VOICE_OPERATOR_INSTRUCTIONS
    assert "Never answer an addressed operator request from your own memory" in (
        " ".join(VOICE_OPERATOR_INSTRUCTIONS.split())
    )
    assert "Do not leave the operator guessing whether you heard them." in (
        " ".join(VOICE_OPERATOR_INSTRUCTIONS.split())
    )
    assert "ask a concise clarification question instead" in VOICE_OPERATOR_INSTRUCTIONS
    assert "First acknowledge in plain speech" in " ".join(VOICE_OPERATOR_INSTRUCTIONS.split())
    assert "I'll check with Builder" in VOICE_OPERATOR_INSTRUCTIONS
    assert "background" in VOICE_OPERATOR_INSTRUCTIONS
    assert "audio" in VOICE_OPERATOR_INSTRUCTIONS
    assert "Agent page records\n  the operator question" in VOICE_OPERATOR_INSTRUCTIONS
    assert "Builder is idle when board_status reports blocked tasks" in (
        " ".join(VOICE_OPERATOR_INSTRUCTIONS.split())
    )
    assert "Direct Realtime tools are for cheap, deterministic, auditable one-step" in (
        VOICE_OPERATOR_INSTRUCTIONS
    )
    assert "recovering a blocked Board task" in VOICE_OPERATOR_INSTRUCTIONS
    assert "dispatching a\n  dispatchable Board task" in VOICE_OPERATOR_INSTRUCTIONS
    assert "opening an existing run trace" in VOICE_OPERATOR_INSTRUCTIONS
    assert "navigate_dashboard" in VOICE_OPERATOR_INSTRUCTIONS
    assert "open_run_trace" in VOICE_OPERATOR_INSTRUCTIONS
    assert "dispatch_board_task" in VOICE_OPERATOR_INSTRUCTIONS
    assert 'intent="open_only"' in VOICE_OPERATOR_INSTRUCTIONS
    assert 'intent="open_then_analyze"' in VOICE_OPERATOR_INSTRUCTIONS
    assert "Preserve all details, constraints, and sub-questions" in VOICE_OPERATOR_INSTRUCTIONS
    assert "do not compress multi-part analysis requests" in VOICE_OPERATOR_INSTRUCTIONS
    assert "Treat each new operator utterance as its own request" in VOICE_OPERATOR_INSTRUCTIONS
    assert "the URL already points at a trace" in VOICE_OPERATOR_INSTRUCTIONS
    assert "call open_run_trace again with\n  the new analysis_request" in VOICE_OPERATOR_INSTRUCTIONS
    assert (
        '"analysis_request": "Analyze the current agent run. Was it efficient? Also tell me what to do next."'
        in VOICE_OPERATOR_INSTRUCTIONS
    )
    assert "resolved run id and task id" in " ".join(VOICE_OPERATOR_INSTRUCTIONS.split())
    assert "Do not analyze the trace in Realtime" in " ".join(VOICE_OPERATOR_INSTRUCTIONS.split())
    assert "call get_builder_agent_update" in VOICE_OPERATOR_INSTRUCTIONS
    assert "Do not treat latest_voice_summary as the current answer by itself" in (
        VOICE_OPERATOR_INSTRUCTIONS
    )
    assert "sprint counts" in VOICE_OPERATOR_INSTRUCTIONS
    assert "fresh factual\n  Board/sprint/approval question" in VOICE_OPERATOR_INSTRUCTIONS
    assert "logs, metrics, observability, failure diagnosis" in VOICE_OPERATOR_INSTRUCTIONS
    assert "failure diagnosis" in VOICE_OPERATOR_INSTRUCTIONS
    assert "auditable board and log verification" in VOICE_OPERATOR_INSTRUCTIONS
    assert "Check how many sprints there are" in VOICE_OPERATOR_INSTRUCTIONS
    assert "delegate_to_builder_agent" in VOICE_OPERATOR_INSTRUCTIONS
    assert 'thread_mode="new"' in VOICE_OPERATOR_INSTRUCTIONS
    assert 'thread_mode="current"' in VOICE_OPERATOR_INSTRUCTIONS
    assert "latest_voice_summary" in VOICE_OPERATOR_INSTRUCTIONS
    assert "Do not inspect or narrate raw tool calls" in VOICE_OPERATOR_INSTRUCTIONS
    assert "call prepare_high_risk_decision first" in VOICE_OPERATOR_INSTRUCTIONS
    assert "before calling confirm_high_risk_action" in VOICE_OPERATOR_INSTRUCTIONS
    assert "switch_builder_runtime" in VOICE_OPERATOR_INSTRUCTIONS
    assert "future runs only" in VOICE_OPERATOR_INSTRUCTIONS
    status_tool = next(
        tool for tool in realtime.TOOL_DEFINITIONS if tool["name"] == "get_builder_agent_update"
    )
    delegation_tool = next(
        tool for tool in realtime.TOOL_DEFINITIONS if tool["name"] == "delegate_to_builder_agent"
    )
    runtime_tool = next(
        tool for tool in realtime.TOOL_DEFINITIONS if tool["name"] == "switch_builder_runtime"
    )
    navigation_tool = next(
        tool for tool in realtime.TOOL_DEFINITIONS if tool["name"] == "navigate_dashboard"
    )
    recover_tool = next(
        tool for tool in realtime.TOOL_DEFINITIONS if tool["name"] == "recover_board_task"
    )
    dispatch_tool = next(
        tool for tool in realtime.TOOL_DEFINITIONS if tool["name"] == "dispatch_board_task"
    )
    run_trace_tool = next(
        tool for tool in realtime.TOOL_DEFINITIONS if tool["name"] == "open_run_trace"
    )
    assert "simple factual status checks" in status_tool["description"]
    assert "current runtime" in status_tool["description"]
    assert "sprint counts" in status_tool["description"]
    assert "provider-limit run status" in status_tool["description"]
    assert "logs/metrics/observability" in status_tool["description"]
    assert "use delegate_to_builder_agent" in status_tool["description"]
    assert "logs/metrics/observability diagnosis" in delegation_tool["description"]
    assert "Do not use this for simple Board/sprint counts" in delegation_tool["description"]
    assert "failure diagnosis" in delegation_tool["description"]
    assert "interpretation beyond the compact status digest" in delegation_tool["description"]
    assert "operator's exact request" in delegation_tool["description"]
    assert "Omit wait_for_completion" in delegation_tool["description"]
    assert "Do not rewrite" in VOICE_OPERATOR_INSTRUCTIONS
    assert "completion is event-driven" in " ".join(VOICE_OPERATOR_INSTRUCTIONS.split())
    assert "I want to improve the todo app so I can search tasks by text." in VOICE_OPERATOR_INSTRUCTIONS
    assert runtime_tool["parameters"]["properties"]["sdk"]["enum"] == ["codex_sdk", "claude"]
    assert "future runs only" in runtime_tool["description"]
    assert "simple operator request" in navigation_tool["description"]
    assert navigation_tool["parameters"]["required"] == ["target"]
    assert "last optimization run" in run_trace_tool["description"]
    assert "does not analyze logs" in run_trace_tool["description"]
    assert run_trace_tool["parameters"]["properties"]["intent"]["enum"] == [
        "open_only",
        "open_then_analyze",
    ]
    assert "analysis_request" in run_trace_tool["parameters"]["properties"]
    assert "immediately through" in recover_tool["description"]
    assert "dispatchable Board task" in dispatch_tool["description"]
