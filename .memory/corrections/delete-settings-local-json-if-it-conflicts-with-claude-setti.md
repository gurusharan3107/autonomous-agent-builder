---
title: Delete settings.local.json if it conflicts with .claude/settings.json
type: correction
date: 2026-04-20
phase: setup
entity: settings-management
tags: [settings, local, override, conflict]
status: active
---

## Correction

settings.local.json overrides .claude/settings.json globally. If worktree permissions differ from main, delete settings.local.json to ensure worktree config takes precedence.

## Agent Retrieval Summary

Retrieve this memory when working on settings-management, setup, or related correction changes. Use it to preserve the repo-local precedent: settings.local.json overrides .claude/settings.json globally.

## User-Facing Summary

settings.local.json overrides .claude/settings.json globally.

## Reusable Guidance

- Treat this as repo-local correction precedent for settings-management.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch settings-management, the setup phase, or related tags: settings, local, override, conflict.

## Retrieval Queries

- delete settings.local.json if it conflicts with .claude/settings.json
- delete settings local json if it conflicts with claude setti
- settings-management
- setup
- settings
- local
- override
- conflict
