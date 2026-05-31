# Resume — Session-Drop Protocol

> Read [README.md](README.md) first. `/start` and `/resume-session` automate *loading*; this is the *validation + mode-choice* protocol they don't encode.

Use when landing with prior context (continue/resume/"where did we leave off"; STATUS `Current Item In Flight` ≠ None; a `.claude/session-data/` checkpoint referenced). Brand-new unrelated question → answer directly, skip this. The *project* has state even when the *agent* is fresh.

## 1 — Orient

Read README → NORTH-STAR → STATUS before any state-changing call. Reading is cheap; misaligned action is expensive.

## 2 — Validate STATUS against reality (most-skipped step)

STATUS may be stale. Validate before acting; on mismatch **fix STATUS first** (wrong STATUS = Tier 1 fail):

| Field | Validate with |
| --- | --- |
| Current Item In Flight | [ROADMAP.md](ROADMAP.md) checkbox |
| Active Workspace | `ls <workspace>` |
| Active Runtime Lane | `builder agent runtime show --json` (dashboard wins) |
| Latest session id | `builder agent sessions --limit 5 --json` |
| Latest board snapshot | `builder board show --json` |
| Blockers | inspect blocked item + evidence |

## 3 — Choose mode

- **A — Continue in-flight item:** real unfinished item + "continue" clear from evidence (last commit/session/test). Work per [FIX-STANDARD.md](FIX-STANDARD.md); close when [EVALUATION.md](EVALUATION.md) Tier 1 passes; update STATUS.
- **A.1 — Continue Track B:** milestone M3.5 or autoresearch item. Confirm activation in [autoresearch README § Prerequisites](../autoresearch/README.md#prerequisites) (unmet → Mode C); read OPTIMIZE → METRICS → OPTIMIZE_IDEAS → HARNESS → COMPARE; resume next loop step.
- **B — Re-pick (clean handoff):** no/closed in-flight item. Use [ROADMAP § How To Pick](ROADMAP.md#how-to-pick-the-next-item); mark `in_progress`; begin.
- **C — Ask (ambiguous):** STATUS vs reality irreconcilable, decision needed, unresolved blocker, or user contradicts STATUS. **Don't start work** — `AskUserQuestion` with: what STATUS says, what reality shows, 2-4 reconciliations, your recommendation. Wait.

## 4 — Close

Update STATUS per its [Update Protocol](STATUS.md#update-protocol); durable learnings → `builder memory add` (source repo) per [FIX-STANDARD § Step 7](FIX-STANDARD.md#step-7--write-memory-back-if-durable); context drop anticipated → `/save-session`.

## Anti-patterns

Don't trust assistant-summary text as evidence (re-derive from CLI/dashboard/repo). Don't restart from PROGRESS.md alone (historical; STATUS is strategic). Don't open a new file to track what STATUS should track. Don't skip Step 2. Don't operate without knowing workspace + lane.
