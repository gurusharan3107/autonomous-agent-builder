---
title: "Autonomous Builder agent catalog rubric"
tags: ["agents", "runtime", "rubric", "lifecycle"]
doc_type: "rubric"
created: "2026-05-15"
---

# Autonomous Builder Agent Catalog Rubric

## Purpose

Use this rubric to identify every Builder-provided lifecycle agent and SDK
subagent, what each one owns, what it can do, what it cannot do, and when it
must ask or block.

This rubric covers the agents declared in
`src/autonomous_agent_builder/agents/definitions.py`:

- primary lifecycle agents in `AGENT_DEFINITIONS`
- Claude Agent SDK sidecar specialists in `SUBAGENT_DEFINITIONS`

For a new-person visual walkthrough of the same architecture and sprint cycle,
open `docs/rubric/agent-sprint-cycle-explainer/index.html`.

It does not replace the surface-specific rubrics for the Agent page or Realtime
Voice. Realtime Voice behavior is owned by
`docs/rubric/realtime-voice-agent-page-agent.md`. SDK-backed Agent page behavior
is owned by `docs/rubric/sdk-backed-agent-page-agent.md`. Codex project subagent
quality is owned by `docs/quality-gate/codex-subagents.md`.

If implementation disagrees with this rubric, treat that as either a code bug
or an explicit product decision that must update the rubric and owner map in the
same change.

## Universal Rules

- Builder owns lifecycle state. Agents consume and mutate it only through
  granted Builder tools and orchestrator-owned transitions.
- Board, backlog, task, approval, memory, knowledge, metrics, and observability
  semantics stay in Builder-owned surfaces. Agents do not redefine those
  semantics in freeform prose.
- Background phase agents must not ask the operator in plain prose. When blocked
  on an operator decision, they emit `OPERATOR_DECISION_JSON:` followed by one
  raw JSON object and stop.
- User-facing chat agents may use `AskUserQuestion` for bounded clarification
  and visible approval paths for mutating actions.
- A mutating action needs an allowed tool, a clear target, and either clear
  operator intent or visible approval. Broad wording is not blanket approval.
- Generated-app task agents edit only the selected task workspace. They do not
  patch generated apps by hand to satisfy Builder validation outside the
  lifecycle lane.
- Subagents are sidecar evidence lanes. They do not own lifecycle state, sprint
  state, approval state, or final shipping decisions.

## Responsibility-First Tool Assignment

Do not start by asking which tool calls a model should have. Start with the
agent responsibility and derive tools from that responsibility.

Use this sequence for every agent:

1. Define the job the agent owns.
2. Define the lifecycle state, code, docs, or evidence it must inspect to do
   that job.
3. Define the exact state changes it is allowed to make.
4. Grant only the tools needed for those reads and writes.
5. Decide auto-approval separately. A tool can be allowed but still require
   operator approval.

If a desired tool does not follow from the agent responsibility, do not add it
to that agent. Create or route to the agent that actually owns the
responsibility.

## Primary Lifecycle Agents

