---
title: "Agent quality gate"
surface: "agent-quality"
summary: "Use when tuning agent behavior to verify mission alignment, observability coverage, tool/model discipline, and context-efficient execution."
commands:
  - "workflow --docs-dir docs read MISSION.md"
  - "workflow --docs-dir docs read references/phase-model"
  - "workflow --docs-dir docs read references/agent-optimization-analysis"
  - "builder quality-gate claude-agent-sdk --json"
  - "builder quality-gate builder-cli --json"
  - "builder agent sessions --json"
  - "builder agent history --session <id> --json"
  - "builder agent runtime show --json"
  - "builder agent runtime probe --json"
  - "builder logs analyze --session <id-or-prefix> --json"
  - "builder metrics show --json"
expectations:
  - "agent behavior stays aligned with docs/MISSION.md: the system chooses workflow, model, tools, and context strategy so the user does not have to"
  - "quality tuning starts from real builder session evidence rather than intuition or static prompt opinions alone"
  - "the default evidence lane is builder-owned session/history/log analysis; OTEL export strengthens the lane but does not replace builder as the repo-local owner"
  - "context efficiency is evaluated as bounded retrieval, compact machine-readable outputs, and minimal repeated or irrelevant tool work"
  - "Codex SDK tuning exposes raw-token optimization summaries with cached, non-cached, phase, tool, and avoidable-cost attribution instead of relying on subscription cost display"
  - "Codex SDK token optimizations preserve model-backed intent/tool selection for judgment prompts and target cache-friendly prompt shape, bounded evidence, deferred tools, compaction, and clear raw/cached/effective token reporting"
  - "Claude Agent SDK tuning preserves the model-backed agent loop for judgment prompts and targets tool scope, permissions, hooks, AskUserQuestion, subagents, tool search, compaction, effort, turn/budget limits, and cache creation/read telemetry"
  - "Metrics and logs analysis expose optimization decisions, telemetry health, and deterministic recommendation codes from structured evidence"
  - "tool use stays phase-appropriate and mission-appropriate; broad or redundant tool scans are treated as quality regressions"
  - "model selection is intentional: cheaper models handle routine work and stronger models are reserved for tasks that need them"
  - "runtime-specific strengths are preserved: Codex SDK uses app-server events and native user-input telemetry, Claude uses Claude Agent SDK mechanics, and API-backed providers stay API-backed"
  - "system-prompt, CLAUDE.md, subagent, and tool-set changes remain bounded product improvements instead of ad hoc per-session fixes"
  - "phase-level agents and subagents exist for isolation or specialization, not as default complexity or parallelism theater"
  - "quality recommendations map back to canonical owner surfaces such as prompts, phase docs, CLAUDE.md, tool contracts, and agent definitions"
  - "the user should experience one coherent builder product, not a visible pile of SDK/runtime decisions"
related_docs:
  - "docs/MISSION.md"
  - "docs/references/phase-model.md"
  - "docs/references/agent-optimization-analysis.md"
  - "docs/references/runtime-settings.md"
  - "docs/quality-gate/modular-runtime.md"
  - "docs/quality-gate/claude-agent-sdk.md"
  - "docs/workflows/agent-quality-tuning-loop.md"
---

# Agent Quality Gate

## Purpose

Use this gate when changing how the builder's agents behave, what context they
load, which tools they may use, how they route across phases, or how their
runtime evidence is interpreted for tuning.

This gate exists to keep agent tuning anchored to the product mission:

- higher delivery quality
- lower user burden
- stronger context efficiency
- bounded runtime behavior that still feels like one builder-owned system

## When To Load

Load this gate before:

- changing agent system prompts or prompt assembly
- changing what `CLAUDE.md` or other repo-owned instructions load into agent
  execution
- changing agent definitions, subagent definitions, or phase-level routing
- changing default model selection or fallback model policy
- changing default tool allowlists, approvals, or phase-level permissions
- changing how builder logs, session history, or observability data are used to
  judge agent quality
