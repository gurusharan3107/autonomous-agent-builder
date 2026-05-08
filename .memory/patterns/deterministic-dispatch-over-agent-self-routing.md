---
title: Deterministic dispatch over agent self-routing
type: pattern
date: 2026-04-14
phase: design
entity: orchestrator
tags: [dispatch, architecture, routing]
status: active
---

## Pattern

## Approach

Use deterministic dispatch in the orchestrator. The orchestrator owns routing based on task_status, not agents. Agents receive work, they don't choose it.

## When To Reuse

Any multi-phase workflow where the order of operations matters and you need auditability of which phase was entered and why.

## Evidence

Azure Architecture Center pattern: 'use deterministic dispatch when the agent executing the phase is identifiable from the task state.' Our orchestrator maps task_status directly to phase handler functions.

## Agent Retrieval Summary

Retrieve this memory when working on orchestrator, design, or related pattern changes. Use it to preserve the repo-local precedent: Approach Use deterministic dispatch in the orchestrator.

## User-Facing Summary

Approach Use deterministic dispatch in the orchestrator.

## Reusable Guidance

- Treat this as repo-local pattern precedent for orchestrator.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch orchestrator, the design phase, or related tags: dispatch, architecture, routing.

## Retrieval Queries

- deterministic dispatch over agent self-routing
- deterministic dispatch over agent self routing
- orchestrator
- design
- dispatch
- architecture
- routing
