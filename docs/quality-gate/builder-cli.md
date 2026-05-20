---
title: "Builder CLI quality gate"
surface: "builder-cli"
summary: "Use when changing the builder CLI surface to verify page-aligned commands, deterministic startup, bounded retrieval, and stable machine contracts."
commands:
  - "builder --json doctor"
  - "builder --help"
  - "builder logs --error --json"
  - "builder logs --info --compact --json"
  - "builder logs analyze --session <id-or-prefix> --json"
  - "builder board show --json"
  - "builder board show --json --full --limit 5"
  - "builder backlog task status <task-id> --json"
  - "builder metrics show --json"
  - "builder metrics show --json --full --limit 10"
  - "builder lint --complexity-report --json"
  - "builder lint --json"
  - "builder logs --error --follow --ndjson"
  - "builder map --json"
  - "builder agent --help"
  - "builder agent runtime --help"
  - "builder agent runtime show --json"
  - "builder agent runtime probe --json"
  - "builder agent runtime models --json"
  - "builder board --help"
  - "builder backlog --help"
  - "builder knowledge --help"
  - "builder memory --help"
  - "builder metrics --help"
  - "builder context --help"
  - "builder readiness --help"
  - "builder readiness status --json"
  - "builder server status --json"
  - "builder server doctor --json"
  - "builder script --help"
  - "builder script list --json"
  - "builder script run build_verify --args '{}' --json"
  - "builder script run change_evidence --args '{}' --json"
  - "AAB_API_URL=http://127.0.0.1:1 builder knowledge search \"system architecture\" --type system-docs --limit 3 --json"
  - "builder quality-gate claude-agent-sdk --json"
  - "workflow quality-gate cli-for-agents"
expectations:
  - "startup orientation follows doctor -> map -> context"
  - "context stays a named bootstrap router; add profiles or aliases instead of fuzzy free-text guessing"
  - "the builder CLI still exposes the primary product pages as the first-level command tree: agent, board, backlog, knowledge, memory, and metrics"
  - "top-level builder commands should reflect product surfaces, not internal storage or ORM nouns such as project, feature, task, approval, or run"
  - "doctor, init, start, logs, map, context, readiness, server, script, and quality-gate may remain top-level because they are operator entrypoints or stable builder-owned libraries rather than storage nouns"
  - "builder start is the single startup owner for the local dashboard and API; do not add parallel start or dashboard-publish entrypoints"
  - "builder server is inspection and cleanup only; it must not become a parallel start lane"
  - "builder start must stop only proven builder-owned listeners by default and return a structured recovery command for unknown listeners"
  - "`builder logs` remains the canonical agent-facing debug lane for embedded runs, with compact structured summaries, prompt-level analysis, and explicit observability coverage before raw payload drill-down"
  - "backlog-tracking surfaces should live under the backlog lane rather than as parallel first-level nouns"
  - "the knowledge lane still provides one coherent command family for list, search, summary, show, add, update, extract, validate, and lint"
  - "disk-backed knowledge and memory reads work without requiring the server when practical"
  - "local knowledge list/search/summary/show remain usable when AAB_API_URL is unset, wrong, or the builder server is down"
  - "agent-facing JSON should prefer compact symbolic fields such as ok, exit_code, code, matched_on, degraded, source, and next over explanatory prose when the machine contract can stay unambiguous"
  - "when a next action is known, JSON should expose the direct command in a compact field instead of embedding that command only inside a sentence"
  - "error envelopes should expose deterministic recovery fields before human-readable explanation so agents do not need to parse prose to self-correct"
  - "new public CLI surfaces must meet a 9+ benchmark against cli-for-agents plus workflow quality-gate cli-for-agents, not merely pass an ad hoc smoke check"
  - "where names, slugs, URLs, or titles are ambiguous, the command family should expose a first-class resolve lane instead of forcing repeated broad search"
  - "process exit codes should distinguish invalid usage, auth or connectivity failures, and not-found failures instead of collapsing all failures into one status"
  - "follow, watch, tail, or progress lanes should expose an explicit --ndjson contract"
  - "mutative commands should expose --dry-run, --yes, or the nearest equivalent reversible control"
  - "before adding or renaming a builder command, inspect existing top-level and group help so new behavior extends an owned surface instead of creating a parallel one"
  - "knowledge discovery exposes explicit narrowing for doc_type and tags as the authored corpus grows"
  - "seed system docs stay distinct from later maintained docs through stable doc_type and doc_family contracts"
  - "the CLI is the product adapter over stable services and schemas, not the owner of the agent loop, runtime sessions, or phase routing"
  - "if SDK tools overlap builder commands, they preserve the same repo semantics and stable JSON fields"
  - "runtime selection lives under builder agent runtime and shares the same settings service as onboarding and dashboard Settings"
  - "runtime JSON exposes compact ok, sdk, provider, model, capabilities, telemetry, code, and next fields without requiring prose parsing"
  - "board JSON exposes complete section counts, compact task rows, sprint summaries, token_estimate, and a focused task-read next step without raw dashboard evidence blobs"
  - "board full JSON is bounded by --limit and summarizes nested runtime, observability, run, and timeline blobs instead of dumping them"
  - "task status JSON preserves Board's local fallback path when the API is down, including degraded/source fields and a compact token_estimate"
  - "logs analysis JSON exposes selected runtime, runtime-native telemetry health, builder-product telemetry health, and deterministic recommendation codes with evidence"
  - "metrics JSON exposes optimization summary, optimization decision, runtime decision summary, and deterministic script candidates when run evidence exists"
  - "metrics full JSON is bounded by --limit, excludes generated dependency/build artifacts and raw forensic blobs, and keeps realtime voice ledger output compact"
  - "packaged deterministic scripts remain discoverable in already-initialized projects even when the copied .agent-builder/scripts directory is older"
  - "script_candidate_build_verify_script maps to builder script run build_verify instead of another model-backed build-verifier rerun"
  - "script_candidate_change_evidence_collector maps to builder script run change_evidence when changed-file evidence is enough and no real PR target exists"
  - "--json stays the stable machine contract with bounded discovery envelopes"
  - "invalid usage and misses return actionable retry hints instead of dead-end failures"
  - "top-level help keeps fresh-session orientation cheap by mapping directly to the visible product pages and essential operator entrypoints"
