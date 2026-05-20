---
title: "Claude Agent SDK Integration"
tags: ["claude", "agent-sdk", "authentication", "onboarding", "knowledge-base", "runtime"]
doc_type: "documentation"
created: "2026-04-19"
---

# Claude Agent SDK Integration

## Purpose

This document describes how `autonomous-agent-builder` integrates Claude-backed
agent execution when the selected runtime is `sdk=claude`.

It is repo-specific. It explains the actual local code paths, backend-selection
rules, onboarding dependency, and configuration expected by this repository.

For the runtime-selection contract across the user-facing `claude` and
`codex_sdk` lanes, see
[runtime-settings.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-settings.md)
and
[modular-runtime-architecture.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/design-docs/modular-runtime-architecture.md).

For the canonical repo-local telemetry and observability policy, including the
recommended split between builder-local history and OTEL structural signals,
see
[claude-agent-sdk-telemetry-observability.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/claude-agent-sdk-telemetry-observability.md).

For the repo-local contract that decides which reduced runtime signals may feed
optimization or introspection recommendations, see
[agent-optimization-analysis.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/agent-optimization-analysis.md).

## Scope

This document is scoped to Claude lanes only. The user-facing Codex lane is
`codex_sdk`; compatibility adapters do not inherit Claude Agent SDK hooks,
permissions, MCP wiring, OneCLI bootstrap, or Claude project-instruction
loading.

The Claude runtime uses Claude in two supported lifecycle ways:

1. multi-turn agent execution through the Claude Agent SDK
2. one-shot local Claude calls through the repo helper in
   `src/autonomous_agent_builder/claude_runtime.py`, also through the embedded
   SDK query path

Deprecated local CLI helper code may remain for compatibility diagnostics, but
it is not a user-facing runtime lane and must not be used for sprint validation.

## Integration Map

| Surface | File | Role |
|------|------|------|
| Runtime adapter | `src/autonomous_agent_builder/runtime/claude_runtime.py` | `AgentRuntime` adapter around `AgentRunner` for `sdk=claude` |
| Runtime helper | `src/autonomous_agent_builder/claude_runtime.py` | Claude backend selection, availability probe, one-shot prompt execution |
| Main agent runner | `src/autonomous_agent_builder/agents/runner.py` | Multi-turn SDLC agent execution via `claude_agent_sdk.query()` |
| OneCLI runtime bootstrap | `src/autonomous_agent_builder/onecli_runtime.py` | Fetches local OneCLI proxy, CA, and placeholder auth env for Claude child processes |
| SDK builder service bridge | `src/autonomous_agent_builder/services/builder_tool_service.py` | Shared builder-facing service layer used by SDK MCP tools without CLI shell-outs |
| SDK MCP adapter | `src/autonomous_agent_builder/agents/tools/sdk_mcp.py` | Registers builder and workspace MCP tools and delegates builder operations to shared services |
| KB quality gate | `src/autonomous_agent_builder/knowledge/agent_quality_gate.py` | Claude-backed KB evaluation via `run_claude_prompt()` |
| Onboarding preflight | `src/autonomous_agent_builder/onboarding.py` | Blocks onboarding before repo work starts if Claude is unavailable |
| Onboarding KB relay | `src/autonomous_agent_builder/onboarding.py` | Runs canonical `builder knowledge extract --json` through Claude |
| Runtime factory | `src/autonomous_agent_builder/runtime/factory.py` | Selects `ClaudeRuntime` only when `RUNTIME_SDK=claude` |
| Settings | `src/autonomous_agent_builder/config.py` | Runtime selection, model, permission mode, and Claude helper backend selection |
| Env bootstrap | `src/autonomous_agent_builder/main.py`, `src/autonomous_agent_builder/cli/main.py` | Loads repo `.env` so server and standalone CLI commands can inherit local auth env vars |

## Ownership Contract

This repo's mission is product-owned software delivery through a simple chat
surface, not a thin wrapper over agent tooling. That means the product and the
agent runtime have different responsibilities.

### `builder` owns the product contract

`builder` is the repo-local product lane. It should own:

