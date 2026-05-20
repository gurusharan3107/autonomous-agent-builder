---
title: "Claude Agent SDK Telemetry and Observability"
tags: ["claude", "agent-sdk", "telemetry", "observability", "opentelemetry"]
doc_type: "documentation"
created: "2026-04-26"
---

# Claude Agent SDK Telemetry and Observability

Canonical repo-local reference for how `autonomous-agent-builder` should use
Claude Agent SDK telemetry and observability.

Use this doc as the owner surface when changing:

- OpenTelemetry environment configuration for Claude child processes
- the split between builder-local session history and OTEL-exported signals
- which telemetry signals are considered high-signal for builder tuning
- sensitive-data export policy
- observability-related best practices and anti-patterns
- how runtime telemetry feeds agent-quality tuning and optimization analysis
- the cross-runtime telemetry-health contract shown by the Observability page
- project-root scoping for the Observability dashboard API

For broader Claude runtime integration and ownership boundaries, see
[claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md).

For how reduced signals should feed tuning recommendations, see
[agent-optimization-analysis.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/agent-optimization-analysis.md).

For the end-to-end telemetry analysis loop across builder logs, metrics, voice
events, app workspaces, and Codex transcript productivity signals, see
[autonomous-builder-telemetry-analysis.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/autonomous-builder-telemetry-analysis.md).

## Purpose

This repo should use telemetry to improve builder quality and context
efficiency without turning observability into a second transcript store.

The target outcome is:

- strong runtime visibility
- low user burden
- bounded high-signal analysis
- explicit privacy discipline
- clear owner boundaries between builder-local state and external observability

That aligns with [MISSION.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/MISSION.md):
the builder should choose workflow, model, tools, and execution strategy for
the user, while leaving behind durable and inspectable state.

## Core Model

Claude Agent SDK does not emit telemetry independently of Claude Code CLI.

The SDK launches Claude Code as a child process. The CLI is the process that
emits traces, metrics, and log events when telemetry is enabled. The SDK
passes configuration through the environment.

Implication for this repo:

- builder owns repo-local session history, interpretation, and tuning policy
- Claude Agent SDK owns runtime execution and telemetry mechanics
- OTEL backend owns structural aggregation and cross-run visibility

## Recommended Architecture

Use a hybrid split.

### Builder-local history is the source of truth for output review

Keep these in builder-local history and retrieval surfaces such as:

- `builder agent sessions --json`
- `builder agent history --session <id> --json`
- `builder logs analyze --session <id-or-prefix> --json`

Builder-local history should remain the source of truth for:

- full prompts when intentionally persisted
- assistant outputs
- tool I/O and tool timeline details
- approval decisions and blocked reasons
- context windows and repo-specific execution context
- user-facing debugging and output-quality review

### OTEL should carry structural telemetry

Use OTEL for cross-run structural signals such as:

- interaction spans
- LLM request spans
- tool spans
- timing and latency
- token and cost metrics
- tool-decision metrics or events
- model-choice and approval-source events
- session correlation

Do not treat OTEL as the primary store for rich conversation review.

### Cross-runtime collector policy

Claude and Codex may export runtime-native telemetry to the same OTEL collector,
but builder must not force both runtimes into the same native event schema.
Claude keeps Claude Code / Claude Agent SDK event names. Codex keeps Codex
`[otel]` event names. Builder-owned normalized telemetry in the active DB remains
the product source of truth for Board, Metrics, Observability,
`builder logs analyze`, and deterministic recommendations.

Metrics projections must keep dashboard refreshes bounded on long-lived
projects. Use aggregate DB queries for all-time totals such as run count, token
count, cost, and gate pass rate, and fetch only a bounded recent window for
displayed run rows, optimization hints, voice ledger events, and todo snapshots.
When metrics cannot load project-scoped observability evidence, they must return
an explicit degraded payload instead of empty optimization, runtime-decision, or
context-budget fields.

### Dashboard telemetry-health contract

The Observability page and `/api/dashboard/observability` should expose one
`observability_coverage.telemetry_health` object with three areas:

