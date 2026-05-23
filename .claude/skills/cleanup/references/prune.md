# Prune lane — execute deletes

Loaded on demand. Consumes an audit list. Executes deletes + immediate dangling-ref cleanup. Single commit.

## Preflight

- Universal preflight (clean git, autoresearch sweep clean).
- **Lane-specific:** an Audit lane run completed within the current session OR operator provides an explicit delete list. Refuse to prune without a vetted list — no ad-hoc deletion.

## Do

```bash
# 1. Per-candidate verification (run for each file in HARD-DELETE / confirmed DELETE? list)
python3 .claude/skills/cleanup/scripts/audit.py <file> --verify
# Runs the 4 safety-blocker checks in order; exit 1 = STOP, do not delete.

# 2. Bulk delete (only after every candidate verified)
git rm <file1> <file2> ...

# 3. Immediate dangling-ref sanity grep (deletes must be paired with this)
grep -rln --include='*.md' -E '<deleted-basenames-joined-by-pipe>' docs/ AGENTS.md CLAUDE.md README.md

# 4. Fix dangling refs (Edit each match; replace with sensible text or strip the link)
# Common patterns:
#   - [name](path-to-deleted)            → name (link stripped) OR strip the line if it was a "see X" pointer
#   - `path-to-deleted` (bare backtick)   → contextually appropriate replacement
#   - Registry table rows (INDEX.md, REFERENCE.md) referring to deleted   → drop the row

# 5. Update any pre-commit allowlists that referenced the deleted files
grep -n '<deleted-basename>' scripts/pre_commit_checks.py
# If the basename is in DOC_OWNER_FILES, remove it.

# 6. Run autoresearch freshness sweep (if present)
python3 .claude/skills/autoresearch/scripts/freshness_sweep.py --json
# Must exit 0.

# 7. Single commit per Prune lane
git add -A docs/ AGENTS.md scripts/pre_commit_checks.py
git commit -m "docs: delete N orphan/deprecated/historical files (-X lines)

- list deleted files (one per line)
- list any cross-cutting cleanups (e.g. DOC_OWNER_FILES updated)
"
git push origin master
```

## Closeout

- **Verify deletions stuck.** `git log --oneline -1` shows the commit; `git status --short` is clean.
- **Verify zero dangling refs remain.** Re-run step 3's sanity grep — empty output required.
- **Memory write IF new pattern.** If a delete candidate hit a safety blocker pattern not yet documented in `criteria.md § Known false-positive patterns`, add it.
- **Recommend next lane.** Typical: Wire (if dangling cleanup uncovered more drift) → Compact (if HARD-DELETE list was small but verbose-drift candidates exist).

## Hard rules

- **Verify all 4 safety blockers per candidate, in order A→B→C→D.** Skipping is how silent runtime breaks happen.
- **Deletes + dangling-ref cleanup are ONE commit.** Don't split — partial state with broken refs is worse than no delete.
- **No `--force` ever.** If a delete is reverting a real-yet-undocumented load-bearing file, the right move is git-checkout-the-file then update `criteria.md` so the next pass doesn't make the same mistake.
- **Push immediately.** Holding deletes uncommitted creates ambiguous repo state.

## Worked example — 2026-05-23 session

- 14 files deleted across 2 commits (split for readable diffs):
  - Commit 1: 11 deprecated stubs + historical logs (`PLAN.md`, `GOAL.md`, `MISSION.md`, `PROGRESS.md`, `IMPROVEMENTS.md`, `SPRINT-PROGRESS.md`, `QUALITY_SCORE.md`, `realtime/{model-prompting,manage-cost}.md`, `design-docs/knowledge-{graph-ui,ui-patterns}.md`)
  - Commit 2: 3 marginal-ref files (`autonomous-builder-telemetry-analysis.md`, `coding-agent-prevention.md`, `workflow-cli-usage.md`)
- Dangling-ref sweep caught refs in 21 downstream files; fixed in same commits.
- `pre_commit_checks.py:DOC_OWNER_FILES` updated to drop deleted entries (MISSION, QUALITY_SCORE).
- `scripts/pre_commit_checks.py` is the canonical example of a place to check — when a tracked-file set has dangling entries, runtime is fine but the set is dead code.
- Net: ~7,300 lines removed across both commits.
