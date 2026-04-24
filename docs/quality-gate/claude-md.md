---
title: "CLAUDE.md quality gate"
surface: "claude-md"
summary: "Use when changing repo-local CLAUDE.md guidance to verify that runtime instructions stay concise, repo-scoped, and aligned with the builder owner surfaces."
commands:
  - "workflow --docs-dir=docs summary quality-gate/claude-md"
  - "workflow --docs-dir=docs read quality-gate/claude-md"
  - "builder quality-gate architecture-boundary --json"
  - "builder quality-gate claude-agent-sdk --json"
  - "builder map --json"
expectations:
  - "CLAUDE.md stays a runtime contract for this repo instead of becoming a second workflow doc or architecture essay"
  - "instructions stay repo-scoped and do not assign builder responsibilities to global ~/.codex surfaces"
  - "CLAUDE.md keeps builder, orchestrator, and runtime responsibilities aligned with the adjacent owner docs instead of redefining them"
  - "retrieval guidance points to canonical builder or workflow surfaces rather than duplicating long procedures inline"
  - "the file remains concise enough to guide runtime behavior without burying the active contract in broad reference prose"
  - "repo-local knowledge and memory continue to be maintained through builder publish surfaces rather than direct file or database mutation guidance"
  - "new guidance uses stable public commands and owned docs instead of compatibility aliases or hidden lanes"
related_docs:
  - "CLAUDE.md"
  - "docs/quality-gate/architecture-boundary.md"
  - "docs/claude-agent-sdk-integration.md"
---

# CLAUDE.md Quality Gate

## Purpose

Use this gate when changing the repo-local
[CLAUDE.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/CLAUDE.md)
contract.

This gate checks whether `CLAUDE.md` still does the narrow job it should do in
this repo: tell the runtime how the builder behaves, where to retrieve
repo-local truth, and which product boundaries must remain intact.

## When To Load

Load this gate before:

- editing [CLAUDE.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/CLAUDE.md)
- adding new runtime instructions or retrieval defaults to `CLAUDE.md`
- moving guidance between `CLAUDE.md`, `AGENTS.md`, and `docs/workflows/`
- changing how `CLAUDE.md` describes builder vs workflow vs SDK responsibilities

## Review Questions

1. Does the change keep `CLAUDE.md` as runtime guidance instead of turning it into a broad reference doc?
2. Is the instruction repo-scoped, or does it incorrectly assign repo behavior to `~/.codex` or other global surfaces?
3. Does the new guidance point to the canonical retrieval or write surface instead of duplicating a procedure inline?
4. Is the ownership split still aligned with [architecture-boundary.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/architecture-boundary.md) and [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)?
5. Will a future agent learn the right command lane quickly, or does the change add another parallel lane or alias?
6. Is the file still concise enough that the active contract is easy to see during runtime?

## Pass Signals

- `CLAUDE.md` stays focused on builder runtime truth, phase/state semantics, and repo-specific invariants.
- Retrieval and write guidance point to canonical `builder`, `workflow`, and repo-doc surfaces.
- The file stays compact and operational rather than explanatory by default.
- Adjacent owner docs and code imply the same boundaries.

## Fail Signals

- `CLAUDE.md` starts duplicating long workflow steps that belong in `docs/workflows/`.
- The file starts acting like a second architecture reference or product PRD.
- New guidance introduces hidden aliases, compatibility commands, or parallel owner surfaces.
- `CLAUDE.md`, adjacent quality-gate docs, and code now imply different responsibility boundaries.
- The runtime would now be encouraged to mutate knowledge or memory outside builder-owned publish surfaces.

## Recommended Verification

Read:

- [CLAUDE.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/CLAUDE.md)
- [architecture-boundary.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/architecture-boundary.md)
- [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)

Check commands when relevant:

- `builder quality-gate architecture-boundary --json`
- `builder quality-gate claude-agent-sdk --json`
- `builder map --json`

## Anti-Patterns

- turning `CLAUDE.md` into a long-form tutorial
- duplicating workflow steps that already live in `docs/workflows/`
- teaching a hidden compatibility command instead of the public builder surface
- mixing repo-local runtime truth with global Codex control-plane guidance

## Related Docs

- [CLAUDE.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/CLAUDE.md)
- [architecture-boundary.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/architecture-boundary.md)
- [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
