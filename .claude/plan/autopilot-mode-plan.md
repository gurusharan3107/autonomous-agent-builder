# Autopilot Mode — Phased Implementation Plan

## Context

Both Codex CLI and Claude Code shipped `/goal` in spring 2026 — a single primitive for long-horizon agentic work. Autonomous Agent Builder is structurally further along than either (visible SDLC, evaluator subagents, lifecycle state machine, durable workspaces) but doesn't yet close the loop: every approval, recovery, and continuation still requires an operator. **Autopilot mode** closes that loop. Operator turns on autopilot → orchestrator + SDK agents ship features from the backlog (develop mode) or apply efficiency/architecture improvements derived from code + tech-stack inspection (optimize mode), with no operator action until autopilot pauses on a defined condition.

**Key architectural correction (per user):** autopilot must live *inside* the existing SDK tool loops (Claude Agent SDK + Codex SDK), not as a parallel orchestrator. Voice operator and agent chat are first-class control surfaces. The implementation is a runtime-policy flag + a small set of new builder MCP tools + one new supervisor subagent + a token-budget primitive + a backlog-creating extension to the existing post-ship optimization phase. No new outer-loop process.

**Fallback policy:** when autopilot encounters anything it cannot safely auto-decide (high-stakes operator question with no clear recommendation, recovery thrashing, supervisor disagreement with verifiers, budget exhaustion), it pauses the **whole session** and surfaces a structured reason via chat/voice/dashboard. Trust is preserved by visible refusal.

## Architectural Principles (apply to every phase)

1. **Builder-owned tools, not new control plane.** Every autopilot capability is exposed as an MCP tool the SDK agents call (Claude side: `agents/tools/sdk_mcp.py`; Codex side: the equivalent tool adapter). The orchestrator's `PHASE_DISPATCH` table is unchanged.
2. **Runtime parity across Claude + Codex SDKs.** Any new MCP tool ships in both adapter surfaces simultaneously.
3. **Reuse existing patterns.** Mirror `services/provider_limits.py` for the token-budget primitive. Model the supervisor on `pr-reviewer` / `build-verifier` (`agents/definitions.py:842-905`). Reuse `task_recover` MCP tool (already present in `sdk_mcp.py:318-326`). Reuse `apply_approval_outcome()` (`orchestrator/approval_outcomes.py:17-52`) for programmatic approvals.
4. **Voice + chat + dashboard stay synchronized.** Autopilot state lives in `services/runtime_settings.py` (`.agent-builder/runtime.env`) so the existing GET/POST `/agent/runtime` endpoint, voice operator, and chat all read/write through one source.
5. **Audit trail by default.** Every autopilot action emits a `ChatEvent` (new types: `autopilot_decision`, `autopilot_pause`, `autopilot_resume`) so the operator can scrub through what was done.

---

## Phase 1 — Foundation: Supervisor evaluator + token budget primitive

**Goal:** ship two primitives as **evidence/observability only** (no gating, no autopilot mode yet). Operators see supervisor judgment and token usage on real tasks. We learn whether the supervisor is trustworthy before Phase 2 makes any decision based on it.

**Changes:**
- New `SubagentDefinition` named `supervisor-evaluator` in `src/autonomous_agent_builder/agents/definitions.py` (slot after `pr-reviewer` definition, ~line 905). Tools: `Read`, `Glob`, `Grep`, builder read-only MCP tools (`board`, `task_show`, `backlog_item_show`, `kb_search`). Output schema: `{ "status": "objective_met|objective_not_met|insufficient_evidence", "confidence": 0.0-1.0, "evidence": [...], "reasoning": "..." }`. Prompt: read task objective + final workspace state with **no prior conversation context**; judge whether the stated objective was achieved.
- Add `supervisor-evaluator` entry to `_AGENT_POLICY` in `src/autonomous_agent_builder/agents/execution_policy.py:69-166`: `effort=low`, `context_strategy=deterministic_verification`, `model=haiku` (via `resolve_subagent_model()` at line 221-233; add to the cheap-model set).
- Wire supervisor into `_phase_build_verify` (`orchestrator/orchestrator.py:854-923`) as an **additional subagent call after build-verifier**. Persist its JSON output to `task.evidence["supervisor"]` and surface in dashboard, but do not gate progression on it yet.
- New module `src/autonomous_agent_builder/services/token_budget.py` mirroring `services/provider_limits.py:1-277`: `build_token_budget_payload`, `mark_token_budget_exhausted`, `token_budget_is_ready`, `clear_token_budget`. Storage: `task.depends_on["token_budget"]` payload + reuse `TaskStatus.CAPABILITY_LIMIT` with `code=token_budget` discriminator (avoids a new status enum value; matches the provider-limit pattern).
- Add `builder_check_token_budget(scope="task"|"session")` MCP tool to `src/autonomous_agent_builder/agents/tools/sdk_mcp.py` (read-only). Returns `{ used, budget, remaining, status }`.
- Extend `RuntimeSettingsUpdate` (`services/runtime_settings.py` + corresponding API model) with `task_token_budget`, `session_token_budget` defaults.
- Per-agent budgets in `_TASK_BUDGET_TOKENS` (`execution_policy.py:47-54`) already exist — extend to include `supervisor-evaluator: 30_000`.

