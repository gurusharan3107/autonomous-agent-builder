---
title: "Runtime Settings"
tags: ["runtime", "settings", "codex-sdk", "claude-agent-sdk", "dashboard"]
doc_type: "reference"
created: "2026-05-01"
---

# Runtime Settings

## Purpose

This reference defines how `autonomous-agent-builder` presents and stores runtime
selection for the dashboard, CLI, and embedded server.

Runtime selection is a harness choice, not only a model-provider choice. Exactly
one `RUNTIME_SDK` value is active for a run. The user-facing lifecycle lanes are
Claude Agent SDK (`claude`) and Codex SDK (`codex_sdk`); compatibility adapters
must not be used as sprint validation lanes.

## Supported Runtimes

| `RUNTIME_SDK` | Provider default | Auth path | Endpoint shape | Settings surface |
| --- | --- | --- | --- | --- |
| `claude` | `claude_agent_sdk` | local `CLAUDE_CODE_OAUTH_TOKEN` for the Claude Agent SDK lane | Claude Agent SDK | model only |
| `codex_sdk` | `codex_subscription` | `codex login` ChatGPT/Codex session | Codex app-server/SDK JSON-RPC | model, profile, sandbox, approval |

The `openai_agents` compatibility adapter may remain in tests or lower-level
adapter code while migrations are in progress, but dashboard runtime switching
and forward-engineering sprint validation should use only `claude` and
`codex_sdk`. `codex_cli` has been removed — `codex_sdk` (Codex app-server/SDK)
supersedes the `codex exec` adapter.

## Builder Source Environment Keys

Runtime settings use the `RUNTIME_` prefix in the autonomous-builder source
`.env` or process environment. Generated app `.env` files must not own Builder
runtime selection, provider settings, auth, or telemetry configuration.

- `RUNTIME_SDK`
- `RUNTIME_PROVIDER`
- `RUNTIME_MODEL`
- `RUNTIME_API_BASE_URL`
- `RUNTIME_API_KEY_ENV`
- `RUNTIME_CODEX_PROFILE`
- `RUNTIME_SANDBOX_MODE`
- `RUNTIME_APPROVAL_POLICY`
- `RUNTIME_TRACING`

The dashboard settings surface, first-run onboarding runtime picker, and CLI
write the same keys to the autonomous-builder source `.env`. Runtime selection
controls the execution harness for future work; it must not rewrite historical
runs or hide telemetry produced by a different runtime. Selecting `claude`
enables the Claude execution lane and Claude OTEL environment from the source
`.env`. Selecting `codex_sdk` enables the Codex SDK execution lane and Codex
runtime telemetry settings from the source `.env`; generated app workspaces may
keep only project-local non-secret telemetry artifacts such as
`.codex/config.toml`. Native telemetry health can show more than one
configured/reachable lane when the source `.env` and project-local Codex
artifact evidence are both present.

When the configured native telemetry endpoint is local, `builder start` owns the
bundled in-process OTLP receiver. Startup must inspect the active project root
as well as the source `.env`: a `codex_sdk` project with `.codex/config.toml`
pointing at `localhost:4318` should get the same reachable collector as a
Claude lane with `AAB_CLAUDE_OTEL_ENABLED=1`. The Observability page should not
show `configured_unreachable` merely because the process environment lacks
Claude OTEL keys while the project-local Codex OTEL config is enabled.

Runtime selection also owns the Day-0 project guidance baseline. Selecting
`claude` uses `CLAUDE.md`; selecting `codex_sdk` uses `AGENTS.md`.
Builder-generated baselines are migrated between those filenames when the
selected lane changes, while user-authored guidance is preserved.

Telemetry keys managed with runtime selection:

- `AAB_CLAUDE_OTEL_ENABLED`
- `AAB_CLAUDE_OTEL_ENDPOINT`
- `AAB_CLAUDE_OTEL_SERVICE_NAME`
- `AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID`
- `AAB_CLAUDE_OTEL_RESOURCE_ATTRIBUTES`
- `AAB_CLAUDE_OTEL_DETAILED_BETA_TRACING`
- `AAB_CLAUDE_OTEL_BETA_TRACING_ENDPOINT`
- `AAB_CLAUDE_OTEL_LOG_USER_PROMPTS`
- `AAB_CLAUDE_OTEL_LOG_TOOL_DETAILS`
- `AAB_CLAUDE_OTEL_LOG_TOOL_CONTENT`
- `AAB_CLAUDE_OTEL_LOG_RAW_API_BODIES`
- `AAB_CODEX_RUNTIME_TELEMETRY_ENABLED`
- `AAB_CODEX_JSONL_TELEMETRY_ENABLED`
- `AAB_CODEX_TELEMETRY_SOURCE`
- `AAB_CODEX_TELEMETRY_COST_SOURCE`

Observability must distinguish selected runtime from telemetry health:

- selected runtime: the harness used for the next Agent turn or dispatch
- Claude native telemetry: Claude OTEL env, signals, sensitive flags, and
  collector reachability
- Codex native telemetry: project-local Codex `[otel]` config, exporter,
  endpoint, collector reachability, and emitted signal support
- Builder product telemetry: active DB facts for project, feature, task, run,
  phase, gate, approval, runtime, model, tool, cost, failure, retry, artifact,
  and PR

Use the public command surface for mutation:

```bash
builder agent runtime show --json
builder agent runtime probe --json
builder agent runtime models --json
builder agent runtime set --sdk claude --provider claude_agent_sdk --json
builder agent runtime set --sdk codex_sdk --provider codex_subscription --json
```

## Dashboard Copy Rules

Dashboard settings and first-run onboarding must describe the selected harness
accurately:

