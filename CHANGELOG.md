# Changelog

Compact, agent-facing project history. Keep entries reverse chronological and
evidence-first. This file records what changed and where to inspect proof; it
does not own product contracts, workflows, or quality gates.

Format follows Keep a Changelog conventions: `Added`, `Changed`, `Fixed`,
`Validation`, and `Notes` as needed.

**Autoresearch loop changes (Baseline / Iterate / Fix lanes, KNOWN_PATTERNS, harness scripts) → [docs/autoresearch/PROGRESS.md](docs/autoresearch/PROGRESS.md), not here.** Builder runtime changes that surfaced through autoresearch still land here.

## 2026-06-26 - fix(ci): green the PR #10 test wall — color-deterministic CLI tests + isolate the dashboard build

The ruff floor fix (`bf1eff9`) let the pytest wall run in CI for the first time in ~12 days, exposing 5 pre-existing failures on `feat/loop4-outcome-attribution`. Reproduced 1:1 in a Python 3.11 venv with CI-resolved deps (typer 0.25.1, click 8.4.2, rich 15.0.0); the typer<0.26 pin was a red herring — the real causes were a color-env leak and an unstubbed frontend build.

### Fixed

- **3 CLI-help tests** (`test_builder_help_exposes_single_startup_owner`, `test_logs_help_includes_raw_mode`, `test_kb_add_help_lists_supported_doc_types`): GitHub Actions forces a terminal (`FORCE_COLOR`), so typer/Rich rendered `--help` as an ANSI-styled panel and the bold/dim escapes interleaved with the text broke the literal substring assertions (CI output byte-identical to a local `FORCE_COLOR=1` repro). `NO_COLOR` does **not** override `FORCE_COLOR` in Rich (verified: both set → escapes still emitted), so the env approach is insufficient. Fixed by making the assertions color-env-independent: a `_plain()` helper (`tests/test_builder_cli_surfaces.py`, `tests/test_kb_publisher.py`) strips ANSI escapes before the substring check. `tests/conftest.py` also sets `NO_COLOR=1` / clears `FORCE_COLOR` for deterministic local output (defense-in-depth, not load-bearing).
- **2 server-start tests** (`test_server_start_uses_repo_local_port_when_flag_omitted`, `test_server_start_flag_overrides_repo_local_port`): `start` calls `_publish_dashboard_assets`, which falls back to the **installed package's** `frontend/` and runs `npm run build` (`tsc -b && vite build`) when the project has no built dashboard — that build fails in CI (no node_modules: `Cannot find type definition file for 'vite/client'`) → `start` exits 1. The tests stubbed `_start_uvicorn` and the port check but not the build; they passed locally only because the repo frontend was already built. Added `_stub_dashboard_publish` (`tests/test_server_cli.py`) so the port-resolution tests no longer depend on a built dashboard.
- `.claude/loops/loops.json`: invalid JSON escape (`\-` in a `grep` regex inside the master prompt, regression from `1f78809`) — the file no longer parsed, so the orchestrator could not load/re-arm loops. Doubled the backslash; JSON parses and the command (`grep -c '^\- \[ \]' …`) runs.

### Validation

- Full suite in a CI-faithful env (Python 3.11, typer 0.25.1 / click 8.4.2 / rich 15.0.0, `FORCE_COLOR=1`): **1731 passed, 0 failed** (was 1728 passed + 3 failed, +2 server-start failing on a fresh CI checkout). `ruff check .` clean. The 5 originally-failing tests verified green under the exact CI conditions.

### Notes

- typer pin (`typer[all]<0.26`) left in place — unverified against 0.26, and harmless; the pin comment's "real CLI-test root cause" claim is superseded by this entry (color, not typer). Unpinning is a separate, testable task.

## 2026-06-19 - fix(ux): IMP-046 — stop leaking the raw build-verify tool dump into the operator's blocked_reason

Found by the dogfooding flywheel (sprint 1): a real notes-app task was blocked with `final_checkout_build_failed: npm run lint FAIL: 59:106931 error 'RTCPeerConnection' is not defined …` shown verbatim on the Board — a minified `node_modules` bundle line, meaningless to a customer who built a notes app, and long enough to bury the Recover button.

### Fixed

- `orchestrator/deterministic_verification.py`: new `summarize_build_failure_for_operator(output)` — names the failed command(s) (e.g. ``Build verification failed: `npm run lint` did not pass …``) and points to run evidence instead of dumping the raw output. Wired into both block sites (`orchestrator/sprint_lifecycle.py`, `services/run_reconciliation.py`). Preserves the `final_checkout_build_failed:` routing prefix (`task_recovery` keys off it) and keeps the raw output in `verification_evidence` (remediation re-derives detail via a fresh BuildVerify run, so no degradation). M2.4 no-internals-leakage.

### Validation

- 3 helper unit tests (names command, no `RTCPeerConnection`/column-number leak, multi-command, capped fallback) + extended reconciliation integration test (`blocked_reason` summarized, raw output stays in evidence). 66 targeted tests green; ruff clean; `architecture-boundary` + `state-integrity` gates ok. Live: recovered the real notes-app strand through the dashboard, blocked→done in ~2 min ($0.20). `T:backend` `T:browser`.

### Notes

- Root cause of the block itself (eslint linting `node_modules` + missing browser globals) was already fixed by the scaffold change in `c8f214b`; this fix is the operator-experience half. Residual frontend frictions (Recover-button visibility, Blocked-column-last layout) deferred. Detail: ROADMAP IMP-046.

## 2026-06-19 - fix(stability): IMP-042/040/044 — never-strand a customer task (retry-budget reset, SSE future cancel, runtime idle timeout)

Stabilization tick toward the dogfooding-reliability bar ("a customer builds feature after feature across multiple sprints without hitting a blocker"). The three open P2 items were design-flagged; the operator made the calls and these are the three customer-stranding failure modes, now closed at root.

### Fixed

- **IMP-044** (`agents/runner.py`, `runtime/claude_runtime.py`, `orchestrator/agent_run_lifecycle.py`, `orchestrator/failure_diagnosis.py`): the Claude runtime stream loop had no idle timeout (Codex did), so a hung SDK stranded the task in a non-terminal phase forever. Added `_STREAM_EVENT_IDLE_TIMEOUT_SECONDS = 120.0` + an `idle_timeout_seconds` param: when set, each `receive_response()` step is bounded by `asyncio.wait_for` (inactivity clock, resets per message — legitimate long turns survive); on expiry returns `RunResult.error` with **no** capability-limit stop_reason → recoverable FAILED. **Armed only on the orchestrated lane** (where `can_use_tool` never blocks on an operator); the chat lane is left unwatched and covered by IMP-040 instead. New `failure_diagnosis.is_runtime_idle_timeout` → `issue="runtime_idle_timeout"`.
- **IMP-040** (`embedded/server/chat_state.py`, `embedded/server/routes/agent.py`): an unanswered AskUserQuestion / approval-card `await future` pinned the live runtime session forever. Added `cancel_session_pending_answers()` + `has_active_subscribers()`; the SSE `event_generator` `finally` cancels the session's pending futures **only when no subscribers remain** (multi-tab safe), raising `CancelledError` to release the session.
- **IMP-042** (`orchestrator/quality_gate_runner.py`): `retry_count` reset only on recovery, never on forward progress → a task carried consumed gate-retries into the next gate cycle and hit `quality_gate_cap_exceeded` prematurely. Now reset to 0 on the gate PASS → `PR_CREATION` forward-progress branch (per-gate budget).

### Validation

- Full suite green; `ruff check .` clean; `state-integrity` + `architecture-boundary` + `claude-agent-sdk` quality-gates ok. Paired prove-fail/pass-with tests for all three (`test_orchestrator_gates.py`, `test_embedded_server_app.py`, `test_agent_runner.py`, `test_failure_diagnosis.py`). `T:backend` `T:browser:na`.

### Notes

- Operator design calls (via AskUserQuestion): idle (not wall-clock) timeout → recoverable FAILED; cancel-on-disconnect for interactive awaits; per-gate retry budget reset on progress. Detail: ROADMAP M1.1 IMP-040/042/044.

## 2026-06-19 - chore(build-maintain-cycle): node-workspace eslint-ignores + self-verify §3a + hermes-chrome skill sync gate

Landed the green, uncommitted follow-on from the prior build-maintain-cycle session so the tree is clean before the stabilization tick.

### Changed

- `services/workspace_scaffold.py` (`_MINIMAL_ESLINT_CONFIG`) + `agents/definitions.py` (scaffold prompt): the scaffolded Node `eslint.config.js` now emits a top-level `ignores` block (`node_modules/**`, `.agent-builder/**`, `dist/**`, `build/**`) so bundled/generated files are never linted; the scaffold prompt now mandates `globals.browser`+`globals.node` (no hand-enumerated browser globals) and the ignore block.
- `docs/workflows/orchestrator-routing.md`: added Shared-fix-contract step **3a — self-verify before declaring done** (surface-specific verifier matrix; partial evidence = not done).
- `.claude/skills/hermes-chrome/`: new hard rules 10 (`bridge()` is inline-only) + 11 (never `sleep N`), an operator HTML guide (`references/hermes-chrome-guide.html`, open-on-demand), and a `scripts/sync-check.py` SKILL↔HTML sync validator wired into `validate.sh`.

### Validation

- `tests/test_workspace_scaffold.py` asserts the eslint `ignores` entries; full suite 1715 passed; `ruff check .` clean; hermes-chrome `validate.sh` PASS (12/12 rules, sync PASS). `T:backend` `T:browser:na`.

## 2026-06-18 - fix(orchestrator): IMP-043(a) — durable FAILED-state persist on the dispatch failure path

Stabilization-loop tick (Epoch 1, bug-fix before features). Burned down a P2 finding the codebase-review loop filed but never fixed.

### Fixed

- `orchestrator/orchestrator.py` (`dispatch` exception handler): the IMP-010 defense suppressed the rollback error but left the FAILED-state `self.db.flush()` **unguarded**. When the session was unrecoverable the `flush()` raised, the exception escaped `dispatch`, the in-memory `FAILED` status was never committed, and the task stayed in a dispatchable status → re-dispatch loop. Now the `flush()` is guarded; on failure it logs `phase_error_persist_fallback` and persists FAILED durably via a fresh short-lived `get_session_factory()` session that re-fetches the task by id and commits (the established side-channel pattern from `agent_run_lifecycle.py:252` / `orchestrator.py:1304`); `phase_error_persist_failed` is logged if the row is absent.

### Validation

- New paired test `tests/test_orchestrator.py::TestDispatchFailedPersistFallback::test_failed_state_persisted_via_fallback_when_primary_flush_raises` — inserts a real task row, forces the primary `flush()` to raise, asserts `dispatch` does not propagate and the task is durably `FAILED`/`blocked_reason` in a separate verify session. Fails-without / passes-with. `tests/test_orchestrator.py` 45 passed; `ruff check` clean; `state-integrity` quality-gate ok. `T:backend` `T:browser:na`.

### Notes

- Scoped to IMP-043(a) (deterministic root cause). Part (b) — `await runtime.run()` has no orchestrator-level timeout — was **split to IMP-044** and left open as a design decision: the Codex runtime already enforces internal idle/response timeouts, so wrapping at the orchestrator level (and the on-timeout transition) is intent-dependent and was not guess-fixed per the Shared fix contract auto-fix gate.

## 2026-06-18 - feat(optimization): rework-share efficiency verdict + gate-timeout reprovisioning

The optimization summary now treats wasted retry spend as a first-class efficiency signal,
and a gate that times out (rather than failing on code) is routed to deterministic
re-provisioning instead of the LLM remediator.

### Added

- `services/codex_optimization.py`: `summarize_runs_for_optimization` now emits `rework_token_total` (gate-remediator raw tokens) and `rework_share` (rework / `raw_total`). When `rework_share >= 0.25`, `_recommended_next_change` returns the new verdict `reduce_rework_before_token_band` — prioritized ahead of the raw-token-band check, because retry waste is the cheaper lever to pull first.
- `MetricsPage.tsx` + `types.ts`: new "Rework" panel (rework % / gate-pass %) and an "inefficient (rework)" benchmark label that overrides the band status at ≥25% rework. Grid widened to 5 columns.

### Fixed

- `orchestrator/gate_feedback.py`: new Step 1.6 — a gate `TIMEOUT` / `DEADLINE_EXCEEDED` failure is a non-code failure (cold workspace re-running deps inside the gate deadline). The LLM remediator cannot fix a timeout, so it is now routed to deterministic out-of-band re-provisioning (`_reprovision_env`, now Python **and** Node via `ensure_node_env`) + a gate re-run, bounded by the retry budget.
- `ObservabilityPage.tsx`: unified recommendations now dedupe by `code` (not just `detail`) and drop empty rows, removing the duplicate/blank recommendation cards.
- `observability/summary_runtime_aggregates.py`: removed the redundant `baseline_ready` info recommendation (it duplicated the deterministic `deterministic_baseline_ready` rule surfaced in the UI).

### Validation

- `tests/test_codex_optimization.py` (+rework-share verdict cases), `tests/test_gate_feedback.py` (+timeout-reprovision path), `tests/test_observability_summary.py`, `tests/test_dashboard_api.py` — 99 passed; `ruff check` clean on all touched files. `T:backend` `T:browser:pending` (Metrics/Observability render needs a live dashboard sweep).

## 2026-06-17 - fix(db): ui_preview_enabled upgrade-path migration (found by the optimization loop's baseline)

The new `optimization` loop's first activation step — an autoresearch baseline — surfaced a real Builder upgrade-path bug. IMP-034b added `Feature.ui_preview_enabled` (`db/models.py:257`) but no matching idempotent migration in `db/session.py`. Since `Base.metadata.create_all` only CREATEs absent tables (never ALTERs existing ones), **any Builder DB created before IMP-034b** — real users upgrading, and the autoresearch seed snapshot — crashed on every ORM query touching `features` with `sqlite3.OperationalError: no such column: features.ui_preview_enabled`. The Builder server never became ready, blocking the entire baseline.

### Fixed

- `db/session.py`: added the missing `if "ui_preview_enabled" not in feature_columns: ALTER TABLE features ADD COLUMN ui_preview_enabled BOOLEAN DEFAULT 0` guard, matching the existing idempotent migration pattern for the other 8 Feature columns.

### Validation

