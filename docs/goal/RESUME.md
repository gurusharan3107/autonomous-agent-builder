# Resume — Session-Drop Protocol

> Read [README.md](README.md) first.

Protocol when an agent lands in a session with prior context (previous agent worked here; user is continuing; previous session crashed/compacted; "pick up where we left off").

Product is designed for session continuity. Don't start fresh just because the *agent* is fresh — the *project* has state.

---

## When to use

- User said "continue", "resume", "where did we leave off", "pick up from README/PLAN.md", etc.
- [STATUS.md](STATUS.md) `Current Item In Flight` ≠ `None`.
- A checkpoint exists under `.claude/session-data/` and user referenced it.
- User pointed you at `docs/goal/` or its legacy stubs (`docs/PLAN.md`, `GOAL.md`, `MISSION.md`).

Brand-new question unrelated to the live roadmap → answer directly, skip this protocol.

---

## The Protocol

### Step 1 — Orient

Read in order, no skipping:

1. [README.md](README.md)
2. [NORTH-STAR.md](NORTH-STAR.md)
3. [STATUS.md](STATUS.md)

Before any state-changing tool call. Reading is cheap; misaligned action is expensive.

### Step 2 — Validate STATUS.md against reality

STATUS may be stale. Validate before acting:

| STATUS field | Validation | If mismatched |
| --- | --- | --- |
| `Current Item In Flight` | Read [ROADMAP.md](ROADMAP.md) for the item; check checkbox | Fix STATUS; if ROADMAP itself is wrong, raise to user |
| `Active Workspace` | `ls <workspace>` | Fix STATUS; ask user if no workspace |
| `Active Runtime Lane` | `builder agent runtime show --json` (in workspace) | Fix STATUS — dashboard wins |
| `Latest agent session id` | `builder agent sessions --limit 5 --json` | Fix STATUS with actual recent id |
| `Latest board snapshot` | `builder board show --json` | Capture fresh; record in STATUS |
| Blockers | Inspect blocked item + evidence | Clear if resolved; add if new |

Reality contradicts STATUS → **fix STATUS first**. Wrong STATUS = Tier 1 resumability failure.

### Step 3 — Choose mode

#### Mode A — Continue the in-flight item

STATUS `Current Item In Flight` is a real unfinished item AND you understand "continue" from evidence (last commit, last session, last test).

- Confirm `in_progress` in STATUS.
- Identify next concrete step from evidence.
- Do the work per [FIX-STANDARD.md](FIX-STANDARD.md).
- Close when Tier 1 of [EVALUATION.md](EVALUATION.md) passes; update STATUS.

#### Mode A.1 — Continue Track B (autoresearch)

`Current Milestone` is `M3.5` *or* in-flight item references autoresearch:

1. Confirm activation via [`docs/autoresearch/README.md § Prerequisites`](../autoresearch/README.md#prerequisites). Unmet → switch to Mode C (premature activation = Tier 1 fail).
2. Read [`docs/autoresearch/README.md`](../autoresearch/README.md) fully.
3. Read order: `OPTIMIZE.md` → `METRICS.md` → `OPTIMIZE_IDEAS.md` → `HARNESS.md` → `COMPARE.md`.
4. Identify in-flight artifact: which idea / fixture / baseline / compare. Cross-check `optimize_results.tsv` + `per_prompt_results.tsv`.
5. Continue next loop step. Update [STATUS.md](STATUS.md) per its [Update Protocol](STATUS.md#update-protocol) on new `keep`/`discard`.

STATUS says M3.5 in progress but autoresearch README says `DORMANT` → STATUS is wrong; fix first.

#### Mode B — Re-pick next item (clean handoff)

No in-flight item, or in-flight closed but STATUS not updated, or you just closed one.

- Use [How To Pick The Next Item](ROADMAP.md#how-to-pick-the-next-item).
- Mark `in_progress` in STATUS.
- Begin.

#### Mode C — Ask for direction (ambiguous)

When:

- STATUS and reality disagree irreconcilably (e.g., dashboard shipped feature X but STATUS says M1.2 pending).
- Next step needs an operator product decision.
- Blocker with no clear resolution.
- User's message contradicts STATUS.

**Don't start work.** Use `AskUserQuestion` with: what STATUS says, what reality shows, 2-4 reconciliations, your recommendation. Wait.

### Step 4 — Resume work

Mode A/B with concrete step in hand:

- Right surface: `docs/IMPROVEMENTS.md` (IMPs), `docs/SPRINT-PROGRESS.md` (sprint), `.memory/` via `builder memory search` (precedent), `builder knowledge` (system docs).
- Run end to end with evidence capture.
- Update STATUS + relevant working doc on every meaningful transition.

### Step 5 — Close

At natural stop (item done / milestone done / blocker / session end):

1. Update [STATUS.md](STATUS.md) per [Update Protocol](STATUS.md#update-protocol).
2. Durable learnings → `builder memory add` from source repo per [FIX-STANDARD.md § Step 7](FIX-STANDARD.md#step-7--write-memory-back-if-durable).
3. Session ending + context drop anticipated → `/save-session` checkpoint. Redundant with STATUS, not primary.

---

## Anti-patterns

- **Don't trust assistant-summary text** as evidence. Re-derive from `builder` CLI / dashboard / repo.
- **Don't restart from PROGRESS.md or SPRINT-PROGRESS.md alone.** Those are historical; strategic state is STATUS.
- **Don't open a new file to "track" what STATUS should track.** Fix STATUS or its [Update Protocol](STATUS.md#update-protocol).
- **Don't skip Step 2.** Reading STATUS without validating = most common resume failure.
- **Don't start work in Mode C without resolving ambiguity.** Asking is cheap; corrective work is expensive.
- **Don't operate without knowing workspace + lane.** Confirm both before any live test.

---

## Related

- [`.claude/session-data/`](../../.claude/session-data/) — per-session checkpoints; supplementary, not primary.
- [`docs/workflows/memory-retrieval-guide.md`](../workflows/memory-retrieval-guide.md) — precedent loading.
- [`docs/workflows/system-improvement-loop.md`](../workflows/system-improvement-loop.md) — for bug-investigation resumes.
- [`docs/workflows/autonomous-lifecycle-validation.md`](../workflows/autonomous-lifecycle-validation.md) — for live operator-flow resumes.
