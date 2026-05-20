# Builder CLI Tool Signal Analysis

> Analysis date: 2026-05-11  
> Workspace: todo-app (initialized, agent_ready)  
> Mission: Measure what each Builder CLI tool returns by default, estimate token cost, and rate whether the output enables the Agent to make the right decision on the first try.

Status: evidence-only. This doc preserves dated measurements and findings; it
does not own current tool-output policy. Promote durable Builder CLI policy to
[builder-cli.md](../references/builder-cli.md), pass/fail expectations to
[builder-cli.md](../quality-gate/builder-cli.md), and SDK-backed Agent behavior
to [sdk-backed-agent-page-agent.md](../rubric/sdk-backed-agent-page-agent.md).

## Executive Summary

The original audit found two context-window destroyers:
`builder metrics show --json` and `builder board show --json` together consumed
roughly 270K tokens in the generated todo app. That finding was real, but it is
now historical rather than current for the default paths.

Current measured defaults in the same todo app are bounded: `builder board show
--json` is 1,350 estimated tokens, `builder metrics show --json` is 2,457, and
`builder logs --info --compact --json` is 585. `builder board show --json
--full --limit 5` is 4,656 estimated tokens and still replaces raw nested
runtime/observability/timeline blobs with summaries.

A live Codex SDK app-server audit also exercised these commands through
`CodexAppServerRuntime` in the generated todo app. The final rerun reported
`runtime_sdk=codex_sdk`, `protocol=codex_app_server_jsonrpc`,
`raw_event_count=418`, `largest_command_output_bytes=13749`,
`largest_event_bytes=13933`, and `chunk_pressure_risk=false`. That run exposed
and then rechecked the focused-read fallback: `builder backlog task status
<task-id> --json` now works from local Board state when the API is down and
returns compact `degraded=true` evidence.

**The design principle is clear:** deterministic state reads (counts, booleans, status enums) should be compact. Evidence-seeking, judgment-requiring, and diagnosis requests should be routed to the Agent, not pre-materialized into tool payloads.

## Official SDK Grounding

The rubric below is grounded in the current primary SDK/protocol docs, not only
repo preference:

- Claude Agent SDK: the SDK exposes built-in file/command/search tools, MCP,
  permissions, hooks, sessions, and `AskUserQuestion`; the documented pattern is
  to pass exact `allowed_tools` / `allowedTools`, resume sessions intentionally,
  and use hooks for validation/logging. Source:
  <https://code.claude.com/docs/en/agent-sdk/overview>.
- Claude Agent SDK MCP: MCP tools follow the
  `mcp__<server-name>__<tool-name>` naming convention, require explicit
  permission, and should usually be granted through `allowedTools` rather than
  broad permission modes. The docs also call out that large tool sets can consume
  significant context and that tool search with deferred definitions is the
  intended mitigation. Source:
  <https://code.claude.com/docs/en/agent-sdk/mcp>.
- Claude Code hooks: `PreToolUse` can allow, deny, or ask before a tool call, and
  `PostToolUse` can feed structured or textual feedback after execution. That
  supports this repo's pattern of using hooks/permission policy to enforce
  workspace boundaries and audit tool results instead of relying on prompt
  prose. Source: <https://code.claude.com/docs/en/hooks>.
- Codex SDK / App Server: Builder's OpenAI-side runtime is Codex, not OpenAI
  Agents SDK. In this repo, `RUNTIME_SDK=codex_sdk` maps to
  `CodexAppServerRuntime`, so App Server is the live Codex SDK proof surface.
  OpenAI describes Codex App Server as the client-friendly, bidirectional
  JSON-RPC API over stdio/JSONL that exposes the Codex harness.
  The protocol centers on long-lived threads, turns, streamed item events,
  server-initiated input or approval requests, and generated protocol bindings
  via `codex app-server generate-ts` or `codex app-server generate-json-schema`.
  That means Builder should validate Codex behavior against the selected Codex
  binary and JSONL event stream, not against Claude MCP or OpenAI Agents SDK
  assumptions. Source:
  <https://openai.com/index/unlocking-the-codex-harness/>.
- Codex CLI / Exec: OpenAI documents Codex CLI as a local coding agent that can
  read, modify, and run code locally with an approvals workflow; the App Server
  article describes Codex Exec as the lightweight non-interactive mode for
  automation and CI. Builder should use these Codex surfaces for Codex-native
  tool-output proof, especially command stdout/stderr size and JSONL telemetry.
  Sources:
  <https://help.openai.com/en/articles/11096431-openai-codex-cli-getting-started>
  and <https://openai.com/index/unlocking-the-codex-harness/>.
