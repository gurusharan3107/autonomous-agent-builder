---
name: cleanup
description: Audit and prune the repo's docs/, skills/, and registry surfaces for orphan files, deprecated stubs, historical-only content, verbose drift, dangling refs, misrouted content, and duplicates. Apply the agent-audience concise rule. Use when the operator says "cleanup pass", "prune docs", "delete dead docs", "audit docs for stale/orphan", "compact docs", "fix dangling refs", "is anything in docs/ stale", "find duplicates", or any variant pairing cleanup/audit/prune/compact/dead-weight/stale with docs/skills/refs. Use BEFORE introducing new docs (dedupe against existing) and AFTER large refactors (refs drift). Four lanes via AskUserQuestion — Audit (detect-only report), Prune (delete orphans + deprecated + historical), Compact (apply concise/agent-audience rule), Wire (fix dangling refs, route misrouted, dedupe). Safety-first — NEVER deletes if runtime code reads the file, CLI walks its directory (quality-gate/, workflows/), file is in pre_commit_checks DOC_OWNER_FILES, or it's a canonical entry-point doc.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# cleanup — audit & prune docs/skills/registries

> **Self-validate after edits.** Any change to this skill's files (SKILL.md, scripts/, references/, templates/, assets/) must be followed by `./scripts/validate.sh` from the skill directory. Hard findings → create-skill Optimize lane.

The operator wants a smaller, fresher, more agent-friendly repo. This skill detects dead weight + verbose drift across `docs/`, `.claude/skills/`, and the cross-referencing registries (INDEX.md, REFERENCE.md, AGENTS.md, CLAUDE.md), then executes deletions / compactions / re-wires under safety blockers that prevent breaking runtime contracts.

## Entry — pick a lane (always `AskUserQuestion` unless prompt names one)

| Lane | When to choose |
|---|---|
| **Audit** | Detect-only sweep. Output: prioritized table of orphan / verbose / dangling / misrouted findings. No mutations. |
| **Prune** | Execute deletes from a confirmed audit list. Includes dangling-ref cleanup as the immediate follow-up. |
| **Compact** | Apply concise/agent-audience rule to target file(s). Preserves file:line refs, exact commands, contract specs. |
| **Wire** | Fix dangling refs (post-delete), route misrouted content, dedupe (link-instead-of-repeat). |

Skip the question when the typed prompt names one unambiguously:

| Typed prompt | Lane | Skip? |
|---|---|---|
| "audit docs / find orphans / what's stale in docs" | Audit | Yes |
| "delete the orphans / prune dead docs / Elon rule on docs" | Prune | Yes |
| "compact / shrink / tighten `<file>`" | Compact | Yes |
| "fix dangling refs / route X to Y / dedupe" | Wire | Yes |
| "cleanup pass" / ambiguous | — | **No — ask.** |

After lane chosen, load `references/<lane>.md` for the procedure. Universal preflight below runs first.

## Universal preflight

1. **Clean git working tree.** `git status --short` returns empty (modulo gitignored). Refuse on dirty tree — operator should commit/stash first; cleanup edits then land as one clean diff per lane.
2. **Baseline freshness OK.** If autoresearch skill is present, run `python3 .claude/skills/autoresearch/scripts/freshness_sweep.py --json` — must exit 0. A failing sweep means cleanup is operating on already-broken state; fix that first.
3. **Recent backup is git.** Cleanup deletes are recoverable via `git checkout`. No external backup needed.

## Detection signals + safety blockers — canonical reference

[references/criteria.md](references/criteria.md) — 8 detection signals (orphan / deprecated stub / historical-only / verbose drift / dangling refs / misrouted / duplicates / over-line-cap) and 4 NEVER-DELETE safety blockers. Loaded on demand by Audit and Prune lanes.

## Hard rules (universal)

1. **Elon rule.** Question every doc's requirement before keeping. Delete aggressively. If you're not restoring ~10% after the sweep, you haven't deleted enough.
2. **Safety blockers are absolute.** Never delete a file matching any of the 4 blockers in `criteria.md § Safety blockers`. The blockers exist because their failures are silent (runtime CLI just stops working).
3. **Agent-audience default.** Compactions follow `~/.claude/CLAUDE.md` Rules: imperative voice, bullets/tables over prose, `file:line` over paragraphs, drop "why this matters" footers, `git show <sha>` 30s test.
4. **Single commit per lane.** Prune in one commit, Compact in another, Wire in a third. Each independently revertable.
5. **Dangling-ref sweep after every Prune.** A delete pass without the immediate sanity grep is incomplete. Wire lane procedure encodes the exact sanity command.
6. **Update memory on new patterns.** If a cleanup pass surfaces a recurring failure mode not yet in `.memory/` or project-local memory, write a feedback entry before closing the lane.
7. **Verify load-bearing status before deleting.** For each delete candidate, run the safety-blocker checks IN ORDER. Skipping ahead is how silent runtime breaks happen.

## Cross-references

- [references/criteria.md](references/criteria.md) — detection signals + safety blockers (read by Audit + Prune)
- [references/audit.md](references/audit.md) — Audit lane: scan → report → operator triage
- [references/prune.md](references/prune.md) — Prune lane: confirmed-list delete + dangling-ref sweep + commit
- [references/compact.md](references/compact.md) — Compact lane: per-file concise-rule application
- [references/wire.md](references/wire.md) — Wire lane: fix dangling, route misrouted, dedupe
- [scripts/audit.py](scripts/audit.py) — deterministic detector; `--json` for machine output
- Sister skills: `create-skill` (Audit lane uses similar deterministic-check pattern), `autoresearch` (preflight/closeout/freshness-sweep precedent), `skill-portfolio-review` (broader skill-cluster cleanup)
- Precedent: 2026-05-23 session removed ~7,300 lines across 14 files via Audit→Prune→Wire flow before this skill existed; this skill encodes that pattern.

## Why this skill exists

Without it, every session re-derives the criteria, re-discovers the safety blockers, and risks deleting load-bearing files. The 2026-05-23 session's first delete-list mistakenly flagged `EVALUATION.md` (14 refs) and `library-retrieval-map.md` (AGENTS.md cite) as orphans before manual sanity caught it — that's the exact failure mode `criteria.md § Safety blockers` prevents.
