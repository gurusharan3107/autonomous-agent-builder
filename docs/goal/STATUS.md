# Status — Live Project State

> Read [README.md](README.md) and [NORTH-STAR.md](NORTH-STAR.md) first.
> Update this file whenever a [ROADMAP.md](ROADMAP.md) milestone/item transitions. See [Update Protocol](#update-protocol).

Live state. If it lies, system is blind.

---

## Current Position

| Field | Value |
| --- | --- |
| Current Epoch | **Epoch 1 — Stabilize** |
| Current Milestone | **M3.5 — Optimization loop activation** (autoresearch Track B) |
| Current Item In Flight | **IMP-036 shipped** — owned `quality_gates/python_env.py` (Python-lane dep-provisioning peer to the Node `npm install` guard) + classify-before-agent in `gate_feedback.py`; 57 targeted tests green, ruff clean. Prior shipped: IMP-034a/034b-backend/035a. Next: IMP-034b frontend preview/approve card + dashboard rebuild + live E2E verify; IMP-035b/c. |
| Active Workspace | none active; devpulse idle (prior IMP-033 kanban workspace cleaned up) |
| Active Runtime Lane | Claude SDK (`claude`) complete; Codex SDK (`codex_sdk`) deferred (M1.2 remaining) |
| Last Update | 2026-06-09 — IMP-036 shipped (owned Python env provisioning + classify-before-agent). 034b frontend + 035b/c + live-verify still pending. |

---

## Last Completed Milestone

**M1.3 — God-file decomposition ratchet** (closed 2026-05-21 by Claude Sonnet 4.6)

Key files <1500: `summary.py` 540, `orchestrator.py` 1345, `routes/agent.py` 1326, `voice_operator.py` 1471. `builder lint --complexity-report --json`: 0 violations. 6 extraction modules. Sequential single-agent throughout.

Prior: **M1.1** — 8 IMPs closed (IMP-001..013; see git log); **M1.2 Claude lane** — devpulse 5/5, $2.08. Re-verify: 79/79 regression tests pass.

---

## Next Action

1. Read [README.md](README.md), [NORTH-STAR.md](NORTH-STAR.md), this file.
2. **Continue M1.4** — two `[ ]` items: (a) forward-engineering on fresh workspace (Claude lane); (b) reverse-engineering on existing workspace. See [ROADMAP § M1.4](ROADMAP.md#m14--two-workspace-validation-rotation).
3. M1.2 Codex SDK lane (deferred): same devpulse sprint on `codex_sdk` + Tier-1 evidence → unblocks M1.2's 3 remaining items.
4. Regressions → [FIX-STANDARD.md](FIX-STANDARD.md).

---

## Blockers

| Discovered | Blocked Item | Description | Unblock Condition |
| --- | --- | --- | --- |
*None.*

---

## Evidence Pointers

Latest authoritative evidence for the current milestone. Replace on milestone advance; durable history → git log + `.memory/`.

| Concern | Latest evidence |
| --- | --- |
| Latest agent session id (Claude lane) | Task `128e02f6` done 11:25 — scaffold (5m17s, $0.108) + code-gen (12m, $0.271) + gates + integration + build verify. IMP-010..013 resolved. |
| Latest agent session id (Codex lane) | *TBD — M1.2 not yet exercised* |
| Latest token telemetry | Session `5a752c0a`: $0.065, 2 turns — `builder logs analyze --session 5a752c0a --json` |
| Latest metrics snapshot | *TBD — run `builder metrics show --json --full --limit 8` after M1.2 dispatch* |
| Latest board snapshot | `pending=3 active=0 done=2` (2026-05-21) — `cd /home/gurusharangupta/Builder-Workspace/devpulse && builder board show --json` |
| Latest complexity report | M1.3 closed 2026-05-21 — 0 violations |
| Latest changelog entry | [CHANGELOG.md](../../CHANGELOG.md) |

---

## Tier Snapshot

Last result of each [EVALUATION.md](EVALUATION.md) tier. Update on milestone closeout.

| Tier | Last Run | Status | Notes |
| --- | --- | --- | --- |
| Tier 1 — Token + UX | 2026-05-22 (M2.3 P0 live run) | **All 5 bars confirmed** — code-gen cache 56x (run) / 72.4x (fleet); `avoidable_cost_flags=[]`; `chunk_pressure_risk=false`; provider-limit operator copy fires; G1 per-turn Session rail live ✓ | — |
| Tier 2 — Lifecycle Coverage | Not yet run | Pending | Runs at M2.1 |
| Tier 3 — Head-to-Head | Not yet run | Pending | Runs at M3.4 |

---

## Recent Decisions

One line per durable decision. Keep recent 20; older → `builder memory add` if durable, else delete.

- **2026-06-09** — **IMP-036 (new, closed)** — generated Python apps had no dep-provisioning owner. Every test site (testing gate, `build_verify`, the `run_tests` workspace tool, `runtime_guidance` command discovery) invoked bare `pytest`/`sys.executable` against an interpreter lacking the app's third-party deps → `ModuleNotFoundError` → the LLM gate-remediator burned its retry cap "fixing" an env failure it can't source-fix. Fix: owned `quality_gates/python_env.py` (idempotent venv-create + editable/`-r` install, canonical `pytest_argv` under the venv — the Python-lane peer to the Node `npm install` guard), wired into all 4 sites; + classify-before-agent Step 1.5 in `gate_feedback.py` (a failed gate matching an env signature re-provisions deterministically and re-runs gates, bounded by the retry budget, rather than dispatching the model). 57 targeted tests green, ruff clean. `T:backend` `T:browser:na`. Detail: ROADMAP M1.1 IMP-036 + CHANGELOG 2026-06-09.
- **2026-06-04** — **IMP-033 negative-scenario browser campaign** (new). Built `docs/goal/TESTING.md` (34 scenarios, 8 surfaces, `S:`-token tracking) + wired a generator-driven `goal-overview.html` §12 "Browser Testing" (`build_goal_overview.py` parses TESTING.md → `gen:testing` markers). Drove a fresh Kanban app (`Builder-Workspace/kanban`, claude lane) through the full forward lifecycle via `/hermes-chrome`: vague ask → 6-Q structured interview → 1 feature → approval → 3-task sprint → working app (3 cols, add/delete, localStorage persists across reload). **Batch 1: 16/34 pass, 4 blocked (need fault injection: SC-08 hung-respond, SC-16 empty-dispatch, SC-18 recover, SC-24 provider-limit), 0 product bugs** (3 false-positives self-caught: rail 0/0/0, Metrics 0, CLI `{}` — all timing/parse). Strongest passes: SC-05/06 interview integrity, SC-11 trivial-ask-not-over-decomposed (IMP-027), SC-25 chat-can't-edit-app-files (IMP-020, byte-identical proof), SC-09 builder-self routing (IMP-016). **Fixed 1 infra bug**: hermes bridge had no cross-call tab memory → tab/RAM accumulation (operator-flagged ×2); added `sessionTabs` persistence in `extension/service_worker.js` (centralizes the reuse `agents/tools/browser_tools.py` already did caller-side), deployed + verified live + orphan closed. Commits `0379c1e`, `3048c62`. Detail: ROADMAP IMP-033 + TESTING.md.
- **2026-06-01** — Root-caused the stuck-recovered-task symptom → 2 fixes. **IMP-031 (new, closed)**: Board "Recover" only reset a blocked task to a dispatchable phase (`implementation`) but never dispatched — `recover_failed_task` is reset-only ("operator can re-dispatch"), dispatch is a separate `_run_dispatch` trigger, and there's no auto-dispatch loop → task stranded silently. Fixed `BoardPage.handleRecover` to chain `dispatchTask` after `recoverTask`; verified live: recover-alone left `active_runs=0`, recover+dispatch → `active_runs=1` (run started). **IMP-003 (frontend gap found + closed)**: the in-progress `active_runs_note` was backend-only — the Metrics page never rendered it (no frontend ref). Added the render (`MetricsPage.tsx` + `OptimizationSummary` type); live-verified the note now shows during an active run → `T:browser` pass. Both shipped via `build_dashboard.sh` rebuild + restart (bundle `index-Xf8CeFgJ.js`).
- **2026-06-01** — Operator-driven marker batch (feedback widget on goal-overview). **IMP-020 → `T:browser` pass**: asked chat to directly Edit index.html — hook-blocked + routed to task dispatch, no approval card (dashboard-first intact). **IMP-029 → `T:backend:na`**: frontend-only fix (client-side AbortSignal), no backend behavior to test (was mis-tagged pending). **IMP-003**: no defect — note is correct + unit-test-covered (gated on `AgentRun.status=='running'`), but couldn't catch a running AgentRun live across 24s (task sat in `implementation` with no running run), so stays `T:browser:pending`. **IMP-028** baselined: code-gen avoidable_token_estimate=0, cache_ratio 8449x, `maintain_current_flow` — the shipped `compact_workspace_map` looks to have resolved the replay; remaining A/B + preset-trim needs a dedicated session. Browser ✓ ticks → 10.
- **2026-06-01** — Live re-verify completed (bridge recovered). **IMP-029 closed**: in the reused shipped session, the new decision card now renders enabled Start now/Hold; clicked Start now → answer registered, delivery started, new task `9177ec3f` spawned → fix confirmed. **IMP-017 → `T:browser` pass**: the IMP-030 rebuild exposed the Backlog "Cancel item" control; cancelling item `f730b511` drove it to terminal `cancelled` (API-confirmed). **G1** re-confirmed live (Session rail 1,821 tok during a running turn). IMP-003 (Metrics in-progress diagnostic) + IMP-020 still pending (no active run / not exercised).
- **2026-06-01** — Fixed IMP-030 + IMP-029 root cause. **IMP-030 closed**: added `scripts/build_dashboard.sh` (vite build → rsync to `embedded/dashboard`), rebuilt + restarted the builder so it serves a fresh bundle (`index-jlc1ZA4V.js`) instead of the stale 2026-05-20 one. **IMP-029** root cause (code-inspection): the only disable path for decision-card answer controls is `submittingEventId === item.id`, cleared only in `submitQuestion`/`submitApproval`'s `finally`; `/api/agent/chat/respond` had no timeout, so a hung respond stranded the lock → controls permanently disabled. Fix `AgentPage.tsx`: `AbortSignal.timeout(30s)` on both responds + a `useEffect` resetting the lock when the blocking item changes. Earlier "duplicate-button" theory disproved — `AgentThreadCards` renders answered questions as text, not buttons. Live re-verify of IMP-029/IMP-017/IMP-003 blocked by a hermes-chrome blank-active-tab state post-restart (not a builder defect); fixes are built + served.
- **2026-06-01** — Goal testing-matrix made honest + browser-verified. status skill/generator/lint gained a `:na`→✗ test state + a both-lanes invariant (lint WARNs on any checkbox missing `T:backend`/`T:browser`); all 131 ROADMAP checkboxes now tagged (no untagged "—"). hermes-chrome E2E on pomodoro @:9876 verified **6 of 9** `T:browser:pending` completed items → pass: IMP-018 (Start now/Hold question card), G1 (Session rail 578 tok/$0.1091), IMP-023 (Metrics headline 5,417/$0.3659), IMP-015 (FEATURE label), IMP-004 (Recover on blocked task), D2 (lifecycle on Board). Still pending: IMP-003 (in-progress capture raced), IMP-020 (not run), IMP-017 (no cancel control in live bundle). Filed **IMP-029** (new instruction into a shipped session → blocked card with disabled controls) + **IMP-030** (no `frontend`→`embedded/dashboard` build→sync→restart pipeline; bundle predates IMP-017).
- **2026-05-30** — Token-cost lever work (branch `imp-027-model-driven-task-decomposition`). DB-verified that trivial-feature burn is **planning-time over-decomposition**, not verifier reruns (deterministic phases record `0,0,0,0` tokens). Shipped **IMP-027a/c** (`851ba75`): chat intake emits `proposed_tasks` sized to the real change as structured model output — a trivial ask now yields 1 task, not a 5-task keyword-template sprint (live-proven on recall-loop). Shipped **IMP-028** (`1ebb84b`): orchestrator injects a ~77-token `compact_workspace_map` into code-gen to cut per-turn re-exploration (code-gen run is ~89% context). Fixed **IMP-021** (`1d1545f`): 3 pre-existing doc-routing tests — real causes were compact-JSON staleness + IMP-020 Bash-deny fallout (test-only fix; the `canonical_ref` theory was wrong). Full suite `1574 passed, 0 failed`. **Bookkeeping note:** code shipped in those 3 commits without a CHANGELOG entry; recorded retroactively this session. IMP-027/028 stay `[ ]` (027b per-task phase planner + 028 live-A/B and Claude-Code-preset experiment still open). Detail: CHANGELOG 2026-05-30 + ROADMAP M1.1 IMP-027/028.
- **2026-05-30** — M1.1 **IMP-020 resolved** as a design call: the interactive chat lane must **never** edit the generated app directly (even with operator approval), because that bypasses the dashboard-first visible SDLC — grounded in CLAUDE.md doctrine ("drive backlog, task, approval, execution through the Agent page"; "Do not infer vague user intent into a mutating lifecycle action"). `agent_tool_policy.chat_mutating_builtin_denial()` + `CHAT_DISPATCH_REQUIRED_BUILTINS = {Edit, Write, Bash, MultiEdit, NotebookEdit}`; `_authorize_chat_tool` denies these (scoped to *ungranted* built-ins, after the preapproved/read-only checks) with a `mcp__builder__task_dispatch` routing message + a `tool_error` event instead of an Approve/Deny card. Granted/confirmable non-built-in mutating tools (e.g. `mcp__workspace__run_command`) keep their cards — the IMP-018 tested approval path is intact (the card-deny regression test was repointed `Bash`→`mcp__workspace__run_command`). 43/43 affected tests green; ruff clean. Surfaced **IMP-021** (pre-existing, not caused by this change): `test_chat_routes_explicit_documentation_intent_to_subagent` is env-sensitive — `resolve_canonical_doc_ref()` returns the temp repo's `master`, not the asserted `"main"`. Full detail: ROADMAP M1.1 IMP-020/021 + CHANGELOG 2026-05-30.
- **2026-05-30** — Operator-driven dashboard validation on a fresh app (recall-loop flashcards). M1.1 **IMP-018** closed (interview free-text → structured `AskUserQuestion`; root cause global `permission_mode="dontAsk"` bypasses `can_use_tool`; fix = per-agent `permission_mode`, `chat`→`"default"` + `preapproved_tools` guard) and **IMP-015** closed (`type=feature` shown as "improvement"; `BacklogPage.itemTypeLabel` + `agent_chat_result_publisher` save-note + `agent_sprint_planning` question now type-aware/neutral; coupled parser made type-agnostic) — both validated live. Built **IMP-019** real-browser self-verification: in-process `browser` SDK MCP server over the Hermes bridge (`mcp__browser__*`) wired into `feature-verifier`/`build-verifier`/`browser-verifier`, `_to_mcp` content envelope, `tool_registry` schemas (P19 registry-drop gap caught by a live run), non-blocking `browser_evidence_tier` advisory; audited via `agent-sdk-verifier-py`; tool path proven live (bridge→Chrome→app). Found **IMP-020** (open, deferred): IMP-018's `"default"` lets the chat lane offer Approve/Deny cards for ungranted mutating built-ins (Edit/Write/Bash) on the generated app — can bypass backlog→dispatch; fix is a design call (approval-card path is intentional/tested). Branch `imp-018-015-019-browser-verify`. Full detail: ROADMAP M1.1 IMP-018/015/019/020 + CHANGELOG 2026-05-30.
- **2026-05-29** — Goal folder revalidated against live code (roadmap-audit). Closed phantom work: M2.5 `AgentDefinition.maxTurns` ticked `[x]` (already shipped under M1.4 — `definitions.py` + `runner_options.py:61`). Narrowed to true remaining gap: M1.5 `query()`→`ClaudeSDKClient` (only `claude_runtime.py:265` chat path left; `runner.py:690` already migrated), M2.6 `can_use_tool` subagent-boundary deny (deny exists for chat tools `agent_tool_policy.py:52`; subagent path `claude_runtime.py:236 _auto_approve` always allows). Downgraded: M2.1 `receive_response` early-break audit P0→hardening (single site `runner.py:692`, no break). Confirmed-absent: M3.2 G3 `SessionStore` (HARD prereq for M3.2+M3.3). Validated top-priority open queue = G3 SessionStore + subagent `can_use_tool` deny + IMP-014/016/017. Full table: [INSIGHTS.md](INSIGHTS.md) 2026-05-29.
- **2026-05-29** — devpulse dashboard validation (hermes-chrome-driven E2E) surfaced 5 builder findings → ROADMAP: M1.1 IMP-014 (Observability fires dispatch-blocking rec on 8-day-stale `mcp__builder__task_*` errors), IMP-015 (`type=feature` rendered as "IMPROVEMENT"), IMP-016 (chat agent mis-routes builder-improvement asks into the app backlog; no builder-self-improvement lane), IMP-017 (no operator-facing remove/cancel/archive for backlog items — verified across dashboard/CLI/enum/REST); M2.1 +2 lifecycle features (auto-complete feature/backlog-item when tasks done) that were mis-filed as devpulse app features (one `sprint_planned`, left in place pending IMP-017). Routing rule recorded: app-related → app backlog, builder-related → ROADMAP. Tooling PR #3 (hermes-chrome bridge + self-optimize `mine_sessions.py` + builder-test hermes-chrome E2E driver) merged to master; `main` deleted, `master` is now the GitHub default.
- **2026-05-23** — M1.3 0-violation gate **fully re-closed**. All 7 violations resolved across two commits (logs.py extraction first, then the remaining six in a single follow-up). Resolutions: (1) `cli/commands/logs.py` 1679→1346 via two sibling extractions (`logs_runtime_aggregates.py` 408 + `logs_db_utils.py` 37); side-effect cleanup removed a dead duplicate `_table_columns`. (2) `services/sprint_execution.py` 828→825 by collapsing `task_uses_sprint_plan` / `task_uses_sprint_design` two-line bodies into single returns and compacting `_task_sprint_execution`. (3) `db/models.py` 679→676 by trimming the `set_task_status` docstring + dropping an inline comment that restated the body. (4) `embedded/server/agent_sprint_planning.py` 502→499 by rewriting `_format_sprint_planning_options` as a one-line generator. (5) `tests/test_builder_cli_surfaces.py` 2734→2574 by extracting the five `test_agent_runtime_set|show_*` tests into a focused `test_builder_cli_agent_runtime.py` (159 lines moved). (6) `.claude/skills/autoresearch/scripts/introspect.py` 806 + (7) `scripts/autoresearch/run.py` 636 registered with baseline entries — autoresearch tooling, not product code (first tooling-class entries in `complexity-baseline.json`). New lint behavior surfaced and respected: `baseline_not_ratcheted_down` means each shrink must update the baseline in the same commit. `freshness_sweep.py:check_logs_emits_session_scoped` re-pointed to the new file. Validation: `builder lint --complexity-report --json` clean; 79/79 affected tests green; freshness sweep clean. **M3.5 D1 (N=5 baseline) unblocked.**
- **2026-05-23** — Project-local `save-session` + `resume-session` skills at `.claude/skills/`. Replace removed user-global versions (whose body triggered compaction). Terse Bash-heredoc save into `.claude/session-data/CURRENT.md`; resume synthesizes from CURRENT + STATUS + git log. Dogfooded — this session's checkpoint is at `.claude/session-data/CURRENT.md`.
- **2026-05-23** — M2.3 `builder logs analyze --session <id>` honestly session-scoped. Root cause of `docs/autoresearch/NEXT-SESSION.md` "telemetry gap": `_runtime_aggregates()` read `agent_runs` globally with no filter, so `top_cost_drivers`, `cache_ratio`, `cached_tokens`, `raw_token_total`, `noncached_plus_output_tokens` bled across all sessions in the DB. Per-prompt `prompts[]` is correctly operator-chat-turn-scoped (Bar 1 vocabulary contract) and was misread as the per-agent surface. Fix: new `tasks.chat_session_id` FK populated at chat-driven Task creation (`persist_sprint_execution_artifacts(... chat_session_id=session_id)`); `_runtime_aggregates(session_id=...)` and helpers (`_optimization_summary`, `_stop_reason_counts`, `_tool_counts`, `_approval_wait_summary`, `_provider_limit_summary`) scope every query via `task_id IN (SELECT id FROM tasks WHERE chat_session_id = ?)`; analyze payload now carries `runtime_aggregates.session_scoped: true` flag. `scripts/autoresearch/run.py` updated to source per-agent attribution from `runtime_aggregates.by_agent` and gate cache-ratio against the session-level `analyze["cache_ratio"]`. Unblocks M3.5 σ-floor + N=5 baseline. Evidence: new `test_logs_analyze_scopes_runtime_aggregates_to_chat_session` (two overlapping sessions, non-bleeding numbers); existing `test_logs_analyze_includes_runtime_aggregates` still green (additive behavior preserved). `docs/autoresearch/NEXT-SESSION.md` retired.
- **2026-05-22** — G1 Session rail wiring complete: `StreamEvent message_start/message_delta` per-turn usage accumulated in `runner.py`; `on_stream_usage` async callback threaded through `ClaudeRuntime` → `run_chat_runtime_loop` → `agent.py`; `publish_stream_usage` on `ChatTurnPublisher` emits `stream_usage` SSE; `AgentPage.tsx` `liveTokens` state overrides `currentTurnTokens` during active runs. 16/16 `test_agent_runner.py` green (1 new: `test_stream_event_invokes_on_stream_usage_callback`).
- **2026-05-22** — M2.3 P0 Tier B SDK fixes confirmed by live devpulse code-gen run: G2 (`exclude_dynamic_sections`) — latest 10-turn code-gen: 219592 cached / 15 raw input = **56x** per-run (99.99% cache hit); fleet code-gen: 72.4x. G12 — `avoidable_cost_flags=[]`, `chunk_pressure_risk=false`. G7 — strict MCP, no regressions. StopFailure — provider-limit blocked card fires operator copy. All 5 Tier-1 bars confirmed. `recommended_next_change: maintain_current_flow`.

- Older decisions (≤2026-05-22 — M1.1/M1.2/M1.4 closures, framework creation, SDK-additions) trimmed 2026-05-29 for the ≤120-line cap; audit trail lives in [ROADMAP.md](ROADMAP.md) `[x]` items, [INSIGHTS.md](INSIGHTS.md), and git history.

---

## Cross-Session Continuity Hints

[Current Position](#current-position) stale or ambiguous → don't start new work:

1. Open [RESUME.md](RESUME.md), follow protocol.
2. Cross-check dashboard (`builder map`, `builder board show --json`, `builder server status --port 9876 --json`) against this file.
3. Reality differs → **fix this file first**. Wrong STATUS = Tier 1 resumability failure.

---

## Update Protocol

**When:** item `[ ]`→`in_progress`→`[x]`; milestone/epoch transition; blocker discovered/cleared; durable decision; Tier of [EVALUATION.md](EVALUATION.md) run.

**How:**

1. Edit [Current Position](#current-position).
2. Move closed milestones → [Last Completed Milestone](#last-completed-milestone).
3. Replace [Next Action](#next-action).
4. Append one-liner to [Recent Decisions](#recent-decisions) if durable.
5. Update [Tier Snapshot](#tier-snapshot) on tier run.
6. Update [Evidence Pointers](#evidence-pointers) on source change.
7. Set `Last Update` to today + author.

**Don't:**

- Let this file exceed ~120 lines. Compress, archive, delete.
