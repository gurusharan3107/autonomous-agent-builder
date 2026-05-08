# Modular Runtime Implementation Plan

Status: superseded by the shipped three-lane runtime contract
(`claude` / `claude_managed` / `codex_sdk`). Keep this file as a historical
note for why the runtime abstraction exists; use
[runtime-settings.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/runtime-settings.md)
and
[modular-runtime.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/modular-runtime.md)
as the current source of truth.

## Current Contract

Autonomous Agent Builder has one active agent harness per run. The user-facing
lifecycle lanes are:

| Runtime `sdk` | Auth owner | Harness owner | Status |
| --- | --- | --- | --- |
| `claude` | Claude Code auth path | `ClaudeRuntime` over Claude Agent SDK | user-facing |
| `claude_managed` | `ANTHROPIC_API_KEY` (Managed Agents beta) | `ManagedAgentsRuntime` over Anthropic Managed Agents (cloud, GitHub-backed projects only) | user-facing |
| `codex_sdk` | Codex login / subscription state | `CodexAppServerRuntime` over Codex app-server JSON-RPC | user-facing |

Compatibility adapters may remain in lower-level runtime code while migrations
are in progress, but they are not dashboard, onboarding, or sprint-validation
lanes.

## Product Invariants

- Builder owns task lifecycle, phase routing, workspace identity, backlog,
  approvals, gates, memory, knowledge, Board, Metrics, and Observability.
- The selected runtime owns only the mechanics for the next model-driven run.
- Runtime switching affects future runs only; it must not rewrite historical
  tasks, runs, metrics, observability, knowledge, memory, approvals, or backlog.
- Claude Agent SDK, Anthropic Managed Agents, and Codex SDK execute the same
  Builder-owned phase agent roles: `planner`, `designer`, `code-gen`,
  `integration-resolver`, `pr-creator`, `build-verifier`, and
  `documentation-bridge`.
- On the `claude_managed` lane, feature-verifier runs through MA Outcomes
  (rubric-graded iterate loop) instead of free-form messaging; lifecycle
  follow-up arrives via `/api/managed-agents/webhook` deduped through the
  `webhook_deliveries` table.
- Codex SDK should use app-server benefits such as thread/turn events, native
  user-input requests, token usage updates, sessions, approvals, sandboxing,
  and provider-limit detection instead of flattening to Claude behavior.

## Validation

Runtime-lane changes should run:

```bash
builder quality-gate modular-runtime --json
builder quality-gate claude-agent-sdk --json
builder quality-gate architecture-boundary --json
PYTHONPATH=src pytest tests/test_runtime_interface.py tests/test_codex_app_server_runtime.py tests/test_onboarding_runtime_selection.py tests/test_execution_policy.py -q
```

## References

- OpenAI Codex authentication: <https://developers.openai.com/codex/auth#openai-authentication>
- OpenAI Codex config: <https://developers.openai.com/codex/config-reference>
