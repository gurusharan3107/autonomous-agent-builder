# Modular Runtime Implementation Spec

## Status

Implementation companion to the shipped three-lane runtime contract
(`claude` / `claude_managed` / `codex_sdk`). See
[modular-runtime-architecture.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/design-docs/modular-runtime-architecture.md)
and
[runtime-settings.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-settings.md).

## Runtime Keys

User-facing runtime selection supports only:

- `claude`
- `claude_managed` (cloud, GitHub-backed projects only)
- `codex_sdk`

Compatibility adapters are not valid user-facing selections. If they remain in
lower-level runtime code, they must fail dashboard, onboarding, and
`builder agent runtime set` activation.

## Settings Schema

```python
class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RUNTIME_", env_file=".env", extra="ignore")

    sdk: str = "claude"  # user-facing: "claude" | "claude_managed" | "codex_sdk"
    provider: str | None = None
    model: str = "anthropic/claude-sonnet-4-5"
    api_base_url: str | None = None
    api_key_env: str | None = None
    codex_profile: str | None = None
    sandbox_mode: str = "workspace-write"
    approval_policy: str = "never"
    tracing: str = "builder"
```

Validation rules:

- `sdk=claude` requires `provider=claude_code`.
- `sdk=claude_managed` requires `provider=anthropic_managed`.
- `sdk=codex_sdk` requires `provider=codex_subscription`.
- `sdk=codex_sdk` must not require `OPENAI_API_KEY`, `api_key_env`, or
  `api_base_url`.
- `sdk=claude_managed` requires an `ANTHROPIC_API_KEY` with Managed Agents
  beta access; the runtime probe fails fast when missing.
- any other `sdk` value returns deterministic `invalid_sdk` guidance pointing to
  `claude`, `claude_managed`, or `codex_sdk`.

## Runtime Interface

`AgentRuntime` remains the adapter boundary. Every user-facing runtime must
implement:

- `run(...) -> RunResult`
- `shutdown()`
- `health_check()`
- `capabilities() -> RuntimeCapabilities`
- `probe() -> RuntimeProbeResult`

Product paths must route through `create_runtime()` instead of importing runtime
adapters directly.

## User-Facing Runtime Lanes

### Claude Runtime

`claude` wraps Builder's Claude Agent SDK runner. It owns Claude runtime
mechanics only:

- Claude Agent SDK query loop
- Claude project setting sources
- Claude permissions, tools, MCP, hooks, session resume, model, and effort

It must not own task lifecycle, backlog, approvals, gates, knowledge, memory,
Board, Metrics, or Observability semantics.

### Managed Agents Runtime

`claude_managed` is the Anthropic Managed Agents (cloud) lane. It delegates
each builder agent invocation to a hosted MA session via
`ManagedAgentsRuntime` and surfaces:

- pre-provisioned per-role agents (planner, designer, code-gen,
  feature-verifier, pr-creator, build-verifier, optimization-agent,
  repo-researcher, browser-verifier, security-reviewer, pr-reviewer,
  documentation-agent) plus multiagent rosters from `_AGENT_POLICY.subagents`
- `github_repository` resources auto-cloned per session (replaces local
  worktrees for cloud execution)
- vault-backed GitHub MCP for PR creation, with credential refresh tracked via
  webhooks
- Outcomes-based feature verification: when `runtime_sdk='claude_managed'`,
  the orchestrator's feature-verifier branch sends `user.define_outcome` (with
  a rubric synthesised from `Feature.acceptance_criteria`) instead of a
  free-form `user.message`; the rubric verdict is captured as both an
  `agent_runs` row and a `feature-verifier-outcome` `gate_results` row
- webhook-driven follow-up via `/api/managed-agents/webhook` with DB-backed
  dedupe (`webhook_deliveries` table); session/outcome/vault events resume
  `Orchestrator.dispatch` for the matching task
- a host-side `builder_memory_search` custom tool so the agent can read
  `.memory/` without projecting it into Memory Stores

It must preserve the Builder-owned phase agent roles and not own task
lifecycle, backlog, approvals, gates, knowledge, memory, Board, Metrics, or
Observability semantics.

### Codex SDK Runtime

`codex_sdk` is the product-facing Codex lane. It talks to the local Codex
app-server JSON-RPC transport and exposes Codex-specific runtime benefits:

- app-server thread and turn events
- streamed agent-message deltas
- native user-input requests
- request-permission and approval surfaces
- token usage updates
- Codex login/subscription auth, workspace tools, sandboxing, sessions, and
  provider-limit detection

It must preserve the same Builder-owned phase agent roles as Claude:
`planner`, `designer`, `code-gen`, `integration-resolver`, `pr-creator`,
`build-verifier`, and `documentation-bridge`.

## CLI Contract

Public runtime commands:

```bash
builder agent runtime show --json
builder agent runtime probe --json
builder agent runtime models --json
builder agent runtime set --sdk claude --provider claude_code --json
builder agent runtime set --sdk claude_managed --provider anthropic_managed --json
builder agent runtime set --sdk codex_sdk --provider codex_subscription --json
builder agent runtime managed-agents setup --json
builder agent runtime managed-agents vault add --name <name> --json
builder agent runtime managed-agents skill upload --path <path> --json
```

JSON failure envelopes should expose deterministic fields such as `ok`,
`status`, `code`, `message`, `next`, and `errors[]`.

## Tests

Required suites:

- `tests/test_runtime_interface.py`
- `tests/test_codex_app_server_runtime.py`
- `tests/test_onboarding_runtime_selection.py`
- `tests/test_execution_policy.py`

Key assertions:

- available runtimes are exactly `claude`, `claude_managed`, and `codex_sdk`
- compatibility adapters are not user-facing runtime lanes
- `codex_sdk` uses Codex app-server telemetry and native user-input events
- `claude_managed` resolves agent IDs from `.agent-builder/managed_agents.json`,
  opens the SSE stream before sending the kickoff event, runs
  `feature-verifier` through `user.define_outcome`, and routes the
  `builder_memory_search` custom tool to the host's `.memory/` filesystem
- webhook deliveries dedupe via the `webhook_deliveries` DB table and resume
  `Orchestrator.dispatch` when the session matches a known `AgentRun`
- runtime switching preserves Builder-owned phase agent policy shape
- product execution paths call `create_runtime()`
- onboarding and dashboard Settings mutate the same `.env` runtime keys and keep
  inactive telemetry lanes disabled

## References

- OpenAI Codex authentication: <https://developers.openai.com/codex/auth#openai-authentication>
- OpenAI Codex config: <https://developers.openai.com/codex/config-reference>
