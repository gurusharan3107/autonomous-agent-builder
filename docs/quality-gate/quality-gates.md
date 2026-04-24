---
title: "Quality gate contract"
surface: "quality-gates"
summary: "Inspect task-scoped gate results through task detail views and keep pass/fail evidence machine-readable."
commands:
  - "builder task status <task-id>"
  - "builder task show <task-id> --full"
expectations:
  - "default verification output stays bounded until task detail expansion is requested"
  - "--json is the stable machine contract"
  - "use task-scoped gate retrieval through builder task surfaces instead of scraping logs"
  - "follow-up action stays obvious when a gate fails"
---

# Quality gate contract

## Purpose

Use this gate when changing how task-scoped gate results are surfaced through
builder task commands.

## When To Load

Load this gate before:

- changing task-status verification output
- changing gate result rendering in `builder task show --full`
- changing JSON fields used to inspect pass/fail evidence

## Pass Signals

- verification remains task-scoped and bounded by default
- JSON stays the stable machine contract
- follow-up action is obvious when verification fails

## Fail Signals

- callers have to scrape logs to understand gate state
- gate details are no longer reachable through task surfaces

## Related Docs

- [verification.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/verification.md)