| Agent | Responsibility owner | Allowed tool calls derived from responsibility | Cannot do or must ask |
| --- | --- | --- | --- |
| `chat` | User-facing Agent page operator. Interprets natural operator intent, retrieves current Builder state, explains it, asks clarifying questions, and executes clear operator-directed Builder actions. | Read/search: `Read`, `Glob`, `Grep`, `mcp__builder__board`, `mcp__builder__backlog_item_list`, `mcp__builder__backlog_item_show`, `mcp__builder__task_list`, `mcp__builder__task_show`, `mcp__builder__task_status`, `mcp__builder__kb_search`, `mcp__builder__memory_search`. Clarify: `AskUserQuestion`. Mutate only when the target and consequence are clear: `mcp__builder__task_recover`, `mcp__builder__task_dispatch`, `mcp__builder__workspace_scaffold` (when workspace needs language-aware setup), `mcp__builder__kb_add`, `mcp__builder__kb_update`, `mcp__builder__memory_add`. | Cannot treat broad wording as blanket approval. Cannot mark work done, shipped, approved, denied, cleared, or deleted by assertion. Cannot run `Bash`, `Write`, or `Edit` — when workspace setup is needed, must invoke `mcp__builder__workspace_scaffold` instead of trying to scaffold via shell. Cannot use Bash, git, npm, or tests as primary Board evidence. Must ask or route approval when target, consequence, or operator intent is unclear. |
| `scaffold` | Runtime-decided workspace bootstrap agent. Decides the stack (web/desktop/CLI/library), language, and gate set from the feature intent and operator answers, then scaffolds the minimum config files and registers the matching gates. Runs as a phase between requirements approval and first implementation dispatch, and on demand from `chat` via `mcp__builder__workspace_scaffold`. | Workspace setup tools: `Read`, `Write`, `Edit`, `Glob`, `Grep`, `Bash` (within workspace `cwd`), `mcp__workspace__get_project_info`, `mcp__workspace__list_directory`, `mcp__workspace__read_file`, `mcp__workspace__run_command`. Clarify stack: `AskUserQuestion`. Register gate set for detected language: `mcp__builder__gates_register`. Scoped Builder context: `mcp__builder__task_show`, `mcp__builder__kb_search`, `mcp__builder__memory_search`. | Cannot hardcode a single language; must decide stack at runtime per feature/operator intent. Cannot mutate backlog, board, sprint, or approval state. Cannot edit anything outside the workspace `cwd`. Cannot dispatch implementation work — only prepares the workspace. Must emit `OPERATOR_DECISION_JSON` if the stack remains genuinely ambiguous after one round of structured questions. |
| `init-project-chat` | User-facing requirements interviewer for forward-engineering bootstrap. Converges on a backlog-ready product contract. | Read/search: `Read`, `Glob`, `Grep`, `Bash`, `mcp__builder__kb_search`, `mcp__builder__memory_search`, `mcp__builder__task_list`, `mcp__builder__task_show`. Clarify: `AskUserQuestion`. | Cannot implement, dispatch, recover, approve, or mutate lifecycle state. Must ask structured product-scope questions when requirements are unclear. |
| `planner` | Background sprint planner. Converts an approved feature into ordered tasks with dependencies and acceptance criteria. | Read/search only: `Read`, `Glob`, `Grep`, `mcp__builder__kb_search`, `mcp__builder__kb_show`, `mcp__builder__memory_search`. | Cannot implement, design architecture, mutate Builder state, or ask the operator directly. Must emit `OPERATOR_DECISION_JSON` if planning needs a product decision. |
| `designer` | Background architecture and contract designer. Produces ADR-style decisions, API contracts, schema proposals, and integration plans. | Read/search: `Read`, `Glob`, `Grep`, `mcp__builder__kb_search`, `mcp__builder__kb_show`, `mcp__builder__memory_search`. KB mutation only when the design creates durable repo knowledge: `mcp__builder__kb_add`, `mcp__builder__kb_update`. | Cannot implement feature code or decide unresolved product tradeoffs. Must emit `OPERATOR_DECISION_JSON` for blocked design choices. |
| `code-gen` | Background task implementer for one selected task workspace. | Workspace reads/edits/runs: `Read`, `Edit`, `Write`, `Glob`, `Grep`, `mcp__workspace__get_project_info`, `mcp__workspace__list_directory`, `mcp__workspace__read_file`, `mcp__workspace__run_command`, `mcp__workspace__run_tests`, `mcp__workspace__run_linter`. Scoped Builder context: `mcp__builder__task_show`, `mcp__builder__kb_search`, `mcp__builder__kb_show`, `mcp__builder__memory_search`. | Cannot inspect Board or backlog because the orchestrator already selected the task. Cannot edit root `CLAUDE.md`, `.claude/CLAUDE.md`, or `AGENTS.md`. Cannot ask the user directly. Must emit `OPERATOR_DECISION_JSON` if implementation needs an operator choice. |
| `integration-resolver` | Background conflict resolver for generated-app task workspaces. | Conflict-scope workspace tools: `Read`, `Edit`, `Write`, `Bash`, `Glob`, `Grep`. | Cannot run `git rebase --abort`, `git rebase --continue`, `git commit`, or `git merge`; the orchestrator owns lifecycle Git operations. Cannot broaden edits beyond listed conflict files unless a directly related test needs adjustment. |
| `pr-creator` | PR preparation for a real Git workspace with a PR target. | PR evidence tools: `Read`, `Bash`, `Glob`, `Grep`. | Cannot operate as a PR agent outside a real Git workspace. If no PR target exists, stop with `NO_PR_TARGET`. Cannot use PR creation as a substitute for deterministic local change evidence. |
| `build-verifier` | Post-merge or missing-proof build verifier. | Smallest verification evidence tools: `Read`, `Bash`, `Glob`, `Grep`. | Cannot repair failures unless explicitly routed to repair work. Cannot repeat proof already supplied by deterministic Builder scripts for local generated-app workspaces. |
| `feature-verifier` | Generated-app feature acceptance verifier and Playwright coverage maintainer. | Workspace visible-behavior verification and repairs: `Read`, `Edit`, `Write`, `Glob`, `Grep`, `mcp__workspace__read_file`, `mcp__workspace__list_directory`, `mcp__workspace__run_command`, `mcp__workspace__run_tests`. | Cannot skip user-visible acceptance validation. Cannot edit Builder runtime guidance files. Cannot dump full traces, browser logs, test lists, or bundles into the transcript. |
| `documentation-bridge` | Orchestrator bridge for bounded maintained-doc refresh work. | No direct tools. It routes resolved documentation work to `documentation-agent`. | Cannot directly mutate docs, code, KB, or memory. Cannot become a second documentation policy owner. |
| `optimization-agent` | Post-ship optimization reviewer for observability-backed recommendations. | Evidence: `Read`, `Glob`, `Grep`, `Bash`, `mcp__builder__metrics`, `mcp__builder__task_show`, `mcp__builder__kb_search`, `mcp__builder__kb_show`, `mcp__builder__memory_search`. Target-app harness edits: `Edit`, `Write`. Builder-side follow-up: `mcp__builder__recommendation_create`. | Cannot optimize by pushing prompt memorization onto the user. Cannot skip tests, weaken acceptance, hide failures, or alter shipped feature scope, backlog priority, sprint state, approval state, runtime selection, or user-facing behavior unless evidence requires that exact change. Cannot edit Builder source directly from a generated-app workspace. |

