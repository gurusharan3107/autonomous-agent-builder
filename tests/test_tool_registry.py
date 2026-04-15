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

    def test_get_tool_prompt_context(self):
        registry = ToolRegistry.build(["Read", "Bash"])
        context = registry.get_tool_prompt_context()
        assert "Read" in context
        assert "Bash" in context
        assert "Available Tools" in context

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
