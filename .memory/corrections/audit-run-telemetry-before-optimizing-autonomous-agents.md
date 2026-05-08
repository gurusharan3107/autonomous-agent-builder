---
title: Audit run telemetry before optimizing autonomous agents
type: correction
date: 2026-05-05
phase: optimization
entity: autonomous-builder-runtime
tags: [telemetry, optimization-agent, codex-sdk, deterministic-scripts, control-surfaces]
status: active
---

## Correction

When validating autonomous builder efficiency, do not judge from the UI timeline or from agent prose alone. Audit each task agent run through builder-owned telemetry, observability summaries, and logs before deciding what should be optimized or which control surface should change.

## Agent Retrieval Summary

Retrieve this memory when a future session is asked whether the autonomous builder used Claude Agent SDK or Codex SDK efficiently, whether an optimization agent missed a candidate, or whether prompts, runtime contracts, tool policy, or deterministic scripts should change.

Use this as the operating rule: inspect per-run `AgentRun` / event data, `builder metrics show --json --full`, `builder logs --info --compact --json`, and `builder logs analyze --json` before proposing prompt changes. The highest-value fix may belong in routing/orchestration, a deterministic script, `CLAUDE.md`, or the agent definition prompt, not only in the visible dashboard.

## User-Facing Summary

Future runs should check the actual telemetry and logs for every task agent run before claiming the builder is efficient. This prevents the optimizer from picking a lower-value deterministic candidate while missing a more expensive repeated agent lane.

## Reusable Guidance

- Compare each run by agent name, runtime, status, total tokens, cached tokens, command count, deterministic checks, reads, edits, and avoidable-cost flags.
- Treat model-backed PR/evidence lanes as suspect for local generated-app Codex workspaces without a real Git PR target. Prefer deterministic `change_evidence` there.
- Treat model-backed build verification as suspect when a generated-app Codex workspace can be verified by deterministic `build_verify`.
- If `logs analyze` reports a runtime that conflicts with observed run coverage, fix the observability surface before using it as optimization evidence.
- Choose the owner surface by failure type: `CLAUDE.md` for runtime contract, `agents/definitions.py` for agent prompt/tool mindset, orchestrator routing for lane selection, embedded scripts for deterministic replacements, and dashboard only for user-visible proof.
- Optimization candidates should be ranked by estimated savings and avoidable-work flags before lower-value deterministic convenience scripts.

## When To Apply

Apply this after shipped sprint validation, when reviewing the optimization pill/timeline, when comparing Claude Agent SDK and Codex SDK lanes, or when a user asks whether the agent stayed focused and token efficient.

## Retrieval Queries

- optimization agent telemetry missed candidate
- pr-creator deterministic change_evidence generated app
- build-verifier deterministic build_verify codex sdk
- logs analyze selected runtime coverage codex_sdk
- control surface CLAUDE prompt orchestrator tool policy optimization
