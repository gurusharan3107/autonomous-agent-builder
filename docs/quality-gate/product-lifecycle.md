---
title: "Product lifecycle quality gate"
surface: "product-lifecycle"
summary: "Use when changing backlog, board, sprint, approval, execution, recovery, or continuation behavior to prove the visible SDLC remains deterministic."
commands:
  - "builder quality-gate product-lifecycle --json"
  - "builder board show --json"
  - "builder logs analyze --session <id-or-prefix> --json"
  - "builder verify --changed --execute --json"
expectations:
  - "builder init, onboarding, clarification, backlog, approval, execution, gates, PR/review, and continuation remain one user-visible journey"
  - "future runtime switches affect only future runs while historical task and telemetry attribution remains visible"
  - "tasks move through explicit lifecycle states rather than direct queueing or hidden status jumps"
  - "blocked states preserve task, workspace, approval, provider-limit, and restart evidence"
  - "post-mutation checks prove board/backlog/approval/runtime changes can be retrieved through product surfaces"
related_docs:
  - "docs/goal/NORTH-STAR.md"
  - "docs/workflows/autonomous-lifecycle-validation.md"
  - "docs/references/phase-model.md"
  - "docs/quality-gate/verification.md"
---

# Product lifecycle quality gate

## Purpose

Use this gate when a change can affect the user's ability to move from idea to
shipped software through the builder-owned SDLC.

Use [GOAL.md](../GOAL.md) as the acceptance contract for cross-runtime product
validation.

## When To Load

Load this gate before changing:

- onboarding or runtime selection
- backlog item creation, sprint planning, approvals, or board task movement
- dispatch, recovery, blocked-state handling, or continuation behavior
- sprint artifacts that allow tasks to skip repeated phase approvals

## Pass Signals

- every mutation has a canonical product owner and a bounded JSON inspection path
- dashboard-visible state agrees with CLI/read API state
- runtime changes are future-runs-only and do not hide historical work
- blocked states include a restart action instead of asking the user to repair state manually

## Fail Signals

- board tasks appear before backlog approval or disappear after runtime switching
- lifecycle state changes are scattered across UI assumptions, agent prose, and route logic
- provider limits, missing context, or runtime failures lose the resumable task identity
- the user has to know which SDK lane shipped prior work to see it
