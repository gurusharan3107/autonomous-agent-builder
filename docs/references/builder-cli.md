# Builder CLI

Canonical reference for the repo-local `builder` CLI.

Use this doc as the owner surface when changing:

- top-level `builder` command shape
- command-group ownership and nesting
- local startup behavior
- dashboard serving behavior
- default port behavior
- CLI JSON envelopes, startup hints, or retry paths
- compact machine fields such as `ok`, `exit_code`, `code`, `matched_on`, `degraded`, `source`, and `next`
- the Day-0 readiness CLI contract

Use the quality gate in [builder-cli.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/builder-cli.md) to verify changes against this contract.

## Purpose

`builder` is the repo-local product CLI for this repository.

It owns:

- local startup/orientation
- Day-0 readiness inspection
- selected-runtime project guidance bootstrap during `builder init`
- lifecycle validation evidence and observability
- backlog and task-state inspection
- quality-gate retrieval
- repo-local knowledge access
- repo-local memory access
- agent session metadata
- project metrics

It does not own:

- global doctrine or cross-project retrieval
- repo workflow-document retrieval
- broad global knowledge search
- user-simulated lifecycle actions during dashboard-first validation

Those remain in `workflow`.

During forward-engineering and reverse-engineering validation, `builder` CLI is
allowed for bootstrap, readiness, observability, read-only state inspection, and
maintainer closeout evidence. It must not be used to prove that backlog
creation, task dispatch, approvals, or phase progression work; those actions
must be driven through the dashboard and Agent page. See
[autonomous-lifecycle-validation.md](../workflows/autonomous-lifecycle-validation.md).

## Command Taxonomy

### Top-Level Operator Entry Points

These may remain first-level because they are operator entrypoints rather than product pages:

- `builder doctor`
- `builder init`
- `builder readiness`
- `builder start`
- `builder logs`
- `builder map`
- `builder context`
- `builder server`
- `builder script`
- `builder quality-gate`

### `builder init`

`builder init` creates repo-local builder state and ensures the target repo has
project guidance for the selected runtime.

Behavior contract:

- create `.agent-builder/` state, config, database, embedded assets, and
  scripts
- create `.agent-builder/onboarding-state.json` when absent so readiness and
  the dashboard have a concrete compatibility state to read
- create root `CLAUDE.md` for `RUNTIME_SDK=claude`, or root `AGENTS.md` for
  Codex SDK, using the workflow-specific Day-0 template for forward or
  reverse engineering
- migrate builder-generated guidance between `CLAUDE.md` and `AGENTS.md` when
  switching between Claude and Codex lanes
- preserve existing user-authored `CLAUDE.md`, `.claude/CLAUDE.md`, or
  `AGENTS.md`
- create or repair runtime settings plus telemetry-safe Claude OTEL and Codex
  JSONL defaults in the autonomous-builder source `.env`; generated app `.env`
  files do not own Builder runtime, auth, or telemetry keys, and only the
  selected runtime lane is enabled
- leave raw prompt, tool, and API body telemetry export disabled by default
- include compact `runtime_guidance`, `telemetry_env`, `onboarding_state`, and
  `readiness` objects in JSON output
- if `.agent-builder/` already exists but the selected runtime guidance file is
  missing, repair only that missing guidance without requiring `--force`
- refuse to initialize when `cwd` is the autonomous-builder source repository
  or worktree (detected via `pyproject.toml` `name = "autonomous-agent-builder"`
  plus `src/autonomous_agent_builder/cli/main.py`); the builder source must
  stay free of project-local `.agent-builder` state

### Top-Level Product Surfaces

These are the first-level product pages and stable repo-local surfaces:

- `builder agent`
- `builder board`
- `builder backlog`
- `builder knowledge`
- `builder metrics`
- `builder memory`
- `builder script`

`builder server` is intentionally not listed as a product surface; it is a
bounded lifecycle inspection and cleanup group for builder-owned local servers.

### `builder board`

Owns compact pipeline-state inspection:

- `show`