- delivery state and the visible SDLC model
- backlog, feature, task, and approval semantics
- quality-gate records and reviewable evidence
- repo-local knowledge-base and memory contracts
- repo-local workflow selection and delivery-state transitions as exposed to the
  user

For repo-local KB state, that means:

- seed docs are regenerated through `builder knowledge extract`
- maintained docs are created or refreshed through `builder knowledge add` or
  `builder knowledge update`
- Claude-backed runtime lanes may decide content, but the durable mutation
  still flows through builder-owned KB tools and schemas

### Claude Agent SDK owns Claude runtime execution

When `RUNTIME_SDK=claude`, the Claude Agent SDK should own:

- multi-turn agent execution
- tool calling and MCP integration
- hooks and permission handling
- session chaining, streaming, and runtime error surfaces

It should not become the owner of:

- task lifecycle semantics
- backlog or approval policy
- KB or memory schema
- the product's SDLC operating model

### `CLAUDE.md` owns SDK project instructions

Project `CLAUDE.md` files are the always-loaded runtime guidance for Claude
Agent SDK sessions when project setting sources are enabled. They should contain
project conventions, build and test commands, architecture boundaries, and
short workflow rules that the Claude runtime must always know.

This Claude-specific rule does not make `CLAUDE.md` the project-instruction
loader for `codex_sdk`. That harness has its own prompt, session, tool,
approval, and settings mechanics behind the shared `AgentRuntime` interface.

`AGENTS.md` is not the Claude runtime surface. In the
`autonomous-agent-builder` repo it is the Codex operator surface for optimizing
the builder itself; in a target repo selected for Codex SDK execution it is the
Codex project-instruction baseline. Do not copy Codex routing, subagent, or
control-plane instructions into Claude runtime prompts or target-repo
`CLAUDE.md` files.

Day-0 initialization must create a workflow-specific target-repo `CLAUDE.md`
when neither `CLAUDE.md` nor `.claude/CLAUDE.md` exists. Forward-engineering
repos receive a scaffolded known/unknown runtime contract with deterministic
command slots; reverse-engineering repos receive a discovery-oriented contract
with preservation rules and detected entrypoint or command evidence where
available. When `RUNTIME_SDK` is `codex_sdk`, the equivalent baseline is
target-repo `AGENTS.md`; switching between Claude and Codex lanes
migrates a builder-generated baseline between `CLAUDE.md` and `AGENTS.md`.
Existing user-authored project guidance must be preserved.

Readiness must block autonomous work when project runtime guidance is absent.
It must also verify the repo-local telemetry contract:
Claude OTEL env is the Claude runtime-native lane, Codex project-local
`.codex/config.toml` is the Codex runtime-native lane, and builder active-DB
events remain the product telemetry source of truth. Raw prompt, tool, and API
body export stays disabled by default. A missing local OTEL collector is not a
blocking readiness failure when the selected lane is Codex. When any selected
runtime points at a loopback collector endpoint, readiness and observability
must distinguish configured from reachable collector state before treating
exported telemetry as usable.

When `RUNTIME_SDK=claude`, runtime SDK calls should make this dependency
explicit: use the Claude Code preset system prompt and project setting sources
so the target repository's `CLAUDE.md` is loaded by design, not only by SDK
defaults. Keep user/global Claude preferences out of builder-owned autonomous
execution unless a future policy deliberately enables them.

### Codex subagents are optional specialist lanes

Codex subagents are useful for bounded, opt-in parallel or specialist review
work. In this repo they should be treated as secondary lanes such as
architecture review, not as the primary execution architecture for the product.

## Current Internal Boundary

The external command and JSON contract can remain `builder`-shaped even when
the internal implementation changes. The preferred internal boundary is:

- shared application or domain services own product semantics
- `builder` CLI is one adapter over those services
- HTTP routes are another adapter
- SDK MCP tools are another adapter

Current implementation shape:

- `sdk_mcp.py` registers the Claude Agent SDK MCP tools
- those tools call `services/builder_tool_service.py`
- that service preserves the builder JSON contract while talking directly to
  builder-owned HTTP and filesystem surfaces
