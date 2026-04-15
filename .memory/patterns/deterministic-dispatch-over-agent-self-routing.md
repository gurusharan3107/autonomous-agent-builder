---
title: Deterministic dispatch over agent self-routing
type: pattern
date: 2026-04-14
phase: design
entity: orchestrator
tags: [dispatch, architecture, routing]
status: active
---

## Approach

Use deterministic dispatch in the orchestrator. The orchestrator owns routing based on task_status, not agents. Agents receive work, they don't choose it.

## When To Reuse

Any multi-phase workflow where the order of operations matters and you need auditability of which phase was entered and why.

## Evidence

Azure Architecture Center pattern: 'use deterministic dispatch when the agent executing the phase is identifiable from the task state.' Our orchestrator maps task_status directly to phase handler functions.
