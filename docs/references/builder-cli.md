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

Use the quality gate in [builder-cli.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/builder-cli.md) to verify changes against this contract.

## Purpose

`builder` is the repo-local product CLI for this repository.

It owns:
- local startup/orientation
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

Those remain in `workflow`.

## Command Taxonomy

### Top-Level Operator Entry Points

These may remain first-level because they are operator entrypoints rather than product pages:

- `builder doctor`
- `builder init`
- `builder start`
- `builder logs`
- `builder map`
- `builder context`
- `builder quality-gate`

### Top-Level Product Surfaces

These are the first-level product pages and stable repo-local surfaces:

- `builder agent`
- `builder board`
- `builder backlog`
- `builder knowledge`
- `builder metrics`
- `builder memory`
- `builder script`

### Nested Backlog Surface

Backlog-tracking nouns do not belong at the top level. They live under `builder backlog`:

- `builder backlog project`
- `builder backlog feature`
- `builder backlog task`
- `builder backlog approval`
- `builder backlog run`

If a command is fundamentally about project backlog state, it should extend `builder backlog ...` instead of creating a parallel first-level noun.

## Startup Contract

`builder start` is the single public startup owner for the local product.

It owns all of these steps:
1. load repo-local environment from `.env`
2. choose the local port
3. kill any listening process already on that port
4. write `.agent-builder/server.port`
5. rebuild `frontend/` when present
6. publish the built frontend into `.agent-builder/dashboard/`
7. launch the embedded repo-local FastAPI app

Do not add parallel public startup lanes such as:
- `builder server start`
- separate dashboard-publish scripts as a primary operator path
- alternate top-level startup aliases

## Serving Model

The local product runs as one Python FastAPI process on one port.

That process serves:
- the local API under `/api/...`
- the dashboard static assets from `.agent-builder/dashboard/`
- the dashboard SPA fallback

So locally:
- the backend is Python and real
- the dashboard is served by that same backend process
- the CLI and dashboard talk to the same local backend

There is not a separate default frontend dev-server port in the repo-local `builder start` flow.

## Port Contract

Default local product port: `9876`

Rules:
- `builder start` with no `--port` uses `9876`
- if `9876` is occupied, `builder start` kills the existing listener and reuses `9876`
- if the operator passes `--port <N>`, `builder start` uses that exact port instead
- `.agent-builder/server.port` records the last launched local product port for CLI discovery

Do not reintroduce range-based fallback like `9876-9886` for the default local-product path.

## Orientation Contract

Fresh-session orientation should stay:
1. `builder --json doctor`
2. `builder map`
3. `builder context <task>`

`builder doctor` owns startup-contract inspection.
`builder start` owns local launch.
`builder logs` owns embedded chat/tool log inspection for diagnosis while the local product is running or after a failed run.

Do not make low-level connectivity checks the primary onboarding path when `doctor` already covers the startup contract.

## Surface Summaries

### `builder logs`

Owns repo-local embedded run diagnostics from `.agent-builder/agent_builder.db`.

Behavior contract:
- `builder logs` is the canonical agent-facing debug lane for autonomous builder runs
- `builder logs --compact --json` should prefer stable compact diagnostics over raw tool-output blobs
- compact log entries should help an agent answer, cheaply: what failed, where it failed, what artifact or input was in scope, and what the next useful debugging step is
- raw tool payloads remain available as secondary drill-down, not the default debugging abstraction
- the Agent page may render the same underlying log events in a more user-friendly summary form; CLI compactness and UI readability do not need identical presentation
- CLI log output should stay session-scoped and bounded by default so a debugging agent can stay context-efficient
- `builder logs --error` remains the fastest path for failure-first diagnosis
- `builder logs --info --compact` remains the default success-path inspection lane when an agent needs structured progress evidence without replaying full raw payloads
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

Behavior contract:
- `builder agent sessions --json` should expose the repo-scoped chat session list with `sdk_session_id` when present so an agent can correlate builder sessions with Claude Agent SDK continuity
- `builder agent history --session <id> --json` should expose top-level `sdk_session_id` plus compact run telemetry such as `duration_ms` and `stop_reason`
- local fallback should preserve the same repo-local semantics for session lookup and telemetry fields when the API is unavailable

### `builder metrics`

Owns project metrics retrieval:
- `show`

## Machine Contract

Rules for agent-friendly CLI behavior:
- `--json` is the stable machine contract
- `--ndjson` is the stream contract for follow, watch, tail, and progress lanes
- misses and invalid usage must return actionable retry hints
- new behavior should extend an existing owned command/group before adding a new surface
- local knowledge and memory read paths should work from disk when practical, even if the configured API endpoint is unreachable
- compact diagnostic lanes such as `builder logs --compact --json` should expose stable summary fields before raw payloads
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
