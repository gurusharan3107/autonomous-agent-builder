---
title: Provider limit text should block active work immediately
type: pattern
date: 2026-04-29
phase: implementation
entity: provider-quota-detection
tags: [provider-limit, quota, blocked-state, capability-limit, context-efficiency]
status: active
---

## Pattern

When an agent or SDK response contains provider quota text such as 'You've hit your limit · resets ...', classify it immediately as a provider-capacity blocker, not as normal assistant output or an implementation/design result. Do not spend additional context trying to infer whether the model hit a limit; route the currently active item to blocked/capability_limit with the reset time preserved, and stop phase advancement until capacity returns or an alternate provider/model is explicitly available. This prevents empty or quota-message runs from becoming fake design_context, fake implementation success, or stale in-progress work.

## Agent Retrieval Summary

Retrieve this memory when working on provider-quota-detection, implementation, or related pattern changes. Use it to preserve the repo-local precedent: When an agent or SDK response contains provider quota text such as 'You've hit your limit · resets ...', classify it immediately as a provider-capacity blocker, not as normal assistant output or an implementation/design result.

## User-Facing Summary

When an agent or SDK response contains provider quota text such as 'You've hit your limit · resets ...', classify it immediately as a provider-capacity blocker, not as normal assistant output or an implementation/design result.

## Reusable Guidance

- Treat this as repo-local pattern precedent for provider-quota-detection.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch provider-quota-detection, the implementation phase, or related tags: provider-limit, quota, blocked-state, capability-limit, context-efficiency.

## Retrieval Queries

- provider limit text should block active work immediately
- provider-quota-detection
- implementation
- provider-limit
- quota
- blocked-state
- capability-limit
- context-efficiency
