# Modular Runtime Implementation Spec

## Status

Superseded by the shipped two-lane runtime contract. This spec remains the
implementation-level companion to
[modular-runtime-architecture.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/design-docs/modular-runtime-architecture.md)
and
[runtime-settings.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-settings.md).

## Runtime Keys

User-facing runtime selection supports only:

- `claude`
- `codex_sdk`

Compatibility adapters are not valid user-facing selections. If they remain in
lower-level runtime code, they must fail dashboard, onboarding, and
`builder agent runtime set` activation.

## Settings Schema

```python
class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RUNTIME_", env_file=".env", extra="ignore")

    sdk: str = "claude"  # user-facing: "claude" | "codex_sdk"
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
- `sdk=codex_sdk` requires `provider=codex_subscription`.
- `sdk=codex_sdk` must not require `OPENAI_API_KEY`, `api_key_env`, or
  `api_base_url`.
- any other `sdk` value returns deterministic `invalid_sdk` guidance pointing to
  `codex_sdk` or `claude`.

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
builder agent runtime set --sdk codex_sdk --provider codex_subscription --json
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

- available runtimes are exactly `claude` and `codex_sdk`
- compatibility adapters are not user-facing runtime lanes
- `codex_sdk` uses Codex app-server telemetry and native user-input events
- runtime switching preserves Builder-owned phase agent policy shape
- product execution paths call `create_runtime()`
- onboarding and dashboard Settings mutate the same `.env` runtime keys and keep
  inactive telemetry lanes disabled

## References

- OpenAI Codex authentication: <https://developers.openai.com/codex/auth#openai-authentication>
- OpenAI Codex config: <https://developers.openai.com/codex/config-reference>
