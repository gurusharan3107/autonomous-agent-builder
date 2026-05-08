---
title: Sprint 1 dispatch exposed critical scope-handoff and gate-routing bugs
type: correction
date: 2026-05-07
phase: implementation
entity: sprint-dispatch
tags: [scope-handoff, code-gen, runtime-guidance, quality-gates, pr-creation, critical]
status: active
---

## Correction

First end-to-end sprint dispatch through Claude Agent SDK exposed three critical bugs in the orchestration → execution context handoff. Sprint 1, feature-01, task 501ad9e0 (todo-app, 2026-05-07).

## Agent Retrieval Summary

Retrieve when: changing the dispatch path, code-gen prompt, task workspace seeding, runtime_guidance template, quality-gate routing, or pr-creation phase. These three bugs all stem from the **chat agent's agreed scope not flowing into the per-task implementation context**, and the orchestrator continuing past errors instead of blocking. Operating rule: every agreed scope decision the chat agent extracts MUST be persisted to a surface the dispatched code-gen agent reads (project context block in the target's CLAUDE.md, or a per-task scope packet attached to the task row, or both).

## User-Facing Summary

Asked builder to build a plain-HTML/CSS/JS todo app with localStorage. The chat agent agreed to that scope and generated a 5-feature backlog. But when the implementation agent picked up feature-01, it built a **Flask + SQLite + Jinja templates** app instead — a completely different stack. Quality gates errored without halting, and the task only blocked at PR creation when a git check failed.

## Reusable Guidance

### Bug 1 — Scope-context-flow (critical)

**What happened:** init-project-chat asked 4 questions and got commitments for: web app, plain HTML/CSS/JS no framework, localStorage, title-only todos. Generated `feature-list.json` with feature-01.acceptance_criteria including *"Opening index.html in a browser renders the app without a server"*. Sprint 1 was approved, three tasks created, the first dispatched to `code-gen`. Code-gen's task workspace had:

- `CLAUDE.md` (the runtime baseline `runtime_guidance.py` wrote at init time, with `Language: python` auto-detected and Framework / App type / Persistence / Package manager all `unknown`).
- A generic task title: "Implement core app behavior for Project scaffold".
- MCP tools (`task_show`, `kb_search`, `memory_search`).

The `code-gen` agent did **not** receive: the chat thread, the agreed scope decisions, or the feature-01 acceptance criteria in any prominent way. It read CLAUDE.md, saw `Language: python` (stale auto-detection from init), and built Flask + SQLite + Jinja.

**Even worse:** as part of its run, code-gen edited CLAUDE.md to "lock in" Framework: flask, App type: web (todo), Persistence: sqlite (todos.db). Subsequent tasks would inherit this lie.

**Where to fix:**
- `init-project-chat` agent (or the sprint-planner) must update target `CLAUDE.md` Project Context block with agreed answers (`Language`, `Framework`, `App type`, `Persistence`, `Package manager`) BEFORE any task is dispatched. The current `runtime_guidance.py` template has these slots; they're just not being repopulated.
- `code-gen` prompt should also pull `acceptance_criteria` from the active feature(s) in the sprint plan and include them as part of the task brief — not rely on CLAUDE.md alone.
- Code-gen edits to the project-context block of CLAUDE.md should be guarded — that block is owned by the chat/planner, not by code-gen. Or, at minimum, audited against the scope decisions before being committed.

### Bug 2 — Quality gates error path swallows errors

After code-gen, dispatch_phase advanced to `_phase_quality_gates`. Both `code_quality` and `testing` gates returned `status=error error_code=FileNotFoundError findings_count=0` (probably looking for lint/test configs in the workspace that don't exist for this freshly-generated app). The orchestrator then dispatched `_phase_pr_creation` anyway — `status=error` was treated identically to "passed".

**Where to fix:** in the dispatch routing, `gate_result status=error` should be a hard halt or block (with a recoverable hint), not a fall-through. Distinguish:
- `status=passed` → advance
- `status=failed_findings` → block with findings, route to fix
- `status=error` → block with error, route to gate-config fix or workspace-bootstrap fix

Right now `error` and `passed` have the same effect on dispatch_followup_selected.

### Bug 3 — Owner-surface-protection requires git, workspace isn't a git repo

`pr_creation` ran "Owner surface protection" which tried to stage runtime guidance via git, hit `fatal: not a git repository (or any of the parent directories): .git`. Task blocked with cost $0.2731, 21 turns, 1m47s.

Per `CLAUDE.md` (builder repo): *"For local generated-app Codex workspaces without a real Git PR target, the orchestrator must use deterministic evidence surfaces before model agents: `change_evidence` for PR/evidence collection and `build_verify` for lint/build/test/browser proof."*

That rule is correct but isn't being applied to **Claude SDK workspaces** — only mentions Codex. The same rule should apply: when no git target exists, route to `change_evidence` (deterministic) before any pr-creator/build-verifier model run, and skip the git-staging guard. Either:
- Detect git-target presence at dispatch time and short-circuit pr_creation to change_evidence.
- Make Owner surface protection no-op gracefully when `.git` is absent.
- Treat the gate's "error" exit (not "failed") as a routing signal to the change_evidence path.

### Confirmed working through this run

- `init-project-chat` → 4 focused questions → feature-list.json (good).
- Sprint scope approval card with full acceptance criteria visible (good).
- Sprint 1 created with 3 tasks (Implement / Cover persistence / Verify) auto-spread per-feature (good).
- Per-task workspace isolation at `/tmp/aab-workspaces/<task_id>/` (good).
- Per-task model routing: `code-gen` ran on `claude-sonnet-4-6` with `effort=medium` (matches `_AGENT_POLICY`).
- Sidebar Cost/Tokens/Turns DOES update — earlier observation that it was stuck at $0 was a mid-run snapshot artefact. It binds to the run after `agent_phase_complete`. Still not live during the run, which is a UX gap but not "broken."
- OTEL telemetry continued to flow correctly through the implementation phase.

## When To Apply

Apply when:
- Reviewing changes to `init-project-chat`, `services/runtime_guidance.py`, `agents/definitions.py` (code-gen prompt), `orchestrator/dispatch.py` (gate routing).
- Triaging "agent built the wrong stack" reports — first check `runtime_guidance.py` Language auto-detection and whether the chat agent updates the project-context block.
- Adding new quality gates — confirm they distinguish error vs failed-findings vs passed in dispatch routing.
- Handling no-git workspaces — confirm pr_creation falls back to change_evidence.

## Retrieval Queries

- scope context not flowing to task workspace
- code-gen built wrong stack flask vs html
- quality gates error swallowed
- owner surface protection git missing
- runtime_guidance language auto-detect override
- per-task feature acceptance criteria flow
- sprint dispatch context handoff
- claude-md project context block ownership
