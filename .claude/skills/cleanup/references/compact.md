# Compact lane — apply concise/agent-audience rule

Loaded on demand. In-place compaction of verbose-drift candidates. PRESERVES file:line refs, exact commands, contract specs. Single commit.

## Preflight

- Universal preflight (clean git, autoresearch sweep clean).
- **Lane-specific:** operator names target file(s), OR audit COMPACT category has flagged candidates the operator vets.
- **Read each target file first.** Don't compact blind; you need to know which content is load-bearing vs framing prose.

## What to cut (the concise rule, applied)

Per `~/.claude/CLAUDE.md` Rules — "All docs default to agent audience":

| Cut | Why | How |
|---|---|---|
| **"Why this matters" footers** | Reader already there if reading | Delete the section entirely |
| **Multi-sentence intros restating the header** | Header is the signal | Delete or compress to one line |
| **"Background" sections > 5 lines** | Background belongs in git log / commit body | Compress to 1-2 lines or delete |
| **Prose paragraphs > 600 chars** | Bullets / tables denser | Convert to bullet list or comparison table |
| **Multiple sentences elaborating one spec** | Spec name + `file:line` carries it | One sentence |
| **Suggestive language ("you might want to consider")** | Agents need imperative | "Do X. If Y, do Z." |
| **Multi-paragraph explanations of one concept** | Reader can infer from spec | Collapse to spec + 1-line clarifier |

## What to KEEP (never cut)

- **`file:line` pointers** — `run.py:870` is denser than three sentences describing the site.
- **Exact commands** — `python3 X.py --flag` stays verbatim.
- **Symptom signatures** — evidence queries an agent uses to match a pattern.
- **Contract specs** — payload shapes, JSON-schema fields, function signatures.
- **Prevention notes** — short, name a defense pattern.
- **`code` formatting** — preserved as-is.
- **Tables of contents / cross-references** — structural navigation.

## Do

```bash
# 1. Pick ONE file at a time. Compaction is judgment-heavy; batch-compaction risks losing subtle specs.
TARGET=docs/path/to/verbose.md
wc -l "$TARGET"

# 2. Read the whole file. Identify sections by header + verbose-drift signals (long paras, footers).
sed -n '1,200p' "$TARGET"  # ... etc.

# 3. Edit section by section. For each verbose section:
#    a. State the spec / pattern / fix-pointer in 1-2 lines.
#    b. Move prose-only context to `git log -p` (where it belongs).
#    c. Convert comparison prose to tables.
#    d. Convert "list of N things separated by 'and'" to bullets.

# 4. Verify file:line refs preserved
grep -oE '[a-z_/.-]+\.(py|md|tsx?|toml):[0-9]+' "$TARGET" | sort -u  # before
# … edit …
grep -oE '[a-z_/.-]+\.(py|md|tsx?|toml):[0-9]+' "$TARGET" | sort -u  # after — set must match

# 5. Verify exact-command preservation
diff <(grep -E '^[ ]*\$ |^[ ]*python3 |^[ ]*git |^[ ]*builder |^[ ]*npm |^[ ]*```' BEFORE.md) \
     <(grep -E '^[ ]*\$ |^[ ]*python3 |^[ ]*git |^[ ]*builder |^[ ]*npm |^[ ]*```' "$TARGET")
# Commands set must match.

# 6. Run autoresearch freshness sweep (if present) — must exit 0
python3 .claude/skills/autoresearch/scripts/freshness_sweep.py --json

# 7. Single commit per Compact lane (may be one file or several related)
git add "$TARGET"
git commit -m "docs(<surface>): compact <file> (-N lines, agent-audience rule)"
git push origin master
```

## Closeout

- **Verify line reduction.** `wc -l` before vs after; expect 20-50% reduction in target sections.
- **Verify no lost references.** file:line set unchanged; command set unchanged.
- **Recommend next lane.** Typical: another Compact (if multiple files queued) → none (cleanup pass done).

## Hard rules

- **One file per commit when possible.** Per-file compaction commits are independently revertable; bulk compactions are diff-noisy and risky.
- **Don't compact contract docs alone.** A reference doc describing a `payload_shape: {a, b, c}` — keep the spec, only compact the surrounding prose.
- **Verify spec preservation diffs.** Compaction WITHOUT the grep-diff on file:line + commands is unreliable.

## Worked example — autoresearch SKILL polish (2026-05-23, commit `0562f7a`)

- KNOWN_PATTERNS.md P10-P17 entries compacted from ~25 lines each to ~13 lines each.
- Removed: "Wallclock to repro" bullets (rarely useful), multi-sentence "Symptom" paragraphs, "Recurrence prevention" → "Prevention" (one sentence).
- Preserved: all file:line refs, all evidence queries, all fix pointers.
- Net: 1356 → 1244 lines (-8%), 11.7k → 10.3k words (-12%). Freshness sweep stayed clean.
