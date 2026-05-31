---
title: "Complexity ratchet quality gate"
surface: "complexity"
summary: "Use when changing Python source, large route/service/test files, or builder lint enforcement that can grow god files or oversized functions."
commands:
  - "builder lint --complexity-report --json"
  - "builder lint --json"
  - "uv run pytest tests/test_complexity_guard.py -q"
expectations:
  - "current historical hotspots are allowed only when listed in docs/quality-gate/complexity-baseline.json with owner and extraction plan"
  - "new Python files above 500 lines fail builder lint unless baselined with an owner and extraction plan"
  - "new Python functions above 250 lines or 50 branch nodes fail builder lint unless baselined with an owner and extraction plan"
  - "baselined files and functions fail if they grow beyond the recorded line or branch count"
  - "baselined files and functions also fail if they shrink but the baseline is not ratcheted down to the new count"
  - "report mode remains non-blocking so agents can inspect hotspots before deciding whether to split code or update the baseline"
related_docs:
  - "docs/REFERENCE.md"
  - "docs/quality-gate/architecture-boundary.md"
---

# Complexity Ratchet Quality Gate

## Purpose

Use this gate to prevent files above the 500-line architecture target and
large-function debt from growing while existing hotspots are being decomposed
incrementally.

## When To Load

Load this gate before:

- adding behavior to large route, orchestrator, service, runtime, or test files
- adding or expanding functions near the ratchet thresholds
- changing `builder lint` complexity enforcement
- updating `docs/quality-gate/complexity-baseline.json`

## Pass Signals

- `builder lint --complexity-report --json` identifies hotspots without blocking
- `builder lint --json` passes the ratchet check
- every over-threshold historical hotspot has an owner and extraction plan
- baselined line and branch counts do not grow
- baseline line and branch counts ratchet down when decomposition reduces a
  hotspot
- new over-threshold code is split before merge, not silently added to the baseline

## Fail Signals

- a new over-threshold file or function is not baselined
- a baseline entry omits owner or extraction plan
- a baselined file or function grows beyond its recorded count
- a baselined file or function shrinks but keeps a stale higher allowed count
- the baseline is updated without a current scanner report
