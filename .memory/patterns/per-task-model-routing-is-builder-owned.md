---
title: Per-task model routing is builder-owned
type: pattern
date: 2026-05-07
phase: implementation
entity: execution-policy
tags: [model-routing, claude-agent-sdk, cost-quality, opus-4-7, sonnet-4-6, haiku-4-5]
status: active
---

## Pattern

Per-task model routing is a builder responsibility, not a user choice. The user does not pick the model or the thinking effort — `src/autonomous_agent_builder/agents/execution_policy.py` and `agents/definitions.py` route model + effort per agent role.

## Agent Retrieval Summary

Retrieve this memory when changing or auditing model selection, runtime defaults, or cost-quality tradeoffs in the Claude Agent SDK lane.

Operating rule: judge model choices by per-job fit. Hard agentic / long-horizon coding / orchestration → Opus 4.7 with `xhigh` effort. Balanced narrow code edits, design review, integration → Sonnet 4.6. Simple classification, fast subagent reads, KB extraction, dispatch → Haiku 4.5. Never collapse to one global model default.

## User-Facing Summary

Builder picks the model and thinking effort per task; the user does not. The chosen model should match task difficulty so cost and quality stay balanced.

## Reusable Guidance

- `_AGENT_POLICY` in `agents/execution_policy.py` owns per-role effort + context strategy. The model itself comes from `settings.agent.{planning,design,implementation,pr}_model` plus the per-agent `model` field on `AgentDefinition` in `agents/definitions.py`.
- Default settings (`config.py`): `planning_model=opus`, `design_model=opus`, `implementation_model=sonnet`, `pr_model=sonnet`. KB models pin `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-opus-4-7`.
- `runtime/factory.py` uses `anthropic/claude-sonnet-4-5` as a default fallback — this is legacy. Current target IDs are `claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5` (no date suffix unless pinning).
- For Opus 4.7 specifically: thinking is adaptive only (`thinking={"type":"adaptive"}`); `budget_tokens`, `temperature`, `top_p`, `top_k` return 400. Use `output_config={"effort": "..."}` instead. `xhigh` is recommended for coding/agentic; `high` is the minimum for intelligence-sensitive work. Set `display:"summarized"` if surfacing thinking text.
- Subagents (`resolve_subagent_model`) should stay cheap: Haiku for `repo-researcher`, `browser-verifier`, `build-verifier`, `pr-reviewer`, `documentation-agent`; Sonnet for `security-reviewer`.
- When evaluating model choice in code review or optimization, do not blanket-suggest Opus everywhere — that violates cost-quality balance. Match model to task class.

## When To Apply

Apply when:
- Editing `execution_policy.py`, `agents/definitions.py`, or `config.py` model defaults.
- Auditing telemetry that shows over-spend on simple tasks or under-delivery on hard ones.
- Migrating models or rolling forward to newer Claude IDs.
- Reviewing optimization-agent recommendations that touch model selection.
- Resolving user feedback that a task was too slow or too dumb — first lever is model fit, not prompt rewrite.

## Retrieval Queries

- per task model routing
- builder model selection
- claude opus sonnet haiku choice
- execution policy model
- runtime model default
- thinking effort per agent
- cost quality tradeoff builder