**Reuse:**
- `provider_limits.py:71-118` payload + mark pattern.
- `definitions.py:842-862` (build-verifier) as the closest sibling for supervisor structure.
- `runner.py:526-535` for SDK subagent registration (auto-picks up the new definition).

**Validation criteria to advance to Phase 2:**
- ✅ Supervisor runs on ≥ 10 real tasks across develop projects; JSON output present in evidence for all.
- ✅ Supervisor agreement rate with eventual operator-issued approval decisions ≥ 85% (measured by comparing `objective_met` to whether operator approved or rejected the related gate).
- ✅ Token budget tracked end-to-end on ≥ 5 runs; status transitions to budget-exhausted state when explicitly overshot; clears on recovery.
- ✅ No regression in existing `_phase_build_verify` flow — all current tests in `tests/test_orchestrator.py` pass.
- ✅ Unit tests added for `supervisor-evaluator` JSON contract and for `token_budget.py` parity with `provider_limits.py`.
- ✅ Dashboard surfaces supervisor judgment + token usage on the task detail page.

---

## Phase 2 — Per-gate auto-approval (autopilot armed but conservative)

**Goal:** introduce autopilot as a runtime flag + per-gate opt-in. Agents in the SDK loop can call a new `builder_approve_gate` MCP tool that programmatically creates an `Approval` record. The supervisor's judgment is now load-bearing — if it disagrees with verifiers, the agent cannot auto-approve and the task remains operator-gated.

**Changes:**
- Add to `RUNTIME_ENV_KEYS` (`services/runtime_settings.py:28-38`): `RUNTIME_AUTOPILOT_ENABLED` (bool), `RUNTIME_AUTOPILOT_GATES` (CSV of `design_review|quality_gates|review_pending|all`), `RUNTIME_AUTOPILOT_MODE` (placeholder for Phase 3+: `develop|optimize`).
- Extend `RuntimeSettingsUpdate` (`agent_api_models.py`) + `GET/POST /agent/runtime` (`embedded/server/routes/agent.py:1316-1381`) to accept these. Broadcast `runtime_settings_updated` ChatEvent on change.
- New MCP tool `builder_approve_gate(gate_id, evidence_summary, decision_rationale)` in `agents/tools/sdk_mcp.py`. Implementation: load `ApprovalGate` (`db/models.py:378-402`), refuse if (a) autopilot disabled, (b) gate type not in `RUNTIME_AUTOPILOT_GATES`, (c) supervisor evidence is missing or `objective_met=false`, or (d) any required verifier (build-verifier, browser-verifier where applicable) is not passing. On accept, construct an `Approval` record with `actor="autopilot"` and call existing `apply_approval_outcome()` (`orchestrator/approval_outcomes.py:17-52`).
- Tool exposure is **autopilot-gated**: `sdk_mcp.build_default_mcp_servers()` filters the tool out when autopilot is off. Same on the Codex adapter side.
- Prompt shaping: extend the `pr-creator` agent (`agents/definitions.py`) and `build-verifier` agent prompts to include autopilot guidance — when autopilot is on, after evidence is collected, call `builder_approve_gate` if the contract is met; otherwise leave for operator.
- Voice + chat command parsing: voice tool `set_autopilot_mode(enabled, gates)` added to `realtime.py`; chat intent router (`agent_prompt_builders.py:37-48`) gets an `autopilot_control` intent that maps to runtime settings mutation.
- Emit `ChatEvent(type="autopilot_decision", payload={action, gate_id, evidence_refs, rationale})` on every auto-approval.