related_docs:
  - "docs/references/builder-cli.md"
  - "docs/claude-agent-sdk-integration.md"
  - "docs/references/runtime-settings.md"
  - "docs/quality-gate/modular-runtime.md"
  - "docs/cli-validation.md"
---

# Builder CLI quality gate

## Purpose

Use this gate when changing the builder CLI surface, its machine-readable
contracts, or the retrieval and state behaviors exposed through the CLI.

The canonical owner surface for the command taxonomy and startup contract lives
in [builder-cli.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/builder-cli.md).

## When To Load

Load this gate before:

- changing `builder` top-level help or command groups
- changing `builder agent runtime` show/probe/models/set behavior
- editing repo-local retrieval surfaces such as `map`, `context`, `knowledge`, or `memory`
- changing which page-aligned surfaces are first-level versus nested
- moving tracking surfaces between top level and `backlog`
- changing CLI JSON envelopes or retry hints
- changing the compact diagnostic contract of `builder logs`
- refactoring builder-facing SDK bridges that must preserve CLI semantics

## Pass Signals

- any new public CLI surface in the repo would score `9+` against `cli-for-agents` and `workflow quality-gate cli-for-agents`
- startup orientation remains `doctor -> map -> context`
- the CLI continues to reflect the builder-owned product surface described in the owner docs
- first-level commands line up with the primary product pages instead of leaking internal implementation nouns
- top-level readiness, server, and script groups stay bounded to gating,
  lifecycle inspection/cleanup, and reusable script-library behavior
- `builder start` remains the single owner for local startup and dashboard publication
- `builder logs --compact --json` remains bounded and structured enough for agent debugging without replaying full raw payloads
- `builder logs analyze --session <id-or-prefix> --json` remains the compact
  prompt/session review lane and includes selected runtime, telemetry-health
  summaries, prompt summaries, and deterministic recommendation evidence without
  replaying full prompt/event payloads by default; full prompt detail requires
  `--full`
- `builder metrics show --json` remains the metrics decision lane and includes
  compact optimization summary, optimization decision, runtime decision summary,
  deterministic script candidates, `progressive_disclosure`, `actionable_next`,
  and `token_estimate` when run evidence exists; nested run and observability
  payloads stay behind `--full`
- `builder metrics show --json --full --limit 10` stays bounded and excludes generated
  dependency/build artifacts, raw previews, stdout/stderr, and other forensic
  blobs from metrics and observability payloads; wider historical sweeps require
  an explicit `--limit`, and realtime voice ledger output stays compact totals
  plus recent failures
- high-frequency agent-facing JSON defaults (`builder agent sessions`,
  `builder readiness status`, `builder readiness assess`, `builder lint`,
  `builder knowledge validate`, and `builder memory contract`) preserve current
  high-signal state, top blockers or previews, stable machine fields, direct
  next commands, `progressive_disclosure`, and `token_estimate`; raw evidence,
  long samples, nested details, hashes, and forensic payloads require `--full`
- `builder agent runtime` remains the single CLI lane for runtime settings,
  probes, model discovery, and telemetry-lane state
- local knowledge read paths still resolve from disk even when the configured API endpoint is unreachable
- new CLI behavior extends an existing command/group when that surface already exists
- JSON output stays stable and bounded
- machine-readable output stays context-efficient by preferring codes, booleans, enums, and direct commands over long explanatory sentences when both are possible
- CLI help remains cheap to scan for a fresh session
- ambiguous surfaces expose `resolve` rather than forcing repeated broad scans
- semantic process exit codes remain stable for invalid usage, auth/connectivity, and not-found cases
- streaming surfaces publish `--ndjson` and keep the event contract explicit
- mutative surfaces keep `--dry-run` and `--yes` style safety affordances

## Fail Signals

- the CLI starts introducing agent-loop behavior or task routing that belongs elsewhere
- top-level commands are organized around storage entities instead of product surfaces
- startup or dashboard publication is split across multiple public commands or scripts
- `builder logs` regresses into raw opaque blobs with no compact diagnostic summary for agents
- local knowledge retrieval regresses into a hard server dependency for basic read paths
- a new command is added without first checking whether an existing surface already owns the same behavior
- CLI output drifts from repo semantics already owned elsewhere
- runtime settings are duplicated outside `builder agent runtime`, onboarding,
  and dashboard Settings
- Codex subscription runtimes ask for API-key or base-URL settings that belong
  only to API-backed providers
- JSON envelopes lose bounded discovery or actionable retry guidance
- agent-facing JSON requires sentence parsing for fields that could have been emitted as compact codes or direct commands
- a new public CLI ships without proving a `9+` score against the benchmark
- ambiguous retrieval requires repeated `search` calls because no `resolve` lane exists
- all non-success paths return the same process exit code even when the JSON payload distinguishes the error
- a follow or watch lane exists but only exposes prose or array JSON instead of an explicit `--ndjson` stream contract
- mutative commands lack `--dry-run`, `--yes`, or another explicit safety lane

## Related Docs

- [builder-cli.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/builder-cli.md)
- [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
- [runtime-settings.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-settings.md)
- [modular-runtime.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/modular-runtime.md)
- [cli-validation.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/cli-validation.md)
