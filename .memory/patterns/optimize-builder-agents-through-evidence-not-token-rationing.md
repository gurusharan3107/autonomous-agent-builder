---
title: Optimize Builder agents through evidence, not token rationing
type: pattern
date: 2026-05-07
phase: optimization
entity: agent-effectiveness
tags: [observability, metrics, logs, agents, tokens]
status: active
---

## Pattern

Use Builder CLI metrics, observability, and logs as the primary evidence lane
for finding ineffective specialist-agent behavior. Optimize the responsible
Builder surface rather than treating token reduction as the goal by itself.

## Agent Retrieval Summary

Retrieve this before changing agent definitions, prompts, allowlists,
denylists, model routing, tools, hooks, observability recommendations, or
delivery-phase policies.

Use this rule: Autonomous Builder should make specialist agents more effective
at their actual job by giving them the right prompt, tools, permissions, context
packet, model, and stop condition. Lower token usage is a result of less wasted
work, not a standalone quality metric.

## User-Facing Summary

This memory explains why Builder exists on top of Codex and Claude Code: it
uses delivery telemetry to improve the agents and workflow so app creation gets
to quality outcomes with less wasted context and time.

## Reusable Guidance

- Inspect `builder metrics show --json --full`, `builder logs --info --compact
  --json`, and `builder logs analyze --json` before changing prompts, tools, or
  model routing.
- Treat repeated over-reading, noisy command output, wrong-tool use, avoidable
  approvals, missing telemetry, and high-turn work as Builder product issues.
- Fix the owning surface: agent definition, prompt, allowlist, denylist, phase
  policy, deterministic script, hook, quality gate, or observability
  recommendation.
- Do not cap tokens arbitrarily. Prefer better task packets, sharper
  permissions, deterministic helpers, and clearer stop conditions.

## When To Apply

Apply this during generated-app validation, post-run optimization, runtime
tuning, observability triage, and any review of why a Builder agent took too
long or used too much context to produce a quality result.

## Retrieval Queries

- ineffective builder agent metrics logs observability
- optimize agents without token rationing
- right prompt tools allowlist denylist context
- why autonomous builder over codex claude code
