# Wire lane — fix refs, route content, dedupe

Loaded on demand. Three modes within one lane:

| Mode | When | Action |
|---|---|---|
| **Fix-dangling** | After a Prune lane, refs to deleted files remain | Edit each ref-bearer to drop link / replace with sensible text |
| **Route-misrouted** | Per-patch detail in milestone-scope docs; cross-cutting decisions in domain logs | Move content to the canonical owner; replace original with link |
| **Dedupe** | Same info maintained in 2+ files | Pick canonical owner; replace duplicates with links |

## Preflight

- Universal preflight (clean git, autoresearch sweep clean).
- **Lane-specific:**
  - For Fix-dangling: a prior Prune commit OR operator-provided basename list.
  - For Route-misrouted: operator-named source + destination, OR audit MISROUTED signal.
  - For Dedupe: operator-named duplicate set, OR audit DUPLICATE signal.

## Do

### Fix-dangling

```bash
# 1. Find all dangling refs (use the basenames from the prior Prune commit)
BASENAMES='PLAN.md|GOAL.md|MISSION.md|...'   # pipe-joined
grep -rln --include='*.md' -E "$BASENAMES" docs/ AGENTS.md CLAUDE.md README.md

# 2. For each match, decide:
#    a. Replace [name](deleted-path) → name (link stripped) for inline mentions
#    b. Drop the entire bullet/row if it was "see X" → X is gone
#    c. For registry tables (INDEX.md, REFERENCE.md), drop the row entirely
#    d. For "deleted-doc cited as authority" prose, replace with the live alternative

# 3. Sanity grep — must be empty after fixes
grep -rln --include='*.md' -E "$BASENAMES" docs/ AGENTS.md CLAUDE.md README.md

# 4. Single commit
git add -A
git commit -m "docs: clear dangling refs to N deleted docs"
```

### Route-misrouted

Pattern: per-patch lane detail accumulated in repo-scope docs (e.g., autoresearch P11/P12/P13 in ROADMAP). Move it.

```bash
# 1. Identify canonical owner
#    autoresearch lane patches → docs/autoresearch/PROGRESS.md
#    Builder runtime changes  → CHANGELOG.md
#    Cross-cutting decisions  → docs/goal/STATUS.md § Recent Decisions
#    Milestone scope          → docs/goal/ROADMAP.md (M§)

# 2. Compress source content to a one-line PROGRESS-style entry; write to canonical owner
# 3. Strip the long form from the original surface
# 4. Add a routing-pointer line in the original surface if useful
#    (e.g., ROADMAP M3.5 header: "Per-patch detail: docs/autoresearch/PROGRESS.md")

# 5. Single commit
git commit -m "docs: route N entries from <source> to <canonical>"
```

### Dedupe

```bash
# 1. Pick the canonical owner — the surface where the content most belongs (single-owner-per-concern).
# 2. Replace duplicates with markdown links: [Topic](path/to/canonical.md)
# 3. If the duplicates added context (the canonical owner didn't have), MERGE that context into canonical first.
# 4. Single commit
git commit -m "docs: dedupe <topic> — canonical owner is <path>"
```

## Closeout

1. **Verify clean state.** Sanity grep for dangling refs / orphan registry entries — empty.
2. **Run autoresearch freshness sweep (if present).** Exit 0.
3. **If a NEW routing pattern emerged:** add a feedback memory describing the canonical-owner rule + cite the example (see `feedback_autoresearch_progress_routing.md` precedent).
4. **Recommend next lane.** Wire is usually the trailing lane. If Audit flagged additional verbose-drift after Wire, run Compact next.

## Hard rules

- **Fix-dangling MUST happen in same commit as the Prune that created the dangling refs.** Splitting them creates intermediate broken state.
- **Route-misrouted: write to canonical owner FIRST, then strip from source.** Reverse order risks data loss if interrupted.
- **Dedupe: prefer link over copy.** Two copies WILL drift; one canonical + N links cannot.
- **Verify with grep before commit.** Every Wire commit's claim should be checkable with a one-line grep.

## Worked examples — 2026-05-23 session

- **Fix-dangling:** 17 files had refs to the 11 deleted docs; cleared in commit `1384ac0`. First-pass regex was too coarse and produced `(deleted), (deleted), (deleted)` markers; surgical Python pass with per-line replacements fixed those (lesson: regex compaction risks ugly artifacts; do per-line edits for high-stakes refs).
- **Route-misrouted:** autoresearch lane P-numbered fixes were in ROADMAP M3.5 + CHANGELOG; routed to `docs/autoresearch/PROGRESS.md`. ROADMAP M3.5 keeps milestone-scope `[ ]` items + a pointer line.
- **Dedupe:** none this session, but the routing pattern is the dedupe pattern with extra steps.
