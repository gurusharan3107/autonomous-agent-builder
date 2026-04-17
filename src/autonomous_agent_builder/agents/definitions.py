"""Agent definitions — versioned, repo-stored, immutable at execution.

This is the agent-as-artifact model. Each AgentDefinition is version-controlled
in this file. At execution time, the git SHA of this file is recorded in
agent_runs for full lineage tracking.

Change tracking: `git diff agents/definitions.py` shows agent evolution.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentDefinition:
    """Immutable definition for an SDLC agent.

    Frozen at execution time — the orchestrator reads these, builds the
    ToolRegistry, and dispatches via query().
    """

    name: str
    description: str
    prompt_template: str
    tools: tuple[str, ...]
    model: str = "sonnet"
    max_turns: int = 30
    max_budget_usd: float = 5.00


# ── SDLC Phase Agent Definitions ──
# These are the core agents. Each maps to a phase in the pipeline.

AGENT_DEFINITIONS: dict[str, AgentDefinition] = {
    "chat": AgentDefinition(
        name="chat",
        description="General-purpose conversational agent for project assistance",
        prompt_template=(
            "You are a helpful AI assistant for the {project_name} project.\n\n"
            "You have access to the project files and can help users:\n"
            "- Understand the codebase structure and architecture\n"
            "- Answer questions about specific files or components\n"
            "- Provide guidance on development tasks\n"
            "- Search through project knowledge and memory\n\n"
            "Use Read/Glob/Grep to explore the codebase when needed.\n"
            "Use builder_kb_search to find relevant documentation.\n"
            "Use builder_memory_search to recall past decisions.\n\n"
            "Project root: {workspace_path}\n\n"
            "User: {user_message}\n"
        ),
        tools=(
            "Read",
            "Glob",
            "Grep",
            "mcp__builder__kb_search",
            "mcp__builder__memory_search",
            "mcp__builder__task_list",
            "mcp__builder__task_show",
        ),
        model="sonnet",
        max_turns=15,
        max_budget_usd=2.00,
    ),
    "planner": AgentDefinition(
        name="planner",
        description="Break features into implementation tasks with dependencies",
        prompt_template=(
            "You are a sprint planning expert for {language} projects.\n\n"
            "Given the feature description and codebase context, produce a task breakdown:\n"
            "- Each task has: title, description, acceptance criteria, estimated complexity\n"
            "- Identify dependencies between tasks\n"
            "- Order tasks for optimal parallel execution\n"
            "- Flag tasks that need design review first\n\n"
            "Analyze the codebase using Read/Glob/Grep to understand the current structure "
            "before planning.\n\n"
            "{tool_context}\n\n"
            "Feature: {feature_description}\n"
            "Project: {project_name}\n"
            "Language: {language}\n"
        ),
        tools=(
            "Read",
            "Glob",
            "Grep",
            "mcp__builder__kb_search",
            "mcp__builder__memory_search",
        ),
        model="opus",
        max_turns=20,
        max_budget_usd=3.00,
    ),
    "designer": AgentDefinition(
        name="designer",
        description="Create architecture decisions and API contracts",
        prompt_template=(
            "You are a senior software architect for {language} projects.\n\n"
            "Given the task and codebase, produce:\n"
            "- Architecture decision record (ADR) for significant changes\n"
            "- API contracts (function signatures, type definitions)\n"
            "- Schema proposals (database, config)\n"
            "- Integration points with existing code\n\n"
            "Use builder_kb_search to read prior ADRs and contracts.\n"
            "Use builder_kb_add to write your ADR and API contracts.\n"
            "Use builder_memory_search to check prior decisions.\n\n"
            "Analyze the codebase thoroughly before designing.\n\n"
            "{tool_context}\n\n"
            "Task: {task_description}\n"
            "Project: {project_name}\n"
            "Language: {language}\n"
        ),
        tools=(
            "Read",
            "Glob",
            "Grep",
            "mcp__builder__kb_add",
            "mcp__builder__kb_search",
            "mcp__builder__memory_search",
        ),
        model="opus",
        max_turns=20,
        max_budget_usd=3.00,
    ),
    "code-gen": AgentDefinition(
        name="code-gen",
        description="Implement features in isolated workspace",
        prompt_template=(
            "You are an expert {language} developer.\n\n"
            "Implement the task in the workspace. Follow the project's existing patterns.\n"
            "- Write clean, tested code\n"
            "- Run tests after implementation to verify\n"
            "- Run linter to check code quality\n"
            "- Fix any issues before completing\n\n"
            "IMPORTANT: Only modify files within the workspace at {workspace_path}.\n\n"
            "{tool_context}\n\n"
            "Task: {task_description}\n"
            "Design: {design_context}\n"
            "Workspace: {workspace_path}\n"
        ),
        tools=(
            "Read",
            "Edit",
            "Write",
            "Bash",
            "Glob",
            "Grep",
            "mcp__workspace__run_tests",
            "mcp__workspace__run_linter",
            "mcp__builder__kb_search",
            "mcp__builder__memory_search",
            "mcp__builder__task_show",
        ),
        model="sonnet",
        max_turns=30,
        max_budget_usd=5.00,
    ),
    "pr-creator": AgentDefinition(
        name="pr-creator",
        description="Create pull requests with quality evidence",
        prompt_template=(
            "You are a PR creation agent.\n\n"
            "Create a pull request for the completed task:\n"
            "- Write a clear PR title and description\n"
            "- Include quality gate results as evidence\n"
            "- Reference the task and design decisions\n"
            "- List files changed with brief rationale\n\n"
            "{tool_context}\n\n"
            "Task: {task_description}\n"
            "Gate Results: {gate_results}\n"
            "Workspace: {workspace_path}\n"
        ),
        tools=("Read", "Bash", "Glob", "Grep"),
        model="sonnet",
        max_turns=15,
        max_budget_usd=2.00,
    ),
    "build-verifier": AgentDefinition(
        name="build-verifier",
        description="Verify post-merge build and integration tests pass",
        prompt_template=(
            "You are a build verification agent.\n\n"
            "After PR merge, verify:\n"
            "- Build succeeds on the merged branch\n"
            "- Integration tests pass\n"
            "- No regressions detected\n\n"
            "{tool_context}\n\n"
            "Branch: {branch}\n"
            "Workspace: {workspace_path}\n"
        ),
        tools=("Read", "Bash", "Glob", "Grep"),
        model="sonnet",
        max_turns=10,
        max_budget_usd=1.50,
    ),
}


def get_agent_definition(name: str) -> AgentDefinition:
    """Get an agent definition by name. Raises KeyError if not found."""
    if name not in AGENT_DEFINITIONS:
        raise KeyError(f"Agent '{name}' not defined. Available: {list(AGENT_DEFINITIONS.keys())}")
    return AGENT_DEFINITIONS[name]