## SDK Subagents

| Subagent | Responsibility owner | Allowed tool calls derived from responsibility | Cannot do or must ask |
| --- | --- | --- | --- |
| `repo-researcher` | Read-only sidecar for repository, ownership, and architecture evidence. | `Read`, `Glob`, `Grep`, `mcp__builder__task_show`, `mcp__builder__kb_search`, `mcp__builder__kb_show`, `mcp__builder__memory_search`. | Cannot edit files, mutate Builder state, or own a lifecycle decision. |
| `browser-verifier` | Sidecar for browser-visible acceptance evidence and UI regression summaries. | `Read`, `Glob`, `Grep`, `Bash`, `mcp__workspace__get_project_info`, `mcp__workspace__list_directory`, `mcp__workspace__read_file`, `mcp__workspace__run_command`, `mcp__workspace__run_tests`, `mcp__workspace__run_linter`. | Cannot become the implementation owner or final lifecycle authority. Cannot mutate Builder Board, backlog, or approvals. |
| `build-verifier` | Sidecar for deterministic build, lint, test, and changed-file evidence. | `Read`, `Glob`, `Grep`, `Bash`, `mcp__workspace__get_project_info`, `mcp__workspace__list_directory`, `mcp__workspace__read_file`, `mcp__workspace__run_command`, `mcp__workspace__run_tests`, `mcp__workspace__run_linter`. | Cannot repair failures unless explicitly asked. Cannot replace the parent agent's lifecycle decision. |
| `security-reviewer` | Sidecar for security and permission-risk evidence on changed surfaces. | `Read`, `Glob`, `Grep`, `mcp__builder__task_show`, `mcp__builder__kb_search`, `mcp__builder__kb_show`, `mcp__builder__memory_search`. | Cannot edit files, broaden the review scope, or approve risky behavior by omission. |
| `pr-reviewer` | Sidecar for PR-readiness evidence, changed-file summaries, and residual risk. | `Read`, `Glob`, `Grep`, `mcp__builder__task_show`, `mcp__builder__metrics`, `mcp__builder__kb_search`, `mcp__builder__memory_search`. | Cannot create or merge PRs. Cannot mutate lifecycle, approval, or Board state. |
| `documentation-agent` | Sidecar owner for maintained repo-local KB creation, update, extraction, linting, and validation. | `mcp__builder__task_show`, `mcp__builder__kb_search`, `mcp__builder__kb_show`, `mcp__builder__kb_contract`, `mcp__builder__kb_lint`, `mcp__builder__kb_extract`, `mcp__builder__kb_add`, `mcp__builder__kb_update`, `mcp__builder__kb_validate`. | Cannot edit repo docs under `docs/`, edit code, or write memory entries. Must respect the provided resolved documentation action instead of inferring a new lane. |

## Per-Agent Operating Rubric

For each agent below: what it must inspect before acting, what evidence it must
produce, how to grade whether it did its job, the failure modes to watch for,
and the `builder` CLI signals that reveal misbehavior during live testing.