- Do not use OpenAI Agents SDK docs as the owner source for this runtime.
  Builder's OpenAI-side lane must be judged against Codex SDK/App Server/CLI
  semantics.

## Tool-Call Surface Rubric

This audit must stay split by execution surface. A compact Claude MCP tool
output does not prove the same behavior for Codex SDK, and a compact CLI command
does not prove the in-process SDK tool wrapper preserves that compactness.

| Surface | Actual tool lane | Output the agent sees | Required default | Current evidence | Remaining gap |
|---|---|---|---|---|---|
| Builder CLI | `builder ... --json` commands from shell or Codex native command tools | CLI stdout/stderr JSON or text | Bounded JSON with counts, IDs, status enums, compact recent evidence, and explicit `--full`/raw opt-in | This scan measured representative CLI payloads and identified the high-risk `board`/`metrics` defaults | Re-measure after every CLI compaction and include invalid/miss cases from `workflow quality-gate cli-for-agents` |
| Claude Agent SDK | In-process MCP servers from `agents/tools/sdk_mcp.py`, backed by `builder_tool_service.py` and `workspace_tools.py` | MCP content payloads and compact dashboard tool events | Compact by default; mutation tools return proof metadata; read tools return bounded evidence; workspace outputs preserve head/tail or line slices; allowed tools stay exact and minimal | Focused tests passed for compact Builder service payloads, workspace output bounds, tool registry exposure, and evidence-routing prompts | Does not prove Codex SDK because Codex does not consume these in-process Claude MCP servers |
| Codex SDK app-server | `codex app-server` JSON-RPC native tools and event stream | Codex app-server events, compact dashboard previews, final assistant text, and token/event telemetry | Native event previews must be bounded; prompts must steer Codex toward compact Builder CLI commands; optimization telemetry must flag large events and command output; approval events must preserve requested/granted permission subsets | `tests/test_codex_app_server_runtime.py` proves compact 500-char event previews, requestUserInput mapping, token usage parsing, raw event counts, and largest event/command-output accounting | Need live Codex SDK run audit with representative Builder CLI commands to prove native command output does not create chunk pressure |
| Codex CLI compatibility | `codex exec --json` JSONL stream | JSONL events, final message file, token metrics, provider-limit signals | JSONL parsing must keep usage/provider-limit evidence without reinjecting raw logs into Builder state | `tests/test_codex_cli_runtime.py` proves subscription command shape, JSONL usage parsing, and provider-limit handling | Compatibility lane only; do not use as proof for app-server native tool output unless the selected runtime is `codex_cli` |
| Realtime voice tools | Realtime sideband tool calls handled by Builder services | Spoken summaries, dashboard voice ledger, compact metrics voice ledger | Voice reads summaries and delegates durable work; it must not dump Agent/tool transcripts into speech or metrics defaults | Current metrics compaction keeps voice ledger summary and failed-output counts instead of raw `tool_outputs` | Operator voice scenarios are still pending and must be audited after a live voice pass |

Pass threshold for each surface:

1. Default output stays below the surface budget and includes a token/size
   estimate or enough metadata to compute one.
2. The first response includes the next exact command/tool when raw or full
   evidence is needed.
3. Mutation tools return post-mutation proof, not raw bodies.
4. File, command, directory, log, metric, and transcript reads are bounded by
   default and require an explicit narrower read or `--full` path for raw data.
5. Evidence-seeking prompts route to the reasoning Agent with compact tools
   instead of a cheap deterministic shortcut.
6. Runtime telemetry records enough token/event data to detect large native tool
   outputs, redundant scans, and chunk-pressure risk.

---

## Tool-by-Tool Analysis

### Tier 1: Compact and High-Signal (No Changes Needed)

| Tool | Default Est. Tokens | Signal (1–10) | Why It Works |
|---|---|---|---|
| `builder memory stats --json` | 36 | 10 | Counts by type/status only. Zero waste. |
| `builder memory list --json` | 59 | 10 | Slug list with previews. Bounded when populated. |
| `builder agent meta --json` | 109 | 10 | Model, effort, SDK, workspace path. Exactly what the Agent needs to know its own runtime. |
| `builder context repo-init --json` | 173 | 9 | Task name, commands, success criteria. Action-oriented. |
| `builder context verification --json` | 162 | 9 | Gate names, task status commands. Task-focused. |
| `builder map --json` | 192 | 9 | Project root, feature counts, memory counts, server reachability, board summary counts. The ideal orientation payload. |

**Key pattern:** These tools return exactly the counts, enums, and action hints the Agent needs. No nested objects. No evidence repetitions. No template text.

