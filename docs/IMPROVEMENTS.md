# Builder Improvements

Living document. Updated as inefficiencies are found during live testing.
Each entry has: symptom, root cause, solution, status.

---

## [IMP-003] `builder metrics show` reports 0 tokens while actual spend is >$0

**Symptom:** `builder metrics show --json` returns `raw_token_total: 0`, `cache_ratio: 0`, `total_runs: 5` but the actual code-gen run used 27 turns and cost $0.46. Metrics surface is completely dark — a developer or operator watching metrics while a run is live would see nothing.

**Session:** devpulse workspace, 2026-05-20, immediately after first feature delivery start.

**Root cause (hypothesis):** The metrics aggregation query is scoped to a different session/project identifier than the running task. Likely the task agent runs are stored under a different `repo_identity` or `project_id` than the metrics query filters on. The `builder logs` surface shows real data (5 entries) but `builder metrics show` returns zeroed aggregates.

**Solution:** Align the metrics aggregation scope with the task execution scope. Verify `repo_identity` used by the code-gen agent matches the key used by `builder metrics show`. Add a CLI-level diagnostic that warns when metrics show 0 tokens while active runs exist.

**Status:** resolved — root cause was that `agent_runs.tokens_input/output` are written at run completion; in-progress runs always show 0. Fixed in `dashboard_metrics.py` by adding `_load_active_run_count` and injecting `active_runs` + `active_runs_note` into `optimization_summary` when any runs are in progress. Regression test: `test_metrics_active_run_injects_diagnostic_note` in `test_dashboard_api.py`.

---

## [IMP-002] Gates-first principle not enforced: 27-turn implementation run before quality gate infrastructure exists

**Symptom:** Fresh devpulse workspace with no `ruff`, `mypy`, or test files. Builder approved delivery and dispatched a `code-gen` agent run. After 27 turns and $0.46, the run hit `FileNotFoundError` in `code_quality` and `testing` gates. The error message: "Configure the gate or bootstrap the workspace before retrying."

**Session:** devpulse workspace, 2026-05-20. Task: "Set up domain model for Developer Pulse Dashboard - MVP". Cost: $0.4623, 27 turns, stop_reason: gate_infrastructure_error.

**Root cause:** The orchestrator dispatches the code-gen agent into implementation without checking whether the target workspace has the required gate tooling (ruff config, pytest config, mypy config). Day-0 readiness assessment either did not run or did not gate the workspace from implementation. The `builder readiness status` check is not wired as a hard prerequisite before the first task dispatch.

**Solution:** Before dispatching the first implementation task in a new workspace, the orchestrator must run `builder readiness assess` or equivalent Day-0 checks and block task dispatch if `code_quality`/`testing` gate infrastructure is missing. The operator should see a clear pre-flight message: "Your workspace needs linting and test setup before Builder can ship code." Bootstrap scripts or guided setup should run first.

**Status:** resolved — fixed by scaffold commits 1fae0bd, c1a39c8, a88ee2c. The orchestrator now detects missing gate infrastructure before dispatch, triggers workspace bootstrap, and blocks implementation until readiness is confirmed. Scaffold trigger fires on missing gate config or recoverable gate-infra error; deterministic python/node fallback ensures bootstrap runs deterministically; strict post-check gates re-entry.

---

## [IMP-001] Agent loses original feature request context after intake follow-up

**Symptom:** Operator submits a feature request → agent asks 3 intake clarification questions → operator answers them → agent responds with "I do not have a captured improvement ready to ship yet. Tell me the improvement you want, and I will ask the missing questions." The entire original request context is dropped and the operator is asked to start over.

**Session:** `68bc4348-dae8-4c1d-a5ea-a5604c315eb4` — devpulse workspace, 2026-05-20, Claude Agent SDK lane.

**Root cause (hypothesis):** The Claude Agent SDK runtime is building the second-turn prompt without referencing the first-turn feature request text. The operator's follow-up answers are treated as a standalone new message rather than as answers to the prior intake questions. The `chat` lane's prompt context assembly is not threading the original `FEATURE_SPEC_JSON` candidate or the prior assistant message into the follow-up turn's context window, so the model has no basis to connect the answers to the original request.

