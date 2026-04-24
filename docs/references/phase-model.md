# Phase Model

Canonical phase-boundary map for agent-native delivery in this repo.

Use this doc as the owner surface when changing:
- phase semantics
- phase entry conditions
- which lane owns operator questioning
- which tools should be auto-allowed, denied, or operator-gated by phase
- how interactive Agent-page work hands off to background execution

This doc defines the canonical model first. It does not rename current task
statuses by itself.

## Purpose

Autonomous Agent Builder should feel like one product that advances work through
clear phases. The user should not have to decide when to interview, plan,
design, implement, verify, or integrate. The system should know.

This phase model keeps those boundaries explicit and context-efficient.

## Entry Paths

There are two canonical entry paths:

1. Forward engineering
   Starts in `requirements`.
   Use when the product or repo is not yet shaped and the agent must turn an
   initial idea into a bounded product direction and initial feature set.
2. Existing-product delivery
   Starts in `planning`.
   Use when the repo already exists and the user wants to add or modify a
   feature on top of the current product.

`Add/modify feature` is an entry condition into `planning`, not a separate
phase.

## Canonical Phases

- [requirements.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phases/requirements.md)
- [planning.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phases/planning.md)
- [design.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phases/design.md)
- [implementation.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phases/implementation.md)
- [verification.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phases/verification.md)
- [integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phases/integration.md)

## Current Repo Mapping

Current task statuses remain the implementation reality for now:

`planning -> design_review/design -> implementation -> quality_gates -> pr_creation -> review_pending -> build_verify`

Canonical mapping:

- `requirements`
  Repo mapping: forward-engineering interactive intake before task-status
  dispatch begins.
- `planning`
  Repo mapping: `pending`, `planning`, and the existing interactive feature
  backlog interview lane for repo changes.
- `design`
  Repo mapping: `design` plus `design_review`.
  Boundary note: design may stay read-only in the main repo context; it should
  hand off one bounded task packet into workspace-backed implementation.
- `implementation`
  Repo mapping: `implementation`.
  Boundary note: this is the first default repo-mutating phase, so the task
  workspace must already be provisioned here.
- `verification`
  Repo mapping: `quality_gates`.
- `integration`
  Repo mapping: `pr_creation`, `review_pending`, `build_verify`.

## SDK-Grounded Rules

- Safe, phase-appropriate read-only tools should be auto-approved through
  `allowed_tools` or equivalent permission rules.
- `canUseTool` is for runtime approvals and operator input handling, not for
  blocking normal technical discovery.
- `AskUserQuestion` is the built-in operator clarification path.
- `TodoWrite` is the built-in organized-progress path for complex multi-step
  work inside an active session; it does not replace durable backlog or task
  state.
- Operator-facing questioning must stay in the top-level interactive lane.
  `AskUserQuestion` is not available inside subagents spawned via the `Agent`
  tool.
- Subagents are optional specialist lanes for context isolation and bounded
  parallel work, not a default owner for every phase.
- Stable workspace `cwd` is the SDK-level execution contract for coding phases.
  In this repo, git worktrees are the default implementation of that contract
  for git-backed tasks.
- Background phases that need operator input should return a bounded blocked
  handoff to the Agent page instead of improvising hidden freeform chat.

## Follow-On Alignment Plan

This doc set is normative for future alignment. Immediate follow-on runtime work
should:

- relax planning-lane permissions so bounded read-only repo discovery is
  auto-allowed
- keep mutation tools denied in `requirements` and `planning`
- keep `AskUserQuestion` only for true operator decisions
- add a stable blocked-handoff contract for non-interactive phases that need
  operator input
- provision a persisted workspace at the `design -> implementation` handoff and
  reuse it through verification and integration
- align prompts and routing so clean-slate product creation starts in
  `requirements` while existing-repo feature delivery starts in `planning`
- align tests with the per-phase permission matrix and handoff rules