- Codex subscription access is **Codex login-backed**. It uses `codex login`,
  not an OpenAI-compatible endpoint and not `OPENAI_API_KEY`.
- `codex_sdk` is the product-facing Codex selector. The Python backend talks to
  `codex app-server` over JSON-RPC so the Agent page can consume streamed
  items, token usage, native `tool/requestUserInput` prompts, approval requests,
  and app-server events while preserving Codex login, workspace tools,
  sandboxing, sessions, and usage telemetry.
- Claude access is **Claude Agent SDK-backed**. Local runs use
  `CLAUDE_CODE_OAUTH_TOKEN` when subscription-backed local auth is required;
  the builder default contract must not require `ANTHROPIC_API_KEY`.
  The default Claude model is the local Claude Code/Agent SDK `sonnet` alias so
  probes use a model the subscription-backed local runtime can resolve.
  Claude-specific prompt, project setting, permission, MCP, hook, and OneCLI
  behavior applies only to `RUNTIME_SDK=claude`.

The settings UI should show one selected harness and the probe result for that
harness. It should not ask for OpenAI API settings when `codex_sdk` is selected,
and it should not show Claude OTEL as the selected runtime telemetry when the
Codex SDK harness is active. Observability must separate:

- current emission: only the selected runtime can be `enabled` or `emitting`
- config readiness: a non-selected runtime may show valid saved config, but only
  as readiness evidence, not live telemetry health
- historical access: previously persisted logs, metrics, sessions, and voice
  ledger evidence remain queryable regardless of current runtime

The non-selected runtime's native telemetry must report `inactive` for current
emission so a static config file is not confused with data being produced.

The dashboard should show the runtime probe result before activation whenever a
credential, model, profile, or endpoint changes. Probe failures should expose
the machine-readable `code` and direct `next` command returned by the runtime.

## Codex Telemetry

Codex runtime usage events must be normalized into:

- `tokens_input`
- `tokens_output`
- `tokens_cached`
- `num_turns`
- `duration_ms`
- `observability.optimization_summary.token_accounting.raw_total_tokens`
- `observability.optimization_summary.token_accounting.cached_input_tokens`
- `observability.optimization_summary.token_accounting.noncached_plus_output_tokens`
- `observability.optimization_summary.token_accounting.cache_ratio`
- `observability.reasoning_output_tokens`
- `observability.telemetry_source`
- `observability.cost_source`

Dashboard token displays must not collapse these into one ambiguous number.
For Codex SDK runs, raw total tokens, cached input tokens, and
non-cached-plus-output tokens are separate operator-visible facts. A high raw
total with a high cached-token share is different from a high fresh-token turn,
but both still belong in the token-monitoring evidence lane.

`codex_sdk` uses `observability.protocol=codex_app_server_jsonrpc` and
`observability.telemetry_source=codex_app_server_events`. Native app-server
user-input requests must surface as Agent-page question cards and record
`observability.request_user_input_count`.

Codex app-server request/response waits are runtime-health boundaries, not open
ended UI waits. Builder must bound the JSON-RPC response wait for `initialize`,
`thread/start` or `thread/resume`, and `turn/start`, then record an error and
shut down the process if the app-server stalls before returning a response. The
post-`turn/start` streaming idle timeout remains separate: it protects active
turn event delivery after the SDK has already returned a thread and turn.

Codex app-server optimization must measure native tool output from the event
stream, not only older `commandExecution`-named events. Generic `item/*` tool or
command events with names such as Bash, shell, command, exec, or terminal must
contribute to `largest_command_output_bytes`; large outputs must trigger the
same `large_command_output` / chunk-pressure guidance as CLI command output.

Codex OTEL configuration is project-local. Builder creates or validates
`.codex/config.toml` with a `[otel]` exporter only when `codex_sdk` is the
selected runtime, because non-selected native telemetry does not produce builder
run evidence. The active `.env` telemetry flags remain mutually exclusive, and
runtime status must report the non-selected lane as inactive rather than
presenting its static config as live telemetry.

Inactive does not mean inaccessible. Historical telemetry already persisted in
builder logs, metrics, session analysis, voice ledgers, and run records remains
queryable regardless of the currently selected runtime. Active/inactive controls
only which native SDK telemetry lane produces new data for the next run.

The managed Codex config must keep high-signal native debugging enabled without
exporting raw prompts:

- `log_user_prompt=false`
- log, metrics, and trace OTLP exporters
- `span_attributes` for builder product, runtime, and goal
- W3C `tracestate` metadata for the same builder correlation fields
- `[feedback] enabled=true` for Codex review and feedback triage
- `[analytics] enabled=true` for Codex usage and product-surface analytics

This native Codex OTEL lane is parallel evidence; it must not replace active-DB
run evidence or pretend Codex and Claude emit the same native telemetry schema.

Builder must never write global `~/.codex/config.toml` for this purpose. If
Codex OTEL config is needed, create or validate only the target project's
`.codex/config.toml`.

For `provider=codex_subscription`, the builder must not invent a metered dollar
cost. Board cards, approval run tables, metrics, and task sidebars should show
cost usage as `subscription` when Codex does not provide a run-level dollar
cost, while retaining token, turn, duration, and telemetry-source details in
the drill-down payload.

## Validation

Runtime settings changes should pass:

```bash
builder quality-gate modular-runtime --json
builder agent runtime show --json
builder agent runtime probe --json
builder logs analyze --session <id-or-prefix> --json
PYTHONPATH=src pytest tests/test_runtime_interface.py tests/test_codex_app_server_runtime.py tests/test_onboarding_runtime_selection.py tests/test_execution_policy.py -q
```
