---
title: Documentation freshness is commit-anchored, not worktree-anchored
type: decision
date: 2026-04-23
phase: implementation
entity: documentation-agent
tags: [documentation-agent, knowledge-base, freshness, git, worktree]
status: active
---

## Decision

Documentation-agent freshness reflects the committed baseline, typically main. A maintained KB doc can be marked current against documented_against_commit while still being stale relative to uncommitted local changes. When checking whether docs reflect the latest changes, compare documented_against_commit to HEAD and also check git status; if the worktree is dirty, current against main does not mean current against the worktree.

## Agent Retrieval Summary

Retrieve this memory when working on documentation-agent, implementation, or related decision changes. Use it to preserve the repo-local precedent: Documentation-agent freshness reflects the committed baseline, typically main.

## User-Facing Summary

Documentation-agent freshness reflects the committed baseline, typically main.

## Reusable Guidance

- Treat this as repo-local decision precedent for documentation-agent.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch documentation-agent, the implementation phase, or related tags: documentation-agent, knowledge-base, freshness, git, worktree.

## Retrieval Queries

- documentation freshness is commit-anchored, not worktree-anchored
- documentation freshness is commit anchored not worktree anch
- documentation-agent
- implementation
- knowledge-base
- freshness
- git
- worktree
