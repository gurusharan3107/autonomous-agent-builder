---
title: "Verification lane contract"
surface: "verification"
summary: "Verification combines gate results, metrics, and task state after an agent run."
commands:
  - "builder quality-gate quality-gates"
  - "builder task show <task-id> --full"
  - "builder metrics show"
expectations:
  - "verification starts with bounded summaries"
  - "metrics remain queryable independently from gate details"
---

# Verification lane contract

## Purpose

Use this gate when changing the verification lane that combines gate state,
metrics, and task inspection after an agent run.

## When To Load

Load this gate before:

- changing verification guidance in `builder context verification`
- changing metrics/task verification sequencing
- changing how verification expands from summary to detail

## Pass Signals

- verification starts bounded and deepens only when needed
- metrics remain independently queryable from task gate details

## Fail Signals

- verification requires reading large task payloads before basic status is clear
- metrics are coupled too tightly to gate-detail retrieval
