---
title: "Approval verification contract"
surface: "approval"
summary: "Use task and approval surfaces together when human approval blocks phase advancement."
commands:
  - "builder task show <task-id> --full"
  - "builder approval list --task <task-id>"
expectations:
  - "approval state remains visible without opening the dashboard"
  - "gate failures and pending approvals stay distinguishable"
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

## Pass Signals

- approval state is visible from builder CLI surfaces
- pending approvals remain distinct from gate failures

## Fail Signals

- users need the dashboard to know whether approval is blocking execution
- approval and gate failure states blur together
