---
name: save-session
description: "Snapshot tactical working context to `.claude/session-data/CURRENT.md` for the next session to resume from. Triggers: `/save-session`, 'save session', 'save progress', 'checkpoint'. Captures what `docs/goal/STATUS.md` does NOT — current intent, next concrete action, open blockers, mid-session learnings, key files touched, useful commands. Writes atomically via Bash heredoc (no Read→Write context bloat). Project-local replacement for the user-global save-session, which was removed because its body triggered compaction near context limit."
allowed-tools: Bash
---

# save-session — tactical checkpoint

> **Self-validate after edits.** Any change to this skill's files (SKILL.md, scripts/, references/, templates/, assets/) must be followed by `./scripts/validate.sh` from the skill directory. Hard findings → create-skill Optimize lane.

`docs/goal/STATUS.md` carries durable goal state (milestone, decisions, evidence pointers). This skill carries the *transient working context* that won't survive a session boundary otherwise.

## When to invoke

Operator says `/save-session`, "save session", "save progress", "checkpoint". Also reasonable to invoke proactively when context is at 70–80% and a natural pause point lands — saves cleanly *before* compaction risk, not after.

## What to write

Single file `.claude/session-data/CURRENT.md` (overwritten each save; git history retains versions). Eight sections, all terse:

| Section | Content |
|---|---|
| `time` | ISO 8601 UTC. |
| `branch` / `last_commit` | `git rev-parse --abbrev-ref HEAD` + `git rev-parse --short HEAD`. |
| `working_on` | 1–3 sentences. The current task in operator language, not internals. |
| `next_action` | One concrete sentence. What the next session should do FIRST. |
| `blockers` | Open questions only the operator can decide. Empty section if none. |
| `learnings` | Mid-session insights worth carrying forward (not durable enough for STATUS Recent Decisions, not generic enough for memory). Empty if none. |
| `key_files` | Path + one-line reason. ≤6 entries. |
| `useful_commands` | Shell commands proven useful this session (lint, test, etc.). ≤4 entries. |

## Pre-write check — ROADMAP tick detection

Before writing the heredoc, scan staged + unstaged diffs for ROADMAP `[ ] → [x]` flips. If any are detected and Hard Rules 13/14 aren't satisfied (CHANGELOG modified, STATUS Recent Decisions has a fresh dated line), surface that as a `blockers` line so the next session's `/start` flags it.

```bash
# Detect ROADMAP ticks in current diff
TICKS=$(git diff --cached --unified=0 docs/goal/ROADMAP.md docs/goal/ROADMAP.md 2>/dev/null | grep '^+' | grep -c '\[x\]' || echo 0)
UNTICKS=$(git diff --cached --unified=0 docs/goal/ROADMAP.md docs/goal/ROADMAP.md 2>/dev/null | grep '^-' | grep -c '\[ \]' || echo 0)
NET_TICKS=$(( TICKS - UNTICKS ))

# Also check unstaged
TICKS_U=$(git diff --unified=0 docs/goal/ROADMAP.md 2>/dev/null | grep '^+' | grep -c '\[x\]' || echo 0)
UNTICKS_U=$(git diff --unified=0 docs/goal/ROADMAP.md 2>/dev/null | grep '^-' | grep -c '\[ \]' || echo 0)
NET_TICKS=$(( NET_TICKS + TICKS_U - UNTICKS_U ))

# Check Hard Rule 14 compliance: CHANGELOG must be modified in same change set if any tick
CHANGELOG_MODIFIED=0
if git diff --cached --name-only 2>/dev/null | grep -q '^CHANGELOG.md$' || git diff --name-only 2>/dev/null | grep -q '^CHANGELOG.md$'; then
  CHANGELOG_MODIFIED=1
fi

# Check Hard Rule: STATUS Recent Decisions has a line dated today
TODAY=$(date +%Y-%m-%d)
STATUS_HAS_TODAY=0
if grep -q "^- \*\*$TODAY\*\*" docs/goal/STATUS.md 2>/dev/null; then
  STATUS_HAS_TODAY=1
fi

# Compose blocker line if needed
BLOCKER_LINE=""
if [ "$NET_TICKS" -gt 0 ]; then
  if [ "$CHANGELOG_MODIFIED" -eq 0 ] && [ "$STATUS_HAS_TODAY" -eq 0 ]; then
    BLOCKER_LINE="ROADMAP has $NET_TICKS new [x] tick(s) but CHANGELOG.md is unmodified AND STATUS Recent Decisions has no $TODAY entry — Hard Rules 13+14 violated; do BOTH before commit"
  elif [ "$CHANGELOG_MODIFIED" -eq 0 ]; then
    BLOCKER_LINE="ROADMAP has $NET_TICKS new [x] tick(s) but CHANGELOG.md is unmodified — Hard Rule 14 violated; add CHANGELOG entry before commit"
  elif [ "$STATUS_HAS_TODAY" -eq 0 ]; then
    BLOCKER_LINE="ROADMAP has $NET_TICKS new [x] tick(s) but STATUS Recent Decisions has no $TODAY entry — add the dated line before commit"
  fi
fi
```