- `claude_native`: Claude OTEL env, configured exporters, signal support,
  sensitive-data flags, and collector reachability
- `codex_native`: project-local Codex `[otel]` config presence, exporter type,
  endpoint, collector reachability, emitted signal support, trace metadata,
  feedback, analytics, and config path
- `builder_product`: active-DB completeness for project, feature, task, run,
  phase, gate, approval, runtime, model, tool, cost, failure, retry, artifact,
  and PR facts

The selected runtime is reported separately from native telemetry health. Only
the selected runtime can report current native telemetry emission as `enabled`,
`reachable`, or `emitting`. A non-selected runtime may still expose config
readiness facts such as saved exporter settings or trace metadata, but its
current emission status must be `inactive` because that lane is not producing
new runtime telemetry. Historical telemetry from that lane remains queryable
through builder logs, metrics, session analysis, run records, and voice ledgers.
User-facing copy must avoid vague states such as `collector unknown` when the
real state is configured, reachable, unreachable, missing, inactive, or not
checked.

The endpoint must resolve its database from the FastAPI app's configured
project root, not from the server process cwd. `builder start` is commonly run
from the source checkout while serving a generated app's `.agent-builder`
directory; in that mode `/observability` still needs to render the generated
app's telemetry instead of returning the source-repo guardrail error.

### Recommendations contract

Metrics and Observability share one optimization decision model:

- Metrics owns scores, run totals, gate pass rate, cost/token aggregates,
  large-output/chunk-pressure aggregates, benchmark status, top cost drivers,
  and the primary next optimization action.
- Observability owns diagnostic coverage, runtime-native telemetry health,
  builder-product telemetry health, capability gaps, phase routing evidence, and
  deterministic recommendations. When large-output or app-server chunk-pressure
  flags exist, Observability should treat aggregate `chunk_pressure` as a
  first-class coverage signal rather than reporting it missing after per-run
  event accounting has been persisted. Recommendation rows must carry
  machine-readable routing fields so Builder fixes and App recommendations can
  be separated without repeating implementation ownership language in the
  dashboard.

The Observability page should render a single user-facing `Recommendations`
panel with tabs for `Builder`, `App`, and `Rejected`. `Builder` is the product
fix queue. `App` is the managed-repo queue handed to the optimization agent,
including items the optimization agent can reject. Deterministic rule-backed
recommendations belong in that panel, not in a second parallel recommendations
section. Runtime Decisions may explain the evidence behind the queue, but must
not render the same script-candidate actions again. The JSON surface remains
machine-friendly via:

- top-level `deterministic_recommendations`
- `observability_coverage.deterministic_recommendations`
- `builder logs analyze --session <id-or-prefix> --json` fields `runtime_native_telemetry_health`,
  `builder_product_telemetry_health`, `telemetry_health`, and
  `deterministic_recommendations`
- deterministic script candidates include `owner_lane`, `next_actor`, and
  `handoff` guidance in Metrics, Observability, and compact logs

## High-Signal Default Policy

The default telemetry policy for this repo should optimize for tuning value per
token and per privacy risk.

### High-signal signals to keep

- `session.id`
- model name
- per-request latency
- input tokens
- output tokens
- cache creation input tokens
- cache read input tokens
- cost estimate
- result subtype and stop reason
- `max_turns` / `max_budget_usd` stops
- tool name
- tool duration
- tool success or failure
- tool decision or approval source
- `AskUserQuestion` requests and answers
- interaction duration
- delegation or subagent usage when visible through builder-local history
- compaction boundary events when emitted by the SDK
- correlation back to builder session ids and prompt-level analysis

### Signals to avoid exporting by default

Do not export raw content by default:

- user prompt bodies
- tool input arguments
- tool output bodies
- raw Anthropic Messages API request or response bodies

These should remain local unless a narrowly approved debugging case requires
them.

### Claude Agent SDK context and cost policy

The Claude Agent SDK agent loop should remain the owner of tool-choice mechanics
for `sdk=claude` turns. Builder should optimize this lane by shaping context and
observability, not by converting judgment prompts into deterministic shortcuts.

