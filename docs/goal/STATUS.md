# Status — Live Project State

> Read [README.md](README.md) and [NORTH-STAR.md](NORTH-STAR.md) first.
> Update this file whenever a [ROADMAP.md](ROADMAP.md) milestone/item transitions. See [Update Protocol](#update-protocol).

Live state. If it lies, system is blind.

---

## Current Position

| Field | Value |
| --- | --- |
| Current Epoch | **Epoch 1 — Stabilize** |
| Current Milestone | **M1.4 — Two-workspace validation rotation** |
| Current Item In Flight | **M1.4 in progress** — per-phase allowlists + preflight probes ✓; forward/reverse workspace validation pending |
| Active Workspace | `/home/gurusharangupta/Builder-Workspace/devpulse` |
| Active Runtime Lane | Claude SDK (`claude`) complete; Codex SDK (`codex_sdk`) deferred (M1.2 remaining) |
| Last Update | 2026-05-23 — Autoresearch skill restructured (single entry + 3 lanes + `docs/autoresearch/` freshness ownership). M2.3 telemetry honesty fix from earlier today still standing. M3.5 D1 (N=5 baseline) remains operator-triggered; skill now drives it via the Baseline lane. |

---

## Last Completed Milestone

**M1.3 — God-file decomposition ratchet** (closed 2026-05-21 by Claude Sonnet 4.6)

Key files <1500: `summary.py` 540, `orchestrator.py` 1345, `routes/agent.py` 1326, `voice_operator.py` 1471. `builder lint --complexity-report --json`: 0 violations. 6 extraction modules. Sequential single-agent throughout.

Prior: **M1.1** — 8 IMPs closed (full list + IMP-010..013 in [docs/IMPROVEMENTS.md](../IMPROVEMENTS.md)); **M1.2 Claude lane** — devpulse 5/5, $2.08. Re-verify: 79/79 regression tests pass.

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

Latest authoritative evidence for the current milestone. Replace on milestone advance; durable history → [docs/PROGRESS.md](../PROGRESS.md).

| Concern | Latest evidence |
| --- | --- |
| Latest agent session id (Claude lane) | Task `128e02f6` done 11:25 — scaffold (5m17s, $0.108) + code-gen (12m, $0.271) + gates + integration + build verify. IMP-010..013 resolved. |
| Latest agent session id (Codex lane) | *TBD — M1.2 not yet exercised* |
| Latest token telemetry | Session `5a752c0a`: $0.065, 2 turns — `builder logs analyze --session 5a752c0a --json` |
| Latest metrics snapshot | *TBD — run `builder metrics show --json --full --limit 8` after M1.2 dispatch* |
| Latest board snapshot | `pending=3 active=0 done=2` (2026-05-21) — `cd /home/gurusharangupta/Builder-Workspace/devpulse && builder board show --json` |
| Latest complexity report | M1.3 closed 2026-05-21 — 0 violations |
| Latest IMPs status | [docs/IMPROVEMENTS.md](../IMPROVEMENTS.md) — IMP-001..013 resolved |
| Latest sprint detail | [docs/SPRINT-PROGRESS.md](../SPRINT-PROGRESS.md) |
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

- **2026-05-23** — Autoresearch skill restructured: single entry point + 3 lanes (Baseline / Iterate / Fix). `AskUserQuestion` asks lane on every invocation unless the prompt unambiguously names one. Hard Rule 1: ROADMAP entry must land before any code change driven by the skill. Hard Rule 2: skill owns `docs/autoresearch/` freshness — every lane's closeout runs a freshness sweep over all 14 files in that folder; any drift the lane didn't cause routes to Fix lane. `README.md` + `METRICS.md` + `HARNESS.md` updated against post-2026-05-23 telemetry contract; pre-fix TSVs (`baseline_runs.tsv`, `optimize_results.tsv`, `per_prompt_results.tsv`) truncated to header-only so next Baseline starts on honest signal. ROADMAP M3.5 line ticked `[x]`.
- **2026-05-23** — M2.3 `builder logs analyze --session <id>` honestly session-scoped. Root cause of `docs/autoresearch/NEXT-SESSION.md` "telemetry gap": `_runtime_aggregates()` read `agent_runs` globally with no filter, so `top_cost_drivers`, `cache_ratio`, `cached_tokens`, `raw_token_total`, `noncached_plus_output_tokens` bled across all sessions in the DB. Per-prompt `prompts[]` is correctly operator-chat-turn-scoped (Bar 1 vocabulary contract) and was misread as the per-agent surface. Fix: new `tasks.chat_session_id` FK populated at chat-driven Task creation (`persist_sprint_execution_artifacts(... chat_session_id=session_id)`); `_runtime_aggregates(session_id=...)` and helpers (`_optimization_summary`, `_stop_reason_counts`, `_tool_counts`, `_approval_wait_summary`, `_provider_limit_summary`) scope every query via `task_id IN (SELECT id FROM tasks WHERE chat_session_id = ?)`; analyze payload now carries `runtime_aggregates.session_scoped: true` flag. `scripts/autoresearch/run.py` updated to source per-agent attribution from `runtime_aggregates.by_agent` and gate cache-ratio against the session-level `analyze["cache_ratio"]`. Unblocks M3.5 σ-floor + N=5 baseline. Evidence: new `test_logs_analyze_scopes_runtime_aggregates_to_chat_session` (two overlapping sessions, non-bleeding numbers); existing `test_logs_analyze_includes_runtime_aggregates` still green (additive behavior preserved). `docs/autoresearch/NEXT-SESSION.md` retired.
- **2026-05-22** — M3.5 Track B Phase B+C complete: `scripts/autoresearch/` populated with 5 self-contained Python scripts (run.py, baseline.py, compare.py, loop.py, extract_context_breakdown.py) implementing the HARNESS.md contract end-to-end. None import from `autonomous_agent_builder`; all invoke `builder` CLI + HTTP endpoints as subprocesses. Plus `docker-compose.yml` (optional Jaeger all-in-one), `setup_seed.sh` (immutable .seed/devpulse capture), and a README runbook. Path A context attribution via tiktoken + 10 CONTEXT-LEDGER anchors. Phase D1 (N=5 baseline across fixtures A–E, ~2 hours, ~25 model runs) and D3 (first optimization iteration) are queued for operator-triggered execution — requires `bash scripts/autoresearch/setup_seed.sh` first, then `python3 scripts/autoresearch/baseline.py`.
- **2026-05-22** — M3.5 Track B autoresearch loop activation started. Pre-harness prereqs closed: lint=0 (extracted G12 trim hook → `agents/hooks_trim.py`, runner SDK options → `agents/runner_options.py`, subagent registry → `agents/subagent_definitions.py`; ratcheted baselines). Tier-1 metrics re-verified on session `5dc61748` (cache 18019×, chunk_pressure false, avoidable_flags []). In-harness prereqs (`gate_pass_rate=1.0` per-baseline-run, N=5 variance) deferred to baseline.py in Phase D1 — chicken-and-egg with harness existence. autoresearch/README.md flipped DORMANT → ACTIVATING.
- **2026-05-22** — G1 Session rail wiring complete: `StreamEvent message_start/message_delta` per-turn usage accumulated in `runner.py`; `on_stream_usage` async callback threaded through `ClaudeRuntime` → `run_chat_runtime_loop` → `agent.py`; `publish_stream_usage` on `ChatTurnPublisher` emits `stream_usage` SSE; `AgentPage.tsx` `liveTokens` state overrides `currentTurnTokens` during active runs. 16/16 `test_agent_runner.py` green (1 new: `test_stream_event_invokes_on_stream_usage_callback`).
- **2026-05-22** — M2.3 P0 Tier B SDK fixes confirmed by live devpulse code-gen run: G2 (`exclude_dynamic_sections`) — latest 10-turn code-gen: 219592 cached / 15 raw input = **56x** per-run (99.99% cache hit); fleet code-gen: 72.4x. G12 — `avoidable_cost_flags=[]`, `chunk_pressure_risk=false`. G7 — strict MCP, no regressions. StopFailure — provider-limit blocked card fires operator copy. All 5 Tier-1 bars confirmed. `recommended_next_change: maintain_current_flow`.
- **2026-05-22** — ROADMAP SDK-grounded additions (codebase-validated): M2.3 P0 (G1/G2/G7/G12) + StopFailure hook; M2.4 G6 `include_hook_events`; M2.5 G4 file checkpointing + G13 `effort:"xhigh"`; M2.6 G5 `permissionDecision="defer"` + typed-retry refinement; M3.2 G3 `SessionStore` HARD prereq + M3.3 dependency note. INSIGHTS revalidation entry appended: withdrew standalone G8 (`AskUserQuestion` already adopted); narrowed G15 (partial in `runner.py:818-845`); audited 5 closed IMPs as already SDK-covered. Commit `2613dc6`.
- **2026-05-22** — M1.4 per-phase allowlists + preflight probes: scaffold `Glob`/`Grep` removed; gate-remediator `Glob` removed; scaffold `auto_approve_tools` AskUserQuestion bug fixed; `SubagentDefinition.max_turns` added (→ SDK `maxTurns`); `AgentRunner._preflight_workspace` added; SDK 0.2.85; `test_all_agents_defined` includes gate-remediator. 9 new tests, 88 green.
- **2026-05-22** — 10 prevention items added to ROADMAP across M1.4/M1.5/M2.1/M2.3/M2.5/M2.6 from INSIGHTS Run #7 (IMP-001..013 + recent gate-remediator → SDK levers: `can_use_tool`, `ClaudeSDKClient`, per-phase `allowed_tools`, `include_partial_messages`, `RateLimitEvent`, typed `AssistantMessageError`, `AgentDefinition.maxTurns`). Two M2.6 items = autopilot preconditions. SDK doctrine → `docs/references/coding-agent-prevention.md`.
- **2026-05-21** — M1.3 closed: `voice_operator.py` 2306→1471 via extracting `HighRiskVoiceActionService` / `VoiceCostLedger` / `build_voice_digest` / `load_voice_board_status` into 4 modules. 0 complexity violations. All 4 key files <1500 ✓.
- **2026-05-21** — M1.3 started: extracted `_publish_agent_run_*` → `agent_chat_result_publisher.py`; `_continue_after_delivery_permission_question` / `_complete_persisted_delivery_scope_approval` → `agent_delivery_continuation.py`. `routes/agent.py` 1762→1326 (<1500 ✓). M1.2 Codex lane deferred.
- **2026-05-21** — Framework governance: Hard Rules 13/14 (commit+push on `[x]`, CHANGELOG before commit) in README; `.gitignore` updated; goal/ self-containment confirmed; INSIGHTS→ROADMAP lifecycle documented; goal-audit ROADMAP cross-check added.
- **2026-05-21** — M1.2 Claude lane: devpulse 5/5, $2.08. Three source-repo gate bugs fixed: `quality_gates/testing.py` `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` removed; `feature_acceptance.py` `_TEST_SUFFIXES` added `.py`; `run-tests.js` shim pattern for Python apps.
- **2026-05-21** — Source-repo improvements (Claude Opus 4.7): `query_timeout_seconds` 90→300; code-gen "Design: " prefix fix; orchestrator walrus → pre-assignment; tests 74/75→79/79 via `_wire_db` autouse on `TestDispatchPhases`/`TestPlanningPhase`.
- **2026-05-21** — M1.1 closed. 8 IMPs resolved. IMP-010 closed: monitor-task not-stopped-on-exception + rollback guard + flush-error structlog. IMP-011 closed: SSE endpoints holding pool connections; fixed by scoping `get_session_factory()` to initial snapshot.
- **2026-05-21** — IMP-007 closed: project-level dispatch guard + prompt constraint. IMP-009 closed: scaffold timeout 30→300s + scaffold-running pre-dispatch guard.
- **2026-05-21** — Legacy strategic docs migrated: `PLAN.md`/`GOAL.md`/`MISSION.md` → deprecation stubs. New goal/ files: FIX-STANDARD, OPERATOR-LANGUAGE, TUNING. Hard Rules 7→12 in README. Working docs (PROGRESS, IMPROVEMENTS, SPRINT-PROGRESS, PROMPT, QUALITY_SCORE, REFERENCE, CHANGELOG) stay, referenced from goal/.
- **2026-05-21** — `docs/goal/` framework initial creation. Durable strategic content migrated; legacy referenced via [INDEX.md](INDEX.md).
- **2026-05-21** — Three-fold success bar finalized: operator UX + developer economics + lifecycle completeness. Both lanes first-class.
- **2026-05-21** — Epochs adopted: Stabilize → Differentiate → Scale. M1.1 = current entry (Track A blocks Track B).

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

- Write running history (→ [docs/PROGRESS.md](../PROGRESS.md)).
- Write bug detail (→ [docs/IMPROVEMENTS.md](../IMPROVEMENTS.md)).
- Write per-sprint task lists (→ [docs/SPRINT-PROGRESS.md](../SPRINT-PROGRESS.md)).
- Let this file exceed ~120 lines. Compress, archive, delete.