**Reuse:**
- `ApprovalGate` + `Approval` + `apply_approval_outcome` — no new approval data model; only a new actor.
- `runtime_settings.py` env-persistence pattern.
- Existing `_SPECIALIST_ROUTE_POLICIES` in `agent_prompt_builders.py` for intent routing.

**Validation criteria to advance to Phase 3:**
- ✅ Auto-approval works end-to-end on a test task for `design_review` alone (with autopilot gates = `design_review`); then for `quality_gates`; then for `review_pending`; then `all`.
- ✅ Refusal contract: 3 manufactured cases where supervisor disagrees with verifiers → autopilot does NOT auto-approve; operator decision required; ChatEvent records the refusal reason.
- ✅ Audit replay: from `ChatEvent` stream, full timeline of any autopilot decision can be reconstructed including the evidence references that were live at decision time.
- ✅ Voice command "autopilot on / off / set gates to all" mutates the runtime setting; chat "/autopilot on" same; dashboard toggle same; all three reflect the same state within 1 second.
- ✅ Operator-driven flow unchanged when `RUNTIME_AUTOPILOT_ENABLED=false`: every existing approval test in `tests/` passes.
- ✅ Unit tests for `builder_approve_gate` refusal cases + Approval-record creation parity with operator-driven path.

---

## Phase 3 — Develop autopilot (continuous task progression + recovery autonomy)

**Goal:** close the outer loop. When a task hits `DONE` and autopilot is on, the next ready task dispatches automatically. Failures trigger bounded auto-recovery. Operator-questions get auto-answered only when the agent has a high-confidence path; otherwise the **session pauses cleanly** with operator-visible reason. This is develop-mode autopilot, complete.

**Changes:**
- Generalize the existing `requires_autonomous_continuation()` pattern from `chat_turn_runtime.py:59-71` (currently used by `init-project-chat`) into a reusable `services/autopilot_continuation.py`. The orchestrator's post-DONE hook checks: autopilot enabled, session not paused, budget remaining, recovery budget remaining → if so, claim and dispatch next QUEUED task in priority order.
- Recovery autonomy: orchestrator's existing FAILED-state handler (per `task_recovery.py:284-359`) gets an "auto-recover" branch when autopilot is on. Bounds: `RUNTIME_AUTOPILOT_RECOVERY_MAX_ATTEMPTS_PER_TASK` (default 3), `RUNTIME_AUTOPILOT_RECOVERY_MAX_SAME_SIGNATURE` (default 1 — repeated same-error means pause). New helper `failure_signature(task, error_text)` for de-duplication. Reuses `task_is_recoverable()` (`task_recovery.py:32-67`) and `recover_failed_task()` for the actual recovery.
- AskUserQuestion handoff: new MCP tool `builder_resolve_operator_question(event_id, answer, rationale)` in `sdk_mcp.py`. Refuses unless (a) autopilot is on, (b) the pending question has a `recommended_option` with confidence above threshold, AND (c) the question is tagged with risk level `low` or `medium` (questions classified `high` always pause the session). Implementation reuses `apply_operator_decision_handoff()` flow in reverse — marks the ChatEvent answered with `actor=autopilot`.
- Session state: lightweight `AutopilotSession` model in `db/models.py` — `id`, `started_at`, `paused_at`, `pause_reason`, `mode (develop|optimize)`, `tokens_used`, `tasks_completed`, `tasks_failed_recovered`, `tasks_failed_paused`. Created on autopilot enable; closed on pause or stop. Lightweight — this is observability, not a new lifecycle owner.
- Voice + chat: "what's autopilot doing?" → returns current AutopilotSession summary. "pause autopilot" / "resume autopilot" / "stop autopilot" → state mutation. "force resume after pause" → operator-confirmed override of last pause reason.
- Dashboard surface: a session ribbon at top of dashboard showing autopilot state (running / paused with reason / off), tasks completed in this session, budget remaining.

