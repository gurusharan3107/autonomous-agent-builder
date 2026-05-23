---
title: "Autonomous Builder Telemetry Analysis"
tags: ["telemetry", "observability", "metrics", "logs", "voice", "codex-productivity"]
doc_type: "reference"
created: "2026-05-11"
---

# Autonomous Builder Telemetry Analysis

Repo-local reference for analyzing `autonomous-agent-builder` regressions from
builder telemetry, session evidence, and compact agent-facing CLI outputs.

## Purpose

Use this doc when the question is:

- which regressions happened in an Autonomous Builder run
- which telemetry gaps prevented fast diagnosis
- which patterns or anti-patterns should become builder defaults
- what should be excluded from metrics or observability to keep agent context
  compact
- whether the issue belongs in source repo code/docs, generated app state, the
  selected runtime, or Codex productivity setup

The goal is high-signal analysis that helps the next agent solve faster without
loading raw transcripts, raw tool bodies, generated artifacts, or low-value
metrics.

## Use With

Use `$codex-productivity-auditor` when the audit also needs Codex transcript or
session-behavior evidence from `~/.codex/sessions` or
`~/.codex/archived_sessions`.

The split is:

- this repo doc owns Autonomous Builder product telemetry analysis
- `$codex-productivity-auditor` owns Codex transcript productivity signals and
  durable Codex setup recommendations
- builder CLI outputs own current product state and run evidence
- workflow docs and quality gates own repo contracts

Do not move this builder-specific telemetry playbook into the global skill. The
skill may point to this repo doc when the audit target is
`autonomous-agent-builder`.

## Evidence Lanes

Start with the owner contracts, then inspect the compact runtime evidence:

```bash
docs/goal/NORTH-STAR.md
workflow --docs-dir docs summary claude-agent-sdk-telemetry-observability
workflow --docs-dir docs summary runtime-switch-dashboard-contract
builder quality-gate claude-agent-sdk --json
builder quality-gate builder-cli --json
builder quality-gate modular-runtime --json
```

From the managed app workspace, use:

```bash
builder agent runtime show --json
builder agent runtime probe --json
builder logs --error --json
builder logs --info --compact --json
builder logs analyze --session <id-or-prefix> --json
builder metrics show --json
builder metrics show --json --full --limit 10
```

Use source repo commands for source repo contracts, docs, tests, and quality
gates. Use generated app workspace commands for run logs, metrics, sessions,
dashboard state, voice events, and `.agent-builder` data.

## Analysis Loop

1. Identify the active workspace:
   - source repo: code, docs, quality gates, runtime implementation
   - generated app: run logs, metrics, dashboard evidence, voice events
2. Check runtime selection:
   - `sdk`, `provider`, `model`
   - auth method and whether an API key is required or used
   - runtime probe result and actionable `next`
3. Check native telemetry health:
   - selected-lane current emission, collector reachability, and sensitive-data
     flags
   - inactive-lane config readiness without treating static config as emitted
     telemetry
   - historical telemetry access for both lanes through logs, metrics, sessions,
     and voice ledgers
   - Codex project-local `[otel]` config, emitted signals, span metadata,
     `tracestate`, review feedback, and analytics status when `codex_sdk` is
     selected
4. Check builder product telemetry:
   - task/run state, stop reason, token/turn/duration fields
   - tool decisions, tool errors, approvals, gates, retries
   - voice tool calls, failed outputs, prepared/confirmed actions
5. Classify each issue:
   - code defect
   - docs or owner-surface drift
   - runtime config problem
   - invalid model or auth assumption
   - stale generated app workspace state
   - missing compact CLI field
   - low-signal or unsafe telemetry field
6. Apply the smallest durable fix and rerun the relevant gate.

## Patterns To Preserve

- Treat `builder logs` and `builder metrics` as compact agent-facing diagnosis
  lanes, not raw transcript dumps.
- Prefer `builder logs --error --json` first, then compact info logs, then
  `logs analyze` only when a session id matters.
- Keep `builder metrics show --json --full --limit 10` bounded by default.
- Preserve voice telemetry as first-class evidence: voice usage, tool calls,
  failed tool outputs, prepared actions, confirmed actions, and delegation ratio.
- Use `claude auth status --json` as local subscription-auth evidence; do not
  infer auth solely from `.env`.
- Use Claude Agent SDK local model aliases such as `sonnet` when local Claude
  subscription auth resolves them and fully-qualified vendor model ids fail.
- Keep Codex OTEL project-local and high-signal when `codex_sdk` is selected.
  When Claude is selected, Codex telemetry must be reported as inactive because
  it is not producing the run evidence.