- `ToolRegistry` must advertise the same bounded parameters as the actual SDK
  MCP tool schemas. For example, workspace `read_file` exposes `start_line` and
  `max_lines` so agents can discover file slicing instead of dumping whole
  files by default.
- workspace file and directory tools must enforce containment with resolved
  path semantics. Sibling-prefix paths and symlinks that resolve outside the
  task workspace are rejected before file or directory existence checks. Use
  the shared `services.path_containment.resolve_contained_path` helper for
  filesystem trust boundaries instead of string-prefix comparisons.
- workspace `run_tests`, `run_linter`, and argv-safe `run_command` tools must
  run with explicit bounded timeouts and process-tree cleanup. Timeout results
  report `exit_code: 124`, `timeout: true`, `killed: true`, and
  `code: command_timeout` so the Agent page can recover instead of hanging.
- the `builder` CLI remains a user and automation adapter, not the runtime's
  internal transport between builder and the SDK
- KB tools exposed to the runtime should preserve the same repo-local schema
  and mutation semantics as `builder knowledge add/update/search/show`

The least desirable long-term boundary is using CLI subprocesses as the main
internal integration path between runtime components. CLI subprocesses are fine
as external user or automation surfaces, but they are not the ideal internal
service boundary for the product.

## Current Backend Rules

`claude_runtime.resolve_claude_backend()` implements the current helper policy:

| `AGENT_AUTH_BACKEND` | Meaning |
|------|------|
| `auto` | Use the embedded SDK helper lane |
| `cli` | Deprecated compatibility mode for local one-shot helper diagnostics only; not a lifecycle lane |
| `sdk` | Force embedded SDK query path for one-shot helper lanes |

Notes:

- This backend switch applies to helper-driven one-shot lanes.
- Sprint execution and runtime switching use Claude Agent SDK or Codex SDK
  lanes only; local Claude CLI and Codex CLI paths are not validation lanes.
- `AgentRunner` in `agents/runner.py` still uses the embedded SDK directly for
  multi-turn agent execution.
- Onboarding currently depends on Claude availability regardless of which helper
  backend is selected.

## App Learnings

These learnings were validated in the app's real onboarding and KB flows.

### Deprecated CLI helper ordering is compatibility-only

If the deprecated CLI-backed helper path is explicitly forced for a diagnostic,
the prompt must appear immediately after `claude -p` and before any variadic
tool flags. This is not the Claude Agent SDK lifecycle lane.

Current shape:

```text
claude -p "<prompt>" --output-format text --model <model> --permission-mode <mode> [--tools ...] [--allowed-tools ...]
```

Why:

- placing the prompt after variadic tool flags can cause current `claude` to
  treat the prompt like another tool argument
- the observed failure mode was a false no-input error during onboarding-owned
  helper calls

Validation:

- `tests/test_claude_runtime.py::test_run_claude_cli_prompt_places_prompt_before_tool_flags`

### Availability probes must stay tool-free

`check_claude_availability()` intentionally ignores requested tools and probes
Claude with a minimal prompt only.

Why:

- onboarding only needs a backend-reachable minimal response, not full task execution
- tool-free probing avoids fragile coupling to Bash/tool flag parsing
- with `AGENT_AUTH_BACKEND=auto`, the probe now follows the same default SDK lane
  as the product's multi-turn runtime instead of opportunistically preferring a
  local CLI binary
- this keeps preflight failures attributable to availability instead of command
  shape

Validation:

- `tests/test_claude_runtime.py::test_check_claude_availability_uses_minimal_prompt`
- `tests/test_claude_runtime.py::test_resolve_claude_backend_auto_prefers_sdk`
- `tests/test_claude_runtime.py::test_resolve_claude_backend_auto_falls_back_to_cli`

### KB extraction should not preflight Claude on every command

`builder knowledge extract` should run its deterministic extraction and validation flow
without a separate Claude availability stop-check.

Why:

- onboarding already owns the hard Claude preflight
- routine KB extraction should stay deterministic-first and work offline
- agent-backed advisory should be best-effort rather than a gate on every extract