**Reuse:**
- `task_recover` MCP tool (already exists at `sdk_mcp.py:318-326`) — no new recovery primitive.
- `apply_operator_decision_handoff` (`orchestrator/operator_decisions.py:13-26`) inverted for autopilot answer.
- `requires_autonomous_continuation` pattern from init-project-chat.
- `voice_operator.py` for the voice-tool wiring template.

**Validation criteria to advance to Phase 4:**
- ✅ End-to-end: a backlog with 5 small feature items → autopilot ships all 5 with zero operator input → all 5 PRs created with autopilot-actor approvals → all 5 build-verify pass with supervisor concurrence.
- ✅ Recovery bound respected: manufactured 4-time recurring failure on one task → session pauses on attempt 4 with `pause_reason=recovery_budget_exhausted`; operator can see exactly which task, which signature.
- ✅ Same-signature bound respected: same-error twice in a row on different attempts → session pauses with `pause_reason=same_signature_recovery_repeat`.
- ✅ Token budget exhaustion: configure low session budget → autopilot pauses at threshold with `pause_reason=session_budget_exhausted`; task that hit it is preserved for resume.
- ✅ High-risk question handoff: agent emits AskUserQuestion tagged `risk=high` → autopilot does NOT auto-answer; pauses with `pause_reason=high_risk_question`; operator can answer via chat/voice; resume picks up.
- ✅ Pause/resume idempotent across voice, chat, dashboard — verified in test that issues conflicting commands.
- ✅ Audit completeness: for one full autopilot session, every decision (approve, recover, answer-question, dispatch-next) appears as a `ChatEvent` with structured payload and timestamps.

---

## Phase 4 — Coverage adequacy gate (precondition for optimize mode)

**Goal:** before optimize mode can run on any project, the test suite must be a credible regression net. "Behavior preserved" is unverifiable otherwise. This phase adds a coverage adequacy gate that locks optimize mode until satisfied.

**Changes:**
- Extend `quality_gates/testing.py:33-96` (`TestingGate`): `coverage_threshold` field already exists at line 42 (default 80) but is unused. Implement actual coverage check — parse `coverage.xml` (pytest-cov) or `coverage-summary.json` (Jest) or equivalent per project type. Return `GateStatus.FAIL` when below threshold AND optimize-mode adequacy is being evaluated; return `GateStatus.WARN` otherwise (preserves current non-optimize behavior).
- New CLI command `builder quality-gate coverage-adequacy --json` exposing the result for both operator and autopilot inspection.
- New runtime settings: `RUNTIME_OPTIMIZE_COVERAGE_THRESHOLD` (default 70, intentionally lower than the strict testing-gate threshold of 80 to set a realistic optimize-mode floor), `RUNTIME_OPTIMIZE_REQUIRES_CHARACTERIZATION` (default true) — when true, coverage check additionally requires presence of a `tests/characterization/` directory or equivalent marker.
- Optimize mode lockout: when `RUNTIME_AUTOPILOT_MODE=optimize` and coverage adequacy fails, autopilot refuses to start with `pause_reason=optimize_coverage_inadequate` and a structured payload listing missing coverage areas.
- Operator override path: one-shot `RUNTIME_OPTIMIZE_FORCE_OVERRIDE=true` (also settable via voice/chat) explicitly acknowledges risk; logs an `autopilot_override` ChatEvent with operator identity.
- Test-generation pre-step: if coverage gate fails and autopilot is in optimize mode, autopilot may first auto-dispatch an `--type improvement` backlog item titled "Characterization tests for <surface>" before entering optimize. This is develop-mode autopilot reused, with the auto-generated item.

**Reuse:**
- `quality_gates/testing.py` infrastructure (`coverage_threshold` field already declared).
- `builder backlog item create --type improvement` (`backlog_items.py:30-34`) for the test-generation pre-step.
- Develop autopilot loop from Phase 3 for shipping the generated improvement items.

