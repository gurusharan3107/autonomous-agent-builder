# Resume — Session-Drop Protocol

> **Read [README.md](README.md) first.**

This file describes the exact protocol an agent follows when it lands in a session that has prior context (a previous agent worked on this project; the user is continuing work; the previous session crashed or was compacted; the operator wants to "pick up where we left off").

The protocol exists because the product itself is designed for session continuity. The agent must not start a fresh line of work just because *it* is fresh — the *project* has state that must be respected.

---

## When To Use This Protocol

Use this protocol in any of the following situations:

- The user said "continue", "resume", "where did we leave off", "pick up from README.md", "pick up from PLAN.md", or anything similar.
- [STATUS.md](STATUS.md) shows `Current Item In Flight` is not `None`.
- A previous session checkpoint file exists under `.claude/session-data/` and the user is referencing it.
- You arrived in this folder because the user pointed you at `docs/goal/` or `docs/goal/README.md` (or one of the legacy stubs `docs/PLAN.md`, `docs/GOAL.md`, `docs/MISSION.md`, which redirect here).

If none of the above is true (the user is asking a brand-new question unrelated to the live roadmap), do not run this protocol — answer the question directly.

---

## The Protocol

### Step 1 — Orient (always)

Read in this exact order, no skipping:

1. [README.md](README.md) — bootstrap rules and file map.
2. [NORTH-STAR.md](NORTH-STAR.md) — mission, success bar, differentiators.
3. [STATUS.md](STATUS.md) — current epoch, current milestone, current item, last action, next action, blockers, evidence pointers.

Do this before any tool call that would change repo state. Reading is cheap; misaligned action is expensive.

### Step 2 — Validate STATUS.md against reality

STATUS.md may be stale or wrong. Validate the most important fields before acting on them:

| STATUS.md field | Validation command | If it doesn't match |
| --- | --- | --- |
| `Current Item In Flight` | Read [ROADMAP.md](ROADMAP.md) for the named item; check its checkbox state | Fix STATUS.md to match ROADMAP; if ROADMAP itself is wrong, raise to user before acting |
| `Active Workspace` | `ls <workspace>` | Fix STATUS.md if path differs; ask user if no workspace exists |
| `Active Runtime Lane` | `builder agent runtime show --json` (from the active workspace) | Fix STATUS.md; runtime selection is dashboard-owned, so the dashboard wins |
| `Latest agent session id` (any lane) | `builder agent sessions --limit 5 --json` (from the active workspace) | Fix STATUS.md with the actual recent session id |
| `Latest board snapshot` | `builder board show --json` (from the active workspace) | Capture fresh; record in STATUS.md evidence pointers |
| Blockers | Inspect the blocked roadmap item and its referenced evidence | Clear if resolved; add if newly discovered |

If reality contradicts STATUS.md, **fix STATUS.md first**. A wrong STATUS.md is itself a Tier 1 resumability failure; never paper over it.

### Step 3 — Choose between three resume modes

After Step 2, classify the situation as one of these:

#### Mode A — Continue the in-flight item

Use when STATUS.md `Current Item In Flight` is a real, unfinished roadmap item *and* you understand what "continue" means from the available evidence (last commit, last session evidence, last test run).

- Mark the item still `in_progress` in STATUS.md (it should already be).
- Identify the next concrete step from the evidence (e.g., "test was failing on assertion X; fix the assertion").
- Do the work, following [FIX-STANDARD.md](FIX-STANDARD.md).
- Close the item when Tier 1 of [EVALUATION.md](EVALUATION.md) passes; update STATUS.md.

#### Mode B — Re-pick the next item (clean handoff)

Use when no item is in flight (`Current Item In Flight: None`), or the in-flight item is already closed but STATUS.md wasn't updated, or you just closed an item.

