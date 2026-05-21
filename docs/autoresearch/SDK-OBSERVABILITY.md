# SDK Observability

> **Read [README.md](README.md) and [METRICS.md](METRICS.md) first.**

This file is the precise prescription for enabling Claude Agent SDK and Codex SDK native telemetry during each autoresearch loop iteration. Builder CLI evidence covers the headline metrics; SDK-native telemetry covers the diagnostics Builder doesn't surface yet.

Source documentation:
- Claude Agent SDK Observability — https://code.claude.com/docs/en/agent-sdk/observability
- Claude Agent SDK Python — https://code.claude.com/docs/en/agent-sdk/python
- Claude Code Monitoring (full env-var reference) — https://code.claude.com/docs/en/monitoring-usage

## How Claude Agent SDK telemetry works

The Claude Agent SDK runs the Claude Code CLI as a child process. The CLI has OpenTelemetry instrumentation built in and exports three independent signals: **metrics**, **log events**, and **traces (beta)**. Each signal has its own enable switch and its own OTLP exporter. The SDK passes telemetry configuration through to the CLI via the child process environment — there is no SDK-level instrumentation; everything happens in the CLI subprocess.

This is critical for the loop because:

1. **The SDK's OTEL surface is the most complete view of what the model saw and did.** Per-turn cache split, per-tool latency, per-hook timing, raw prompt and response bodies — all available with the right env vars.
2. **No source-code change to Builder is needed** to start capturing it. Builder spawns the SDK; if the SDK's environment has the right OTEL vars, the CLI exports without Builder touching anything.
3. **It is the ground truth.** Builder's `prompt_summaries` and `context_budget` are derived estimates; the OTEL `claude_code.api_request_body` event is what Anthropic actually saw.

## Recommended loop setup

Each loop iteration should run with this environment, configured per-run so the per-run evidence is isolated:

```bash
RUN_ID="$(uuidgen)"
EVIDENCE_DIR="/tmp/autoresearch/${RUN_ID}"
mkdir -p "$EVIDENCE_DIR/otel" "$EVIDENCE_DIR/raw_bodies"

# Enable telemetry
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1
export ENABLE_BETA_TRACING_DETAILED=1     # needed for hook spans

# All three signals to local OTLP collector (Jaeger all-in-one is easiest)
export OTEL_TRACES_EXPORTER=otlp
export OTEL_METRICS_EXPORTER=otlp
export OTEL_LOGS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318

# Aggressive flush so short turns export before they end
export OTEL_METRIC_EXPORT_INTERVAL=1000
export OTEL_LOGS_EXPORT_INTERVAL=1000
export OTEL_TRACES_EXPORT_INTERVAL=1000

# Service tagging so we can filter this run in the collector
export OTEL_SERVICE_NAME="autoresearch-${RUN_ID}"
export OTEL_RESOURCE_ATTRIBUTES="run.id=${RUN_ID},fixture.id=${FIXTURE_ID},branch=${BRANCH},autoresearch.iteration=true"

# Content capture — REQUIRED for context ledger Path A
export OTEL_LOG_USER_PROMPTS=1
export OTEL_LOG_TOOL_DETAILS=1
export OTEL_LOG_TOOL_CONTENT=1
export OTEL_LOG_RAW_API_BODIES=file:${EVIDENCE_DIR}/raw_bodies

# Now start builder in this environment so the SDK child inherits it
builder start --port "${PORT}" --force &
```

After the fixture run completes:

```bash
# Stop builder, flush remaining OTEL batches
builder server stop --port "${PORT}"
sleep 3   # give exporters their final flush window

# Capture Builder-side evidence
builder logs analyze --session "${SESSION_ID}" --full --json > "${EVIDENCE_DIR}/analyze.json"
builder metrics show --json --full > "${EVIDENCE_DIR}/metrics.json"
builder board show --json > "${EVIDENCE_DIR}/board.json"

# Capture SDK-side evidence (raw bodies are already on disk in $EVIDENCE_DIR/raw_bodies)
# Pull traces/metrics/logs from the OTLP collector that was running locally:
curl -s "http://127.0.0.1:16686/api/traces?service=autoresearch-${RUN_ID}" \
  > "${EVIDENCE_DIR}/otel/traces.json"
```

The Jaeger all-in-one image (`jaegertracing/all-in-one`) is the simplest local OTLP endpoint that accepts traces; for logs/metrics, point at any OTLP collector you trust (a local `otel-collector-contrib` works fine and writes to disk).

