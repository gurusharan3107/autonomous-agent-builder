---
name: status
description: >
  Owns docs/goal/ governance + the operator overview page. CONSULT THIS SKILL
  BEFORE editing ROADMAP.md or STATUS.md — it defines the maintenance contract
  (where pending vs completed items live, compactness budgets, what is necessary,
  how it synthesizes into goal-overview.html). Four lanes: contract (read the
  rules before editing), lint (check ROADMAP/STATUS obey them + HTML is in sync),
  update (deterministically regenerate the overview's live numbers + priorities),
  open (launch the page). Triggers: "/status open|update|lint", "update the goal
  overview", "refresh goal-overview", "before I edit the ROADMAP/STATUS", "lint
  the goal docs", "how should I update the roadmap". NOT for project quality
  audits (/audit).
allowed-tools: Bash
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
  overview's Open-priorities view. State acceptance, not a work-log.
- **Closed** — `` - [x] **<id>** — <one-line outcome>. <evidence pointer>. `` where the
  pointer is a commit hash, `test_…` name, file, `.memory` slug, or date. The full
  story moves to git/CHANGELOG/`.memory`; do not re-narrate it inline.
- **Splits** (e.g. `IMP-027a/b/c`) are allowed as child bullets; running logs are not.
- **Metadata tokens** (feed the Tasks matrix; excluded from char budgets):
  `` `IF` `` on an open item = in-flight bucket (else pending). `` `T:backend` ``
  / `` `T:browser` `` = that test passed; append `:pending` (`` `T:browser:pending` ``)
  for in-progress. Backend = builder-CLI/pytest; browser = `/hermes-chrome` real-browser.
  Add only on real evidence (a `test_…`/count for backend; live-browser proof for browser).

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
milestone + `Pn` + label + Done/Browser/Backend ticks (driven by the `IF`/`T:` tokens).
Rendered last on the page.

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
5. **Staleness scan** (when editing this skill): verify
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
