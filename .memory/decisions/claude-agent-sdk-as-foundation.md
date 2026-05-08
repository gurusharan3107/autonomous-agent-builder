---
title: Claude Agent SDK as foundation
type: decision
date: 2026-04-14
phase: design
entity: orchestrator
tags: [sdk, architecture, foundation]
status: active
---

## Decision

Use Claude Agent SDK as the foundation for the autonomous builder. Replaces 6 custom components (prompt management, tool dispatch, session handling, cost tracking, permission control, streaming).

## Trace

- Inputs: Evaluated Agent SDK docs, existing custom implementation, maintenance burden
- Policy: Prefer SDK over custom when SDK covers >80% of requirements
- Exception: None â€” SDK covers all requirements
- Approval: Architecture review confirmed

## Agent Retrieval Summary

Retrieve this memory when working on orchestrator, design, or related decision changes. Use it to preserve the repo-local precedent: Decision Use Claude Agent SDK as the foundation for the autonomous builder.

## User-Facing Summary

Decision Use Claude Agent SDK as the foundation for the autonomous builder.

## Reusable Guidance

- Treat this as repo-local decision precedent for orchestrator.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch orchestrator, the design phase, or related tags: sdk, architecture, foundation.

## Retrieval Queries

- claude agent sdk as foundation
- orchestrator
- design
- sdk
- architecture
- foundation
