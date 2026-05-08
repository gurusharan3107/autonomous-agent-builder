---
title: Surface ownership - what goes where (AGENTS.md vs steering vs workflow vs scripts)
type: pattern
date: 2026-04-17
phase: implementation
entity: agents
tags: [ownership, placement, surfaces, organization]
status: active
related: [command-execution-friction-prevention-via-steering-files]
---

## Pattern

## Approach

Clear ownership model for where to place different types of content: AGENTS.md, steering files, workflow docs, scripts, CLAUDE.md, memory.

**Decision tree:**
1. ≤3 lines? → AGENTS.md quick commands
2. Repeated mistake? → Steering file (`.kiro/steering/`)
3. Complex multi-step workflow? → Workflow doc (`docs/workflows/`) + trigger in AGENTS.md
4. Repetitive multi-command? → Script (`scripts/`) + add to AGENTS.md
5. Non-obvious decision? → Memory (`.memory/decisions/`)
6. Project-specific context? → CLAUDE.md

**Surface ownership:**

| Surface | Content | When |
|---------|---------|------|
| AGENTS.md | Triggers, quick commands, 1-3 line rules | Always-visible reference |
| Steering | Detailed patterns, ❌/✅ examples | Repeated mistakes, friction |
| Workflow docs | Multi-step procedures | Infrequent but complex |
| Scripts | Executable automation | Repetitive sequences |
| CLAUDE.md | Project rules, architecture | Project-specific context |
| Memory | Decisions, patterns, corrections | Non-obvious choices |

**Key distinctions:**
- Steering (auto-loaded, compressed) vs Workflow (manual load, detailed)
- Script (executable) vs Steering (guidance)
- AGENTS.md (workflow/process) vs CLAUDE.md (project-specific)

## When To Reuse

Use this pattern when:
- Encountering friction and deciding where to document
- Creating new documentation/automation
- Unsure whether to create steering file vs workflow doc
- Deciding between script vs steering file
- Organizing project knowledge

## Evidence

**Created:** Surface ownership table in AGENTS.md (2026-04-17)
- 6 surfaces with clear ownership
- Decision tree for placement
- Distinctions between similar surfaces
- Examples for each surface type

**Examples:**
- `command-execution-patterns.md` → Steering (repeated friction)
- `memory-retrieval-guide.md` → Workflow (complex, infrequent)
- `deploy_dashboard.ps1` → Script (repetitive commands)
- `browser-testing-use-playwright-cli-avoid-chrome-devtools-mcp` → Memory (correction)
- Environment constraints → CLAUDE.md (project-specific)
- Triggers table → AGENTS.md (always-visible)

## Agent Retrieval Summary

Retrieve this memory when working on agents, implementation, or related pattern changes. Use it to preserve the repo-local precedent: Approach Clear ownership model for where to place different types of content: AGENTS.md, steering files, workflow docs, scripts, CLAUDE.md, memory.

## User-Facing Summary

Approach Clear ownership model for where to place different types of content: AGENTS.md, steering files, workflow docs, scripts, CLAUDE.md, memory.

## Reusable Guidance

- Treat this as repo-local pattern precedent for agents.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch agents, the implementation phase, or related tags: ownership, placement, surfaces, organization.

## Retrieval Queries

- surface ownership - what goes where (agents.md vs steering vs workflow vs scripts)
- surface ownership what goes where agents md vs steering vs
- agents
- implementation
- ownership
- placement
- surfaces
- organization
