# cleanup criteria — detection signals + safety blockers

Loaded on demand by Audit + Prune lanes. The canonical spec for what cleanup looks for and what it must never delete.

## Detection signals (what to flag)

| # | Signal | Predicate | Action |
|---|---|---|---|
| 1 | **Orphan** | 0 runtime refs (`src/`, `scripts/`, `.claude/skills/`) AND 0 doc-graph refs OR only 1 ref to a registry (INDEX.md / REFERENCE.md) | DELETE |
| 2 | **Deprecated stub** | First 50 lines contain `deprecated`, `migrated to`, `redirect`, `obsolete`, or a header pattern like `# X.md — Deprecated` | DELETE |
| 3 | **Historical-only** | Log of events all in closed/shipped state + content reproducible from `git log` + `.memory/` (e.g., IMPROVEMENTS.md after all IMPs close) | DELETE |
| 4 | **Verbose drift** | Multiple ≥600-char paragraphs where bullets would do; "Why this matters" footers; intro paragraphs restating the section title; multi-sentence elaborations of single specs | COMPACT |
| 5 | **Dangling refs** | Links to non-existent files; bare `path.md` mentions of deleted files | WIRE (fix link or strip ref) |
| 6 | **Misrouted content** | Per-patch detail in milestone-scope docs (e.g., autoresearch P-numbered fixes in ROADMAP); cross-cutting decisions buried in domain logs | WIRE (move to domain log) |
| 7 | **Duplicate content** | Same info maintained in 2+ files (drift inevitable) | WIRE (canonical-owner + link from others) |
| 8 | **Over line-cap** | `len(splitlines())` exceeds a `docs/goal/README.md § "Compression triggers per file"` cap (currently `STATUS.md > 120`). Catches table/bullet-heavy files that evade the long-paras signal. `ROADMAP.md` is EXEMPT — it's the spine; closed `[x]` items stay. | COMPACT (trim oldest rolling content → memory/git per the owning doc's rule) |

## Safety blockers (NEVER delete if any apply)

| # | Blocker | Detection command | Why it matters |
|---|---|---|---|
| A | **Runtime code reads it** | `grep -rln 'docs/foo.md' src scripts` returns ≥1 | Runtime CLI / service consumes the file; deleting silently breaks |
| B | **Directory walked by runtime CLI** | File is under `docs/quality-gate/` or `docs/workflows/` | `builder quality-gate <surface>` / `workflow read <name>` walk these dirs; missing file = CLI surface gap |
| C | **In `pre_commit_checks.py:DOC_OWNER_FILES`** | `grep -F 'docs/foo.md' scripts/pre_commit_checks.py` | Set drives "CHANGELOG required when this file changes" gate; dangling entry is dead code but harmless |
| D | **Canonical entry-point doc** | Path matches `CLAUDE.md` / `AGENTS.md` / `README.md` / `docs/goal/{README,NORTH-STAR,ROADMAP,STATUS,INDEX}.md` / `docs/REFERENCE.md` / `docs/autoresearch/{README,PROGRESS,OPTIMIZE,METRICS,HARNESS,COMPARE,SDK-OBSERVABILITY,CONTEXT-LEDGER,GAPS,OPTIMIZE_IDEAS,baseline_variance,fixtures,INTROSPECTION}.md` | Loaded at session entry by skills / read by operators on every visit; deleting breaks everything |

**Verification order: A → B → C → D.** A short-circuit on any HIT means KEEP, regardless of other signals. The orphan-detection signal #1 in the table above MUST be intersected with these blockers — a file with 0 refs can still be load-bearing via dir-walk.

## Known false-positive patterns (lessons from 2026-05-23)

| Mistake | Why it happened | Defense |
|---|---|---|
| Flagged `EVALUATION.md` as DELETE (had 14 refs) | Initial `grep -F` script had a subprocess output-handling bug | Use `audit.py` script (deterministic) instead of ad-hoc grep |
| Flagged `library-retrieval-map.md` as orphan | AGENTS.md cites it WITHOUT the `.md` suffix (`workflow read references/library-retrieval-map`) | When orphan-detecting, also grep for stem (`library-retrieval-map`) not just basename (`library-retrieval-map.md`) |
| Flagged `quality-gate/*.md` files as orphans | They're walked by `builder quality-gate` CLI, not basename-referenced | Apply Blocker B before scoring orphans |
| Flagged `phases/*.md` as orphans | They're listed FROM `phase-model.md`; basename grep with path component missed it | Grep both `phases/X.md` and `X.md` patterns |

## Discipline checklist (Elon rule operationalized)

Before closing a lane:

- [ ] Did I QUESTION every retained file's requirement? (rule 1: question every part)
- [ ] Did I delete aggressively? If <10% will need restoring, I haven't deleted enough.
- [ ] Did I check ALL 4 safety blockers per delete candidate, in order?
- [ ] Did I run the dangling-ref sanity grep after the delete pass?
- [ ] Did I write a memory entry if a new cleanup pattern surfaced?
- [ ] Did I run the freshness sweep (autoresearch) AFTER the lane, expecting exit 0?

## Inputs the audit script needs

`scripts/audit.py` consumes this file's structure. It enumerates every `.md` under `docs/` and `.claude/skills/`, computes the 8 signals + 4 blockers per file, and emits a prioritized JSON or human-readable report. Don't bypass it with ad-hoc grep loops — the 2026-05-23 false-positive on EVALUATION came from exactly that shortcut.
