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
| Last Update | 2026-05-22 — M2.3 P0 Tier B SDK fixes landed (G1/G2/G7/G12/StopFailure); M1.4 validation pending |

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
| Tier 1 — Token + UX | 2026-05-22 (M2.3 P0 batch) | Partial — `avoidable_cost_flags=[]` ✓; `chunk_pressure_risk=false` ✓; code-gen cache 71.8x ✓; provider-limit operator copy ✓; per-session G2 delta + G1 StreamEvent deferred (quota resets Jun 1) | Re-run Jun 1 on fresh code-gen session |
| Tier 2 — Lifecycle Coverage | Not yet run | Pending | Runs at M2.1 |
| Tier 3 — Head-to-Head | Not yet run | Pending | Runs at M3.4 |

---

## Recent Decisions

One line per durable decision. Keep recent 20; older → `builder memory add` if durable, else delete.

- **2026-05-22** — M2.3 P0 Tier B SDK fixes landed: `exclude_dynamic_sections=True` (G2), `include_partial_messages=True` (G1), `strict_mcp_config=True` native (G7), `PostToolUse` output-trim hook for Bash/Read/MCP (G12), `RateLimitEvent` stream-message capture → structured provider-limit payload (StopFailure). 5 ROADMAP M2.3 P0 items [x]; 5 new tests + 88 green. Evidence rerun: `avoidable_cost_flags=[]` ✓; `chunk_pressure_risk=false` ✓; code-gen cache ratio 71.8x ✓; provider-limit blocked card fires operator copy ✓. Per-session G2 delta + G1 StreamEvent capture deferred to June 1 (provider quota reset).
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
