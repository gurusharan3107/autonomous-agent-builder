---
title: "Dashboard UX quality gate"
surface: "dashboard-ux"
summary: "Use when changing dashboard pages or visible workflows to prove the user can see current state, next action, evidence, and runtime effects without SDK-specific reasoning."
commands:
  - "builder quality-gate dashboard-ux --json"
  - "builder start --port 9876"
  - "builder logs analyze --session <id-or-prefix> --json"
  - "builder verify --changed --execute --json"
expectations:
  - "Agent, Board, Metrics, Observability, Knowledge, Memory, Backlog, Inbox, and Compare show coherent current project state"
  - "Agent page keeps prompt-submission progress visible: after submit, the operator message remains in Conversation and the Agent shows an active three-dot thinking indicator until assistant text, a question, or an error arrives"
  - "button clicks have deterministic frontend behavior and matching backend event evidence"
  - "runtime switching keeps historical work visible and makes only future-run behavior change"
  - "recommendations are consolidated into one user-facing panel with tabs or filters instead of duplicate panels"
  - "Observability recommendations are split into Builder, App, Completed, and Rejected tabs; Builder cards show product fixes, App cards are the optimization-agent queue, and Completed cards retain resolved lifecycle evidence"
  - "Observability recommendations use the available Builder CLI evidence surfaces, including metrics top drivers, budget status, telemetry health, tool events, provider limits, approvals, and recovery signals; they must not collapse to script candidates only"
  - "Observability recommendations expose rank, owner lane, next action, evidence source, and the diagnostic command without forcing the operator to read raw logs first"
  - "Observability recommendations must show whether the card has been validated from bounded Builder evidence before the operator treats it as actionable"
  - "Builder-owned recommendations leave the active queue only after deterministic latest-telemetry lifecycle evidence proves the issue is resolved"
  - "Observability action recommendations appear once in the Recommendations panel; Runtime decisions may show evidence, not duplicate recommendation cards"
  - "Board keeps one compact Sprint selector/control surface instead of duplicating sprint history cards above the lanes"
  - "Board phase progress renders as a compact timeline rail with Plan, Design, Implement, Gates, Review, Build, and Done milestones instead of a bulky phase-pill strip"
  - "Floating dashboard controls, including the Realtime Voice widget, stay fully inside the viewport after drag, expand, collapse, and window resize, while collapse returns to the user's saved control anchor"
  - "Board task details hand off run prompts, tool calls, gates, cost, tokens, runtime metadata, and diff evidence to Agent Run trace instead of duplicating the trace"
  - "empty, blocked, loading, failed, and success states are explicit rather than vague unknowns"
related_docs:
  - "docs/design-docs/design-language.md"
  - "docs/workflows/autonomous-lifecycle-validation.md"
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
- Observability recommendations are grounded in multiple CLI-derived evidence surfaces, not only deterministic script candidates
- Observability shows a compact active-tab priority queue before detailed cards so the operator knows what to fix first
- Observability cards mark recommendations as validated only when they include the bounded CLI evidence command and matching structured evidence
- Observability moves applied or telemetry-observed recommendations into Completed with lifecycle and evidence details, rather than hiding them or leaving them stale under Builder/App
- Agent page running state must not collapse to `No active transcript`; show an active Agent thinking affordance when the backend status is running before text streams
- Board moves from the phase rail into the five lanes without an extra Sprint history card strip
- Board sprint progress uses one low-noise milestone timeline: Plan, Design, Implement, Gates, Review, Build, Done
- floating controls use a temporary expanded-position clamp for viewport fit, then return to the saved collapsed anchor when collapsed
- Board active-task detection covers early-phase tasks in `planning` or `design` that have no agent run yet (empty `latest_run_status`), so those tasks show as active rather than idle
- Board owns pipeline status and task context; Agent Run trace owns per-run evidence, with visible links between them
- text labels use actual task, memory, approval, and run names rather than vague placeholders

## Fail Signals

- users see duplicate recommendation surfaces, unknown collector states, or vague task names
- Observability has material metrics, telemetry, approval, provider-limit, or recovery evidence but still shows only generic script-candidate cards
- Observability cards do not identify the evidence source or diagnostic command that produced the recommendation
- Observability presents recommendation cards as actionable without first showing a validation status or bounded evidence path
- fixed Builder-owned recommendations remain in the active Builder queue after newer telemetry proves the same issue resolved
- Agent prompt submit leaves the operator staring at `No active transcript`, an empty thread, or only side-panel status while the backend run is active
- Board repeats the same Sprint selection/history as both a dropdown/control and a row of large cards above the lanes
- Board drawers duplicate Agent Run trace timelines, tool calls, token/cost breakdowns, or diff evidence
- switching SDK lanes hides shipped work or historical telemetry
- UI state can only be explained by reading logs or database rows
- dashboard pages regress from product surfaces into disconnected diagnostic panels