Validation:

- `tests/test_kb_publisher.py::test_kb_extract_does_not_require_claude_preflight`
- `tests/test_onboarding_api.py::test_onboarding_agent_kb_command_uses_plain_extract_contract`

### Helper lanes and runner lanes should be debugged separately

This repo deliberately splits Claude usage into:

- helper lanes: bounded one-shot prompts via `run_claude_prompt()`
- runner lanes: multi-turn execution via `claude_agent_sdk.query()`

Operational implication:

- `AGENT_AUTH_BACKEND=auto` and `AGENT_AUTH_BACKEND=sdk` keep helper behavior
  on the SDK lane
- `AGENT_AUTH_BACKEND=cli` is deprecated compatibility behavior for helper
  diagnostics only
- it does not convert `AgentRunner` into a CLI-only path
- fixes in `claude_runtime.py` should not be assumed to change
  `agents/runner.py`

### SDK request options must match the installed SDK and selected model lane

`AgentRunner` builds `ClaudeAgentOptions` for the multi-turn Claude Agent SDK
lane. Keep those options limited to fields accepted by the active installed SDK
and selected Claude Code lane model.

Current rule:

- pass tool policy, system prompt preset, project setting source, MCP servers,
  permission mode, model, cwd, turn and cost bounds, SDK subagents, effort, and
  thinking policy when supported
- do not pass user-configurable `task_budget` into `ClaudeAgentOptions` for the
  current Claude Code lane models
- keep task pacing, token-budget rationale, and phase budget decisions in
  Builder runtime policy evidence instead of sending rejected SDK request fields

Why:

- unsupported SDK/model options can cause model-backed runs to fail before any
  useful tool activity happens
- a failed run with zero tokens, zero cost, no tool events, or SDK/API error
  text in assistant output is not useful product evidence
- recoverable SDK errors such as missing Claude login must return clean Builder
  JSON without leaking async generator or SDK cleanup tracebacks before the JSON
  envelope
- Builder still owns the lifecycle budget policy even when the runtime lane
  cannot accept a particular SDK option

Validation:

- `tests/test_agent_runner.py::test_execute_query_uses_sdk_client_receive_response`
- `tests/test_agent_runner.py::test_execute_query_exposes_full_tool_set_when_can_use_tool_is_present`
- `tests/test_claude_runtime.py::test_run_claude_sdk_prompt_drains_error_result_before_raising`

## Local Authentication Contract

### OneCLI Runtime Boundary

This repo now supports OneCLI as the preferred runtime boundary when Claude
child processes need provider access without receiving real provider tokens.

Enable it with non-secret local configuration:

```bash
export AAB_ONECLI_ENABLED=true
export ONECLI_URL=http://127.0.0.1:10254
```

Optional settings:

| Setting | Default | Purpose |
|------|------|------|
| `ONECLI_API_KEY` | unset | App-to-OneCLI API key if the OneCLI instance requires it |
| `ONECLI_AGENT` / `AAB_ONECLI_AGENT` | unset | Existing OneCLI agent identifier to request from `/api/container-config` |
| `AAB_ONECLI_FAIL_CLOSED` | `false` | Fail Claude runtime bootstrap when OneCLI is unavailable |

Runtime behavior:

- `src/autonomous_agent_builder/onecli_runtime.py` calls the local OneCLI
  `/api/container-config` endpoint once per Claude launch.
- `src/autonomous_agent_builder/claude_runtime.py` passes the returned env into
  the SDK helper lane.
- `src/autonomous_agent_builder/agents/runner.py` passes the returned env into
  the main multi-turn Claude Agent SDK runner.
- the child process receives OneCLI proxy and CA settings plus placeholder auth
  values such as `CLAUDE_CODE_OAUTH_TOKEN=placeholder`.
- if OneCLI is active, direct provider env vars inherited from the parent are
  overwritten with placeholder values before spawning Claude.

Owner boundary:

- builder owns fetching and applying OneCLI runtime env before Claude launch
- Claude Agent SDK owns cwd, permissions, hooks, MCP, sessions, and the agent loop
- OneCLI owns proxy URLs, CA material, agent tokens, and provider-secret
  injection at request time

