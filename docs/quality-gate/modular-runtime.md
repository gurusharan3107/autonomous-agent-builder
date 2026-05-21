---
title: "Modular runtime quality gate"
surface: "modular-runtime"
summary: "Use when changing runtime selection, runtime adapters, provider probes, or dashboard runtime settings."
commands:
  - "builder agent runtime show --json"
  - "builder agent runtime probe --json"
  - "builder agent runtime models --json"
  - "builder quality-gate architecture-boundary --json"
  - "builder quality-gate claude-agent-sdk --json"
  - "pytest tests/test_runtime_interface.py tests/test_codex_app_server_runtime.py tests/test_onboarding_runtime_selection.py tests/test_execution_policy.py -q"
expectations:
  - "exactly one runtime harness is active for a run"
  - "user-facing runtime selection exposes only claude and codex_sdk; compatibility adapters must not be advertised as sprint validation lanes"
  - "selected runtime owns the Day-0 guidance baseline: claude uses CLAUDE.md, Codex uses AGENTS.md, and builder-generated baselines migrate when lanes switch"
  - "runtime selection flows through RuntimeSettings and create_runtime() rather than product paths instantiating adapters directly"
  - "claude keeps AgentRunner and Claude Agent SDK mechanics behind ClaudeRuntime"
  - "codex_sdk uses the Codex app-server/SDK JSON-RPC contract with Codex login auth and must expose token, turn, duration, native user-input, and telemetry-source fields in RunResult observability"
  - "compatibility adapters such as codex_cli and openai_agents may remain in lower-level tests but must fail user-facing runtime activation"
  - "provider limits, auth misses, unsupported models, and unsupported capabilities normalize into deterministic builder state"
  - "dashboard and CLI settings describe Codex SDK subscription access as Codex login-backed"
  - "dashboard Settings and first-run onboarding mutate the same runtime settings service and keep Claude OTEL versus Codex telemetry mutually exclusive"
  - "inactive runtime lanes stop producing new telemetry while previously generated telemetry remains accessible through logs, metrics, and session analysis"
  - "when codex_sdk is selected, project-local Codex telemetry config includes log, metrics, trace, span_attributes, tracestate, feedback, and analytics signals without writing global ~/.codex/config.toml"
  - "Codex subscription cost usage renders as subscription metering instead of fabricated dollar cost"
related_docs:
  - "docs/design-docs/modular-runtime-architecture.md"
  - "docs/references/runtime-settings.md"
  - "docs/claude-agent-sdk-integration.md"
---

# Modular Runtime Quality Gate

## Purpose

Use this gate when changing runtime selection, runtime adapters, provider probes,
or dashboard/runtime settings.

The check keeps the two user-facing runtime lanes distinct:

- `claude`: Claude Agent SDK with local Claude OAuth token auth and
  `ClaudeRuntime`
- `codex_sdk`: Codex app-server/SDK JSON-RPC path over the same local Codex
  login auth

Compatibility adapters such as `codex_cli` and `openai_agents` may remain in
lower-level runtime tests while migration work is in progress, but they are not
dashboard, onboarding, or sprint-validation lanes.

## When To Load

Load this gate before:

- changing `RuntimeSettings`, `runtime/factory.py`, or any runtime adapter
- adding, renaming, or removing `builder agent runtime ...` commands
- changing Agent page, orchestrator, or documentation bridge runtime wiring
- changing dashboard copy or settings for runtime selection
- changing compatibility adapter behavior that could leak into user-facing
  runtime selection

## Pass Signals

- Product execution paths call `create_runtime()` and do not instantiate runtime
  adapters directly.
- `codex_sdk` paths expose Codex app-server/SDK benefits without `codex exec`:
  streamed items, native user-input requests, tools, workspace access,
  sandboxing, approvals, session IDs, provider-limit detection, and usage
  telemetry.
