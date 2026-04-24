"""Tests for agent definitions."""

from __future__ import annotations

import pytest

from autonomous_agent_builder.agents.definitions import (
    AGENT_DEFINITIONS,
    SUBAGENT_DEFINITIONS,
    get_agent_definition,
    get_subagent_definition,
)


class TestAgentDefinitions:
    def test_all_agents_defined(self):
        expected = {
            "chat",
            "init-project-chat",
            "planner",
            "designer",
            "code-gen",
            "pr-creator",
            "build-verifier",
            "documentation-bridge",
        }
        assert set(AGENT_DEFINITIONS.keys()) == expected
        assert set(SUBAGENT_DEFINITIONS.keys()) == {"documentation-agent"}

    def test_planner_is_opus(self):
        planner = get_agent_definition("planner")
        assert planner.model == "opus"

    def test_code_gen_is_sonnet(self):
        codegen = get_agent_definition("code-gen")
        assert codegen.model == "sonnet"

    def test_chat_is_haiku(self):
        chat = get_agent_definition("chat")
        assert chat.model == "haiku"

    def test_init_project_chat_is_opus(self):
        chat = get_agent_definition("init-project-chat")
        assert chat.model == "opus"

    def test_planner_is_read_only(self):
        planner = get_agent_definition("planner")
        write_tools = {"Edit", "Write", "Bash"}
        assert not write_tools.intersection(planner.tools)
        assert "mcp__builder__kb_show" in planner.tools

    def test_code_gen_has_write_tools(self):
        codegen = get_agent_definition("code-gen")
        assert "Edit" in codegen.tools
        assert "Write" in codegen.tools
        assert "Bash" in codegen.tools
        assert "mcp__builder__kb_show" in codegen.tools

    def test_chat_can_use_builder_and_workflow_via_bash(self):
        chat = get_agent_definition("chat")
        assert "Bash" in chat.tools
        assert "builder" in chat.prompt_template
        assert "workflow" in chat.prompt_template
        assert "AskUserQuestion" in chat.prompt_template

    def test_chat_exposes_mutation_tools_but_does_not_auto_approve_them(self):
        chat = get_agent_definition("chat")
        assert "mcp__builder__memory_add" in chat.tools
        assert "mcp__builder__kb_add" in chat.tools
        assert "mcp__builder__kb_update" in chat.tools
        assert chat.auto_approve_tools is not None
        assert "mcp__builder__memory_add" not in chat.auto_approve_tools
        assert "mcp__builder__kb_add" not in chat.auto_approve_tools
        assert "mcp__builder__kb_update" not in chat.auto_approve_tools

    def test_chat_requires_approval_for_bash(self):
        chat = get_agent_definition("chat")
        assert chat.auto_approve_tools is not None
        assert "Bash" not in chat.auto_approve_tools

    def test_codegen_can_record_learning_through_official_surfaces(self):
        codegen = get_agent_definition("code-gen")
        assert "mcp__builder__memory_add" in codegen.tools
        assert "mcp__builder__kb_add" in codegen.tools
        assert "mcp__builder__kb_update" in codegen.tools
        assert "Knowledge requirements:" in codegen.prompt_template

    def test_designer_can_publish_repo_local_kb_through_builder_surfaces(self):
        designer = get_agent_definition("designer")
        assert "mcp__builder__kb_search" in designer.tools
        assert "mcp__builder__kb_show" in designer.tools
        assert "mcp__builder__kb_add" in designer.tools
        assert "mcp__builder__kb_update" in designer.tools
        assert "Knowledge requirements:" in designer.prompt_template
        assert "builder_kb_add and builder_kb_update" in designer.prompt_template

    def test_planner_mentions_required_docs_contract(self):
        planner = get_agent_definition("planner")
        assert "depends_on.system_docs.required_docs" in planner.prompt_template
        assert "Knowledge requirements:" in planner.prompt_template

    def test_definitions_are_frozen(self):
        planner = get_agent_definition("planner")
        with pytest.raises(AttributeError):
            planner.name = "hacked"

    def test_unknown_agent_raises(self):
        with pytest.raises(KeyError):
            get_agent_definition("nonexistent")

    def test_documentation_subagent_maintains_user_and_agent_friendly_kb(self):
        subagent = get_subagent_definition("documentation-agent")
        assert "mcp__builder__kb_search" in subagent.tools
        assert "mcp__builder__kb_contract" in subagent.tools
        assert "mcp__builder__kb_lint" in subagent.tools
        assert "mcp__builder__kb_extract" in subagent.tools
        assert "mcp__builder__kb_add" in subagent.tools
        assert "mcp__builder__kb_update" in subagent.tools
        assert "mcp__builder__kb_validate" in subagent.tools
        assert "AskUserQuestion" not in subagent.tools
        assert "docs/" in subagent.prompt
        assert "both human users and future agents" in subagent.prompt
        assert "Respect the provided `resolved_action`, `target_doc_type`, `mode`, and `freshness_mode` fields" in subagent.prompt
        assert "For first-doc creation, call `builder_kb_contract` before drafting." in subagent.prompt
        assert "Use `builder_kb_lint` to catch contract failures before `builder_kb_add`" in subagent.prompt
        assert "Attempt at most one repair retry after a lint or publish failure." in subagent.prompt
        assert "JSON object" in subagent.prompt

    def test_documentation_bridge_only_owns_agent_tool_and_doc_auto_approvals(self):
        bridge = get_agent_definition("documentation-bridge")
        assert bridge.tools == ()
        assert bridge.auto_approve_tools is not None
        assert bridge.auto_approve_tools[0] == "Agent"
        assert "mcp__builder__kb_update" in bridge.auto_approve_tools
        assert "documentation-agent" in bridge.prompt_template

    def test_all_have_prompt_templates(self):
        for name, defn in AGENT_DEFINITIONS.items():
            assert defn.prompt_template, f"{name} has empty prompt_template"
            assert "{" in defn.prompt_template, f"{name} prompt has no template vars"

    def test_budget_limits(self):
        for name, defn in AGENT_DEFINITIONS.items():
            assert defn.max_budget_usd > 0, f"{name} has no budget"
            assert defn.max_turns > 0, f"{name} has no turn limit"
