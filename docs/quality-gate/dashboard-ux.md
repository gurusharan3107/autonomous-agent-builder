---
title: "Dashboard UX quality gate"
surface: "dashboard-ux"
summary: "Use when changing dashboard pages or visible workflows to prove the user can see current state, next action, evidence, and runtime effects without SDK-specific reasoning."
commands:
  - "builder quality-gate dashboard-ux --json"
  - "builder start --port 9876"
  - "builder logs analyze --json"
  - "builder verify --changed --execute --json"
expectations:
  - "Agent, Board, Metrics, Observability, Knowledge, Memory, Backlog, Inbox, and Compare show coherent current project state"
  - "button clicks have deterministic frontend behavior and matching backend event evidence"
  - "runtime switching keeps historical work visible and makes only future-run behavior change"
  - "recommendations are consolidated into one user-facing panel with tabs or filters instead of duplicate panels"
  - "empty, blocked, loading, failed, and success states are explicit rather than vague unknowns"
related_docs:
  - "docs/workflows/design-language.md"
  - "docs/references/dashboard-first-validation.md"
---

# Dashboard UX quality gate

## Purpose

Use this gate when a change affects what the operator sees or clicks in the
dashboard.

## When To Load

Load this gate before changing:

- any dashboard route, tab, card, button, runtime switcher, or status panel
- metrics and observability presentation
- backlog, board, approval, memory, knowledge, or agent-page visible flows

## Pass Signals

- visible state is grounded in active product state and stable API fields
- every primary button has an inspectable backend event, state transition, or no-op reason
- runtime differences are visible as capability/evidence differences, not user burden
- text labels use actual task, memory, approval, and run names rather than vague placeholders

## Fail Signals

- users see duplicate recommendation surfaces, unknown collector states, or vague task names
- switching SDK lanes hides shipped work or historical telemetry
- UI state can only be explained by reading logs or database rows
- dashboard pages regress from product surfaces into disconnected diagnostic panels
