"""Tests for agent definitions."""

from __future__ import annotations

import pytest

from autonomous_agent_builder.agents.definitions import (
    AGENT_DEFINITIONS,
    SubagentDefinition,
    get_agent_definition,
    get_subagent_definition,
)
from autonomous_agent_builder.agents.subagent_definitions import SUBAGENT_DEFINITIONS


class TestAgentDefinitions:
    def test_all_agents_defined(self):
        expected = {
            "chat",
            "init-project-chat",
            "planner",
            "designer",
            "ui-prototyper",
            "scaffold",
            "gate-remediator",
            "code-gen",
            "pr-creator",
            "build-verifier",
            "feature-verifier",
            "integration-resolver",
            "documentation-bridge",
            "optimization-agent",
        }
        assert set(AGENT_DEFINITIONS.keys()) == expected
        assert set(SUBAGENT_DEFINITIONS.keys()) == {
            "browser-verifier",
            "build-verifier",
            "documentation-agent",
            "pr-reviewer",
            "repo-researcher",
            "security-reviewer",
        }

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
        assert "Bash" not in codegen.tools
        assert "mcp__workspace__run_command" in codegen.tools
        assert "mcp__builder__kb_show" in codegen.tools

    def test_code_gen_prompt_includes_recovery_context(self):
        codegen = get_agent_definition("code-gen")
        assert "Recovery context: {recovery_context}" in codegen.prompt_template

    def test_code_gen_prompt_includes_workspace_map_slot(self):
        # IMP-027 context follow-up: a compact workspace file map is injected so
        # code-gen locates files without burning list_directory/Read turns.
        codegen = get_agent_definition("code-gen")
        assert "{workspace_map}" in codegen.prompt_template

    def test_pr_creator_requires_workspace_hygiene_check(self):
        pr_creator = get_agent_definition("pr-creator")
        assert "git status" in pr_creator.prompt_template
        assert "untracked files" in pr_creator.prompt_template
        assert "scratch" in pr_creator.prompt_template

    def test_chat_routes_through_mcps_not_shell(self):
        # Per docs/rubric/autonomous-builder-agents.md: chat must not have Bash,
        # Write, or Edit. Its job is to translate operator intent into Builder
        # lifecycle moves via MCP tools — never via shell or direct file edits.
        chat = get_agent_definition("chat")
        assert "Bash" not in chat.tools
        assert "Write" not in chat.tools
        assert "Edit" not in chat.tools
        assert "AskUserQuestion" in chat.tools
        assert chat.auto_approve_tools is not None
        assert "AskUserQuestion" not in chat.auto_approve_tools
        # Prompt explicitly forbids shell/filesystem workarounds.
        assert "You do NOT have Bash, Write, or Edit" in chat.prompt_template
        # Lifecycle routing remains explicit.
        assert "Do not treat the task board as the backlog" in chat.prompt_template
        assert "`mcp__builder__board` first" in chat.prompt_template
        assert "never mark a Board task complete" in chat.prompt_template
        assert "mcp__builder__task_recover" in chat.prompt_template
        assert "requiring an exact recovery phrase" in chat.prompt_template
        assert "mcp__builder__board" in chat.tools
        assert "mcp__builder__task_status" in chat.tools
        assert "mcp__builder__task_recover" in chat.tools
        assert "mcp__builder__task_dispatch" in chat.tools
        assert "mcp__builder__board" in chat.auto_approve_tools
        assert "mcp__builder__task_status" in chat.auto_approve_tools

    def test_chat_exposes_mutation_tools_but_does_not_auto_approve_them(self):
        chat = get_agent_definition("chat")
        assert "mcp__builder__memory_add" in chat.tools
        assert "mcp__builder__kb_add" in chat.tools
        assert "mcp__builder__kb_update" in chat.tools
        assert "mcp__builder__task_recover" in chat.tools
        assert "mcp__builder__task_dispatch" in chat.tools
        assert chat.auto_approve_tools is not None
        assert "mcp__builder__memory_add" not in chat.auto_approve_tools
        assert "mcp__builder__kb_add" not in chat.auto_approve_tools
        assert "mcp__builder__kb_update" not in chat.auto_approve_tools
        assert "mcp__builder__task_recover" not in chat.auto_approve_tools
        assert "mcp__builder__task_dispatch" not in chat.auto_approve_tools

    def test_chat_requires_approval_for_bash(self):
        chat = get_agent_definition("chat")
        assert chat.auto_approve_tools is not None
        assert "Bash" not in chat.auto_approve_tools
        assert "mcp__builder__backlog_item_list" in chat.tools
        assert "mcp__builder__backlog_item_show" in chat.tools
        assert "mcp__builder__backlog_item_list" in chat.auto_approve_tools
        assert "mcp__builder__backlog_item_show" in chat.auto_approve_tools

    def test_scaffold_runtime_contract(self):
        # Scaffold decides stack at runtime, writes minimum config, never
        # mutates backlog/board. See docs/rubric/autonomous-builder-agents.md.
        scaffold = get_agent_definition("scaffold")
        # Workspace edit tools — scaffold must be able to write config files.
        assert "Read" in scaffold.tools
        assert "Write" in scaffold.tools
        assert "Edit" in scaffold.tools
        assert "mcp__workspace__run_command" in scaffold.tools
        # Glob and Grep are not needed — scaffold writes config, not text searches.
        assert "Glob" not in scaffold.tools
        assert "Grep" not in scaffold.tools
        assert "Glob" not in (scaffold.auto_approve_tools or ())
        assert "Grep" not in (scaffold.auto_approve_tools or ())
        # Stack ambiguity is resolved via AskUserQuestion, not freeform prose.
        assert "AskUserQuestion" in scaffold.tools
        # No backlog/board mutation — scaffold cannot touch lifecycle state.
        forbidden = {
            "mcp__builder__board",
            "mcp__builder__task_dispatch",
            "mcp__builder__task_recover",
            "mcp__builder__kb_add",
            "mcp__builder__kb_update",
            "mcp__builder__memory_add",
            "mcp__builder__backlog_item_list",
        }
        assert forbidden.isdisjoint(set(scaffold.tools))
        # AskUserQuestion never auto-approves: operator must answer explicitly.
        assert scaffold.auto_approve_tools is not None
        assert "AskUserQuestion" not in scaffold.auto_approve_tools
        # Cap the agent aggressively to avoid the runaway-turn pattern.
        assert scaffold.max_turns <= 12
        assert scaffold.max_budget_usd <= 2.00
        # Prompt encodes the SCAFFOLD_RESULT_JSON contract used by the
        # orchestrator to update Project.language.
        assert "SCAFFOLD_RESULT_JSON" in scaffold.prompt_template
        assert "product language" in scaffold.prompt_template
        # Scaffold uses operator-facing terms ('web app', 'command-line tool')
        # and never leaks framework names into questions.
        assert "framework" in scaffold.prompt_template.lower()

    def test_codegen_gets_only_task_scoped_context_and_workspace_execution_tools(self):
        codegen = get_agent_definition("code-gen")
        assert "Bash" not in codegen.tools
        assert "mcp__workspace__get_project_info" in codegen.tools
        assert "mcp__workspace__list_directory" in codegen.tools
        assert "mcp__workspace__run_command" in codegen.tools
        assert "mcp__workspace__run_tests" in codegen.tools
        assert "mcp__workspace__run_linter" in codegen.tools
        assert "mcp__builder__task_show" in codegen.tools
        assert "mcp__builder__kb_search" in codegen.tools
        assert "mcp__builder__kb_show" in codegen.tools
        assert "mcp__builder__memory_search" in codegen.tools
        assert "mcp__builder__board" not in codegen.tools
        assert "mcp__builder__backlog_item_list" not in codegen.tools
        assert "mcp__builder__memory_add" not in codegen.tools
        assert "mcp__builder__kb_add" not in codegen.tools
        assert "mcp__builder__kb_update" not in codegen.tools
        assert "Knowledge requirements:" in codegen.prompt_template
        assert "Do not inspect the task board or backlog" in codegen.prompt_template

    def test_codegen_bounds_server_and_command_output_for_codex(self):
        codegen = get_agent_definition("code-gen")
        assert "Keep command output bounded" in codegen.prompt_template
        assert "Never run a long-lived dev server in the foreground" in codegen.prompt_template
        assert "stop it" in codegen.prompt_template

    def test_feature_verifier_bounds_browser_validation_output_for_codex(self):
        verifier = get_agent_definition("feature-verifier")
        assert "Keep shell output bounded" in verifier.prompt_template
        assert "Never run a long-lived dev server in the foreground" in verifier.prompt_template
        assert "Do not print Playwright traces" in verifier.prompt_template
        assert "Bash" not in verifier.tools
        assert "mcp__workspace__run_command" in verifier.tools

    def test_build_verifier_boundary_is_runtime_agnostic_for_directory_workspaces(self):
        verifier = get_agent_definition("build-verifier")
        assert "local generated-app directory workspaces" in verifier.prompt_template
        assert "builder script run build_verify --json" in verifier.prompt_template

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
        assert (
            "Respect the provided `resolved_action`, `target_doc_type`, `mode`, "
            "and `freshness_mode` fields"
        ) in subagent.prompt
        assert (
            "For first-doc creation, call `builder_kb_contract` before drafting."
            in subagent.prompt
        )
        assert (
            "Use `builder_kb_lint` to catch contract failures before `builder_kb_add`"
            in subagent.prompt
        )
        assert (
            "Attempt at most one repair retry after a lint or publish failure."
            in subagent.prompt
        )
        assert "JSON object" in subagent.prompt

    def test_documentation_bridge_only_owns_agent_tool_and_doc_auto_approvals(self):
        bridge = get_agent_definition("documentation-bridge")
        assert bridge.tools == ()
        # Bridge delegates to documentation-agent via Agent tool only.
        # KB mutation tools must NOT be in auto_approve_tools: the bridge
        # runs in the auto-approve path (no can_use_tool callback from
        # _run_bridge_agent), so any extra tool here is auto-approved and
        # bypasses the delegation contract.
        assert bridge.auto_approve_tools == ("Agent",)
        assert "mcp__builder__kb_update" not in (bridge.auto_approve_tools or ())
        assert "documentation-agent" in bridge.prompt_template

    def test_optimization_agent_is_post_ship_bounded_and_observability_grounded(self):
        agent = get_agent_definition("optimization-agent")
        assert agent.model == "sonnet"
        assert "Observability and recommendation payload" in agent.prompt_template
        assert "Review every open recommendation" in agent.prompt_template
        assert "recommendation_decisions" in agent.prompt_template
        assert "Do not alter shipped feature scope" in agent.prompt_template
        assert "OPERATOR_DECISION_JSON" in agent.prompt_template
        assert "mcp__builder__metrics" in agent.tools
        assert "mcp__builder__recommendation_create" in agent.tools
        assert "AskUserQuestion" not in agent.tools

    def test_all_have_prompt_templates(self):
        for name, defn in AGENT_DEFINITIONS.items():
            assert defn.prompt_template, f"{name} has empty prompt_template"
            assert "{" in defn.prompt_template, f"{name} prompt has no template vars"

    def test_budget_limits(self):
        for name, defn in AGENT_DEFINITIONS.items():
            assert defn.max_budget_usd > 0, f"{name} has no budget"
            assert defn.max_turns > 0, f"{name} has no turn limit"

    def test_gate_remediator_runtime_contract(self):
        gate = get_agent_definition("gate-remediator")
        # Must be able to read, create, and edit workspace files.
        assert "Read" in gate.tools
        assert "Write" in gate.tools
        assert "Edit" in gate.tools
        assert "Grep" in gate.tools
        # Glob excluded — gate-remediator works from error output, not file globs.
        assert "Glob" not in gate.tools
        assert "Glob" not in (gate.auto_approve_tools or ())
        # Uses workspace MCP for running commands, not Bash.
        assert "mcp__workspace__run_command" in gate.tools
        assert "Bash" not in gate.tools
        # Capped to avoid runaway loops.
        assert gate.max_turns <= 16
        # Prompt encodes GATE_FIX_RESULT_JSON sentinel and scope boundary.
        assert "GATE_FIX_RESULT_JSON" in gate.prompt_template
        assert "Never delete any existing file" in gate.prompt_template
        # FIX 3: python3 not bare python — bare python exits 127 in workspaces.
        assert "python3" in gate.prompt_template
        assert '"python"' not in gate.prompt_template

    def test_scaffold_prompt_instructs_no_claude_skills_dir(self):
        # FIX 4: the prompt must contain an explicit negative constraint so the
        # model does not attempt to load skills from .claude/skills/ (which does
        # not exist in ephemeral workspaces — skills arrive via prompt enrichment).
        scaffold = get_agent_definition("scaffold")
        assert "ephemeral workspaces have no" in scaffold.prompt_template
        assert "skills are provided via prompt enrichment" in scaffold.prompt_template

    def test_codegen_instructs_no_claude_skills_dir(self):
        # FIX 4: same constraint for code-gen.
        codegen = get_agent_definition("code-gen")
        assert "ephemeral workspaces have no" in codegen.prompt_template
        assert "skills are provided via prompt enrichment" in codegen.prompt_template

    def test_codegen_command_discipline_python3_and_mcp_not_bash(self):
        # FIX 3+5: code-gen must instruct python3 (not bare python) and route
        # build/test commands through mcp__workspace__ tools, not Bash.
        codegen = get_agent_definition("code-gen")
        assert "python3" in codegen.prompt_template
        assert "mcp__workspace__run_tests" in codegen.prompt_template
        assert "mcp__workspace__run_command" in codegen.prompt_template
        assert "never pass" in codegen.prompt_template

    def test_subagent_definition_supports_max_turns(self):
        # SubagentDefinition.max_turns is forwarded to the SDK as maxTurns.
        defn = SubagentDefinition(
            name="test",
            description="test",
            prompt="test",
            tools=("Read",),
            max_turns=8,
        )
        assert defn.max_turns == 8

    def test_subagent_definition_max_turns_defaults_none(self):
        defn = SubagentDefinition(
            name="test",
            description="test",
            prompt="test",
            tools=("Read",),
        )
        assert defn.max_turns is None