- Keep historical telemetry accessible for both lanes. Runtime selection controls
  new telemetry emission only; already persisted logs, metrics, sessions, and
  voice ledgers remain valid evidence.
- Use Codex `span_attributes`, `tracestate`, `[feedback]`, and `[analytics]` to
  make review, feedback, usage, and trace correlation agent-friendly without
  exporting raw prompts.
- Record runtime, model, provider, effort, stop reason, token fields, duration,
  tool outcome, and telemetry source in compact JSON.
- Record context-budget evidence at Builder handoff boundaries. SDK-backed Agent
  prompt assembly and Realtime Voice session/tool exchanges should expose
  component token estimates, signal value, lane/stage, and correlation ids
  without persisting raw prompts, transcripts, tool arguments, or tool outputs.
- Push repeated deterministic findings into code, quality gates, tests, or repo
  docs instead of relying on prompt text.

## Anti-Patterns To Avoid

- Running generated-app telemetry commands from the builder source checkout.
- Treating source repo `.env` as a global default for every generated app.
- Treating `CLAUDE_CODE_OAUTH_TOKEN` absence in `.env` as missing auth when
  `claude auth status --json` is logged in.
- Suppressing the local Claude OAuth token while trying to use Claude Agent SDK
  subscription auth.
- Requiring `ANTHROPIC_API_KEY` for the default local Claude Agent SDK lane.
- Using unsupported fully-qualified model ids when the local SDK expects aliases.
- Exporting raw prompts, raw tool inputs, raw tool outputs, secrets, or raw API
  bodies by default.
- Allowing stale logs-only Codex OTEL configs to masquerade as full telemetry.
- Treating missing Codex `tracestate`, review feedback, or analytics config as
  acceptable because log export alone is present.
- Reporting non-selected native telemetry as reachable or emitted just because a
  static config file exists.
- Hiding historical telemetry from an inactive lane when the data was already
  generated and persisted.
- Counting generated dependency paths, build artifacts, raw transcripts, or
  large forensic blobs as normal metrics output.
- Conflating a full-suite unrelated test failure with the telemetry fix under
  review.

## Exclusions

Do not include these as normal metrics or observability payloads:

- raw user prompts
- raw assistant messages
- raw tool inputs or outputs
- raw API request or response bodies
- tokens, secrets, cookies, OAuth values, or provider API keys
- generated dependency trees such as `node_modules`
- build output directories such as `dist`, coverage, cache, and bundled assets
- unbounded file lists
- full JSONL transcripts
- screenshots, audio, or large binary artifacts
- unrelated dirty worktree state unless it blocks the current analysis

It is acceptable to expose counts, hashes, bounded path samples, short error
strings, session ids, run ids, tool names, phase names, status, stop reason,
duration, token counts, and recommendation codes.

## Agent Prompt Boundary

Observability, metrics, and log analysis questions that ask "what should I fix
next" or require prioritization remain model-backed Agent work. Builder may
prepare a bounded telemetry context pack before the model turn, but it must not
replace dependent operator intent with a canned deterministic answer.

Token reduction is a telemetry optimization signal, not a reason to downgrade
the product experience. When model judgment is needed, improve the evidence
shape with compact summaries, truncation, and purpose-built tools instead of
removing the model from the decision.

Deterministic handling is reserved for exact product-state questions where the
answer is already encoded in Builder state, such as explaining a currently
visible missing observability signal. The cross-runtime policy lives in
`docs/rubric/deterministic-vs-model-backed-agent-behavior.md`.

## Output Shape

Return compact findings:

```text
Issues Fixed
- <issue>: <durable fix> [evidence command]

Patterns
- <pattern to preserve>

Anti-Patterns
- <anti-pattern to avoid>

Excluded From Metrics
- <excluded data class>: <reason>

Validation
- <command>: <result>
```

Avoid long transcript excerpts. Prefer command evidence, ids, counts, and short
paths.

## Related Docs

- ~~GOAL.md~~
- [builder-cli.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/builder-cli.md)
- [runtime-settings.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-settings.md)
- [deterministic-vs-model-backed-agent-behavior.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/rubric/deterministic-vs-model-backed-agent-behavior.md)
- [claude-agent-sdk-telemetry-observability.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/claude-agent-sdk-telemetry-observability.md)
- [realtime-voice-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/realtime-voice-integration.md)
- `$codex-productivity-auditor` at `/Users/gurusharan/.codex/skills/codex-productivity-auditor/SKILL.md`