Official SDK guidance to preserve in Builder behavior:

- The loop accumulates system prompt, tool definitions, conversation history,
  tool inputs, and tool outputs across a session. Large tool outputs and long
  sessions increase context pressure even when stable content is prompt-cached.
- Persistent project rules belong in `CLAUDE.md` / project settings loaded via
  `setting_sources=["project"]`; one-off prompts are a weaker place for durable
  rules and may be summarized during compaction.
- The SDK automatically compacts near the context limit and emits a
  `compact_boundary` system message. Compaction can summarize away older detail,
  so Builder evidence should preserve completed actions, file paths, decisions,
  test results, blockers, and next goals outside raw transcript replay.
- Track `cache_creation_input_tokens` and `cache_read_input_tokens` separately
  from input/output tokens. The SDK's `total_cost_usd` is a local estimate and
  should be treated as tuning evidence, not authoritative billing.
- For large MCP/custom tool catalogs, use tool search or smaller tool surfaces;
  for small focused tool sets, direct loading may be simpler and faster.
- For interactive products, use permission callbacks, approval cards, and
  `AskUserQuestion` to surface necessary choices. Use hooks for deterministic
  safety policy and post-tool feedback, not as a replacement for model-backed
  intent understanding.
- Export structural OTEL by default: model/tool spans, token and cost metrics,
  timing, failures, and permission decisions. Do not enable raw prompt, tool
  argument, full tool-output, or raw API body export as a default product mode.

### Large-output retention

Codex app-server command output is allowed to remain local Builder evidence, but
it must not become default model context again after a run. When a Codex runtime
event carries large command output, Builder stores the full event under
`.agent-builder/runtime-artifacts/codex-app-server/`, returns only compact
previews to Builder run evidence, and marks `context_retention.resume_recommended`
as `false` for that SDK session. The optimization summary for that run scores
the compacted reinjection event stream, not the raw artifact body; the original
size remains visible through `large_output_artifacts` and
`tool_output_reinjection.largest_original_command_output_bytes`. The next Agent
page turn should start a fresh Codex app-server thread and rely on Builder's
compact chat context, logs, metrics, and artifact pointer rather than resuming
full app-server history. Metrics can keep lifetime large-output counts for audit
history, but active next-action recommendations and deterministic script
candidates must use the compacted/recent signal so pre-fix runs do not keep the
operator pinned to stale truncation work.

### Codex app-server turn.error handling

When the Codex app-server returns a `turn.error` alongside a non-empty
`final_output`, the runtime checks whether the error text duplicates the streamed
answer via `_turn_error_duplicates_output`. This handles the case where a
successful Samantha-delegated answer is mistakenly echoed as a `turn.error`
event. When the duplication check passes, the run is returned as
`completed_with_turn_error_text` with `ignored_turn_error: true` in
observability rather than as a failure. A real `turn.error` that does not
duplicate the output is still surfaced as an error result.

### Codex app-server chunk-limit retry

When the Codex app-server runtime retries after a chunk-limit failure
(`attempt > 0`), it passes `session=None` to `_run_once` so the SDK starts a
fresh app-server thread rather than resuming the bloated thread that caused the
transport failure. Resuming the same thread would replay the oversized context
and reproduce the failure. The fresh thread receives compact Builder context
instead of the full prior history.

## Minimal Recommended OTEL Environment

Use OTLP export and enable all three signals, while keeping content-export
flags off by default.

```python
OTEL_ENV = {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
    "OTEL_TRACES_EXPORTER": "otlp",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
    "OTEL_METRIC_EXPORT_INTERVAL": "2000",
    "OTEL_LOGS_EXPORT_INTERVAL": "1000",
    "OTEL_TRACES_EXPORT_INTERVAL": "1000",
    "OTEL_SERVICE_NAME": "autonomous-agent-builder",
    "OTEL_RESOURCE_ATTRIBUTES": (
        "service.version=0.1.0,deployment.environment=local,"
        "builder.runtime=claude_agent_sdk,"
        "builder.goal=voice_first_delivery_os"
    ),
    "OTEL_METRICS_INCLUDE_SESSION_ID": "true",
    "ENABLE_BETA_TRACING_DETAILED": "1",
    "BETA_TRACING_ENDPOINT": "http://localhost:4318",
}
```