Do not put real `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` values in
repo `.env` for the Claude runtime lane once OneCLI is enabled. Keep `.env` to
non-secret local routing config such as `AAB_ONECLI_ENABLED=true` and
`ONECLI_URL=http://127.0.0.1:10254`.

### What This Repo Supports

For local development, this repo supports Claude-backed lifecycle work through
the embedded Claude Agent SDK path. The supported auth model should follow
Claude Code's documented surfaces first.

Current local assumptions:

- the local Claude session is authenticated through Claude Code's supported auth flow
- repo `.env` loading is a convenience for local process inheritance and
  non-secret local routing config, not the primary documented vendor contract

`src/autonomous_agent_builder/main.py` and `src/autonomous_agent_builder/cli/main.py`
load repo `.env` so local subprocess-backed lanes can inherit env vars when
present.

### What Is Repo Truth vs Vendor Doc Truth

Repo truth:

- this codebase explicitly supports Claude Agent SDK-backed lifecycle calls
- this codebase now loads repo `.env` for both app and standalone `builder` CLI execution
- this codebase can use OneCLI to replace real provider-token inheritance with
  runtime proxy, CA, and placeholder env for Claude child processes
- onboarding is intentionally disabled when Claude is unavailable

Vendor-doc truth:

- Anthropic documents Claude Code auth by running `claude` and completing the login flow
- Anthropic documents `claude setup-token` as the supported long-lived token setup path
- Anthropic documents credential storage in macOS Keychain and `apiKeyHelper` / settings-based configuration
- Anthropic does not document `CLAUDE_CODE_OAUTH_TOKEN` as the primary public project-level auth contract for Claude Code

Treat `.env`-based token inheritance here as a repo convenience layer over the
documented Claude Code auth model, not as the canonical vendor contract.

## Required Local Configuration

### Minimum

For local Claude-backed onboarding and KB lanes, the product-facing runtime is
the Claude Agent SDK. Local subscription-backed auth uses
`CLAUDE_CODE_OAUTH_TOKEN`; do not make `ANTHROPIC_API_KEY` part of the default
builder contract.

You need:

- Claude Agent SDK installed in the repo environment
- `CLAUDE_CODE_OAUTH_TOKEN` available in the process environment or repo `.env`
  for local subscription-backed runs
- if you use repo `.env`, the relevant entrypoint must load it before starting
  the SDK-backed agent turn

### Repo Settings

Relevant runtime settings currently live in `AgentSettings`:

| Setting | Default | Purpose |
|------|------|------|
| `AGENT_IMPLEMENTATION_MODEL` | `sonnet` | Model for helper-driven Claude work and onboarding KB relay |
| `AGENT_PERMISSION_MODE` | `acceptEdits` | Permission mode passed to Claude SDK helper runs |
| `AGENT_AUTH_BACKEND` | `auto` | Helper backend selection: `auto` and `sdk` use the SDK lane; `cli` is deprecated compatibility |

Permission posture:

- Default to `acceptEdits` because this app runs agents inside isolated repo or workspace directories.
- Keep repo hooks as the hard deny layer for repo-specific boundaries.
- Do not treat `dontAsk` or `bypassPermissions` as the normal local mode.

Recommended local mode when you want subscription-backed local usage:

```bash
export AGENT_AUTH_BACKEND=sdk
export AGENT_PERMISSION_MODE=acceptEdits
```

Local env inheritance for automation:

```bash
export CLAUDE_CODE_OAUTH_TOKEN=...
```

or place it in `.env`. This works only because this repo loads `.env` in both
the server and standalone CLI entrypoints. Prefer the OneCLI runtime boundary
when the goal is to avoid storing real provider tokens in repo-local files; when
OneCLI is disabled, the SDK child process inherits the real local token.

## Onboarding Contract

Onboarding now treats Claude as a hard prerequisite.

Current behavior in `src/autonomous_agent_builder/onboarding.py`:

