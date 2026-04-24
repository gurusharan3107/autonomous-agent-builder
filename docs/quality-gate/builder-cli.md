---
title: "Builder CLI quality gate"
surface: "builder-cli"
summary: "Use when changing the builder CLI surface to verify page-aligned commands, deterministic startup, bounded retrieval, and stable machine contracts."
commands:
  - "builder --json doctor"
  - "builder --help"
  - "builder logs --error --json"
  - "builder logs --info --compact --json"
  - "builder logs --error --follow --ndjson"
  - "builder map --json"
  - "builder agent --help"
  - "builder board --help"
  - "builder backlog --help"
  - "builder knowledge --help"
  - "builder memory --help"
  - "builder metrics --help"
  - "builder context --help"
  - "AAB_API_URL=http://127.0.0.1:1 builder knowledge search \"system architecture\" --type system-docs --limit 3 --json"
  - "builder quality-gate claude-agent-sdk --json"
  - "workflow quality-gate cli-for-agents"
expectations:
  - "startup orientation follows doctor -> map -> context"
  - "context stays a named bootstrap router; add profiles or aliases instead of fuzzy free-text guessing"
  - "the builder CLI still exposes the primary product pages as the first-level command tree: agent, board, backlog, knowledge, memory, and metrics"
  - "top-level builder commands should reflect product surfaces, not internal storage or ORM nouns such as project, feature, task, approval, or run"
  - "doctor, init, start, logs, context, and quality-gate may remain top-level because they are operator entrypoints rather than product pages"
  - "builder start is the single startup owner for the local dashboard and API; do not add parallel start or dashboard-publish entrypoints"
  - "`builder logs` remains the canonical agent-facing debug lane for embedded runs, with compact structured summaries available before raw payload drill-down"
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
  - "--json stays the stable machine contract with bounded discovery envelopes"
  - "invalid usage and misses return actionable retry hints instead of dead-end failures"
  - "top-level help keeps fresh-session orientation cheap by mapping directly to the visible product pages and essential operator entrypoints"
related_docs:
  - "docs/references/builder-cli.md"
  - "docs/claude-agent-sdk-integration.md"
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
- `builder start` remains the single owner for local startup and dashboard publication
- `builder logs --compact --json` remains bounded and structured enough for agent debugging without replaying full raw payloads
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
- [cli-validation.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/cli-validation.md)
