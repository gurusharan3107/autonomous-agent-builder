---
title: "Architecture invariants quality gate"
surface: "architecture-invariants"
summary: "Use for domain, layering, adapter, orchestrator, runtime, and event-model changes that need stricter checks than the broad architecture-boundary gate."
commands:
  - "builder quality-gate architecture-invariants --json"
  - "builder quality-gate architecture-boundary --json"
  - "builder map --json"
  - "builder verify --changed --execute --json"
expectations:
  - "core concepts remain stable: project, feature, task, run, gate, approval, session, workspace, knowledge, memory"
  - "UI, CLI, API routes, services, orchestrator, persistence, runtime adapters, and SDK tools remain separated by owner responsibility"
  - "CLI, dashboard, SDK tools, and internal agents adapt over shared services instead of duplicating lifecycle logic"
  - "events and streams are projections of canonical state, not a second truth source"
  - "new agents, gates, workflows, models, and product surfaces can be added without duplicating phase movement or retry logic"
related_docs:
  - "docs/quality-gate/architecture-boundary.md"
  - "docs/quality-gate/modular-runtime.md"
  - "docs/references/phase-model.md"
---

# Architecture invariants quality gate

## Purpose

Use this gate for changes that could weaken the builder's domain model,
layering, adapter design, or deterministic orchestration.

## When To Load

Load this gate before changing:

- orchestrator state transitions, retry policy, blocked-state handling, or phase routing
- runtime adapters, SDK tools, CLI adapters, dashboard routes, or service boundaries
- event streaming, logs, metrics, observability, or product telemetry projections
- domain model names or ownership of project/task/run/gate/approval/session/workspace state

## Pass Signals

- product state remains owned by services/persistence and surfaced through adapters
- runtime lanes execute work but do not redefine backlog, board, approval, memory, knowledge, or metrics semantics
- command/query split stays explicit and machine-readable
- failures are isolated with preserved state and a clear restart path

## Fail Signals

- route handlers, UI code, CLI code, runtime adapters, and agent prompts each invent state transitions
- SDK-specific behavior leaks into product semantics
- event streams become required as truth rather than evidence/projection
- new abstractions duplicate existing owners instead of tightening the boundary
