---
name: resume-session
description: "Tactical-first session-entry skill. Use when the prior session ran /save-session and you want CURRENT.md's tactical context surfaced FIRST. Reads `.claude/session-data/CURRENT.md` (current intent, next action, blockers, learnings), then chains into the `start` skill via the Skill tool so framework + STATUS + drift + git log also load. Both `/resume-session` and `/start` converge to the same fully-loaded state; this skill just changes which block heads the synthesis. Triggers: `/resume-session`, 'resume session', 'continue where I left off', 'pick up where we left off'. Does NOT auto-execute. If `.claude/session-data/CURRENT.md` is missing or >48h old, falls back directly to `start` for the framework-first path."
allowed-tools: Bash, Read
---

# resume-session — tactical-first session entry

> **Self-validate after edits.** Any change to this skill's files (SKILL.md, scripts/, references/, templates/, assets/) must be followed by `./scripts/validate.sh` from the skill directory. Hard findings → create-skill Optimize lane.

Counterpart to [`start`](../start/SKILL.md). When the prior session ran `/save-session`, `CURRENT.md` carries actionable handoff (current intent, next concrete action, open blockers, mid-session learnings) that `docs/goal/STATUS.md` deliberately does not. This skill surfaces that block FIRST, then chains into `start` so framework + STATUS + drift + git log also load. Both entry paths converge on the same fully-loaded state.

## When to invoke

- Operator says `/resume-session`, "resume session", "continue where I left off", "pick up where we left off".
- Operator explicitly knows the prior session ran `/save-session` and wants the tactical layer at the top of the briefing.

**Use `/start` instead** if you don't know whether the prior session saved, or you want framework + STATUS at the top.

## Workflow

### Step 1 — Read tactical handoff

```bash
CURRENT=.claude/session-data/CURRENT.md
if [ ! -f "$CURRENT" ]; then
  echo "(no CURRENT.md — falling back to /start for framework-first entry)"
  exit 0  # signal to skip Step 2's tactical block; Step 3's chain into start still fires
fi

age_h=$(( ( $(date +%s) - $(stat -c %Y "$CURRENT") ) / 3600 ))
if [ "$age_h" -ge 48 ]; then
  echo "(CURRENT.md is ${age_h}h old — too stale; falling back to /start)"
  exit 0
fi

echo "--- CURRENT.md (${age_h}h old) ---"
cat "$CURRENT"
```

### Step 2 — Print the tactical synthesis block

From the CURRENT.md output, synthesize a compact "**From prior session**" block:

- **Where you left off** — pull from `working_on` (1–3 sentences).
- **Next action** — verbatim from `next_action`.
- **Blockers** — if any; otherwise omit.
- **Mid-session learnings** — if any; otherwise omit.

If `CURRENT.md.time` is more than 24h old, prefix the block with `"(checkpoint is ${age_h}h old — verify against STATUS + git log below)"`.

If Step 1 fell back (missing or >48h stale), skip this block entirely.

### Step 3 — Chain into `start` for framework + STATUS load

Invoke the `start` skill via the Skill tool with no args. `start` will:

- Read `AGENTS.md` + `docs/goal/README.md`.
- Print STATUS Current Position + Last Update + top Recent Decisions.
- Run `check_status_drift.py` for drift warnings.
- Print recent git log.
- Synthesize its own briefing.

The combined operator-facing output: tactical block (this skill's Step 2) → framework + STATUS briefing (start's synthesis). `start` will independently re-check CURRENT.md in its own Step 3; that's fine — the file is small and the read is cheap. The operator sees one continuous briefing.

### Step 4 — Wait for operator direction

`start` ends with "Suggested next move: … Ready to proceed?". Do not auto-execute the next action. The operator picks the direction.

## Hard rules

1. **Read-only.** No writes. Drift warnings and tactical block are advisory.
2. **Always chain into `start`.** Never skip the framework + STATUS load. If CURRENT.md is missing or stale, fall back directly to `start` — never emit a tactical-only briefing.
3. **Honest about staleness.** Flag CURRENT.md age inline when 24–48h old; ignore when >48h.
4. **No auto-execution.** Operator must say "go" before any state-changing tool runs.
5. **Do not duplicate `start`'s logic.** This skill is intentionally thin — Step 1 reads CURRENT.md, Step 2 synthesizes the tactical block, Step 3 delegates everything else.

## Counterparts

- [`start`](../start/SKILL.md) — primary entry skill; this skill chains into it.
- [`save-session`](../save-session/SKILL.md) — writes the CURRENT.md this skill reads.
