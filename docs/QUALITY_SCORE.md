# Quality Score

Last audit: 2026-05-15

Scope: code-review and operator validation rating for Autonomous Agent Builder
itself. Managed-app validation used the todo app workspace; the builder source
repo was not used as a managed/generated app.

## Rating Scale

| Score | Meaning |
| --- | --- |
| 9.5-10 | Production-grade: deterministic owner surface, covered by tests/gates, browser-visible when user-facing, and no known material operator-risk gap. |
| 8.5-9.4 | Strong: main workflow works and is tested, but one material edge, evidence gap, or maintainability issue remains. |
| 7.0-8.4 | Usable but below target: repeated manual diagnosis, degraded reporting, unclear owner state, or missing validation coverage remains. |
| Below 7.0 | Not acceptable for autonomous operation: correctness or operator trust can fail in normal use. |

Target for every area: 9.5+.

## Current Scores

| Area | Current | Target | Evidence | Required change to reach 9.5+ |
| --- | ---: | ---: | --- | --- |
| Runtime result correctness | 9.5 | 9.5 | Samantha routing was proven correct: `delegate_to_builder_agent` completed while the old runtime rendered a duplicate final answer as `run_error`. Codex app-server now ignores `turn.error` only when it duplicates final output, and tests cover the case. | Keep the duplicate-error regression test and monitor `builder logs --error --json` for non-duplicate runtime errors. |
| Context and transport resilience | 9.2 | 9.5 | Realtime/Agent recent-context reinjection is capped, chunk-limit retry now starts a fresh Codex app-server thread, and the managed-app replay completed without a new `run_error`. Metrics still report `agent-chat` as the largest avoidable token driver. | Finish full tool-output truncation before reinjection and promote the repeated state lookup shortcut into a stable deterministic path. |
| Deterministic retrieval and CLI ergonomics | 9.3 | 9.5 | Metrics expose bounded raw payload access and point `next_step` / `actionable_next` at resolvable `builder logs analyze --session ... --json` commands. Local fallback now reports fallback reason/base URL. | Persist generated recommendation candidates and expose a direct review command or dashboard queue. |
| Observability trust | 9.4 | 9.5 | Runtime-native telemetry health, context budget, chunk pressure, top cost drivers, and Realtime voice ledger signals are present. Official OpenAI Codex app-server and Realtime docs were checked against the implementation. | Make recommendation lifecycle state first-class instead of inferring it from optimization-agent output text. |
| Recommendation persistence | 8.4 | 9.5 | `builder_recommendations` exists and `recommendation_create` can file review items, but metrics-derived deterministic recommendations are not yet reliably persisted for maintainer review. | Persist deterministic recommendation candidates with status, evidence, owner lane, and review affordances. |
| Managed-app lifecycle validation | 9.6 | 9.5 | Browser validation used the todo app managed workspace on isolated port `9877`, left active port `9876` untouched, and verified natural Samantha prompts through visible Voice/Conversation surfaces. | Keep this as the required validation lane for future product-facing Builder changes. |

Overall rating: **9.35/10**. The system is strong enough for continued
operator use, but not yet 9.5+ overall because recommendation persistence and
full pre-reinjection output truncation remain incomplete.

## Evidence

- Official docs validation:
  - OpenAI Codex app-server docs confirm `thread/start` creates a new thread,
    `thread/resume` appends to an existing thread, and `thread/fork` copies
    stored history. The chunk-limit retry therefore uses a fresh thread.
  - OpenAI Realtime docs confirm text input via `conversation.item.create`
    followed by `response.create`, and tool results via
    `function_call_output` with the same `call_id`.
- Browser-visible managed-app proof:
  - Isolated patched server on `http://127.0.0.1:9877/` rendered the Agent
    dashboard using the todo app DB and dashboard assets.
  - Active managed app server remained on `9876`; the isolated proof server was
    stopped after validation.
  - Operator prompt `What should we fix next?` used bounded
    `get_builder_agent_update`, not a full Agent run.
  - Operator prompt `Can you look into why the last run failed and tell me what
    to fix?` completed without adding a new `run_error`.
- Runtime regression validation:
  - `uv run pytest tests/test_builder_cli_surfaces.py tests/test_embedded_agent_routes.py tests/test_codex_app_server_runtime.py tests/test_realtime_voice_operator.py -q`
    passed with 299 tests.
  - `uv run pytest tests/test_codex_app_server_runtime.py tests/test_realtime_voice_operator.py tests/test_realtime_voice_frontend_static.py tests/test_embedded_agent_routes.py -q`
    passed with 166 tests.
  - `uv run pytest tests/test_runtime_interface.py tests/test_codex_app_server_runtime.py tests/test_onboarding_runtime_selection.py tests/test_execution_policy.py -q`
    passed with 86 tests.
- Quality gates:
  - `builder quality-gate builder-cli --json` passed.
  - `builder quality-gate claude-agent-sdk --json` passed.
  - `builder quality-gate product-lifecycle --json` passed.
- Style and patch hygiene:
  - `uv run ruff check` passed on touched Python runtime/CLI/test surfaces.
  - `git diff --check` passed.

## Root Cause

The original Samantha error was not a routing failure. Samantha delegated to
Builder and the Realtime tool output completed successfully. The runtime adapter
treated duplicated Codex app-server `turn.error` text as authoritative even when
the same text had already streamed as the final answer. That is now guarded.

The later live failure was a separate transport-history issue: chunk-limit retry
reused the same resumed Codex app-server thread. Because `thread/resume`
appends to existing history, retrying in that thread rehydrated the same bloated
context. The retry now starts a fresh app-server thread with bounded-use
instructions.

## 9.5+ Remediation Plan

1. Implement full tool-output truncation before reinjection, not only compact
   artifact retention after runtime completion.
2. Promote repeated board/backlog/metrics state lookups into deterministic,
   bounded commands or scripts that Samantha and Agent can prefer naturally.
3. Persist deterministic metrics recommendations into Builder-owned state with
   review status, evidence, owner lane, and dashboard/CLI review affordances.
4. Re-run the same managed-app browser path, focused runtime tests, quality
   gates, and `git diff --check` after each durable fix.
