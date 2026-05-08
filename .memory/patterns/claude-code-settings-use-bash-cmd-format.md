---
title: Claude Code settings use Bash(cmd:*) format
type: pattern
date: 2026-04-20
phase: setup
entity: claude-code-settings
tags: [settings, permissions, configuration]
status: active
---

## Pattern

Use 'Bash(git:*)', 'Bash(npm:*)' format in permissions, not 'bash'. This restricts commands to specific CLI invocations for safety.

## Agent Retrieval Summary

Retrieve this memory when working on claude-code-settings, setup, or related pattern changes. Use it to preserve the repo-local precedent: Use 'Bash(git:*)', 'Bash(npm:*)' format in permissions, not 'bash'.

## User-Facing Summary

Use 'Bash(git:*)', 'Bash(npm:*)' format in permissions, not 'bash'.

## Reusable Guidance

- Treat this as repo-local pattern precedent for claude-code-settings.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch claude-code-settings, the setup phase, or related tags: settings, permissions, configuration.

## Retrieval Queries

- claude code settings use bash(cmd:*) format
- claude code settings use bash cmd format
- claude-code-settings
- setup
- settings
- permissions
- configuration
