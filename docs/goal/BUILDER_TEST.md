# BUILDER_TEST.md — End-to-End Builder Validation Plan

Operator-driven, dashboard-first test plan for proving the **builder product**
(lane: `claude`) works end-to-end on a **fresh managed app**. Distinct from
[`TESTING.md`](TESTING.md) (the status-skill-owned, generator-parsed `SC-NN`
ledger): this doc is a standalone, hand-run **plan** — what to test, the exact
steps, and what to validate — not a token ledger. Nothing here feeds
`goal-overview.html`.

## How to run

- **Driver:** drive every UI action through `/hermes-chrome` with a visible cursor,
  exactly as an operator would. `curl`/`builder` CLI is for *observing* state only,
  never for *triggering* a UI action.
- **One full positive pass, then inject negatives.** Run the positive lifecycle
  (P-01 → P-10) on one fresh app to completion; then exercise the negative
  scenarios (N-01 → N-12) as deviations from known-good state.
- **Inspect neighbouring surfaces.** A change verified only on the touched surface
  is unverified — after each phase sweep Agent / Backlog / Board / Metrics /
  Observability.
- **Side-effects are the proof.** A session that *completes* is not a pass. Verify
  the durable state change (backlog item, task status, generated file, no dupes).
- **Fix root causes, not symptoms.** A failure → fix where it lives (builder `src/`,
  not a workaround); builder defect → ROADMAP `IMP-*`; app defect → the app's own
  backlog.

## Lanes & verdict

| Token | Meaning |
| --- | --- |
| **backend** | provable via pytest / `builder` CLI / REST |
| **browser** | provable only by driving the real dashboard |
| ✅ pass | contract held, side-effect confirmed |
| ❌ fail | crash / silent half-state / stranded lock / dupe / bypass → file `IMP-*` |
| ⛔ blocked | needs fault-injection or an unbuilt surface; note the prereq |

## System under test

Fresh app: **expense-tracker** (`/home/gurusharangupta/Builder-Workspace/expense-tracker`),
served on a free port (e.g. :9876). Submit a deliberately **vague** ask and let the
builder's interview shape scope — that is the real operator flow.

Lifecycle under proof (`CLAUDE.md` task-status order):
`pending/planning → design/design_review → implementation → quality_gates →
pr_creation/review_pending → build_verify → done`, with the dashboard surfaces
Agent · Backlog · Board · Metrics · Observability · Settings.

---

## Positive scenarios (happy path — the canonical end-to-end ship)

Run in order; each builds on the prior state.

### P-01 — Init & readiness gate
- **Steps:** (1) `builder init --project-name expense-tracker` in the workspace.
  (2) `builder start --port <p>`. (3) Open the dashboard in Chrome.
