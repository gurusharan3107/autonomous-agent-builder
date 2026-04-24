---
title: Claude Agent SDK as foundation
type: decision
date: 2026-04-14
phase: design
entity: orchestrator
tags: [sdk, architecture, foundation]
status: active
---

## Decision

Use Claude Agent SDK as the foundation for the autonomous builder. Replaces 6 custom components (prompt management, tool dispatch, session handling, cost tracking, permission control, streaming).

## Trace

- Inputs: Evaluated Agent SDK docs, existing custom implementation, maintenance burden
- Policy: Prefer SDK over custom when SDK covers >80% of requirements
- Exception: None â€” SDK covers all requirements
- Approval: Architecture review confirmed