- New regression test `test_init_db_adds_ui_preview_enabled_column_to_legacy_features_table` (seeds a legacy `features` table without the column, runs `init_db`, asserts the column exists + a `SELECT` no longer raises) — fails-without/passes-with the fix. `tests/test_db_sprint_pr_migration.py` neighborhood 13 passed; ruff clean. `T:backend` `T:browser:na`.

## 2026-06-17 - IMP-023 Fix B: accurate cost + dispatch count in the `logs analyze` headline

The `builder logs analyze --session <id> --json` headline reported `total_cost_usd=0` for chat-target sessions even when sub-agent runs spent money (Fix A, 2026-05-31, already corrected the token total). The session cost was invisible to the operator and to the autoresearch baseline (cost attribution), and there was no field at all for the sub-agent dispatch fan-out. The enabler half of the cost-optimization work (M2.3) — get the measurement right before optimizing against it.

### Fixed

- `_analyze_timeline` (`cli/commands/logs.py`): `total_cost_usd` now falls back to the session-scoped `runtime_aggregates["totals"]["cost_usd"]` (sum of `agent_runs.cost_usd`) when both prompt telemetry and the analysis-target agent_run carry no cost — mirroring the existing token fallback.

### Added

- New `run_count` field in the analyze headline (`runtime_aggregates["totals"]["runs"]`) — exposes the sub-agent dispatch count. Deliberately a distinct field rather than overloading `prompt_count` (which stays `len(prompts)` = operator-chat-turn count, bound by the Bar 1 vocabulary contract).

### Notes

- Does NOT change `recommended_next_change` / `avoidable_token_estimate` — those read the token-based `optimization_summary` (already covered by Fix A), not the headline cost. Fix B's value is accurate operator-facing cost + dispatch visibility (unblocks autoresearch cost attribution).

### Validation

- New prove-fail-without-fix test `test_logs_analyze_headline_cost_and_run_count_fall_back_to_session_aggregate_imp023b`; analyze tests 9 passed, consumer files 45 passed, `test_builder_cli_surfaces.py` 58 passed; ruff clean. `T:backend` `T:browser:na`.

## 2026-06-16 - Restore green ruff-lint CI floor (157 → 0 errors)

CI's `ruff check .` step (`ci.yml`, Python 3.11) had been red since the workflow was wired (6/6 `ci.yml` runs failed). A failed lint step **skips** the format-check and pytest steps, so the test wall had not actually run in CI for ~12 days. Found during a stabilization sweep (STATUS claimed "ruff clean" — it was scoped to changed files only, not `ruff check .`).

### Fixed

