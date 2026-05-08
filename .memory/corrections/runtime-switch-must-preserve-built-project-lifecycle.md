---
title: Runtime switch must preserve built project lifecycle
type: correction
date: 2026-05-03
phase: runtime
entity: runtime-switch
tags: [runtime, onboarding, codex-sdk, claude-agent-sdk, readiness]
status: active
---

## Correction

## Constraint
Switching between Claude Agent SDK and Codex SDK is an execution-runtime change, not a product-lifecycle reset. Builder product state remains authoritative for onboarding readiness, backlog, sprint phase, board tasks, knowledge, memory, approvals, and shipped evidence.

## What Went Wrong
A mid-project SDK switch could route the dashboard back to onboarding or show the init-project bootstrap prompt for an already built project. That conflates runtime readiness with product initialization and risks duplicate requirements gathering, feature-list regeneration, and lost user trust.

## What To Do Instead
On runtime switch, persist runtime config, repair the selected telemetry lane, run deterministic readiness assessment, and resume the current product surface. Only show onboarding or init-project chat when the workspace is genuinely new/empty and has no builder work state or generated app surface. Runtime-specific differences should appear in diagnostics, model/effort/cost, limits, and observability, not in lifecycle continuity.

## Agent Retrieval Summary

Retrieve this memory when working on runtime-switch, runtime, or related correction changes. Use it to preserve the repo-local precedent: Constraint Switching between Claude Agent SDK and Codex SDK is an execution-runtime change, not a product-lifecycle reset.

## User-Facing Summary

Constraint Switching between Claude Agent SDK and Codex SDK is an execution-runtime change, not a product-lifecycle reset.

## Reusable Guidance

- Treat this as repo-local correction precedent for runtime-switch.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch runtime-switch, the runtime phase, or related tags: runtime, onboarding, codex-sdk, claude-agent-sdk, readiness.

## Retrieval Queries

- runtime switch must preserve built project lifecycle
- runtime-switch
- runtime
- onboarding
- codex-sdk
- claude-agent-sdk
- readiness
