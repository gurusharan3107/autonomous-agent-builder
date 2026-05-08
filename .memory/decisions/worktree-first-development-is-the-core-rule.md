---
title: Worktree-first development is the core rule
type: decision
date: 2026-04-20
phase: implementation
entity: worktree-workflow
tags: [worktree, development, isolation]
status: active
---

## Decision

All code changes MUST happen in git worktrees. Never edit in main repo. This ensures: complete isolation, no accidental conflicts, clean branch history, ability to work on multiple features in parallel.

## Agent Retrieval Summary

Retrieve this memory when working on worktree-workflow, implementation, or related decision changes. Use it to preserve the repo-local precedent: All code changes MUST happen in git worktrees.

## User-Facing Summary

All code changes MUST happen in git worktrees.

## Reusable Guidance

- Treat this as repo-local decision precedent for worktree-workflow.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch worktree-workflow, the implementation phase, or related tags: worktree, development, isolation.

## Retrieval Queries

- worktree-first development is the core rule
- worktree first development is the core rule
- worktree-workflow
- implementation
- worktree
- development
- isolation
