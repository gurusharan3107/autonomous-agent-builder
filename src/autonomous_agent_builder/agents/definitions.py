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
    auto_approve_tools: tuple[str, ...] | None = None
    model: str = "sonnet"
    max_turns: int = 30
    max_budget_usd: float = 5.00


@dataclass(frozen=True)
class SubagentDefinition:
    """Immutable definition for SDK subagents invoked inside a parent session."""

    name: str
    description: str
    prompt: str
    tools: tuple[str, ...]
    model: str = "sonnet"


DOCUMENTATION_AGENT_TOOLS: tuple[str, ...] = (
    "mcp__builder__task_show",
    "mcp__builder__kb_search",
    "mcp__builder__kb_show",
    "mcp__builder__kb_contract",
    "mcp__builder__kb_lint",
    "mcp__builder__kb_extract",
    "mcp__builder__kb_add",
    "mcp__builder__kb_update",
    "mcp__builder__kb_validate",
)


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
            "Use Bash for repo-safe argv commands when direct CLI evidence is needed.\n"
            "The `builder` CLI and `workflow` CLI are approved for this project and "
            "should be treated as first-class tools.\n"
            "Use builder_kb_search to find relevant documentation.\n"
            "Use builder_memory_search to recall past decisions.\n"
            "When you confirm a durable repo-specific lesson, use builder_memory_add "
            "to record it through the official memory surface instead of "
            "editing `.memory/` directly.\n"
            "When you intentionally publish or revise repo-local KB docs, use "
            "builder_kb_add or builder_kb_update instead of editing KB files directly.\n\n"
            "When a bounded user decision is required, use `AskUserQuestion` instead of embedding "
            "multiple choices in plain text. Keep headers concise, keep labels short, and put the "
            "recommended choice first.\n\n"
            "Project root: {workspace_path}\n\n"
            "User: {user_message}\n"
        ),
        tools=(
            "Read",
            "Glob",
            "Grep",
            "Bash",
            "mcp__builder__kb_search",
            "mcp__builder__kb_add",
            "mcp__builder__kb_update",
            "mcp__builder__memory_search",
            "mcp__builder__memory_add",
            "mcp__builder__task_list",
            "mcp__builder__task_show",
        ),
        auto_approve_tools=(
            "Read",
            "Glob",
            "Grep",
            "mcp__builder__kb_search",
            "mcp__builder__memory_search",
            "mcp__builder__task_list",
            "mcp__builder__task_show",
        ),
        model="haiku",
        max_turns=15,
        max_budget_usd=2.00,
    ),
    "init-project-chat": AgentDefinition(
        name="init-project-chat",
        description="Forward-engineering planning interviewer that converges on a backlog contract",
        prompt_template=(
            "You are an expert project planner for a brand-new software project.\n\n"
            "Your job is to interview the user until the first implementation scope is crisp, "
            "gap-free, and ready to turn into a feature backlog.\n\n"
            "When you need the user to choose among a few concrete options, use `AskUserQuestion` "
            "instead of writing the options inline. Keep headers concise, keep labels short, and "
            "put the recommended choice first.\n\n"
            "User: {user_message}\n"
        ),
        tools=(
            "Read",
            "Glob",
            "Grep",
            "Bash",
            "mcp__builder__kb_search",
            "mcp__builder__memory_search",
            "mcp__builder__task_list",
            "mcp__builder__task_show",
        ),
        auto_approve_tools=(
            "Read",
            "Glob",
            "Grep",
            "mcp__builder__kb_search",
            "mcp__builder__memory_search",
            "mcp__builder__task_list",
            "mcp__builder__task_show",
        ),
        model="opus",
        max_turns=20,
        max_budget_usd=5.00,
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
            "When the work clearly needs maintained repo-local knowledge docs, call out the "
            "expected required_docs under depends_on.system_docs.required_docs and whether the "
            "task will need feature or testing documentation.\n\n"
            "Analyze the codebase using Read/Glob/Grep to understand the current structure "
            "before planning.\n\n"
            "If you cannot continue without an operator decision, do not ask the user directly "
            "from this background phase. Emit `OPERATOR_DECISION_JSON:` followed immediately by "
            "one raw JSON object and nothing else after that object. Use this shape:\n"
            "{{\n"
            '  "phase": "planning",\n'
            '  "summary": "<brief why planning is blocked>",\n'
            '  "question": "<exact operator decision needed>",\n'
            '  "options": ["<option 1>", "<option 2>"],\n'
            '  "recommended_option": "<one option or empty>"\n'
            "}}\n\n"
            "{tool_context}\n\n"
            "Feature: {feature_description}\n"
            "Project: {project_name}\n"
            "Language: {language}\n"
            "Knowledge requirements: {knowledge_requirements}\n"
        ),
        tools=(
            "Read",
            "Glob",
            "Grep",
            "mcp__builder__kb_search",
            "mcp__builder__kb_show",
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
            "Use builder_kb_search and builder_kb_show to read prior ADRs and contracts.\n"
            "When the task requires durable repo-local knowledge docs, publish or "
            "refresh them through builder_kb_add and builder_kb_update instead of "
            "drafting KB markdown only in the response.\n"
            "Use builder_memory_search to check prior decisions.\n\n"
            "Analyze the codebase thoroughly before designing.\n\n"
            "If design cannot continue without an operator decision, do not ask the user "
            "directly from this background phase. Emit `OPERATOR_DECISION_JSON:` followed "
            "immediately by one raw JSON object and nothing else after that object. Use this "
            "shape:\n"
            "{{\n"
            '  "phase": "design",\n'
            '  "summary": "<brief why design is blocked>",\n'
            '  "question": "<exact operator decision needed>",\n'
            '  "options": ["<option 1>", "<option 2>"],\n'
            '  "recommended_option": "<one option or empty>"\n'
            "}}\n\n"
            "{tool_context}\n\n"
            "Task: {task_description}\n"
            "Project: {project_name}\n"
            "Language: {language}\n"
            "Knowledge requirements: {knowledge_requirements}\n"
        ),
        tools=(
            "Read",
            "Glob",
            "Grep",
            "mcp__builder__kb_search",
            "mcp__builder__kb_show",
            "mcp__builder__kb_add",
            "mcp__builder__kb_update",
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
            "When you confirm a durable repo-specific decision, pattern, or correction, "
            "record it with builder_memory_add instead of editing `.memory/` directly.\n"
            "Use builder_kb_search and builder_kb_show to retrieve repo-local KB context.\n"
            "When the task explicitly requires durable repo-local KB publication, use "
            "builder_kb_add or builder_kb_update instead of editing KB files directly.\n\n"
            "If implementation is blocked on an operator product decision, do not continue by "
            "guessing and do not ask the user directly from this background phase. Emit "
            "`OPERATOR_DECISION_JSON:` followed immediately by one raw JSON object and nothing "
            "else after that object. Use this shape:\n"
            "{{\n"
            '  "phase": "implementation",\n'
            '  "summary": "<brief why implementation is blocked>",\n'
            '  "question": "<exact operator decision needed>",\n'
            '  "options": ["<option 1>", "<option 2>"],\n'
            '  "recommended_option": "<one option or empty>"\n'
            "}}\n\n"
            "{tool_context}\n\n"
            "Task: {task_description}\n"
            "Design: {design_context}\n"
            "Workspace: {workspace_path}\n"
            "Knowledge requirements: {knowledge_requirements}\n"
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
            "mcp__builder__kb_show",
            "mcp__builder__kb_add",
            "mcp__builder__kb_update",
            "mcp__builder__memory_search",
            "mcp__builder__memory_add",
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
    "documentation-bridge": AgentDefinition(
        name="documentation-bridge",
        description=(
            "Repo-owned bridge that delegates bounded documentation refresh work "
            "to documentation-agent"
        ),
        prompt_template=(
            "You are the repo-owned documentation automation bridge.\n\n"
            "You do not own direct documentation mutation tools. Your only job is to "
            "invoke the `documentation-agent` specialist through the Agent tool and "
            "return its final JSON object unchanged.\n\n"
            "Rules:\n"
            "- Always use the `documentation-agent` subagent for this task.\n"
            "- Do not answer from your own knowledge instead of delegating.\n"
            "- Do not use any tool other than the Agent tool.\n"
            "- Preserve the bounded context exactly as given.\n"
            "- Return exactly one raw JSON object and nothing else.\n\n"
            "Task:\n{task_description}\n"
        ),
        tools=(),
        auto_approve_tools=("Agent", *DOCUMENTATION_AGENT_TOOLS),
        model="sonnet",
        max_turns=8,
        max_budget_usd=2.00,
    ),
}


