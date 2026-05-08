---
title: Shipping requires integrating the task worktree
type: pattern
date: 2026-04-29
phase: integration
entity: task-worktree-shipping
tags: [worktree, integration, shipping, backlog]
status: active
---

## Pattern

A feature is not shipped just because a task worktree contains passing code. After build verification, the completed task branch must be integrated back into the generated repo root/main so the next backlog item starts from the shipped baseline. If the next task cannot create a worktree or sees an unborn/stale main, inspect whether the previous feature was only completed in its worktree and add/fix the deterministic integration step.

## Agent Retrieval Summary

Retrieve this memory when working on task-worktree-shipping, integration, or related pattern changes. Use it to preserve the repo-local precedent: A feature is not shipped just because a task worktree contains passing code.

## User-Facing Summary

A feature is not shipped just because a task worktree contains passing code.

## Reusable Guidance

- Treat this as repo-local pattern precedent for task-worktree-shipping.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch task-worktree-shipping, the integration phase, or related tags: worktree, integration, shipping, backlog.

## Retrieval Queries

- shipping requires integrating the task worktree
- task-worktree-shipping
- integration
- worktree
- shipping
- backlog