Recommended defaults:

- keep short export intervals for short-lived builder tasks
- set `OTEL_SERVICE_NAME` explicitly
- attach resource attributes for environment and version
- attach builder-specific resource attributes for runtime, project, and goal
- keep `session.id` available for correlation
- enable detailed beta tracing for Agent SDK runs while keeping prompt and tool
  body export flags off by default
- use a real OTLP collector endpoint; builder diagnostics should treat copied
  placeholders like `http://your-collector:4318` as not ready
- for loopback endpoints such as `http://localhost:4318`, distinguish
  configured from reachable; configuration alone is not usable exported telemetry

### Local memory-light collector

For local validation, run the repo-owned collector profile:

```bash
scripts/start_local_otel_collector.sh
```

This starts the pinned official collector image
`ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector:0.150.1`
with:

- OTLP HTTP on `127.0.0.1:4318`
- a `128M` memory cap and one CPU by default
- `memory_limiter` before `batch` in every pipeline
- `debug` export at basic verbosity for proof without local storage

The launcher prefers Apple's `container` CLI when available and falls back to
Docker or Podman. Override defaults with:

```bash
AAB_OTEL_COLLECTOR_MEMORY=256M \
AAB_OTEL_COLLECTOR_PORT=4318 \
AAB_OTEL_COLLECTOR_IMAGE=ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector:0.150.1 \
scripts/start_local_otel_collector.sh
```

## Signals This Setup Should Provide

Without exporting raw transcripts, the target setup should give:

### Traces

- `claude_code.interaction`
- `claude_code.llm_request`
- `claude_code.tool`

These should support:

- model choice review
- latency review
- tool duration review
- failure localization
- parent-child correlation across the agent loop

### Metrics

Expect metrics such as:

- token usage
- cost usage
- tool decision counts

These should support:

- cheap-vs-expensive lane analysis
- per-workflow cost baselining
- regression detection when tool churn increases

### Log events

Use events for:

- model choice
- approval or decision source
- tool success or failure
- request duration or cost summaries

## Best Practices

### Keep builder-local and OTEL roles distinct

- builder-local history is for qualitative review and product-state debugging
- OTEL is for structural telemetry, timing, aggregation, and correlation

### Tune from reduced signals first

Treat builder-local evidence plus structural OTEL as the foundation for agent
optimization. The product should infer when to use a stronger model, lower
effort, a specialist tool, or a narrower context lane; the user should only need
to express product intent.

Use:

- `builder logs analyze --session <id-or-prefix> --json`
- builder session history
- bounded OTEL spans and metrics

before changing prompts, model policy, tool contracts, phase boundaries, or
asking for richer content export.

For dispatch-only continuation turns, builder-local analysis should expose the
terminal chat-turn status and dispatch correlation without requiring transcript
export. A successful auto-dispatch should appear as `stop_reason=task_dispatched`
with the correlated task id/status in `builder logs analyze`.

### Keep content export opt-in and narrow

Only enable content-heavy flags for a narrow, explicit debugging case:

- `OTEL_LOG_USER_PROMPTS`
- `OTEL_LOG_TOOL_DETAILS`
- `OTEL_LOG_TOOL_CONTENT`
- `OTEL_LOG_RAW_API_BODIES`

Turn them back off after the debugging window closes.

### Keep service identity stable

Use a stable `OTEL_SERVICE_NAME` and resource attributes so builder telemetry
is easy to separate from unrelated services.

### Prefer repo-owned analysis surfaces

Builder should remain the first diagnostic surface for:

- prompt-by-prompt review
- context-efficiency interpretation
- repo-specific output-quality analysis

OTEL should strengthen this lane, not replace it.

### Use telemetry to improve builder-owned surfaces

