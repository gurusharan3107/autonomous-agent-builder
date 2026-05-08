# Day-0 Readiness

Canonical contract for deciding whether an initialized repo may enter
autonomous builder work.

Use this doc as the owner surface when changing:
- readiness states or pass criteria
- `.agent-builder/readiness.json`
- `builder readiness assess`
- `builder readiness status`
- selected-runtime project guidance creation and readiness checks
- Agent-page routing before requirements, repo understanding, or delivery
- the relationship between onboarding completion and autonomous work

## Purpose

Readiness is the deterministic Day-0 gate between `builder init` and autonomous
work.

`builder init` creates repo-local builder state. It does not prove that the
repo is safe for autonomous work. The readiness contract proves that next step.

Day-0 setup must leave each initialized repo with a base workflow-specific
project guidance file for the selected runtime. Claude Agent SDK uses
`CLAUDE.md` or `.claude/CLAUDE.md`; Codex SDK uses `AGENTS.md`. When the
selected runtime changes between Claude and Codex, builder migrates a
builder-generated baseline between those filenames. It must also create a
repo-local `.env` with runtime selection and safe telemetry defaults so
observability is available from the first agent run.

## Lifecycle

Forward engineering:

```text
init -> readiness -> requirements interview -> backlog -> delivery
```

Reverse engineering:

```text
init -> readiness -> repo understanding -> planning -> delivery
```

`onboarding-state.json.ready` is compatibility output for existing UI and API
consumers. The canonical source is `.agent-builder/readiness.json`.

## Owner Surfaces

- `builder readiness assess --json` recomputes the contract from local repo
  state and writes `.agent-builder/readiness.json`.
- `builder readiness status --json` reads the persisted contract and reports
  `unknown` when the file is missing, stale, or unreadable.
- `builder init` creates the selected runtime's root guidance file:
  `CLAUDE.md` for `RUNTIME_SDK=claude`, `AGENTS.md` for Codex SDK. It
  preserves existing user-authored guidance and migrates builder-generated
  guidance when switching between Claude and Codex lanes.
- `builder init` creates or repairs a root `.env` with `RUNTIME_SDK`,
  provider/model settings, Claude OTEL keys, and Codex runtime telemetry keys.
  The selected runtime lane is enabled and the inactive lane is disabled.
- `builder init` creates `.agent-builder/onboarding-state.json` when absent so
  readiness can report concrete phase blockers instead of an absent-state
  bootstrap failure.
- Claude Agent SDK phases use the Claude Code preset and project setting
  sources so `CLAUDE.md` is loaded deterministically during autonomous work.
- Codex SDK phases use Codex-native `AGENTS.md` discovery so Codex sees the
  same Day-0 contract through its own instruction loader.
- The Agent page consumes readiness through the builder backend and blocks
  autonomous work when `can_continue=false`.
- `CLAUDE.md` points to this runtime invariant but does not duplicate the
  schema or flow rules.

## Schema

The persisted contract is versioned with `schema_version: "1"`.

Required top-level fields:

- `mode`: `forward_engineering`, `reverse_engineering`, or `unknown`
- `state`: `unknown`, `agent_ready`, or `blocked`
- `can_continue`: boolean gate for autonomous work
- `project_root`: absolute project path
- `repo_fingerprint`: inputs used to reject stale readiness
- `assessed_at`: ISO timestamp for a persisted assessment
- `checks`: per-check status records
- `summary`: required, optional, and skipped check counts
- `blocking_reasons`: machine-readable required failures
- `invalidated_by`: fingerprint inputs that changed since assessment
- `next`: direct recovery commands or bounded operator actions

CLI exit codes:

- `0`: `agent_ready`
- `2`: `blocked`
- `3`: `unknown`
- `1`: internal error

## Mode Gates

Forward engineering requires:

- repo-local builder state exists under `.agent-builder/`
- selected-runtime project guidance exists: `CLAUDE.md` for Claude,
  `AGENTS.md` for Codex
- builder-created runtime guidance includes Day-0 sections for project context,
  builder contract, deterministic commands, validation, telemetry, context
  discipline, and update rules
- deterministic command slots exist even when values are `unknown`
- telemetry `.env` is present; selected runtime state is explicit and native
  telemetry health is distinguishable from runtime selection
- when a selected runtime points at a loopback OTEL collector endpoint, the
  configured local collector reachability is checked; non-local collector
  endpoints remain configuration-only checks
- raw prompt, tool, and API body telemetry export flags are not enabled by
  default
- onboarding mode is `forward_engineering`
- the project root is writable
- the workspace is clean-slate or intentionally disposable
- core onboarding phases through work-item seed passed
- repo scan phase is recorded as passed as part of the common init contract
- work-item seed must not create forward-engineering backlog, features, or
  tasks; those are created only after the operator completes the Agent
  requirements interview
- feature backlog write path is available
- KB extract and validate are marked `skipped`, not failed

Reverse engineering requires:

- repo-local builder state exists under `.agent-builder/`
- selected-runtime project guidance exists: `CLAUDE.md` for Claude,
  `AGENTS.md` for Codex
- builder-created runtime guidance includes Day-0 sections for repo discovery,
  existing-command preservation, deterministic commands, validation, telemetry,
  context discipline, and update rules
- deterministic command slots exist even when values are `unknown`
- telemetry `.env` is present; selected runtime state is explicit and native
  telemetry health is distinguishable from runtime selection
- when a selected runtime points at a loopback OTEL collector endpoint, the
  configured local collector reachability is checked; non-local collector
  endpoints remain configuration-only checks
- raw prompt, tool, and API body telemetry export flags are not enabled by
  default
- onboarding mode is `reverse_engineering`
- core onboarding phases through work-item seed passed
- repo scan mapped source, test, or runtime surfaces
- KB extract passed
- KB validate passed
- KB quality gate is `passed`

## Staleness

Persisted readiness must become `unknown` when tracked inputs change.

Tracked inputs include:

- project root
- readiness mode
- git branch, head, and dirty state
- detected manifest hashes
- project runtime guidance path and hash
- `.agent-builder/config.yaml`
- `.agent-builder/onboarding-state.json`
- feature-list presence

Do not let stale `agent_ready` status route the Agent page into requirements,
planning, implementation, or dispatch.

The readiness gate distinguishes configured telemetry from reachable telemetry.
When the selected runtime points at a loopback collector such as
`http://localhost:4318`, readiness should report whether that collector is
reachable instead of collapsing the state into a vague `unknown`. For Codex,
native OTEL configuration is project-local `.codex/config.toml`; readiness and
observability should validate that project-local config without writing global
`~/.codex` settings. Non-local collector endpoints remain configuration-only
checks.
