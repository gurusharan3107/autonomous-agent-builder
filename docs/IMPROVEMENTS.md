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
