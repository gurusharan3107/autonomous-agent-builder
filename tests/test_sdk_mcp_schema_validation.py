"""IMP-026: MCP tool schema validation — self-correcting error messages.

Guards that validate_mcp_args:
- Returns None for valid args (no false positives).
- Returns a self-correcting error envelope when a wrong/unknown param is sent.
- Returns a missing-required-param error when a required param is absent.
- Error messages name the correct param so the model can self-correct.
- Error envelopes set is_error: True so normalize_tool_response classifies
  them as 'tool_error' events, surfacing in `builder logs --error`.
- Schema descriptions on run_tests, read_file, list_directory, task_list
  contain guidance that steers models away from common wrong-param names.
"""

from __future__ import annotations

from autonomous_agent_builder.agents.tools.sdk_mcp import (
    _LIST_DIRECTORY_SCHEMA,
    _PARAM_ALIASES,
    _READ_FILE_SCHEMA,
    _RUN_TESTS_SCHEMA,
    _TASK_LIST_SCHEMA,
    validate_mcp_args,
)
from autonomous_agent_builder.embedded.server.agent_tool_policy import normalize_tool_response

# ── validate_mcp_args: happy-path (None means valid) ─────────────────────────


def test_validate_mcp_args_returns_none_for_valid_run_tests():
    """run_tests with only 'test_pattern' and 'timeout_sec' is valid."""
    result = validate_mcp_args(
        "run_tests",
        _RUN_TESTS_SCHEMA,
        {"test_pattern": "tests/test_foo.py"},
    )
    assert result is None


def test_validate_mcp_args_returns_none_for_empty_args_on_optional_only_schema():
    """run_tests with no args is valid (no required params)."""
    result = validate_mcp_args("run_tests", _RUN_TESTS_SCHEMA, {})
    assert result is None


def test_validate_mcp_args_returns_none_for_valid_read_file():
    result = validate_mcp_args(
        "read_file",
        _READ_FILE_SCHEMA,
        {"file_path": "src/main.py", "start_line": 1, "max_lines": 50},
    )
    assert result is None


def test_validate_mcp_args_returns_none_for_valid_task_list():
    result = validate_mcp_args(
        "task_list",
        _TASK_LIST_SCHEMA,
        {"feature_id": "feat-123"},
    )
    assert result is None


# ── validate_mcp_args: known alias → self-correcting error ───────────────────


def test_validate_mcp_args_corrects_test_p_to_test_pattern():
    """Model sends 'test_p' — must get 'use test_pattern instead' message."""
    result = validate_mcp_args("run_tests", _RUN_TESTS_SCHEMA, {"test_p": "tests/"})
    assert result is not None
    msg = result["content"][0]["text"]
    assert "test_p" in msg
    assert "test_pattern" in msg
    assert "instead" in msg.lower()


def test_validate_mcp_args_corrects_path_to_file_path():
    """Model sends 'path' to read_file — must get 'use file_path instead' message."""
    result = validate_mcp_args("read_file", _READ_FILE_SCHEMA, {"path": "src/main.py"})
    assert result is not None
    msg = result["content"][0]["text"]
    assert "path" in msg
    assert "file_path" in msg


def test_validate_mcp_args_corrects_item_id_to_feature_id_on_task_list():
    """Model sends 'item_id' to task_list — must get 'use feature_id instead' message."""
    result = validate_mcp_args("task_list", _TASK_LIST_SCHEMA, {"item_id": "bitem-42"})
    assert result is not None
    msg = result["content"][0]["text"]
    assert "item_id" in msg
    assert "feature_id" in msg


def test_validate_mcp_args_corrects_path_to_relative_path_on_list_directory():
    """Model sends 'path' to list_directory — must get 'use relative_path instead'."""
    result = validate_mcp_args("list_directory", _LIST_DIRECTORY_SCHEMA, {"path": "src/"})
    assert result is not None
    msg = result["content"][0]["text"]
    assert "path" in msg
    assert "relative_path" in msg


# ── validate_mcp_args: unknown param with close-match suggestion ──────────────