**Solution:** The second-turn prompt must include the prior conversation context (operator's original request + agent's intake questions + operator's answers). The Claude Agent SDK `chat` lane should either (a) pass the full prior conversation thread as context, or (b) persist the partial feature spec candidate and re-inject it into the follow-up prompt alongside the operator's answers so the model can complete the intake loop and produce `FEATURE_SPEC_JSON`.

**Status:** resolved — fixed in `agent_prompt_builders.py` (added `recent_context` parameter to `_feature_spec_chat_prompt`), `chat_turn_prompting.py` (pass `recent_context` to feature spec prompt branch), and `routes/agent.py` (force-build recent context when `feature_spec_requested=True` even when the user message is a short follow-up answer). The `force=True` bypass in `_recent_chat_context_for_prompt` ensures short operator answers like "Yes, for my team" are still paired with prior context. Regression tests in `test_agent_feature_spec_prompt_contracts.py`.

---

## [IMP-005] `builder memory list` empty response from managed-app workspace gives no scope hint to debugging agents

**Symptom:** Running `builder memory list --json` from `/home/gurusharangupta/Builder-Workspace/devpulse` returns `data: []` with `token_estimate: 25`. Running the same command from the Builder source repo returns 90+ entries. A debugging agent (Claude or Codex) who is investigating a Builder bug while sitting in a managed-app workspace may mistakenly conclude that prior session memories were lost.

**Status correction (2026-05-20):** The empty response is **correct by design** — memory is repo-scoped. The Builder source repo holds Builder-debugging precedent; each managed app holds its own app-specific precedent. The two scopes are intentionally separate. This was operator workflow error on the part of the debugging agent, not a Builder CLI bug.

**Remaining minor improvement (optional, low priority):** The empty-result JSON envelope could include a `memory_root_exists` boolean and the resolved `memory_root` absolute path so an agent can tell at a glance whether they're querying the right scope. Today's silent `data: []` does not distinguish "scope exists but no entries" from "no `.memory/` directory in cwd."

**Solution (if pursued):** In `src/autonomous_agent_builder/cli/commands/memory.py`, the `list_memories`, `search`, and `summary` commands could add `memory_root: str(Path.cwd() / ".memory")` and `memory_root_exists: bool` to the payload. Three-line change per command, no behavior change for callers that already get results.

**Status:** confirmed-not-a-bug (memory scope is correctly repo-local); minor diagnostic enhancement open

---

## [IMP-004] Recover button returns 409 for gate-infrastructure-blocked tasks — no operator escape path

**Symptom:** Task blocked after quality gate `FileNotFoundError` (no ruff/pytest in workspace). Board shows a `Recover` button. Clicking it returns `409 Conflict: task_not_recoverable`. The error message says only specific blocked-reason types can be recovered. Gate infrastructure errors are not in that list. Operator has no visible path forward.

**Session:** devpulse workspace, 2026-05-20. Task `128e02f6`. `POST /api/tasks/128e02f6/recover` → 409.

**Root cause:** The recovery endpoint whitelist does not include `gate_infrastructure_error` as a recoverable state. The Board renders a Recover button for ALL blocked tasks regardless of whether recovery is actually possible.

**Solution (two parts):**
1. **Backend**: Add `gate_infrastructure_error` to the recoverable states in the task recovery handler — recovery for this case should reset the task to `pending` so it can be re-dispatched after the operator fixes the workspace infrastructure.
2. **Frontend**: The Board task card should only render the Recover button when the task's `blocked_reason` type is actually recoverable. For gate-infrastructure errors, show an actionable message: "Set up linting and tests in your workspace, then retry." with a link to setup guidance.

**Status:** resolved — fixed in two parts. Backend: commits 1fae0bd and c1a39c8 added `gate_infrastructure_error` to recoverable states so the recovery endpoint no longer returns 409 for this case. Frontend: commit 8799f1b gates the Recover button on the backend `can_recover` signal so it only renders when recovery is actually possible. Operators now see an actionable message instead of a dead 409.

---

<!-- entries added during testing -->

---

## [IMP-006] Scaffold agent completes without emitting `SCAFFOLD_RESULT_JSON:` sentinel — all downstream tasks block

**Symptom:** Scaffold agent ran (5 turns, $0.0915, stop_reason=end_turn) but produced no files and no `SCAFFOLD_RESULT_JSON:` sentinel line. Orchestrator treated the run as `scaffold_failed` and blocked the domain-model task. Without the sentinel the orchestrator cannot proceed to dispatch implementation tasks.

**Session:** devpulse workspace, 2026-05-21, session `666f6b7f`. Board: all 5 tasks blocked after a single scaffold run.

**Root cause (confirmed):** The scaffold agent tried to create `pyproject.toml` via shell heredoc (`cat > file << 'EOF'`) instead of the `Write` tool. The workspace boundary enforcement hook blocks shell-based file writes. The agent's final output was: *"Once Write is permitted (or the file is created manually), I can complete scaffolding and emit `SCAFFOLD_RESULT_JSON`."* — then `end_turn` without the sentinel. The prompt said "write the gate config" but didn't say *which tool to use*, so the model chose the shell path which was blocked.

**Solution:** Added explicit prompt constraint: "ALWAYS use the `Write` tool to create files. NEVER use shell heredoc (`cat > file << 'EOF'`) or `echo` redirects — those are blocked by the workspace enforcement hook." Applied to `agents/definitions.py` scaffold `prompt_template`. Regression test: re-run scaffold and verify `pyproject.toml` written + sentinel emitted.

**Status:** resolved — prompt fix applied; `pyproject.toml` written manually to unblock the domain-model task workspace for the current test cycle.

---

## [IMP-007] Agent dispatches all tasks simultaneously → connection pool exhaustion

**Symptom:** After calling `mcp__builder__task_dispatch` for the first task, the agent immediately called it 3 more times without waiting. This saturated the SQLAlchemy `QueuePool limit of size 5 overflow 10`, timing out at 30s. Subsequent tasks show "Session's transaction has been rolled back due to a previous exception during flush."

**Session:** devpulse workspace, 2026-05-21, session `666f6b7f`. The agent issued 4 consecutive `task_dispatch` calls in the same turn.

**Root cause:** The agent-chat prompt didn't prevent bulk dispatch. The dispatch route had no per-project concurrency limit — only a per-task duplicate check. 4 concurrent agent loops each opening independent DB sessions saturated the pool.

**Solution (two parts):**
1. **Prompt constraint**: Added "Dispatch ONE task at a time. Never call `mcp__builder__task_dispatch` for multiple tasks in the same turn. Wait for the response before dispatching the next." to both the `continuation_guidance` and `model_backed_delivery_context` branches of `agent_prompt_builders.py`.
2. **Backend guard**: Added `reserve_project_dispatch` / `release_project_dispatch` to `dispatch_lock.py` (max 1 concurrent dispatch per project). The dispatch route now returns `{"status": "project_busy"}` when a project slot is occupied; releases happen in the `_run_dispatch_step` `finally` block.

**Status:** resolved — prompt fix in `agent_prompt_builders.py`; backend guard in `dispatch_lock.py` + `routes/tasks.py`. Regression tests: `test_reserve_project_dispatch_blocks_at_limit`, `test_dispatch_returns_project_busy_when_project_already_dispatching` in `test_dispatch_guards.py`.

---

## [IMP-008] `git worktree add` fails when workspace has no initial commit (unborn HEAD)

**Symptom:** When operator asks to ship a feature into a fresh workspace that has never had any git commit, the orchestrator attempts `git worktree add` and gets: `warning: HEAD points to an invalid (or orphaned) reference`. All tasks that require a worktree (UI shell, core behavior, persistence, verify) block immediately.

**Session:** devpulse workspace, 2026-05-21. The devpulse workspace has no commits (empty master branch, `git log` returns "does not have any commits yet").

**Root cause:** `git worktree add` requires at least one commit on the current branch. An unborn HEAD is not a valid base ref for worktree creation. Scaffold did not create an initial commit.

**Solution:** Added unborn-HEAD guard to `WorkspaceManager.create_workspace` in `workspace/manager.py`. Before `git worktree prune`, it runs `git rev-parse --verify HEAD`; if HEAD is unborn (returncode != 0), it runs `git commit --allow-empty -m "init"` to create the base ref. Regression test: `test_workspace_manager_creates_initial_commit_for_unborn_head` in `test_sprint_branch_lifecycle.py`.

**Status:** resolved — fix in `workspace/manager.py`, regression test added, 1 passed.

---

## [IMP-009] Agent dispatches implementation tasks before scaffold completes

**Symptom:** In session `666f6b7f`, the agent called `mcp__builder__workspace_scaffold` and then immediately called `mcp__builder__task_dispatch` multiple times in the same turn without waiting for the scaffold run to finish. The scaffold run was still `status=running` when the first task dispatch happened.

**Root cause (confirmed):** Two compounding issues:
1. The scaffold HTTP endpoint is synchronous and blocks until the scaffold agent completes, but the `_api_request` HTTP client had a 30 s timeout. When scaffold takes longer, the client raises a timeout error while the server-side scaffold agent continues running. The agent sees an error response and proceeds.
2. When multiple tool calls appear in the same Claude Agent SDK model turn, they are executed concurrently. If the model output `workspace_scaffold` and `task_dispatch` in the same turn, both fire simultaneously regardless of order.

**Solution (two parts):**
1. **Scaffold HTTP timeout**: Increased the `builder_workspace_scaffold` API request timeout from 30 s to 300 s in `builder_tool_service.py` so the client waits for the scaffold agent to complete rather than timing out.
2. **Backend pre-dispatch guard**: The dispatch route now checks `task.agent_runs` for any `AgentRun` with `agent_name="scaffold"` and `status="running"`. If found, it returns `{"status": "scaffold_pending"}` before allowing dispatch. Added prompt constraint: "If workspace scaffold is in progress, do not call `mcp__builder__task_dispatch` until scaffold completes."

**Status:** resolved — timeout fix in `builder_tool_service.py`; pre-dispatch guard in `routes/tasks.py`. Regression test: `test_dispatch_returns_scaffold_pending_when_scaffold_agent_running` in `test_dispatch_guards.py`.

---

## [IMP-010] SQLAlchemy session rolls back during long-running scaffold agent, blocking the task

**Symptom:** On re-verify (2026-05-21), dispatching a recovered task with `force_scaffold=True` in `recovery_context` causes the scaffold Claude agent to start, produce one line of output ("Let me check the existing workspace structure before writing the gate config."), then the `_run_dispatch_step` session rolls back. The task is blocked with: "Dispatch failed: This Session's transaction has been rolled back due to a previous exception during flush." The scaffold agent_run shows `status=failed` with the dispatch failure reason as its error (written by `mark_task_running_agent_runs_failed`).

**Session:** devpulse workspace, 2026-05-21 08:24:24. Task 128e02f6. Scaffold agent_run 84f2ca7f started at 08:24:24, failed at 08:26:57.

**Root cause (hypothesis):** `run_agent_lifecycle` calls `await db.commit()` after creating the `AgentRun` record (line 195 of `agent_run_lifecycle.py`). During the scaffold Claude agent execution, `persist_realtime_run_update` is called from `record_output_chunk` (via `on_chunk` callback in `runtime.run()`). If `db.flush()` inside `persist_realtime_run_update` fails (e.g., SQLite BUSY after the 15 s `busy_timeout`), the session transaction is rolled back. The exception then propagates through `runtime.run()` → `_run_workspace_scaffold_if_needed` → `_phase_implementation` → `orchestrator.dispatch`. The except block in `dispatch` (line 321–327 in orchestrator.py) then tries `await self.db.flush()` on the already-rolled-back session, triggering the "session rolled back" error. Additionally, the `monitor_workspace_diff` background asyncio task is not stopped on exception (lines 290–294 are not in a `finally` block), leaving it running after the exception.

**Contributing factors:**
- The session is held open for the entire scaffold duration (inside `async with session_factory() as db:` in `_run_dispatch_step`).
- `busy_timeout=15000` means SQLite will retry writes for 15 s before BUSY error. Concurrent server requests that briefly hold the write lock during the 2.5-minute scaffold run could trigger this.
- The `monitor_workspace_diff` asyncio task is not cancelled on exception — it continues writing to the session after `runtime.run()` has thrown.

**Solution:** Two parts:
1. **Stop monitor on exception**: Wrap `monitor_workspace_diff` lifecycle in a `finally` block in `run_agent_lifecycle` to ensure `stop_monitor.set()` and `monitor_task.cancel()` are always called even if `runtime.run()` throws.
2. **Diagnose the flush failure**: Add structlog error capture for the original flush exception inside `persist_realtime_run_update` before the exception propagates, so the root cause (BUSY, constraint, etc.) is visible in logs.

**Solution applied (2026-05-21):**
1. **Monitor task always stopped**: Wrapped `result = await runtime.run(...)` in a `try/finally` block in `run_agent_lifecycle` so `stop_monitor.set()` + `monitor_task.cancel()` always fire even if the runtime raises. Prevents the monitor writing to a rolled-back session.
2. **Flush error logged**: Added structlog `agent_run_lifecycle_flush_error` before re-raising in `persist_realtime_run_update` so the original flush failure (SQLite BUSY, constraint, etc.) is visible in server logs.
3. **Dispatch rollback guard**: Added `await self.db.rollback()` before the FAILED-state flush in `orchestrator.dispatch`'s except block so a rolled-back session can accept the blocked-reason write.

**Status:** resolved — fixes in `agent_run_lifecycle.py` (try/finally + flush-error log) and `orchestrator.py` (rollback guard). No dedicated regression test added (requires a real long-running agent call to trigger the SQLite BUSY race); monitored via structlog `agent_run_lifecycle_flush_error` events in live runs.

---

## [IMP-011] SSE endpoints hold DB pool connections for their entire client lifetime, exhausting the pool during long scaffold runs

**Symptom:** On re-verify (2026-05-21), task 128e02f6 blocked again with the same session-rollback error after the IMP-010 fix was applied. Server log showed `sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.00` immediately before the rollback. The scaffold had been running for ~4 minutes at that point.

**Session:** devpulse workspace, 2026-05-21 09:05:10–09:09:09 (second attempt after IMP-010 fix). Same task and symptom as IMP-010 but different root cause.

**Root cause:** `board_stream` and `approval_stream` SSE endpoints in `dashboard_api.py` inject `db: AsyncSession = Depends(get_db)`. FastAPI's `Depends` context manager stays open for the lifetime of the HTTP request. For SSE endpoints the request lives as long as the client is connected — potentially many minutes. With 2 SSE clients connected during a 4-minute scaffold run, 2 pool connections were held permanently. Combined with the dispatch session (1 connection) and concurrent HTTP requests, the default SQLite `QueuePool(pool_size=5, max_overflow=10)` reached its 15-connection ceiling. After 30 s waiting, callers received `TimeoutError`, which rolled back the dispatch session and triggered the IMP-010 symptom again.

**Contributing factors:**
- Default `QueuePool` settings (5+10) are appropriate for PostgreSQL but too small for local SQLite dev where long-lived connections accumulate.
- Both SSE handlers only needed the DB session for the initial snapshot query; subsequent loop iterations read only from an in-memory hub queue.

**Solution:** Remove `db: AsyncSession = Depends(get_db)` from `board_stream` and `approval_stream`. Replace with an explicit `async with get_session_factory()() as db:` block scoped to just the initial snapshot query so the connection is returned to the pool before the long-lived SSE generator loop begins.

**Files changed:** `src/autonomous_agent_builder/api/routes/dashboard_api.py` — `board_stream` (line ~1655) and `approval_stream` (line ~1693).

**Status:** resolved — 2026-05-21. No regression test added (SSE lifetime requires a live server to verify); validated by successful live re-dispatch of task 128e02f6 with `active=1 blocked=0` sustained through the scaffold run.

---

## [IMP-012] Dispatch session connection becomes invalid after ~90s, causing `Can't reconnect until invalid transaction is rolled back`

**Symptom:** After IMP-010 and IMP-011 fixes, task 128e02f6 blocked again ~90s into the scaffold run with "Dispatch failed: ... Original exception was: Can't reconnect until invalid transaction is rolled back." Exit code 143 (SIGTERM) seen in `ProcessError` from the claude subprocess. No `agent_run_lifecycle_flush_error` log — the connection became invalid before any flush was attempted.

**Root cause:** `run_agent_lifecycle` uses the dispatch session (`db`) for ALL DB operations during `runtime.run()`: the `monitor_workspace_diff` task calls `persist_realtime_run_update` every ~1s, each doing `db.flush()` + `db.commit()` on the same session that was opened minutes ago. SQLAlchemy's aiosqlite connection becomes invalid under sustained load — the async worker thread handling becomes unstable after many repeated operations on a long-held connection.

**Solution (IMP-012):** Change `persist_realtime_run_update` to use a SHORT-LIVED session from `get_session_factory()` for each intermediate real-time update, instead of the dispatch session. The dispatch session is left IDLE during the entire `runtime.run()` call. `run.merge()` is used to persist the latest `AgentRun` attribute values in each short-lived session.

**Files changed:**
- `agent_run_lifecycle.py`: add `from autonomous_agent_builder.db.session import get_session_factory`
- `agent_run_lifecycle.py`: replace `db`-based `persist_realtime_run_update` with short-lived `async with get_session_factory()() as update_db: ... await update_db.merge(run)`

**Why this works:** Short-lived sessions (opened, flushed, committed, closed in <10ms) are much less likely to encounter connection invalidation issues than a single session held open for 4+ minutes under load. The dispatch session remains idle (no DB operations) during `runtime.run()`, so its connection stays valid for the final update after the run completes.

**Additional fix required:** `_publish_realtime_board_snapshot` in `orchestrator.py` called `publish_board_snapshot(self.db)` which starts `await db.flush()` on the dispatch session inside `db_write_lock`. This write transaction held the SQLite write lock, blocking the short-lived sessions' next INSERT. Fix: changed `_publish_realtime_board_snapshot` to use `async with get_session_factory()() as read_db:` — a fresh read session that has nothing to flush, so no write transaction is started on the dispatch session.

**Status:** resolved — 2026-05-21. Validated live: scaffold completed (5m17s, 8 turns, $0.108), code-gen completed (12m, 26 turns, $0.271), quality gates + integration + build verify all passed. Task 128e02f6 reached `done` at 11:25 — first full M1.2 lifecycle completion.

---

## [IMP-013] Orphan task branch cannot fast-forward into sprint branch — `fatal: refusing to merge unrelated histories`

**Symptom:** After code-gen completed successfully (IMP-012 fixed), quality gates ran and the integration step failed: "Integration failed: could not fast-forward task/128e02f6...: fatal: refusing to merge unrelated histories". Task blocked at 10:02.

**Root cause:** The task workspace's initial commit (`7ceded1 chore: preserve builder runtime guidance`) is an ORPHAN root — it has no parent. The sprint branch was initialized with a SEPARATE root commit (`447031c init`) after the task workspace was created. Two disconnected histories. The `is_fast_forward_divergence()` check in `workspace_policy.py` only matched "not possible to fast-forward" and "diverging branches", so the "refusing to merge unrelated histories" error bypassed the rebase fallback path in `workspace_integration.py`.

**Solution:**
1. `workspace_policy.py`: add `"refusing to merge unrelated histories"` to `is_fast_forward_divergence()` so the rebase fallback is triggered.
2. `workspace_integration.py` `rebase_task_workspace_for_integration`: detect orphan branch (no common ancestor via `git merge-base`) and use `git rebase --onto target_branch --root` instead of plain `git rebase target_branch`. Without `--root`, git cannot find a fork point for an orphan branch.

**Files changed:** `workspace_policy.py`, `workspace_integration.py`.

**Status:** resolved — 2026-05-21. Validated: `workspace_rebased_for_integration` + `workspace_integrated_fast_forward` both emitted at 11:25; task reached `done` at 11:25:34.
