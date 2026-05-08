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

There are two canonical entry paths after `builder init` and Day-0 readiness:

1. Forward engineering
   Enters `requirements` after readiness returns `agent_ready`.
   Use when the product or repo is not yet shaped and the agent must turn an
   initial idea into a bounded product direction and initial feature set.
2. Reverse engineering / existing-product delivery
   Enters repo understanding and `planning` after readiness returns
   `agent_ready`.
   Use when the repo already exists and the user wants to add or modify a
   feature on top of the current product.

`Add/modify feature` is an entry condition into `planning`, not a separate
phase.

Readiness is a pre-phase gate, not a delivery phase. Its canonical contract is
[day-0-readiness.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/day-0-readiness.md).

During validation, phase progression must be driven by natural Agent-page
prompts and visible dashboard actions. The user should not choose model, effort,
tools, MCP servers, context strategy, phase names, or task-dispatch commands.
The dashboard-first validation contract is
[dashboard-first-validation.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/dashboard-first-validation.md).

## Canonical Phases

- [requirements.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phases/requirements.md)
- [planning.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phases/planning.md)
- [design.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phases/design.md)
- [implementation.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phases/implementation.md)
- [verification.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phases/verification.md)
- [integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phases/integration.md)

## Current Repo Mapping

Current task statuses remain the implementation reality for now:

`queued/pending -> planning -> design_review/design -> implementation -> quality_gates -> pr_creation -> review_pending -> build_verify`

Canonical mapping:

- `requirements`
  Repo mapping: forward-engineering interactive intake after readiness and
  before task-status dispatch begins.
- `planning`
  Repo mapping: `queued`, `pending`, `planning`, reverse-engineering repo
  understanding, and the existing interactive feature backlog interview lane for
  repo changes.
  Forward-engineering sprint note: after sprint backlog approval, planning may
  run once at sprint scope and attach per-task implementation briefs to queued
  tasks. Tasks covered by an approved sprint plan do not need a separate
  task-level planning approval. The sprint planning turn must request a
  sprint-scope approval before persisting the sprint plan or creating Board
  tasks; if denied, the product backlog is left unchanged.
- `design`
  Repo mapping: `design` plus `design_review`.
  Boundary note: design may stay read-only in the main repo context; it should
  hand off one bounded task packet into workspace-backed implementation.
  Forward-engineering sprint note: design may run once at sprint scope when
  approved items share architecture or domain context. Task-level design remains
  reserved for high-risk or independent architecture changes.
- `implementation`
  Repo mapping: `implementation`.
  Boundary note: this is the first default repo-mutating phase, so the task
  workspace must already be provisioned here.
  Board rendering note: the sprint-level Implementation stage should be treated
  as active only while implementation or downstream integration runtime work is
  in flight. Plan and Design details belong behind the sprint detail sidebar,
  not as repeated chips or always-visible orchestration tables inside each
  status lane.
  Multi-sprint board note: the Board defaults to the latest/current sprint and
  filters task lanes to that sprint's generated task IDs. Older sprint tasks are
  available through the sprint selector, not mixed into the current sprint lanes.
- `verification`
  Repo mapping: `quality_gates`.
  Forward-engineering sprint note: after implementation tasks complete, the
  sprint must prove the generated app through build/test/lint plus Browser Use
  acceptance evidence. A shell or app-local proof script may validate a recorded
  Browser Use artifact when local headless Chrome is unstable.
- `integration`
  Repo mapping: `pr_creation`, `review_pending`, `build_verify`.
  Forward-engineering sprint note: `build_verify` owns final sprint completion.
  Real verifier failures keep the task failed/blocked; advisory metadata gaps
  such as `git status` in a non-git disposable directory do not block shipping
  when build/test/lint/browser proof pass. When all sprint-generated tasks are
  `done`, integration marks the sprint `shipped`, verification `passed`, and the
  approved backlog feature `done`. After that state transition, builder may run
  the `optimization-agent` as a post-ship delivery-system review. That agent can
  act on structured observability recommendations, but it must not reopen or
  redefine the shipped sprint lifecycle.

## SDK-Grounded Rules

- Safe, phase-appropriate read-only tools should be auto-approved through
  `allowed_tools` or equivalent permission rules.
- `canUseTool` is for runtime approvals and operator input handling, not for
  blocking normal technical discovery.
- `AskUserQuestion` is the built-in operator clarification path.
- If a top-level Claude Agent SDK lane restricts tools explicitly, include
  `AskUserQuestion` in that lane's allowed tools whenever ambiguous user intent
  may need clarification.
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
- Sprint-level planning and design are read-only artifacts. They may happen
  before task worktrees exist, but every mutating implementation task or batch
  must still receive a persisted workspace before file edits.
- Integration auto-commits any uncommitted workspace changes before merging the
  task branch, so no work is lost if the agent finishes without committing.
- Recovered tasks must clear stale operator-decision handoffs before re-entering
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
  `requirements` while reverse-engineering feature delivery starts in
  repo understanding and `planning`
- align tests with the per-phase permission matrix and handoff rules