`builder board show --json` is a default decision payload, not a raw dashboard
dump. It must preserve complete section counts, current blocked/active work,
compact task identifiers, sprint summary fields, and direct next commands while
omitting raw `description`, `acceptance_criteria`, `sprint_execution`,
`observability`, `agent_runs`, `activity_timeline`, and verification evidence
blocks. The default section limit is intentionally small; agents should follow
`builder backlog task status <task-id> --json` for focused task diagnosis.

`builder board show --json --full --limit <n>` is still bounded. It expands
board task fields for the selected section limit, but replaces repeated nested
runtime and timeline blobs with compact summaries. It must not reintroduce the
full dashboard payload or sprint transcript as a single command output.

Focused task status reads must preserve the same local-fallback behavior as
Board. If the API is down but `.agent-builder/` state exists, `builder backlog
task status <task-id> --json` should resolve the task from local Board state,
return `degraded=true` / `source=local_db_fallback`, and keep a compact
`token_estimate` rather than dead-ending after Board points to the focused read.

### `builder script`

Owns reusable deterministic script-library behavior:

- `list`
- `run <script-name>`

The script surface must merge project-copied scripts with packaged builder
scripts so already-initialized workspaces can use newly shipped deterministic
helpers without rerunning `builder init`. Project-local scripts remain the
override point; packaged scripts are the compatibility fallback.

`build_verify` is the deterministic proof command for repeated verifier work.
It infers workspace checks from local project files, runs package-owned
`npm run lint`, `npm run build`, and `npm test` scripts when present, and can
add a bounded HTTP app-smoke check through `app_url` and `paths` arguments.

`change_evidence` is the deterministic changed-file evidence command. It
captures the same bounded diff summary shape used by builder runs so agents can
collect PR/review evidence without spending a model turn when there is no real
remote PR target.

### Nested Backlog Surface

Backlog-tracking nouns do not belong at the top level. They live under `builder backlog`:

- `builder backlog project`
- `builder backlog item`
- `builder backlog task`
- `builder backlog approval`
- `builder backlog run`

If a command is fundamentally about project backlog state, it should extend `builder backlog ...` instead of creating a parallel first-level noun.

Typed backlog item mutation belongs in `builder backlog item update`. Status
changes such as closing validation improvements should use
`builder backlog item update <item-id> --status done --yes --json` so the API
and progress artifacts stay in sync.

## Startup Contract

`builder start` is the single public startup owner for the local product.

It owns all of these steps:

1. load repo-local environment from `.env`
2. choose the local port
3. stop an existing listener only when it is proven builder-owned
4. write `.agent-builder/server.port`
5. rebuild `frontend/` when present
6. publish the built frontend into `.agent-builder/dashboard/`
7. launch the embedded repo-local FastAPI app

Do not add parallel public startup lanes such as:

- `builder server start`
- separate dashboard-publish scripts as a primary operator path
- alternate top-level startup aliases

`builder server` is not a startup lane. It owns lifecycle inspection and
cleanup for builder-owned local server processes:

- `builder server status --json`
- `builder server doctor --json`
- `builder server stop --port <port> --json`

Unknown listeners must not be killed by default. Use `builder server status`
first, then `builder start --force` or `builder server stop --force` only when
the listener is safe to stop.

## Serving Model

The local product runs as one Python FastAPI process on one port.

That process serves:

- the local API under `/api/...`
- the dashboard static assets from `.agent-builder/dashboard/`
- the dashboard SPA fallback

Dashboard static asset serving must stay inside the resolved dashboard
`assets/` directory. Requests with `..`, encoded traversal, or sibling-prefix
paths must return 404 instead of falling through to adjacent files.

Route code must resolve project-local state through the app-scoped project root,
not the server process current working directory. Route-level `Path.cwd()` and
relative `.agent-builder` reads are intentionally blocked by static tests.

So locally:

- the backend is Python and real
- the dashboard is served by that same backend process
- the CLI and dashboard talk to the same local backend

There is not a separate default frontend dev-server port in the repo-local `builder start` flow.

## Port Contract

Default local product port: `9876`

Rules:

- `builder start` with no `--port` uses `9876`
- if `9876` is occupied by a builder-owned listener, `builder start` stops it and reuses `9876`
- if `9876` is occupied by an unknown listener, `builder start` fails with a structured recovery command instead of killing it
- if the operator passes `--port <N>`, `builder start` uses that exact port instead
- `.agent-builder/server.port` records the last launched local product port for CLI discovery

Do not reintroduce range-based fallback like `9876-9886` for the default local-product path.

## Orientation Contract

Fresh-session orientation should stay:

1. `builder --json doctor`
2. `builder map`
3. `builder context <task>`

`builder doctor` owns startup-contract inspection.
`builder readiness` owns Day-0 autonomous-work readiness.
`builder start` owns local launch.
`builder logs` owns embedded chat/tool log inspection for diagnosis while the local product is running or after a failed run.

Do not make low-level connectivity checks the primary onboarding path when `doctor` already covers the startup contract.

## Readiness Contract

`builder readiness` is the public CLI for
[day-0-readiness.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/day-0-readiness.md).

Commands:

- `builder readiness assess --json`
- `builder readiness status --json`

`assess` recomputes readiness from local repo state and writes
`.agent-builder/readiness.json`. `status` reads the persisted contract and
reports `unknown` when the file is missing, stale, or unreadable.

Exit codes:

- `0`: `agent_ready`
- `2`: `blocked`
- `3`: `unknown`
- `1`: internal error

Machine-readable output must include compact fields for `ok`, `status`, `code`,
`exit_code`, `mode`, `state`, `can_continue`, `blocking_reasons`,
`invalidated_by`, `next`, `actionable_next`, `progressive_disclosure`, and
`token_estimate`. Full readiness checks, raw persisted fields, and fingerprint
diagnostics require `--full`.

## Surface Summaries

### `builder logs`

Owns repo-local embedded run diagnostics from `.agent-builder/agent_builder.db`.

Behavior contract:

- `builder logs` is the canonical agent-facing debug lane for autonomous builder runs
- `builder logs --compact --json` should prefer stable compact diagnostics over raw tool-output blobs
- compact log entries should help an agent answer, cheaply: what failed, where it failed, what artifact or input was in scope, and what the next useful debugging step is
- raw tool payloads remain available as secondary drill-down, not the default debugging abstraction
- the Agent page may render the same underlying log events in a more user-friendly summary form; CLI compactness and UI readability do not need identical presentation
- CLI log output should stay bounded by default so a debugging agent can stay context-efficient; session scoping is explicit via `--session`
- `builder logs --error` remains the fastest path for failure-first diagnosis and is project-wide by default so older failed runtime or realtime voice tool outputs are not hidden by a newer clean session
- `builder logs --info --compact` remains the default success-path inspection lane when an agent needs structured progress evidence without replaying full raw payloads
- `builder logs analyze --session <id-or-prefix> --json` is the prompt-by-prompt session review lane and should expose observability coverage plus runtime aggregates so agents can distinguish local chat-event evidence from missing OpenTelemetry metrics, logs, and traces without ad hoc database queries
- `builder logs analyze --session <id-or-prefix> --json` also mirrors the dashboard telemetry decision
  contract: `selected_runtime`, `runtime_native_telemetry_health`,
  `builder_product_telemetry_health`, full `telemetry_health`, and
  `deterministic_recommendations` with stable rule codes, severity, evidence,
  and next action
- dispatch-only continuation turns should not remain indefinitely running in
  `builder logs analyze`; when `mcp__builder__task_dispatch` succeeds, analysis
  should expose `stop_reason=task_dispatched` and the correlated task id/status
- `builder logs --follow --ndjson` is the explicit stream contract for machine-readable log follow lanes

### `builder knowledge`

Owns repo-local knowledge operations under `.agent-builder/knowledge/`:

- `contract`
- `add`
- `list`
- `show`
- `search`
- `summary`
- `update`
- `extract`
- `validate`
- `lint`

Behavior contract:

- `builder knowledge add` and `builder knowledge update` are the canonical write path for repo-local KB docs
- `system-docs` is only one doc type inside the broader knowledge root
- tag-driven knowledge authoring and retrieval is first-class; use `--tag`, `--tags`, `--feature`, and `--testing` to stamp or filter maintained docs
- `builder knowledge search` should keep supporting bounded narrowing by doc type, task, and tags as the knowledge corpus grows

