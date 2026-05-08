---
title: Builder owns provider-limit resume and model policy
type: decision
date: 2026-04-29
phase: implementation
entity: orchestrator
tags: [orchestration, provider-limit, model-policy]
status: active
---

## Decision

Provider-limit stops should become structured capability blocks with reset metadata and phase-preserving resume, then be resumed by builder orchestration from product events instead of manual CLI or database repair. Model, effort, subagent, and context choices belong in src/autonomous_agent_builder/agents/execution_policy.py so the Agent page user does not choose Haiku/Sonnet/Opus or thinking level manually.

## Agent Retrieval Summary

Retrieve this memory when working on orchestrator, implementation, or related decision changes. Use it to preserve the repo-local precedent: Provider-limit stops should become structured capability blocks with reset metadata and phase-preserving resume, then be resumed by builder orchestration from product events instead of manual CLI or database repair.

## User-Facing Summary

Provider-limit stops should become structured capability blocks with reset metadata and phase-preserving resume, then be resumed by builder orchestration from product events instead of manual CLI or database repair.

## Reusable Guidance

- Treat this as repo-local decision precedent for orchestrator.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch orchestrator, the implementation phase, or related tags: orchestration, provider-limit, model-policy.

## Retrieval Queries

- builder owns provider-limit resume and model policy
- builder owns provider limit resume and model policy
- orchestrator
- implementation
- orchestration
- provider-limit
- model-policy
