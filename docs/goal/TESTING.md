# TESTING.md — Builder Test Ledger

Standing bug-hunt ledger against the **builder product** (lane: `claude`). One
scenario per row, each tagged **positive vs negative** and **backend vs
browser**. Goal: surface where the lifecycle *falters*, then **fix root causes,
not symptoms**. App-vs-builder routing: builder defects → ROADMAP/`IMP-*`; app
defects → the app's own backlog.

**Engine:** [`/builder-test`](../../.claude/skills/builder-test/SKILL.md) executes
the rows — backend rows in its STATIC/UNIT/INTEGRATION phases, browser rows in
its E2E phase via `/hermes-chrome` — fixes each `S:fail` at root cause, flips the
`S:` token, files the `IMP-*`, then runs `/status update`.
**Format owner:** the [`status`](../../.claude/skills/status/SKILL.md) skill owns
this file's token contract + the `goal-overview.html` § "Browser Testing" mirror
(generated; never hand-edit the HTML — run
`python3 .claude/skills/status/scripts/build_goal_overview.py`).

## Test criteria — what to cover

Every surface (`S1`–`S8`) must carry **both** a positive and a negative row.

- **Positive (`K:P`)** — the documented contract works on intended input: correct
  output, state transition, or invariant holds. Proves the surface *does its job*.
- **Negative (`K:N`)** — edge / empty / malformed / adversarial / concurrent /
  fault-injected input is handled *gracefully*: guarded, re-prompted, or surfaced
  as a clean blocked/error state. Never a crash, silent half-state, stranded lock,
  duplicate, or policy bypass.

Lane = where the row is exercised: **`backend`** = pytest / `builder` CLI;
**`browser`** = `/hermes-chrome` real-browser. A row's lane is the surface that
*proves* the expectation, not merely where it's convenient to look.

| Surface | Positive must prove | Negative must prove |
| --- | --- | --- |
| S1 Bootstrap | clean init + readiness gate | dirty/re-init/occupied-port guarded |
| S2 Interview | vague ask → structured interview | empty/contradictory/misrouted input handled |
| S3 Backlog/sprint | correct sizing + labels + controls | malformed create / rejected proposal sane |
| S4 Dispatch/Board | run starts, rail + activity live | empty/double-dispatch/stop guarded |
| S5 Approvals/blocked | card controls register | hung/limit/edit-bypass handled cleanly |
| S6 Metrics/observ. | headline + invariants populated | stale-error rec not dispatch-blocking |
| S7 UI integrity | fresh bundle, state survives nav | reload mid-task doesn't corrupt state |
| S8 Continuity | resume reuses cwd, runs render | restart mid-task doesn't strand |

## How tracking works

One scenario per line under a `## S<n>` surface group. Each carries a `K:` kind
token and an `S:` state token (the `S:` token is the source of truth for the HTML
mirror):

| Token | Meaning | Badge |
| --- | --- | --- |
| `S:pending` | not yet started | ⬜ |
| `S:inflight` | **current testing effort** — being exercised now | 🔄 |
| `S:pass` | exercised, behaved correctly | ✓ |
| `S:fail` | bug found (links the `IMP-*` / finding) | ✗ |
| `S:blocked` | can't run yet (prereq / environment / fault-injection needed) | ⛔ |

**Current effort = every `S:inflight` row.** Everything else is the pending
backlog. As a scenario is verified, flip its token and (on `S:fail`) name the
filed `IMP-*`.

Line shape (parser-stable — `K:` precedes `S:`):
`` - `SC-NN` **Title** — <condition>. Expect: <correct behavior> (<anchor>). `K:<P|N>/<backend|browser>` `S:<state>` ``

`<anchor>` = the contract or prior-defect class the expectation is grounded in.

---

## S1 — Bootstrap & readiness

- `SC-01` **Dirty/non-empty workspace init** — `builder init` where the dir already has files. Expect: clean init or explicit guard, no silent half-state. (forward-flow step 2). `K:N/backend` `S:pass`
- `SC-02` **Re-init an initialized workspace** — `builder init` twice. Expect: idempotent, no duplicate `.agent-builder` or wiped state. (day-0 readiness). `K:N/backend` `S:pass`
- `SC-03` **Start on occupied port w/o `--force`** — port already bound. Expect: actionable error, not a silent failed bind. (forward-flow step 1). `K:N/backend` `S:pass`
- `SC-04` **Readiness gate visible pre-product** — first product ask before readiness passes. Expect: Day-0 readiness gates autonomous work, surfaced in UI. (CLAUDE.md day-0-readiness). `K:P/browser` `S:pass`

## S2 — Requirements interview (Agent page)

- `SC-05` **Vague one-word ask** — "build me an app". Expect: model interviews for audience/workflow/data/first-outcome, not a generic-MVP dump. (forward-flow step 3). `K:P/browser` `S:pass`
- `SC-06` **Structured question card integrity** — answer a clarification card. Expect: 3 options, recommended-first, inline custom box; answer stays visible on the card post-submit. (IMP-018). `K:P/browser` `S:pass`
- `SC-07` **Empty/blank answer** — submit a clarification with no input. Expect: graceful re-prompt, no crash / stuck card. (negative input). `K:N/browser` `S:pass`
- `SC-08` **Rapid double-submit answer** — click submit twice fast. Expect: no stranded answer-control lock; controls recover. (IMP-029). `K:N/browser` `S:blocked`
- `SC-09` **Builder-self-improvement ask in app chat** — "make the builder faster" typed into app chat. Expect: NOT captured into the app backlog; routed to builder-self lane. (IMP-016). `K:N/browser` `S:pass`
- `SC-10` **Contradictory follow-up answers** — answer A then contradict in next round. Expect: model reconciles or re-asks; no silent pick. (negative input). `K:N/browser` `S:pending`