1. `start_onboarding()` loads state
2. `_preflight_onboarding_claude()` probes Claude availability before pipeline work
3. if Claude is unavailable, onboarding stops immediately
4. `repo_detect` is marked `blocked`
5. the dashboard state stays not-ready with a Claude-unavailable message

This is intentional. Onboarding must not partially run and then fail later in
KB extraction because that leaves the repo in a misleading half-onboarded state.

Operational takeaway:

- once the Claude availability phase passes, later onboarding failures should be
  debugged as command-contract, delegation, or content-quality problems first
- after the recent fixes, the KB lane regressions were caused by command shape
  and quality gates, not by generic Claude unavailability

## KB Integration Contract

### Canonical Surface

The canonical KB orchestration command remains:

```bash
builder knowledge extract --force --json
```

That command is consumed by onboarding and other automation surfaces through its
machine-readable contract.

### Claude Dependency

`builder knowledge extract` no longer preflights Claude availability before running
the extraction pipeline. It runs deterministic extraction first and treats
agent-backed advisory as best-effort.

Current behavior:

- extraction and deterministic validation remain authoritative
- `builder knowledge validate` is deterministic by default
- Claude-backed review is opt-in advisory via `builder knowledge validate --use-agent`
- onboarding keeps the hard Claude preflight at the workflow level

### Quality Gate

`builder knowledge validate` distinguishes:

- deterministic validation as the blocking contract
- agent-backed advisory as an optional follow-up lane

`knowledge/agent_quality_gate.py` currently routes its Claude calls through
`run_claude_prompt()`. That means the quality gate follows the same helper
backend rules as the repo runtime helper.

## Multi-Turn Agent Execution

`src/autonomous_agent_builder/agents/runner.py` is the core multi-turn path.

Current behavior:

- imports `claude_agent_sdk` at call time
- builds `ClaudeAgentOptions`
- wires repo safety hooks through `HookMatcher`
- resolves a phase policy with model, effort, thinking budget, context strategy,
  selected subagents, permission policy, hook policy, and reason code
- streams `AssistantMessage` text
- captures `ResultMessage` cost, usage, and stop reason
- persists the resolved runtime policy inside run observability evidence
- maps SDK-specific failures into repo error types

This path is not currently routed through `claude_runtime.py`. That is a
deliberate distinction:

- helper lanes optimize for bounded, one-shot Claude work
- runner lanes optimize for full agent execution with hook wiring and session
  chaining

### Permission and Hook Boundaries

Current repo posture:

- SDK permission mode defaults to `acceptEdits`
- the working directory boundary is the repo or task workspace passed as `cwd`
- repo hooks still run before or alongside permission handling and can deny tool calls
- scratch-space writes are allowed in the workspace, the system temp dir, and `/tmp`
- direct KB writes remain blocked; KB mutation must go through the builder publish lane
- Bash is intentionally narrower than raw shell access because the repo validates command shape in `PreToolUse`

Anthropic-aligned interpretation:

- use `acceptEdits` when the agent is operating inside an isolated directory
- use hooks for deterministic repo-specific rules
- use `canUseTool` only if this app later needs dynamic runtime approvals beyond hook policy
- include `AskUserQuestion` in explicit top-level tool lists when the lane may
  need clarification; do not rely on prompt text alone to create that capability

### Specialist Subagent Policy

Claude SDK subagents are used only as bounded sidecar specialists. They should
not own product state, phase movement, or user questioning.

Current specialist definitions live in
`src/autonomous_agent_builder/agents/definitions.py`:

| Subagent | Use |
|---|---|
| `repo-researcher` | read-only architecture, ownership, and repo evidence |
| `browser-verifier` | browser-visible acceptance and UI regression evidence |
| `build-verifier` | deterministic build, lint, test, and changed-file evidence |
| `security-reviewer` | permission, data, credential, egress, and state-boundary risk |
| `pr-reviewer` | PR-readiness evidence and residual risk |
| `documentation-agent` | bounded KB and maintained-doc refresh |
| `optimization-agent` | post-ship review of observability recommendations and one bounded delivery-system optimization |