Telemetry findings should map back to concrete repo-owned changes such as:

- prompt shaping
- model selection rules
- tool allowlists
- phase permissions
- subagent boundaries
- KB or doc placement
- builder log summaries

### Use the Claude docs assistant only as a docs-advisory companion

For Claude-Agent-SDK-specific questions, the Claude docs assistant can be a
useful bounded advisory lane when:

- the question is about SDK usage patterns
- the answer is tied to an exact docs page or section
- the result is treated as official-doc interpretation, not repo-runtime proof

Good use cases:

- permission mode selection
- session semantics clarification
- subagent or hook pattern fit
- telemetry and observability setup questions

The assistant should strengthen repo workflow by accelerating doc retrieval and
interpretation. It should not replace builder-local evidence, code inspection,
or testing.

## Anti-Patterns

### Using OTEL as a transcript warehouse

This adds privacy risk and retrieval noise while duplicating builder-local
history.

### Exporting raw content by default

Do not enable prompt, tool-body, or raw API-body export as the standard mode.

### Tuning from traces alone

Traces can show timing and structure, but not the full product-state context.
Use builder-local history as the paired evidence lane.

### Using the docs assistant as implementation truth

The Claude docs assistant cannot see this repo's code, runtime state, or test
results. Do not accept it as proof that the current builder implementation is
correct.

If the question is "what does our builder actually do?" or "is our
implementation correct?", the next step is repo evidence, not another docs
assistant question.

### Ignoring observability gaps

If spans, metrics, or events are missing, report that explicitly instead of
pretending the tuning recommendation is complete.

### Over-collecting low-signal data

If a signal does not change a concrete builder decision, it should not be a
default export candidate.

### Blurring product and runtime ownership

Do not move backlog, approval, KB, memory, or tuning semantics into the SDK or
observability backend.

## Validation Checklist

Before calling telemetry setup complete, verify:

- `CLAUDE_CODE_ENABLE_TELEMETRY=1` is effective in the runtime that launches Claude
- traces, metrics, and logs exporters are all configured intentionally
- export intervals are short enough for short-lived builder tasks
- `OTEL_SERVICE_NAME` and resource attributes are set
- a configured local collector endpoint is reachable, not only present in `.env`
- content-export flags remain off unless explicitly approved
- `builder logs analyze` still reports builder-local history as the primary repo
  review surface
- `builder logs analyze --session <id-or-prefix> --json` reports selected runtime, runtime-native
  telemetry health, builder-product telemetry health, and deterministic
  recommendation codes with evidence
- the Observability page has one `Recommendations` panel, with rule-backed
  recommendations under the same tabbed surface as optimization, phase, and
  script recommendations
- each open recommendation appears under the `Builder`, `App`, or `Rejected`
  tab without repeating internal owner labels in every card
- Runtime Decisions shows supporting evidence only and does not repeat the
  action cards from Recommendations
- dispatch-only chat turns show `task_dispatched` terminal evidence and the
  correlated task id/status in builder-local analysis
- Codex runs with large command output persist a local runtime artifact, expose
  compact event previews, record `tool_output_reinjection.policy:
  truncate_tool_output_before_reinjection`, avoid resuming the full SDK thread
  on the next Agent page turn, and no longer score the compacted run as active
  `large_command_output` reinjection debt
- a real session shows usable structural telemetry in the chosen OTEL backend

## Current Repo Recommendation

For `autonomous-agent-builder` specifically:

- keep builder-local history as the source of truth for output review and
  quality tuning
- keep large Codex command output local as runtime artifacts and feed future
  turns compact Builder context plus artifact pointers, not full app-server
  history
- enable OTEL for structural telemetry only
- keep content export disabled by default
- use telemetry to tune builder-owned product surfaces rather than to create a
  second analytics persona

## Related Docs

- [MISSION.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/MISSION.md)
- [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
- [agent-optimization-analysis.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/agent-optimization-analysis.md)
- [agent-quality.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/agent-quality.md)
- [agent-quality-tuning-loop.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/agent-quality-tuning-loop.md)
