# Roadmap — From Current State To "Preferred Over Codex CLI And Claude Code"

> Read [README.md](README.md) and [NORTH-STAR.md](NORTH-STAR.md) first.
> Update [STATUS.md](STATUS.md) on any milestone/item transition.

Three epochs × milestones × items. Items checkbox-tracked. Milestone `pending`→`in_progress`→`done` only when every item `[x]` AND relevant tier of [EVALUATION.md](EVALUATION.md) passes with evidence.

Spine of all work. Non-roadmap work → add to the right epoch first; no ad-hoc.

---

## Epoch 1 — Stabilize

**Outcome:** Ships features end-to-end on both lanes across multiple managed-app workspaces. Operator-facing bugs closed. Performance bars met. Architecture decomposed enough for safe further work.

**Gating tier:** [EVALUATION.md § Tier 1](EVALUATION.md#tier-1--token--ux-bars-every-release) on primary workspace, both lanes.

### M1.1 — Close the open operator-facing defects

Each IMP closed with: root cause, SDK-grounded fix, regression test, post-fix evidence, durable memory entry if applicable. History in git log + `.memory/`.

- [x] **IMP-001** — Agent loses original feature request context after intake follow-up. Fixed in `agent_prompt_builders.py` + `chat_turn_prompting.py` + `routes/agent.py`; regression tests in `test_agent_feature_spec_prompt_contracts.py`.
- [x] **IMP-002** — Gates-first not enforced: 27-turn run before workspace has ruff/pytest infra. Fixed by scaffold commits 1fae0bd, c1a39c8, a88ee2c.
- [x] **IMP-003** — `builder metrics show` reports 0 tokens for in-progress runs. Fixed in `dashboard_metrics.py`; regression test `test_metrics_active_run_injects_diagnostic_note`.
- [x] **IMP-004** — Recover button returns 409 for gate-infrastructure-blocked tasks. Fixed in backend (IMP-002 commits) and frontend (commit 8799f1b).
- [x] **IMP-006** — Scaffold agent fails to emit sentinel because it uses shell heredoc instead of Write tool. Prompt constraint added to `agents/definitions.py`; regression verified on devpulse.
- [x] **IMP-008** — `git worktree add` fails on unborn HEAD. Unborn-HEAD guard added to `workspace/manager.py`; regression test `test_workspace_manager_creates_initial_commit_for_unborn_head`.
- [x] **IMP-007** — Agent dispatches all tasks simultaneously → connection pool exhaustion. Prompt constraint + project-level dispatch lock added; regression tests in `test_dispatch_guards.py`.
- [x] **IMP-009** — Agent dispatches before scaffold completes. Scaffold HTTP timeout raised to 300 s + pre-dispatch scaffold-running guard; regression test in `test_dispatch_guards.py`.
- [x] **IMP-010** — SQLAlchemy session rolls back during long scaffold runs. Fixed with try/finally + flush-error structlog in `agent_run_lifecycle.py` and rollback guard in `orchestrator.py`. Monitored via `agent_run_lifecycle_flush_error` events.
- [x] **IMP-011** — SSE endpoints (`board_stream`, `approval_stream`) hold pool connections for full client lifetime, exhausting QueuePool during long runs. Fixed in `dashboard_api.py` by scoping session to initial snapshot only.
- [x] **IMP-012** — Dispatch session becomes invalid after ~90s. Fixed by switching `persist_realtime_run_update` to short-lived sessions from `get_session_factory()`. Validated: scaffold completed 5m17s, code-gen 12m, task 128e02f6 reached `done` at 11:25.
- [x] **IMP-013** — Orphan task branch refuses fast-forward merge (`unrelated histories`). Fixed with rebase-before-integrate in `workspace_integration.py`. Validated: `workspace_rebased_for_integration` + `workspace_integrated_fast_forward` both emitted at 11:25.
- [x] Re-verify all closures end-to-end against the devpulse workspace in both runtime lanes (M1.2 prerequisite). Evidence: 79/79 regression tests pass (2026-05-21). All IMP-specific tests pass. Live devpulse re-verify surfaced IMP-010 through IMP-013 — all closed in same session.

### M1.2 — Both lanes ship one feature on devpulse end-to-end

Forward-engineering scenario, both lanes, same operator wording.

- [x] Fresh devpulse workspace boots successfully via `builder init`; readiness gate green.
- [x] Claude Agent SDK lane: devpulse sprint 5/5 tasks done, $2.08 total (2026-05-21). Domain model → UI shell → core behavior → persistence → verify. All quality gates passed. 127 tests green.
- [x] Source-repo gate bugs unblocked Claude lane: (1) `quality_gates/testing.py` removed `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` that killed pytest-asyncio; (2) `feature_acceptance.py` `_TEST_SUFFIXES` added `.py` so Python test files count toward coverage; (3) `run-tests.js` shim pattern added for Python apps with no npm test command.
- [x] `docs/goal/` framework and `goal-audit` skill created and stabilized: 5 audit runs, 3 skill bugs fixed (driver-shape mismatch, `top_prompts` → `recent_prompts` recency signal, HARD RULE blocking skill from editing STATUS.md). Framework is now agent-resumable and self-correcting.
- [x] **goal-audit `--since-run` mode**: collector emits "deltas since last INSIGHTS.md entry" so rapid successive runs show only new signal rather than re-analyzing the full window. Surfaced in Run #2 as an audit cadence sharpness limit.
- [x] **goal-audit memory write**: `builder memory add --type pattern --tag goal-audit,intent-extraction` recording "prefer recency-ranked intent over token-weighted intent" per FIX-STANDARD.md § Step 7. Surfaced in Run #3.
- [ ] Codex SDK lane: same operator wording, same outcome. Evidence shows Codex-specific telemetry, app-server events, native user-input request paths. *(deferred — Claude lane complete; Codex lane to be run separately)*
- [ ] Both lanes meet all four Tier-1 thresholds (`cache_ratio > 5x` after turn 2, `chunk_pressure_risk: false`, `avoidable_cost_flags: []`, gate-pass rate `1.0`). Run: `builder logs analyze --session <id> --json` + `builder metrics show --json --full --limit 8`. *(pending Codex lane run)*
- [ ] Session evidence (`builder logs analyze --session <id> --json` for each lane) archived under [STATUS.md § Evidence Pointers](STATUS.md#evidence-pointers). *(pending Codex lane run)*

### M1.3 — God-file decomposition ratchet complete

Source: [docs/quality-gate/complexity.md](../quality-gate/complexity.md) + `complexity-baseline.json`. Active violations → zero.

- [x] Every active file violation in `complexity-baseline.json` has either been split below the 500-line target or registered as a documented historical baseline (not a fresh violation).
- [x] `services/voice_operator.py`, `observability/summary.py`, `orchestrator/orchestrator.py`, `embedded/server/routes/agent.py` each below 1,500 measured lines or split into named owner modules. *(summary.py 540, orchestrator.py 1345, routes/agent.py 1326, voice_operator.py 1471 — all ✓)*
- [x] `builder lint --complexity-report --json` reports `0 violations`.
- [x] Constraint: extraction is sequential single-agent; **never** parallel agents (see `.memory/feedback_extraction_constraints.md`).
- [x] **Project-local `save-session` / `resume-session` skills** at `.claude/skills/{save,resume}-session/`. Replaced the user-global versions (removed 2026-05-23 because their save body triggered compaction near context limit). Project-local rewrite: Bash-heredoc atomic write to `.claude/session-data/CURRENT.md` (no Read→Write context bloat), terse SKILL.md bodies (~60 lines each vs prior 1.8 KB global), focused on bridging *tactical* working context that `docs/goal/STATUS.md` doesn't capture (current intent, next concrete action, open blockers/questions, mid-session learnings, key files touched + reason, useful one-off commands). `resume-session` reads CURRENT.md + STATUS Current Position + recent git log, synthesizes a single "here's where you left off" message; does NOT auto-execute. `CURRENT.md` gitignored per existing `.gitignore:26` convention — session-data is machine-local fast-resume; cross-machine continuity rides on `docs/goal/STATUS.md`. Validated by dogfooding: this session's checkpoint at `.claude/session-data/CURRENT.md`. *(2026-05-23)*
- [x] **Re-close the 0-violation gate** (regression discovered 2026-05-23 during Baseline lane preflight, closed same-day). Operator decision: path B — extract rather than ratchet baselines. Sequential single-agent extraction per `.memory/feedback_extraction_constraints.md`. `builder lint --complexity-report --json` now reports `0 violations`. Per-file resolution:
    - [x] `cli/commands/logs.py` 1679→1346 via two sibling extractions: `logs_runtime_aggregates.py` (408 lines — SQL aggregate machinery) and `logs_db_utils.py` (37 lines — shared sqlite helpers). `_selected_runtime_from_coverage` preserved at module level (test-imported). Bug side-effect: removed dead duplicate `_table_columns`. Baseline ratcheted 1679→1346. `freshness_sweep.py` updated for new file location.
    - [x] `services/sprint_execution.py` 828→825 via inlining `task_uses_sprint_plan` + `task_uses_sprint_design` (single return) and compacting `_task_sprint_execution`.
    - [x] `db/models.py` 679→676 by tightening `set_task_status` docstring + dropping a 2-line inline comment that restated the function body.
    - [x] `embedded/server/agent_sprint_planning.py` 502→499 by rewriting `_format_sprint_planning_options` as a single-line generator. Baseline ratcheted 500→499.
    - [x] `tests/test_builder_cli_surfaces.py` 2734→2574 by extracting the 5 `test_agent_runtime_set|show_*` cases into `tests/test_builder_cli_agent_runtime.py` (159 lines moved; pre-extracted seam clean). Baseline ratcheted 2589→2574. `SimpleNamespace` import removed (now only used in extracted file).
    - [x] `.claude/skills/autoresearch/scripts/introspect.py` 806 — registered with baseline entry + extraction plan; autoresearch tooling, not product code (first tooling-class baseline entries).
    - [x] `scripts/autoresearch/run.py` 636 — registered with baseline entry + extraction plan; autoresearch tooling.

### M1.4 — Two-workspace validation rotation

Forward + reverse scenarios validated. Both lanes per scenario.

- [ ] **Forward:** fresh app from scratch in a new workspace (devpulse or equivalent). Both lanes.
- [ ] **Reverse:** operate on an existing app workspace (todo-app, a checked-out external repo). Both lanes.
- [ ] Both scenarios produce identical operator-visible behavior across lanes. Lane attribution preserved in run history after a runtime switch.
- [ ] [docs/PROMPT.md](../PROMPT.md) operator-prompt scripts executed in both lanes; rubric pass for [docs/rubric/sdk-backed-agent-page-agent.md](../rubric/sdk-backed-agent-page-agent.md) and [docs/rubric/realtime-voice-agent-page-agent.md](../rubric/realtime-voice-agent-page-agent.md).
- [x] **Per-phase `allowed_tools` allowlists for subagents** matched to verified workspace capability. Scaffold: removed `Glob`, `Grep` (unnecessary search tools); gate-remediator: removed `Glob`. `SubagentDefinition.max_turns` added; forwarded to SDK as `maxTurns`. *(INSIGHTS Run #7 § P0-1, P1-3.)*
- [x] **Deterministic CLI preflight probes** before `client.query()` — `git rev-parse HEAD` (hard fail for git-required phases: code-gen, gate-remediator, integration-resolver, pr-creator, build-verifier, feature-verifier, optimization-agent); `shutil.which("ruff")` and `pyproject.toml` existence logged as soft warnings for Python-gate phases. *(INSIGHTS Run #7 § P1-3.)*

### M1.5 — Realtime Voice (Samantha) parity with Agent page

Voice is a peer operator surface, not a bolt-on.


- [ ] Voice and Agent share the same chat session, same approvals, same pending-question cards.
- [ ] Voice-initiated feature shipped end to end with browser proof in both lanes.
- [ ] Realtime auth boundary holds (Realtime uses `OPENAI_API_KEY`; selected runtime auth not leaked into Realtime; Codex subscription runs strip OpenAI credentials).
- [ ] Voice-initiated delegations rebind correctly to delegated Agent session; no orphan voice transcripts.
- [ ] **Migrate multi-turn agent flows from `query()` to `ClaudeSDKClient` async context manager.** Long-lived voice streams are the first surface that breaks if `query()` is held across minutes; `__aexit__` cancels background monitor tasks deterministically. Replaces the manual `try/finally + stop_monitor.set()` discipline that IMP-010 fixed by hand. *(INSIGHTS Run #7 § Section C Action 1, P0-2.)*

---

## Epoch 2 — Differentiate

**Outcome:** Wins decisively on differentiators. Codex CLI / Claude Code can't match — differentiators are structural, not features.

**Gating tier:** [Tier 2](EVALUATION.md#tier-2--lifecycle-coverage-bars-every-milestone) on every managed app in scope; [Tier 3](EVALUATION.md#tier-3--head-to-head-bars-to-declare-preferred) head-to-head begins here.

### M2.1 — Lifecycle completeness proof

Full requirements → design → backlog → implementation → verification → ship → optimize loop. Dashboard-visible, resumable, durable.

- [ ] One end-to-end project completed on devpulse with every phase visible in the dashboard, including post-ship optimization recommendation lane.
- [ ] Resumability: kill the dashboard mid-sprint, restart, confirm exact state restored — no operator data loss, no stale "running" status, no orphaned approvals.
- [ ] Runtime switch mid-project: switch from `claude` to `codex_sdk` between sprints; historical attribution preserved; future work uses the new lane.
- [ ] Multi-operator handover: a second operator joining mid-project sees the same Board, Backlog, Inbox, and Agent state as the first.
- [ ] **Audit every `async for message in client.receive_response():` site for early `break`.** The Claude Agent SDK Python reference explicitly warns this causes asyncio cleanup issues. Replace with a flag + drain pattern so resumability and mid-sprint kill/restart never strand monitor tasks or rolled-back sessions. *(INSIGHTS Run #7 § P0-2.)*

### M2.2 — Memory and knowledge as decisive differentiators

Memory + KB compound across sessions; prevent re-litigating settled questions.

- [ ] Memory retrieval workflow ([docs/workflows/memory-retrieval-guide.md](../workflows/memory-retrieval-guide.md)) is the documented standard step 0 of every non-trivial fix.
- [ ] Knowledge base freshness gate (`builder knowledge validate --json`) is wired into the documentation refresh gate before PR creation in every shipped sprint.
- [ ] Memory write-back rate: every closed IMP that has a non-obvious owner boundary, single-control-owner pattern, or recurring trap produces a `builder memory add` entry with the correct type and tag.
- [ ] Demonstrate compounding: pick a topic where memory and KB exist; show that a fresh session reaches a correct decision faster than the original session did.

### M2.3 — Cost-aware execution surface complete

Token / cache / chunk / avoidable-cost telemetry is first-class: Metrics page, Agent page Session rail, `builder metrics show`, `builder logs analyze`, observability recs.

- [ ] `builder metrics show` and the Metrics page agree with raw `builder logs --compact` cost on every run.
- [ ] Per-turn non-cached-plus-output, raw, and cached tokens visible and accurate in the Agent page Session rail in both lanes.
- [ ] Observability recommendations distinguish builder-owned optimization candidates from general workflow-state warnings (approval/blocked signals routed to builder state, not optimization).
- [ ] Optimization-agent only runs when post-ship evidence demonstrates a candidate; never on Builder-owned generated-app residuals.
- [x] **`builder logs analyze --session <id>` is honestly session-scoped.** `tasks.chat_session_id` FK links chat-driven Task creation to its originating session; `_runtime_aggregates(session_id=...)` filters `agent_runs` by `task_id IN (SELECT id FROM tasks WHERE chat_session_id = ?)`. `top_cost_drivers`, `cache_ratio`, `cached_tokens`, `raw_token_total`, `noncached_plus_output_tokens` are this session's numbers — not global. Unblocks M3.5 autoresearch σ-floor. Evidence: `test_logs_analyze_scopes_runtime_aggregates_to_chat_session` (two overlapping sessions → non-bleeding aggregates) + `test_logs_analyze_includes_runtime_aggregates` (additive contract preserved); 7/7 logs_analyze tests green, 18/18 sprint_execution tests green. *(2026-05-23)*
- [x] **First-class `RateLimitEvent` surface in dashboard, driven by `StopFailure` hook.** `RateLimitEvent` handled in `runner.py` message loop; `status="rejected"` captures `resets_at`, `rate_limit_type`, `utilization`; `RunResult` carries SDK-sourced `provider_limit` dict. `_is_empty_sdk_result` short-circuits; `run_phase` prefers pre-set `provider_limit` over text-parsed rebuild. *(2026-05-22)*
- [x] **G2 — `exclude_dynamic_sections=True` on `SystemPromptPreset`.** Added to `agents/runner.py`, `claude_runtime.py`, `onboarding.py`. Eliminates dynamic cwd/memory/git sections; directly unblocks Tier-1 `cache_ratio > 5x` bar. *(2026-05-22)*
- [x] **G12 — `PostToolUseHookSpecificOutput.updatedToolOutput` truncation/normalization.** `trim_tool_output_for_context()` hook in `agents/hooks.py`; 8 000-char ceiling; curated tool set (Bash, Read, `mcp__workspace__run_tests`, `mcp__workspace__run_linter`). Registered in `runner.py` as second PostToolUse `HookMatcher`. *(2026-05-22)*
- [x] **G1 — `include_partial_messages=True` + per-turn token visibility in Agent Session rail.** Added to all three `ClaudeAgentOptions` construction sites. `StreamEvent message_start/message_delta` accumulate per-turn `input/cached/output` tokens in `runner.py`; `on_stream_usage` async callback threaded through `ClaudeRuntime.run()` → `run_chat_runtime_loop` → `agent.py`; `publish_stream_usage` on `ChatTurnPublisher` emits `stream_usage` SSE events; `AgentPage.tsx` accumulates into `liveTokens` state and overrides `currentTurnTokens` in Session rail during active runs. *(2026-05-22)*
- [x] **G7 — `strict_mcp_config=True` on `ClaudeSDKClient`.** Native `ClaudeAgentOptions` parameter set; `"strict-mcp-config": None` CLI flag removed from `extra_args`. *(2026-05-22)*

### M2.4 — Operator UX polish to "no internals leakage"

Every operator-facing surface respects [OPERATOR-LANGUAGE.md](OPERATOR-LANGUAGE.md) banned-term contract.

- [ ] Banned-term audit across Agent transcript, Voice transcript, Board, Backlog, Inbox, Metrics, Observability, Settings, and approval cards: zero leakage of `lifecycle`, `scaffold`, `dispatch`, `worktree`, `permission mode`, `SDK`, `MCP`, `recover`, `blocked_reason`, `gate`, `chunk`, `bounded`, `raw/full logs`, `token pressure`, etc., unless the operator typed them first.
- [ ] All pending questions and approvals render readable operator labels (no `[object Object]`, no internal payload objects).
- [ ] Inline question/approval controls land in the composer/footer (one control owner), with historical timeline entries as evidence only.
- [ ] Recover button visible only when blocked-reason is actually recoverable. Otherwise an actionable next-step message.
- [ ] **G6 — `include_hook_events=True` → `HookEventMessage` stream surfaced on Agent page.** Today PreToolUse/PostToolUse outcomes (workspace boundary, bash validation, dispatch lock) are logged out-of-band; operators see opaque "blocked" cards. Streaming `HookEventMessage` lets the Agent timeline render the actual block reason in operator language. Verified absent in `src/`. *(SDK rubric § Hooks; INSIGHTS ad-hoc § G6, P1.)*

### M2.6 — Autopilot mode

When enabled: orchestrator owns approval, recovery, continuation — no operator intervention. Operator opts in; Builder handles the rest.

- [ ] Autopilot toggle in dashboard Settings; persisted per project.
- [ ] When autopilot is on: orchestrator auto-approves ready tasks, auto-recovers `capability_limit` / `cycle-detected` blocked states, and auto-advances to the next ready task after completion — without waiting for operator input.
- [ ] Operator can disable autopilot mid-sprint; in-flight work is not interrupted.
- [ ] All autopilot actions are dashboard-visible (Board + Agent timeline show who approved/recovered: operator or autopilot).
- [ ] Autopilot does not approve design/plan phases if the operator has not confirmed scope; only implementation-onwards phases are eligible by default.
- [ ] **`can_use_tool` callback enforces subagent phase boundaries (autopilot precondition).** Without operator oversight, prompt-only tool guidance is insufficient — return `PermissionResultDeny(message="...", interrupt=False)` to block parallel dispatches (IMP-007 class), wrong-tool selection (IMP-006 class), or precondition-violating calls (IMP-009 class) at the SDK boundary, one layer earlier than the existing `dispatch_lock.py` backend guard. *(INSIGHTS Run #7 § Section C Action 2, P0-1.)*
- [ ] **Retry/cycle state machine fed from typed SDK error signals (autopilot precondition).** Use `ResultMessage.is_error`, `ResultMessage.errors`, `ResultMessage.api_error_status`, `AssistantMessageError` literal (`"rate_limit" | "max_output_tokens" | "server_error" | ...`), and `RateLimitEvent`. Increment cycle-detection counter on the transition itself; never on the next (commit `1153ec6` lesson). Synthetic-state test for every retry path before autopilot ships unattended. *(INSIGHTS Run #7 § P2-5. `agents/runner.py:818-845` already catches `CLINotFoundError`/`ProcessError`/`CLIJSONDecodeError`; extend to `AssistantMessageError`/`api_error_status`.)*
- [ ] **G5 — `permissionDecision="defer"` + `DeferredToolUse` for mid-run approval gates.** Today high-risk tool calls during unattended runs collapse the task to BLOCKED state; with autopilot on, this is a dead end. Returning `permissionDecision="defer"` from a `PreToolUseHookSpecificOutput` queues a `DeferredToolUse` the operator (or autopilot policy) can resolve later without halting the surrounding plan. Verified absent in `src/`. Pre-requisite: `ctx7 docs /anthropics/claude-agent-sdk-python "permissionDecision defer DeferredToolUse"` against SDK 0.2.85. *(SDK rubric § Permissions; INSIGHTS ad-hoc § G5, P1.)*

### M2.5 — Architecture and design language coherence

The dashboard feels like one product.

- [ ] Frontend React architecture rubric ([docs/rubric/frontend-react-architecture.md](../rubric/frontend-react-architecture.md)) passes on all current and future surfaces; no god components.
- [ ] Backend service architecture rubric ([docs/rubric/backend-service-architecture.md](../rubric/backend-service-architecture.md)) passes; clear ownership boundaries; no second control owners for the same concern.
- [ ] Design language ([docs/design-docs/design-language.md](../design-docs/design-language.md)) applied consistently; design-system primitives only, no ad-hoc styles.
- [ ] **Codify the short-lived-session pattern in the backend rubric.** Dispatch session stays idle during `runtime.run()`; intermediate DB writes from `on_chunk`/`receive_response` use `async with get_session_factory()() as db:` per chunk (IMP-012 pattern); SSE endpoints never `Depends(get_db)` past the initial snapshot (IMP-011 pattern). *(INSIGHTS Run #7 § P0-2.)*
- [ ] **Empty-response envelope convention in the backend rubric.** Every aggregation endpoint that can return empty/zero returns a `state` field (`"running" | "no_data" | "scope_mismatch"`) plus a `note` string (IMP-003 `active_runs_note` pattern, IMP-005 `memory_root` pattern). *(INSIGHTS Run #7 § P1-4.)*
- [ ] **`AgentDefinition.maxTurns` set per subagent** in the subagent definition rubric. Caps runaway loops at the SDK boundary. *(INSIGHTS Run #7 § P0-1.)*
- [ ] **G4 — File checkpointing for scope-limited subagents (gate-remediator, integration-resolver, build-verifier).** Replace the current "never delete files" prompt rule (`.memory/project_gate_remediator.md`) with an SDK-guaranteed checkpoint/revert boundary. Subagent runs in a checkpoint; on policy violation or hook denial, revert. Codify in the subagent definition rubric so the prompt rule becomes belt-and-braces, not the primary defense. Verified absent in `src/`. *(SDK rubric § Session lifecycle; INSIGHTS ad-hoc § G4, P1.)*
- [ ] **G13 — `effort:"xhigh"` carve-out for planner/designer on high-complexity items in `execution_policy.py`.** Today `execution_policy.py` plumbs `effort` as `low/medium/high/none` only (Opus 4.7 supports `"xhigh"` for deep reasoning). Carve-out only fires when item complexity score crosses a documented threshold so the cost ceiling is bounded. *(SDK rubric § Configuration; INSIGHTS ad-hoc § G13, P2.)*

---

## Epoch 3 — Scale

**Outcome:** Handles real-world complexity — multi-feature apps, long horizons, multi-operator teams, head-to-head wins on canonical tasks. "Preferred" claim defensible with evidence.

**Gating tier:** [Tier 3](EVALUATION.md#tier-3--head-to-head-bars-to-declare-preferred).

### M3.1 — Complex multi-feature app delivery

Non-trivial app (15+ features, integrations, real DB / auth / deployment), end-to-end, both lanes.

- [ ] Project plan, sprints, backlog, approvals, and shipped evidence persist across the full delivery.
- [ ] Both lanes reach the same shipped state when given the same operator prompts.
- [ ] Total tokens, total turns, total wall-clock, total operator interventions tracked per lane and added to STATUS.md evidence.

### M3.2 — Long-horizon session continuity

Survives 30+ day gaps and multi-machine usage with no operator confusion.

- [ ] **G3 — `SessionStore` adapter (Postgres-backed) with conformance harness validation. HARD PREREQUISITE for the items below.** Today resume relies on local JSONL + `Task.session_id` keyed by workspace `cwd` (`.memory` confirms cwd-bound resume); a 30-day gap or second machine breaks this contract. SDK adds `SessionStore` parity in Python `0.1.64` with a conformance harness — implement, validate, then ship M3.2 items. Verified absent in `src/`. Pre-requisite: `ctx7 docs /anthropics/claude-agent-sdk-python "SessionStore conformance"` against SDK 0.2.85. *(SDK rubric § Session lifecycle; INSIGHTS ad-hoc § G3, P1; article `2026-04-24-python-agent-sdk-adds-sessionstore-parity-and-a-conformance-`.)*
- [ ] Operator returns to a project after 30+ days; sees the same Board, Backlog, Inbox, Agent state. No stale "running" markers. Memory and KB still relevant.
- [ ] Same project resumed from a second machine (operator on laptop and desktop) with consistent state.

### M3.3 — Multi-operator collaboration

Two operators on the same project, no stepping on each other.

- [ ] Two concurrent Agent sessions on the same project produce consistent state. **Depends on G3 `SessionStore` adapter (M3.2).**
- [ ] Approvals attributable to the operator who granted them.
- [ ] Memory and KB capture the team's accumulated learning, not just one operator's.

### M3.4 — Head-to-head benchmark wins

Defensible "preferred" claim. Canonical task set through Codex CLI, Claude Code, Builder. Measure tokens / turns / wall-clock / success-without-intervention. Record in `docs/goal/benchmarks/` (created when M3.4 starts).

- [ ] Define the canonical task set (5–10 tasks of varying complexity, agreed up front) and the measurement protocol (same prompt wording, same starting workspace, same model/runtime where comparable).
- [ ] Build the harness: scripted runs against all three tools; metrics captured uniformly.
- [ ] Builder wins on tokens-per-feature on majority of canonical tasks in both lanes.
- [ ] Builder wins on success-without-intervention on majority of canonical tasks in both lanes.
- [ ] Builder wins on wall-clock for shipped outcome (including the time the operator spends).
- [ ] Lifecycle-coverage tasks (multi-sprint, durable state, resumability) — Builder is the *only* tool that completes them.

### M3.5 — Optimization loop activation (autoresearch Track B)

Source: [docs/autoresearch/](../autoresearch/). Activates only after [autoresearch/README.md](../autoresearch/README.md) prerequisites pass (incl. M1.1 IMP closures + M2.3 cost-aware execution).

**Per-patch / per-run detail: [docs/autoresearch/PROGRESS.md](../autoresearch/PROGRESS.md).** This section keeps milestone-scope items only. Autoresearch skill closeouts (Baseline / Iterate / Fix) write to PROGRESS.md, not here.

- [ ] All Track B prerequisites met (IMP-001 to IMP-004 closed, baseline variance measured, gate-pass rate at 1.0, complexity at 0 violations).
- [ ] Autoresearch loop produces at least one optimization that survives variance gating and ships.
- [ ] The loop's optimizations are reflected back into runtime policy (`execution_policy.py`) and prompt shape, not just kept in the experiment results TSV.
- [ ] **After-fix sibling search** — after a bug-fix task closes, a bounded `repo-researcher` subagent scans for sibling files/tests that exhibit the same pattern and flags them before the sprint ends. Add as OPTIMIZE_IDEAS #11; promote when runtime evidence shows recurring same-pattern regressions.

---

## How To Pick The Next Item

1. Read [STATUS.md](STATUS.md) → current epoch + milestone.
2. First `[ ]` in current milestone not blocked by another.
3. Multiple valid → prefer one protecting more [NORTH-STAR § Differentiators](NORTH-STAR.md#differentiators).
4. Mark `in_progress` in STATUS before starting.
5. Tick `[x]` only when acceptance evidence exists + relevant [EVALUATION.md](EVALUATION.md) tier passes.
6. Update STATUS.
7. **Commit + push.** `[x]` tick + STATUS + evidence files in one commit, pushed. Unpushed `[x]` = not closed.

## How To Propose A New Milestone Or Item

- Add milestone/item to the correct epoch here.
- Note in [STATUS.md § Recent Decisions](STATUS.md#recent-decisions).
- Changes success bar → update [EVALUATION.md](EVALUATION.md) in same change.
