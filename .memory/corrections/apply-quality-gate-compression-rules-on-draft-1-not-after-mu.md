---
title: Apply quality-gate compression rules on draft 1, not after multiple revision rounds
type: correction
date: 2026-05-08
phase: implementation
entity: agents-md
tags: [agents-md, quality-gate, fix-discipline, memory-discipline]
status: active
---

## Correction

When editing any owner-gated surface (AGENTS.md, CLAUDE.md, runtime contracts, quality-gate docs), read the gate's rules in full BEFORE the first edit and apply its compression/shape rules on draft 1 — do not iterate through three rounds of trim-and-prune that the gate already told you to skip. The gate exists precisely so the right shape lands on the first attempt.

## Agent Retrieval Summary

Retrieve before any AGENTS.md / CLAUDE.md edit, or any time `workflow quality-gate <surface>` exists for the file being changed. The active rule: read the gate, then apply ALL its compression/shape clauses (terse triggers, owner docs hold detail, anti-patterns to avoid) to the FIRST draft — not after multiple revision rounds.

## User-Facing Summary

The quality gate is a contract for shape, not a checker run after the fact. Match the shape on the first try.

## Reusable Guidance

- For AGENTS.md specifically: gate prescribes "Keep AGENTS.md compressed: triggers, boundaries, dead ends, and routing" and "If the content is longer than a few stable lines, move it to a retrievable doc and keep only the trigger in AGENTS.md." Apply this as the constraint on draft 1, not as feedback after draft 3.
- Anti-pattern observed: started with verbose triggers that inlined taxonomy, type-selection logic, save procedure, and lifecycle. Trimmed in three rounds before reaching the gate-conformant shape (one row = trigger + command + cwd rule + doc link). The 5→3→2-row arc was avoidable; the gate told me "one trigger line per stable task class" and "long prose where a one-line trigger plus owner doc would be clearer" from the start.
- Mechanic: when the gate says "move detail to a retrievable doc", write that doc FIRST (or update it), then write the AGENTS.md row LAST as a thin pointer. This forces the row to be a pointer, not a self-contained explanation.
- Applies broadly: any surface with a quality gate (`builder quality-gate <surface>`, `workflow quality-gate <surface>`) is asking for a specific shape. Read the gate, then write to that shape — do not write a freelance draft and trust the gate to catch it later.

## When To Apply

Before editing AGENTS.md, CLAUDE.md, or any quality-gate-owned doc. Specifically: at the moment the temptation arises to add a new row or section, run the relevant gate first and write the edit to its shape.

## Retrieval Queries

- agents.md edit shape
- quality gate first not last
- compression triggers owner doc
- one trigger line per task class
- write to gate shape on draft one