def test_validate_mcp_args_suggests_close_match_for_unknown_param():
    """Unknown param with enough character overlap triggers a 'did you mean' hint."""
    result = validate_mcp_args(
        "read_file",
        _READ_FILE_SCHEMA,
        {"file_path": "src/main.py", "start_ln": 5},  # 'start_ln' → 'start_line'
    )
    assert result is not None
    msg = result["content"][0]["text"]
    assert "start_ln" in msg
    assert "start_line" in msg


def test_validate_mcp_args_unknown_param_no_match_lists_allowed():
    """Completely unrelated param lists allowed params instead of a suggestion."""
    result = validate_mcp_args(
        "run_tests",
        _RUN_TESTS_SCHEMA,
        {"xyz_unknown_param": "value"},
    )
    assert result is not None
    msg = result["content"][0]["text"]
    assert "xyz_unknown_param" in msg
    # Should mention what IS allowed
    assert "test_pattern" in msg or "Allowed params" in msg


# ── validate_mcp_args: missing required param ─────────────────────────────────


def test_validate_mcp_args_reports_missing_required_param():
    """task_list without feature_id must report 'feature_id' is missing."""
    result = validate_mcp_args("task_list", _TASK_LIST_SCHEMA, {"status": "pending"})
    assert result is not None
    msg = result["content"][0]["text"]
    assert "feature_id" in msg
    assert "missing" in msg.lower() or "required" in msg.lower()


def test_validate_mcp_args_reports_missing_required_file_path():
    result = validate_mcp_args("read_file", _READ_FILE_SCHEMA, {"start_line": 1})
    assert result is not None
    msg = result["content"][0]["text"]
    assert "file_path" in msg


# ── is_error envelope: surfaces in builder logs --error ──────────────────────


def test_validate_mcp_args_error_envelope_has_is_error_true():
    """Error envelope must set is_error: True so normalize_tool_response classifies
    it as a tool_error, which is what builder logs --error filters on."""
    result = validate_mcp_args("run_tests", _RUN_TESTS_SCHEMA, {"test_p": "tests/"})
    assert result is not None
    assert result.get("is_error") is True


def test_validate_mcp_args_error_classified_as_tool_error_by_normalize():
    """normalize_tool_response must classify the is_error envelope as tool_error."""
    error_envelope = validate_mcp_args("read_file", _READ_FILE_SCHEMA, {"path": "src/main.py"})
    assert error_envelope is not None
    event_type, _content = normalize_tool_response(error_envelope)
    assert event_type == "tool_error"


# ── schema descriptions: self-correcting guidance in tool descriptions ────────


def test_run_tests_schema_description_mentions_test_pattern():
    """Description for test_pattern must mention the correct param name to prevent
    model from using 'path', 'pattern', or 'test_p'."""
    desc = _RUN_TESTS_SCHEMA["properties"]["test_pattern"]["description"]
    assert "test_pattern" in desc
    # Must warn against the common wrong names
    assert "path" in desc or "test_p" in desc or "pattern" in desc


def test_read_file_schema_description_mentions_file_path():
    desc = _READ_FILE_SCHEMA["properties"]["file_path"]["description"]
    assert "file_path" in desc
    assert "path" in desc  # warns against using 'path'


def test_list_directory_schema_description_mentions_relative_path():
    desc = _LIST_DIRECTORY_SCHEMA["properties"]["relative_path"]["description"]
    assert "relative_path" in desc
    assert "path" in desc  # warns against using 'path'


def test_task_list_schema_description_mentions_feature_id():
    desc = _TASK_LIST_SCHEMA["properties"]["feature_id"]["description"]
    assert "feature_id" in desc
    # Must warn against 'item_id', 'task_id', or 'project_id'
    assert any(wrong in desc for wrong in ("item_id", "task_id", "project_id"))


# ── _PARAM_ALIASES coverage ───────────────────────────────────────────────────


def test_param_aliases_covers_key_run_tests_aliases():
    assert "test_p" in _PARAM_ALIASES.get("run_tests", {})
    assert "path" in _PARAM_ALIASES.get("run_tests", {})


def test_param_aliases_covers_key_read_file_aliases():
    assert "path" in _PARAM_ALIASES.get("read_file", {})
    assert "file" in _PARAM_ALIASES.get("read_file", {})


def test_param_aliases_covers_key_task_list_aliases():
    assert "item_id" in _PARAM_ALIASES.get("task_list", {})
    assert _PARAM_ALIASES["task_list"]["item_id"] == "feature_id"