- changing Codex SDK telemetry use, request-user-input handling, or
  runtime-strength analysis in tuning recommendations
- changing optimization-analysis policy for builder-self tuning

## Pass Signals

- tuning begins from real builder evidence such as `builder agent history` and
  `builder logs analyze`, not from generic prompt ideology
- the user still stays in a simple chat-first product while the builder owns
  workflow, model, tool, and context decisions
- prompt and instruction surfaces stay concise, non-duplicative, and scoped to
  the correct owner surface
- phase behavior stays consistent with the canonical phase model
- subagents are justified by isolation or specialization and improve net
  efficiency rather than inflating context or tool churn
- tool use is bounded, relevant, and proportionate to the task
- model choice reflects cost-aware execution without silently lowering quality
- runtime selection and telemetry fields match the selected harness and are not
  collapsed to a lowest-common-denominator feature set
- recommendations are specific enough to map back to a repo-owned surface that
  can actually be changed and verified

## Fail Signals

- tuning is justified only by static code reading or taste rather than session
  evidence
- the user would need to understand internal model, tool, or subagent strategy
  to get the intended product behavior
- the agent repeatedly performs broad discovery, duplicate retrieval, or large
  irrelevant reads for routine tasks
- long prose outputs are emitted where compact symbolic fields or direct next
  commands would have been enough
- phase prompts, `CLAUDE.md`, knowledge docs, and system prompts start
  duplicating each other instead of keeping one owner per concern
- new subagents are added to mask weak routing or weak main-lane prompts
- Codex SDK is treated like Codex CLI compatibility behavior when app-server
  events, native user-input, or richer telemetry are available
- runtime tuning pushes product-state ownership into the SDK lane
- telemetry or observability gaps are ignored and replaced with guesswork

## Recommended Verification

Read:

- [MISSION.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/MISSION.md)
- [phase-model.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phase-model.md)
- [agent-optimization-analysis.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/agent-optimization-analysis.md)
- [claude-agent-sdk.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/claude-agent-sdk.md)

Check evidence when relevant:

- `builder agent sessions --json`
- `builder agent history --session <id> --json`
- `builder agent runtime show --json`
- `builder agent runtime probe --json`
- `builder logs analyze --session <id-or-prefix> --json`
- `builder metrics show --json`

Confirm that:

- the latest session shows the intended model and bounded tool behavior
- context-efficiency warnings are explained or eliminated
- Codex SDK runs include `optimization_summary` fields in metrics and logs
  analysis, including raw tokens, non-cached + output tokens, cache ratio, phase
  ceremony tokens, top cost drivers, and a concrete next-change recommendation
- Metrics includes a stable `optimization_decision`, runtime decision summary,
  and deterministic script candidates when enough structured evidence exists
- Observability and `builder logs analyze --session <id-or-prefix> --json` include selected runtime,
  runtime-native telemetry health, builder-product telemetry health, and stable
  deterministic recommendation codes with evidence
- tuning decisions target the smallest correct owner surface
- observability gaps are reported explicitly when they block stronger analysis

## Anti-Patterns

- tuning prompts without checking what the runtime actually did
- adding more context sources when the real problem is weak routing or weak tool
  discipline
- creating a subagent for every phase instead of fixing the main execution
  contract
- treating OTEL export as a substitute for builder-owned local evidence
- optimizing for verbose intelligence theater instead of compact, high-quality
  delivery

## Related Docs

- [MISSION.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/MISSION.md)
- [phase-model.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/phase-model.md)
- [agent-optimization-analysis.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/agent-optimization-analysis.md)
- [runtime-settings.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-settings.md)
- [modular-runtime.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/modular-runtime.md)
- [claude-agent-sdk.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/claude-agent-sdk.md)
- [agent-quality-tuning-loop.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/agent-quality-tuning-loop.md)
