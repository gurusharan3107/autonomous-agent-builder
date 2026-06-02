---
name: status
description: >
  Owns docs/goal/ governance + the operator overview page. CONSULT THIS SKILL
  BEFORE editing ROADMAP.md or STATUS.md — it defines the maintenance contract
  (where pending vs completed items live, compactness budgets, what is necessary,
  how it synthesizes into goal-overview.html). Six lanes: contract (read the
  rules before editing), lint (check ROADMAP/STATUS obey them + HTML is in sync),
  update (deterministically regenerate the overview's live numbers + priorities),
  open (launch the page), build (autonomous build loop — work through ROADMAP
  items in order, build each, mark [x], commit, /status update, repeat until done
  or dashboard-gated), test (for each closed [x] item with a pending T: token, run
  the appropriate test, upgrade the token to passed/na, commit, then /status update).
  Triggers: "/status open|update|lint|build|test", "update the goal overview",
  "refresh goal-overview", "before I edit the ROADMAP/STATUS", "lint the goal
  docs", "how should I update the roadmap", "start building", "work through the
  roadmap", "build the next item", "run tests", "test the built items", "mark
  backend tests", "check what needs testing". NOT for project quality audits (/audit).
allowed-tools: Bash, Read, Edit, Write, Agent
---

# status — govern docs/goal/ + the operator overview

`docs/goal/` is the project spine. `ROADMAP.md` + `STATUS.md` are the source of
truth; `goal-overview.html` is a generated read-only mirror. This skill owns the
**maintenance contract** for all three and the tooling that enforces it.

- **`/status` (contract)** → read the rules below before editing ROADMAP/STATUS.
- **`/status lint`** → check ROADMAP/STATUS obey the contract + HTML is in sync.
- **`/status update`** → regenerate the overview's numbers, priorities, meters.
- **`/status open`** → launch the page in a browser.

> **Before editing `ROADMAP.md` or `STATUS.md`, read the Maintenance Contract,
> then `/status lint` after.** Source of truth is the markdown; data flows one
> way: markdown → HTML. This skill only ever *reads* the markdown and *writes*
> the HTML — never the reverse.

## Maintenance Contract

### Write compact — always

Terse beats complete. Agent-audience: every reader pays tokens for every word.
- If a few words carry the meaning, never write the paragraph.
- One fact per line. Drop articles, hedges, narration, restated context.
- A pointer (commit / `test_…` / file:line / `.memory` slug) **replaces** a retelling — link, don't re-narrate.
- No status theatre: no "successfully", "as you can see", "it's worth noting", dated "PROVEN/Delivered" chains.
- Applies to **every** agent write to ROADMAP/STATUS — items, closeouts, decisions, in-flight notes alike.

Default to the shortest form that survives a re-read by a cold agent. When in doubt, cut.

### Where things live (one owner per concern)

| Surface | Holds | Does NOT hold |
| --- | --- | --- |
| `ROADMAP.md` | The forward spine. One checkbox line per item, grouped under `### M<x.y>`. Open = intent + acceptance + `Pn`. Closed = outcome + one evidence pointer. | Multi-step work-logs, dated delivery chains, root-cause prose. |
| `STATUS.md` | The "now": current epoch/milestone, **Current Item In Flight** (the running log), Next Action, Blockers, Evidence Pointers. | The full roadmap; closure history. |
| `CHANGELOG.md` / git / `.memory/` | Durable closure detail: root cause, fix, file:line, test names, commits. | — |
| `goal-overview.html` | Generated synthesis: status snapshot, per-milestone meters, **Open priorities** (capped view), **Tasks** matrix (last; every checkbox + testing ticks). Regenerated, never hand-edited. | Anything not in a `<!-- gen:* -->` region or the `#artifact-data` block. |

### Item shape

- **Open** — `` - [ ] `Pn` **<id/title>** — <one-line intent + what "done" looks like>. ``
  Carries a priority token (`P0`–`P3`); without it the item is invisible to the
  overview's Open-priorities view. State acceptance, not a work-log. **Tag both test
  lanes** — `` `T:backend:…` `` + `` `T:browser:…` `` (a new open item is normally
  `:pending`/`:pending`, or `:na` for whichever lane can't reach it).
- **Closed** — `` - [x] **<id>** — <one-line outcome>. <evidence pointer>. `` where the
  pointer is a commit hash, `test_…` name, file, `.memory` slug, or date. The full
  story moves to git/CHANGELOG/`.memory`; do not re-narrate it inline. **Tag both test
  lanes** — bare `` `T:backend` ``/`` `T:browser` `` only with real evidence, else `:na`.
- **Splits** (e.g. `IMP-027a/b/c`) are allowed as child bullets; running logs are not.
- **Metadata tokens** (feed the Tasks matrix; excluded from char budgets):
  `` `IF` `` on an open item = in-flight bucket (else pending). **Every checkbox carries
  both a `` `T:backend` `` and a `` `T:browser` `` token** (lint WARNs on a missing lane —
  there is no untagged "—" resting state; "—" only ever means *not yet triaged*). Each lane
  is one of three states: bare (`` `T:backend` ``) = that test **passed** → ✓; `:pending`
  (`` `T:browser:pending` ``) = testable in that lane but **not yet verified** → ⏳; `:na`
  (`` `T:browser:na` ``) = that lane **structurally cannot** test the item (pure
  runtime/infra/refactor/storage/deletion/CLI/docs) → ✗. Backend = builder-CLI/pytest;
  browser = `/hermes-chrome` real-browser. Use the bare pass form only on real evidence (a
  `test_…`/count for backend; live-browser proof for browser); otherwise `:pending`/`:na`.

### Compactness budgets (linted)

- Open item ≤ **240** chars of text; closed item ≤ **160**. These are ceilings, not
  targets — aim well under. A good open item is one line; a good closed item is
  outcome + pointer.
- One canonical entry per id. A re-opened/re-diagnosed item is **edited in place**,
  not appended as a second `[x]`/`[ ]` line with the same id.
- No `Delivered/Remaining/PROVEN/CORRECTION/PARTIAL DELIVERY` chains inside an item —
  that running detail belongs in STATUS.md **Current Item In Flight**.

### Synthesis into the overview

`/status update` regenerates, from the markdown only:
- `#artifact-data` JSON (derivable keys; `tiers`/`source` preserved).
- `<!-- gen:* -->` markers: `snapshot_date`, `epoch`, `milestone`, `roadmap_totals`,
  `priorities`, `tasks`.
- Per-milestone meters (`.ms` blocks): `<small>done / total</small>` + bar width.

**Open priorities** = open `[ ]` items carrying a `Pn` token, sorted P0→P3 then file
order, then **capped per level** by `PRI_CAP` (P0:3 P1:3 P2:3 P3:1) into a curated
view. Tag an item by adding the token; re-prioritize by editing it. The full prioritized
backlog (uncapped) is in the Tasks matrix.

**Tasks** = every roadmap checkbox, bucketed completed → in-flight → pending, each row
milestone + `Pn` + label + Done/Browser/Backend ticks (driven by the `IF`/`T:` tokens):
✓ passed · ⏳ pending & doable · ✗ not applicable to that lane · — not yet triaged (lint
WARNs — every checkbox should be tagged in both lanes). Rendered last on the page.

## Workflow

### Lane: lint
```bash
python3 .claude/skills/status/scripts/lint_goal_docs.py            # report; exit 2 on ERROR
python3 .claude/skills/status/scripts/lint_goal_docs.py --strict   # exit 1 on WARN too
```
Report ERROR findings first (structural — block until fixed), then WARN (over-budget /
missing priority / missing evidence / inline work-log / duplicate id). Fix the
**source markdown**, never the HTML. An HTML-sync ERROR means run `/status update`.

### Lane: update
```bash
python3 .claude/skills/status/scripts/build_goal_overview.py
```
Report the printed change summary (`artifact-data JSON`, `gen:priorities`,
`meters[...]`, totals) or "no change — already in sync". On non-zero exit, surface the
error verbatim and STOP (missing file/marker, or unparseable STATUS Current Position).
Prove idempotency with `--check` (exit 0 = in sync). Offer to `/status open`.

### Lane: open
```bash
f=docs/goal/goal-overview.html
if grep -qi microsoft /proc/version 2>/dev/null; then
  explorer.exe "$(wslpath -w "$f")" 2>/dev/null \
    || cmd.exe /c start "" "$(wslpath -w "$f")" 2>/dev/null \
    || powershell.exe -NoProfile -Command "Start-Process '$(wslpath -w "$f")'"
else
  xdg-open "$f" >/dev/null 2>&1 &
fi
```
Report the path. **On WSL2 `xdg-open` silently fails** — route through the Windows host
(`explorer.exe` + `wslpath -w`; rc=1 is success). If no opener works, give the path.

### Lane: build

Autonomous build loop. Runs without user intervention; pauses only when the next
item is dashboard-gated (needs live builder dashboard / browser session / external
service login) or on error.

**Capability levers used:**
- **Subagents** — each item's build work is delegated to a context-isolated subagent
  so the coordinator loop stays lean across many items.
- **TaskCreate/TaskUpdate** — in-session tracking per item; survives compaction.
- **PushNotification** — alerts when the loop completes or stalls.
- **No hooks** — this runs in a managed harness where hooks are unavailable.

**Algorithm** (loop until exit condition holds):

```bash
# 1. Find next item
item=$(python3 .claude/skills/status/scripts/next_build_item.py [M<x.y>])
# exit 1 = no more items → loop complete
```

For each item returned:

1. **Gate: Linux-ok?**
   - `dashboard_gated=true` → print blocker reason, send PushNotification, **stop**.
   - `dashboard_gated=false` → proceed.

2. **TaskCreate** — `{title: item.id, status: "in_progress"}`. Prevents re-doing
   on compaction.

3. **Route to domain skill** — before dispatching, identify the right skill for this item:

   | Item keyword | Skill to preload in subagent |
   |---|---|
   | Browser / UI / dashboard / widget / overlay | `hermes-chrome` or `hermes-chrome-bridge` |
   | Builder / orchestrator / backlog / board / sprint | `builder-test` |
   | Self-optimization / prompt tuning / token budget | `self-optimize` |
   | Autoresearch / baseline / iterate / fix lane | `autoresearch` |
   | Architecture / quality gate / boundary | reference `CLAUDE.md` quality gates |
   | Agent SDK / Claude runtime / session / hooks | `claude-api` skill or Claude SDK rubric |

   The subagent's **first action** is to invoke that skill via the Skill tool. The skill carries
   proven patterns, API shapes, and architecture invariants — the subagent must not re-derive them
   from scratch.

4. **Dispatch subagent** (context-isolated):
   - Prompt: item id + acceptance clause + the domain skill name to invoke first (from routing table above).
   - The subagent: (1) invokes the domain skill, (2) reads relevant existing source files, (3) writes/extends Python files, scripts, or docs using the skill's guidance.
   - Returns: `{success: bool, files_changed: [...], evidence: str, note: str}`.

5. **On subagent success — update ROADMAP, regenerate overview, then commit (in this order):**
   ```bash
   # a. Mark item [x] in ROADMAP.md
   python3 .claude/skills/status/scripts/close_build_item.py \
     --raw-line "<item.raw_line>" \
     --evidence "<evidence>" \
     --note "<note>"

   # b. Update STATUS.md Current Item In Flight (inline edit)

   # c. /status update — regenerate goal-overview.html BEFORE committing
   python3 .claude/skills/status/scripts/build_goal_overview.py
   # Surface any non-zero exit and stop — do not commit a stale overview.

   # d. Lint (non-blocking on WARN; ERROR blocks commit)
   python3 .claude/skills/status/scripts/lint_goal_docs.py

   # e. Commit: ROADMAP.md + STATUS.md + goal-overview.html + all source files together
   git add ROADMAP.md STATUS.md docs/goal/goal-overview.html <changed files>
   git commit -m "build(M<x.y>): <item.id> — <note>

   <evidence>

   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
   ```
   **Order is mandatory:** ROADMAP updated → overview regenerated → commit.
   The commit always contains both the ROADMAP change and the up-to-date HTML.

6. **TaskUpdate** — mark `completed`.

7. **Loop** — go back to step 1.

**Exit conditions:**
- `next_build_item.py` exits 1 → all items done → send PushNotification
  "Build loop complete: all items in M<x.y> closed. Overview current."
- `dashboard_gated=true` → send PushNotification "Build loop paused — next item needs
  live dashboard: <reason>. Resume after setup."
- Subagent returns `success=false` → log the failure, send PushNotification, stop.
  Do not commit partial work.

**Resumability:** Because each item is committed before moving to the next, a
re-run of `/status build` after an interruption automatically skips already-closed
items (they are `[x]` in ROADMAP and `next_build_item.py` returns only `[ ]` lines).

**Subagent prompt template:**

```
You are building one autonomous-agent-builder roadmap item.

STEP 1 — invoke the domain skill first (Skill tool):
  <skill-name from routing table>
The skill carries proven patterns, API shapes, and architecture invariants for this
domain. Do not re-derive them — use what the skill loads.

STEP 2 — read existing src/ files before writing anything new.
  Reuse over reinvent. The existing module interfaces are authoritative.

STEP 3 — build the item:
ITEM: <item.body>
MILESTONE: <item.milestone>  PRIORITY: <item.priority>
ACCEPTANCE: <item.body's "done looks like" clause>
PLATFORM: Linux/WSL2.

STEP 4 — if architecture compliance is uncertain, check CLAUDE.md quality gates
  before finishing. They catch drift against this repo's invariants.

Return ONLY this JSON when done:
{"success": true/false, "files_changed": [...],
 "evidence": "<file or short description>", "note": "<one-line outcome>"}
```

### Lane: test

Run tests for all closed `[x]` items that still have `T:backend:pending` or
`T:browser:pending` tokens. Upgrades tokens to bare (passed) or leaves `:pending`
with a failure note. Always runs `/status update` at the end.

**Capability levers:**
- **Sequential per-item loop** — test → update token → `/status update` → commit → next. One commit per item so progress is always visible in the overview and history is granular.
- **Subagent per test** (context isolation) — the test execution for each item runs in a context-isolated subagent; parent coordinator stays lean across many items.
- **Monitor tool** — streams test command output live instead of blocking.
- **TaskCreate per item** — tracks each item independently; survives compaction.
- **PushNotification** — final summary on loop completion.
- **No hooks** — managed harness; not available.

**Project-specific reality (autonomous-agent-builder):**
- `T:browser` = `:na` for backend-only items — pure orchestrator/DB/CLI items have no web UI.
- `T:backend` = pytest or `builder` CLI on Linux/WSL2. Most items are directly testable.
- `T:browser:pending` = use `/hermes-chrome` real-browser verification for UI/dashboard items.
- The test lane classifies, runs what it can directly, and lists dashboard-gated items with clear reasons.

**Algorithm — sequential per-item loop:**

```bash
# 1. Load all pending-test items once (exit 1 = none → done)
items=$(python3 .claude/skills/status/scripts/pending_test_items.py [M<x.y>])
```

For **each item one at a time**:

2. **TaskCreate** — `{title: item.id, status: "in_progress"}`.

3. **Classify** (from item's `linux_backend` field):
   - `testable` — run `item.backend_cmd` directly (pytest / builder CLI).
   - `browser_testable` — dispatch hermes-chrome subagent.
   - `dashboard_gated` — skip execution; result is `pending` with `reason` as note.
   - `na` — result is `na`; no execution needed.

4. **Run the test** (for `testable`):
   - Execute `item.backend_cmd` via Bash. Use Monitor tool to stream output live.
   - Capture exit code: 0 → `passed`; non-zero → `pending` with failure note.
   - For `browser_testable`: dispatch hermes-chrome subagent; collect pass/fail.
   - For `dashboard_gated` / `na`: skip to step 5 with pre-determined result.

5. **Update the T: token in ROADMAP.md immediately:**
   ```bash
   python3 .claude/skills/status/scripts/update_t_token.py \
     --raw-line "<item.raw_line>" \
     --lane backend \
     --result passed|pending|na \
     [--note "<failure or dashboard_reason>"]
   # Also update T:browser if item.browser == "pending":
   python3 .claude/skills/status/scripts/update_t_token.py \
     --raw-line "<item.raw_line>" --lane browser --result passed|pending|na
   ```

6. **`/status update` — regenerate goal-overview.html BEFORE committing:**
   ```bash
   python3 .claude/skills/status/scripts/build_goal_overview.py
   # Non-zero exit → surface error, stop loop.
   ```

7. **Commit — ROADMAP.md + goal-overview.html together:**
   ```bash
   git add docs/goal/ROADMAP.md docs/goal/goal-overview.html
   git commit -m "test(<milestone>): <item.id> — <result>

   T:backend=<result> | <note or dashboard_reason>

   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
   ```
   **Order is mandatory:** token updated → overview regenerated → commit.
   Both files always travel together in the same commit.

8. **TaskUpdate** — mark `completed`.

9. **Loop** — next item from the list.

**Exit (loop done):** send PushNotification with summary:
`"Test loop complete: <n> passed, <n> browser-verified, <n> dashboard-gated, <n> na. Overview current."`

**Resumability + idempotency:** `update_t_token.py` no-ops if the token already matches. Re-running `/status test` skips items whose tokens are already upgraded (they won't appear in `pending_test_items.py` output).

**Dashboard-gated items report** (printed per item + in final PushNotification):
```
DASHBOARD-GATED — <item.id>: <reason>. Verify via live builder dashboard.
```

## Hard rules

1. **Consult the Maintenance Contract before editing ROADMAP/STATUS; `/status lint`
   after.** Non-compliant edits are the thing this skill exists to prevent.
2. **Never hand-edit the live numbers in `goal-overview.html`.** Run the generator —
   hand edits re-drift on the next run.
3. **`ROADMAP.md` / `STATUS.md` are the source of truth — never written from this
   skill.** Update flows one way: markdown → HTML. (The agent edits the markdown by
   hand following the contract; the *skill scripts* only read it.)
4. **Never touch hand-authored narrative prose** in the HTML. The generator rewrites
   only the `#artifact-data` block, `<!-- gen:NAME -->` regions, and per-milestone
   meters. A number outside those needs a new marker, not a free edit.
5. **Trust exit codes.** Generator non-zero = missing file/marker / unparseable STATUS.
   Linter exit 2 = a structural ERROR. Surface them; never paper over by editing HTML.
6. **Counting + priority semantics are the scripts', not a naive grep.** Closed/open =
   `[x]`/`[ ]` occurrences within milestone sections (from the first `### M<x.y>`);
   priorities = inline `` `Pn` `` tokens on open items.

## CLOSEOUT (every run)

1. **Contract lane**: confirm you surfaced the where-it-lives + budgets before any
   ROADMAP/STATUS edit, and ran `/status lint` after.
2. **Lint lane**: report ERROR/WARN counts; ERRORs block.
3. **Update lane**: confirm the generator exited 0 + report the change summary (or "no
   change"); re-run `--check` to prove idempotency if you patched.
4. **Open lane**: confirm the launch command was issued + report the path.
5. **Build lane**: after each item — confirm commit hash + item closed in ROADMAP +
   `/status update` ran. On loop exit — report total built, dashboard-gated skipped (with
   reasons), PushNotification sent.
6. **Test lane**: for each item — confirm token updated + `/status update` ran + commit
   hash (ROADMAP + goal-overview in same commit). Final: counts passed / browser-verified /
   dashboard-gated / na, PushNotification sent.
7. **Staleness scan** (when editing this skill): verify
   `scripts/build_goal_overview.py` + `scripts/lint_goal_docs.py` + `scripts/mine_sessions.py`
   exist and the six `<!-- gen:* -->` markers (`snapshot_date`, `epoch`, `milestone`,
   `roadmap_totals`, `priorities`, `tasks`) + the `#artifact-data` block still exist in
   `goal-overview.html`. Missing markers make the generator fail loudly — restore them.

## Reference

- Linter: [`scripts/lint_goal_docs.py`](scripts/lint_goal_docs.py) — contract checks +
  severities + `--strict`.
- Generator: [`scripts/build_goal_overview.py`](scripts/build_goal_overview.py) —
  parsing rules, patch targets, priority parsing + `PRI_CAP`, `--check` idempotency.
- Session miner: [`scripts/mine_sessions.py`](scripts/mine_sessions.py) — self-contained
  transcript content-miner for **deriving `T:` testing evidence**. E.g.
  `python3 scripts/mine_sessions.py --preset browser_testing --project-filter <repo> --since 60d`
  for browser-test signal; backend evidence is usually the closed item's own `test_…`
  pointer (more reliable than transcript grep). Verify a hit is real before tagging —
  exclude quoted error strings (`'test_p'`) and jsdom e2e (≠ real-browser).
- Source of truth: `docs/goal/ROADMAP.md`, `docs/goal/STATUS.md`.
- Artifact: `docs/goal/goal-overview.html` (hand-authored prose + generated regions).
- Build loop helpers (create before using `/status build`):
  - [`scripts/next_build_item.py`](scripts/next_build_item.py) — find + classify next `[ ]` item; exit 1 = none left.
  - [`scripts/close_build_item.py`](scripts/close_build_item.py) — mark item `[x]` with evidence pointer.
- Test loop helpers (create before using `/status test`):
  - [`scripts/pending_test_items.py`](scripts/pending_test_items.py) — find `[x]` items with `:pending` T: tokens; classifies testability + emits `backend_cmd`.
  - [`scripts/update_t_token.py`](scripts/update_t_token.py) — idempotent T:lane token upgrade (pending→passed/na); safe to re-run.
