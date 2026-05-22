# Coding-Agent Prevention — SDK-grounded patterns

> **Read this before writing new agent code** that touches dispatch, session management, streaming callbacks, quality-gate retries, or telemetry. Each pattern is grounded in the official [Claude Agent SDK Python reference](https://code.claude.com/docs/en/agent-sdk/python) and the [Claude Cookbook](https://platform.claude.com/cookbook).

**Origin:** extracted from [INSIGHTS.md Run #7 (2026-05-22)](../goal/INSIGHTS.md), where five priority patterns from IMP-001…IMP-013 and recent gate-remediator fixes were mapped to concrete SDK affordances. The trackable `[ ]` items live in [ROADMAP.md](../goal/ROADMAP.md) (M1.4, M1.5, M2.1, M2.3, M2.5, M2.6); this doc carries the *why* + *which SDK lever*.

**Scope:** prevention applies to the autonomous-builder *product* code (Claude Agent SDK + Codex SDK lanes). Hooks, MCP servers, subagents, and runtime callbacks are first-class product-side mechanisms. The "managed environment" caveat applies only to the Claude Code dev session, not to product code.

---

## P0-1 — Agent picks wrong tool / fires multi-tool turns / loses prior-turn context

**Past bugs:** IMP-001 (context drop on intake follow-up), IMP-006 (scaffold shell heredoc instead of Write tool), IMP-007 (4 `task_dispatch` calls in one turn → pool exhaustion), IMP-009 (dispatch before scaffold completed), commit `cd05a09` (scaffold Write/Edit tools + `dontAsk` clarification).

**Root cause:** Prompts described intent but did not pin SDK affordances. Model followed path of least resistance: shell over Write, parallel over serial, fresh state over threaded state.

**SDK-grounded fix:**

- **`can_use_tool: CanUseTool` callback** in `ClaudeAgentOptions`. Return `PermissionResultDeny(message="...", interrupt=False)` to block a tool call at the SDK boundary. Enforces: only one dispatch tool active at a time; no shell when Write is the right answer; preconditions met before dispatch tool fires. Stronger than prompt — the model literally cannot execute a denied tool.
- **`allowed_tools: list[str]`** scoped per phase in `ClaudeAgentOptions`. Scaffold: `["Write", "Read", "Bash"]`. Code-gen: `["Edit", "Bash", "Read"]`. Gate-remediator: `["Edit", "Bash", "Read", "Grep"]`. Never union across phases.
- **`AgentDefinition.maxTurns: int`** per subagent (camelCase in `AgentDefinition`). Caps runaway loops at the SDK boundary.
- **`ClaudeSDKClient` (not `query()`) for multi-turn flows.** `ClaudeSDKClient` retains conversation context automatically across `client.query()` calls in the same session — solves the IMP-001 class without manual `recent_context` threading. If `query()` is required, pass `continue_conversation=True` or `resume=<session_id>`.
- **`PermissionMode = "dontAsk"`** already in use per commit `cd05a09`. Keep the agent on this path.
- **Cookbook: Programmatic Tool Calling (PTC)** for orchestrations where tool ordering matters.

**Rule:** Before adding a new subagent, write its `allowed_tools`, `maxTurns`, and (where serialization matters) a `can_use_tool` callback. The prompt is the soft constraint; these three are the hard constraints.

---

## P0-2 — Long-lived DB sessions + streaming callbacks = pool exhaustion

**Past bugs:** IMP-010 (monitor task kept writing to rolled-back session), IMP-011 (SSE `Depends(get_db)` held pool connections), IMP-012 (dispatch session invalid after ~90s under sustained load).

**Root cause:** One SQLAlchemy session held across the full `runtime.run()` (4+ minutes), with background callbacks calling `flush()` on it. FastAPI `Depends(get_db)` kept connections alive for SSE client lifetime.

**SDK-grounded fix:**

- **`async with ClaudeSDKClient(options=...) as client:`** — `__aexit__` calls `disconnect()` and cancels background tasks deterministically. Replaces manual `try/finally` + `stop_monitor.set()` that IMP-010 fixed by hand.
- **SDK cleanup gotcha (official docs warning):** *"avoid using `break` to exit early when iterating messages — this can cause asyncio cleanup issues."* Audit every `async for message in client.receive_response():` site for early `break`; use a flag and drain.
- **Short-lived session per chunk/StreamEvent.** Open `async with get_session_factory()() as db:` inside the callback, flush+commit+close. Don't hold the dispatch session. (Encoded in `.memory/patterns/project_long_lived_session_pattern.md`.)
- **`include_partial_messages=True` → `StreamEvent`.** Each event carries `session_id`, `uuid`, raw stream data. Persist via short-lived sessions; never pipe through the dispatch session.
- **SSE endpoints: never `Depends(get_db)`.** Scope a session to the initial snapshot only; release before the long-lived `async for` loop. (Done in IMP-011.)

**Rule:** Any DB write that happens during `runtime.run()` (i.e., inside an `on_chunk`/`receive_response` loop) uses a fresh short-lived session. The dispatch session stays idle during the run and is used only for the final result write after `runtime.run()` returns.

---

## P1-3 — Lifecycle preconditions not enforced at phase boundaries

**Past bugs:** IMP-002 (code-gen dispatched into workspace with no ruff/pytest), IMP-004 (Recover button shown for non-recoverable states), IMP-008 (`git worktree add` against unborn HEAD), IMP-013 (orphan branch refused fast-forward merge — `unrelated histories`).

**Root cause:** Each stage assumed prior stages set up state correctly. Failures happened deep in the call stack, not at the boundary.

**SDK-grounded fix:**

- **Deterministic CLI probes before `client.query()`** — `subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace, capture_output=True)`, `shutil.which("ruff")`, `(workspace / "pyproject.toml").exists()`. Raise before dispatch; never let the agent attempt and fail.
- **Match `allowed_tools` to verified capability.** If ruff is missing, exclude `Bash(ruff:*)` from the allowlist. The model can't call what it can't see.
- **UI affordances gated on backend `can_X` signal.** Backend returns `{"can_recover": bool, "reason": str}`; frontend renders only when `can_recover=True`. Pattern applied in IMP-004 commit `8799f1b`.
- **`can_use_tool` callback** for runtime precondition gates. If the agent tries to use a tool against a path the workspace can't support, deny with a specific reason.

**Rule:** Every state transition has a precondition check at the entry. Cheap precondition check > expensive deep-stack failure recovery. UI affordances mirror backend `can_X` signals; never render a control whose backend would 4xx.

---

## P1-4 — Telemetry without diagnostic context

**Past bugs:** IMP-003 (`metrics show` returns 0 tokens during in-progress runs), IMP-005 (`memory list` empty doesn't distinguish scope mismatch from genuinely-empty).

**Root cause:** Aggregation endpoints returned data without enough context for callers to interpret `0`/`[]`.

**SDK-grounded fix:**

- **`include_partial_messages=True`** in `ClaudeAgentOptions` to receive `StreamEvent` during `runtime.run()`. Extract token counts and POST to metrics endpoint as the run proceeds, not only at `ResultMessage`.
- **Persist `AssistantMessage.usage`** per turn — each AssistantMessage carries `usage = {input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens}`.
- **`ResultMessage.model_usage`** for per-model breakdown: `{model_name: {inputTokens, outputTokens, cacheReadInputTokens, cacheCreationInputTokens, webSearchRequests, costUSD, contextWindow, maxOutputTokens}}`. Surface on the Metrics page in both lanes.
- **`RateLimitEvent`** is first-class in the SDK — `status: "allowed" | "allowed_warning" | "rejected"`, `resets_at`, `utilization`, `rate_limit_type` (`"five_hour" | "seven_day" | ...`). Surface to the dashboard so provider-limit blocked states have first-class telemetry, not stale-gate-failure noise. Maps to the CLAUDE.md provider-limit rule.
- **Empty-response convention:** every aggregation endpoint that can return empty/zero returns a `state` field (`"running" | "no_data" | "scope_mismatch"`) plus a `note` string. IMP-003 added `active_runs` + `active_runs_note`.

**Rule:** Every endpoint that aggregates over time-bounded state has to answer "why is this empty/zero?" in the response envelope. Never return `{"data": []}` alone.

---

## P2-5 — Quality-gate retry/cycle state machine

**Past bugs:** Commit `1153ec6` (`increment retry_count after remediation to avoid cycle detection`), commit `a0e8ca7` (gate-remediator agent + `remediation_possible` fixes).

**Why P2:** Single known instance, but blast radius is M2.6 autopilot — auto-recovery loops must be safe before autopilot ships.

**Root cause:** Cycle detection fired before the retry counter incremented; the first retry looked identical to the second.

**SDK-grounded fix:**

- Feed retry-vs-cycle decisions from typed SDK error signals, not string parsing:
  - **`ResultMessage.is_error: bool`**, `ResultMessage.errors: list[str] | None`, `ResultMessage.api_error_status: int | None`, `ResultMessage.subtype: str`.
  - **`AssistantMessageError`** literal type: `"authentication_failed" | "billing_error" | "rate_limit" | "invalid_request" | "server_error" | "max_output_tokens" | "unknown"`.
- Increment the cycle-detection counter on the transition itself, never on the next transition.
- Add a synthetic-state test for every retry path before M2.6 autopilot ships.

**Rule:** State machines that need cycle detection increment the counter on the transition; never on the next one. Decide retry-vs-cycle from typed SDK error signals.

---

## Prevention checklist

1. **Tool affordances are SDK-pinned.** Every subagent has explicit `allowed_tools`, `maxTurns`, and (where serialization matters) a `can_use_tool` callback. Prompts are soft constraints; these are hard.
2. **`ClaudeSDKClient` over `query()` for multi-turn flows.** Async context manager handles cleanup deterministically. Never `break` mid-iteration.
3. **One short-lived session per DB write during agent runs.** Dispatch session stays idle during `runtime.run()`; result writes happen after it returns.
4. **Precondition check at every state-transition entry.** Probe deterministically (subprocess, `shutil.which`, `Path.exists()`) before `client.query()`. Match `allowed_tools` to verified capability.
5. **Aggregation endpoints carry diagnostic state in the envelope.** `state` + `note` on every endpoint that can return empty/zero.
6. **Typed SDK error signals over string parsing.** `ResultMessage.is_error`, `AssistantMessageError`, `RateLimitEvent`. Feed state machines from these.
7. **Increment cycle-detection counters on the transition itself.** Never on the next.
8. **No managed-app codebase mutations.** All Builder fixes land in the `autonomous-agent-builder` source repo; never in `/home/gurusharangupta/Builder-Workspace/*` or `/tmp/aab-workspaces/*`.
9. **Prevention is product-side.** The autonomous-builder uses hooks (`ClaudeAgentOptions.hooks: dict[HookEvent, list[HookMatcher]]`), MCP servers (`mcp_servers`), and subagents (`agents: dict[str, AgentDefinition]`) — these enforce at the SDK boundary. A `PreToolUse` hook is a hard guarantee; a prompt is not.
10. **Cite the exact SDK option name when proposing a fix.** "Add a callback" is too vague; "add a `can_use_tool` callback that denies `Bash` when `Write` is the right tool, returning `PermissionResultDeny(message=...)`" is right.

---

## Cross-reference — ROADMAP items each pattern protects

| Pattern | ROADMAP items that will regress if uncaught |
| --- | --- |
| P0-1 (tool / turn / context) | M1.2 Codex lane, M1.4 reverse-flow, M2.6 autopilot, M3.4 benchmarks |
| P0-2 (sessions / streaming) | M1.5 voice realtime, M2.1 resumability, M3.2 long-horizon, M3.3 multi-operator |
| P1-3 (preconditions) | M1.4, M2.1, M2.6 |
| P1-4 (telemetry context) | M2.3, M3.4 |
| P2-5 (retry state machine) | M2.6 autopilot — **blocking prerequisite** |