### `chat`

- **Inputs (must read before acting):** current operator message; visible Board
  state via `mcp__builder__board`; the selected task's status and blocked
  reason via `mcp__builder__task_status` / `task_show`; relevant backlog item
  via `backlog_item_show`. Do not retrieve broader retrieval surfaces unless
  the current operator intent requires them.
- **Outputs:** one product-language response that either explains state,
  routes intent to a lifecycle MCP, or emits a structured `AskUserQuestion`.
  Every tool mutation must name an exact target and consequence.
- **Quality bar:** zero forbidden operator-language terms (see GOAL.md
  "Forbidden Operator Language"); zero direct file writes; zero shell
  workarounds for missing lifecycle MCPs; one outstanding question card at a
  time; cache ratio > 5x after turn 2; response length proportional to the
  decision in front of the operator.
- **Failure modes:** asking the operator about permissions / Write hooks /
  worktree paths / dispatch; attempting to bootstrap or write code via Bash;
  treating a 409 `task_not_recoverable` as recoverable; repeating an MCP call
  that previously returned a valid payload because Builder mis-flagged the
  result as `tool_error`.
- **Tuning signals (live CLI inspection):**
  - `builder agent history --session <id> --full --json` → enumerate
    `tool_use` types. Any non-empty count of `Bash`, `Write`, or `Edit` means
    `chat` is doing scaffold / code-gen work that should be routed to
    `scaffold` or `code-gen` instead.
  - `mcp__builder__*` items returning with `type: tool_error` while
    `payload.content` contains valid JSON ⇒ Builder-side result classification
    bug; do not blame `chat` for retrying.
  - `builder logs analyze --session <id> --json` reporting `cache_ratio: 0`
    after turn 2 ⇒ system prompt or per-turn prefix is varying; not a `chat`
    bug but a runner-side cache key bug.

### `scaffold`

- **Inputs:** approved feature description; operator answers from prior
  `chat` turns; existing workspace contents (`mcp__workspace__list_directory`,
  `_detect_language` equivalent); any pre-existing config files that indicate
  an in-place stack.
- **Outputs:** a written scaffold (`pyproject.toml` + ruff/pytest config for
  Python; `package.json` + eslint config for Node; `go.mod` for Go; etc.); a
  registered gate set via `mcp__builder__gates_register`; one short summary
  message identifying the stack chosen and why; durable workspace state that
  lets a fresh `_detect_language` return a concrete language.
- **Quality bar:** stack chosen matches the feature intent without forcing
  the operator to know language names; gates registered actually run (no
  `FileNotFoundError`); a single `code-gen` dispatch immediately after
  scaffold completes with all gates passing; idempotent — re-running on an
  already-scaffolded workspace is a no-op.
- **Failure modes:** hardcoding Python; scaffolding the wrong stack for the
  feature (CLI when operator wanted web); writing files outside `cwd`;
  registering gates that have no binary available; producing empty
  directories without config files; never running — i.e., orchestrator
  dispatched `code-gen` first.
- **Tuning signals:**
  - Fresh devpulse run with no `pyproject.toml`/`package.json` after
    requirements approval ⇒ scaffold phase didn't run.
  - `code-gen` agent runs where `blocked_reason` mentions `FileNotFoundError`
    in `code_quality`/`testing` gates ⇒ scaffold phase didn't register the
    matching gate set.
  - Operator-page chat contains the phrase "bootstrap", "Write permission",
    or "pyproject.toml" ⇒ `scaffold` was bypassed and `chat` is trying to do
    the job itself.

### `planner`

- **Inputs:** approved feature description; existing codebase structure via
  `Read`/`Glob`/`Grep`; relevant KB docs via `kb_search` / `kb_show`;
  relevant prior decisions via `memory_search`.
- **Outputs:** ordered task list with dependencies, complexity, and
  acceptance criteria; an `OPERATOR_DECISION_JSON` if any planning question
  cannot be resolved from retrieval.
- **Quality bar:** each task has a single owner, a single workspace, a
  visible acceptance criterion, and is sized for one implementation run; no
  task assumes scaffold work; no task mutates Builder runtime guidance.
- **Failure modes:** producing tasks that overlap file ownership; planning
  scaffold work as a regular task (scaffold belongs to the `scaffold` agent);
  asking the operator directly instead of emitting
  `OPERATOR_DECISION_JSON`.
- **Tuning signals:** task list with `setup-*` titles that should have been
  scaffold work; tasks whose acceptance criteria require an unbootstrapped
  workspace to already have config.

