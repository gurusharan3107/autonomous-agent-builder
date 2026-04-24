---
title: Documentation freshness is commit-anchored, not worktree-anchored
type: decision
date: 2026-04-23
phase: implementation
entity: documentation-agent
tags: [documentation-agent, knowledge-base, freshness, git, worktree]
status: active
---

Documentation-agent freshness reflects the committed baseline, typically main. A maintained KB doc can be marked current against documented_against_commit while still being stale relative to uncommitted local changes. When checking whether docs reflect the latest changes, compare documented_against_commit to HEAD and also check git status; if the worktree is dirty, current against main does not mean current against the worktree.
