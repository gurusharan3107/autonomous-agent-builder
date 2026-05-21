# GOAL.md — Deprecated, Migrated to docs/goal/

**This file is a redirect.** All content has been migrated into the [`docs/goal/`](goal/README.md) framework. New agents and new references should not target this file.

## Where each section of the original GOAL.md now lives

| Original GOAL.md section | Where it is now |
| --- | --- |
| Primary goal statement ("lead operator and principal engineer", "rigorous live testing", "non-technical operator", lifecycle ownership) | [`docs/goal/NORTH-STAR.md`](goal/NORTH-STAR.md) and [`docs/goal/ROADMAP.md`](goal/ROADMAP.md) M2.1 (lifecycle completeness). |
| "Scope of inefficiency" (tokens, context bloat, agent use, surface drift, dead code, slow paths, operator UX) | [`docs/goal/EVALUATION.md § Tier 1`](goal/EVALUATION.md#tier-1--token--ux-bars-every-release) plus the autoresearch composite metric in [`docs/autoresearch/OPTIMIZE.md`](autoresearch/OPTIMIZE.md). |
| "Builder CLI is the primary investigative weapon" | [`docs/goal/TUNING.md § Continuous CLI Monitoring`](goal/TUNING.md#continuous-cli-monitoring-always-on-not-on-demand). |
| Testing standard (multi-turn, board transitions, monitoring, gate infrastructure, recovery, history inspection, cross-checking) | [`docs/goal/EVALUATION.md § Tier 1`](goal/EVALUATION.md#tier-1--token--ux-bars-every-release) and [`§ Tier 2`](goal/EVALUATION.md#tier-2--lifecycle-coverage-bars-every-milestone). |
| **Fix standard (steps 0-7)** | [`docs/goal/FIX-STANDARD.md`](goal/FIX-STANDARD.md). |
| Acceptance thresholds (cache ratio, chunk pressure, avoidable cost flags, gates-first, zero stale messages, CLI/UI parity, recovery path) | [`docs/goal/EVALUATION.md § Tier 1 Hard Gates`](goal/EVALUATION.md#tier-1--token--ux-bars-every-release). |
| Acceptance layers (operator UX abstraction, live shipping + token monitoring) | [`docs/goal/EVALUATION.md § Tier 1.2 Operator UX bars`](goal/EVALUATION.md#12--operator-ux-bars-per-session). |
| Guiding principles (ask don't assume, simplest first, don't touch unrelated code, flag uncertainty) | [`docs/goal/NORTH-STAR.md § Agent Working Principles`](goal/NORTH-STAR.md#agent-working-principles-always-on). |
| **Per-agent boundaries** (chat / scaffold / code-gen / build-verifier / repo-researcher / doc-bridge) | [`docs/rubric/autonomous-builder-agents.md`](rubric/autonomous-builder-agents.md) (authoritative). Referenced from [`docs/goal/INDEX.md`](goal/INDEX.md). |
| **Tuning methodology** (continuous CLI monitoring + per-prompt tuning loop) | [`docs/goal/TUNING.md`](goal/TUNING.md). |
| **Forbidden operator language** (banned terms, good/bad prompts) | [`docs/goal/OPERATOR-LANGUAGE.md`](goal/OPERATOR-LANGUAGE.md). |
| **Operator scenarios** (F1-F10 forward, E1-E9 edge, R1-R3 reverse) | [`docs/goal/OPERATOR-LANGUAGE.md § Operator Scenarios`](goal/OPERATOR-LANGUAGE.md#operator-scenarios). |

## What to do instead

- **New agent landing on the project:** read [`docs/goal/README.md`](goal/README.md) first. It is the single authoritative entry point and lists every replacement file.
- **External reference still pointing here:** follow the table above to find the new owner. Update the reference when you next touch the file.

This file is kept (rather than deleted) so that existing references in `docs/REFERENCE.md`, `docs/quality-gate/product-lifecycle.md`, `docs/references/realtime-voice-integration.md`, `docs/references/autonomous-builder-telemetry-analysis.md`, `docs/autoresearch/README.md`, and similar locations resolve to a real file that explains where the content moved. Do not add new references to this file.
