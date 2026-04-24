"""Tests for SDK hooks — workspace boundary, bash argv, and audit logging."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from autonomous_agent_builder.agents.hooks import (
    _sanitize_for_log,
    audit_log_tool_use,
    enforce_workspace_boundary,
    keep_tool_stream_open,
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

    async def test_blocks_direct_codex_write_with_workflow_hint(self):
        hook_input = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(Path.home() / ".codex" / "docs" / "workflows" / "x.md")
            },
        }
        context = {"workspace_path": "/tmp/workspace"}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result["decision"] == "block"
        assert "workflow CLI" in result["reason"]

    async def test_blocks_root_level_quality_gate_doc_write(self, tmp_path):
        workspace = tmp_path / "workspace"
        (workspace / "docs").mkdir(parents=True)
        hook_input = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(workspace / "docs" / "new-quality-gate.md")},
        }
        context = {"workspace_path": str(workspace)}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result["decision"] == "block"
        assert "docs/quality-gate/" in result["reason"]

    async def test_blocks_duplicate_quality_gate_surface_write(self, tmp_path):
        workspace = tmp_path / "workspace"
        gate_dir = workspace / "docs" / "quality-gate"
        gate_dir.mkdir(parents=True)
        (gate_dir / "builder-cli.md").write_text("# existing\n", encoding="utf-8")
        hook_input = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(gate_dir / "builder-cli-quality-gate.md")},
        }
        context = {"workspace_path": str(workspace)}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result["decision"] == "block"
        assert "existing doc" in result["reason"]

    async def test_blocks_quality_gate_owner_doc_wording_on_write(self, tmp_path):
        workspace = tmp_path / "workspace"
        gate_dir = workspace / "docs" / "quality-gate"
        gate_dir.mkdir(parents=True)
        hook_input = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(gate_dir / "builder-cli.md"),
                "content": (
                    "---\n"
                    "title: Builder CLI quality gate\n"
                    "surface: builder-cli\n"
                    "summary: Verify CLI changes.\n"
                    "commands:\n"
                    "  - builder --help\n"
                    "expectations:\n"
                    "  - help stays bounded\n"
                    "---\n\n"
                    "# Builder CLI quality gate\n\n"
                    "## Purpose\n\n"
                    "Review the CLI change.\n\n"
                    "## When To Load\n\n"
                    "- before changing commands\n\n"
                    "## Owner Split\n\n"
                    "- builder should own product semantics\n\n"
                    "## Pass Signals\n\n"
                    "- help stays bounded\n\n"
                    "## Fail Signals\n\n"
                    "- internal nouns leak\n"
                ),
            },
        }
        context = {"workspace_path": str(workspace)}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result["decision"] == "block"
        assert "quality-gate docs must stay review-contract surfaces" in result["reason"]

    async def test_blocks_root_level_workflow_doc_write(self, tmp_path):
        workspace = tmp_path / "workspace"
        workflow_dir = workspace / "docs" / "workflows"
        workflow_dir.mkdir(parents=True)
        (workflow_dir / "task-workspace-isolation.md").write_text("# workflow\n", encoding="utf-8")
        hook_input = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(workspace / "docs" / "task-workspace-isolation.md")},
        }
        context = {"workspace_path": str(workspace)}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result["decision"] == "block"
        assert "docs/workflows/" in result["reason"]

    async def test_allows_write_within_tmp_scratch_space(self):
        hook_input = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/aab-scratch/output.txt"},
        }
        context = {"workspace_path": "/repo/workspace"}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result == {}

    async def test_blocks_path_traversal(self):
        hook_input = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/workspace/../../../etc/passwd"},
        }
        context = {"workspace_path": "/tmp/workspace"}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result["decision"] == "block"

    async def test_blocks_local_kb_write_within_workspace(self):
        hook_input = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/workspace/.agent-builder/knowledge/context/doc.md"},
        }
        context = {"workspace_path": "/tmp/workspace"}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result["decision"] == "block"
        assert "builder_kb_add" in result["reason"]

    async def test_blocks_local_memory_write_within_workspace(self):
        hook_input = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/workspace/.memory/corrections/example.md"},
        }
        context = {"workspace_path": "/tmp/workspace"}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result["decision"] == "block"
        assert "builder_memory_add" in result["reason"]

    async def test_blocks_direct_codex_search_with_workflow_hint(self):
        hook_input = {
            "tool_name": "Grep",
            "tool_input": {
                "path": str(Path.home() / ".codex" / "docs"),
                "pattern": "workflow",
            },
        }
        context = {"workspace_path": "/tmp/workspace"}
        result = await enforce_workspace_boundary(hook_input, None, context)
        assert result["decision"] == "block"
        assert "workflow CLI" in result["reason"]


@pytest.mark.asyncio
async def test_keep_tool_stream_open_returns_continue_marker():
    result = await keep_tool_stream_open({}, None, {})
    assert result == {"continue_": True}


@pytest.mark.asyncio
class TestValidateBashArgv:
    async def test_blocks_shell_metacharacters(self):
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "rg foo src | head"},
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

    async def test_blocks_builder_kb_mutation_command(self):
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "builder knowledge add --type context --title Test --content Body"},
        }
        result = await validate_bash_argv(hook_input, None, {})
        assert result["decision"] == "block"
        assert "builder_kb_add" in result["reason"]

    async def test_blocks_builder_memory_mutation_command(self):
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "builder memory add --type correction --phase testing "
                    "--entity hooks --tags x --title T --content Body"
                )
            },
        }
        result = await validate_bash_argv(hook_input, None, {})
        assert result["decision"] == "block"
        assert "builder_memory_add" in result["reason"]

    async def test_allows_builder_kb_extract_command(self):
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "builder knowledge extract --force --output-dir system-docs --json"
            },
        }
        result = await validate_bash_argv(hook_input, None, {})
        assert result == {}

    async def test_allows_builder_cli_discovery_command(self):
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "builder --help"},
        }
        result = await validate_bash_argv(hook_input, None, {})
        assert result == {}

    async def test_allows_workflow_cli_discovery_command(self):
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "workflow --help"},
        }
        result = await validate_bash_argv(hook_input, None, {})
        assert result == {}


@pytest.mark.asyncio
class TestAuditLogToolUse:
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