### Tier 2: Functional but Over-Weight (Trim Needed)

| Tool | Default Est. Tokens | Signal (1–10) | Problem | Fix |
|---|---|---|---|---|
| `builder doctor --json` | 230 | 9 | Near-ideal. Slightly verbose readiness sub-object. | Keep as-is; the cost is justified for a startup gate. |
| `builder server status --json` | 386 | 7 | Full `metadata` dict per server duplicates `command` array and timestamps. | Return only `{port, owned_live, pid, started_at, version}`. Drop the full command array and schema_version. |
| `builder knowledge list --json` | 377 | 8 | Good. Previews are useful. | Keep as-is. |
| `builder knowledge validate --json` | ~600 | 7 | `blocking_render_status` appears in both `details` and top-level. `checks[].details` nests the same data a third time. | Deduplicate: return `checks` summary only; move `blocking_render_status` and `unresolved_item_counts` to a `--verbose` flag. Default: `{passed, score, summary, blocking_docs, checks: [{name, passed, score, message}]}`. |
| `builder readiness status --json` | 361 | 8 | Clean when `agent_ready`. When blocked, `blocking_reasons` is useful but `next` duplicates it. | Merge `blocking_reasons` and `next` into a single `actions` array. Drop `repo_fingerprint` from status (it's assess territory). |
| `builder readiness assess --json` | **1,849** | **4** | **Telemetry evidence block repeated verbatim 3x** (telemetry_env_config, telemetry_content_safe, telemetry_collector_reachable). Each ~120 tokens. That's ~360 tokens of pure duplication. Plus `repo_fingerprint` with SHA hashes the Agent never needs. | **Deduplicate the three telemetry checks into one telemetry block.** Drop `config_hash` and `onboarding_state_hash` from `repo_fingerprint` (the Agent needs `branch`, `dirty`, `mode` only). Expected savings: ~500 tokens. |
| `builder lint --json` | 497–1,262 | 5 | Two wildly different sizes depending on KB state. When KB is initialized, the `knowledge` check inflates with full `deterministic_validation` details including `blocking_render_status`, `unresolved_item_counts`, and 6 check objects with nested `details`. | Cap lint at summary level by default. Move `details` behind `--verbose`. Default should be: `{name, command, status, passed, summary}` per check. |
| `builder logs --info --compact --json` | 585 | 7 | Good with `--compact`. Without it, payloads would be unbounded. `next_action` hint per log entry is low-value. | Drop `next_action` from default compact output. The Agent will call `builder logs analyze` for deep diagnosis. |
| `builder logs --error --json` | 562 | 7 | Good for failure-first. Same `next_action` bloat. | Same fix: drop `next_action` from default. |
| `builder logs analyze --session <id> --json` | target <2,000 | 8 | Historical default replayed full prompt rows, telemetry health, runtime aggregates, and phase decisions; one live run measured `token_estimate=10671`. | Default to summary mode with prompt summaries and compact telemetry health. Keep full payload behind `--full --json`. |
| `builder memory contract --json` | 711 | 5 | Returns the full template specification including sample markdown. The Agent almost never needs this. | Default to `{doc_type, required_frontmatter_keys, allowed_types, allowed_statuses}`. Move `sample_markdown`, `rules`, and `recommended_body_sections` behind `--full`. |
| `builder script list --json` | 202 | 8 | Good. Name + description per script. | Keep as-is. |
| `builder quality-gate` | ~400 | 7 | Lists 16 surfaces with title + summary. Useful for discovery but the Agent usually calls a specific surface. | Keep as-is for discovery. Specific surfaces should use `builder quality-gate <surface> --json`. |

### Tier 3: Resolved Hotspots (Regression Watch)

| Tool | Default Est. Tokens | Signal (1–10) | Problem | Fix |
|---|---|---|---|---|
| `builder board show --json` | **1,350** | **8** | Historical failure was a full sprint/dashboard deepcopy. Current default keeps complete counts, five compact rows per section, current sprint summary, `sections_truncated`, `raw_evidence.full_payload_command`, and focused task next step. | Keep this guarded by CLI tests. Use `builder backlog task status <task-id> --json` for diagnosis. `--full --limit 5` is bounded at 4,656 estimated tokens and summarizes nested blobs. |
| `builder metrics show --json` | **2,457** | **7** | Historical failure was full run history with repeated observability. Current default is a compact decision lane with optimization and runtime summaries. It is still above the ideal 500-token target but no longer a context-window destroyer. | Continue trimming lower-value metric fields, but preserve optimization decision evidence. Keep `builder metrics show --json --full --limit 10` as the opt-in deeper run payload. |

### Tier 4: Specialized Tools (Acceptable as Special-Purpose)

| Tool | Default Est. Tokens | Signal (1–10) | Notes |
|---|---|---|---|
| `builder backlog task list --json` | ~1,205 | 7 | Task list is bounded. Acceptable for task iteration. |
| `builder backlog task status <id> --json` | varies | 6 | Single task detail. Watch for sprint_execution bloat same as board show. |
| `builder backlog task show <id> --full --json` | large | 4 | `--full` brings implementation_brief. Should be opt-in only. |
| `builder agent sessions --json` | varies | 7 | Session list. Keep scoped. |
| `builder agent history --session <id> --json` | large | 5 | Full transcript. Only for deep diagnosis. |
| `builder verify --execute --json` | varies | 6 | Behavioral proof output. Acceptable for verification. |

---

## Cross-Cutting Problems

### 1. Telemetry Evidence Triplication

`readiness assess` repeats the same telemetry evidence object (collector status, export intervals, signal state, endpoint details) across three checks: `telemetry_env_config`, `telemetry_content_safe`, and `telemetry_collector_reachable`. Each copy is ~120 tokens. Combined waste: ~240 tokens per assess call.

**Fix:** Merge into a single `telemetry` check with `{enabled, active_lane, collector_reachable, content_safe, inactive_disabled}`.

### 2. Runtime Decision Summary Bloat

`metrics show` and `board show` both include `runtime_decision_summary` with 7 phase decision objects, each containing ~15 fields. This is immutable infrastructure configuration that is the same for every run in a sprint. It adds ~800 tokens per run but provides zero decision value after the first occurrence.

**Fix:** Reference `runtime_decision_summary` by hash or sprint_id. Store once. Return a `runtime_decision_hash` field and only include the full decision on `--full` or `--verbose`.

### 3. Observability Infrastructure in Every Run

Every run in `metrics show` includes `{source, enabled, metrics_exporter, logs_exporter, traces_exporter, enhanced_tracing, detailed_beta_tracing, service_name, resource_attributes, headers_configured, endpoint_configured, endpoint_placeholder, collector{...}, collector_reachable, export_intervals_ms, sensitive_data_flags, signal_state}`. This is identical across 166 runs.

**Fix:** Extract to a single `observability_config` at the top level. Per-run entries get `observability_hash` only.

### 4. Verification Evidence Duplication

`board show` copies the same `verification_evidence` object (including 21 acceptance run UUIDs and the full checkout verification) across all 6 sprint features because they share a single verification task. 21 UUIDs × 6 copies = 126 UUID entries for what is a single verification event.

**Fix:** Reference verification by `verification_task_id`. Include verification details only in the sprint-level or `--full` output.

### 5. Implementation Brief Per-Task Copy

Each task's `sprint_execution.implementation_brief` repeats the full feature description text. For a sprint with 6 features × 3 tasks = 18 copies of similar brief text.

**Fix:** Store `implementation_brief` at the sprint level. Per-task entries reference the sprint brief plus a `task_role` (core-app-behavior / persistence-tests / browser-verification).

---

## Token Budget Impact Model

Assume the Agent needs the following for a typical decision cycle:

| Decision Point | Tools Called | Current Tokens | Ideal Tokens | Savings |
|---|---|---|---|---|
| Startup orientation | `doctor` + `map` | 422 | 422 | 0 |
| Board state check | `board show` | 1,350 | ~1,000 | 350 |
| Task health check | `metrics show` | 2,457 | ~1,000 | 1,457 |
| Readiness check | `readiness status` | 361 | 200 | 161 |
| Readiness diagnose | `readiness assess` | 1,849 | ~800 | 1,049 |
| Lint check | `lint` | 497–1,262 | ~200 | 297–1,062 |
| Error diagnosis | `logs --error` | 562 | 400 | 162 |
| KB health | `knowledge validate` | 600 | 200 | 400 |
| **Total decision cycle** | | **~8K** | **~4K** | **~4K** |

The current default cycle is no longer larger than a context window. The
remaining work is polish and cross-runtime proof, especially a live Codex SDK
app-server run that exercises representative Builder CLI reads and records
native command/event sizes.

---

## Recommendations

### Immediate (Block Agent Intelligence)

1. **Live Codex SDK audit**: Run an app-server-backed Codex turn in a generated
   app that reads Board, Metrics, Logs, Knowledge, Memory, and task/backlog
   state, then record `largest_command_output_bytes`,
   `largest_event_bytes`, and chunk-pressure status.
2. **`builder metrics show --json`**: Continue reducing low-value repeated
   fields while preserving optimization decision evidence. Target: ~1K tokens.
3. **`builder readiness assess --json`**: Deduplicate telemetry checks into one
   block. Drop SHA hashes from `repo_fingerprint`. Target: ~800 tokens.

### Short-Term (Reduce Waste)

4. **`builder lint --json`**: Default to `{name, command, status, passed, summary}` per check. Move `details` behind `--verbose`. Target: ~200 tokens.
5. **`builder knowledge validate --json`**: Deduplicate `blocking_render_status` (appears in `details` and at top level). Move check `details` behind `--verbose`. Target: ~200 tokens default.
6. **`builder logs --info/error --compact`**: Drop `next_action` per entry. Target: ~400 tokens.
7. **`builder memory contract --json`**: Default to keys/types only. Move template behind `--full`. Target: ~100 tokens.
8. **`builder server status --json`**: Drop `command` array and `schema_version` from per-server metadata. Target: ~200 tokens.

### Architectural (Prevent Regressions)

9. **Add `token_estimate` to every tool response.** Some tools already include this field. Make it mandatory and surface it in a response header so the Agent can budget context.
10. **Add max-token budgets per tool category.** Status/read tools: ≤500. List/index tools: ≤1000. Detail/show tools: ≤2000. Full/history tools: ≤5000. Anything larger requires `--full`.
11. **Factor shared objects by reference.** `runtime_decision_summary`, `observability`, and `sprint_execution` should be stored once and referenced by hash or ID, not copied into every element.
12. **The Agent page SDK tools should mirror these compact defaults.** MCP tool definitions should expose the compact form. The Agent should never receive 125K+ tokens from a single tool call.

---

## Signal Rating Methodology

| Rating | Meaning |
|---|---|
| 10 | Perfect signal, zero waste. Agent gets exactly what it needs. |
| 8–9 | High signal, minimal waste. Minor trimmable overhead. |
| 6–7 | Functional but carries avoidable bloat. Agent can use it but pays unnecessary token cost. |
| 4–5 | Overweight for what it delivers. Significant waste that impairs Agent decision cycles. |
| 1–3 | Crisis-level bloat. Destroys context window. Agent cannot use default output effectively. |

---

## Appendix: Compact Default Payload Shapes

### `builder board show --json` (current default, measured 1,350 tokens)

```json
{
  "counts": {"pending": 0, "active": 0, "review": 0, "done": 17, "blocked": 1},
  "done": [{"id": "393693f7-...", "title": "Implement core app behavior...", "status": "done"}],
  "blocked": [{"id": "543ead12-...", "title": "Verify Deterministic tests...", "status": "capability_limit", "blocked_reason": "provider limit blocked..."}],
  "current_sprint": {"sprint_id": "dff57b5e-...", "active_phase": "shipped", "task_counts": {"done": 3}},
  "sprints_summary": {"count": 6, "latest": [{"sprint_id": "dff57b5e-...", "label": "Sprint 2"}]},
  "sections_truncated": {"done": {"returned": 5, "omitted": 12}},
  "raw_evidence": {"full_payload_command": "builder board show --json --full --limit 5"},
  "ok": true
}
```

### `builder metrics show --json` (current default, measured 2,457 tokens)

```json
{
  "summary": {
    "total_cost": 10.24,
    "total_tokens": 197614,
    "total_runs": 171,
    "gate_pass_rate": 93.6
  },
  "recent_runs": [
    {
      "id": "44b5fe73-...",
      "agent_name": "Agent",
      "status": "completed",
      "cost_usd": 0.032,
      "duration_ms": 6963,
      "stop_reason": "end_turn"
    }
  ],
  "ok": true
}
```

### `builder readiness assess --json` (proposed default, ~800 tokens)

```json
{
  "state": "agent_ready",
  "can_continue": true,
  "summary": {"required_passed": 17, "required_failed": 0},
  "blocking_reasons": [],
  "next": [],
  "repo_fingerprint": {"branch": "main", "dirty": true, "mode": "reverse_engineering"},
  "checks": [
    {"id": "builder_state", "status": "passed", "required": true, "message": "Builder state present."},
    {"id": "telemetry", "status": "passed", "required": true, "message": "Telemetry configured: claude lane active, collector reachable."}
  ],
  "ok": true
}
```

---

*This analysis started as a scan-only CLI audit. Follow-up implementation
compacted the Claude MCP service, workspace-tool defaults, metrics defaults,
and board CLI defaults. Codex SDK still needs a live native-tool output audit
because its app-server event lane is separate from the Claude in-process MCP
lane and from the compatibility Codex Exec path.*