- Codex runtime usage is normalized into persisted `agent_runs` fields and chat
  `run_status.observability` so Board, Metrics, approvals, and
  `builder logs analyze` use the same token/turn telemetry.
- Dashboard settings and first-run onboarding use the same runtime settings
  writer as `builder agent runtime set`, including mutually exclusive Claude
  OTEL versus Codex runtime telemetry env flags. Project-local Codex
  `.codex/config.toml` is created or refreshed for Codex-selected runs only,
  and must include OTLP logs, metrics, traces, `span_attributes`, `tracestate`,
  `[feedback]`, and `[analytics]` without touching global Codex config.
- Historical telemetry from either lane remains accessible through builder logs,
  metrics, session analysis, run records, and voice ledgers even when that lane
  is no longer selected for new telemetry emission.
- Board, Metrics, approvals, task sidebars, and `builder logs analyze` use the
  normalized runtime telemetry fields instead of raw adapter-specific events.
- Day-0 readiness validates the selected runtime's guidance file: `CLAUDE.md`
  for Claude and `AGENTS.md` for Codex. Switching between those lanes migrates a
  builder-generated baseline instead of leaving duplicate active guidance.
- Compatibility adapters are not returned by user-facing runtime lists and fail
  user-facing activation with a deterministic `invalid_sdk` error.
- Runtime probes return compact machine-readable fields: `ok`, `sdk`,
  `provider`, `model`, `code`, `next`, and `capabilities`.
- Runtime-specific provider limits and auth/config failures map into builder
  state without changing backlog, board, approval, or phase semantics.
- Codex transport chunk-limit failures are treated as retryable runtime
  transport errors for both known variants: `separator is not found` with
  `chunk exceed`, and `separator is found` with `chunk is longer than limit`.
- Codex app-server large command output is materialized as local Builder
  artifact evidence before the returned runtime event stream is compacted; the
  run's active optimization summary scores the compacted reinjection stream and
  records the original size in `tool_output_reinjection`.

## Fail Signals

- Codex subscription access is presented as an OpenAI API endpoint or as an
  OpenAI Agents SDK provider.
- Codex usage events are stored only as raw events and do not populate
  `tokens_input`, `tokens_output`, `tokens_cached`, `num_turns`, `duration_ms`,
  or `observability.telemetry_source`.
- Codex project-local telemetry is logs-only, lacks trace metadata, or disables
  feedback or analytics surfaces needed for review and triage.
- Runtime status reports non-selected native telemetry as producing emitted
  signals, reachable collector health, or live trace metadata.
- Runtime selection hides or discards historical telemetry from the inactive
  lane.
- Codex app-server `item/tool/requestUserInput` requests do not appear as
  Agent-page question cards when `RUNTIME_SDK=codex_sdk`.
- Codex app-server native command or tool output is ignored before artifact and
  compaction accounting, so oversized `item/*` events neither preserve local
  evidence nor emit `context_retention`/`tool_output_reinjection` policy.
- One known Codex chunk-limit wording retries while another equivalent wording
  fails directly and leaves a runtime-error recommendation unresolved.
- Dashboard cost copy shows `$0.0000` as if Codex subscription auth had emitted a
  metered cost instead of identifying subscription metering.
- `openai_agents` silently falls back to ChatGPT/Codex login state.
- `codex_cli`, `openai_agents`, or other compatibility adapters appear in the
  dashboard runtime selector, onboarding lane picker, or sprint validation docs.
- Product routes import Claude, Codex, or OpenAI adapter classes directly when
  `create_runtime()` can be used.
- Adapter mechanics change task lifecycle, approval, backlog, board, knowledge,
  memory, or metrics semantics.
- Dashboard/runtime settings ask users for provider credentials that the selected
  harness does not use.

## Related Docs

- [modular-runtime-architecture.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/design-docs/modular-runtime-architecture.md)
- [runtime-settings.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-settings.md)
- [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