`src/autonomous_agent_builder/agents/execution_policy.py` owns which phase gets
which specialist. The product rule is stable: specialists provide structured
evidence to the parent run; they do not ask the user, create hidden state
transitions, or replace builder-owned gates.

### Post-ship optimization agent

When a sprint reaches `shipped`, builder may invoke the top-level
`optimization-agent` against the shipped task as a background delivery-system
review. This is intentionally a model turn, not a deterministic auto-fix:

- deterministic recommendation rules identify candidate optimizations from
  structured facts
- the optimization agent reads observability, metrics, logs, and quality-gate
  evidence
- it chooses at most one recommendation to implement
- it leaves sprint state, approval state, backlog scope, runtime selection, and
  shipped feature behavior owned by the orchestrator
- it emits structured JSON evidence, including `implemented`, `skipped`, or
  `blocked`

This follows the SDK guidance to use programmatic subagents for focused,
context-isolated sidecar evidence while keeping lifecycle ownership in the
parent application. The optimization agent can use `repo-researcher`,
`build-verifier`, and `security-reviewer` as bounded sidecars, but those
subagents do not own the optimization decision or any product state mutation.

### Product Gates For Claude Path Changes

Claude runtime changes can affect more than SDK mechanics. Use these gates when
the change reaches the corresponding product surface:

- `builder quality-gate claude-agent-sdk --json` for Claude SDK mechanics,
  permissions, hooks, MCP, sessions, and runtime setup.
- `builder quality-gate product-lifecycle --json` for backlog, board, sprint,
  approval, execution, recovery, or continuation behavior.
- `builder quality-gate state-integrity --json` for DB canonical state,
  projections, telemetry, events, migrations, or post-mutation checks.
- `builder quality-gate dashboard-ux --json` for user-visible pages, buttons,
  runtime switching, metrics, and observability panels.
- `builder quality-gate architecture-invariants --json` for domain model,
  layering, adapters, orchestrator ownership, and event-model changes.

## Safe Local Run Patterns

### Check Local Claude Availability

```bash
builder agent runtime probe --json
```

Equivalent helper expectation:

- bounded prompt
- no tools required
- fast failure if Claude is unavailable

### Start App With OneCLI Runtime Injection

```bash
export AGENT_AUTH_BACKEND=sdk
export AAB_ONECLI_ENABLED=true
export ONECLI_URL=http://127.0.0.1:10254
python -m autonomous_agent_builder
```

### Expected Onboarding Outcome

- if Claude works: onboarding can proceed
- if Claude does not work: onboarding is blocked immediately with a clear state

## Unsupported Assumptions

Do not assume:

- Anthropic has a dedicated public SDK doc for local subscription auth in this
  exact embedded-repo pattern
- onboarding can succeed without Claude and "fix itself later"
- helper backend selection automatically changes `AgentRunner` multi-turn SDK
  execution
- that `AGENT_AUTH_BACKEND=cli` is a supported lifecycle lane
- a post-preflight onboarding failure automatically means Claude auth is broken
- nested Claude calls are safe by default because each individual command works
  when run manually
- OneCLI is active just because the local ports are listening; set
  `AAB_ONECLI_ENABLED=true` or provide `ONECLI_URL` / `ONECLI_API_KEY`

## Vendor References

- [Claude Code advanced setup](https://code.claude.com/docs/en/getting-started)
- [Claude Code settings](https://code.claude.com/docs/en/settings)
- [Claude Code IAM and credential management](https://code.claude.com/docs/en/team)

## Source References

- [claude_runtime.py](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/claude_runtime.py)
- [runner.py](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/agents/runner.py)
- [onboarding.py](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/onboarding.py)
- [agent_quality_gate.py](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/knowledge/agent_quality_gate.py)
- [config.py](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/config.py)
- [onecli_runtime.py](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/onecli_runtime.py)
- [main.py](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/main.py)
- [cli/main.py](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/cli/main.py)

## Related Docs

- [knowledge-extraction.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/knowledge-extraction.md)
- [quality-gate/knowledge-base.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/knowledge-base.md)
- [autonomous-lifecycle-validation.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/autonomous-lifecycle-validation.md)
