---
name: save-session
description: "Snapshot tactical working context to `.claude/session-data/CURRENT.md` for the next session to resume from. Triggers: `/save-session`, 'save session', 'save progress', 'checkpoint'. Captures what `docs/goal/STATUS.md` does NOT — current intent, next concrete action, open blockers, mid-session learnings, key files touched, useful commands. Writes atomically via Bash heredoc (no Read→Write context bloat). Project-local replacement for the user-global save-session, which was removed because its body triggered compaction near context limit."
allowed-tools: Bash
---

# save-session — tactical checkpoint

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

## How to write (Bash heredoc — atomic, low context)

```bash
mkdir -p .claude/session-data
cat > .claude/session-data/CURRENT.md <<'EOF'
# Session checkpoint

**time:** 2026-05-23T18:42:00Z
**branch:** master
**last_commit:** 7893bdd

## working_on
<1–3 sentences of current intent>

## next_action
<one concrete sentence>

## blockers
- <operator decision needed>  OR  *(none)*

## learnings
- <insight worth carrying>  OR  *(none)*

## key_files
- `path/to/file.py` — why it was touched
- ...

## useful_commands
- `python3 -m pytest tests/foo.py -q` — fast suite
- ...
EOF
```

The heredoc is the entire write. **Do not** Read the previous CURRENT.md first — that bloats context. Overwrite blindly; `git diff` shows the delta.

## Hard rules

1. **Bash heredoc only.** Never use Read/Write/Edit tools for this skill's primary write — the whole point is context economy.
2. **Operator language.** Same vocabulary contract as `docs/goal/STATUS.md`: no internal jargon (lifecycle, sprint, dispatch, etc.) in `working_on` or `next_action`.
3. **Terse.** If a section would run past ~5 lines, you're capturing too much — that belongs in STATUS Recent Decisions or `builder memory add`, not here.
4. **No closeout propagation.** This skill does NOT touch ROADMAP / STATUS / CHANGELOG. It's purely tactical handoff. The next session's actual work generates those updates.
5. **No commit.** This skill writes the file only. `.claude/session-data/` is gitignored per existing repo convention — session-data is machine-local fast-resume, not durable cross-machine state. Cross-machine handoff rides on `docs/goal/STATUS.md`.

## Counterpart

[`resume-session`](../resume-session/SKILL.md) reads this file + STATUS.md + recent git log to synthesize "here's where you left off" at session start.
