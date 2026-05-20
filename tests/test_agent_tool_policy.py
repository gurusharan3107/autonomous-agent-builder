"""Tests for Agent chat tool policy helpers."""

from __future__ import annotations

from autonomous_agent_builder.embedded.server.agent_tool_policy import (
    extract_tool_text_payload,
    feature_spec_tool_denial,
    kb_validate_policy,
    normalize_tool_response,
    tool_summary,
)


def test_extract_tool_text_payload_reads_json_text_content() -> None:
    payload = extract_tool_text_payload(
        {"content": [{"type": "text", "text": '{"task_id": "task-1"}'}]}
    )

    assert payload == {"task_id": "task-1"}


def test_normalize_tool_response_classifies_error_payloads() -> None:
    event_type, content = normalize_tool_response({"status": "error", "message": "failed"})

    assert event_type == "tool_error"
    assert '"message": "failed"' in content


def test_kb_validate_policy_rejects_parent_directory_escape(tmp_path) -> None:
    allowed, updated_input, deny_reason, next_action = kb_validate_policy(
        tmp_path,
        {"kb_dir": "../outside"},
    )

    assert allowed is False
    assert updated_input["kb_dir"] == "../outside"
    assert "must stay under `.agent-builder/knowledge/`" in deny_reason
    assert "system-docs" in next_action


def test_feature_spec_tool_denial_blocks_mutating_tools() -> None:
    deny_tool, deny_reason = feature_spec_tool_denial("Bash")

    assert deny_tool is True
    assert "FEATURE_SPEC_JSON" in deny_reason


def test_tool_summary_uses_command_description_for_bash() -> None:
    summary, description = tool_summary(
        "Bash",
        {"command": "npm test", "description": "Run frontend tests"},
    )

    assert summary == "npm test"
    assert description == "Run frontend tests"
