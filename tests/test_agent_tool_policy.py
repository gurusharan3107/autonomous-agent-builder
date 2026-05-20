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


def test_normalize_tool_response_keeps_success_with_nested_gate_errors() -> None:
    # Regression: mcp__builder__task_show returns a successful task payload that
    # legitimately includes gate_results with status="error" for failed gates.
    # The classifier must look at the envelope, not substring-scan the body.
    task_show_success = {
        "schema_version": "1",
        "id": "t1",
        "status": "blocked",
        "blocked_reason": "Gate infrastructure error in code_quality, testing",
        "gate_results": [
            {"gate_name": "testing", "status": "error"},
            {"gate_name": "code_quality", "status": "error"},
        ],
    }

    event_type, _ = normalize_tool_response(task_show_success)

    assert event_type == "tool_result"


def test_normalize_tool_response_honours_sdk_is_error_blocks() -> None:
    sdk_error_blocks = [{"type": "text", "text": "denied", "is_error": True}]
    sdk_success_blocks = [
        {
            "type": "text",
            "text": '{"status": "blocked", "gate_results": [{"status": "error"}]}',
        }
    ]

    err_type, _ = normalize_tool_response(sdk_error_blocks)
    ok_type, _ = normalize_tool_response(sdk_success_blocks)

    assert err_type == "tool_error"
    assert ok_type == "tool_result"


def test_normalize_tool_response_treats_string_error_prefix_as_error() -> None:
    event_type, _ = normalize_tool_response("Error: something failed")
    traceback_type, _ = normalize_tool_response("Traceback (most recent call last):")

    assert event_type == "tool_error"
    assert traceback_type == "tool_error"


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