**Validation criteria to advance to Phase 5:**
- ✅ Coverage adequacy gate correctly identifies a low-coverage project (<70%) and a high-coverage project (>70%) using pytest-cov and Jest test fixtures.
- ✅ Optimize mode refuses to start when gate fails; refusal reason includes specific uncovered modules.
- ✅ Operator override path works once; subsequent optimize runs require a fresh override (override does not persist).
- ✅ Existing `TestingGate` behavior unchanged for non-optimize contexts — coverage stays a WARN signal in standard quality-gates phase.
- ✅ Test-generation pre-step: feed a low-coverage project to optimize-mode autopilot → autopilot generates and ships characterization-test backlog item → coverage gate now passes → optimize mode proceeds.

---

## Phase 5 — Optimize autopilot (codebase + tech-stack scanning, backlog-producing)

**Goal:** elevate the existing `post_ship_optimization.py` from a per-sprint postscript to a **backlog producer**. Autopilot in optimize mode scans the codebase + tech stack, generates `--type optimization` backlog items with metric-driven stop signals, then runs them through develop-mode autopilot (which is the loop from Phase 3, unchanged). Behavior preservation is the supervisor's job (already in place from Phase 1).

**Changes:**
- Extend `orchestrator/post_ship_optimization.py:52-216` to optionally create backlog items. When `RUNTIME_AUTOPILOT_MODE=optimize` and recommendations exist, additionally call `backlog_item_create(type="optimization", source="AGENT", ...)` for each accepted recommendation. Each item's description must include baseline metric, target metric, measurement strategy, and behavior-preservation contract (the supervisor's verification criteria).
- Extend the `optimization-agent` (`agents/definitions.py:662-720`) prompt and policy (`execution_policy.py:158-165`) to operate in two modes: (a) existing per-sprint mode (unchanged), (b) new full-codebase scan mode when autopilot triggers it. In scan mode, the agent inspects: tech-stack graph (`knowledge/evidence_graph.py:480-547`), profiling/observability payload, slow-query logs, bundle size where applicable, and best-practice patterns via `builder_ctx7_lookup`.
- New MCP tool `builder_ctx7_lookup(library, query)` in `sdk_mcp.py`. Bounded wrapper around shell `ctx7 docs <id> "<query>"` with file-based caching (24h TTL) keyed on `(library, query)`. Refuses if rate-limited; surfaces quota errors as evidence.
- New MCP tool `builder_optimization_baseline(metric, scope)` for the optimization-agent to record metric baselines before suggesting changes. Stored in `MetricsResponse.optimization_decision` (`services/dashboard_metrics.py:65-78`, currently unstructured — formalize the schema here).
- Optimize autopilot loop: scan → generate optimization backlog items → develop autopilot picks them up (same loop as Phase 3) → for each item, supervisor verifies behavior preservation post-build-verify → autopilot ships approved items.
- Stop conditions specific to optimize mode: (a) scan produces zero new candidates above an impact threshold, (b) N consecutive optimization tasks fail behavior preservation (default 2), (c) session token budget exhausted. All flow into the existing pause-session mechanism from Phase 3.

**Reuse:**
- `post_ship_optimization.py:52-216` end-to-end pipeline.
- `optimization-agent` definition + policy already in place.
- `knowledge/evidence_graph.py:480-547` for tech-stack detection.
- `dashboard_metrics.py:65-78` `optimization_decision` field (formalize schema, no new field).
- All of develop autopilot loop from Phase 3 for the execution.
- Supervisor from Phase 1 for behavior preservation.

**Validation criteria for release:**
- ✅ Optimize scanner produces ≥ 5 plausible `--type optimization` backlog items on a real codebase (this repo or a target app). Each item has structured `baseline`, `target`, `measurement_strategy`, `behavior_preservation_contract` fields.
- ✅ ctx7 tool caches results (24h TTL), respects rate limits, never spends more than 3 lookups per scan.
- ✅ Behavior preservation verified end-to-end: an optimize-mode session runs, supervisor confirms behavior unchanged per the contract; tests pass after each merged optimization item.
- ✅ Net zero regression on functional tests in the target after a full optimize-mode cycle.
- ✅ Optimize session pauses correctly on (a) zero new candidates, (b) 2 consecutive preservation failures, (c) budget exhaustion — each with distinct `pause_reason`.
- ✅ Audit replay: from `ChatEvent` stream + `MetricsResponse.optimization_decision`, the operator can see exactly which files were touched, which baselines moved, and which were behavior-preservation-verified.

