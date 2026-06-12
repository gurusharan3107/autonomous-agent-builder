"""Tests for ToolRegistry — the keystone contract."""

from __future__ import annotations

import pytest

from autonomous_agent_builder.agents.tool_registry import (
    ToolNotAvailableError,
    ToolRegistry,
    ToolValidationError,
)


class TestToolRegistry:
    def test_build_with_sdk_builtins(self):
        registry = ToolRegistry.build(["Read", "Glob", "Grep"])
        assert len(registry.tools) == 3
        assert "Read" in registry.tools
        assert "Glob" in registry.tools
        assert "Grep" in registry.tools

    def test_build_filters_unknown_tools(self):
        registry = ToolRegistry.build(["Read", "NonExistentTool"])
        assert len(registry.tools) == 1
        assert "Read" in registry.tools

    def test_validate_tool_call_success(self):
        registry = ToolRegistry.build(["Read"])
        assert registry.validate_tool_call("Read", {"file_path": "/tmp/test.py"})

    def test_validate_tool_call_not_available(self):
        registry = ToolRegistry.build(["Read"])
        with pytest.raises(ToolNotAvailableError):
            registry.validate_tool_call("Write", {"file_path": "/tmp/test.py"})

    def test_validate_tool_call_missing_required_param(self):
        registry = ToolRegistry.build(["Read"])
        with pytest.raises(ToolValidationError):
            registry.validate_tool_call("Read", {})

    def test_validate_tool_call_no_args(self):
        registry = ToolRegistry.build(["Read"])
        assert registry.validate_tool_call("Read")

    def test_list_tools(self):
        registry = ToolRegistry.build(["Read", "Edit", "Write"])
        tools = registry.list_tools()
        assert set(tools) == {"Read", "Edit", "Write"}

    def test_kb_validate_tool_is_available(self):
        registry = ToolRegistry.build(["mcp__builder__kb_validate"])
        assert "mcp__builder__kb_validate" in registry.tools
        assert registry.tools["mcp__builder__kb_validate"].read_only is True

    def test_kb_contract_and_lint_tools_are_available(self):
        registry = ToolRegistry.build(["mcp__builder__kb_contract", "mcp__builder__kb_lint"])
        assert "mcp__builder__kb_contract" in registry.tools
        assert "mcp__builder__kb_lint" in registry.tools
        assert registry.tools["mcp__builder__kb_contract"].read_only is True
        assert registry.tools["mcp__builder__kb_lint"].read_only is True

    def test_kb_extract_tool_is_available(self):
        registry = ToolRegistry.build(["mcp__builder__kb_extract"])
        assert "mcp__builder__kb_extract" in registry.tools

    def test_recommendation_create_tool_is_available(self):
        registry = ToolRegistry.build(["mcp__builder__recommendation_create"])
        assert "mcp__builder__recommendation_create" in registry.tools
        assert registry.tools["mcp__builder__recommendation_create"].read_only is False

    def test_workspace_read_file_advertises_bounded_slice_params(self):
        registry = ToolRegistry.build(["mcp__workspace__read_file"])
        schema = registry.tools["mcp__workspace__read_file"]
        params = {param.name: param for param in schema.params}

        assert params["file_path"].required is True
        assert params["start_line"].required is False
        assert params["start_line"].default == 1
        assert params["max_lines"].required is False
        assert params["max_lines"].default == 200

    def test_get_tool_prompt_context(self):
        registry = ToolRegistry.build(["Read", "Bash"])
        context = registry.get_tool_prompt_context()
        # Bash has constraints — the Tool Constraints section appears
        assert "Bash" in context
        assert "Tool Constraints" in context
        assert "workspace_boundary" in context
        assert "argv_only" in context
        # Common param mistakes section always present
        assert "Common param mistakes" in context
        assert "file_path" in context
        assert "timeout" in context

    def test_get_tool_prompt_context_no_constraints(self):
        registry = ToolRegistry.build(["Read", "Glob"])
        context = registry.get_tool_prompt_context()
        # No constrained tools — Tool Constraints section absent but Common param
        # mistakes section always present.
        assert "Tool Constraints" not in context
        assert "Common param mistakes" in context
        assert "file_path" in context

    def test_get_tool_prompt_context_includes_mcp_param_hints(self):
        registry = ToolRegistry.build(["Read"])
        context = registry.get_tool_prompt_context()
        assert "mcp__workspace__run_command" in context
        assert "argv" in context
        assert "mcp__builder__task_list" in context
        assert "feature_id" in context
        assert "task_id" in context
        assert "item_id" in context

    def test_read_only_flag(self):
        registry = ToolRegistry.build(["Read", "Edit"])
        assert registry.tools["Read"].read_only is True
        assert registry.tools["Edit"].read_only is False

    def test_constraints(self):
        registry = ToolRegistry.build(["Bash"])
        assert "workspace_boundary" in registry.tools["Bash"].constraints
        assert "argv_only" in registry.tools["Bash"].constraints

    def test_build_with_custom_tools(self):
        async def my_tool(workspace_path: str, flag: bool = False) -> dict:
            """A custom tool for testing."""
            return {"content": [{"type": "text", "text": "ok"}]}

        registry = ToolRegistry.build(
            ["Read", "mcp__workspace__my_tool"],
            custom_tools={"mcp__workspace__my_tool": my_tool},
        )
        assert "mcp__workspace__my_tool" in registry.tools
        schema = registry.tools["mcp__workspace__my_tool"]
        assert schema.description == "A custom tool for testing."
        assert len(schema.params) == 2
