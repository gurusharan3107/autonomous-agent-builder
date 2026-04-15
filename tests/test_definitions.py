"""Tests for agent definitions."""

from __future__ import annotations

import pytest

from autonomous_agent_builder.agents.definitions import (
    AGENT_DEFINITIONS,
    get_agent_definition,
)


class TestAgentDefinitions:
    def test_all_agents_defined(self):
        expected = {"planner", "designer", "code-gen", "pr-creator", "build-verifier"}
        assert set(AGENT_DEFINITIONS.keys()) == expected

    def test_planner_is_opus(self):
        planner = get_agent_definition("planner")
        assert planner.model == "opus"

    def test_code_gen_is_sonnet(self):
        codegen = get_agent_definition("code-gen")
        assert codegen.model == "sonnet"

    def test_planner_is_read_only(self):
        planner = get_agent_definition("planner")
        write_tools = {"Edit", "Write", "Bash"}
        assert not write_tools.intersection(planner.tools)

    def test_code_gen_has_write_tools(self):
        codegen = get_agent_definition("code-gen")
        assert "Edit" in codegen.tools
        assert "Write" in codegen.tools
        assert "Bash" in codegen.tools

    def test_definitions_are_frozen(self):
        planner = get_agent_definition("planner")
        with pytest.raises(AttributeError):
            planner.name = "hacked"

    def test_unknown_agent_raises(self):
        with pytest.raises(KeyError):
            get_agent_definition("nonexistent")

    def test_all_have_prompt_templates(self):
        for name, defn in AGENT_DEFINITIONS.items():
            assert defn.prompt_template, f"{name} has empty prompt_template"
            assert "{" in defn.prompt_template, f"{name} prompt has no template vars"

    def test_budget_limits(self):
        for name, defn in AGENT_DEFINITIONS.items():
            assert defn.max_budget_usd > 0, f"{name} has no budget"
            assert defn.max_turns > 0, f"{name} has no turn limit"
