---
title: Codex global rules live in ~/.codex/AGENTS.md, not ~/.claude/CLAUDE.md
type: correction
date: 2026-05-07
phase: implementation
entity: agents-md-inheritance
tags: [agents-md, inheritance, codex, global]
status: active
---

## Correction

For Codex working on the autonomous-agent-builder repo, the global
agent-facing rules live in `~/.codex/AGENTS.md`, not `~/.claude/CLAUDE.md`.
Repo-local `CLAUDE.md` is the autonomous-builder runtime contract for the
Claude Agent SDK lane; it is not an agent-facing instruction surface for
Codex.

## Agent Retrieval Summary

When starting a session that touches this repo, load `~/.codex/AGENTS.md`
for global Codex rules and the repo-local `AGENTS.md` for repo triggers.
Read repo `CLAUDE.md` only when you are debugging or evolving the Claude
Agent SDK runtime contract that the builder applies to a target app.

The pre-fix repo `AGENTS.md` first line pointed at `~/.claude/CLAUDE.md`,
which led to mis-loading runtime guidance instead of agent-working rules.
The fix changed that line to point at `~/.codex/AGENTS.md`.

## User-Facing Summary

The repo's `AGENTS.md` first line used to point at `~/.claude/CLAUDE.md`.
That is the wrong global for an agent working on this builder. The right
global is `~/.codex/AGENTS.md`. Repo `CLAUDE.md` is the autonomous-builder
runtime contract for the Claude Agent SDK lane, not an agent-working
instruction surface.

## Reusable Guidance

- Codex global rules: `~/.codex/AGENTS.md`
- Repo Codex rules: `<repo>/AGENTS.md`
- Builder runtime contract for Claude Agent SDK lane: `<repo>/CLAUDE.md`
- Target-app runtime guidance written by `builder init`: `<app>/CLAUDE.md`
  or `<app>/AGENTS.md` depending on `RUNTIME_SDK`

## When To Apply

Apply this when:

- a fresh session starts on this repo
- diagnosing why agent-working rules feel off or runtime-coloured
- editing the repo's `AGENTS.md` first-line inheritance pointer
- explaining the four CLAUDE.md / AGENTS.md surfaces to a future agent

## Retrieval Queries

- agents-md vs claude-md
- ~/.codex/AGENTS.md global rules
- repo AGENTS.md inheritance pointer
- builder runtime contract surface ownership
