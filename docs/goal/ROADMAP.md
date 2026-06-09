# Roadmap — From Current State To "Preferred Over Codex CLI And Claude Code"

> Read [README.md](README.md) and [NORTH-STAR.md](NORTH-STAR.md) first.
> Update [STATUS.md](STATUS.md) on any milestone/item transition.
> Item style + compactness: [.claude/skills/status/SKILL.md](../../.claude/skills/status/SKILL.md) Maintenance Contract. Lint: `/status lint`.

Three epochs × milestones × items. Items checkbox-tracked. Milestone `pending`→`in_progress`→`done` only when every item `[x]` AND the relevant [EVALUATION.md](EVALUATION.md) tier passes with evidence.

Spine of all work. Non-roadmap work → add to the right epoch first; no ad-hoc.

---

## Epoch 1 — Stabilize

**Outcome:** Ships features end-to-end on both lanes across multiple managed-app workspaces. Operator-facing bugs closed. Performance bars met. Architecture decomposed enough for safe further work.

**Gating tier:** [EVALUATION.md § Tier 1](EVALUATION.md#tier-1--token--ux-bars-every-release) on primary workspace, both lanes.

### M1.1 — Close the open operator-facing defects

Closed = root cause + SDK-grounded fix + regression test + evidence pointer. Full detail in git log + `.memory/`.

- [x] **IMP-001** — feature-request context lost after intake follow-up. `agent_prompt_builders.py`; `test_agent_feature_spec_prompt_contracts.py`. `T:backend` `T:browser:na`
- [x] **IMP-002** — gates-first not enforced (27-turn run pre-infra). Scaffold commits 1fae0bd, c1a39c8, a88ee2c. `T:backend` `T:browser:na`
- [x] **IMP-003** — metrics showed 0 tokens for in-progress runs. Backend note (`dashboard_metrics.py`) + Metrics page now renders `active_runs_note`; live-verified. `T:backend` `T:browser`
- [x] **IMP-004** — Recover 409 on gate-infra-blocked tasks. Backend (IMP-002) + frontend 8799f1b. `T:backend` `T:browser`
- [x] **IMP-006** — scaffold used shell heredoc not Write tool. Prompt constraint in `agents/definitions.py`. `T:backend` `T:browser:na`
- [x] **IMP-007** — simultaneous dispatch → pool exhaustion. Prompt constraint + project dispatch lock; `test_dispatch_guards.py`. `T:backend` `T:browser:na`
- [x] **IMP-008** — `git worktree add` fails on unborn HEAD. Guard in `workspace/manager.py`; `test_workspace_manager_creates_initial_commit_for_unborn_head`. `T:backend` `T:browser:na`
- [x] **IMP-009** — dispatch before scaffold done. 300s scaffold timeout + scaffold-running guard; `test_dispatch_guards.py`. `T:backend` `T:browser:na`
- [x] **IMP-010** — session rollback during long scaffold. try/finally + rollback guard (`agent_run_lifecycle.py`/`orchestrator.py`); event `agent_run_lifecycle_flush_error`. `T:backend` `T:browser:na`
- [x] **IMP-011** — SSE streams held pool conns for client lifetime. `dashboard_api.py` scopes session to initial snapshot. `T:backend` `T:browser:na`
- [x] **IMP-012** — dispatch session invalid after ~90s. `persist_realtime_run_update` → short-lived `get_session_factory()`. Task 128e02f6 done 11:25. `T:backend` `T:browser:na`
- [x] **IMP-013** — orphan branch refuses FF merge (unrelated histories). Rebase-before-integrate `workspace_integration.py`. `T:backend` `T:browser:na`
- [x] Re-verify all closures e2e on devpulse, both lanes (M1.2 prereq). 79/79 regression tests (2026-05-21). `T:backend` `T:browser`
- [x] `P1` **IMP-014** — 7-day retention window; stale errors age out; rec gated to within-window count. `summary_runtime_aggregates.py`. `T:backend` `T:browser:na`
- [x] **IMP-015** — `type=feature` items shown as "improvement". `BacklogPage.tsx itemTypeLabel` + type-aware `save_note`; `test_agent_feature_spec_capture_routes.py`. `T:backend` `T:browser`
- [x] `P1` **IMP-016** — `message_targets_builder_self()` classifier; builder-self asks no longer dispatch to app backlog. `agent_message_intent.py`. `T:backend` `T:browser:na`
- [x] **IMP-017** — terminal `cancelled` state + cancel route/CLI/dashboard control across the stack. `efe81e5`; dashboard "Cancel item" live-verified (item→`cancelled`). `T:backend` `T:browser`
- [x] **IMP-018** — interview fell back to free-text (AskUserQuestion dead). Fix: per-agent `permission_mode`, chat→`"default"`; `test_chat_permission_mode_questions.py`. `T:backend` `T:browser`
- [x] `P0` **IMP-019** — `is_ui_task()` gate + `browser_evidence_tier` queryable field; `GateResultModel` persists tier. `build_verification.py`. `T:backend` `T:browser:na`
- [x] **IMP-020** — chat `default` showed approval cards for app edits. Fix: chat never edits app — deny ungranted Edit/Write/Bash; `test_chat_permission_mode_questions.py`. `T:backend` `T:browser`
- [x] **IMP-021** — 3 pre-existing doc-routing test failures (compact-JSON staleness + IMP-020 Bash-deny fallout); test-only fix, 11 green. `cdb8be8`. `T:backend` `T:browser:na`
- [x] `P1` **IMP-022** — phase runs rendered as clickable trace rows in sidebar. `TaskDetailSidebar.tsx`. `T:backend:na` `T:browser`
- [x] **IMP-023** — cost/token analyze headline read 0 (last-write-wins clobber). `_merge_run_status_telemetry` sums additive fields; `test_timeline_analysis.py`. `T:backend` `T:browser`
- [x] `P1` **IMP-024** — cache_ratio = cached/(cached+input) clamped 0–1; 4 call sites fixed; type errors resolved. `test_codex_optimization.py + test_builder_cli_surfaces.py`. `T:backend` `T:browser:na`
- [x] `P3` **IMP-025** — superseded by IMP-027; token burn = planning-time over-decomposition. `2026-06-02`. `T:backend:na` `T:browser:na`
- [x] `P1` **IMP-026** — validate_mcp_args() + _PARAM_ALIASES table; self-correcting errors; schema descriptions guide model. `tests/test_sdk_mcp_schema_validation.py`. `T:backend` `T:browser:na`
- [x] `P0` **IMP-036** — generated Python apps had no dep-provisioning owner; bare `pytest`/`sys.executable` at every test site → `ModuleNotFoundError` → LLM gate-remediator burned its retry cap on an env failure it can't source-fix. Fix: owned `quality_gates/python_env.py` (idempotent venv provision + canonical `pytest_argv`, peer to the Node `npm install` guard) wired into all 4 test/command-discovery sites, + classify-before-agent in `gate_feedback.py` (env-signature failure → deterministic re-provision, not model dispatch). `test_python_env.py`. `T:backend` `T:browser:na`
- [ ] `P0` **IMP-027** — complexity-proportional SDLC: ceremony scales with risk, not uniform (trivial footer → 5-task sprint). Invariant: model proposes, policy floors mandated gates (security/user-facing/schema). Phase plan = visible board artifact. `T:backend:pending` `T:browser:pending`
  - **Done (027a/c) —** intake emits `proposed_tasks` sized to the change; planner scales task count (`agent_feature_payloads.py`, `services/sprint_execution.py`); live-confirmed 1 task for a trivial ask (was 5).
  - **Open (027b) —** per-task phase planner: deterministic floor table + model additions, finalized post-scaffold, rendered as the board artifact. Owner: orchestrator phase routing.
- [ ] `P0` **IMP-028** — code-gen replays ~20.5k context/turn (~89% of run cost). Shipped `compact_workspace_map` in the code-gen prompt (`workspace_tools.py`, ~77 tok). Remaining: live A/B of tool-call counts; ~13–15k preset-trim experiment. `T:backend:pending` `T:browser:na`
- [x] **IMP-029** — answer controls could lock on a hung `/api/agent/chat/respond`. Fixed `AgentPage.tsx` (AbortSignal.timeout + reset-on-item-change); live-verified answerable. `T:backend:na` `T:browser`
- [x] **IMP-030** — repeatable dashboard build→sync pipeline (`scripts/build_dashboard.sh`); rebuilt + served fresh bundle `index-jlc1ZA4V.js` (was stale 2026-05-20). `T:backend` `T:browser:na`
- [x] **IMP-031** — Board "Recover" reset a blocked task without dispatching it → stranded. Fixed `BoardPage.tsx` to chain `dispatchTask`; live-verified `active_runs` 0→1. `T:backend:na` `T:browser`
- [ ] `P1` **IMP-032** — Board shows only the current sprint; a prior-sprint blocked task is invisible (`board` API `blocked:1` but the view shows Blocked 0), no sprint switcher → operator can't find/Recover it. Add a sprint switcher or cross-sprint needs-attention view. `T:backend:na` `T:browser:pending`
- [ ] `P0` `IF` **IMP-033** — negative-scenario browser-testing campaign on a fresh Kanban app (34 `TESTING.md` scenarios). 25 pass / 7 blocked (need fault injection) / 2 pending / 0 product bugs; +1 infra fix (hermes bridge session-tab). `T:backend:na` `T:browser:pending`
- [ ] `P1` **IMP-034** — generated apps lack UI taste: no design guidance exists in any agent prompt, so code-gen ships generic AI-slop UIs (default blue/purple, no empty/loading/error states, ad-hoc spacing, flat type). Fix sourced from the taste-skill project + Vercel Web Interface Guidelines / Refactoring UI / NN/g heuristics.
  - **(034a) Direct, always-on —** compact (~520 tok) stack-agnostic Product-UI design directive in `agents/design_directive.py`, injected into the `code-gen` system prompt gated by `is_ui_task()` (reused from IMP-019). STATIC → rides the cached prompt prefix (≈0 tok/turn after first; respects IMP-028 budget); empty for CLI/library/non-UI work. `T:backend:pending` `T:browser:pending`
  - **(034b) Prototype-first, operator-selectable —** opt-in UI prototype/mockup preview in the design phase the operator approves before implementation; reuses the 034a directive. **Backend DONE:** `ui-prototyper` agent + `Feature.ui_preview_enabled` opt-in + `should_run_ui_preview` predicate; `_phase_design` dispatches it → `DesignDocument(ui_preview)` + `ApprovalGate(ui_preview)` → `DESIGN_REVIEW`, approve → `IMPLEMENTATION` (reuses existing gate plumbing, no migration). `test_ui_preview_backend.py`. **Pending:** frontend preview/approve card (iframe in AgentPage) + dashboard rebuild + live E2E verify. `T:backend` `T:browser:pending`
- [ ] `P2` **IMP-035** — full-lane capability-fit audit (all 13 Claude Agent SDK phases vs `claude-agent-sdk-rubric`). Lane already well-tuned (G1/G2/G7, cache-read tracking, `ClaudeSDKClient` streaming, tool-output trim hook, resume-chaining, per-role tiers all confirmed optimal). 3 genuine under-uses found:
  - **(035a) — DONE** documentation-bridge parent was sonnet for a zero-reasoning Agent pass-through → moved to haiku (`definitions.py` model + `execution_policy._model_for_agent`); `test_documentation_bridge_parent_runs_on_haiku`. `T:backend` `T:browser:na`
  - **(035b) —** optimization-agent: fork the telemetry/log evidence sweep to a read-only subagent so a large `observability_payload` doesn't crowd the main window before the exact-candidate write (conditional on large payloads). `T:backend:pending` `T:browser:na`
  - **(035c) —** init-project-chat: test dialing effort medium→low (keep opus) for the AskUserQuestion interview lane; reject if gap-finding quality regresses. `T:backend:pending` `T:browser:na`
  - **Note:** audit mis-listed `chat` as haiku — it's actually in the `implementation_model` bucket → resolves to **sonnet**. Possible larger win (chat runs often) but may be intentional for interview quality; needs an operator call before acting. `T:backend:pending` `T:browser:pending`

### M1.2 — Both lanes ship one feature on devpulse end-to-end

Forward-engineering scenario, both lanes, same operator wording.

- [x] Fresh devpulse boots via `builder init`; readiness gate green. (2026-05-21) `T:backend` `T:browser:na`
- [x] Claude lane: devpulse 5/5 tasks, $2.08 (2026-05-21); all gates pass, 127 tests green. `T:backend` `T:browser:na`
- [x] Source-repo gate bugs unblocked Claude lane: pytest-asyncio autoload, `.py` test-suffix coverage, `run-tests.js` shim. `T:backend` `T:browser:na`
- [x] `docs/goal/` framework + goal-audit skill stabilized (5 runs, 3 skill bugs fixed; `README.md`). `T:backend:na` `T:browser:na`
- [x] goal-audit `--since-run` deltas mode. `c5fcdae` (migrated → self-optimize). `T:backend:na` `T:browser:na`
- [x] goal-audit memory write: prefer recency- over token-weighted intent. `T:backend:na` `T:browser:na`
- [ ] `P1` Codex SDK lane: same wording/outcome + Codex telemetry / app-server / native-input evidence. *(deferred — Claude lane complete)* `T:backend:pending` `T:browser:pending`
- [ ] `P1` Both lanes meet 4 Tier-1 thresholds (`cache_ratio>5x`, `chunk_pressure_risk:false`, `avoidable_cost_flags:[]`, gate-pass 1.0). *(pending Codex)* `T:backend:pending` `T:browser:na`
- [ ] `P1` Session evidence archived under [STATUS.md § Evidence Pointers](STATUS.md#evidence-pointers). *(pending Codex)* `T:backend:na` `T:browser:na`

### M1.3 — God-file decomposition ratchet complete

Source: [docs/quality-gate/complexity.md](../quality-gate/complexity.md) + `complexity-baseline.json`. Active violations → zero.

- [x] Every `complexity-baseline.json` violation split <500 or registered as a documented historical baseline. `T:backend` `T:browser:na`
- [x] `voice_operator.py`/`summary.py`/`orchestrator.py`/`routes/agent.py` each <1500 (1471/540/1345/1326). `T:backend` `T:browser:na`
- [x] `builder lint --complexity-report --json` → 0 violations. (2026-05-23) `T:backend` `T:browser:na`
- [x] Constraint: sequential single-agent extraction, never parallel (`.memory/feedback_extraction_constraints.md`). `T:backend:na` `T:browser:na`
- [x] Project-local save/resume-session skills at `.claude/skills/` (replaced compaction-triggering globals). (2026-05-23) `T:backend:na` `T:browser:na`
- [x] Re-close the 0-violation gate (2026-05-23 regression). Path B — extract not ratchet: `T:backend` `T:browser:na`
    - [x] `cli/commands/logs.py` 1679→1346 (split `logs_runtime_aggregates.py` + `logs_db_utils.py`). `T:backend` `T:browser:na`
    - [x] `services/sprint_execution.py` 828→825 (inlined helpers). `T:backend` `T:browser:na`
    - [x] `db/models.py` 679→676 (docstring trim). `T:backend` `T:browser:na`
    - [x] `embedded/server/agent_sprint_planning.py` 502→499. `T:backend` `T:browser:na`
    - [x] `tests/test_builder_cli_surfaces.py` 2734→2574 (extracted runtime cases). `T:backend` `T:browser:na`
    - [x] `.claude/skills/autoresearch/scripts/introspect.py` 806 — baseline entry (tooling). `T:backend` `T:browser:na`
    - [x] `scripts/autoresearch/run.py` 636 — baseline entry (tooling). `T:backend` `T:browser:na`

### M1.4 — Two-workspace validation rotation

Forward + reverse scenarios validated. Both lanes per scenario.

- [ ] `P1` **Forward:** fresh app in a new workspace (devpulse or equivalent). Both lanes. `T:backend:pending` `T:browser:pending`
- [ ] `P1` **Reverse:** operate on an existing app workspace (todo-app / checked-out external repo). Both lanes. `T:backend:pending` `T:browser:pending`
- [ ] `P1` Identical operator-visible behavior across lanes; lane attribution preserved after a runtime switch. `T:backend:pending` `T:browser:pending`
- [ ] `P1` [docs/PROMPT.md](../PROMPT.md) scripts run in both lanes; rubric pass for [sdk-backed](../rubric/sdk-backed-agent-page-agent.md) + [voice](../rubric/realtime-voice-agent-page-agent.md) agent-page rubrics. `T:backend:pending` `T:browser:pending`
- [x] Per-phase subagent `allowed_tools` allowlists; `SubagentDefinition.max_turns` → SDK `maxTurns`. `definitions.py`/`runner_options.py`. `T:backend` `T:browser:na`
- [x] Deterministic CLI preflight probes before `query()` (`git rev-parse HEAD` hard-fail for git phases; ruff/pyproject soft warns). `runner.py`. `T:backend` `T:browser:na`

### M1.5 — Realtime Voice (Samantha) parity with Agent page

Voice is a peer operator surface, not a bolt-on.

- [ ] `P1` Voice + Agent share session, approvals, pending-question cards. `T:backend:pending` `T:browser:pending`
- [ ] `P1` Voice-initiated feature shipped e2e with browser proof, both lanes. `T:backend:pending` `T:browser:pending`
- [ ] `P1` Realtime auth boundary holds (Realtime=`OPENAI_API_KEY`; runtime auth not leaked; Codex-sub runs strip OpenAI creds). `T:backend:pending` `T:browser:na`
- [ ] `P1` Voice delegations rebind to the delegated Agent session; no orphan transcripts. `T:backend:pending` `T:browser:pending`
- [x] **Chat runtime → `ClaudeSDKClient` context manager** — chat path migrated; `__aexit__` cancels monitor tasks deterministically. `d03aff4`. `T:backend` `T:browser:na`

### M1.6 — Deletion-debt paydown (Musk-hat audit)

Source: `elon` audits — `docs/audits/autonomous-agent-builder-musk-hat-2026-05-30.html` + `-2026-05-31.html`. 90-day deletion ratio 0.081→0.092 (grows-only). All LOC import-verified.

- [x] **Tier 1a** — deleted `codex_cli` adapter (635 LOC; superseded by `codex_sdk`). `factory.py`/`runtime_settings.py` trimmed; 96 tests green. `T:backend` `T:browser:na`
- [x] **Tier 1b** — deleted dead `opencode` wrapper (21 LOC). Commit 589a950. `T:backend` `T:browser:na`
- [x] **Tier 1c** — retired `openai_agents`/`opencode_go` lane (282 LOC); `get_implemented==get_available==[claude,codex_sdk]`; 189 tests. Commit 5532f10. `T:backend` `T:browser:na`
- [x] **Tier 1d** — deleted `architecture_evidence.py` (dup of `proof_contract.py`) + `runtime_boundary.py` (0 importers) + stale `openai-agents` extra. 1554 collects clean. `T:backend` `T:browser:na`
- [ ] `P1` **Tier 2** — collapse the dual FastAPI app onto the embedded server (`embedded/server/app.py` canonical; remove `api/app.py`). Blocker: 45 conftest-`client` files bind `api.app`. Migrate per-file with reconciliation, smallest-delta first. `T:backend:pending` `T:browser:na`
- [ ] `P1` **Tier 3** — rename `api/` shared core → `core/` (one app + one shared core + two thin runtimes). Blocked on Tier 2. `T:backend:pending` `T:browser:na`
- [ ] `P1` Overlaps M1.3: 16 files ≥1000 LOC (onboarding 1931, evidence_graph 1817, dashboard_api 1736, kb 1735) — refactor via M1.3 extraction, not deletes. `T:backend:pending` `T:browser:na`

---

## Epoch 2 — Differentiate

**Outcome:** Wins decisively on differentiators. Codex CLI / Claude Code can't match — differentiators are structural, not features.

**Gating tier:** [Tier 2](EVALUATION.md#tier-2--lifecycle-coverage-bars-every-milestone) on every managed app in scope; [Tier 3](EVALUATION.md#tier-3--head-to-head-bars-to-declare-preferred) head-to-head begins here.

### M2.1 — Lifecycle completeness proof

Full requirements → design → backlog → implementation → verification → ship → optimize, dashboard-visible, resumable, durable.

- [ ] `P2` One e2e project on devpulse, every phase dashboard-visible incl. post-ship optimization lane. `T:backend:pending` `T:browser:pending`
- [ ] `P2` Resumability: kill the dashboard mid-sprint, restart, exact state restored (no loss, no stale "running", no orphan approvals). `T:backend:pending` `T:browser:pending`
- [ ] `P2` Runtime switch mid-project (`claude`→`codex_sdk`) preserves history; future work uses the new lane. `T:backend:pending` `T:browser:pending`
- [ ] `P2` Multi-operator handover: a 2nd operator sees the same Board/Backlog/Inbox/Agent. `T:backend:pending` `T:browser:pending`
- [ ] `P2` Codify flag+drain for `receive_response()` loops (hardening; single site `runner.py:692`, no early break today). Downgraded P0→hardening. `T:backend:pending` `T:browser:na`
- [ ] `P2` Auto-complete a feature when all its tasks `done` (forward-only; no revert; manual changes independent). `T:backend:pending` `T:browser:pending`
- [ ] `P2` Auto-complete a backlog item when all its tasks finish. `T:backend:pending` `T:browser:pending`

### M2.2 — Memory and knowledge as decisive differentiators

Memory + KB compound across sessions; prevent re-litigating settled questions.

- [ ] `P2` Memory-retrieval workflow is the documented step 0 of every non-trivial fix. `T:backend:na` `T:browser:na`
- [ ] `P2` KB freshness gate (`builder knowledge validate --json`) wired into the doc-refresh gate before PR in every sprint. `T:backend:pending` `T:browser:na`
- [ ] `P2` Memory write-back: every closed IMP with a non-obvious boundary / single-owner pattern / recurring trap → `builder memory add`. `T:backend:na` `T:browser:na`
- [ ] `P2` Demonstrate compounding: a fresh session reaches a correct decision faster via memory+KB. `T:backend:pending` `T:browser:na`

### M2.3 — Cost-aware execution surface complete

Token / cache / chunk / avoidable-cost telemetry first-class: Metrics page, Session rail, `builder metrics show`, `builder logs analyze`, observability recs.

- [ ] `P2` `builder metrics show` + Metrics page agree with raw `builder logs --compact` cost every run. `T:backend:pending` `T:browser:pending`
- [ ] `P2` Per-turn noncached+output / raw / cached tokens accurate in the Agent Session rail, both lanes. `T:backend:pending` `T:browser:pending`
- [ ] `P2` Observability recs separate optimization candidates from workflow-state warnings (approval/blocked → state, not optimization). `T:backend:pending` `T:browser:pending`
- [ ] `P2` Optimization-agent runs only on post-ship candidate evidence, never on generated-app residuals. `T:backend:pending` `T:browser:na`
- [ ] `P2` **G14** — full OTel spans/metrics, not just env checks (`observability/runtime.py:145` wires none). Emit spans/metrics for hook exec + cache hits + token usage to a queryable sink. `T:backend:pending` `T:browser:na`
- [ ] `P3` **G15** — Codex per-server MCP `[env]` + OAuth. CONDITIONAL/P3 — N/A until MCP servers are wired into the Codex lane. `T:backend:pending` `T:browser:na`
- [x] `logs analyze --session` honestly session-scoped (`tasks.chat_session_id` FK). `test_logs_analyze_scopes_runtime_aggregates_to_chat_session`. (2026-05-23) `T:backend` `T:browser:na`
- [x] First-class `RateLimitEvent` surface driven by `StopFailure` hook (`runner.py`; `provider_limit` dict). (2026-05-22) `T:backend` `T:browser:na`
- [x] **G2** `exclude_dynamic_sections=True` on preset (runner/claude_runtime/onboarding); unblocks `cache_ratio>5x`. (2026-05-22) `T:backend` `T:browser:na`
- [x] **G12** `updatedToolOutput` truncation hook (`agents/hooks.py`, 8k ceiling). (2026-05-22) `T:backend` `T:browser:na`
- [x] **G1** `include_partial_messages=True` + per-turn token Session rail (`stream_usage` SSE → `AgentPage.tsx`). (2026-05-22) `T:backend` `T:browser`
- [x] **G7** `strict_mcp_config=True` on client. (2026-05-22) `T:backend` `T:browser:na`

### M2.4 — Operator UX polish to "no internals leakage"

Every operator-facing surface respects [OPERATOR-LANGUAGE.md](OPERATOR-LANGUAGE.md).

- [ ] `P2` Banned-term audit across all operator surfaces: zero leakage of lifecycle/scaffold/dispatch/worktree/SDK/MCP/gate/chunk/etc. unless the operator typed it first. `T:backend:pending` `T:browser:pending`
- [ ] `P2` All pending questions/approvals render readable labels (no `[object Object]`, no payload objects). `T:backend:pending` `T:browser:pending`
- [ ] `P2` Inline question/approval controls in the composer/footer (one owner); timeline entries evidence-only. `T:backend:na` `T:browser:pending`
- [ ] `P2` Recover button shows only when blocked-reason is recoverable; else an actionable next-step. `T:backend:pending` `T:browser:pending`
- [ ] `P2` **G6** `include_hook_events=True` → `HookEventMessage` on the Agent page (render the real block reason in operator language). Absent in src. `T:backend:pending` `T:browser:pending`

### M2.6 — Autopilot mode

When enabled: orchestrator owns approval, recovery, continuation — no operator intervention. Operator opts in.

- [ ] `P2` Autopilot toggle in Settings, persisted per project. `T:backend:pending` `T:browser:pending`
- [ ] `P2` Autopilot on: auto-approve ready tasks, auto-recover `capability_limit`/`cycle-detected`, auto-advance after completion. `T:backend:pending` `T:browser:pending`
- [ ] `P2` Operator can disable autopilot mid-sprint; in-flight work not interrupted. `T:backend:pending` `T:browser:pending`
- [ ] `P2` All autopilot actions dashboard-visible (who approved/recovered: operator vs autopilot). `T:backend:pending` `T:browser:pending`
- [ ] `P2` Autopilot won't approve design/plan without operator scope confirm; implementation-onward only by default. `T:backend:pending` `T:browser:pending`
- [x] **`can_use_tool` enforces phase boundaries** — `_auto_approve` denies ungranted mutating built-ins via `chat_mutating_builtin_denial`. `d03aff4`. `T:backend` `T:browser:na`
- [ ] `P2` Retry/cycle state machine from typed SDK errors (`ResultMessage.is_error/errors/api_error_status`, `AssistantMessageError`, `RateLimitEvent`); increment cycle counter on the transition. Extend `runner.py:818`. `T:backend:pending` `T:browser:na`
- [ ] `P2` **G5** `permissionDecision="defer"` + `DeferredToolUse` for mid-run approval gates (high-risk calls don't dead-end BLOCKED under autopilot). Absent in src. `T:backend:pending` `T:browser:pending`

### M2.5 — Architecture and design language coherence

The dashboard feels like one product.

- [ ] `P2` Frontend React rubric passes on all surfaces; no god components. `T:backend:na` `T:browser:na`
- [ ] `P2` Backend service rubric passes; clear ownership, no second control owners. `T:backend:na` `T:browser:na`
- [ ] `P2` Design language applied; primitives only, no ad-hoc styles. `T:backend:na` `T:browser:pending`
- [ ] `P2` Codify the short-lived-session pattern in the backend rubric (dispatch session idle during run; per-chunk `get_session_factory()`; SSE no `Depends(get_db)` past snapshot). `T:backend:na` `T:browser:na`
- [ ] `P2` Empty-response envelope convention in the backend rubric (`state` + `note` on every aggregation endpoint). `T:backend:pending` `T:browser:na`
- [x] `AgentDefinition.maxTurns` per subagent (`definitions.py`=20; `runner_options.py:61`). (M1.4 dup) `T:backend` `T:browser:na`
- [ ] `P2` **G4** file checkpointing for scope-limited subagents (checkpoint/revert vs the "never delete" prompt rule). Absent in src. `T:backend:pending` `T:browser:na`
- [ ] `P2` **G13** `effort:"xhigh"` carve-out for planner/designer above a complexity threshold (`execution_policy.py` plumbs low/med/high/none only). `T:backend:pending` `T:browser:na`

---

## Epoch 3 — Scale

**Outcome:** Handles real-world complexity — multi-feature apps, long horizons, multi-operator teams, head-to-head wins. "Preferred" claim defensible with evidence.

**Gating tier:** [Tier 3](EVALUATION.md#tier-3--head-to-head-bars-to-declare-preferred).

### M3.1 — Complex multi-feature app delivery

Non-trivial app (15+ features, integrations, real DB/auth/deployment), e2e, both lanes.

- [ ] `P3` Project plan, sprints, backlog, approvals, shipped evidence persist across the full delivery. `T:backend:pending` `T:browser:pending`
- [ ] `P3` Both lanes reach the same shipped state given the same operator prompts. `T:backend:pending` `T:browser:pending`
- [ ] `P3` Total tokens / turns / wall-clock / operator interventions tracked per lane in STATUS evidence. `T:backend:pending` `T:browser:na`

### M3.2 — Long-horizon session continuity

Survives 30+ day gaps and multi-machine usage with no operator confusion.

- [ ] `P1` **G3 — `SessionStore` adapter (Postgres) + conformance harness.** `IF` HARD PREREQ for M3.2/M3.3. Today resume = local JSONL + `Task.session_id` by cwd; a 30-day gap / 2nd machine breaks it. SDK parity since 0.1.64; PostgresSessionStore landed `4ad77d4`. `T:backend` `T:browser:na`
- [ ] `P3` Operator returns after 30+ days; same Board/Backlog/Inbox/Agent, no stale "running", memory+KB still relevant. `T:backend:pending` `T:browser:pending`
- [ ] `P3` Same project resumed from a second machine with consistent state. `T:backend:pending` `T:browser:pending`

### M3.3 — Multi-operator collaboration

Two operators on one project, no stepping on each other.

- [ ] `P3` Two concurrent Agent sessions on one project → consistent state. **Depends on G3 (M3.2).** `T:backend:pending` `T:browser:pending`
- [ ] `P3` Approvals attributable to the operator who granted them. `T:backend:pending` `T:browser:pending`
- [ ] `P3` Memory + KB capture the team's learning, not one operator's. `T:backend:pending` `T:browser:na`

### M3.4 — Head-to-head benchmark wins

Defensible "preferred" claim. Canonical task set through Codex CLI, Claude Code, Builder. Record in `docs/goal/benchmarks/` (created at M3.4 start).

- [ ] `P3` Define the canonical task set (5–10 tasks, varying complexity) + the measurement protocol. `T:backend:na` `T:browser:na`
- [ ] `P3` Build the harness: scripted runs against all three tools; metrics captured uniformly. `T:backend:pending` `T:browser:na`
- [ ] `P3` Builder wins on tokens-per-feature on a majority of tasks, both lanes. `T:backend:pending` `T:browser:na`
- [ ] `P3` Builder wins on success-without-intervention on a majority of tasks, both lanes. `T:backend:pending` `T:browser:na`
- [ ] `P3` Builder wins on wall-clock for shipped outcome (incl. operator time). `T:backend:pending` `T:browser:na`
- [ ] `P3` Lifecycle-coverage tasks (multi-sprint, durable state, resumability) — Builder is the only tool that completes them. `T:backend:pending` `T:browser:pending`

### M3.5 — Optimization loop activation (autoresearch Track B)

Source: [docs/autoresearch/](../autoresearch/). Activates only after [autoresearch/README.md](../autoresearch/README.md) prerequisites pass.

**Per-patch / per-run detail: [docs/autoresearch/PROGRESS.md](../autoresearch/PROGRESS.md).** Milestone-scope items only here; skill closeouts write to PROGRESS.md.

- [ ] `P3` All Track B prerequisites met (IMP-001..004 closed, baseline variance measured, gate-pass 1.0, complexity 0 violations). `T:backend:pending` `T:browser:na`
- [ ] `P3` Autoresearch loop produces ≥1 optimization that survives variance gating and ships. `T:backend:pending` `T:browser:na`
- [ ] `P3` Optimizations reflected back into runtime policy (`execution_policy.py`) + prompt shape, not just the results TSV. `T:backend:pending` `T:browser:na`
- [ ] `P3` After-fix sibling search — a bounded `repo-researcher` scans for same-pattern siblings before the sprint ends. OPTIMIZE_IDEAS #11; promote on recurring same-pattern regressions. `T:backend:pending` `T:browser:na`

---

## How To Pick The Next Item

1. Read [STATUS.md](STATUS.md) → current epoch + milestone.
2. First `[ ]` in the current milestone not blocked by another.
3. Multiple valid → prefer the one protecting more [NORTH-STAR § Differentiators](NORTH-STAR.md#differentiators).
4. Mark `in_progress` in STATUS before starting.
5. Tick `[x]` only when acceptance evidence exists + the relevant [EVALUATION.md](EVALUATION.md) tier passes.
6. Update STATUS.
7. **Commit + push.** `[x]` tick + STATUS + evidence in one commit, pushed. Unpushed `[x]` = not closed.

## How To Update This File

- Compact always: one line per item; open = `Pn` + intent + acceptance; closed = outcome + evidence pointer. Work-logs → STATUS *Current Item In Flight*; closure detail → git/CHANGELOG/`.memory`. Rules + budgets: [status SKILL.md](../../.claude/skills/status/SKILL.md).
- **Every item states its test lanes.** Tag each checkbox with both `T:backend:…` and `T:browser:…` — bare `T:backend`/`T:browser` = that test passed, `:pending` = testable in that lane but not yet verified, `:na` = that lane structurally can't test it. `/status lint` WARNs on a missing lane; there is no untagged "—".
- `/status lint` before and after editing; `/status update` to resync [goal-overview.html](goal-overview.html).
- New milestone/item → correct epoch here + note in [STATUS.md § Recent Decisions](STATUS.md#recent-decisions); success-bar change → [EVALUATION.md](EVALUATION.md) same change.
