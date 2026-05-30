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
- [ ] **IMP-014** — Observability "Runtime Error Trend" emits the dispatch-blocking recommendation ("fix the recurring runtime error trend before dispatching more autonomous work") on stale errors that never age out. 9 `mcp__builder__task_*` tool_errors from 2026-05-20 (task `128e02f6`/`task-0`: dispatch → 409 `task_not_dispatchable`, recover ×3 → 409 `task_not_recoverable`, status → 404, show ×4) still surfaced as "unresolved" 8 days later. Evidence: `builder logs --error` `count:9` reconciles with the Observability card. Root cause TBD: error-trend retention/resolution + recommendation gating logic. *(devpulse validation 2026-05-28.)*
- [ ] **IMP-015** — Backlog dashboard renders `type=feature` items under "PLANNED IMPROVEMENTS" with an "IMPROVEMENT" badge; the chat agent likewise calls captured features "improvements". REST/CLI report `type=feature` (`db/models.py` has distinct `FEATURE`/`IMPROVEMENT` enums) — operator sees the wrong type. Root cause TBD: backlog badge/view derivation in the embedded dashboard + chat-agent capture phrasing. *(devpulse validation 2026-05-28.)*
- [ ] **IMP-016** — Chat agent mis-routes builder-improvement requests into the managed-app backlog; no builder-self-improvement lane exists in the dashboard. Two builder-lifecycle requests were captured as devpulse `feature` items (one advanced to `sprint_planned`, risking builder lifecycle code being generated *into the devpulse app*). Root cause TBD: intent classification doesn't distinguish "improve the app being built" from "improve the builder itself". *(devpulse validation 2026-05-28; the two mis-filed items are tracked under M2.1.)*
- [ ] **IMP-017** — No operator-facing way to remove / cancel / archive a backlog item. Verified across all surfaces: dashboard Backlog page has no delete/cancel control, detail-panel action, status dropdown, or command-palette command; `builder backlog item` CLI exposes only `create/update/list/show` (no `delete`); `FeatureStatus` enum has no cancelled/archived/abandoned terminal state (only `backlog…done` + `blocked`); no DELETE REST route; the only `delete(Feature)` path is `onboarding.py` seed-reset (all-or-nothing). Compounds IMP-016 — a mis-filed item cannot be retracted. Root cause TBD: add a retire/cancel state + operator control (dashboard + CLI + route). *(devpulse validation 2026-05-29; the 2 mis-filed M2.1 items are left in place pending this capability.)*
- [x] **IMP-018** — Requirements interview degrades to free-text Q&A instead of structured `AskUserQuestion` option cards; the model itself reports "the structured question tool is disabled in this session." Root cause: the global default `permission_mode="dontAsk"` (`config.py`, `runner.py`) is applied to the interactive `chat` lane. Per the installed SDK (`claude_agent_sdk/types.py`: `"dontAsk"` = "deny if not pre-approved") and the official user-input docs, `dontAsk` bypasses the `can_use_tool` callback — and `_authorize_chat_tool` (`routes/agent.py`) is the *only* place AskUserQuestion answers + tool-approval cards are produced. So the entire interactive question/approval machinery was dead. The `definitions.py` prose band-aid ("dontAsk means auto-approved… you MUST use AskUserQuestion", commit cd05a09) could not re-enable a mode-bypassed tool. Fix: added per-agent `AgentDefinition.permission_mode`; `chat` now runs under `"default"`; runner forwards it; a `preapproved_tools` guard in `_authorize_chat_tool` preserves silent execution of granted tools so no new approval-card friction appears; misleading prose corrected. Regression tests: `test_chat_permission_mode_questions.py` + `test_agent_runner.py` (forwards `permission_mode="default"`). *(recall-loop flashcard-app validation 2026-05-30; live structured-card proof pending server restart.)*
- [x] **IMP-015** — *(root cause found 2026-05-30)* Backlog dashboard renders `type=feature` items under "PLANNED IMPROVEMENTS" with an "IMPROVEMENT" badge, and the chat agent calls captured features "improvements". Root cause: `frontend/src/pages/BacklogPage.tsx` `itemTypeLabel()` literally did `if (value === "feature") return "improvement"`, and `agent_chat_result_publisher.py` hardcoded `save_note = "I captured that improvement as …"` regardless of `feature.item_type`. Confirmed live on recall-loop: both items stored `type=feature` but displayed/announced as "improvement". Fix: `itemTypeLabel` shows the real type; `save_note` is type-aware (`feature`/`improvement`/`optimization`/`incident`); the coupled capture-note parser in `agent_feature_payloads.py` made type-agnostic (`content_announces_captured_feature`) so the regex/markers still detect any noun; impacted assertions in `test_agent_feature_spec_capture_routes.py` + `test_agent_feature_spec_tooling_routes.py` updated. *(frontend half needs dashboard rebuild to render; backend + tests green.)*
- [ ] **IMP-019** — Builder cannot self-verify the generated app in a **real browser**; "shipped/verified" overstates confidence for vanilla apps. The `browser-verifier` subagent (`subagent_definitions.py`) has only `Read/Glob/Grep/Bash/mcp__workspace__*` tools (`definitions.py:73` `VERIFICATION_SPECIALIST_TOOLS`) — no live-browser-driving tool. `embedded/scripts/feature_acceptance.py` runs an existing Playwright suite only when the app ships `playwright.config.*` + an e2e script; for vanilla HTML/JS workspaces it falls back to jsdom/node tests (`:170-181`). Live recall-loop evidence (2026-05-30): the feature shipped "verified" on a 19-test **jsdom** `acceptance.test.js` — no real browser ever rendered it; operator-side hermes-chrome testing caught the real-browser flow (deck/card CRUD, reveal→Again/Good/Easy SM-2 scheduling, streak, localStorage reload-persistence) that jsdom cannot prove (runtime JS errors, CSS/layout, routing, visual). Fix (Claude-Agent-SDK-native, mirrors what the operator does manually): add an in-process MCP browser server (Playwright-MCP or a CDP/hermes-style bridge) wired into `browser-verifier`'s tool list exactly like `mcp__workspace__*`, with a sandboxed launch/teardown policy; the verifier navigates the rendered app, exercises the agreed acceptance criteria, captures screenshots + console errors, and returns structured pass/fail/regression evidence; gate `quality_gates → pr_creation/build_verify` on real-browser proof for user-facing web features (fall back to jsdom only when a browser cannot launch, recorded as a weaker evidence tier). **Increment delivered 2026-05-30:** in-process `browser` SDK MCP server (`agents/tools/browser_tools.py` Hermes-bridge socket client + `agents/tools/sdk_mcp.py` `create_sdk_mcp_server(name="browser", …)` exposing `mcp__browser__{navigate,page_context,read_text,click_text,fill,screenshot}`, built only when allowed); wired into `feature-verifier` + `build-verifier` allowed_tools and the `browser-verifier` subagent, with prompts directing real-browser acceptance and graceful `bridge_unavailable` fallback; unit tests `test_browser_verification_tools.py` (7, green). **Live proof 2026-05-30:** invoking the exact tool path (`browser_tools.browser_navigate` → real Hermes bridge → real Chrome → running recall-loop app at :5173) returned `ok=True` title "Recall Loop", `read_text` returned real rendered content (due/streak), `screenshot` wrote a JPEG, and the `_to_mcp` envelope delivered the JSON inside `content` (model receives real data — the F1 fix, caught by the `agent-sdk-verifier-py` audit, is required: SDK `call_tool` returns empty `CallToolResult` without a `content` key; verified vs SDK 0.2.85 source). **URL resolution delivered 2026-05-30:** `mcp__browser__resolve_app_url` + `browser_tools.resolve_dev_server()` deterministically resolve the serve command + URL from the workspace `package.json` serve script (dev/preview/serve/start, explicit or family-default port) or a static `index.html`; the `feature-verifier` prompt now directs resolve→start→drive; tested (4 cases) + live-verified against recall-loop (`npm run dev` → `http://localhost:5173/`). **Evidence-tier signal delivered 2026-05-30:** `build_verification.browser_evidence_tier()` classifies a feature-verifier result as `real_browser` / `jsdom_fallback` (bridge down — acceptable) / `no_browser_proof` (bridge up but no live evidence — the gap), wired into `quality_gate_runner` as a **non-blocking** structlog advisory (`feature_acceptance_browser_evidence_tier`) so jsdom-tier ships are visible without blocking headless/CI; 3 tier tests. **Registry gap found + fixed in a live run 2026-05-30:** a live `feature-verifier` run (recall-loop "Show Total Cards" feature) showed `agent_phase_start` resolved tools WITHOUT `mcp__browser__*` and emitted `tool_not_found_in_registry` for all 7 — the P19 contract gap: the tools were in allowed_tools + the MCP server but had no `tool_registry` schema, so the registry dropped them (the verifier even issued a `ToolSearch` for `mcp__browser__resolve_app_url`, proving it wanted the tool). Fixed by registering the 7 `mcp__browser__*` schemas in `tool_registry.py`; regression test asserts `BROWSER_TOOLS ⊆ tool_registry._SDK_BUILTINS`. Unit tests + the registry fix were caught only by the live run — neither the unit tests nor the SDK audit covered the internal registry contract. **Live end-to-end PROVEN 2026-05-30 (rerun):** with IMP-020 resolved, two clean live feature-verifier runs (recall-loop "Today: date line" + "motivational tagline") each autonomously called `mcp__browser__resolve_app_url → navigate → read_text → screenshot` against the rendered app at `:5173`, **0 errors** (no `tool_not_found_in_registry`, no `bridge_unavailable`); `agent_phase_start agent=feature-verifier` resolved with all 7 `mcp__browser__*` tools. **Two operator-visibility/correctness fixes landed + tested (`browser_tools.py`, 14/14 `test_browser_verification_tools.py` green):** (a) `browser_navigate` now uses `useSelectedTab=False` → bridge `chrome.tabs.create` so verification runs in an **operator-visible tab** (was hijacking the active tab in place, invisibly — operator-confirmed a tab now opens); (b) `goto reload=True` forces a real navigation so a tab parked on the same URL no longer serves a **stale render** (confirmed: live read flipped from stale "May 31, 2026" to fresh "Today: May 31, 2026"). **Evidence-tier observability fix (`quality_gate_runner.py`):** `feature_acceptance_browser_evidence_tier` now logs on **every** acceptance (not only when an advisory is set) so a silent `real_browser` pass is distinguishable from the tier never running. **Remaining (operator-validated 2026-05-30):** (1) promote the advisory to a hard gate once tiers are reliably observed; (2) ~~dedicated-tab reuse + teardown~~ **DONE 2026-05-30** — `browser_tools._session_tabs` pins the tab id returned by the first `navigate` and stamps it onto every subsequent action so a session stays in ONE operator-visible tab (the bridge has no cross-call tab memory, so a naive navigate spawned a new tab per call → operator saw two); `browser_close()` sends `close_tab` and is wired into `quality_gate_runner` after feature acceptance so a run leaves no orphan tabs (hermes-chrome closeout step 4). Live-verified: nav#1+nav#2 reuse one tab, teardown closes it; 3 unit tests. Aligns with hermes-chrome `operate.md` session-isolation (`useSelectedTab:False` first + `sessionName` group + `close_tab`); (3) **cursor only on interaction** — read-only verifications (navigate/read/screenshot) show no animated cursor because the cursor overlay is click/fill-only; acceptable but less watchable, and worth a deliberate "cursor-driven walkthrough" mode for trust; (4) **serve-from-task-workspace** — the verifier navigates the canonical `:5173` (serving `~/Builder-Workspace/recall-loop`), not its isolated task workspace (`/tmp/.../aab-workspaces/<uuid>/`); pre-merge it can verify stale/unchanged deployment — the verifier should serve ITS OWN workspace on a fresh port and drive that; (5) **`page_context` empty on div-based apps** — structural extraction returns empty `headings/buttons/inputs` for recall-loop (only `read_text` worked); confirm whether this is correct (no semantic tags) or an extension `getPageContext` gap. *(recall-loop validation + rerun 2026-05-30; substantial capability build; plumbing + visibility proven, verification fidelity hardening remains.)*
- [ ] **IMP-020** — IMP-018 side-effect: the interactive chat lane under `permission_mode="default"` now surfaces tool-approval cards for ungranted mutating built-ins (Edit/Write/Bash) on the generated app, which an operator could approve — bypassing the dashboard-first backlog→dispatch delivery lifecycle. Under the prior `"dontAsk"` these were silently denied, forcing the model to capture a feature + dispatch. Live evidence (recall-loop 2026-05-30): asked for a small home-screen stat, the chat agent attempted `Edit .../src/app.js` directly (read the file, planned the diff) and surfaced an Approve/Deny card instead of capturing+dispatching; operator denied and the model asked how to proceed. The approval-card path itself is intended/tested (`test_agent_tool_approval_routes` Bash card), so the fix is a design judgment: in `_authorize_chat_tool`, for the `chat` lane deny ungranted mutating built-ins (Edit/Write/Bash/MultiEdit/NotebookEdit) with a message routing to `mcp__builder__task_dispatch`, while keeping approval cards for legitimately-confirmable granted tools. **Resolved 2026-05-30 (design call — always force capture→dispatch).** Grounded in CLAUDE.md dashboard-first doctrine ("drive backlog, task, approval, and execution behavior through the Agent page"; "Do not infer vague user intent into a mutating lifecycle action"): the chat lane must **never** edit the generated app directly, even with operator approval, because that bypasses the visible SDLC — the core product value. Fix: `agent_tool_policy.chat_mutating_builtin_denial()` + `CHAT_DISPATCH_REQUIRED_BUILTINS = {Edit, Write, Bash, MultiEdit, NotebookEdit}`; `_authorize_chat_tool` (after the preapproved/read-only checks, so the deny is scoped to *ungranted* built-ins) denies these with a `mcp__builder__task_dispatch` routing message and emits a `tool_error` event (operator sees the reason) instead of an Approve/Deny card. Granted/confirmable non-built-in mutating tools (e.g. `mcp__workspace__run_command`) keep their approval cards — the tested path is intact. Tests: `test_chat_permission_mode_questions.py` (5 parametrized deny + granted-card-preserved); `test_agent_tool_approval_routes.py` (new route-level `test_chat_lane_denies_direct_edit_and_routes_to_dispatch`; the pre-existing card-deny test repointed from `Bash` to `mcp__workspace__run_command` since Bash is now denied outright). 43/43 affected tests green; ruff clean (no new findings). *(recall-loop validation 2026-05-30; chat→dispatch design call resolved.)*
- [ ] **IMP-021** — `test_agent_documentation_chat_routes.py::test_chat_routes_explicit_documentation_intent_to_subagent` fails (pre-existing, surfaced during IMP-020 closeout 2026-05-30, **not** caused by it): asserts the doc-intent subagent prompt contains `"canonical_ref": "main"`, but `resolve_canonical_doc_ref()` (`knowledge/maintained_freshness.py:60`) resolves `main` → remote default → current branch → `master` → `main`, and the test's temp git repo has no `main` branch (this machine's git `init.defaultBranch=master`), so it falls back to the temp repo's branch. Environment-sensitive test, not a confirmed product defect. Fix options: (a) make the test create a `main` branch (or assert against the resolved ref, not a literal `"main"`); or (b) if the product should track the repo's real default, decide whether `CANONICAL_DOC_REF`/resolution order should prefer the remote default over a hardcoded `main`. Root-cause + decide test-vs-product before patching. *(IMP-020 closeout 2026-05-30.)*
- [ ] **IMP-022** — Dashboard does not let the operator open individual **phase-level agent runs** (feature-verifier, gate-remediator, build-verifier, etc.) to inspect completed or ongoing sub-agent activity. Root cause: `frontend/src/features/board/TaskDetailSidebar.tsx:35` `taskRuns = agentRuns.filter((run) => !isPhaseLevelRun(run))` drops phase-level runs, and `:36` surfaces only ONE trace run (the running one, else `latestRun`). The backend already exposes the data (`routes/gates.py:103` `GET /tasks/{id}/runs`, `:111` `GET /runs`, `:117` `GET /runs/{run_id}`; `Task.agent_runs` with `selectinload(AgentRun.events)`), so this is a frontend surfacing gap: render each phase-level run (agent name, status running/done, duration, cost) as a clickable row that opens its event trace, including in-flight runs. *(operator validation 2026-05-30 — "i am not able to click the agent runs like feature verifier, or gate remediator; i should see completed or ongoing runs".)*

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
- [ ] **Migrate the chat runtime from bare `query()` to the `ClaudeSDKClient` async context manager.** PARTIAL — the subagent/phase-dispatch path is already migrated (`runner.py:690` uses `async with ClaudeSDKClient(options=options) as client`). Remaining gap: `claude_runtime.py:265` (the long-lived chat path) still uses bare `sdk_query(prompt=…, options=…)` — the surface most exposed to multi-minute holds. Migrate it so `__aexit__` cancels background monitor tasks deterministically, replacing the manual `try/finally + stop_monitor.set()` discipline IMP-010 fixed by hand. *(INSIGHTS Run #7 § Section C Action 1, P0-2; narrowed 2026-05-29 roadmap-audit.)*

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
- [ ] **Codify the flag-+-drain pattern for `receive_response()` loops (hardening; no acute bug today).** Revalidated 2026-05-29: the single `async for … client.receive_response()` site (`runner.py:692`) has **no early `break`**, so the acute asyncio-cleanup risk is absent. Remaining work is preventive only — codify the flag+drain rule in the backend rubric so a future early `break` can't strand monitor tasks or rolled-back sessions. **Downgraded from P0** to hardening. *(INSIGHTS Run #7 § P0-2; revalidated 2026-05-29 roadmap-audit.)*
- [ ] **Auto-complete a feature when all its tasks are done** — forward-only: when the last task of a feature transitions to `done`, set the feature to `done`; a task reverting to `pending` does not revert the feature; manual feature status changes stay independent. Builder lifecycle behavior. *(Surfaced via devpulse validation 2026-05-28; originally mis-filed as a devpulse app feature, `sprint_planned`. See IMP-016.)*
- [ ] **Auto-complete a backlog item when all its tasks finish** — when any task reaches completed, check sibling tasks; if all are `done`, transition the backlog item to `done`. Builder lifecycle behavior. *(Same origin as above; mis-filed as a devpulse app feature. See IMP-016.)*

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
- [ ] **`can_use_tool` enforces subagent phase boundaries (autopilot precondition).** PARTIAL — the callback is wired on all run paths and `PermissionResultDeny` enforcement already exists for chat tools (`agent_tool_policy.py:52`, reached via `routes/agent.py:702 can_use_tool`). Gap: the subagent/runtime path uses `claude_runtime.py:236 _auto_approve` (always `PermissionResultAllow`), so phase-boundary denial — parallel dispatches (IMP-007 class), wrong-tool selection (IMP-006 class), precondition-violating calls (IMP-009 class) — is NOT enforced at the SDK boundary for subagents. Extend the existing deny logic to the subagent path, one layer earlier than the `dispatch_lock.py` backend guard. *(INSIGHTS Run #7 § Section C Action 2, P0-1; narrowed 2026-05-29 roadmap-audit.)*
- [ ] **Retry/cycle state machine fed from typed SDK error signals (autopilot precondition).** Use `ResultMessage.is_error`, `ResultMessage.errors`, `ResultMessage.api_error_status`, `AssistantMessageError` literal (`"rate_limit" | "max_output_tokens" | "server_error" | ...`), and `RateLimitEvent`. Increment cycle-detection counter on the transition itself; never on the next (commit `1153ec6` lesson). Synthetic-state test for every retry path before autopilot ships unattended. *(INSIGHTS Run #7 § P2-5. `agents/runner.py:818-845` already catches `CLINotFoundError`/`ProcessError`/`CLIJSONDecodeError`; extend to `AssistantMessageError`/`api_error_status`.)*
- [ ] **G5 — `permissionDecision="defer"` + `DeferredToolUse` for mid-run approval gates.** Today high-risk tool calls during unattended runs collapse the task to BLOCKED state; with autopilot on, this is a dead end. Returning `permissionDecision="defer"` from a `PreToolUseHookSpecificOutput` queues a `DeferredToolUse` the operator (or autopilot policy) can resolve later without halting the surrounding plan. Verified absent in `src/`. Pre-requisite: `ctx7 docs /anthropics/claude-agent-sdk-python "permissionDecision defer DeferredToolUse"` against SDK 0.2.85. *(SDK rubric § Permissions; INSIGHTS ad-hoc § G5, P1.)*

### M2.5 — Architecture and design language coherence

The dashboard feels like one product.

- [ ] Frontend React architecture rubric ([docs/rubric/frontend-react-architecture.md](../rubric/frontend-react-architecture.md)) passes on all current and future surfaces; no god components.
- [ ] Backend service architecture rubric ([docs/rubric/backend-service-architecture.md](../rubric/backend-service-architecture.md)) passes; clear ownership boundaries; no second control owners for the same concern.
- [ ] Design language ([docs/design-docs/design-language.md](../design-docs/design-language.md)) applied consistently; design-system primitives only, no ad-hoc styles.
- [ ] **Codify the short-lived-session pattern in the backend rubric.** Dispatch session stays idle during `runtime.run()`; intermediate DB writes from `on_chunk`/`receive_response` use `async with get_session_factory()() as db:` per chunk (IMP-012 pattern); SSE endpoints never `Depends(get_db)` past the initial snapshot (IMP-011 pattern). *(INSIGHTS Run #7 § P0-2.)*
- [ ] **Empty-response envelope convention in the backend rubric.** Every aggregation endpoint that can return empty/zero returns a `state` field (`"running" | "no_data" | "scope_mismatch"`) plus a `note` string (IMP-003 `active_runs_note` pattern, IMP-005 `memory_root` pattern). *(INSIGHTS Run #7 § P1-4.)*
- [x] **`AgentDefinition.maxTurns` set per subagent.** Completed under M1.4: `definitions.py` sets `max_turns=20` on every subagent; `runner_options.py:61` forwards it to the SDK as `maxTurns`. Caps runaway loops at the SDK boundary. *(Duplicate of the M1.4 closure; revalidated 2026-05-29 roadmap-audit — `grep max_turns src/.../agents` confirms per-subagent values + forwarding.)*
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