If `$BLOCKER_LINE` is non-empty, include it as the first item in the `## blockers` section of the heredoc. Don't refuse the save (this skill doesn't block) — the goal is the next session's `/start` sees it via the tactical handoff.

## How to write (Bash heredoc — atomic, low context)

```bash
mkdir -p .claude/session-data
cat > .claude/session-data/CURRENT.md <<EOF
# Session checkpoint

**time:** $(date -u +%Y-%m-%dT%H:%M:%SZ)
**branch:** $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
**last_commit:** $(git rev-parse --short HEAD 2>/dev/null || echo unknown)

## working_on
<1–3 sentences of current intent>

## next_action
<one concrete sentence>

## blockers
${BLOCKER_LINE:+- $BLOCKER_LINE
}- <operator decision needed>  OR  *(none)*

## learnings
- <insight worth carrying>  OR  *(none)*

## key_files
- \`path/to/file.py\` — why it was touched
- ...

## useful_commands
- \`python3 -m pytest tests/foo.py -q\` — fast suite
- ...
EOF
```

Note the heredoc delimiter is **unquoted `EOF`** (not `'EOF'`) so `$BLOCKER_LINE` + `$(date ...)` + `$(git ...)` interpolate. All other dollar-sign references inside the body use escaped backticks for the example commands.

The heredoc is the entire write. **Do not** Read the previous CURRENT.md first — that bloats context. Overwrite blindly; `git diff` shows the delta.

## Hard rules

1. **Bash heredoc only.** Never use Read/Write/Edit tools for this skill's primary write — the whole point is context economy.
2. **Operator language.** Same vocabulary contract as `docs/goal/STATUS.md`: no internal jargon (lifecycle, sprint, dispatch, etc.) in `working_on` or `next_action`.
3. **Terse.** If a section would run past ~5 lines, you're capturing too much — that belongs in STATUS Recent Decisions or `builder memory add`, not here.
4. **No closeout propagation.** This skill does NOT touch ROADMAP / STATUS / CHANGELOG. It's purely tactical handoff. The next session's actual work generates those updates.
5. **No commit.** This skill writes the file only. `.claude/session-data/` is gitignored per existing repo convention — session-data is machine-local fast-resume, not durable cross-machine state. Cross-machine handoff rides on `docs/goal/STATUS.md`.

## Counterparts

- [`start`](../start/SKILL.md) — primary session-entry skill. Reads CURRENT.md only when fresh (<48h); framework + STATUS is the authoritative path.
- [`resume-session`](../resume-session/SKILL.md) — tactical-first session-entry skill. Reads CURRENT.md FIRST, then chains into `start` for framework + STATUS. Both paths converge on the same loaded state.
