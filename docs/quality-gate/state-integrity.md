---
title: "State integrity quality gate"
surface: "state-integrity"
summary: "Use when changing persistence, projections, events, migrations, or product telemetry to prove active DB state remains canonical."
commands:
  - "builder quality-gate state-integrity --json"
  - "builder metrics show --json --full --limit 10"
  - "builder logs analyze --session <id-or-prefix> --json"
  - "builder memory lint --json"
expectations:
  - "active DB product facts remain canonical for project, feature, task, run, phase, gate, approval, runtime, model, tool, cost, failure, retry, artifact, and PR"
  - "artifacts, JSON files, chat transcripts, SSE events, dashboard responses, and logs are projections or evidence, not competing sources of truth"
  - "writes are transactional or have deterministic post-mutation retrieval checks"
  - "model-backed mutation claims require an allowed Builder tool plus exact target/consequence evidence or visible approval"
  - "embedded and main server surfaces expose the same product contract"
  - "builder-normalized telemetry powers Board, Metrics, Observability, logs analyze, and deterministic recommendations"
related_docs:
  - "docs/references/runtime-switch-dashboard-contract.md"
  - "docs/quality-gate/modular-runtime.md"
  - "docs/quality-gate/architecture-boundary.md"
---

# State integrity quality gate

## Purpose

Use this gate when a change can create drift between the active DB and any
derived product surface.

## When To Load

Load this gate before changing:

- database models, migrations, repositories, or write paths
- dashboard API projections, streams, metrics, observability, or logs analysis
- memory, knowledge, approval, task, or runtime-settings mutation behavior
- archived-to-active migration or compatibility projections

## Pass Signals

- the active DB is the canonical source for product state and recommendations
- projections include enough IDs, status, runtime, and evidence to debug drift
- mutation commands return retrieval and lint/proof evidence where applicable
- model-backed agents may execute clear operator intent through granted Builder tools, but do not infer broad wording as approval for destructive or bulk state changes
- stale archive or generated artifact state is never read directly as live truth

## Fail Signals

- artifacts, raw logs, or archived builder data are treated as live state
- CLI/API/UI disagree on task, run, approval, telemetry, or runtime attribution
- a mutation succeeds without a retrievable canonical record
- an agent claims it marked, cleared, deleted, approved, denied, dispatched, or shipped Builder state without a granted tool and exact visible target/consequence evidence
- recommendations trigger from transcript text instead of structured facts