### `builder memory`

Owns repo-local decisions, patterns, and corrections:

- `list`
- `summary`
- `contract`
- `show`
- `search`
- `add`
- `init`
- `reindex`
- `lint`
- `stats`
- `relate`
- `unrelate`
- `flag`
- `graduate`
- `invalidate`

### `builder agent`

Owns saved agent-session inspection and stable runtime metadata:

- `sessions`
- `history`
- `meta`
- `runtime`
- `documentation-refresh`

Behavior contract:

- `builder agent sessions --json` should expose a compact repo-scoped chat
  session list with `sdk_session_id` when present, bounded previews,
  `actionable_next`, `progressive_disclosure`, and `token_estimate` so an agent
  can correlate builder sessions with selected-runtime continuity without
  loading raw session-list fields; the default list is intentionally small, use
  `--limit <n>` for a wider recent-session window, and raw fields require
  `--full`
- `builder agent history --session <id> --json` should expose top-level `sdk_session_id` plus compact run telemetry such as `duration_ms` and `stop_reason`
- `builder agent history --session <id> --json` should mirror the visible Agent
  transcript contract: user/assistant/error messages stay readable, while raw
  runtime transport events such as `runtime_item_started` or
  `runtime_item_completed` do not appear as transcript messages
- local read-only inspection mode should preserve the same repo-local semantics
  for session lookup, runtime metadata, transcript boundaries, and telemetry
  fields when the API is unavailable
- `builder agent runtime show --json` reads the active runtime settings,
  validation errors, capabilities, and telemetry-lane state
- `builder agent runtime probe --json` checks the selected harness without
  mutating product lifecycle state
- `builder agent runtime models --json` lists models when the selected runtime
  supports model discovery and returns a compact unsupported-capability payload
  when it does not
- `builder agent runtime set --sdk <runtime> --json` is the CLI mutation path for
  the same runtime settings changed by onboarding and dashboard Settings; it
  must update `.env` runtime keys and keep Claude OTEL versus Codex telemetry
  lanes mutually exclusive

### `builder metrics`

Owns project metrics retrieval:

- `show`

Metrics default payloads must include a compact `optimization_summary` when run
telemetry exists. The summary uses raw tokens as the primary score and exposes
non-cached + output tokens, cache ratio, avoidable-cost flags, top cost drivers,
benchmark status, and the next recommended optimization change without requiring
raw database inspection. Full phase breakdowns and wider driver detail require
`--full`.

Metrics payloads should also include `optimization_decision`,
`runtime_decision_summary`, and `deterministic_script_candidates` when enough
structured run evidence exists. These fields let an agent choose the next
optimization without scraping the dashboard:

- `optimization_decision.next_action` names the current best optimization move
- `optimization_decision.target_area` names the owner area to improve
- `deterministic_script_candidates[]` contains stable codes, triggers,
  severity, and estimated token savings
- `script_candidate_build_verify_script` should map to
  `builder script run build_verify --args '{"app_url":"http://127.0.0.1:<port>","paths":["/"]}' --json`
  when a generated app exposes local build/test scripts
- `script_candidate_change_evidence_collector` should map to
  `builder script run change_evidence --args '{}' --json` when changed-file
  evidence is sufficient and no real PR target exists
- compact `--json` output keeps `actionable_next`, `progressive_disclosure`,
  and `raw_evidence.command` pointing to focused next reads such as
  `builder backlog run summary <query> --json`, `builder logs analyze --session
  <id> --json`, and `builder metrics show --json --full --limit 10`
- the `progressive_disclosure` analyze command must always resolve to a real
  session id from recent runs; `_metrics_analysis_command` iterates recent runs
  to extract the first usable id, falling back to
  `builder metrics show --json --full --limit 10` only when no id is available
- when the primary API endpoint is unreachable, the metrics fallback response
  includes `fallback_reason` and `fallback_base_url` from `BuilderConnectivityError`
  so agents can distinguish endpoint misconfiguration from transient failures
