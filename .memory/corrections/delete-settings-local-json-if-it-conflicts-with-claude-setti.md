---
title: Delete settings.local.json if it conflicts with .claude/settings.json
type: correction
date: 2026-04-20
phase: setup
entity: settings-management
tags: [settings, local, override, conflict]
status: active
---

settings.local.json overrides .claude/settings.json globally. If worktree permissions differ from main, delete settings.local.json to ensure worktree config takes precedence.