- **py311 parse failure** (`.claude/plugin/hermes_chrome/scripts/install_hermes_chrome_bridge.py:117`): backslash escape sequences inside an f-string replacement field — valid only on Python 3.12+, but the project targets `py311`. Extracted the `str.replace(...)` chain into a local `win_ext_path` variable before the f-string (byte-identical output). This was 8 of the `invalid-syntax` errors.
- **103 autofixable lint errors** via `ruff check --fix` (I001 import-sort, F401 unused imports, W293 whitespace, F541 f-prefix, UP017 `datetime.UTC`, UP041, E401, etc.) across 39 files — all behavior-preserving.
- **56 manual errors**: E402 import-reorder to top blocks (`agent_chat_result_publisher.py`, `agent_run_lifecycle.py`, `quality_gate_runner.py`, `tests/test_orchestrator_gates.py` — no circular deps, verified by import); SIM105 → `contextlib.suppress` (9); N806/ASYNC230 `# noqa` (intentional in-function constants / one-off script); B904 `raise ... from`; B905 `strict=False`; E741 rename; SIM103 direct-bool-return.
- **Regression self-corrected**: the F401 autofix wrongly stripped two test-surface re-exports from `routes/agent.py` (`_append_voice_final_summary_if_needed`, `_message_has_documentation_intent`) — they used a non-redundant `name as _name` alias and lacked `# noqa`. Restored both with `# noqa: F401` (the file's existing re-export convention). Caught by the full suite (2 failures), fixed before commit.

### Notes

- **Scoped lint-only** (operator decision): `ruff format` (216 files would reformat) deliberately NOT run — that is the documented repo-wide-format avalanche (`feedback_ci_autofix_design`, ~219 files reverted before). CI's `Ruff format check` step stays red pending a separate reviewed pass.

### Validation

- `ruff check .` → "All checks passed!" (0 errors).
- Full suite: **1644 passed, 0 failed** (clean post-fix run). `T:backend` `T:browser:na`.

## 2026-06-09 - IMP-036: owned Python workspace env provisioning + classify-before-agent

Generated Python apps had no dep-provisioning owner (the Node lane did, via `npm install` guards). Every phase that ran pytest invoked bare `pytest` / `sys.executable` against an interpreter where the app's third-party deps were never installed → `ModuleNotFoundError` → the LLM gate-remediator burned its retry cap "fixing" an environmental problem it cannot fix by editing code. Fix: a single owned module for *how a Python app's tests are run*, plus a classify-before-agent step so environmental gate failures re-provision deterministically instead of dispatching the model.

### Added

- `quality_gates/python_env.py` — single source of truth for Python-lane test provisioning: `is_python_workspace`, `setup_commands` (idempotent venv-create + editable/`-r` install, mirrors the Node `npm install` guard), `pytest_argv` (canonical venv-interpreter invocation, `venv_required` for plan-time callers), `ensure_python_env` (inline async provision, `force=True` rebuild), and `is_environmental_failure` (missing-dep / interpreter signature matcher). Deterministic by design — never delegated to an agent.
- `tests/test_python_env.py` — provisioning command shape, idempotency, env-failure signatures, venv-interpreter selection.

### Changed

- `orchestrator/gate_feedback.py` — Step 1.5 classify-before-agent: a failed gate with an environmental signature re-provisions the workspace env (`ensure_python_env(force=True)`) and re-runs the gates, bounded by the retry budget (escalates to capability-limit when exhausted), instead of burning the gate-remediator on an unfixable-by-source failure.
- `quality_gates/testing.py`, `embedded/scripts/build_verify.py`, `agents/tools/workspace_tools.py`, `services/runtime_guidance.py` — all four test-running / command-discovery call sites now route through `python_env` so the interpreter rule lives in one place (provision the venv, run pytest under it; bare `pytest` hits the host env lacking the app's deps).

### Validation

- 57 targeted tests pass (`test_python_env` + `test_gate_feedback` + `test_node_quality_gates` + `test_orchestrator_build_verification`); changed files ruff-clean. `T:backend` `T:browser:na` (no operator surface).

## 2026-06-04 - IMP-034b (backend): operator-selectable UI prototype preview

Backend for the prototype-first half of IMP-034: for UI features where the operator opted in, the builder generates a static HTML mockup after design and holds for approval BEFORE implementation. Reuses the existing ApprovalGate + DESIGN_REVIEW + DesignDocument plumbing — no schema migration, no new TaskStatus. Frontend preview/approve card is the next increment (IMP-034 stays open).

### Added

- `agents/definitions.py` — new `ui-prototyper` AgentDefinition (sonnet, 10 turns): emits one self-contained static HTML mockup to `.ui-preview/mockup.html` using the IMP-034a `{design_directive}`, ends with a `UI_PREVIEW_RESULT_JSON` sentinel.
- `db/models.py` — `Feature.ui_preview_enabled: bool = False` (the per-feature opt-in).
- `orchestrator/build_verification.py` — `should_run_ui_preview(task)` = `is_ui_task` AND `feature.ui_preview_enabled is True` (pure, testable predicate).
- `tests/test_ui_preview_backend.py` — payload normalization, `ui_preview` approval routing, the predicate, and the agent-definition contract.

### Changed

- `orchestrator/orchestrator.py` — `_phase_design` success branch: when `should_run_ui_preview`, dispatch `ui-prototyper`, persist a `DesignDocument(doc_type="ui_preview")`, open `ApprovalGate(gate_type="ui_preview")`, and park in `DESIGN_REVIEW`; else proceed to `IMPLEMENTATION` (unchanged). New `_run_ui_preview` / `_read_ui_preview_mockup` helpers.
- `orchestrator/approval_outcomes.py` — `ui_preview` gate APPROVE → `IMPLEMENTATION` (reject/changes still → BLOCKED).
- `embedded/server/agent_feature_payloads.py` + `agent_feature_delivery.py` — normalize + persist `ui_preview_enabled` from the feature-spec payload (mirrors `proposed_tasks`).
- `agents/execution_policy.py` — `ui-prototyper` policy (medium effort, sonnet, 60k budget). `agent_run_lifecycle.py` — KeyError-safe setdefaults for the new template vars.

### Validation

- 77 targeted tests + 374 in the broad backend sweep pass; my changed files ruff-clean; imports OK. (1 unrelated pre-existing failure: `test_dashboard_design_tokens` — caused by uncommitted frontend WIP not in this change; reproduces with all 034b changes stashed.)

## 2026-06-04 - IMP-035a: documentation-bridge parent runs on haiku

Full-lane capability-fit audit (all 13 Claude Agent SDK phases vs `claude-agent-sdk-rubric`) confirmed the lane is already well-tuned — G1/G2/G7, `cache_read_input_tokens` tracking, `ClaudeSDKClient` multi-turn streaming, the `trim_tool_output` PostToolUse hook, planner→designer resume-chaining, and per-role model tiers are all already optimal (credited, not re-recommended). Three genuine under-uses surfaced (→ ROADMAP IMP-035). Shipping the one structural certainty:

### Changed

- `agents/definitions.py` + `agents/execution_policy.py` — `documentation-bridge` is a zero-reasoning Agent-tool pass-through (`tools=()`, prompt = "invoke documentation-agent, return its JSON unchanged"), but `_model_for_agent` bucketed it into `implementation_model` (sonnet), wasting parent tokens. Moved it out of that bucket → falls through to `AgentDefinition.model="haiku"`; `_thinking_for_model("haiku")` → None. The real reasoning stays in the (sonnet) documentation-agent child.
- `tests/test_execution_policy.py` — `EXPECTED_ROLE_POLICIES["documentation-bridge"]` thinking `_ADAPTIVE`→`None` (coupled to the haiku move) + new `test_documentation_bridge_parent_runs_on_haiku`.

### Notes

- 035b (optimization-agent evidence-sweep subagent) and 035c (init-project-chat effort medium→low) parked on ROADMAP — calibration tweaks needing live validation.
- Audit correction: `chat` is in the `implementation_model` bucket → resolves to **sonnet**, not haiku as first stated. Possible larger win (chat runs often) but may be intentional for interview quality — flagged on ROADMAP, not acted on.

## 2026-06-04 - IMP-034a: Product-UI design directive injected into UI code-gen

Operator observation: generated apps lack UI taste. Root cause — **no design guidance existed in any agent prompt**, so `code-gen` shipped generic AI-slop UIs (default blue/purple, missing interactive states, ad-hoc spacing, flat type). Fix distills the transferable, stack-agnostic subset of the third-party `taste-skill` project + Vercel Web Interface Guidelines / Refactoring UI / NN/g heuristics into a compact directive (the upstream skill is landing-page-scoped, React/Tailwind-bound, and ~35K tokens — deliberately NOT inlined). Mechanism rejected: installing the skill via `npx skills add` — the builder's code-gen runs in ephemeral workspaces with no `.claude`, so it discovers no filesystem skills; guidance must be prompt-enrichment (see `verifier-skill-vs-prompt`).

### Added

- `agents/design_directive.py` — `PRODUCT_UI_DESIGN_DIRECTIVE` (~520 tok, repo `estimate_tokens`) + `design_directive_block(is_ui)`. STATIC, stack-agnostic, principle-level (color/spacing/hierarchy/depth/states/forms/a11y/motion). Sourced from taste-skill + Vercel WIG / Refactoring UI / NN/g.
- `tests/test_design_directive.py` — 7 tests: highest-slop-signal coverage, stack-agnostic (no React/Tailwind/GSAP leak), UI gate, KeyError-safe template formatting both ways, <900-tok compactness ceiling.

### Changed

- `agents/definitions.py` — `code-gen` `prompt_template` gains a `{design_directive}` block beside `{workspace_map}`.
- `orchestrator/orchestrator.py` — injects the directive into the code-gen prompt gated by `is_ui_task(task, feature)` (reused from IMP-019); empty for CLI/library/non-UI work.
- `orchestrator/agent_run_lifecycle.py` — `template_vars.setdefault("design_directive", "")` keeps every other agent's `format()` KeyError-safe.
- `services/codex_optimization.py` — `prompt_budget_breakdown` registers a `design_directive` token segment for observability.

### Notes

- **Efficiency (capability-fit, Claude lane):** directive is STATIC and injected once → amortizes to ~0 marginal tokens/turn via **conversation-history prefix caching** (the IMP-028 replay path), NOT system-prompt caching (the builder's `system_prompt` is the pure `claude_code` preset with `exclude_dynamic_sections`; the rendered template is the first user message). `claude-agent-sdk` gate `ok:true` — this is model-loop judgment guidance, not a deterministic shortcut. Considered + rejected: moving the directive to `system_prompt: {append}` (marginal cross-run cache gain vs. fragmenting the single-prompt model).
- IMP-034b (operator-selectable UI prototype preview) still open. `T:browser` live-verification of 034a still pending.

## 2026-06-04 - Enforcement wiring: activate test-sync gate (local hook + CI) + goal-doc progress-routing lint

`/self-optimize` (14d) found "behavioral change without test update" still the #1 recurring theme (score 30, 7 fix-commits) **despite** the existing `pre_commit_checks.py` gate — root cause: the gate was never activated. Rule existed; nothing enforced it.

### Added

- `.github/workflows/ci.yml` — CI wall: `ruff check` + `ruff format --check` + `pytest` on PR + push to `master`. Enforces the test-failure gate regardless of a local `--no-verify` bypass.
- `lint_goal_docs.py` `PROGRESS_ROUTING` — WARN-only check flagging autoresearch run-log markers (`baseline_runs_summary` / `iteration #N` / `run #N`) misrouted into ROADMAP/STATUS instead of `docs/autoresearch/PROGRESS.md`. Zero-false-positive tokens (σ-floor / cache_ratio deliberately excluded; verified against current docs). See `feedback_autoresearch_progress_routing`.
- `.github/workflows/ci-autofix.yml` — deterministic auto-remediation tier: on a PR, runs `ruff --fix` + `ruff format` in CI (clean cloud checkout — never touches local WIP) and pushes the style fix back to the PR branch. Loop-safe via `GITHUB_TOKEN`. Judgment fixes (tests/logic) deferred to on-demand `@claude`, not autonomous.

### Fixed

- `.githooks/pre-commit` — was inert (`core.hooksPath` unset, so git used empty `.git/hooks`) and called `python` (absent on WSL → exit 127). Hardened to a `python3`/`python` fallback + `exec` (valid for normal clones). **This repo runs in a managed env where hooks are disabled**, so local-hook enforcement does not fire here — `core.hooksPath` was *not* left set; **CI (`ci.yml` + `ci-autofix.yml`) is the enforcement floor**, since it runs on GitHub's runners outside the managed env.
- `.github/workflows/documentation-freshness.yml` — `main` → `master` across trigger, `git fetch origin master:master` (would otherwise fail — `main` is deleted), and PR text. Default branch is `master`.

### Notes

- Pre-existing repo-wide `builder lint` debt (2 memory errors + 31 complexity ratchet violations, from uncommitted WIP on disk) is unrelated to this change and not addressed here.

## 2026-05-31 - IMP-023 Fix B (real root cause: telemetry clobbering) + chat-turn annotation repair

builder-test static→DB root-cause dig on the live pomodoro forward-eng app. Two fixes, both root-cause not symptom.

### Fixed

- **IMP-023 Fix B** (`observability/timeline_analysis.py`) — `builder logs analyze` reported `total_cost_usd=0` (and pre-fallback `total_tokens=0`) for chat sessions. DB inspection of session `2d97e274` proved the cost WAS persisted (`chat_run_status_payload` writes `cost_usd`/`tokens_used`; one run_status carried `cost_usd=0.1041185, tokens_used=946`). Root cause: a single prompt emits several run_status events — initial running marker, the real model-run total, then deterministic continuation/dispatch/terminal markers carrying **zeros** — and `build_timeline_prompts` folded them all into the one prompt with **last-write-wins**, so a trailing zero marker clobbered the real totals. Fix: `_merge_run_status_telemetry` **accumulates** additive telemetry (`cost_usd`, `tokens_used`, `tokens_input/output/cached`, `raw_tokens`, `noncached_plus_output_tokens`, `duration_ms`) across a prompt's run_status events; keeps last-non-empty for status scalars. Streaming partial usage is live-SSE only (`publish_stream_usage` never persists run_status) so summing cannot double-count. **Live-verified**: `total_cost_usd 0 → 0.1041185`, `total_tokens 0 → 946` (the accurate per-prompt figure; supersedes the Fix-A 4445 raw-aggregate fallback that over-counted by pulling the dispatched task's runs into the chat-session headline). The Fix-A fallback stays for the distinct no-run_status (agent_run-only) case.
- **chat-turn prompt-plan annotations** (`embedded/server/chat_turn_prompting.py`) — the M1.3-extracted wrapper annotated `documentation_context` as `str | None` and `forward_engineering_context` as `str | None`, but the real runtime types are `dict[str, Any] | None` (from `ActiveSpecialistRoute.context`) and `bool` (from `_needs_init_project_bootstrap`). Corrected both; clears 4 propagated Pyright errors across `chat_turn_prompting.py` + `routes/agent.py`. Annotation-only; runtime behavior unchanged.

### Validation

- `tests/test_timeline_analysis.py` (new, 3 tests: trailing-zero survival, multi-real-invocation sum, observability promotion). 189 chat/timeline/cli/observability tests green; 57 CLI-surface tests green (incl. the Fix-A `…falls_back_to_raw_aggregate_imp023` guard, still passing). Live re-check of `builder logs analyze --session 2d97e274` confirms non-zero cost+token headline.

## 2026-05-30 - Token-cost work: IMP-027a/c task sizing + IMP-028 workspace map; IMP-021 doc-tests fixed

Cheaper-per-change work (goal: beat codex/claude-code on enterprise cost-per-change). Root cause of the burn was DB-verified as **planning-time over-decomposition**, not within-phase reruns: deterministic verifier phases (build-verifier / evidence-collector / feature-acceptance-tests) record `0,0,0,0` tokens. ROADMAP items IMP-027/028 remain `[ ]` (027b per-task phase planner + 028 live A/B and preset experiment still open); only the delivered portions are recorded here.

### Added

- **IMP-027a + IMP-027c** (commit `851ba75`) — model-driven task decomposition (intake-folded). The chat intake agent now emits `proposed_tasks` (N≥1, sized to the real change) as structured output of its existing prompt-interpretation pass — model intelligence, not a deterministic keyword classifier. Wiring: `Feature.proposed_tasks` JSON column (`db/models.py` + idempotent migration `db/session.py`); `normalize_proposed_tasks` + payload carry (`agent_feature_payloads.py`); persistence (`agent_feature_delivery.persist_feature_spec`); model contract + sizing guidance in both intake prompts (`agent_prompt_builders.py` — "a trivial single-surface change is ONE task"); planner consumption (`sprint_execution._model_proposed_templates` / `_task_templates_for_feature`, model decomposition is source of truth, deterministic risk templates are fallback; `str.format` replaced with `_format_task_title`). **Live-proven**: a real Sonnet chat turn on a trivial cosmetic ask emitted `proposed_tasks` len 1; the planner produced exactly 1 task where the identical request previously produced a 5-task sprint.
- **IMP-028** (commit `1ebb84b`) — compact workspace file map injected into code-gen to stop per-turn re-exploration. The orchestrator injects `compact_workspace_map` (`agents/tools/workspace_tools.py`) into the code-gen prompt at dispatch (`orchestrator._phase_implementation`), via a `{workspace_map}` slot in the code-gen `prompt_template` and a `setdefault("workspace_map","")` in `agent_run_lifecycle` so every other agent's `str.format` stays KeyError-safe. Recall-loop map ≈ 77 tokens for the whole tree, replacing multiple ~20k-cached exploration turns (code-gen run was ~89% context, not generation).

### Fixed

- **IMP-021** (commit `1d1545f`) — three pre-existing doc-routing test failures (`test_agent_documentation_chat_routes::test_chat_routes_explicit_documentation_intent_to_subagent` + `test_agent_documentation_tool_approval::{test_documentation_routed_kb_contract_and_lint_skip_interactive_approval, test_documentation_routed_turn_still_prompts_for_unrelated_tools}`), confirmed failing at pre-session commit `cdb8be8` (unrelated to IMP-027/028). The original `canonical_ref` branch-resolution theory was wrong; actual causes were **(1) compact-JSON staleness** — doc context is serialized compact (`agent_prompt_builders.py:232`) but the tests asserted the old spaced format — and **(2) IMP-020 fallout** — the unrelated-tool test exercised `Bash`, which IMP-020 now denies-outright in the chat lane (no approval card). Fix is test-only (product behavior is correct): updated the three assertions to compact format and repointed the unrelated-tool case from `Bash` to `mcp__workspace__run_command`.

### Validation

- Full suite green: `1574 passed, 0 failed` (background run, 6m11s). 94+ regression green for IMP-027; 145 regression green for IMP-028; 11 doc-routing tests green for IMP-021. ruff clean throughout.

### Notes

- ROADMAP `[ ]` retained for IMP-027/028 by the commit-on-tick rule (sub-items open). This is a catch-up bookkeeping commit: code shipped in `851ba75`/`1ebb84b`/`1d1545f` without an accompanying CHANGELOG entry; this records the proof retroactively.

## 2026-05-30 - M1.1 IMP-018 + IMP-015 + IMP-020 closed; IMP-019 real-browser verification built

Operator-driven dashboard validation on a fresh managed app (recall-loop, a spaced-repetition flashcard app). Full idea→ship loop validated (5-task sprint, 0 errors, ~$2.02; real-browser acceptance + localStorage persistence proven; 62 generated-app tests + lint green).

### Fixed

- **IMP-018** — requirements interview degraded to free-text instead of structured `AskUserQuestion` cards. Root cause: global `permission_mode="dontAsk"` bypasses the SDK `can_use_tool` callback (the only place AskUserQuestion + tool-approval cards are produced). Added per-agent `AgentDefinition.permission_mode`; `chat` runs `"default"`; `runner.py` forwards it; `preapproved_tools` guard in `_authorize_chat_tool` preserves silent execution of granted tools. Validated live: structured cards render. Tests `test_chat_permission_mode_questions.py` + `test_agent_runner.py`.
- **IMP-015** — `type=feature` items rendered/announced as "improvement". `BacklogPage.tsx` `itemTypeLabel` mapped feature→"improvement"; `agent_chat_result_publisher` hardcoded the save-note noun; `agent_sprint_planning` hardcoded the start-question wording. Now type-aware/neutral; coupled capture-note parser in `agent_feature_payloads` made type-agnostic. Validated live: badge shows FEATURE.
- **IMP-020** — IMP-018's `permission_mode="default"` let the chat lane offer Approve/Deny cards for ungranted mutating built-ins (Edit/Write/Bash) on the generated app, which an operator could approve — bypassing the dashboard-first backlog→dispatch lifecycle. Design call resolved (always force capture→dispatch, grounded in CLAUDE.md dashboard-first doctrine): `agent_tool_policy.chat_mutating_builtin_denial()` + `CHAT_DISPATCH_REQUIRED_BUILTINS = {Edit, Write, Bash, MultiEdit, NotebookEdit}`; `_authorize_chat_tool` denies these (scoped to *ungranted* built-ins, after the preapproved/read-only checks) with a `mcp__builder__task_dispatch` routing message + a `tool_error` event instead of a card. Granted/confirmable non-built-in mutating tools (e.g. `mcp__workspace__run_command`) keep their cards — the tested path is intact. Tests: `test_chat_permission_mode_questions.py` (parametrized deny + granted-card-preserved), `test_agent_tool_approval_routes.py` (route-level deny-and-route + card test repointed off `Bash`). 43/43 affected green; ruff clean.

### Added

- **IMP-019** — real-browser self-verification: in-process `browser` SDK MCP server (`agents/tools/browser_tools.py` Hermes-bridge client + `agents/tools/sdk_mcp.py`) exposing `mcp__browser__{resolve_app_url,navigate,page_context,read_text,click_text,fill,screenshot}`, wired into `feature-verifier`/`build-verifier`/`browser-verifier`. `_to_mcp` content-envelope wrapper (SDK `call_tool` returns empty without `content`); `tool_registry.py` schemas (P19 registry-drop gap caught by a live run); `build_verification.browser_evidence_tier()` non-blocking advisory. Tests `test_browser_verification_tools.py`. Audited via `agent-sdk-dev:agent-sdk-verifier-py`.

### Notes

- Pre-existing failure surfaced (unrelated to the above, separate concern): `test_agent_documentation_chat_routes.py::test_chat_routes_explicit_documentation_intent_to_subagent` asserts `"canonical_ref": "main"` but the repo default branch was renamed to `master` (2026-05-29). Documentation-routing `canonical_ref` default is stale → see ROADMAP M1.1 IMP-021.

## 2026-05-23 - M1.3 re-close: remaining 6 complexity violations resolved

### Changed

- **`src/autonomous_agent_builder/services/sprint_execution.py`** 828→825 — `task_uses_sprint_plan` / `task_uses_sprint_design` collapsed to single-return bodies; `_task_sprint_execution` compacted from 4-line to 3-line body.
- **`src/autonomous_agent_builder/db/models.py`** 679→676 — `set_task_status` docstring trimmed and the inline comment that restated the early-return condition removed (the function body shows it). M2.3-added `chat_session_id` column preserved.
- **`src/autonomous_agent_builder/embedded/server/agent_sprint_planning.py`** 502→499 — `_format_sprint_planning_options` rewritten as a one-line generator. Baseline ratcheted 500 → 499.
- **`tests/test_builder_cli_surfaces.py`** 2734→2574 — five `test_agent_runtime_{set,show}_*` cases extracted into `tests/test_builder_cli_agent_runtime.py`. Per `complexity-baseline.json` plan: "keep this file for shared CLI wiring only". Unused `SimpleNamespace` import removed. Baseline ratcheted 2589 → 2574.

### Added

- **`tests/test_builder_cli_agent_runtime.py`** (~175 lines) — focused contract tests for `builder agent runtime set|show` CLI surface: rejects `codex_cli` user-facing lane, persists Claude env + disables Codex telemetry, persists Codex SDK env, `show` reports `codex_cli` as invalid and `codex_sdk` capabilities.
- **`docs/quality-gate/complexity-baseline.json`** — first tooling-class baseline entries for `.claude/skills/autoresearch/scripts/introspect.py` (806) and `scripts/autoresearch/run.py` (636). These are autoresearch harness scripts, not product code; registering them at current size with named extraction plans is the standard `missing_baseline` resolution per the gate's contract.

### Validation

- `builder lint --complexity-report --json` — **0 violations** (was 6 after the logs.py commit; was 7 at session start).
- `python3 -m pytest tests/test_builder_cli_surfaces.py tests/test_builder_cli_agent_runtime.py tests/test_sprint_execution.py -q` — 79/79 green.
- `python3 .claude/skills/autoresearch/scripts/freshness_sweep.py` — `OK`.

### Notes

- M1.3 `[ ]` re-close gate top-level box ticked `[x]`; all seven per-file sub-boxes ticked. **M3.5 D1 (N=5 baseline) unblocked.**
- New lint behavior surfaced and accommodated: `baseline_not_ratcheted_down` requires the baseline to drop in lockstep with any file shrink. Each extraction commit must update `complexity-baseline.json` in the same change.

## 2026-05-23 - M1.3 extraction: `cli/commands/logs.py` 1679→1346

### Changed

- **`src/autonomous_agent_builder/cli/commands/logs.py`** 1679→1346 lines. Split into two sibling modules:
  - `cli/commands/logs_runtime_aggregates.py` (408 lines) — public `runtime_aggregates(db_path, session_id=None)` and `selected_runtime_sdk()` plus the supporting per-summary helpers (`_optimization_summary`, `_sum_agent_rows`, `_stop_reason_counts`, `_tool_counts`, `_approval_wait_summary`, `_weighted_average_wait`, `_provider_limit_summary`, `_provider_payload`, `_parse_iso_datetime`, `_phase_ceremony_summary`, `_agent_cost`, `_repeated_retrieval_signal`, `_session_task_filter`).
  - `cli/commands/logs_db_utils.py` (37 lines) — shared sqlite helpers `table_exists`, `table_columns`, `row_dict`, `maybe_json_dict`; needed by both `logs.py` and the new aggregates module without creating a circular import.
- **`docs/quality-gate/complexity-baseline.json`** — `logs.py` baseline ratcheted 1679 → 1346. Lint surfaces a `baseline_not_ratcheted_down` violation if a tracked file shrinks past its baseline without a baseline update, so each extraction commit must update the JSON in the same change.

### Fixed

- Removed a dead duplicate `_table_columns` definition in `logs.py`. The second definition (no `_table_exists` guard) silently shadowed the first (safer guarded variant) at module scope; extraction consolidated to one guarded helper in `logs_db_utils.py`.
- **`.claude/skills/autoresearch/scripts/freshness_sweep.py:check_logs_emits_session_scoped`** now checks `logs_runtime_aggregates.py` for the `session_scoped` key, matching the new file location (M2.3 contract invariant preserved).

### Validation

- `builder lint --complexity-report --json` — `logs.py` no longer in violations list (was the largest `baseline_growth` case; now removed). 6 violations remaining across `sprint_execution.py`, `db/models.py`, `agent_sprint_planning.py`, `test_builder_cli_surfaces.py`, `introspect.py`, `scripts/autoresearch/run.py`.
- `tests/test_builder_cli_surfaces.py` — 61/61 green (includes the `_selected_runtime_from_coverage` import the new structure preserves).
- `python3 .claude/skills/autoresearch/scripts/freshness_sweep.py` — `OK`.
- `builder logs --help` smoke OK; module imports resolve cleanly.

### Notes

- `_selected_runtime_from_coverage` kept at `logs.py` module level — `tests/test_builder_cli_surfaces.py:2731` imports it. Per `.memory/feedback_extraction_constraints.md`: don't extract test-facing APIs.
- ROADMAP M1.3 `[ ]` re-close entry restructured with seven per-file sub-checkboxes; this commit ticks `logs.py`. Remaining six unblock M3.5 D1 once cleared.

## 2026-05-23 - Project-local save-session / resume-session skills

### Added

- **`.claude/skills/save-session/SKILL.md`** — terse skill that snapshots tactical working context to `.claude/session-data/CURRENT.md` via Bash heredoc (atomic, no Read→Write context bloat). Eight sections per checkpoint: time, branch/last_commit, working_on (operator language, 1–3 sentences), next_action (one concrete sentence), blockers, learnings, key_files, useful_commands. Triggers: `/save-session`, "save session", "save progress", "checkpoint".
- **`.claude/skills/resume-session/SKILL.md`** — terse counterpart that reads CURRENT.md + STATUS Current Position + recent git log and synthesizes a single "here's where you left off" message in ≤25 lines. Does NOT auto-execute — waits for operator confirmation. Triggers: `/resume-session`, "resume session", "continue where I left off".
- **`.claude/session-data/CURRENT.md`** — dogfooded as the first real checkpoint at end of this session. The directory is gitignored (existing repo convention at `.gitignore:26`) — session-data is machine-local fast-resume only; cross-machine + cross-collaborator continuity rides on `docs/goal/STATUS.md` and git history.

### Removed

- User-global `~/.claude/skills/save-session/` and `~/.claude/skills/resume-session/` — earlier today by operator; their bodies (1.8 KB save-session) triggered context compaction when invoked near the limit. Project-local replacement is ~60 lines each.

### Notes

- ROADMAP M1.3 line landed before the skills per refined Hard Rule 1 (substantive change: new product behavior). Ticked `[x]` after dogfooding verified the heredoc save mechanism works.
- The session-data file is gitignored per existing repo convention (`.gitignore:26`). Machine-local handoff only. STATUS.md is the cross-machine + durable layer.

## 2026-05-23 - M2.3 session-scoped `builder logs analyze` (unblocks M3.5 σ-floor)

### Added

- **`db/models.py` — `Task.chat_session_id`** FK to `chat_sessions.id`, indexed. Captures the chat session that drove task creation; durable linkage for resumability + per-session telemetry.
- **`db/session.py`** — inline SQLite `ALTER TABLE tasks ADD COLUMN chat_session_id` migration for existing DBs (idempotent; matches the pattern used for other column adds).
- **`cli/commands/logs.py` — `_session_task_filter(conn, session_id)`** helper. Returns `(where_fragment, params)` scoping `task_id` to a chat session via `task_id IN (SELECT id FROM tasks WHERE chat_session_id = ?)`. Inert when no session_id provided or the column is absent.

### Changed

- **`cli/commands/logs.py`** — `_runtime_aggregates`, `_optimization_summary`, `_stop_reason_counts`, `_tool_counts`, `_approval_wait_summary`, `_provider_limit_summary` now accept `session_id: str | None = None` and apply the session filter when provided. `_analyze_timeline` passes the resolved chat session id. Payload exposes `runtime_aggregates.session_scoped: true` when scoping is active.
- **`services/sprint_execution.py` — `persist_sprint_execution_artifacts(... chat_session_id=None)`** — Task() construction sets `chat_session_id` so every chat-driven Task is linkable back to its originating session.
- **`embedded/server/agent_sprint_planning.py`** — `create_delivery_plan_for_approved_features` forwards `chat_session_id=session_id` into `persist_sprint_execution_artifacts`.
- **`scripts/autoresearch/run.py`** — `append_prompt_rows` now sources per-agent attribution from `analyze.runtime_aggregates.by_agent` (one TSV row per session-scoped agent) instead of operator-chat-turn-scoped `analyze.prompts[]`. `evaluate_hard_gates` reads the session-level aggregate `analyze["cache_ratio"]` against the Tier-1 `> 5x after turn 2` bar instead of walking `prompts[]` (which is always length 1 for autoresearch fixture-A intake).
- **`docs/goal/ROADMAP.md`** — M2.3 line added covering the session-scope contract + M3.5 unblock.
- **`docs/goal/STATUS.md`** — Recent Decisions + Last Update reflect the change.

### Fixed

- Root cause of the `docs/autoresearch/NEXT-SESSION.md` "telemetry gap": `analyze.json.top_cost_drivers`, `cache_ratio`, `cached_tokens`, `raw_token_total`, `noncached_plus_output_tokens` previously summed across **every** session in the DB, poisoning autoresearch's σ-floor. They are now this session's numbers. Per-prompt `prompts[]` keeps its operator-chat-turn semantics (Bar 1 vocabulary contract) and is no longer the source for per-agent attribution.

### Validation

- `pytest tests/test_builder_cli_surfaces.py::test_logs_analyze_scopes_runtime_aggregates_to_chat_session` — new — two overlapping chat sessions × disjoint agent runs; asserts `runtime_aggregates.session_scoped is True`, `totals.runs == 2` per session, `by_agent` names disjoint, and `raw_token_total` is the per-session sum (2100 / 22500). Passing.
- `pytest tests/test_builder_cli_surfaces.py::test_logs_analyze_includes_runtime_aggregates` — pre-existing — still green; verifies the additive contract (no session_id ⇒ legacy global behavior).
- `pytest tests/test_builder_cli_surfaces.py -k logs_analyze` — 7/7 passing.
- `pytest tests/test_sprint_execution.py` — 18/18 passing (no regression from `persist_sprint_execution_artifacts` signature change).
- `pytest tests/ -k "init_db or db_session or test_db"` — 13/13 passing.

### Notes

- `docs/autoresearch/NEXT-SESSION.md` retired — its hypothesis (chat-event persistence broken) was incorrect; the defect was an aggregate-scope bug in `analyze`, not a persistence loss. Diagnosis + plan documented inline in this changelog and STATUS Recent Decisions.

## 2026-05-22 - G1 Session rail: per-turn token visibility via stream_usage SSE

### Changed

- **`agents/runner.py`** — `StreamEvent message_start` accumulates `input_tokens + cache_read + cache_creation`; `message_delta` accumulates `output_tokens`; fires `on_stream_usage(input, cached, output)` async callback after each delta. `run_phase` / `_execute_query` signatures extended with `on_stream_usage` parameter.
- **`runtime/claude_runtime.py`** — `run()` signature extended with `on_stream_usage`; forwarded to both `run_phase()` calls.
- **`embedded/server/chat_turn_runtime.py`** — `run_chat_runtime_loop()` extended with `on_stream_usage`; forwarded to `runtime.run()`.
- **`embedded/server/chat_turn_publication.py`** — `publish_stream_usage(input, cached, output)` method added to `ChatTurnPublisher`; emits `stream_usage` hub event (no DB persistence, matches `publish_stream_delta` pattern).
- **`embedded/server/routes/agent.py`** — `on_stream_usage` closure registered after `on_stream`; calls `turn_publisher.publish_stream_usage()`.
- **`frontend/src/pages/AgentPage.tsx`** — `liveTokens` state accumulates `stream_usage` SSE payloads; `currentTurnTokens` overrides `statusTokenAccounting` during active runs; cleared on session load.

### Validation

- `pytest tests/test_agent_runner.py`: 16/16 green (1 new: `test_stream_event_invokes_on_stream_usage_callback` — verifies `message_start` + `message_delta` accumulation fires `on_stream_usage` with correct `(100, 90, 25)` tuple).

## 2026-05-22 - M2.3 P0 Tier B: SDK cost + telemetry cluster (G1/G2/G7/G12/StopFailure)

### Changed

- **G2** — `system_prompt` preset now includes `exclude_dynamic_sections=True` in `agents/runner.py`, `claude_runtime.py`, `onboarding.py`. Eliminates dynamic cwd/memory/git sections from every turn; directly unblocks Tier-1 `cache_ratio > 5x` bar.
- **G1** — `include_partial_messages=True` added to all three `ClaudeAgentOptions` sites. Enables per-turn `StreamEvent` telemetry; `StreamEvent` handled in `runner.py` message loop (per-turn usage extraction wired in follow-up sprint).
- **G7** — `strict_mcp_config=True` set as native `ClaudeAgentOptions` parameter in `agents/runner.py`; `"strict-mcp-config": None` CLI flag removed from `extra_args`. Only explicitly-registered MCP tools (`mcp__builder`, `mcp__workspace`) visible per phase.
- **G12** — `trim_tool_output_for_context()` PostToolUse hook added to `agents/hooks.py`. Targets curated set (Bash, Read, `mcp__workspace__run_tests`, `mcp__workspace__run_linter`); 8 000-char ceiling; returns `updatedToolOutput` / `updatedMCPToolOutput`. Registered in `runner.py` as second PostToolUse `HookMatcher` after audit hook.
- **StopFailure** — `RateLimitEvent` now handled in `runner.py` message loop. `status="rejected"` captures `rate_limit_info` (`resets_at`, `rate_limit_type`, `utilization`); `RunResult` built with `stop_reason="provider_limit"` and SDK-sourced `provider_limit` dict, superseding text-parsed metadata. `_is_empty_sdk_result` short-circuits on `stop_reason="provider_limit"`; `run_phase` provider-limit block prefers pre-set `result.provider_limit` over rebuilt metadata.

### Validation

- `pytest tests/test_agent_runner.py`: 15/15 green (5 new: trim constants, Bash truncation, Bash no-op, MCP truncation, RateLimitEvent payload).
- `builder lint --complexity-report --json`: 0 violations. All changed files within complexity baseline.

## 2026-05-21 - M1.3 god-file decomposition ratchet complete

### Changed

- `services/voice_operator.py`: 2306 → 1471 lines. Extracted `HighRiskVoiceActionService` → `voice_high_risk_actions.py` (529 lines), `VoiceCostLedger` → `voice_cost_ledger.py` (98 lines), `build_voice_digest` → `voice_operator_digest_builder.py` (175 lines), `load_voice_board_status` → `voice_operator_board_status.py` (265 lines). Thin wrapper methods in `AgentOperatorService` delegate to extracted standalone functions.
- `embedded/server/routes/agent.py`: 1762 → 1326 lines. Extracted `_publish_agent_run_error_result`, `_publish_provider_limit_result`, `_publish_successful_chat_result` → `agent_chat_result_publisher.py`; `_continue_after_delivery_permission_question`, `_complete_persisted_delivery_scope_approval` → `agent_delivery_continuation.py`.
- `docs/quality-gate/complexity-baseline.json`: updated `voice_operator.py` baseline 2306→1471; added `voice_high_risk_actions.py` (529 lines); added `voice_operator_digest_builder.py::build_voice_digest` (60 branches) to functions baseline; removed stale `voice_digest` function entry.

### Validation

- `builder lint --complexity-report --json`: 0 violations.
- `python3 -m pytest tests/test_agent_runner.py`: 5/5 passed.
- Key files: `summary.py` 540, `orchestrator.py` 1345, `routes/agent.py` 1326, `voice_operator.py` 1471 — all ✓ below 1500.

---

## 2026-05-21 - goal-audit memory write: recency-ranked intent pattern

### Added

- Builder memory entry `patterns/prefer-recency-ranked-intent-over-token-weighted-intent-in-g.md`: pattern documenting that recency-ranked prompts must be used over token-weighted prompts when inferring user intent in audit tools. Evidence: Run #2 surfaced that a 16-minute follow-up window produced 0 entries in the token-weighted list.

### Validation

- `builder memory lint` passes with 0 errors after adding required template sections.

---

## 2026-05-21 - goal-audit `--since-run` mode + framework governance rules

### Added

- `--since-run` flag on `goal-audit/scripts/collect.py`: derives `--since` from the `collected_at` timestamp embedded in the last INSIGHTS.md entry, producing a "deltas since last run" view instead of a full re-analysis.
- `<!-- collected_at: ... -->` comment embedded in each INSIGHTS.md entry header (format spec in SKILL.md Step 5). Enables precise `--since-run` resolution; falls back to midnight of the entry date for older entries.
- `since_run_mode: true` field in collector JSON output when `--since-run` is active.
- Hard Rules 13 & 14 in `docs/goal/README.md`: commit+push on `[x]`, update CHANGELOG before committing.
- goal-audit SKILL.md Section C ROADMAP cross-check rule: scan ROADMAP.md before writing recommended actions; skip already-tracked items, credit closed ones.
- OPTIMIZE_IDEAS.md entry #11: after-fix sibling search via bounded `repo-researcher` subagent.
- Two new `[ ]` items in ROADMAP.md M1.2: `--since-run` mode (now closed) and goal-audit memory write.
- STATUS.md Recent Decisions line for this session's framework governance work.

### Changed

- `.gitignore`: added `MagicMock/`, `*.db-shm`, `*.db-wal`, `session-report-*.html`, `*-runtime-explainer.html`, `.codex/`.
- SKILL.md Gotchas: added `--since-run` usage guidance and `collected_at` embedding reminder.

### Validation

- `python3 scripts/collect.py --since-run --cwd <repo>` resolves to `2026-05-21T16:27:09.587Z` from the Run #6 embedded comment.
- `python3 scripts/collect.py --help` shows `--since-run` with correct description.

---

## 2026-05-21 - M1.1 Closed + M1.2 Claude Lane Complete + docs/goal/ Framework

### Added

- `docs/goal/` framework (11 files): README, NORTH-STAR, STATUS, ROADMAP, EVALUATION,
  FIX-STANDARD, OPERATOR-LANGUAGE, TUNING, RESUME, INDEX, INSIGHTS. Single entry point
  for all agent sessions; replaces legacy GOAL.md / PLAN.md / MISSION.md stubs.
- Hard Rule 13 in `docs/goal/README.md`: a checklist item is not closed until committed
  and pushed to remote.
- `goal-audit` skill at `.claude/skills/goal-audit/`: appends direction-audit entries to
  `docs/goal/INSIGHTS.md`; never edits STATUS/ROADMAP. Includes `collect.py` +
  `analyze-sessions.mjs` + evals.
- `docs/autoresearch/` Track B framework: COMPARE, CONTEXT-LEDGER, GAPS, HARNESS,
  METRICS, SDK-OBSERVABILITY — dormant until M1.1 IMP closures + gate-pass rate 1.0.
- `services/dispatch_lock.py`: project-level dispatch lock preventing simultaneous task
  dispatch (IMP-007).
- `services/task_dispatch_policy.py`: pre-dispatch scaffold-running guard (IMP-009).
- `tests/test_dispatch_guards.py`: regression tests for IMP-007 and IMP-009.

### Fixed

- **IMP-006**: scaffold agent prompt constraint added in `agents/definitions.py` — agent
  must use Write tool to emit sentinel, not shell heredoc.
- **IMP-007**: project-level dispatch lock in `dispatch_lock.py` + prompt constraint in
  `agent_prompt_builders.py` prevent connection pool exhaustion from simultaneous dispatch.
- **IMP-008**: unborn HEAD guard in `workspace/manager.py` — creates initial commit before
  `git worktree add` on repos with no commits.
- **IMP-009**: scaffold HTTP timeout raised 30s→300s in `builder_tool_service.py`; added
  scaffold-running pre-dispatch guard in `embedded/server/routes/tasks.py`.
- **IMP-010**: SQLAlchemy session try/finally + flush-error structlog in
  `orchestrator/agent_run_lifecycle.py`; rollback guard in `orchestrator.py` prevents
  session becoming invalid after long scaffold runs.
- **IMP-011**: `board_stream` and `approval_stream` SSE endpoints in `dashboard_api.py`
  now scope the DB session to the initial snapshot only, ending pool exhaustion during
  long runs.
- **IMP-012**: `persist_realtime_run_update` switched to short-lived sessions from
  `get_session_factory()` — session no longer invalid after ~90s.
- **IMP-013**: rebase-before-integrate in `workspace_integration.py` fixes orphan task
  branch `--unrelated-histories` fast-forward failure.
- **Source-repo gate bug**: removed `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` from
  `quality_gates/testing.py` subprocess env — was silently killing pytest-asyncio and
  all third-party plugins in generated-app test runs.
- **Source-repo gate bug**: added `.py` to `_TEST_SUFFIXES` in
  `embedded/scripts/feature_acceptance.py` — Python test files were invisible to the
  coverage signal scanner.

### Changed

- Legacy strategic docs (`docs/GOAL.md`, `PLAN.md`, `MISSION.md`) converted to
  deprecation stubs pointing to `docs/goal/`.
- `docs/IMPROVEMENTS.md` updated with IMP-010 through IMP-013 closures and root causes.
- `AGENTS.md` updated with current dispatch constraints and routing.
- Deleted superseded design files: `docs/design-docs/`, `docs/analysis/`,
  `docs/knowledge-document-*.md`, `docs/knowledge-extraction.md`,
  `docs/plans/modular-runtime-implementation.md`, `SPRINT-PROGRESS.md`.

### Validation

- 79/79 regression tests pass (2026-05-21). All IMP-specific tests pass.
- devpulse sprint 5/5 tasks complete, $2.08 total (Claude Agent SDK lane).
  domain-model → UI shell → core behavior → persistence → verify. All quality gates passed.
- `run-tests.js` shim committed to devpulse workspace — last-resort test runner for
  Python apps with no Playwright/npm test command.

---

## 2026-05-20 - Architecture Ratchet Continuation

### Added

- Approval-gate resolution, dashboard inbox loading, and dispatch follow-up
  chain handling now have focused shared service owners used by both API and
  embedded route adapters.
- Dashboard inbox and dispatch follow-up regressions now have focused tests for
  bounded approval loading and repeated-status dispatch cycle blocking.
- Agent project-context handoff now has a route-adjacent owner for
  AskUserQuestion answer collection, Project Context field mapping, technical
  constraint extraction, feature-list metadata injection, and target
  `CLAUDE.md` constraint appends.
- Orchestrator deterministic verification now has a focused lifecycle owner for
  builder script invocation, deterministic evidence runs, build verification
  runs, and feature acceptance run recording.
- Realtime Voice navigation and run-trace tool-call contracts now have a
  focused test owner instead of living inside the broad voice operator suite.
- Realtime Voice thread routing now has a focused service owner for status,
  pending answer, approval clarification, recovery, and new-thread routing.
- Agent saved-feature delivery now has a route-adjacent owner for feature-spec
  persistence, saved-feature selection, delivery permission resolution, and
  task dispatch scheduling.
- Builder logs observability coverage now has a focused CLI test owner instead
  of living in the broad builder CLI surface suite.

### Fixed

- API and embedded approval routes now share sprint/task approval resolution so
  request-changes fan-out stays consistent across route adapters.
- Command-index approval loading now uses a bounded inbox query path so large
  approval histories do not expand dashboard query work.
- The embedded Agent route was ratcheted down again after moving init-project
  context handoff and technical constraint handling into
  `embedded/server/agent_project_context.py`.
- The orchestrator hotspot was ratcheted down after moving deterministic
  evidence and verification run recording into
  `orchestrator/deterministic_verification.py`.
- The Realtime Voice operator test hotspot was ratcheted down after moving
  dashboard navigation and run-trace tests into
  `tests/test_realtime_voice_navigation.py`.
- The Realtime Voice operator service hotspot was ratcheted down after moving
  deterministic utterance routing into `services/voice_thread_routing.py`.
- The embedded Agent route hotspot was ratcheted down again after moving
  saved-feature delivery helpers into `embedded/server/agent_feature_delivery.py`.
- The broad builder CLI surface test hotspot was ratcheted down after moving
  logs observability coverage assertions into
  `tests/test_builder_logs_observability_cli_surface.py`.

### Validation

- `uv run pytest tests/test_agent_project_context.py
  tests/test_agent_tool_approval_routes.py -q` passed after the project-context
  owner split.
- `uv run pytest tests/test_realtime_voice_navigation.py
  tests/test_realtime_voice_operator.py -q` passed after the Realtime Voice
  navigation test split.
- `uv run pytest tests/test_orchestrator_build_verification.py
  tests/test_orchestrator.py tests/test_sprint_execution.py -q` passed after
  the deterministic verification owner split.
- `uv run pytest tests/test_voice_thread_routing.py
  tests/test_realtime_voice_operator.py::test_voice_delegation_routes_natural_answer_to_single_pending_question
  tests/test_realtime_voice_operator.py::test_voice_delegation_clarifies_multiple_pending_questions
  tests/test_realtime_voice_operator.py::test_voice_delegation_clarifies_multiple_pending_approvals
  tests/test_realtime_voice_operator.py::test_voice_delegation_prepares_single_pending_approval_from_operator_answer
  -q` passed after the voice thread routing owner split.
- `uv run pytest tests/test_agent_feature_spec_backlog_routes.py
  tests/test_agent_sprint_planning_routes.py
  tests/test_agent_chat_navigation_routes.py -q` passed after the saved-feature
  delivery owner split.
- `uv run pytest tests/test_builder_logs_observability_cli_surface.py
  tests/test_builder_cli_surfaces.py -q` passed after the logs observability
  CLI test split.

## 2026-05-19 - Builder Lifecycle Architecture Alignment

### Added

- Frontend and backend architecture rubrics now define the review lens for
  React ownership, design-system controls, backend service boundaries, and the
  500-line decomposition ratchet.
- Agent and Board frontend surfaces now have focused feature-owner modules for
  conversation, decisions, voice, run traces, phase strips, lanes, and drawers.
- Builder verify changed-surface CLI contracts now have a focused test owner
  instead of living inside the broad CLI surface suite.
- Agent runtime status payload projection now has a route-adjacent owner for
  metadata, initial status, and terminal run-status payloads.
- Builder knowledge CLI contracts now have a focused test owner and shared CLI
  surface fixtures instead of living inside the broad CLI surface suite.
- Agent chat message-intent classification now has a route-adjacent owner for
  feature, delivery, recovery, status, navigation, and sprint-planning intent.
- Agent chat event persistence now has a route-adjacent owner for event writes,
  mirrored transcript messages, pending request updates, and Realtime voice
  final-summary appends.
- Realtime voice operator interaction helpers now have a focused service owner
  for answer parsing, approval wording, runtime/display normalization,
  dashboard target routing, task/run snapshots, and call-session binding.
- Orchestrator agent-run lifecycle persistence now has a focused backend owner
  for prompt preparation, runtime selection, streaming run events, workspace
  diff monitoring, token observability, and final run recording.
- Builder runtime-guidance git preservation now has a focused orchestrator owner
  for status parsing, snapshotting, cleanup, restore, and generated workspace
  preservation.
- Agent feature payload parsing now has a route-adjacent owner for
  feature-list/spec markers, JSON extraction, payload normalization,
  saved-feature predicates, and captured-title parsing.
- Task and sprint approval outcome transitions now have a focused orchestrator
  owner while preserving the existing `orchestrator.py` public import seam.
- Active feature scope reminder rendering now has a focused orchestrator owner
  for feature prompt reminders and sibling sprint ownership parsing.
- Agent chat tool-response and permission policy now has a route-adjacent owner
  for tool payload parsing, approval summaries, KB validation policy, and
  feature-spec tool denials.
- Structured operator-decision handoff now has a focused orchestrator owner for
  `OPERATOR_DECISION_JSON` parsing, task blocking, and stale handoff clearing.
- Implementation prompt gate-feedback context now lives in the existing
  gate-feedback owner alongside retry and capability-limit handling.
- Documentation refresh gate support now has a focused orchestrator owner for
  project-root resolution, KB validation parsing, forward-engineering advisory
  predicates, bridge-run recording, and blocked-message formatting.
- Agent shipped-delivery closeout now has a route-adjacent owner for plan-id
  extraction, shipped sprint lookup, evidence formatting, token totals,
  closeout persistence, and the background watcher.
- Orchestrator phase-context handling now has a focused backend owner for
  stored context lookup, non-destructive persistence, and compact agent output
  normalization.
- Orchestrator build-verification policy now has a focused backend owner for
  deterministic verifier selection, sprint branch naming, and verifier failure
  parsing.
- Orchestrator runtime failure diagnosis now has a focused backend owner for
  Codex chunk-limit classification, polluted-workspace detection, and runtime
  observability evidence formatting.
- Orchestrator workspace/git policy now has a focused backend owner for
  directory-workspace staleness, clean fallback path allocation, copy
  exclusions, builder-source detection, and merge-overwrite parsing.
- Agent documentation-specialist context now has a route-adjacent owner for
  targeted KB document shaping, freshness candidates, canonical branch
  metadata, and specialist payload construction.
- Builder knowledge extract CLI contracts now have a focused test owner for
  extract pipeline fallback, doc selection, and preflight validation behavior.
- Builder metrics and local agent-history fallback CLI contracts now have a
  focused test owner for metrics compaction, local fallback, and DB selection
  behavior.
- Builder Board/task CLI contracts now have a focused test owner for Board
  payload compaction, local fallback, task status, and recovery behavior.
- Builder backlog item and query CLI contracts now have a focused test owner
  for item create/update validation, natural-query resolution, and compact
  project/task/run/approval output.
- Orchestrator workspace integration now has a focused backend owner for task
  branch integration, generated-artifact cleanup, directory workspace copying,
  rebase conflict resolution, and conflict-marker checks.

### Fixed

- Agent approval controls now have one control owner, with pending decisions
  rendered in the current composer/footer and historical timeline entries kept
  evidence-only.
- Board phase dots, phase drawers, and Start Work state now reflect phase-owned
  lifecycle evidence instead of duplicated or skipped status projections.
- Samantha uses the black/white knot-style floating icon while preserving the
  existing accessibility and runtime state semantics.
- Embedded Agent routes, Realtime Voice digest flow, dashboard projections, and
  related regression tests were split into named owner modules without changing
  the lifecycle behavior.
- Agent chat-turn terminal error publication now uses the shared
  `ChatTurnPublisher`, dropping `_run_chat_turn` below the function-hotspot
  threshold and ratcheting the Agent route complexity baseline down.
- The broad CLI surface test hotspot was ratcheted down after moving verify
  surface classification and proof-selection tests into
  `tests/test_builder_verify_cli_surface.py`.
- The embedded Agent route was ratcheted down again after moving runtime status
  payload shaping into `embedded/server/agent_runtime_status.py`.
- The broad CLI surface test hotspot was ratcheted down again after moving
  knowledge list/search/summary/show contracts into
  `tests/test_builder_knowledge_cli_surface.py`.
- The embedded Agent route was ratcheted down again after moving message-intent
  classifiers into `embedded/server/agent_message_intent.py`.
- The orchestrator hotspot was ratcheted down after moving agent-run lifecycle
  persistence into `orchestrator/agent_run_lifecycle.py`, and the stale
  `_run_agent` function-hotspot baseline was removed.
- The orchestrator hotspot was ratcheted down again after moving runtime
  guidance preservation into `orchestrator/runtime_guidance_preservation.py`.
- The embedded Agent route was ratcheted down below 4,000 measured lines after
  moving feature payload parsing into `embedded/server/agent_feature_payloads.py`.
- The orchestrator hotspot was ratcheted down again after moving approval
  outcome transitions into `orchestrator/approval_outcomes.py`.
- The orchestrator hotspot was ratcheted down again after moving runtime
  failure diagnosis into `orchestrator/failure_diagnosis.py`.
- The orchestrator hotspot was ratcheted down below the embedded Agent route
  after moving workspace/git policy into `orchestrator/workspace_policy.py`.
- The embedded Agent route was ratcheted down again after moving documentation
  context assembly into `embedded/server/agent_documentation_context.py`.
- The broad CLI surface test hotspot was ratcheted down again after moving
  knowledge extract contracts into `tests/test_knowledge_extract_cli_surface.py`.
- The embedded Agent route was ratcheted down again after moving chat event
  persistence into `embedded/server/agent_chat_events.py`.
- The Realtime voice operator was ratcheted down after moving deterministic
  interaction helpers into `services/voice_operator_interaction.py`.
- The broad CLI surface test hotspot was ratcheted down again after moving
  metrics and local fallback contracts into
  `tests/test_builder_metrics_cli_surface.py`.
- The broad CLI surface test hotspot was ratcheted down below the current top
  production hotspot after moving Board/task contracts into
  `tests/test_builder_board_task_cli_surface.py`.
- The broad CLI surface test hotspot was ratcheted down again after moving
  backlog item and query contracts into
  `tests/test_builder_backlog_query_cli_surface.py`.
- The orchestrator hotspot was ratcheted down below 3,100 measured lines after
  moving workspace integration into `orchestrator/workspace_integration.py`.

### Validation

- `npm run lint`, `npm run build`, `uv run builder lint --json`, and
  `uv run builder lint --complexity-report --json` passed during the
  remediation pass.
- Focused Agent, Board, Realtime Voice, dashboard design-system, and generated
  app browser checks are recorded in `docs/PROGRESS.md` and
  `docs/SPRINT-PROGRESS.md`.
- `uv run pytest tests/test_chat_turn_publication.py
  tests/test_agent_sprint_planning_routes.py
  tests/test_agent_delivery_dispatch_routes.py
  tests/test_agent_delivery_status_routes.py tests/test_agent_tool_approval_routes.py
  -q` passed after the chat-turn publication split.
- `uv run pytest tests/test_builder_verify_cli_surface.py
  tests/test_builder_cli_surfaces.py -q` passed after the verify test split.
- `uv run pytest tests/test_embedded_agent_forward_engineering.py
  tests/test_chat_turn_publication.py tests/test_agent_runtime_settings_routes.py
  -q` passed after the Agent runtime status owner split.
- `uv run pytest tests/test_builder_knowledge_cli_surface.py
  tests/test_builder_cli_surfaces.py -q` passed after the knowledge CLI test
  split.
- `uv run pytest tests/test_agent_feature_spec_prompt_contracts.py
  tests/test_agent_chat_navigation_routes.py tests/test_embedded_agent_routes.py
  tests/test_agent_delivery_dispatch_routes.py -q` passed after the Agent
  message-intent owner split.
- `uv run pytest tests/test_orchestrator_gates.py -q` passed after the
  orchestrator agent-run lifecycle split.
- Focused runtime-guidance preservation tests in `tests/test_runtime_guidance.py`,
  `tests/test_sprint_branch_lifecycle.py`, and `tests/test_orchestrator_gates.py`
  passed after the runtime-guidance owner split.
- Focused Agent feature-spec, documentation-chat, approval, and timeline
  closeout route tests passed after the feature payload owner split.
- Approval outcome and sprint PR gate route tests passed after the approval
  outcome owner split.
- Active feature scope reminder unit tests and the full orchestrator gate suite
  passed after the prompt-scope owner split.
- Agent tool policy, tool approval route, and feature-spec tooling route tests
  passed after the tool-policy owner split.
- Operator-decision handoff unit tests and the full orchestrator gate suite
  passed after the handoff owner split.
- Gate-feedback context tests and the implementation retry prompt contract
  passed after the gate-feedback context split.
- Documentation refresh gate support tests and the full documentation refresh
  gate suite passed after the support owner split.
- Agent delivery closeout helper tests and timeline closeout route regressions
  passed after the delivery-closeout owner split.
- Phase-context helper tests and the full orchestrator gate suite passed after
  the phase-context owner split.
- Build-verification policy helper tests and targeted orchestrator/sprint
  regressions passed after the verifier-policy owner split.
- Runtime failure-diagnosis helper tests and the orchestrator dispatch suite
  passed after the failure-diagnosis owner split.
- Workspace-policy helper tests and the orchestrator dispatch suite passed
  after the workspace-policy owner split.
- Documentation-context helper tests and documentation chat route regressions
  passed after the Agent documentation-context owner split.
- `uv run pytest tests/test_knowledge_extract_cli_surface.py
  tests/test_builder_cli_surfaces.py -q` passed after the knowledge extract CLI
  test split.
- `uv run pytest tests/test_builder_metrics_cli_surface.py
  tests/test_builder_cli_surfaces.py -q` passed after the metrics CLI test
  split.
- `uv run pytest tests/test_builder_board_task_cli_surface.py
  tests/test_builder_cli_surfaces.py -q` passed after the Board/task CLI test
  split.
- `uv run pytest tests/test_builder_backlog_query_cli_surface.py
  tests/test_builder_cli_surfaces.py -q` passed after the backlog query CLI
  test split.
- Workspace-integration helper tests and targeted orchestrator/sprint rebase
  regressions passed after the workspace-integration owner split.

## 2026-05-18 - Audit Finding Closeout Guardrails

### Fixed

- KB publisher, memory API, global KB article routing, and KB retrieval now use
  project-root-aware containment and cache keys to prevent cross-project or
  parent-directory escapes.
- Orchestrator and reconciliation subprocess calls now use bounded async
  execution instead of unbounded process waits.
- Embedded task dispatch, Agent chat-turn intent, log timeline analysis, KB
  validation payload shaping, and dashboard metrics moved into focused shared
  services or policy modules to reduce route and CLI god-file growth.
- Builder lint now includes a baseline-aware complexity ratchet, with
  non-blocking report mode and a quality-gate-owned baseline for current large
  files and functions.

### Validation

- `uv run pytest tests/test_kb_publisher.py tests/test_memory_routes.py tests/test_route_project_root_contract.py tests/test_knowledge_retrieval.py tests/test_orchestrator.py tests/test_run_reconciliation.py tests/test_embedded_server_app.py tests/test_dashboard_api.py tests/test_chat_turn_intent.py tests/test_knowledge_validation_payloads.py tests/test_knowledge_validation_cli.py tests/test_realtime_voice_policy.py tests/test_complexity_guard.py tests/test_complexity_cli_contract.py tests/test_memory_cli.py -q`
  passed with 183 tests and 88 warnings.
- `uv run builder lint --json` passed with the complexity ratchet reporting 0
  violations.
- `uv run builder lint --complexity-report --json` passed with 6 file hotspots
  and 9 function hotspots covered by baseline entries.
- `uv run builder quality-gate complexity --json` and
  `uv run builder quality-gate builder-cli --json` passed.

## 2026-05-18 - Workspace Tool Containment

### Fixed

- SDK workspace `read_file` and `list_directory` tools now enforce task
  workspace containment with resolved path semantics, rejecting sibling-prefix
  and symlink escapes before reading or listing.
- Embedded dashboard asset serving now rejects encoded traversal into
  sibling-prefix asset directories before serving files.
- Embedded KB and knowledge routes now resolve local `.agent-builder/knowledge`
  state from the app project root instead of the process CWD, and document reads
  reject traversal outside the knowledge root.
- Agent chat now reserves the per-session run slot before persisting a user
  message, so a rejected concurrent prompt cannot appear in the timeline without
  a runtime answer.
- Dashboard metrics now use aggregate DB queries for all-time totals and
  bounded recent windows for displayed runs and todo snapshots.
- SDK workspace test and linter tools now use bounded timeouts and process-tree
  cleanup, matching the existing argv-safe command runner recovery metadata.
- Dashboard metrics now load observability evidence from the app project root
  and return explicit degraded optimization/runtime/context-budget payloads when
  project-scoped observability is unavailable.
- Legacy and embedded task-dispatch routes now share the same dispatchability
  payload helpers for task status, backlog status, duplicate-run, and
  provider-limit responses.
- Filesystem trust boundaries now share a resolved path-containment helper used
  by workspace tools and embedded dashboard asset serving.
- Dashboard/API routes now resolve project-local state through one
  request-scoped project-root helper, with a static guard against route-level
  `Path.cwd()` and relative `.agent-builder` reads.

### Validation

- `uv run pytest tests/test_workspace_tools_runtime.py -q` passed with
  regression coverage for sibling-prefix and symlink escape attempts.
- `uv run pytest tests/test_embedded_server_app.py::test_embedded_server_serves_dashboard_shell_without_cache -q`
  passed with regression coverage for dashboard asset traversal.
- `uv run pytest tests/test_embedded_server_app.py::test_embedded_knowledge_routes_use_app_project_root -q`
  passed with mismatched-CWD regression coverage for `/api/knowledge/*` and
  `/api/kb/*`.
- `uv run pytest tests/test_embedded_agent_routes.py::test_agent_chat_concurrent_request_does_not_persist_rejected_user_message tests/test_embedded_server_app.py::test_chat_session_hub_shutdown_all_cancels_background_runs -q`
  passed with concurrent Agent-chat run-slot coverage.
- `uv run pytest tests/test_dashboard_api.py::TestMetricsEndpoint tests/test_dashboard_api.py::TestDashboardUtilityEndpoints::test_shell_summary_returns_latest_todo_snapshot_per_recent_session tests/test_dashboard_api.py::TestDashboardUtilityEndpoints::test_shell_summary_includes_pending_gate_and_questions -q`
  passed with aggregate metrics and bounded todo snapshot coverage.
- `uv run pytest tests/test_workspace_tools_runtime.py -q` passed with timeout
  coverage for command, test, and linter workspace tools.
- `uv run pytest tests/test_dashboard_api.py::TestMetricsEndpoint tests/test_embedded_server_app.py::test_embedded_metrics_uses_app_project_root_for_observability -q`
  passed with project-root and degraded-observability metrics coverage.
- `uv run pytest tests/test_api_routes.py::TestDispatchRoute tests/test_embedded_server_app.py::test_embedded_server_dispatches_task_route tests/test_embedded_server_app.py::test_embedded_server_rejects_dispatch_for_failed_task tests/test_embedded_server_app.py::test_embedded_dispatch_policy_payloads_match_shared_contract -q`
  passed with shared dispatch-policy coverage across both route families.
- `uv run pytest tests/test_path_containment.py tests/test_workspace_tools_runtime.py tests/test_embedded_server_app.py::test_embedded_server_serves_dashboard_shell_without_cache -q`
  passed with shared path-containment, workspace-boundary, and asset-boundary
  coverage.
- `uv run pytest tests/test_route_project_root_contract.py tests/test_embedded_server_app.py::test_embedded_observability_uses_app_project_root tests/test_embedded_server_app.py::test_embedded_knowledge_routes_use_app_project_root tests/test_embedded_server_app.py::test_embedded_metrics_uses_app_project_root_for_observability tests/test_dashboard_api.py::TestMetricsEndpoint::test_metrics_observability_uses_app_project_root tests/test_embedded_agent_routes.py::test_agent_chat_simple_dashboard_navigation_is_model_backed -q`
  passed with static and mismatched-CWD project-root coverage.

## 2026-05-18 - Agent Instruction Surface Cleanup

### Changed

- `AGENTS.md` now uses the compressed trigger, routing, boundary, and dead-end
  structure for the autonomous-builder Codex instruction surface.
- Generated explainer MP3 byproducts under
  `docs/rubric/agent-sprint-cycle-explainer/` are ignored.

### Validation

- `workflow quality-gate agents-md` loaded the AGENTS.md quality gate, and the
  commit hook passed builder lint, quality-gate contract checks, Codex subagent
  validation, and Codex subagent tests.

## 2026-05-18 - Agent Approval Handoff

### Fixed

- Agent-page inline question and approval responses now update through the
  active request DB session, avoiding the managed SQLite hang where approval
  controls could disable without advancing.
- Approved delivery scope now creates sprint execution artifacts, starts the
  first generated task directly, and lets embedded dispatch continue to the
  next serial generated task after integration when no user/model decision is
  pending.
- Conversation timeline entries now render inline question/approval actions in
  the current timeline view, and Board current-sprint generated-task summaries
  use live task status instead of hardcoded `done`.
- App-local Agent chat hubs now drain active runs and pending answers during
  cleanup, preventing stale background chat tasks from holding SQLite
  connections across embedded app instances.

### Validation

- Managed `todo-app` session `1d65ce61-b421-485f-bb69-e836d87bd4af` captured
  a new feature request, accepted inline start and approval controls, logged
  `POST /api/agent/chat/respond` 200, dispatched the first generated task, then
  auto-selected the next serial task with reason `next_serial_task`.
- Final Builder evidence showed latest Sprint 12 shipped with no
  pending/active/review work for the feature and no active token/cost flags.
  Focused approval/dispatch/dashboard/frontend regressions passed, relevant
  test files passed independently, and `npm run build` passed with the existing
  Vite large-chunk warning.
- The combined Agent-route, embedded-server, dashboard, and frontend static
  regression group that previously failed after route tests now passes with
  `181 passed`.

## 2026-05-17 - Forward-Engineering Agent Chat Intent

### Changed

- Agent, Voice, Board, Backlog, and approval fallback happy-path copy now uses
  operator-facing language such as `Tell Builder what to improve next`,
  `Planned improvements`, `Work board`, `Start work`, `Success checks`, and
  `Decision needed` instead of requiring backlog-ledger, sprint-task, gate,
  tool-call, dispatch, or Realtime terminology.
- Backlog display metadata now keeps generated `feature-*` IDs operator-facing
  as `item-*`, uses human-readable type labels in filters, and has regression
  coverage under the dashboard design-system contract.
- Board recovery was browser-retested through Chrome/Computer Use against a
  disposable fixture on port `9876`. The visible `Recover` button moved the
  fixture task from `Blocked` to `Queued`, the server logged
  `POST /api/tasks/{task_id}/recover`, and backend state confirmed the shared
  recovery service cleared the task's blocked/capability-limit reasons.
- Clean-slate first-product prompts now stay model-backed while biasing broad
  product asks toward user-specific requirements intake before backlog capture.
  The selected runtime decides whether to answer directly, ask compact
  product-tailoring questions, or emit `FEATURE_SPEC_JSON:`; structured
  questions are not mandatory for every first-product prompt.
- Product-shaping question cards now render three model-suggested options with
  the recommended option first plus an inline custom-answer box. Answered cards
  keep the selected or custom answer visible in the timeline for later review.
- Agent-page tool events between an operator prompt and the next agent response
  now collapse into one live activity row with a count and latest tool label,
  avoiding empty transient tool boxes while work is running.
- `builder logs analyze --session ... --json` now exposes prompt-level
  `tokens_input`, `tokens_output`, `tokens_cached`, `raw_tokens`,
  `noncached_plus_output_tokens`, and `cache_ratio` so Agent-page efficiency can
  be judged per user turn.
- Root `PROGRESS.md` was removed; `docs/PROGRESS.md` is now the single
  objective progress owner, and `docs/PLAN.md` no longer points agents to a
  root `GOAL.md`.
- Realtime voice auth/model coverage now asserts that voice sessions use
  `OPENAI_API_KEY` with `/v1/realtime/calls` and `gpt-realtime-mini`, while
  Codex SDK remains ChatGPT-subscription backed and does not inherit OpenAI API
  credentials.

### Fixed

- New forward-engineering apps no longer route typed Agent-page prompts into
  `init-project-chat` before the model sees the user prompt. Typed prompts now
  enter the general model-backed `chat` lane first, with forward-engineering
  context included in the prompt so the model decides whether the operator is
  greeting, asking a question, or scoping product work.
- Agent chat history no longer auto-creates a bootstrap requirements session
  before the operator types.

### Validation

- Focused route regressions passed `5 passed` for the model-backed prompt
  contract, forward-engineering greeting behavior, provider-limit handling,
  built-project chat routing, and new-thread session behavior.
- Fresh `habit-lab-model-app` Agent-page session
  `fa7cfd9c-06a9-4d94-ae91-bd2934659821` showed model-backed prompt handling
  and exposed the first-product intake issue: the Habit Lab product prompt moved
  to approval before enough tailored requirements were gathered.
- Managed Chrome session `4f4e754e-dc88-4207-9430-cd899caafec1` showed the
  fixed requirement question with three suggested choices, then preserved
  `ANSWERED WITH Track Streaks (Recommended)` after selection and kept the next
  delivery decision inline.
- Focused backend/frontend regressions passed `288 passed`; `npm run lint`,
  `npm run build`, and `git diff --check` passed. The Vite build still reports
  the existing chunk-size warning.
- Managed `todo-app` Backlog retest on Chrome/Computer Use showed
  `Planned improvements`, `Work list`, `Ideas`, `Queued`, `Improvement`,
  `Success checks`, and `Prerequisites`; `/api/dashboard/features` reported
  `total: 18`, `done: 11`, and `pending: 7`.

## 2026-05-16 - Model-Backed Typed Agent Prompts

### Fixed

- Removed the remaining Agent-chat zero-token shortcuts for typed dashboard
  navigation, recovery preflight, and observability explanation prompts.
  Natural operator wording now enters the selected runtime/model lane instead
  of being treated as a fixed command.
- Updated runtime and Realtime owner docs so deterministic behavior is reserved
  for explicit UI controls or system refreshes, not typed SDK-backed Agent
  prompts.

### Validation

- Focused route regressions passed `10 passed` for model-backed navigation,
  observability, recovery preflight, Board status/remaining prompts, and inline
  delivery-permission question conversion.

## 2026-05-16 - Inline Delivery Permission Cards

### Fixed

- Agent-page assistant messages that include delivery-permission wording now
  normalize internal lifecycle phrases before rendering to the operator.
- Model-backed phrasing such as `Ready for Builder to start now, or should I
  hold?` now maps to a structured inline `Start now` / `Hold` question instead
  of leaving the next action as plain assistant prose.

### Validation

- Managed `todo-app` session `4a8e3bbb-be94-4ac4-a9b7-40ad4d34e175` proved the
  inline option click continued through the Codex SDK model lane and completed
  with SDK session `019e3028-4790-7a01-9b48-df0b0ac3f03f`, `32,322` raw
  tokens, `2,432` cached tokens, `29,890` non-cached-plus-output tokens, and no
  missing telemetry signals.
- After restarting the managed dashboard from the current Builder source, the
  Agent history endpoint rendered the same historical question and assistant
  message with operator-safe wording instead of raw `approval/status` text.
- Focused route regressions passed `4 passed` for operator-safe question
  serialization, assistant-content sanitization, and delivery-permission prompt
  conversion.

## 2026-05-16 - Operator-Safe Question Cards

### Fixed

- Agent-page `ask_user_question` cards now sanitize runtime-native question
  payloads before serialization, so model-generated cards do not expose internal
  lifecycle terms such as backlog, sprint, lifecycle, bounded, raw/full logs,
  chunk, or token pressure to non-technical operators.
- Runtime question guidance now explicitly treats `request_user_input` and
  `AskUserQuestion` text as operator-facing UI.

### Validation

- Computer Use verified the managed `todo-app` session
  `4a8e3bbb-be94-4ac4-a9b7-40ad4d34e175` no longer rendered `backlog`,
  `bounded`, `approval/status`, or `large logs` in the visible inline question
  card after rebuild and hard refresh.
- Focused regressions passed `3 passed` for operator-safe question payloads,
  historical question serialization, and feature-spec question continuation;
  Codex request-user-input mapping passed `1 passed`.

## 2026-05-16 - Codex App-Server Response Timeout

### Fixed

- Codex app-server JSON-RPC response waits for `initialize`, `thread/start` or
  `thread/resume`, and `turn/start` now have a bounded timeout. A stalled
  app-server is recorded as a runtime error and shut down instead of leaving
  the Agent page indefinitely `running` with no SDK session id, no token usage,
  and no log error.

### Validation

- Live managed `todo-app` evidence showed session
  `4a8e3bbb-be94-4ac4-a9b7-40ad4d34e175` entered the `codex_sdk` model-backed
  path with prompt assembly `estimated_tokens: 681`, then stalled before any
  SDK session id or usage. `PYTHONPATH=src pytest
  tests/test_codex_app_server_runtime.py -q` passed `14 passed` with new
  pre-response timeout coverage.

## 2026-05-16 - Model-Backed Agent Prompt Contract

### Fixed

- Agent-page delivery continuation, read-only status, recovery, and feature-spec
  prompt handling no longer use zero-token deterministic user-prompt shortcuts.
  Typed operator prompts now enter the selected runtime/model path; the model
  inspects bounded Builder state, chooses tool calls, and asks a structured
  question when intent is unclear.
- Runtime timeline glyphs now render Codex, Claude, and Samantha/OpenAI marks
  instead of text placeholders.
- Fresh root Agent-page sessions now bootstrap an empty transcript instead of
  stalling on `Loading agent transcript...` with a disabled composer.

### Changed

- `CLAUDE.md`, the SDK-backed Agent rubric, the deterministic-vs-model-backed
  behavior rubric, and the runtime-switch dashboard contract now reserve
  deterministic behavior for explicit UI controls, system refreshes, and exact
  persisted-state reads rather than typed prompt interpretation.

### Validation

- Focused Agent route regressions passed `12 passed`; frontend static Agent-page
  regressions passed `3 passed`; `tests/test_runtime_boundary_gate.py` passed
  `4 passed`; `npm run lint` passed; `frontend` `npm run build` passed with the
  existing Vite large-chunk warning.
- Required owner checks passed: `workflow --docs-dir docs read REFERENCE`,
  `builder quality-gate claude-md --json`, `workflow --docs-dir=docs summary
  quality-gate/claude-md`, `builder quality-gate architecture-boundary --json`,
  `builder quality-gate claude-agent-sdk --json`, and `builder map --json`.

## 2026-05-16 - Agent Lifecycle Proof and Voice Handoff

### Fixed

- Agent-page inline question choices now submit directly from the visible
  design-system option row instead of only selecting local draft state; Computer
  Use verified `Due reminders (Recommended)` advanced managed `todo-app`
  session `bf352c22-e6be-424d-9fae-bcedfa8477df` to `Question Answered` and
  `Ready`.
- Agent-page question and approval prompts no longer use a dialog path. They
  render inline with Builder status pills, token-backed review surfaces,
  readable option labels, and inline approval actions.
- Board activity timelines now carry runtime/provider metadata through both
  dashboard API schemas so Agent Run trace can attribute Codex SDK, Claude
  Agent SDK, and Samantha/OpenAI timeline rows correctly.
- Realtime text mode now submits typed operator requests on Enter, keeps the
  typed request visible, and opens the delegated SDK-backed Agent thread instead
  of leaving the operator in an empty Voice shell session.
- Agent-page active chat polling now refreshes history quietly while an
  SDK-backed run is live, so the Conversation timeline stays mounted instead of
  flashing `Loading agent transcript...` every polling interval.
- Agent-page pending delivery questions now render as timeline-native
  `Question` / `Approval needed` entries, expose inline `Start now` / `Hold`
  controls, and keep the composer below the thread content.
- Agent-page New Thread now starts from a real empty session instead of
  rehydrating stale voice/session history after refresh.
- Shipped Agent-page delivery sessions now append a final `Builder shipped ...`
  closeout with implementation, tests, browser proof, integration, and token
  evidence. Closeout recovery resolves display `sprint-plan-*` ids through the
  persisted `sprint_plan` document before checking the owning Sprint.
- Visible Agent-page approval/start responses now hide internal plan ids, task
  titles, and sprint-task wording; the plan id is stored in a non-visible
  `delivery_plan_created` event for recovery and shipped closeout.
- Codex SDK chunk-limit retries and Agent-page feature-spec prompts now bias
  toward bounded retrieval and compact context when the existing evidence is
  enough, avoiding raw/full/broad shell-output reinjection after chunk failures.

### Changed

- Agent Run trace now collapses adjacent uninformative tool-use rows into one
  counted timeline entry, reducing repeated empty boxes while keeping raw log
  detail available in the full trace lane.
- Metrics and session rails keep raw, cached, and non-cached-plus-output token
  fields separate so cache-heavy prompts no longer look like fresh output spend.
- Metrics recommendations now use active recent evidence for next-action
  guidance while retaining historical raw/cached/non-cached totals for audit, so
  stale agent-chat raw totals no longer keep driving follow-up work after clean
  deterministic runs.

### Validation

- Computer Use proof on managed `todo-app` session
  `bf352c22-e6be-424d-9fae-bcedfa8477df` showed inline `Due reminders
  (Recommended)` submit through `/api/agent/chat/respond`; `builder agent
  history` then reported `32,254` raw tokens, `2,432` cached tokens, `29,822`
  non-cached-plus-output tokens, and `stop_reason=completed`.
- Computer Use proof on managed `todo-app` session
  `ec2d5ffd-8f0d-400e-9456-d517191da072` showed the live Agent page ship
  `Collapsible completed todos section`; Board reached `pending: 0`,
  `active: 0`, `review: 0`, `done: 35`, `blocked: 0`, and refresh showed the
  final shipped closeout in Conversation.
- Computer Use proof on managed `todo-app` session
  `b409573c-08ed-40be-b8c5-a37363b48324` kept the full Conversation timeline
  visible across repeated active polling while the SDK-backed Agent/chat and
  recovered code-gen runs were running.
- Final closeout token evidence for that live sprint was `176,481` raw,
  `171,136` cached, and `5,345` non-cached-plus-output tokens across `12`
  completed run records.
- The same managed `todo-app` metrics lane now reports
  `recommended_next_change: maintain_current_flow` with empty active avoidable
  flags after the deterministic closeout runs.
- `PYTHONPATH=src pytest ... -q` focused Agent/Codex regression set passed
  `9 passed`; the inline decision/trace focused set passed `7 passed`;
  Realtime frontend/operator suite passed `67 passed`; `npm run lint` passed;
  `frontend` `npm run build` passed with the existing Vite chunk warning;
  `builder quality-gate dashboard-ux --json`, `builder quality-gate
  product-lifecycle --json`, `builder quality-gate builder-cli --json`, and
  `builder quality-gate claude-agent-sdk --json` returned `ok`.

## 2026-05-16 - Agent Sprint Continuation Recovery

### Fixed

- Agent-page persisted delivery approvals now recover after refresh or missed
  SSE delivery: pending approval cards unlock the composer, the session rail
  shows `blocked`, and approving `Delivery scope approval` creates the sprint
  plan even when the original live waiter is gone.
- After a sprint plan creates dispatchable Board work, short continuation
  prompts such as `start` now dispatch the next Builder task instead of falling
  through to generic model-backed chat.

### Validation

- Visible Computer Use validation on managed `todo-app` session
  `b48fc8cf-59b7-4dea-97e3-59b717eea602` recovered a hidden pending approval,
  accepted `approve`, and created plan `sprint-plan-6a41b3ba1754` with three
  work steps for `Text search for todos`.
- The misrouted live `start` run exposed the efficiency issue clearly:
  `87,121` raw tokens, `85,888` cached tokens, `1,233` non-cached plus output,
  and `282,816ms` duration while Board task state stayed queued/planning.
- `PYTHONPATH=src pytest tests/test_embedded_agent_routes.py::test_go_ahead_dispatches_first_pending_sprint_task_without_manual_board tests/test_embedded_agent_routes.py::test_chat_respond_recovers_persisted_delivery_scope_approval_without_live_waiter tests/test_embedded_agent_routes.py::test_chat_respond_recovers_persisted_pending_question_without_live_waiter tests/test_realtime_voice_frontend_static.py -q`
  passed `12 passed`; `npm run lint` and `npm run build` passed from
  `frontend/` with only the existing Vite large-chunk warning.

## 2026-05-15 - Codex SDK and Realtime Voice Robustness

### Fixed

- Ready Board delivery follow-ups from the Agent page now use context-driven
  model-backed interpretation instead of an exact `start shipping` phrase
  trigger, so natural operator wording can let the selected runtime inspect
  Builder state and choose the dispatch tool chain.
- Agent Run trace now streams from bounded Board payloads in the embedded
  dashboard route, so historical completed-run diff evidence no longer blocks
  the selected active task-owned run from rendering while an agent is running.
- Agent chat recovery-continuation now calls Builder's shared task recovery
  service before dispatching, so "recover this and keep going" does not skip an
  earlier failed generated sprint task to start later pending work.
- Task workspace integration now preserves tracked local target files before
  fast-forwarding task output, making checkout-conflict recovery an
  orchestrator/integration-gate responsibility instead of an operator/manual
  generated-app fix.
- Codex app-server runtime now treats `turn.error` as non-fatal only when it
  duplicates the final streamed answer, preserving real runtime errors while
  preventing successful Samantha delegated answers from being rendered as
  `Agent error`.
- Codex app-server chunk-limit retry now starts a fresh app-server thread
  instead of resuming the bloated thread that caused the transport failure.
- Codex app-server large command output is now scored from the compacted
  reinjection event stream while the full output remains stored as a Builder
  artifact, so live metrics stop treating already-compacted output as the
  active `truncate_tool_output_before_reinjection` fix.
- Agent-page observability prompts and Codex chunk-limit retries now include
  concrete bounded retrieval commands before any raw or `--full` evidence path.
- Agent-page Session token accounting now separates non-cached-plus-output,
  raw, and cached tokens so Codex SDK prompt-cache reuse is not presented as
  fresh model spend.
- Agent-page `New thread` now detaches stale voice/session history, clears
  `session`, `task`, and `run` URL state, stops active voice refresh, and opens
  a genuinely empty transcript instead of rehydrating the prior thread after
  refresh.
- Agent-page Conversation composer now answers pending structured questions and
  visible approvals inline through the canonical response path, so operators
  can keep typing naturally below the timeline without knowing internal card
  controls.
- Generated-app post-ship optimization now defers Builder-owned residuals such
  as agent-chat token budget, runtime error trends, and bounded retrieval
  policy back to Builder source instead of launching an owner-mismatched
  model-backed optimization-agent run from the managed app lane.
- Agent-page chat status and Metrics now preserve input, output, cached, raw,
  and non-cached-plus-output token fields instead of collapsing SDK usage into a
  single output bucket for `agent-chat`.
- Realtime text mode now submits typed Samantha requests on plain Enter while
  preserving Shift+Enter for multiline input, so Voice testing does not depend
  on hidden keyboard shortcuts.
- Realtime Voice delegation now returns immediately with event-driven
  completion, rebinds the active Realtime call to the delegated Agent session,
  and switches the visible Agent page from the empty Voice session to the
  Builder Conversation thread.
- Realtime Voice policy and tool guidance now require Samantha to pass the
  operator's exact feature/shipping request into `delegate_to_builder_agent`
  instead of narrowing it into an investigation prompt.
- Agent-page transcript layout now defaults and migrates to the current
  timeline UI, preventing refresh from rehydrating the older card renderer when
  a browser still has the previous `cards` preference.
- Voice tab transcripts now use the same timeline renderer as Conversation,
  label normal Samantha turns as `Samantha`, label operator turns as `Operator`,
  and keep the Realtime input below the transcript instead of inside the old
  voice-card stack.
- Realtime Voice now gives a bounded Samantha activation cue by saying exactly
  `Hi there!` on connect without creating a synthetic operator message; after that it
  waits for non-empty operator speech or typed input, and the sideband no longer
  speaks pending-approval reminders on a timer.
- Realtime Voice recent-context reinjection is capped before prompt assembly so
  Samantha-to-Agent handoffs do not repeatedly replay oversized prior context.
- Metrics fallback reporting now exposes fallback reason/base URL, and metrics
  next steps point to resolvable `builder logs analyze --session ... --json`
  commands.
- Forward-engineering onboarding now treats docs/scratch-only workspaces and
  empty code directories as non-code, avoiding reverse-engineering mode for
  operator notes or bootstrap shells.
- The floating Samantha UI is consolidated into one voice orb component with
  the ambient glow, error/retry state, and start/stop action in the same
  entrypoint.

### Changed

- Added a full goal checklist in `docs/PROGRESS.md` covering operator UX,
  live shipping, token monitoring, surface coverage, and enforcement status.
- Added SDK-grounded token optimization direction to the Agent behavior rubric,
  runtime telemetry reference, agent-quality tuning workflow, and agent-quality
  gate: keep judgment prompts model-backed, then optimize cache-friendly prompt
  shape, bounded evidence, deferred tools, compaction, and token reporting.
- Added Claude Agent SDK best-practice direction to the Claude telemetry
  reference, Claude SDK gate, SDK-backed Agent rubric, and tuning workflow:
  preserve the agent loop, then tune tool scope, permissions, hooks,
  `AskUserQuestion`, subagents, tool search, compaction, effort, turn/budget
  limits, cache usage, and structural OTEL.
- Added a repo memory correction and global ad-hoc memory note for the
  SDK-backed token-optimization rule after explicit user approval.
- Pre-commit checks now require `CHANGELOG.md` for product, docs, hook, or
  operator-surface changes, while keeping tests-only commits exempt.
- The Builder quality score document now records the current 9.5+ rubric,
  score, evidence, and remaining remediation plan.
- Added a repo-local correction that managed app validation must use a generated
  app workspace, not the Builder source repo as the managed app.
- Added a repo-local correction that Codex must not install dependencies, edit
  source, or clean worktrees inside managed app workspaces during Builder
  validation; recovery and shipping must go through Builder-owned agents, gates,
  and services.
- Added project-scoped Codex custom-agent registrations and a deterministic
  `codex-subagents` quality gate for architecture review, code review, and code
  simplification lanes.
- Added the Autonomous Builder agent catalog rubric plus a visual
  agent-sprint-cycle explainer artifact for new-person orientation.
- Hidden local explainer byproducts such as nested `.claude/settings.local.json`
  `.thumbnails/`, and local `audio/` generation artifacts are now ignored
  instead of entering project history.

### Validation

- `uv run pytest tests/test_embedded_agent_routes.py::test_recover_and_keep_going_recovers_first_blocked_sprint_task_before_dispatch tests/test_embedded_agent_routes.py::test_continue_remaining_verification_task_dispatches_current_sprint_task tests/test_embedded_agent_routes.py::test_recovery_status_check_does_not_auto_dispatch_sprint_task -q`
  passed `3 passed`.
- `uv run pytest tests/test_orchestrator.py::test_integrate_task_workspace_preserves_tracked_target_changes_before_merge tests/test_orchestrator.py::test_tracked_overwrite_paths_extracts_safe_relative_paths -q`
  passed `2 passed`.
- `uv run pytest tests/test_embedded_agent_routes.py -q` passed `99 passed`.
- `uv run pytest tests/test_orchestrator.py tests/test_task_recovery.py tests/test_run_reconciliation.py -q`
  passed `54 passed`.
- `uv run pytest tests/test_dashboard_design_system_contract.py::test_agent_run_trace_surfaces_token_breakdown tests/test_pre_commit_checks.py -q`
  passed `14 passed`.
- `PYTHONPATH=src pytest tests/test_realtime_voice_frontend_static.py tests/test_dashboard_design_system_contract.py::test_realtime_voice_degrades_to_text_mode_without_microphone -q`
  passed `5 passed`; `npm run lint` and `npm run build` passed from
  `frontend/`.
- Managed `todo-app` Voice-tab proof showed the bounded activation cue as
  `SAMANTHA ... Hi there!`, with no `thinking · Samantha` label and no synthetic
  operator message.
- `python scripts/pre_commit_checks.py` passed all selected commit-hook checks,
  including `changelog_update_required`.
- Managed `todo-app` dashboard proof reduced `/api/dashboard/board` from
  `11801990` bytes to `835662` bytes and `/api/dashboard/board/stream` from
  `12703880` bytes over two seconds to `879995` bytes; Chrome-visible Run trace
  loaded the selected task-owned run and event timeline.
- `python3 scripts/check_codex_subagents.py --repo-root .` passed.
- `uv run pytest tests/test_codex_subagents.py -q` passed.
- Official OpenAI Codex subagent docs checked for project-scoped
  `.codex/agents/` files and required custom-agent keys.
- Commit-prep checks passed: `uv run pytest tests/test_codex_subagents.py tests/test_builder_cli_surfaces.py tests/test_pre_commit_checks.py -q`
  reported `163 passed`; `npm run lint` and `npm run build` passed from
  `frontend/`; `builder verify --changed --execute --json` passed executable
  proof and required only manual dashboard browser proof.
- Manual browser proof passed through Chrome on `http://127.0.0.1:9876/` and
  `/board` after `builder start --port 9876` from the managed `todo-app`
  workspace.
- Official OpenAI Codex app-server docs checked for `thread/start` versus
  `thread/resume` semantics; the retry fix now follows those documented
  boundaries.
- Official OpenAI Realtime docs checked for WebRTC data-channel text input and
  function-call output flow; the current Realtime Voice implementation matches
  `conversation.item.create`, `function_call_output`, and `response.create`
  expectations.
- Browser-visible managed-app proof used the todo app workspace on isolated
  port `9877`, leaving the active managed app server on `9876` untouched.
- Samantha operator prompt `What should we fix next?` used bounded
  `get_builder_agent_update` instead of a full Agent run.
- Samantha operator prompt `Can you look into why the last run failed and tell
  me what to fix?` completed without creating a new `run_error`.
- `uv run pytest tests/test_builder_cli_surfaces.py tests/test_embedded_agent_routes.py tests/test_codex_app_server_runtime.py tests/test_realtime_voice_operator.py -q`
  passed `299 passed`.
- `uv run pytest tests/test_codex_app_server_runtime.py tests/test_realtime_voice_operator.py tests/test_realtime_voice_frontend_static.py tests/test_embedded_agent_routes.py -q`
  passed `166 passed`.
- `uv run pytest tests/test_codex_app_server_runtime.py tests/test_codex_optimization.py tests/test_runtime_optimization.py tests/test_embedded_agent_routes.py::test_observability_context_pack_keeps_analysis_model_backed tests/test_embedded_agent_routes.py::test_compatible_resume_session_rejects_codex_large_output_context`
  passed `33 passed` for the output reinjection and bounded retrieval slice.
- Chrome-visible Agent-page validation in the managed `todo-app` workspace
  created session `4ac92212-f60e-4153-8185-22a1163038a5`; after the run,
  `builder metrics show --json --full --limit 8` reported
  `active_avoidable_cost_flags: []`, `recent_large_output_runs: 0`, and
  `recommended_next_change: reduce_agent-chat_raw_tokens`.
- `builder quality-gate builder-cli --json`,
  `builder quality-gate claude-agent-sdk --json`, and
  `builder quality-gate product-lifecycle --json` passed.
- `uv run pytest tests/test_embedded_agent_routes.py -q` passed `101 passed`
  for the Agent route surface after the ready-delivery follow-up change.
- `ruff check` on touched Python surfaces and `git diff --check` passed.
- Managed `todo-app` high-priority live run shipped Sprint 5 to `pending: 0`,
  `active: 0`, `review: 0`, `done: 29`, `blocked: 0`; Chrome proof added
  `Pay taxes`, toggled `Mark high` to `High priority`, and preserved the visual
  priority state after refresh.
- High-priority token proof recorded `39,808` raw scoping tokens with `33,152`
  cached; task runs used `60,062`, `63,383`, and `52,673` raw tokens; final
  metrics reported `raw_token_total: 2328520`, `noncached_plus_output_tokens:
  527715`, `cache_ratio: 5.2114`, and no recent risky or large-output runs.
- Focused validation for the new owner split passed:
  `PYTHONPATH=src pytest tests/test_realtime_voice_frontend_static.py
  tests/test_sprint_execution.py::test_post_preflight_decision_routes_generated_app_residuals_to_model_review
  tests/test_sprint_execution.py::test_post_preflight_decision_defers_builder_owned_generated_app_residuals
  tests/test_sprint_execution.py::test_post_preflight_decision_treats_current_guidance_as_resolved
  tests/test_sprint_execution.py::test_post_preflight_decision_runs_model_review_for_builder_source_residuals
  -q` passed `10` tests; `ruff check` passed on touched Python tests/source;
  `npm run lint` and `npm run build` passed from `frontend/`.

## 2026-05-14 - Builder Context Budget Observability

### Added

- Builder-owned `context_budget` events at SDK-backed Agent prompt assembly and
  Realtime Voice session/tool exchange boundaries.
- Context component token estimates, signal category/value, runtime/provider/
  model/effort, and correlation ids without raw prompt/tool payload storage.
- Observability and Metrics panels for estimated context, latest lane, signal
  value, top components, and signal categories.
- Compact `context_budget` evidence in `builder logs analyze`,
  `builder logs --info --compact --json`, and `builder metrics show --json`.

### Changed

- Realtime context-budget persistence is best-effort, so observability storage
  cannot break voice control or websocket shutdown paths.
- Codex optimization now keeps active top cost drivers separate from historical
  top drivers, so old expensive runs do not alone drive next-action advice.

### Validation

- Browser-visible Observability changed from missing context evidence to
  `MISSING SIGNALS 0` and showed a `Context budget` panel with `5 handoff
  events`, `15K` estimated context, latest lane `realtime_voice`, and signal
  value `high`.
- Browser-visible SDK-backed Agent prompt on `TASK F3918457` recorded
  `context_budget.lane=sdk_agent`, `stage=agent_prompt_assembly`,
  `total_estimated_tokens=2180`, `signal_category=mixed`.
- Browser-visible Realtime Voice text prompt on `TASK E0C803C3` recorded
  `context_budget.lane=realtime_voice`, `stage=realtime_tool_exchange`,
  `estimated_tokens=1038`, `signal=high`.
- Computer Use browser proof on the rebuilt managed `todo-app` dashboard showed
  fresh Voice session `BCDE6F97` say `Hi there!`, accept
  `I want to improve the todo app so I can search tasks by text.`, and
  automatically switch to Conversation session
  `b48fc8cf-59b7-4dea-97e3-59b717eea602` with visible `USER · OPERATOR` and
  `TOOL · SAMANTHA` entries. Builder logs recorded
  `delegate_to_builder_agent ok (running)`, SDK prompt assembly
  `estimated_tokens=900`, and the completed Agent run at `50,081` raw tokens
  with large command output compacted into a Builder artifact.
- `uv run pytest tests/test_context_budget.py tests/test_observability_summary.py tests/test_codex_optimization.py -q`
  passed `25 passed`.
- `uv run pytest tests/test_realtime_voice_operator.py tests/test_embedded_agent_routes.py -q`
  passed `151 passed`.
- `uv run pytest tests/test_builder_cli_surfaces.py tests/test_dashboard_api.py -q`
  passed `166 passed`.
- `npm run build` passed from `frontend/`.

### Notes

- This creates the measurement/control plane needed for future context
  reduction; it does not yet automatically reduce token use.
