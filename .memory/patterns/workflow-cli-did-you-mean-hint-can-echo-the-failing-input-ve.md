---
title: Workflow CLI 'Did you mean' hint can echo the failing input — verify with workflow doctor + ls
type: pattern
date: 2026-05-08
phase: implementation
entity: workflow-cli
tags: [workflow-cli, tool-quirk, debugging, fix-discipline]
status: active
---

## Pattern

When `workflow resolve <name>`, `workflow summary <name>`, or `workflow read <name>` returns "No doc matching '<name>'", the CLI's "Did you mean: …" hint can list the SAME name that just failed (it appears to echo the input rather than only suggesting close matches that exist on disk). Treat the hint as advisory, not authoritative — confirm with `workflow doctor` (shows the docs root and count) and `workflow list` / `ls $HOME/.claude/docs/workflows /home/gurusharangupta/code/autonomous-agent-builder/docs/workflows` before assuming the doc exists.

## Agent Retrieval Summary

Retrieve before deeply trusting a `workflow` CLI hint. If the resolver fails and the hint suggests the same name, the doc almost certainly does not exist — verify with `workflow doctor` (docs root) and direct `ls` on the workflows/references directories before concluding.

## User-Facing Summary

The workflow CLI's "Did you mean" hint sometimes echoes the input. When in doubt, list the actual docs directory.

## Reusable Guidance

- `workflow doctor` reveals the active docs root (default `~/.claude/docs`; override with `--docs-dir`). Both stores must be checked: global at `~/.claude/docs/`, repo-local at `<repo>/docs/`.
- `workflow list` (with the right `--docs-dir`) shows what is actually indexed and groups by type (PRINCIPLES / WORKFLOWS / REFERENCES / QUALITY-GATES).
- Direct `ls $HOME/.claude/docs/workflows` and `ls <repo>/docs/workflows` are the ground truth.
- A stale AGENTS.md or CLAUDE.md trigger that points to a non-existent doc may keep being prescribed because the hint feels affirmative — periodically grep AGENTS.md for `workflow .* summary <name>` and verify each name resolves.
- Concrete instance observed in this repo: AGENTS.md prescribed `workflow summary workflow-doc-creation`. The CLI hint suggested the same name. After exhaustive search across `~/.claude/docs`, the repo `docs/`, and the entire home tree, no such file existed. The row was stale and was removed.

## When To Apply

Apply whenever a `workflow` CLI resolution fails. Do not iterate variations of the name; pause, run `workflow doctor` + `workflow list`, and confirm the file with `ls`. If it does not exist, the AGENTS.md/CLAUDE.md trigger that prescribed it is stale.

## Retrieval Queries

- workflow cli no doc matching
- workflow resolve hint misleading
- workflow doctor docs root
- stale agents.md workflow trigger
- did you mean echoes input