- Use [How To Pick The Next Item](ROADMAP.md#how-to-pick-the-next-item) from ROADMAP.
- Mark the new item `in_progress` in STATUS.md.
- Begin work.

#### Mode A.1 — Continue in-flight Track B (autoresearch) work

Use when `Current Milestone` is `M3.5` *or* `Current Item In Flight` references the autoresearch loop. Track B has its own read order that must run on top of Steps 1–3 above:

1. Confirm Track B is actually activated by checking the prerequisites in [`docs/autoresearch/README.md § Prerequisites`](../autoresearch/README.md#prerequisites). If any prerequisite is unmet, switch to Mode C (ask) — Track B was activated prematurely and that is itself a Tier 1 failure.
2. Read [`docs/autoresearch/README.md`](../autoresearch/README.md) in full (it is the entry point for the sister framework).
3. Follow its read order: `OPTIMIZE.md` → `METRICS.md` → `OPTIMIZE_IDEAS.md` → `HARNESS.md` → `COMPARE.md`.
4. Identify the in-flight artifact: which idea, which fixture, which baseline run, which compare result. Cross-check `docs/autoresearch/optimize_results.tsv` and `docs/autoresearch/per_prompt_results.tsv` for the latest rows.
5. Continue with the next loop step. Update [STATUS.md](STATUS.md) per its [Update Protocol](STATUS.md#update-protocol) when the loop produces a new `keep` or `discard` verdict.

If reality and STATUS disagree on whether Track B is active (e.g., STATUS says "M3.5 in progress" but `docs/autoresearch/README.md § Status` still says `DORMANT`), STATUS is wrong — fix it before doing anything else.

#### Mode C — Ask for direction (ambiguous)

Use when:

- STATUS.md and reality disagree in ways you can't reconcile (e.g., dashboard shows shipped feature X but STATUS.md says M1.2 is pending).
- The next concrete step depends on a product decision the operator must make.
- A blocker exists with no clear resolution path.
- The user's message contradicts STATUS.md.

In this mode, **do not start new work**. Use `AskUserQuestion` (or its equivalent) with a structured question that includes:

- What STATUS.md currently says.
- What reality currently shows.
- The 2-4 plausible reconciliations.
- Your recommendation.

Wait for direction before acting.

### Step 4 — Resume work

Once you've chosen a mode and (in Mode A/B) identified the concrete step:

- Use the right working surface: `docs/IMPROVEMENTS.md` for IMP work, `docs/SPRINT-PROGRESS.md` for sprint task work, `.memory/` for repo precedent (`builder memory search`), `builder knowledge` for system docs.
- Run the work end to end, including evidence capture.
- Update STATUS.md and the relevant working doc on every meaningful transition.

### Step 5 — Close the loop

When the resumed work reaches a natural stopping point (item done, milestone done, blocker hit, end of session):

1. Update [STATUS.md](STATUS.md) per its [Update Protocol](STATUS.md#update-protocol).
2. Record durable learnings via `builder memory add` from the Builder source repo per [FIX-STANDARD.md § Step 7](FIX-STANDARD.md#step-7--write-memory-back-if-the-learning-is-durable).
3. If the session is ending and you anticipate context drop, write a session checkpoint to `.claude/session-data/` via the `/save-session` skill — but treat that checkpoint as redundant with STATUS.md, not as the primary resume artifact. STATUS.md is the primary artifact.

---

## Anti-Patterns To Avoid On Resume

- **Don't trust assistant-summary text** as evidence of state. Re-derive state from `builder` CLI, dashboard, and repo inspection.
- **Don't restart from PROGRESS.md or SPRINT-PROGRESS.md alone.** Those are historical/sprint detail. The strategic state lives in STATUS.md.
- **Don't open a new file or abstraction to "track" what STATUS.md should track.** If STATUS.md is insufficient, fix STATUS.md or its [Update Protocol](STATUS.md#update-protocol).
- **Don't skip Step 2.** Reading STATUS.md without validating it against reality is the most common resume failure.
- **Don't start in-scope work in Mode C without resolving the ambiguity first.** Asking is cheap; corrective work is expensive.
- **Don't operate without knowing which workspace and which lane the current step targets.** Confirm both before any live test.

---

## Related Surfaces

- [`.claude/session-data/`](../../.claude/session-data/) — per-session checkpoints from the `/save-session` skill. Use as supplementary evidence on resume; never as the primary state.
- [`builder memory` workflow](../workflows/memory-retrieval-guide.md) — the procedure for loading repo precedent before any non-trivial fix.
- [`docs/workflows/system-improvement-loop.md`](../workflows/system-improvement-loop.md) — reproduce, trace true owner, fix, retest. Use this when resumed work is a bug investigation.
- [`docs/workflows/autonomous-lifecycle-validation.md`](../workflows/autonomous-lifecycle-validation.md) — dashboard-first lifecycle validation. Use this when resumed work is a live operator-flow test.
