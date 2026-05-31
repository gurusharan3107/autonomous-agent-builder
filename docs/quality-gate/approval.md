---
title: "Approval verification contract"
surface: "approval"
summary: "Use task and approval surfaces together when human approval blocks phase advancement."
commands:
  - "builder backlog task show <task-id> --full --json"
  - "builder backlog approval list --task <task-id> --json"
  - "builder backlog approval show <gate-id> --json"
expectations:
  - "approval state remains visible without opening the dashboard"
  - "Agent-page approval and question controls render readable operator labels"
  - "gate failures and pending approvals stay distinguishable"
  - "approval resolution can trigger the next ready task without duplicate dispatch"
related_docs:
  - "docs/quality-gate/product-lifecycle.md"
  - "docs/workflows/autonomous-lifecycle-validation.md"
---

# Approval verification contract

## Purpose

Use this gate when changing how approval state is surfaced alongside gate and
task status.

## When To Load

Load this gate before:

- changing approval list output
- changing task detail output that includes approval state
- changing how blocked approvals are distinguished from failed gates
- changing approval-page submission or follow-up dispatch behavior

## Pass Signals

- approval state is visible from builder CLI surfaces
- Agent-page approval and question controls render readable operator labels and
  never show raw option objects, SDK event names, or lifecycle-only wording
- pending approvals remain distinct from gate failures
- after an approval is submitted, the product selects and dispatches the next
  ready task when one exists
- approval auto-dispatch and manual board dispatch remain idempotent for the
  same task
- malformed approval submissions fail with a clear client error and required
  field detail, not a server 500 or ambiguous blocked card

## Fail Signals

- users need the dashboard to know whether approval is blocking execution
- approval and gate failure states blur together
- approval requires a second operator click to continue an already-approved
  sprint when a ready task is available
- approval or delivery-choice controls display raw payloads, `[object Object]`,
  or internal labels where the operator needs a plain action such as `Start now`
  or `Hold`
- approval and manual dispatch can start duplicate agents for the same task
- approval submission fails with a generic 500 when a required field such as
  approver identity is missing
