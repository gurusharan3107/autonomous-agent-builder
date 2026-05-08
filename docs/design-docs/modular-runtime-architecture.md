# Modular Runtime Architecture

## Purpose

Support multiple agent harnesses without collapsing their authentication,
session, tool, approval, or endpoint models into one leaky abstraction.

The runtime abstraction is a harness boundary, not just a model-provider switch.
Exactly one harness is active for a run.

## Harnesses

| Harness | Runtime key | Auth | Endpoint shape | Primary use |
| --- | --- | --- | --- | --- |
| Claude Agent SDK | `claude` | Claude Code OAuth/token path | Claude Agent SDK / Claude Code | user-facing Claude lane |
| Codex SDK | `codex_sdk` | ChatGPT/Codex login | Codex app-server/SDK JSON-RPC | user-facing Codex lane with SDK/app-server telemetry |

Compatibility adapters such as `codex_cli` and `openai_agents` may remain in
lower-level runtime code while migrations are in progress, but they are not
dashboard, onboarding, or sprint-validation lanes.

## Control Plane

Builder remains the owner of:

- task lifecycle and phase routing
- workspace/worktree identity
- backlog, approvals, gates, memory, and knowledge state
- runtime choice and capability probing
- user-facing Agent page state
- normalized logs and provider-limit handling

The active harness owns only the mechanics for one model-driven run:

- model call loop
- SDK/CLI-native tools
- SDK/CLI-native streaming
- SDK/CLI-native session continuation
- SDK/CLI-native approval or interruption events

## Runtime Selection

Runtime settings resolve in this order:

1. project/runtime setting
2. explicit CLI/API override for a probe
3. process environment default
4. hard default: `sdk=claude`

The selected runtime must pass a probe before becoming active. A probe checks
auth, model availability, minimal prompt execution, streaming shape if enabled,
and whether required tool/capability surfaces are supported.

## Capability Profile

Each runtime reports a capability profile:

- `chat`
- `streaming`
- `tools`
- `mcp`
- `subagents`
- `workspace_access`
- `shell`
- `sandboxing`
- `approvals`
- `session_resume`
- `subscription_auth`
- `api_key_auth`
- `model_listing`
- `provider_limit_detection`
- `tracing`

Product code must consult the profile instead of assuming Claude behavior. If a
capability is missing, the orchestrator must block or degrade through product
state rather than silently falling back to another runtime.

## Runtime Boundaries

### Claude Runtime

Claude mode preserves existing behavior:

- Claude Agent SDK import and query loop
- Claude Code OAuth/token path
- OneCLI integration where configured
- `can_use_tool`, Claude hooks, Claude MCP server builders
- Claude session resume
- Claude model/effort policy

None of this should be loaded for the Codex SDK lane.

### Codex SDK Runtime

`codex_sdk` is the product-facing selector for the Codex SDK/app-server
contract. It must not shell through `codex exec`. The Python runtime adapter
talks to the local `codex app-server` JSON-RPC transport, which is the same deep
integration surface used by rich Codex clients and the experimental Python SDK.

The SDK lane exposes Codex-specific benefits instead of lowest-common-denominator
Claude parity:

- app-server thread and turn events
- streamed `item/agentMessage/delta`
- native `item/tool/requestUserInput` prompts for onboarding interviews
- MCP elicitation and request-permission surfaces
- token usage updates from `thread/tokenUsage/updated`
- Codex login/subscription auth, workspace tools, sandboxing, approvals,
  sessions, and provider-limit detection

If a future Node or Python SDK package wrapper replaces the direct JSON-RPC
adapter, it must preserve the same normalized `RunResult` metrics,
observability fields, and Agent-page question-card behavior.

Codex subscription auth does not provide a run-level dollar cost in runtime
usage events. The builder records tokens, turns, duration, reasoning tokens, and
`cost_source=subscription_unmetered` instead of fabricating a cost.

If a future generic AI SDK lane is useful, treat it as a separate product
decision. It should not be used to represent Codex subscription auth.

## Data Flow

```text
Agent page / orchestrator
  -> RuntimeSettings
  -> RuntimeFactory
  -> one active AgentRuntime
  -> harness-specific execution
  -> normalized RunResult
  -> builder-local history, gates, metrics, capability-limit state
```

## Failure Policy

Auth, quota, rate limit, unsupported model, unsupported tool, sandbox denial,
and malformed event streams must be normalized into deterministic builder errors.
Provider-limit-like failures should use the existing `capability_limit` path and
preserve the task's phase resume target.

## Implementation Order

The initial implementation is complete. Future changes should preserve this
shape:

1. Runtime settings/probe service and CLI.
2. Product paths routed through `create_runtime()`.
3. Codex app-server/SDK runtime adapter.
4. Dashboard Settings and first-run onboarding runtime selection.
5. Runtime-specific quality gates and telemetry normalization.

The dashboard/settings copy contract lives in
[runtime-settings.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-settings.md).
The review contract lives in
[modular-runtime.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/modular-runtime.md).

## References

- OpenAI Codex authentication: <https://developers.openai.com/codex/auth#openai-authentication>
- OpenAI Codex config: <https://developers.openai.com/codex/config-reference>