SUBAGENT_DEFINITIONS: dict[str, SubagentDefinition] = {
    "documentation-agent": SubagentDefinition(
        name="documentation-agent",
        description=(
            "Repo-local documentation maintenance specialist. Use when the user asks whether "
            "documentation or the knowledge base is updated, when the app needs refreshed "
            "system docs, or when the active task clearly requires maintained feature/testing "
            "KB docs to be created or refreshed for both user understanding and agent retrieval."
        ),
        prompt=(
            "You are the repo-local documentation specialist for this project.\n\n"
            "Maintain repo-local knowledge under `.agent-builder/knowledge` through the canonical "
            "builder knowledge surfaces. The maintained KB serves both human users and future "
            "agents. Every durable KB update should be readable to a user while also making it "
            "easy for an agent to answer: what this application does, what features exist, which "
            "files matter, what to change, and what invariants or reminders must not be missed.\n\n"
            "Do not mutate repo docs under `docs/`, do not edit code, and do not write memory "
            "entries.\n\n"
            "Documentation action resolver:\n"
            "- Respect the provided `resolved_action`, `target_doc_type`, `mode`, and "
            "`freshness_mode` fields instead of inferring the lane from prose.\n"
            "- `add`: missing maintained `feature` or `testing` doc. Call `builder_kb_contract` "
            "once, draft once, lint once, then publish with `builder_kb_add`.\n"
            "- `update`: bounded change to one existing maintained doc. Read it with "
            "`builder_kb_show`; if you are changing maintained-doc metadata or refreshing the "
            "body, call `builder_kb_contract` before regenerating markdown, then lint before "
            "`builder_kb_update`.\n"
            "- `extract`: canonical freshness refresh on `main`. Use `builder_kb_extract` "
            "instead of composing manual maintained-doc freshness updates.\n"
            "- `advisory_only`: inspect and report likely stale docs on non-`main`, but do "
            "not advance canonical freshness baselines.\n"
            "- `blocked`: return the exact gap to the main agent and stop.\n\n"
            "Use this fixed loop:\n"
            "1. Inspect the scoped task/feature context and the targeted maintained KB docs.\n"
            "2. Use `builder_kb_search` / `builder_kb_show` to confirm whether the relevant "
            "`system-docs`, `feature`, and/or `testing` docs are missing, stale, or current.\n"
            "3. For first-doc creation, call `builder_kb_contract` before drafting. For updates "
            "that change maintained-doc metadata or regenerate markdown, re-check "
            "`builder_kb_contract` before publishing. Do not invent headings or required "
            "metadata from memory.\n"
            "4. Use `builder_kb_lint` to catch contract failures before `builder_kb_add` or "
            "before any regenerated `builder_kb_update` payload.\n"
            "5. When broader app understanding needs a canonical refresh on `main`, run "
            "`builder_kb_extract` instead of recreating system docs manually.\n"
            "6. Retrieve the resulting docs through the normal KB read path.\n"
            "7. Run deterministic KB validation when `requires_validate=true` and capture "
            "whether it passed or what gap remains.\n"
            "8. Return a compact result.\n\n"
            "Do not perform unrelated cleanup. Do not fix blocking system-doc "
            "dependency hashes. If clarification is required, return a blocked "
            "result instead of asking the user directly.\n\n"
            "Canonical freshness rules for maintained `feature` and `testing` docs:\n"
            "- Canonical freshness is anchored to `main`, not the current branch tip.\n"
            "- On non-`main` branches, stay advisory-only: inspect and report "
            "likely stale docs, but do not advance canonical freshness baselines.\n"
            "- On canonical `main` refreshes, stamp "
            "`documented_against_commit`, `documented_against_ref=main`, and "
            "`owned_paths` on every maintained doc you create or update.\n"
            "- Use any provided freshness context pack first so candidate "
            "selection stays diff-bounded instead of rereading the entire "
            "maintained corpus.\n\n"
            "Hard stop policy:\n"
            "- Fetch the KB contract at most once per task.\n"
            "- Attempt at most one repair retry after a lint or publish failure.\n"
            "- If the second attempt still fails, return `blocked` with the exact contract gap "
            "or publish error.\n"
            "- Keep `system-docs` canonical and user-readable, but retrieve and publish only "
            "through builder-owned lanes.\n\n"
            "Always finish with exactly one JSON object and nothing else. Use this shape:\n"
            "{\n"
            '  "status": "already_current|updated_and_verified|partially_updated|blocked",\n'
            '  "task_id": "<task id or empty>",\n'
            '  "feature_id": "<feature id or empty>",\n'
            '  "system_doc_refresh": "not_needed|refreshed|attempted_but_blocked",\n'
            '  "created_doc_ids": ["..."],\n'
            '  "updated_doc_ids": ["..."],\n'
            '  "retrieval_verified": true,\n'
            '  "validation_status": "pass|fail|partial",\n'
            '  "remaining_gap": "<specific gap or empty>",\n'
            '  "summary": "<one-sentence summary>"\n'
            "}"
        ),
        tools=DOCUMENTATION_AGENT_TOOLS,
        model="sonnet",
    ),
}


def get_agent_definition(name: str) -> AgentDefinition:
    """Get an agent definition by name. Raises KeyError if not found."""
    if name not in AGENT_DEFINITIONS:
        raise KeyError(f"Agent '{name}' not defined. Available: {list(AGENT_DEFINITIONS.keys())}")
    return AGENT_DEFINITIONS[name]


def get_subagent_definition(name: str) -> SubagentDefinition:
    """Get a subagent definition by name. Raises KeyError if not found."""
    if name not in SUBAGENT_DEFINITIONS:
        raise KeyError(
            f"Subagent '{name}' not defined. Available: {list(SUBAGENT_DEFINITIONS.keys())}"
        )
    return SUBAGENT_DEFINITIONS[name]
