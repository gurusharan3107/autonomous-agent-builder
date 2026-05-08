---
title: Treat empty SDK and provider-limit output as blockers
type: pattern
date: 2026-04-29
phase: implementation
entity: sdk-empty-and-limit-results
tags: [sdk, provider-limit, no-op, capability-limit]
status: active
---

## Pattern

Zero-token or zero-cost SDK runs and provider-limit messages must not advance planning, design, implementation, or quality gates as successful agent output. Detect empty results and provider-limit text, avoid resuming from empty sessions, and route to capability_limit or a model fallback instead. Add a no-op implementation delta gate so unchanged worktrees fail back to implementation rather than shipping the previous baseline.

## Agent Retrieval Summary

Retrieve this memory when working on sdk-empty-and-limit-results, implementation, or related pattern changes. Use it to preserve the repo-local precedent: Zero-token or zero-cost SDK runs and provider-limit messages must not advance planning, design, implementation, or quality gates as successful agent output.

## User-Facing Summary

Zero-token or zero-cost SDK runs and provider-limit messages must not advance planning, design, implementation, or quality gates as successful agent output.

## Reusable Guidance

- Treat this as repo-local pattern precedent for sdk-empty-and-limit-results.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch sdk-empty-and-limit-results, the implementation phase, or related tags: sdk, provider-limit, no-op, capability-limit.

## Retrieval Queries

- treat empty sdk and provider-limit output as blockers
- treat empty sdk and provider limit output as blockers
- sdk-empty-and-limit-results
- implementation
- sdk
- provider-limit
- no-op
- capability-limit