- compact `--json` output should not duplicate top-level totals already present
  under `summary`, should limit `recent_runs` to the newest three compact
  analysis pointers, and should keep per-run storage ids plus expanded phase
  decisions behind `--full --limit`
- full metrics payloads are still bounded evidence, not transcript dumps:
  generated dependency/build paths, raw previews, stdout/stderr, and other
  forensic blobs are excluded from metrics and observability serialization;
  realtime voice ledger output remains compact totals plus recent failures; and
  larger historical sweeps require an explicit `--limit`

## Machine Contract

Rules for agent-friendly CLI behavior:

- `--json` is the stable machine contract
- `--ndjson` is the stream contract for follow, watch, tail, and progress lanes
- misses and invalid usage must return actionable retry hints
- new behavior should extend an existing owned command/group before adding a new surface
- local knowledge and memory read paths should work from disk when practical, even if the configured API endpoint is unreachable
- compact diagnostic lanes such as `builder logs --compact --json` should expose stable summary fields before raw payloads
- prompt-by-prompt runtime review should stay in `builder logs analyze --session <id-or-prefix> --json`, including resolved session identity, SDK session id, per-prompt telemetry, tool summaries, context-efficiency signals, observability coverage, telemetry health, deterministic recommendation codes, raw-token optimization fields, and compact runtime aggregates for phase ceremony, provider limits, approval wait, stop reasons, and tool-event coverage
- when `builder logs` is sparse, the CLI should still provide product-owned
  secondary evidence via `builder metrics show --json --full --limit 10` and
  `builder backlog run summary/show` before an agent drops to raw database
  inspection
- agent-facing JSON should prefer compact symbolic fields over human prose when the contract can stay unambiguous
- when the next useful action is known, expose it as a direct command field such as `next`
- error payloads should expose deterministic recovery fields before longer explanatory text
- process exit codes should distinguish invalid usage, auth/connectivity, and not-found paths instead of collapsing all failures into one status

## 9+ Benchmark Bar

Any new public CLI surface in this repo must score `9+` against the combined benchmark owned by:

- [CLI For Agents](/Users/gurusharan/.codex/docs/references/cli-for-agents.md)
- `workflow quality-gate cli-for-agents`
- [Builder CLI quality gate](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/builder-cli.md)

A new CLI surface does not qualify for `9+` unless all of these hold:

- one command model serves both humans and agents; only the renderer changes
- first-run orientation is cheap and obvious, with a startup lane such as `doctor -> map -> context`
- bounded discovery exists before exact reads: `list` or `search`, then `resolve` where ambiguity exists, then `summary` or `show`
- default output is bounded; large payloads stay behind `--full`, `--verbose`, or explicit section targeting
- all meaningful reads expose stable `--json`
- follow, watch, tail, or progress lanes expose `--ndjson`
- errors expose deterministic machine fields and semantic process exit codes
- mutative commands expose `--dry-run`, `--yes`, or the nearest equivalent safety control
- help stays cheap to scan and points to the cheapest useful first command

The benchmark is strict about three failure modes that cap a CLI below `9` even if the rest of the surface is strong:

- no first-class `resolve` lane where names, slugs, URLs, or titles are ambiguous
- process exit codes do not distinguish not-found, invalid-usage, and auth/connectivity failures
- stream or follow lanes exist but do not publish an explicit `--ndjson` contract

## Review Checklist

Before a new CLI command or command family is accepted, verify:

- root help is page-aligned and cheap
- `doctor` or the equivalent startup contract works in `--json`
- one bounded discovery path works in `--json`
- one exact read path works in `--json`
- one miss path returns structured retry guidance
- one mutative path proves `--dry-run` and/or `--yes`
- one follow or watch path proves `--ndjson` when the surface streams
- exit codes match the documented semantic taxonomy

## Retrieval And Ownership Boundary

Use `builder` when the question is about this repo's:

- startup state
- backlog
- board
- approvals
- runs
- local KB
- local memory
- local metrics

Use `workflow` when the question is about:

- repo docs under `docs/`
- global doctrine
- cross-project precedent
- global knowledge

## Related Docs

- [Builder CLI quality gate](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/builder-cli.md)
- [CLI validation](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/cli-validation.md)