### `code-gen`

- **Inputs:** the single selected task brief and design context via
  `mcp__builder__task_show`; the task workspace (worktree `cwd`); any
  language-specific config the scaffold agent already produced; KB context
  if `knowledge_requirements` reference it.
- **Outputs:** code changes inside the worktree; passing
  `mcp__workspace__run_tests` / `run_linter`; a bounded final response (≤ 8
  lines per the prompt) listing changed files and pass/fail evidence.
- **Quality bar:** zero edits outside the worktree (enforced by
  `enforce_workspace_boundary` hook); zero edits to `CLAUDE.md` /
  `AGENTS.md`; tests added or updated for the new behavior; lint passes; the
  final response stays bounded.
- **Failure modes:** writing outside the worktree (hook should block); long
  freeform narration in the final response; running long-lived dev servers
  in foreground; emitting browser proof from this lane (belongs to
  `feature-verifier` / `browser-verifier`).
- **Tuning signals:** `enforce_workspace_boundary` denials in audit log ⇒
  worktree `cwd` is wrong, or `code-gen` is trying to edit Builder source;
  `chunk_pressure_risk: true` from `builder metrics show --json --full` ⇒
  long Bash output not redirected to a temp log; `num_turns >> task
  complexity` ⇒ task brief or design context was insufficient.

### `build-verifier`

- **Inputs:** the worktree at terminal state; project-specific lint/test
  commands derived from registered gate set.
- **Outputs:** structured pass/fail evidence (file list, command list,
  command outputs); a short summary suitable for the parent run's evidence
  field.
- **Quality bar:** zero edits; runs only the commands the registered gate
  set defines; does not repeat proof already supplied by deterministic
  scripts; emits a stable JSON shape consumable by `agent_runs.evidence`.
- **Failure modes:** trying to repair failures (out of scope); dumping full
  test transcripts into the parent run output; depending on local-machine
  state not reflected in the worktree.
- **Tuning signals:** any `Edit` / `Write` tool call in `builder agent
  history` for this run ⇒ wrong tools granted; `duration_ms` >> typical run
  ⇒ running commands outside the gate set.

The remaining agents (`integration-resolver`, `pr-creator`,
`feature-verifier`, `documentation-bridge`, `optimization-agent`, plus all
SDK subagents) retain the existing table-row contract above. Add a per-agent
stanza here when extending or constraining any of them.

## Permission Derivation

Allowed tools and auto-approved tools are separate decisions:

- Allow a tool only when the agent responsibility requires that read or write.
- Auto-approve read-only tools only when their source of truth is already within
  the agent's responsibility.
- Do not auto-approve mutating tools just because the agent owns the
  responsibility. First require a clear target and consequence.
- If the same tool could support two responsibilities, route the task to the
  agent that owns the responsibility instead of broadening another agent.

## Evaluation Checklist

- Is the selected agent the narrow owner for the current phase or surface?
- Did the agent use only tools that its definition grants?
- Did it retrieve Builder state through Builder tools instead of inferring from
  backlog prose, Git state, or test output?
- Did any mutating action have a clear target and either clear intent or visible
  approval?
- Did a background agent emit `OPERATOR_DECISION_JSON` instead of asking the
  operator directly?
- Did generated-app work stay inside the selected task workspace and avoid
  protected Builder guidance files?
- Did subagents stay sidecar and avoid lifecycle ownership?
- Did documentation work use the maintained KB tools when updating KB, and avoid
  repo docs unless the owning doc surface was intentionally changed?

## Validation

Useful checks after changing agent definitions, tools, or this rubric:

```bash
builder quality-gate claude-agent-sdk --json
builder quality-gate builder-cli --json
PYTHONPATH=src pytest tests/test_definitions.py tests/test_builder_tool_service.py -q
```

For Agent page or lifecycle behavior changes, also run the relevant focused
`tests/test_embedded_agent_routes.py` or `tests/test_realtime_voice_operator.py`
cases and complete browser-visible validation through the dashboard workflow.

## Related Docs

- `docs/rubric/sdk-backed-agent-page-agent.md`
- `docs/rubric/realtime-voice-agent-page-agent.md`
- `docs/rubric/deterministic-vs-model-backed-agent-behavior.md`
- `docs/quality-gate/agent-quality.md`
- `docs/quality-gate/claude-agent-sdk.md`
- `docs/quality-gate/codex-subagents.md`
- `docs/references/phase-model.md`
