"""Tests for SDK hooks — workspace boundary, bash argv, audit log."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from autonomous_agent_builder.agents.hooks import (
    _sanitize_for_log,
    audit_log_tool_use,
    enforce_workspace_boundary,
    validate_bash_argv,
)


@pytest.mark.asyncio
class TestWorkspaceBoundary:
    async def test_allows_write_within_workspace(self):
        hook_input = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/workspace/src/main.py"},
        }
        context = {"workspace_path": "/tmp/workspace"}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result == {}

    async def test_blocks_write_outside_workspace(self):
        hook_input = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/etc/passwd"},
        }
        context = {"workspace_path": "/tmp/workspace"}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result["decision"] == "block"

    async def test_blocks_path_traversal(self):
        hook_input = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/workspace/../../../etc/passwd"},
        }
        context = {"workspace_path": "/tmp/workspace"}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result["decision"] == "block"

    async def test_allows_read_within_workspace(self):
        hook_input = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/workspace/README.md"},
        }
        context = {"workspace_path": "/tmp/workspace"}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result == {}

    async def test_blocks_search_outside_workspace(self):
        hook_input = {
            "tool_name": "Grep",
            "tool_input": {"path": "/home/user/.ssh"},
        }
        context = {"workspace_path": "/tmp/workspace"}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result["decision"] == "block"

    async def test_allows_no_path(self):
        hook_input = {
            "tool_name": "Glob",
            "tool_input": {"pattern": "*.py"},
        }
        context = {"workspace_path": "/tmp/workspace"}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result == {}


@pytest.mark.asyncio
class TestBashArgvValidation:
    async def test_allows_simple_command(self):
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest --tb=short -q"},
        }
        result = await validate_bash_argv(hook_input, None, {})
        assert result == {}

    async def test_blocks_pipe(self):
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "cat file.txt | grep secret"},
        }
        result = await validate_bash_argv(hook_input, None, {})
        assert result["decision"] == "block"

    async def test_blocks_semicolon(self):
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls; rm -rf /"},
        }
        result = await validate_bash_argv(hook_input, None, {})
        assert result["decision"] == "block"

    async def test_blocks_command_chaining(self):
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "test -f file && cat file"},
        }
        result = await validate_bash_argv(hook_input, None, {})
        assert result["decision"] == "block"

    async def test_blocks_backtick_injection(self):
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "echo `whoami`"},
        }
        result = await validate_bash_argv(hook_input, None, {})
        assert result["decision"] == "block"

    async def test_blocks_dollar_substitution(self):
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "echo $HOME"},
        }
        result = await validate_bash_argv(hook_input, None, {})
        assert result["decision"] == "block"

    async def test_ignores_non_bash_tools(self):
        hook_input = {
            "tool_name": "Read",
            "tool_input": {"command": "anything | goes"},
        }
        result = await validate_bash_argv(hook_input, None, {})
        assert result == {}

    async def test_allows_empty_command(self):
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": ""},
        }
        result = await validate_bash_argv(hook_input, None, {})
        assert result == {}


@pytest.mark.asyncio
class TestAuditLogToolUse:
    """Test audit_log_tool_use hook."""

    async def test_logs_tool_use_without_db(self):
        hook_input = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.py"},
            "tool_response": "file contents here",
        }
        result = await audit_log_tool_use(hook_input, "tu-123", {})
        assert result == {}

    async def test_logs_tool_use_with_db_session(self):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        hook_input = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/out.py"},
            "tool_response": "ok",
        }
        context = {"run_id": "run-1", "db_session": mock_session}
        result = await audit_log_tool_use(hook_input, "tu-456", context)
        assert result == {}
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    async def test_handles_exception_gracefully(self):
        result = await audit_log_tool_use(None, None, {})
        assert result == {}

    async def test_logs_dict_response(self):
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_response": {"content": "output"},
        }
        result = await audit_log_tool_use(hook_input, None, {})
        assert result == {}


class TestSanitizeForLog:
    """Test _sanitize_for_log helper."""

    def test_short_values_unchanged(self):
        data = {"key": "short value"}
        assert _sanitize_for_log(data) == data

    def test_long_values_truncated(self):
        data = {"key": "x" * 2000}
        result = _sanitize_for_log(data)
        assert len(result["key"]) < 2000
        assert "2000 chars" in result["key"]

    def test_non_string_values_unchanged(self):
        data = {"count": 42, "items": [1, 2, 3]}
        assert _sanitize_for_log(data) == data
