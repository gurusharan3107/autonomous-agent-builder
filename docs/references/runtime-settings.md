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
Claude Agent SDK (`claude`), Anthropic Managed Agents (`claude_managed`, cloud,
GitHub-backed projects only), and Codex SDK (`codex_sdk`); compatibility
adapters must not be used as sprint validation lanes.

## Supported Runtimes

| `RUNTIME_SDK` | Provider default | Auth path | Endpoint shape | Settings surface |
| --- | --- | --- | --- | --- |
| `claude` | `claude_code` | Claude Code auth path | Claude Agent SDK / Claude Code | model only |
| `claude_managed` | `anthropic_managed` | `ANTHROPIC_API_KEY` (Managed Agents beta access) | Managed Agents API (cloud sessions, hosted agents, vault-backed MCP, webhook follow-up) | model only |
| `codex_sdk` | `codex_subscription` | `codex login` ChatGPT/Codex session | Codex app-server/SDK JSON-RPC | model, profile, sandbox, approval |

Compatibility adapters such as `codex_cli` and `openai_agents` may remain in
tests or lower-level adapter code while migrations are in progress, but dashboard
runtime switching and forward-engineering sprint validation should use only
`claude`, `claude_managed`, or `codex_sdk`.

## Environment Keys

Runtime settings use the `RUNTIME_` prefix in `.env` or process environment:

- `RUNTIME_SDK`
- `RUNTIME_PROVIDER`
- `RUNTIME_MODEL`
- `RUNTIME_API_BASE_URL`
- `RUNTIME_API_KEY_ENV`
- `RUNTIME_CODEX_PROFILE`
- `RUNTIME_SANDBOX_MODE`
- `RUNTIME_APPROVAL_POLICY`
- `RUNTIME_TRACING`

The dashboard settings surface and first-run onboarding runtime picker write the
same `.env` keys as the CLI. Runtime selection controls the execution harness
for future work; it must not rewrite historical runs or hide telemetry produced
by a different runtime. Selecting `claude` enables the Claude execution lane and
Claude OTEL environment. Selecting `codex_sdk` enables the Codex SDK execution
lane and project-local Codex telemetry settings. Native telemetry
health can show more than one configured/reachable lane when the project has
both Claude env and Codex `.codex/config.toml` evidence.

Runtime selection also owns the Day-0 project guidance baseline. Selecting
`claude` or `claude_managed` uses `CLAUDE.md`; selecting `codex_sdk` uses
`AGENTS.md`. Builder-generated baselines are migrated between those filenames
when the selected lane changes, while user-authored guidance is preserved.

`claude_managed` requires a GitHub-backed project (the runtime probe fails fast
when no `github_repository` resource can be derived) and an
`ANTHROPIC_API_KEY` with Managed Agents beta access. One-time agent provisioning
runs through `builder agent runtime managed-agents setup`; lifecycle follow-up
arrives via `/api/managed-agents/webhook` and is deduped through the
`webhook_deliveries` table.

Telemetry keys managed with runtime selection:

- `AAB_CLAUDE_OTEL_ENABLED`
- `AAB_CLAUDE_OTEL_ENDPOINT`
- `AAB_CLAUDE_OTEL_SERVICE_NAME`
- `AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID`
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
- Claude access is **Claude runtime-backed**. Claude-specific prompt, project
  setting, permission, MCP, hook, and OneCLI behavior applies only to
  `RUNTIME_SDK=claude`.

The settings UI should show one selected harness and the probe result for that
harness. It should not ask for OpenAI API settings when `codex_sdk` is selected,
and it should not show Claude OTEL as the selected runtime telemetry when the
Codex SDK harness is active. Observability may still show a
non-selected runtime's native telemetry as `ok` when it is independently
configured and reachable, or `inactive` when it is intentionally not part of the
current selected runtime state.

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
- `observability.reasoning_output_tokens`
- `observability.telemetry_source`
- `observability.cost_source`

`codex_sdk` uses `observability.protocol=codex_app_server_jsonrpc` and
`observability.telemetry_source=codex_app_server_events`. Native app-server
user-input requests must surface as Agent-page question cards and record
`observability.request_user_input_count`.

Codex OTEL configuration is project-local. When a Codex runtime is selected,
builder may create or validate `.codex/config.toml` with a `[otel]` exporter
that points at the same collector endpoint used by Claude. This native Codex
OTEL lane is parallel evidence; it must not replace active-DB run evidence or
pretend Codex and Claude emit the same native telemetry schema.

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
builder logs analyze --json
PYTHONPATH=src pytest tests/test_runtime_interface.py tests/test_codex_app_server_runtime.py tests/test_onboarding_runtime_selection.py tests/test_execution_policy.py -q
```
