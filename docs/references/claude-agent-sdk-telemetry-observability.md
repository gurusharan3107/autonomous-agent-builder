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

For broader Claude runtime integration and ownership boundaries, see
[claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md).

For how reduced signals should feed tuning recommendations, see
[agent-optimization-analysis.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/agent-optimization-analysis.md).

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

### Dashboard telemetry-health contract

The Observability page and `/api/dashboard/observability` should expose one
`observability_coverage.telemetry_health` object with three areas:

- `claude_native`: Claude OTEL env, configured exporters, signal support,
  sensitive-data flags, and collector reachability
- `codex_native`: project-local Codex `[otel]` config presence, exporter type,
  endpoint, collector reachability, emitted signal support, and config path
- `builder_product`: active-DB completeness for project, feature, task, run,
  phase, gate, approval, runtime, model, tool, cost, failure, retry, artifact,
  and PR facts

The selected runtime is reported separately from native telemetry health. A
non-selected runtime can still be `ok` if it has valid telemetry configuration
and a reachable collector. A runtime can also be `inactive` when it is not the
selected execution lane and has no active telemetry evidence. User-facing copy
must avoid vague states such as `collector unknown` when the real state is
configured, reachable, unreachable, missing, inactive, or not checked.

### Recommendations contract

Metrics and Observability share one optimization decision model:

- Metrics owns scores, run totals, gate pass rate, cost/token aggregates,
  benchmark status, top cost drivers, and the primary next optimization action.
- Observability owns diagnostic coverage, runtime-native telemetry health,
  builder-product telemetry health, capability gaps, phase routing evidence, and
  deterministic recommendations.

The Observability page should render a single user-facing `Recommendations`
panel with tabs for `All`, `Optimization`, `Phase`, `Scripts`, and `Rules`.
Deterministic rule-backed recommendations belong in that panel, not in a second
parallel recommendations section. The JSON surface remains machine-friendly via:

- top-level `deterministic_recommendations`
- `observability_coverage.deterministic_recommendations`
- `builder logs analyze --json` fields `runtime_native_telemetry_health`,
  `builder_product_telemetry_health`, `telemetry_health`, and
  `deterministic_recommendations`

## High-Signal Default Policy

The default telemetry policy for this repo should optimize for tuning value per
token and per privacy risk.

### High-signal signals to keep

- `session.id`
- model name
- per-request latency
- token counts
- cost
- tool name
- tool duration
- tool success or failure
- tool decision or approval source
- interaction duration
- delegation or subagent usage when visible through builder-local history
- correlation back to builder session ids and prompt-level analysis

### Signals to avoid exporting by default

Do not export raw content by default:
- user prompt bodies
- tool input arguments
- tool output bodies
- raw Anthropic Messages API request or response bodies

These should remain local unless a narrowly approved debugging case requires
them.

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
        "service.version=1.0,deployment.environment=production"
    ),
    "OTEL_METRICS_INCLUDE_SESSION_ID": "true",
}
```

Recommended defaults:
- keep short export intervals for short-lived builder tasks
- set `OTEL_SERVICE_NAME` explicitly
- attach resource attributes for environment and version
- keep `session.id` available for correlation
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
- `builder logs analyze --json` reports selected runtime, runtime-native
  telemetry health, builder-product telemetry health, and deterministic
  recommendation codes with evidence
- the Observability page has one `Recommendations` panel, with rule-backed
  recommendations under the same tabbed surface as optimization, phase, and
  script recommendations
- dispatch-only chat turns show `task_dispatched` terminal evidence and the
  correlated task id/status in builder-local analysis
- a real session shows usable structural telemetry in the chosen OTEL backend

## Current Repo Recommendation

For `autonomous-agent-builder` specifically:

- keep builder-local history as the source of truth for output review and
  quality tuning
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
