# Autonomous Delivery Documentation Refresh

Stable reference for how Autonomous Agent Builder should own documentation
freshness inside the software delivery lifecycle.

Use this doc as the owner surface when changing:
- where documentation refresh belongs in the SDLC
- which runtime owns the decision to refresh maintained docs
- how documentation refresh relates to worktree, branch, commit, and PR strategy
- how Git and GitHub automation should participate without becoming the delivery
  owner

## Purpose

Autonomous Agent Builder exists to own software delivery as one coherent
product.

That includes documentation freshness.

Maintained documentation is not an afterthought and not a separate external
workflow. It is part of the same delivery system that owns planning, design,
implementation, validation, branching, worktree use, commit strategy, and
release readiness.

The user should not need to decide:
- when documentation should refresh
- whether a doc update belongs before or after PR creation
- whether GitHub automation or an internal specialist should own the work
- how documentation freshness interacts with worktrees, commits, or merge flow

Those are builder responsibilities.

## Mission Alignment

This contract follows
[MISSION.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/MISSION.md):

- the system owns the real work of the software lifecycle
- workflow, model, tool, and context choices stay inside one operating
  environment
- documentation and knowledge are maintained as part of delivery, not as an
  external cleanup task
- worktrees, reusable procedures, and automated validation are built-in product
  responsibilities

This doc exists to keep documentation freshness aligned with that mission
instead of drifting toward an external-user mental model such as “someone
pushed to `main`, now documentation should react.”

## Ownership Contract

### Builder and orchestrator own

- SDLC progression and phase ordering
- worktree strategy and workspace isolation choices
- branch strategy and branch lifecycle
- commit strategy and publish readiness
- deciding when maintained docs must be created, refreshed, or verified
- invoking the documentation refresh gate before publish or merge decisions
- deciding whether a Git or GitHub transport lane is needed

### Documentation-agent owns

- bounded refresh of repo-local maintained KB and documentation surfaces
- retrieval-led verification of the updated docs
- deterministic validation follow-through on the documentation scope it touched
- reporting exact remaining gaps when documentation cannot be completed safely

The documentation-agent remains an internal specialist, not a separate product
persona and not the owner of delivery sequencing.

See
[documentation-agent.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/documentation-agent.md)
for the detailed specialist contract.

### Git and GitHub lanes own

- transport work after builder has already decided the strategy
- branch creation or switching when requested by the builder-owned delivery flow
- pushing a prepared branch
- opening or updating a PR
- observing merge or CI outcomes

Git or GitHub lanes do not own:
- worktree policy
- branch policy
- commit policy
- documentation freshness policy
- SDLC routing

They are publish transport, not the delivery brain.

## Primary Delivery Flow

The mission-aligned path is builder-owned delivery first:

`planning -> design -> implementation -> quality_gates -> pr_creation -> build_verify`

This means:

- documentation refresh should happen before final publish or merge decisions
- maintained docs should be assessed in the same delivery flow that owns code
  changes and verification
- branch, worktree, and commit decisions should already be under builder
  control when documentation refresh runs
- documentation should not primarily depend on a post-merge recovery flow to
  remain current
- the current implementation runs the documentation refresh gate inside the
  `quality_gates -> pr_creation` boundary after code/test gates pass or warn,
  and before PR promotion is allowed

The documentation refresh gate is the checkpoint where the builder determines:
- whether maintained docs are already current
- whether a bounded documentation-agent refresh is required
- whether documentation blocks promotion to the next delivery step
- whether the remaining gap is documentation-scoped or a broader quality issue

## Safety Net Role Of Post-Main Automation

The existing `push`-to-`main` documentation workflow remains useful, but only as
a secondary backstop.

Its role is:
- audit for documentation drift after merged changes land
- catch cases that escaped the primary builder-owned flow
- open bounded repair work or follow-up PRs when drift is detected

Its role is not:
- primary documentation ownership
- deciding the normal point at which maintained docs should refresh
- replacing the documentation refresh gate inside builder-owned delivery

When the primary builder-owned flow is working correctly, post-`main`
automation should be rare, corrective, and audit-oriented.

## Invocation Boundary

The intended boundary is:

- external entrypoint: builder-owned surface
- internal execution: Claude Agent SDK bridge plus the internal
  `documentation-agent`
- tool execution: builder MCP/tool-service route

This means:

- users or automation should enter through a builder-owned command or delivery
  phase
- the app should use its internal Claude Agent SDK bridge to invoke the
  documentation-agent
- the documentation-agent should use the builder-owned KB/task tools backed by
  shared services
- internal runtime code should not treat CLI subprocess calls as the default
  owner boundary

## Main Baseline Contract

Canonical maintained-doc freshness remains anchored to `main`.

That baseline contract is owned by
[main-commit-reference.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/main-commit-reference.md).

This doc does not change that rule. It changes where the decision to apply that
rule belongs:
- primary inside builder-owned delivery flow
- secondary inside post-`main` drift detection

## Non-Goals

This architecture should not become:

- a GitHub-first delivery system where CI owns documentation strategy
- a separate GitHub agent that decides worktree, branch, commit, and doc
  policy
- a documentation policy that lives mainly in post-merge automation
- a duplicate owner split where builder, documentation-agent, and GitHub docs
  all claim the same responsibility

## Anti-Patterns

- treating “push to `main`” as the normal trigger for documentation freshness
- making GitHub automation the owner of branch, worktree, or commit strategy
- invoking freeform Claude prompts in CI as the primary documentation owner
  path
- requiring the user to decide when documentation should refresh during normal
  delivery
- letting documentation refresh happen outside builder-owned publish readiness
  decisions

## Expected Follow-Through

This spec is architecture-first.

It should guide later implementation work that:
- introduces or formalizes a builder-owned documentation refresh gate before
  `pr_creation`
- keeps the documentation-agent as the bounded internal specialist
- keeps the existing post-`main` workflow only as a backstop
- preserves the builder-owned internal route: builder surface -> SDK bridge ->
  documentation-agent -> builder tool services

## Related Docs

- [MISSION.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/MISSION.md)
- [CLAUDE.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/CLAUDE.md)
- [documentation-agent.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/documentation-agent.md)
- [main-commit-reference.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/main-commit-reference.md)
- [architecture-boundary.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/architecture-boundary.md)