## S3 — Backlog & sprint

- `SC-11` **Trivial ask not over-decomposed** — ask for one small feature. Expect: ~1 task, not a fixed 5-task keyword sprint (token burn). (IMP-027). `K:P/browser` `S:pass`
- `SC-12` **Feature type label** — create `type=feature` item. Expect: rendered "Feature", never "Improvement". (IMP-015). `K:P/browser` `S:pass`
- `SC-13` **Cancel/remove a backlog item** — use the cancel control. Expect: drives to terminal `cancelled`. (IMP-017). `K:P/browser` `S:pass`
- `SC-14` **Reject a sprint proposal** — reject at the approval card. Expect: sane non-stuck state; can re-plan. (lifecycle step 4). `K:N/browser` `S:pending`
- `SC-15` **Malformed item create** — empty title / junk type. Expect: validation error, no broken row. (negative input). `K:N/browser` `S:blocked`

## S4 — Dispatch / Board / execution

- `SC-16` **Dispatch with no dispatchable task** — hit dispatch on an empty Board. Expect: clear empty state, no phantom run. (lifecycle step 5). `K:N/browser` `S:blocked`
- `SC-17` **Dispatch while one is running** — dispatch a 2nd task mid-run. Expect: concurrency guard, no double active run. (lifecycle step 5). `K:N/browser` `S:pass`
- `SC-18` **Recover blocked task dispatches** — Recover a blocked task. Expect: recover *and* dispatch (active_run starts), not stranded reset-only. (IMP-031). `K:P/browser` `S:blocked`
- `SC-19` **Stop a running task** — cancel mid-run. Expect: clean terminal state, run actually stops. (lifecycle). `K:P/browser` `S:blocked`
- `SC-20` **Live token/cost rail** — watch a running turn. Expect: Session rail tokens/cost tick live during the run. (G1). `K:P/browser` `S:pass`
- `SC-21` **No blank wait state** — during agent work. Expect: live tool-activity count visible, never empty transient boxes / blank wait. (forward-flow step 3). `K:P/browser` `S:pass`

## S5 — Approvals & blocked states

- `SC-22` **Approval card controls** — reach an approval gate. Expect: enabled Start now/Hold; answer registers. (IMP-018). `K:P/browser` `S:pass`
- `SC-23` **Hung respond recovers** — respond stalls. Expect: controls re-enable via timeout, not permanently disabled. (IMP-029). `K:N/browser` `S:blocked`
- `SC-24` **Provider-limit blocked card** — hit a provider limit. Expect: blocked card w/ reset metadata, not a stale gate failure or DB-repair ask. (CLAUDE.md provider-limit contract). `K:N/browser` `S:blocked`
- `SC-25` **Chat can't edit app files** — ask chat to directly edit a generated file. Expect: denied + routed to dispatch, no Approve/Deny bypass card. (IMP-020). `K:N/browser` `S:pass`

## S6 — Metrics & observability

- `SC-26` **Headline tokens/cost non-zero** — after a run, read Metrics. Expect: headline tokens/cost/prompt_count populated, not 0 while raw is non-zero. (IMP-023). `K:P/browser` `S:pass`
- `SC-27` **In-progress run note** — during an active run, read Metrics. Expect: `active_runs_note` renders. (IMP-003). `K:P/browser` `S:pass`
- `SC-28` **Stale-error rec not blocking** — old `mcp__builder__task_*` errors present. Expect: no dispatch-blocking optimization rec; optimization vs workflow-state separated. (IMP-014). `K:N/browser` `S:pass`
- `SC-29` **cache_ratio bounded** — read telemetry. Expect: `cache_ratio` ∈ [0,1]. (IMP-024). `K:P/backend` `S:pass`

## S7 — UI integrity / persistence

- `SC-30` **Fresh bundle served** — load the dashboard. Expect: current build assets, not a stale pre-pipeline bundle. (IMP-030). `K:P/browser` `S:pass`
- `SC-31` **Reload mid-task** — refresh during a run. Expect: Board/task state intact, run continues. (resumability). `K:N/browser` `S:pass`
- `SC-32` **Navigate away & back** — switch pages during a run. Expect: state intact, run uninterrupted. (UI integrity). `K:N/browser` `S:pass`

## S8 — Session continuity

- `SC-33` **Resume after restart** — restart builder mid-task. Expect: resume reuses same workspace cwd; task continues. (CLAUDE.md state/isolation). `K:N/browser` `S:pass`
- `SC-34` **Phase-run sidebar** — open a task detail. Expect: phase-level agent runs render in the sidebar. (IMP-022). `K:P/browser` `S:pass`

---

## Closeout rule

Durable findings → typed backlog at session close: `incident` for observed
product failures, `improvement` for required hardening, `optimization` for
efficiency/agent-experience. Builder defects also get an `IMP-*` row on
ROADMAP. Reusable traps → `builder memory`.