---

## Cross-Phase Concerns

- **Runtime parity.** Every new MCP tool (`builder_check_token_budget`, `builder_approve_gate`, `builder_resolve_operator_question`, `builder_ctx7_lookup`, `builder_optimization_baseline`) ships in both the Claude side (`sdk_mcp.py`) and the Codex side (its tool adapter) simultaneously. Phase 1 should add a thin tool-registration abstraction if one doesn't exist yet, to avoid duplicating tool definitions.
- **Telemetry.** Extend `builder logs analyze` to emit autopilot-specific aggregates: per-session tasks-completed, recovery rate, supervisor-disagreement rate, budget-utilization. Surface in `builder metrics show --json`.
- **Test isolation.** All autopilot end-to-end tests must use disposable workspaces (per existing pattern in `tests/test_orchestrator.py`) and stub the Claude/Codex SDK at the runner boundary — never call real models in CI.
- **Documentation.** Each phase updates `docs/quality-gate/` and `docs/workflows/` for the surfaces it touches. Use `workflow --docs-dir docs read REFERENCE` to find the correct owner location before writing new docs.

## Verification (end-to-end, post-Phase-5)

1. **Develop autopilot smoke run.** Initialize a fresh app in `/home/gurusharangupta/Builder-Workspace`, seed 3 small features in backlog. Enable autopilot via voice ("autopilot on, develop mode"). Confirm: all 3 ship without operator input; supervisor concurred on all; PR-actor records show `autopilot`; AutopilotSession in DB shows `tasks_completed=3, tasks_failed_recovered=0, tasks_failed_paused=0`.
2. **Refusal smoke run.** Manufacture a high-risk operator question in the second of 3 tasks. Confirm autopilot ships task 1, pauses on task 2 with `pause_reason=high_risk_question`, surfaces via chat ribbon + voice digest, and resumes after operator answers.
3. **Optimize autopilot smoke run.** On a project that passes the coverage adequacy gate, enable optimize mode. Confirm: scanner generates `--type optimization` backlog items; develop loop ships them; supervisor verifies behavior preservation on each; functional tests pass after the session.
4. **Coverage lockout.** On a thin-coverage project, attempt optimize mode. Confirm autopilot refuses with `pause_reason=optimize_coverage_inadequate`; operator override one-shot works; characterization-test pre-step also works.
5. **Cross-surface state sync.** With autopilot running, issue `pause` via voice, then `resume` via chat, then `stop` via dashboard within 5 seconds. Confirm the AutopilotSession state transitions in order with no race conditions and final state matches the last issued command.
6. **Runtime parity.** Repeat smoke run #1 with `RUNTIME_SDK=codex_sdk`. All criteria pass identically.

## Critical Files to Modify

(Pattern repeated across phases; representative paths.)

- **Definitions + policy:** `src/autonomous_agent_builder/agents/definitions.py`, `src/autonomous_agent_builder/agents/execution_policy.py`
- **Orchestrator:** `src/autonomous_agent_builder/orchestrator/orchestrator.py`, `src/autonomous_agent_builder/orchestrator/post_ship_optimization.py`, `src/autonomous_agent_builder/orchestrator/operator_decisions.py`
- **Services:** new `src/autonomous_agent_builder/services/token_budget.py`, new `src/autonomous_agent_builder/services/autopilot_continuation.py`, modify `src/autonomous_agent_builder/services/runtime_settings.py`, `src/autonomous_agent_builder/services/task_recovery.py`
- **Tools:** `src/autonomous_agent_builder/agents/tools/sdk_mcp.py` (+ Codex adapter equivalent)
- **API + voice:** `src/autonomous_agent_builder/embedded/server/routes/agent.py`, `src/autonomous_agent_builder/embedded/server/routes/realtime.py`, `src/autonomous_agent_builder/services/voice_operator.py`
- **DB models:** `src/autonomous_agent_builder/db/models.py` (new `AutopilotSession`)
- **Quality gates:** `src/autonomous_agent_builder/quality_gates/testing.py`
- **Tests:** add `tests/test_autopilot_phase1.py`, `..._phase2.py`, etc. — one suite per phase, plus end-to-end in `tests/test_autopilot_e2e.py`.