- **Validate:** `.agent-builder/` created; `/health` → `ok`; the project loads;
  Day-0 readiness is satisfied (or the UI surfaces exactly what's missing) **before**
  any autonomous work is offered.
- **Grounds:** day-0-readiness; forward-flow steps 1–2.

### P-02 — Vague ask triggers a real interview
- **Steps:** On the Agent page, submit *"I want an app to track my spending."*
- **Validate:** the model responds with a **structured `AskUserQuestion` card**
  (3 options, recommended-first, inline custom box) probing audience / workflow /
  data / first-outcome — **not** a generic-MVP dump and **not** a plain-text
  question with a `?`.
- **Grounds:** forward-flow step 3; IMP-018.

### P-03 — Interview converges to a scoped feature
- **Steps:** Answer 2–4 clarification cards (categories, add/list, totals view…).
- **Validate:** each answer stays visible on its card post-submit; the thread
  converges to a concrete feature spec; no contradiction loop; no leaked internals.
- **Grounds:** IMP-018; interview integrity.

### P-04 — Feature captured, sized correctly (no over-decomposition)
- **Steps:** Let the builder propose backlog/sprint. Open the Backlog page.
- **Validate:** one `type=feature` item labelled **"Feature"** (never "Improvement");
  task count matches the real change size (a small ask ≈ 1–few tasks, **not** a fixed
  5-task keyword sprint).
- **Grounds:** IMP-015; IMP-027.

### P-05 — Approve the sprint/plan at the gate
- **Steps:** Reach the approval card; click **Start now**.
- **Validate:** controls are enabled and register the answer; state advances out of
  approval (no stranded lock); thread shows the answered card as text.
- **Grounds:** IMP-018; IMP-029.

### P-06 — Dispatch starts a run; live rail ticks
- **Steps:** Observe the Board + Session rail as the first task dispatches.
- **Validate:** a run starts (`active_runs` ≥ 1); the Session rail tokens/cost tick
  **live** during the turn; a live tool-activity count shows (never a blank wait box).
- **Grounds:** G1; forward-flow step 3; IMP-031 (dispatch actually fires).

### P-07 — UI code-gen carries the design directive
- **Steps:** Let code-gen run for the UI feature; inspect the generated app's UI.
- **Validate:** generated UI shows real **design taste** (spacing, hierarchy, type,
  states) — the IMP-034a Product-UI directive is in effect for `is_ui_task`, not a
  generic unstyled scaffold.
- **Grounds:** IMP-034a.

### P-08 — Quality gates + doc-refresh boundary
- **Steps:** Watch the task cross `quality_gates → pr_creation`.
- **Validate:** code/test gates run; maintained-doc freshness validated; for a local
  workspace with no real PR target, deterministic `change_evidence` / `build_verify`
  are used (not a hung pr-creator).
- **Grounds:** CLAUDE.md quality_gates→pr_creation boundary; local-workspace rule.

### P-09 — Build-verify produces a working app
- **Steps:** Reach `build_verify`; open the generated app.
- **Validate:** app builds and runs; the requested feature works (add an expense →
  it lists → a total updates → persists across reload); task reaches `done`.
- **Grounds:** build_verify; lifecycle terminal state.

### P-10 — Metrics & observability honest after the run
- **Steps:** Read Metrics + Observability; cross-check `builder logs analyze
  --session <id>` and `metrics show` from the app workspace.
- **Validate:** headline tokens/cost/prompt_count **non-zero** (not 0 while raw is
  populated); `cache_ratio ∈ [0,1]`; Observability error-trend count **equals**
  `builder logs --error` count; no dispatch-blocking rec from stale errors.
- **Grounds:** IMP-023; IMP-024; IMP-014.

---

## Negative scenarios (graceful handling — inject after a clean positive pass)

Each must end in a **guarded / re-prompted / clean blocked-or-error** state —
never a crash, silent half-state, stranded lock, duplicate, or policy bypass.

### N-01 — Dirty / re-init workspace *(backend)*
- **Steps:** `builder init` in a non-empty dir; then `builder init` again.
- **Validate:** clean init or explicit guard; idempotent re-init; no wiped state, no
  duplicate `.agent-builder`.  · Grounds: SC-01/02.

### N-02 — Start on an occupied port without `--force` *(backend)*
- **Steps:** `builder start --port <p>` against an already-bound port.
- **Validate:** actionable error, not a silent failed bind.  · Grounds: SC-03.

### N-03 — Empty / blank interview answer *(browser)*
- **Steps:** Submit a clarification card with no input.
- **Validate:** graceful re-prompt; card not stuck; no crash.  · Grounds: SC-07.

### N-04 — Contradictory follow-up answers *(browser)*
- **Steps:** Answer A, then contradict it on the next card.
- **Validate:** model reconciles or re-asks; no silent pick.  · Grounds: SC-10.

### N-05 — Rapid double-submit of an answer *(browser)*
- **Steps:** Click a card's submit twice in fast succession.
- **Validate:** no stranded answer-control lock; controls recover.  · Grounds: SC-08/IMP-029.

### N-06 — Builder-self ask typed into app chat *(browser)*
- **Steps:** Type *"make the builder faster"* into the app's Agent chat.
- **Validate:** **not** captured into the expense-tracker backlog; routed to the
  builder-self lane.  · Grounds: SC-09/IMP-016.

### N-07 — Reject the sprint proposal *(browser)*
- **Steps:** At the approval card, reject instead of approving.
- **Validate:** sane non-stuck state; can re-plan.  · Grounds: SC-14.

### N-08 — Malformed backlog item create *(browser)*
- **Steps:** Create an item with empty title / junk type.
- **Validate:** validation error, no broken row.  · Grounds: SC-15.

### N-09 — Cancel / remove a backlog item *(browser)*
- **Steps:** Use the cancel control on an item.
- **Validate:** drives to terminal `cancelled`; no orphan.  · Grounds: SC-13/IMP-017.

### N-10 — Dispatch with nothing dispatchable / double-dispatch *(browser)*
- **Steps:** Hit dispatch on an empty Board; then dispatch a 2nd task mid-run.
- **Validate:** clear empty state (no phantom run); concurrency guard blocks the
  double active run.  · Grounds: SC-16/SC-17.

### N-11 — Stop a running task / recover a blocked one *(browser, fault-inject)*
- **Steps:** Cancel mid-run; separately, Recover a blocked task.
- **Validate:** stop → clean terminal state, run actually halts; recover →
  recover **and** dispatch (not reset-only stranded).  · Grounds: SC-19/SC-18/IMP-031.

### N-12 — Chat cannot edit generated app files *(browser)*
- **Steps:** Ask the chat to directly edit a generated source file.
- **Validate:** denied + routed to task dispatch; **no** Approve/Deny bypass card;
  generated file byte-identical after.  · Grounds: SC-25/IMP-020.

### N-13 — Reload / navigate-away mid-task *(browser)*
- **Steps:** Refresh during a run; switch pages and return.
- **Validate:** Board/task state intact; run uninterrupted; no corrupted half-state.
  · Grounds: SC-31/SC-32.

### N-14 — Restart builder mid-task (continuity) *(browser, fault-inject)*
- **Steps:** Restart `builder` while a task is mid-flight; reopen the dashboard.
- **Validate:** resume reuses the same workspace `cwd`; the task continues; phase
  runs render in the task sidebar.  · Grounds: SC-33/SC-34.

---

## Closeout

Durable findings → typed backlog at session close: `incident` (observed product
failure), `improvement` (required hardening), `optimization` (efficiency /
agent-experience). Builder defects also get an `IMP-*` on ROADMAP; reusable traps →
`builder memory`. If a negative scenario needs fault-injection that isn't yet
reachable from the dashboard, mark it ⛔ blocked with the missing prereq named.
