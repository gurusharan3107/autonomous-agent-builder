---
title: Worktree-first development is the core rule
type: decision
date: 2026-04-20
phase: implementation
entity: worktree-workflow
tags: [worktree, development, isolation]
status: active
---

All code changes MUST happen in git worktrees. Never edit in main repo. This ensures: complete isolation, no accidental conflicts, clean branch history, ability to work on multiple features in parallel.
