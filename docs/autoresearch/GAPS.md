# Gaps — What Source Changes Would Improve The Loop

> **Read [README.md](README.md), [METRICS.md](METRICS.md), [SDK-OBSERVABILITY.md](SDK-OBSERVABILITY.md), and [HARNESS.md](HARNESS.md) first.**

This file is the honest list of Builder source changes that would simplify or improve the autoresearch loop. The framework as specified is **runnable today against the current source** (per [HARNESS.md](HARNESS.md)) — these are improvements, not blockers.

Each gap has: what it is, why it matters, scope of source change, effort estimate, and whether it's needed for v1 (must have to run the loop), v2 (improves diagnostic resolution), or v3 (operational polish).

When a gap closes, also update [METRICS.md](METRICS.md) (which TSV column gets richer) and remove the gap row from this file.

## Summary table

| Gap | Tier | What it gives | Source change cost |
| --- | --- | --- | --- |
| [G-1](#g-1--mcp-server-status-snapshot-via-builder-cli) | v2 | Visibility into MCP server failures that cause silent tool denials | Small |
| [G-2](#g-2--promptblockledger-instrumentation-context-ledger-path-b) | v2 | Structured per-block context attribution (replaces OTEL raw-body parsing) | Medium |
| [G-3](#g-3--cache-creation-vs-cache-read-split-in-builder-analyze) | v2 | Distinguishes cache writes from cache reads (cache churn detection) | Small |
| [G-4](#g-4--per-model-usage-breakdown-in-builder-analyze) | v2 | Per-model cost when multi-model routing is in play | Small |
| [G-5](#g-5--hook-execution-timeline-in-builder-analyze) | v3 | Per-hook timing surfaces silent runtime growth | Medium |
| [G-6](#g-6--per-agent-otel-env-via-claudeagentoptions-env) | v3 | Fine-grained OTEL control without machine-wide env | Small |
| [G-7](#g-7--autonomous-agent-edit-step-in-loop) | v3 | Removes the human-in-the-loop step | Medium |
| [G-8](#g-8--codex-app-server-raw-payload-extractor) | v2 | Path A context attribution for Codex lane | Medium |
| [G-9](#g-9--rate-limit-utilization-in-builder-analyze) | v3 | Early-warning for runs approaching rate-limit fragility | Small |
| [G-10](#g-10--permission-denial-aggregation-in-builder-analyze) | v3 | Counts tokens wasted on denied tool attempts | Small |

---

## G-1 — MCP server status snapshot via Builder CLI

**What:** Add `builder agent mcp-status --json` that wraps the SDK's `get_mcp_status()` and prints per-server connection status, configured tools, and any error. Currently the autoresearch harness can call the SDK directly in Python, but that requires the harness to import and configure the SDK — extra dependency surface.

**Why it matters:** An MCP server that fails mid-run (network blip, auth expiration) causes tool denials that look in `analyze.json` like the agent chose not to call the tool. The loop attributes the token waste to the wrong cause and may keep a "win" that actually broke a tool.

**Source change:**
- Add `src/autonomous_agent_builder/cli/commands/agent.py` subcommand `mcp_status`.
- Implementation calls `claude_agent_sdk.get_mcp_status()` directly (the SDK function works without a query in flight).
- For Codex lane, query the Codex app-server equivalent.

**Effort:** ~50 lines, half a day including tests.

**Tier:** v2. Without it, the harness uses `python -c 'from claude_agent_sdk import get_mcp_status; ...'` as a workaround. Adequate; ugly.

**Roadmap home:** [docs/goal/ROADMAP.md § M2.3](../goal/ROADMAP.md#m23--cost-aware-execution-surface-complete) (cost-aware surface complete).

---

## G-2 — `PromptBlockLedger` instrumentation (CONTEXT-LEDGER Path B)

**What:** Add a `PromptBlockLedger` class and persist its serialized form as a chat event when each prompt is assembled. Specified in detail in [CONTEXT-LEDGER.md § Path B](CONTEXT-LEDGER.md#path-b--source-level-instrumentation).

**Why it matters:** Path A (OTEL raw-body parsing) works today but depends on stable anchor strings in the prompt assembly. As Builder's prompt shape evolves, anchors will drift and the loop will start producing high `unattributed_tokens`. Path B is drift-proof because the source declares each block's identity.

**Source change touches:**
- New: `src/autonomous_agent_builder/agents/prompt_block_ledger.py` (~60 lines).
- Modified: `src/autonomous_agent_builder/agents/execution_policy.py` (instrument `build_system_prompt`).
- Modified: `src/autonomous_agent_builder/embedded/server/routes/agent.py` (instrument `_general_chat_prompt` and feature-spec / init-project prompt builders).
- Modified: `src/autonomous_agent_builder/embedded/server/agent_documentation_context.py`, `agent_observability_context.py` (each adds `ledger.add(...)`).
- Modified: `src/autonomous_agent_builder/orchestrator/phase_context.py`, `active_feature_scope.py`, `gate_feedback.py`, `workspace_integration.py` (same instrumentation pattern).
- Modified: `src/autonomous_agent_builder/cli/commands/logs.py` — add `prompt_block_ledger` to the `prompts[i]` payload of `analyze`.
- New: `tests/test_prompt_block_ledger.py` — invariant that the ledger total matches the assembled prompt's tiktoken count exactly.

**Effort:** 2–3 days. Many touch points but each is small; the invariant test pins correctness.

**Tier:** v2. v1 runs on Path A; v2 prefers Path B with Path A as cross-check.

**Roadmap home:** [docs/goal/ROADMAP.md § M3.5](../goal/ROADMAP.md#m35--optimization-loop-activation-autoresearch-track-b) — implementation prerequisite for the autoresearch loop's diagnostic resolution upgrade.

---

## G-3 — Cache creation vs cache read split in Builder analyze

**What:** `builder logs analyze --session <id> --full --json` currently exposes `cached_tokens` as a single number. The SDK natively distinguishes `cache_creation_input_tokens` (paid, creates a cache entry) from `cache_read_input_tokens` (cheap, reads an existing entry). Add both fields to the per-prompt and per-agent-run payloads.

**Why it matters:** **Cache churn**. A change that increases `cache_creation` while decreasing `cache_read` can look like a token reduction (input tokens go down because more is "cached") but is actually a cost regression. The loop will keep this change. Without the split, it's invisible.

**Source change:**
- `src/autonomous_agent_builder/observability/summary.py`, `summary_db.py`, and the persistence path for `AgentRun.observability` need to store `cache_creation_input_tokens` and `cache_read_input_tokens` separately. Today the assumption appears to be a single `cached_tokens` value.
- The SDK `ResultMessage.usage` dict provides both fields; the SDK adapter that persists telemetry needs to extract and store both.
- `cli/commands/logs.py` analyze output adds the two fields to `prompts[*]` and `agent_run_evidence[*]`.

**Effort:** 1 day. Schema migration to add columns + adapter changes + CLI surface update.

**Tier:** v2. Without it, the loop must cross-validate using OTEL `claude_code.token.usage` metric, which means the harness needs an OTEL collector that retains time-series. Workable; more moving parts.

**Roadmap home:** [docs/goal/ROADMAP.md § M2.3](../goal/ROADMAP.md#m23--cost-aware-execution-surface-complete).

---

## G-4 — Per-model usage breakdown in Builder analyze

**What:** Add `model_usage` per-prompt and per-run, sourced from `ResultMessage.model_usage`. Per-model: `inputTokens`, `outputTokens`, `cacheReadInputTokens`, `cacheCreationInputTokens`, `webSearchRequests`, `costUSD`.

**Why it matters:** When multi-model routing is in play (e.g., chat uses Sonnet, verifier uses Haiku, planner uses Opus), Builder's aggregate `tokens` field hides the mix. An optimization that shifts work from Sonnet to Haiku looks like a small cost win in aggregate but may be a large quality regression invisible to the gates.

**Source change:**
- Same SDK adapter that fixes G-3 also captures `model_usage` and persists per-model breakdown.
- `cli/commands/logs.py` analyze output exposes the breakdown.

**Effort:** Half a day if combined with G-3 (shared adapter change).

**Tier:** v2.

**Roadmap home:** [docs/goal/ROADMAP.md § M2.3](../goal/ROADMAP.md#m23--cost-aware-execution-surface-complete).

---

## G-5 — Hook execution timeline in Builder analyze

**What:** Capture `HookEventMessage` events (when `include_hook_events=True` is set on the SDK options) and persist them as a `hook_event` chat event type. Analyze output exposes `hooks[*]` with per-hook timing.

**Why it matters:** Hooks add latency that is invisible in `analyze` today. A new hook that adds 200ms per turn shows up as a small `duration_ms` increase but no obvious cause. With the timeline, the cause is visible.

**Source change:**
- Enable `include_hook_events=True` on `ClaudeAgentOptions` for all Claude-lane runs (always on, not configurable — telemetry-only).
- Add `hook_event` to the chat event taxonomy in the persistence layer.
- Add `hooks[*]` projection to analyze output.

**Effort:** 1 day. Hook event modeling + persistence + analyze surface.

**Tier:** v3. Loop runs fine without it; this is for hunting latency regressions specifically.

**Roadmap home:** Could land alongside M2.3 (cost-aware execution surface) or as a standalone improvement in M3.4 (head-to-head benchmark, where latency parity matters).

---

## G-6 — Per-agent OTEL env via `ClaudeAgentOptions.env`

**What:** Pass OTEL configuration through `ClaudeAgentOptions.env` from Builder so different agents (or different runs) can have different telemetry settings. Today, OTEL env is machine-wide (whatever was exported before `builder start`).

**Why it matters:** During the autoresearch loop, multiple parallel runs on the same machine would conflict on `OTEL_LOG_RAW_API_BODIES=file:<dir>` since they'd write to the same dir. Per-agent env avoids the conflict and supports parallel runs.

**Source change:**
- `src/autonomous_agent_builder/agents/execution_policy.py` and the Claude SDK adapter expose a hook for per-run env overrides.
- Harness passes `OTEL_*` per-run via that hook.

**Effort:** Half a day.

**Tier:** v3. v1 and v2 run serially.

**Roadmap home:** [docs/goal/ROADMAP.md § M3.5](../goal/ROADMAP.md#m35--optimization-loop-activation-autoresearch-track-b) (parallel-iteration polish).

---

## G-7 — Autonomous `agent_edit` step in loop

**What:** Today `loop.py` pauses at `agent_edit(idea)` for a human to make the source change for the picked idea. Make it autonomous by invoking a Claude or Codex SDK session with the idea description, allowlist, and a structured prompt that asks for the change.

**Why it matters:** Without it, the loop is semi-autonomous — a human edits between iterations. This caps iteration rate at human attention rate. The whole Karpathy promise is "100 experiments while you sleep"; that needs autonomy.

**Source change:**
- New module `scripts/autoresearch/agent_edit.py` that wraps `claude_agent_sdk.query` (or the Codex equivalent) with:
  - System prompt loaded from a new `docs/autoresearch/AGENT-EDIT-PROMPT.md` (built when this gap is closed).
  - Idea text as the user prompt.
  - Allowlist enforced via `disallowedTools` blocking edits outside the idea's `files`.
  - Permission callback that auto-approves only allowlist file edits and rejects everything else.
- Time bound per edit (e.g., 10 min); if the agent doesn't produce a diff, mark idea as `exhausted` and move on.

**Effort:** 2 days. The hard part is the prompt design and the permission callback shape; the SDK plumbing is small.

**Tier:** v3. v1 and v2 of the loop are human-in-the-loop. Most learning value happens at v1/v2 anyway — the loop's purpose is to *find* wins, not to maximize iteration count before the loop is well-tuned.

**Roadmap home:** [docs/goal/ROADMAP.md § M3.5](../goal/ROADMAP.md#m35--optimization-loop-activation-autoresearch-track-b) follow-on.

---

## G-8 — Codex app-server raw payload extractor

**What:** Build the Codex-lane analog of `extract_context_breakdown.py`. The Claude lane uses OTEL `OTEL_LOG_RAW_API_BODIES=file:<dir>` to capture full prompts; the Codex lane logs differently and needs its own extractor.

**Why it matters:** Without it, `per_prompt_results.tsv` rows for Codex-lane runs have empty `context_breakdown_json`. The loop can still keep/discard based on composite, but per-prompt diagnostics are missing — meaning Codex-lane wins are harder to attribute to a specific block.

**Source change:**
- Identify the Codex app-server log file location (already persisted by Builder per the Codex runtime contract).
- New: `scripts/autoresearch/extract_context_breakdown_codex.py` that parses Codex payloads with the same anchor logic as the Claude extractor but adapted to Codex prompt structure.

**Effort:** 1–2 days. Mostly understanding the Codex payload shape and re-implementing anchor matching.

**Tier:** v2. v1 of the loop should run on Claude lane first; once Claude wins, re-test the same changes on Codex lane using composite-only comparison until the Codex extractor lands.

**Roadmap home:** Follows G-2 (or in parallel — independent files).

---

## G-9 — Rate-limit utilization in Builder analyze

**What:** Capture `RateLimitEvent.utilization` from the SDK message stream and surface it in `analyze.json`. Today Builder has `provider-limit-reset` metadata but not the utilization curve.

**Why it matters:** A run that ends at 95% utilization is fragile — the next run could fail. The loop should be able to read utilization and either: (a) wait for reset before the next iteration, (b) discard runs that pushed utilization above a threshold even if composite improved.

**Source change:**
- Capture `RateLimitEvent` in the SDK adapter and persist as `rate_limit_event` chat events.
- Surface `rate_limit_max_utilization` per session in analyze output.

**Effort:** Half a day.

**Tier:** v3. Loop runs without it; this is robustness polish for long-running unattended loops.

**Roadmap home:** Standalone; can land anytime.

---

## G-10 — Permission denial aggregation in Builder analyze

**What:** Aggregate `ResultMessage.permission_denials` per session and per prompt; surface in analyze output.

**Why it matters:** A run that succeeded after 8 denials wasted tokens on attempts the model didn't know would fail. Counting denials per session helps the loop detect "the win was achieved despite the agent fighting permissions" — usually a sign the allowlist needs adjustment.

**Source change:**
- Capture denials in the SDK adapter; persist count per agent run.
- Surface `permission_denial_count` per `agent_run_evidence` row.

**Effort:** Half a day.

**Tier:** v3.

**Roadmap home:** Standalone; useful alongside G-9.

---

## What's already covered (no gap)

These are signals the framework needs that **Builder CLI already exposes** without source changes. Listing them here to prevent re-litigation:

- Total session tokens, cost, prompt count: `analyze.json` top-level.
- Per-prompt tokens, cache ratio, context budget: `analyze.json` `prompts[*]`.
- Per-agent-run tokens, duration, stop_reason, cost: `analyze.json` `agent_run_evidence[*]`.
- Avoidable cost flags, chunk pressure risk: `metrics.json`.
- Sprint state, board phase, blocked tasks: `board.json`.
- Recent errors: `errors.json`.
- Top cost drivers, recommended next change: `analyze.json`.
- Headless chat send/respond: `POST /api/agent/chat` and `POST /api/agent/chat/respond` (verified at `embedded/server/routes/agent.py:1566` and `:1632`).
- Headless history read: `GET /api/agent/chat/history`.
- Board polling: `GET /api/dashboard/board`.

## What's covered by enabling SDK env vars (no source change)

These need no source changes — only OTEL env vars per [SDK-OBSERVABILITY.md § Recommended loop setup](SDK-OBSERVABILITY.md#recommended-loop-setup):

- Full prompt body (raw API requests) — `OTEL_LOG_RAW_API_BODIES=file:<dir>`.
- Per-tool wall-clock latency split (blocked-on-user vs execution) — OTEL traces.
- Cache creation vs cache read split — OTEL `claude_code.token.usage` metric (if Builder analyze doesn't carry it, the collector does).
- Hook execution timing — OTEL `claude_code.hook` spans with `ENABLE_BETA_TRACING_DETAILED=1`.

## How to use this file

- Before starting source-code work for autoresearch, read this file top to bottom. Each gap row tells you whether the change is worth doing now (v1 not blocked without it) or later (v2/v3 polish).
- When closing a gap, delete its section from this file and update [METRICS.md](METRICS.md) (which TSV column got richer) and [docs/goal/STATUS.md](../goal/STATUS.md) (record the source-change milestone).
- If a new gap appears (a measurement the loop wants but the system doesn't expose), add a section here following the same structure: What / Why / Source change / Effort / Tier / Roadmap home.

## Related

- [METRICS.md](METRICS.md) — every column we capture today (gaps named in the "What we are NOT capturing" table).
- [HARNESS.md](HARNESS.md) — explicit "what the harness does NOT do today" section maps to G-1, G-4, G-7, G-8.
- [CONTEXT-LEDGER.md](CONTEXT-LEDGER.md) — Path A (works today, gap is anchor drift over time) vs Path B (G-2).
- [docs/goal/ROADMAP.md § M2.3 and § M3.5](../goal/ROADMAP.md) — where these gaps land on the strategic roadmap.
