---
title: Create task worktree at design-to-implementation handoff
type: decision
date: 2026-04-24
phase: implementation
entity: workspace-lifecycle
tags: [worktree, workspace, orchestrator, claude-agent-sdk]
status: active
---

## Decision

For git-backed tasks, create and persist the task workspace at the design-to-implementation handoff, or the first equivalent repo-mutating phase. Planning and design may stay read-only without a task worktree. Workspace provisioning is orchestrator-owned; implementation, verification, PR creation, and build verification reuse the same persisted workspace cwd and branch.

## Agent Retrieval Summary

Retrieve this memory when working on workspace-lifecycle, implementation, or related decision changes. Use it to preserve the repo-local precedent: For git-backed tasks, create and persist the task workspace at the design-to-implementation handoff, or the first equivalent repo-mutating phase.

## User-Facing Summary

For git-backed tasks, create and persist the task workspace at the design-to-implementation handoff, or the first equivalent repo-mutating phase.

## Reusable Guidance

- Treat this as repo-local decision precedent for workspace-lifecycle.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch workspace-lifecycle, the implementation phase, or related tags: worktree, workspace, orchestrator, claude-agent-sdk.

## Retrieval Queries

- create task worktree at design-to-implementation handoff
- create task worktree at design to implementation handoff
- workspace-lifecycle
- implementation
- worktree
- workspace
- orchestrator
- claude-agent-sdk