> **Critical:** Do **not** set `OTEL_EXPORTER_OTLP_ENDPOINT` to `console`. The Claude Code CLI uses stdout as its SDK message channel; `console` exporter writes telemetry there and breaks the SDK pipe. Always point at a local OTLP endpoint.

## What each signal gives you

| Signal | Useful for | TSV column it feeds |
| --- | --- | --- |
| `claude_code.interaction` span | True wall-clock per agent turn, parent for all child spans. | `per_prompt_results.tsv.duration_ms` (validation against `agent_run_evidence.duration_ms`) |
| `claude_code.llm_request` span (attrs: model, latency, token counts) | Per-API-call latency and token counts; surfaces retries. | Diagnostic only; aggregated as `top_cost_drivers` already. |
| `claude_code.tool` + `.tool.execution` + `.tool.blocked_on_user` spans | Per-tool latency split between "waiting for permission" and "actually running". A long `blocked_on_user` means the approval card sat unanswered; a long `execution` means the tool is slow. | Diagnostic only. |
| `claude_code.hook` span | Per-hook timing. Reveals whether a hook is silently growing turn duration. | Diagnostic only. |
| `claude_code.user_prompt` log event | Prompt text. Lets us verify the harness sent the fixture prompt verbatim. | Sanity check, not TSV. |
| `claude_code.tool_result` log event | Tool inputs and (optionally) outputs. | Diagnostic for tool-output bloat. |
| `claude_code.api_request_body` / `claude_code.api_response_body` log events | **The full prompt sent to Anthropic and the full response.** Cache breakpoints visible. This is the ground truth for context ledger Path A. | `per_prompt_results.tsv.context_breakdown_json` (parsed from these). |
| `claude_code.cost.usd` metric | Counter for cost. Useful for cross-validating Builder's `cost_usd`. | Diagnostic; Builder already aggregates. |
| `claude_code.token.usage` metric | Counter per token type (input / output / cache_read / cache_creation). The `cache_creation` split is **missing from Builder analyze today** (see [METRICS.md gap table](METRICS.md#what-we-are-not-capturing-and-why-it-matters)). | `per_prompt_results.tsv.cache_creation_tokens` |
| `claude_code.tool_decision` metric | Counter of allow/deny decisions per tool. | Diagnostic. |
| `RateLimitEvent` (in-process SDK message, not OTEL) | Per-event rate-limit utilization. | Captured by harness from chat stream; written to a side file `${EVIDENCE_DIR}/rate_limits.jsonl`. |

## Codex SDK parity

The Codex SDK lane has different native telemetry. It does not use the Claude Agent SDK's OTEL surface; instead Builder persists Codex app-server events and turn telemetry directly. The harness must capture per-lane evidence separately and normalize for comparison.

For Codex runs:
- Set `RUNTIME_SDK=codex_sdk` via `builder agent runtime set --sdk codex_sdk --provider codex_subscription --json`.
- Do **not** set Claude OTEL env vars for Codex runs; they have no effect.
- Capture Codex telemetry from `builder logs analyze --session <id> --full --json`. The `agent_run_evidence[*]` rows for Codex runs include Codex-specific fields (token, turn, duration, provider-limit, native-user-input, telemetry-source).
- The Codex equivalent of `cache_creation` is reported through Builder's existing `tokens_cached` plus the `large_command_output` flag for chunk pressure. The cache-creation distinction does not apply identically — Codex caching semantics differ.
- The harness writes both lanes' rows into the same TSV with `runtime_sdk` as the discriminator column. Comparisons across lanes must group by `runtime_sdk` first.

## How the SDK env vars interact with Builder source

Builder spawns Claude SDK and Codex SDK child processes via `agents/execution_policy.py` and `runtime/codex_app_server_runtime.py`. The current source passes through OneCLI-derived environment for auth (see [docs/claude-agent-sdk-integration.md](../claude-agent-sdk-integration.md)) but does not actively strip OTEL env vars. So:

- Variables exported in the shell **before** `builder start` propagate to the Claude SDK subprocess on every run. No source change needed.
- For tighter control (per-turn or per-agent OTEL settings) Builder would need to pass them explicitly through `ClaudeAgentOptions.env`. That is **future work** ([GAPS.md G-6](GAPS.md)) — not required for v1.

## How to validate the setup

Before running the first real baseline, smoke-test that telemetry actually flows:

```bash
# 1. Start a local OTLP receiver. The trivial sink for smoke-testing is a stdout collector.
docker run --rm -p 4318:4318 otel/opentelemetry-collector-contrib --config /etc/otelcol-contrib/config-default.yaml

# 2. Export the OTEL env from "Recommended loop setup" above.

# 3. Run any one-shot SDK call:
python3 -c "
from claude_agent_sdk import query, ClaudeAgentOptions
import asyncio, os
async def main():
  async for m in query(prompt='Say hello', options=ClaudeAgentOptions(env=dict(os.environ))):
    print(m)
asyncio.run(main())
"

# 4. Confirm the collector logged at least one span named claude_code.interaction
#    and at least one metric named claude_code.token.usage.

# 5. Confirm $EVIDENCE_DIR/raw_bodies/ contains at least one api_request_body file.
```

If any of those three signals is missing, fix the env or collector before running the loop — otherwise the harness will write TSV rows with empty `context_breakdown_json`.

## What this enables vs what Builder CLI alone enables

| Capability | Builder CLI alone | With SDK OTEL enabled |
| --- | --- | --- |
| Total tokens per session | ✓ | ✓ |
| Per-prompt tokens and cache ratio | ✓ | ✓ |
| Cost per run | ✓ (estimated) | ✓ (estimated, plus per-model split) |
| Tool-call list per turn | ✓ | ✓ |
| Per-tool wall-clock latency | partial (duration_ms per agent run only) | **per tool, including blocked-on-user split** |
| Cache *creation* vs *read* split | ✗ | **✓ via `claude_code.token.usage` metric** |
| Full prompt body sent to Anthropic | ✗ | **✓ via `OTEL_LOG_RAW_API_BODIES=file:...`** |
| Cache breakpoint positions in the prompt | ✗ | **✓ visible in raw bodies** |
| Per-hook execution timing | ✗ | **✓ via `claude_code.hook` spans** |
| Rate-limit utilization trajectory | partial (resets_at only) | **✓ via `RateLimitEvent.utilization`** |
| Per-model usage when multi-model | ✗ | **✓ via `ResultMessage.model_usage`** |
| Tool-decision counter (allows vs denies) | ✗ | **✓ via `claude_code.tool_decision` metric** |
| MCP server status snapshot | ✗ | **✓ via `get_mcp_status()` SDK call (not OTEL, but SDK-native)** |

Five of these are the missing-but-unlocked-by-OTEL signals that turn the loop from "we saw the cost go down but not why" into "we saw the cost go down because cache reads grew and cache creation dropped on turn 3, where the board-state block was removed." That diagnostic resolution is what makes the loop converge.

## Cost and content-disclosure caveats

`OTEL_LOG_RAW_API_BODIES=file:<dir>` writes full request and response JSON to disk per turn, including the full conversation history (with extended-thinking content redacted). That:

- Generates a lot of files. Plan disk: a 25-min ship-cycle generates ~100 MB of raw bodies. Rotate `$EVIDENCE_DIR` per run, archive or delete after analysis.
- Includes operator-provided text (the fixture prompts) and tool outputs verbatim. The autoresearch fixtures are scripted and contain no sensitive data, so this is fine. If the loop is ever pointed at a fixture that contains secrets, this var must be turned off (or `=1` for inline-truncated instead of `=file:...`).
- Subsumes `OTEL_LOG_USER_PROMPTS=1` and `OTEL_LOG_TOOL_DETAILS=1` — those vars become redundant when raw bodies are on. The recommended setup leaves them on for backstop in case the raw-body capture is misconfigured.

## When to skip parts of this setup

| Phase | OTEL config |
| --- | --- |
| Smoke-testing the harness (no actual optimization) | Skip OTEL entirely; Builder CLI alone is enough. |
| Baseline variance measurement (N=5 per fixture) | Enable metrics + logs (no traces, no raw bodies). Cheap, complete enough for σ. |
| Optimization iteration (every loop step) | Enable all three signals + raw bodies. Diagnostic resolution matters most here. |
| Promotion validation (ship-cycle 25-min) | Same as iteration. |
| Quarterly Tier 3 head-to-head benchmarks | All signals on; archive `${EVIDENCE_DIR}` permanently as the comparison record. |

## Related

- [METRICS.md](METRICS.md) for the full per-column source mapping.
- [CONTEXT-LEDGER.md](CONTEXT-LEDGER.md) for how to turn raw-body capture into per-source attribution.
- [HARNESS.md](HARNESS.md) for where in the runner this configuration is applied.
- [GAPS.md](GAPS.md) for the source-change items (Codex parity telemetry, per-agent OTEL via `ClaudeAgentOptions.env`).
