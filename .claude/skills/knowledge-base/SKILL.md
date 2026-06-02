---
name: knowledge-base
description: "All operations on the user's global Claude-tooling knowledge base at ~/.claude/knowledge/. The KB is the coding agent's first-stop discovery surface for SDK levers across Claude Code, Claude Agent SDK (Python+TS), Claude Managed Agents, and the OpenAI Codex SDK — when it's stale, the next session reinvents what already exists (see INSIGHTS Run #7's 13-IMP cost of context blindness). This skill handles every KB operation: REFRESH (detect upstream deltas + write gap articles for new features), MAINTAIN (validate URLs + lint + check rubric slug refs + flag staleness), INGEST (lint and add user-provided drafts with correct tags), AUDIT (full coverage re-check across all four surfaces), SEARCH (smart query expansion), DEDUPE (find overlapping articles), RUBRIC OPS (read/edit/re-ingest the four surface rubrics), and OPEN (open the operator-facing knowledge-browser.html in a browser). Use this skill proactively whenever the user says 'refresh the KB', 'audit the KB', 'is our KB current?', 'what's new in Claude SDK / Codex SDK?', 'update the rubrics', 'add this article to the KB', 'check if our KB has X', 'find overlapping KB articles', 'are KB URLs still valid?', 'have new features landed since last sweep?', 'open the KB browser', 'show the KB html', or asks about adopting any Claude or Codex feature that may not yet be indexed. ALSO use proactively on a monthly cadence and after any major upstream release (new Anthropic Claude Code week, new Python/TS SDK minor version, new Codex CLI minor version). The four surface rubrics live at predictable slugs: claude-agent-sdk-rubric, claude-code-rubric, claude-managed-agents-rubric, codex-sdk-rubric. Skip this skill ONLY if the user explicitly says 'don't touch the KB' or asks a question that's already answered by the rubrics."
model: sonnet
effort: high
allowed-tools: Read, Write, Edit, Bash, WebFetch, Task
compatibility:
  - python3 >= 3.9
  - workflow CLI at ~/.claude/bin/workflow.py
  - WebFetch tool
  - Task tool with Haiku model access (for parallel writer subagents)
---

# Knowledge Base Operations

> **Self-validate after edits.** Any change to this skill's files (SKILL.md, scripts/, references/, templates/, assets/) must be followed by `./scripts/validate.sh` from the skill directory. Hard findings → create-skill Optimize lane.

The global Claude-tooling knowledge base at `~/.claude/knowledge/raw/` is the agent's discovery surface. This skill owns every operation on it.

## Scope — what this skill covers

| Operation | When to invoke | Phases run |
|---|---|---|
| **REFRESH** | "refresh the KB", "what's new?", monthly cadence, after upstream release | A → B → C → D → E |
| **MAINTAIN** | "audit URLs", "check KB for stale articles", quarterly cadence | M1 → M2 → M3 |
| **INGEST** | "add this article", "ingest these drafts" | I1 → I2 → I3 |
| **AUDIT** | "is our KB current?", first run, after long gap | A (no-delta-gate mode) → B → C → D → E |
| **SEARCH** | "find KB article on X", "what do we know about Y?" | S1 → S2 |
| **DEDUPE** | "find overlapping articles", "any duplicates?" | D1 → D2 |
| **RUBRIC OPS** | "update the SDK rubric", "what's in the Codex rubric?" | R1 → R2 → R3 |
| **OPEN** | "open", "show the html", "open the browser/KB browser" | O1 |

If the user's message names an operation unambiguously (e.g. "refresh", "maintain", "ingest this file"), skip the question and run it directly. Otherwise, first action is `AskUserQuestion`:

| Option | Covers | When to pick |
|---|---|---|
| **Update** | REFRESH, AUDIT | Bring KB up to date — detect upstream delta, write gap articles, update rubrics |
| **Health check** | MAINTAIN | Validate existing KB — lint sweep, URL validity, rubric slug refs |
| **Other** | INGEST, SEARCH, DEDUPE, RUBRIC OPS, OPEN | Add an article, search, find duplicates, edit rubrics, open KB browser |

## ⚠ Hard rules

1. **Only mutate `~/.claude/knowledge/raw/` and rubric articles.** Do NOT edit `~/.claude/CLAUDE.md` triggers (user-controlled).
2. **Per-feature URLs only for article `source_url`.** Each article cites its specific docs sub-page, not a surface overview.
3. **Use full path to the Linux workflow binary.** On WSL-2, `/mnt/c/.../workflow` may shadow the Linux binary. Always invoke `/home/$USER/.local/bin/workflow`.
4. **Don't auto-add new tags to the taxonomy.** Pick from the existing 17–18 tags (see [`references/frontmatter-schema.md`](references/frontmatter-schema.md)). New tags need user confirmation.
5. **Keep rubric titles short and stable.** The four canonical titles are `Claude Agent SDK rubric`, `Claude Code rubric`, `Claude Managed Agents rubric`, `Codex SDK rubric`. These produce predictable slugs that `~/.claude/CLAUDE.md` BEFORE triggers depend on.
6. **Don't ingest articles that fail `--strict` lint.** Fix frontmatter or sections first.
7. **Don't delete articles.** Mark stale ones in their `## Maintenance` note, or write a successor article that supersedes. Future maintainers may want history.
8. **Don't auto-recommend new BEFORE triggers in `~/.claude/CLAUDE.md`.** Surface that work to the user; let them decide.

## Operation: REFRESH

### Phase A — Detect what changed

Run the bundled state-tracker:

```bash
python3 .claude/skills/knowledge-base/scripts/detect_updates.py --json > /tmp/kb-delta.json
cat /tmp/kb-delta.json
```

The script fetches Anthropic's What's New, Python+TS SDK CHANGELOGs, and Codex GitHub releases — diffs against `.claude/skills/knowledge-base/state.json` (the durable record of last refresh) — emits `{ delta: { surface: [new_features], ... }, current_versions, since }`.

If `delta` is empty across all four surfaces: report "no upstream changes since last refresh" and exit. If non-empty: proceed.

### Phase B — Write gap articles via parallel Haiku writers

For each candidate feature, confirm gap with `workflow knowledge search "<feature>"`. For genuine gaps, group by surface and dispatch **1 Haiku general-purpose subagent per surface** (4 max in parallel). Each subagent WebFetches per-feature URL, writes 200-400 word article to `/tmp/kb-drafts/<date>-<slug>.md` matching the schema in [`references/frontmatter-schema.md`](references/frontmatter-schema.md).

Why 4 parallel agents (not 1 per article, not 1 for all): empirically the right cost lever. 4 × 10–12 articles = 2–3 min wall-clock; 1-per-article wastes setup; 1-for-everything serializes WebFetches.

### Phase C — Lint + ingest

Lint each draft. The most common failure is missing `date_published: unknown`:

```bash
PASS=0; FAIL=0
for f in /tmp/kb-drafts/<date>-*.md; do
  out=$(/home/$USER/.local/bin/workflow knowledge lint "$f" --strict --json 2>&1)
  ok=$(echo "$out" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',False))")
  if [ "$ok" = "True" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "FAIL: $f"; fi
done
echo "Pass: $PASS Fail: $FAIL"
```

Fix failures (typically missing frontmatter field — see [`references/ingest-gotchas.md`](references/ingest-gotchas.md) § 4). Re-lint until 0 fails.

Then ingest each, extracting tags from frontmatter with `Grep`:

```bash
for f in /tmp/kb-drafts/<date>-*.md; do
  tags=$(grep -oP 'tags:\s*\[\K[^\]]+' "$f" | tr -d ' "'"'" | tr ',' ',')
  /home/$USER/.local/bin/workflow knowledge ingest "$f" --tags "$tags" --json > /dev/null
done
```

The ingest auto-reindexes after each call. Verify count grew.

### Phase D — Update surface rubrics

For each surface with new articles, read its rubric, edit the relevant subsection table to add rows for new articles, and re-ingest. See "Operation: RUBRIC OPS" below for the detailed pattern.

### Phase E — Verify + persist state

```bash
# 1. Every new article lints clean
for f in ~/.claude/knowledge/raw/<date>-*.md; do
  /home/$USER/.local/bin/workflow knowledge lint "$f" --strict --json | python3 -c "import sys,json; assert json.load(sys.stdin).get('ok'), 'lint failed'"
done
# 2. All four rubrics readable
for slug in claude-agent-sdk-rubric claude-code-rubric claude-managed-agents-rubric codex-sdk-rubric; do
  /home/$USER/.local/bin/workflow knowledge read "$slug" --json | python3 -c "import sys,json; assert json.load(sys.stdin).get('status')=='ok', f'rubric missing'"
done
# 3. Sample searches return new articles in top 3
for q in "<feature1>" "<feature2>"; do
  /home/$USER/.local/bin/workflow knowledge search "$q" --json | python3 -c "import sys,json; print(json.load(sys.stdin)['results'][0]['title'])"
done
```

Then rebuild the operator browser (new articles must appear in the view) and persist state:

```bash
python3 .claude/skills/knowledge-base/scripts/build_browser.py
python3 .claude/skills/knowledge-base/scripts/detect_updates.py --commit-state
```

If new surfaces emerged (e.g., new SDK family), surface to user — DO NOT auto-edit `~/.claude/CLAUDE.md` triggers.

### Phase F — Cross-skill triggers + self-schedule

REFRESH closeout has two responsibilities beyond the KB itself: record a rubric-change marker, and reschedule itself.

**1. Rubric-updated marker.** For each of the four surface rubrics, after Phase D updates rows: append/update a `"last_rubric_update"` field in `.claude/skills/knowledge-base/state.json` with `{ "<rubric-slug>": "<ISO date>" }`. A shifted Claude Agent SDK rubric is a re-baseline signal — surface it to the operator as an `autoresearch` Baseline trigger (see `autoresearch/references/lanes/baseline.md`). This is how SDK signature drift flows from KB refresh → re-baseline without silently going stale.

**2. Prompt operator to run `/knowledge-base REFRESH` next month.** `CronCreate` is session-bound and does not persist — do not use it. Instead, tell the user: "Next REFRESH due ~30 days from now. Use `/schedule` to set a recurring remote routine if you want it automated."

## Operation: MAINTAIN

Quarterly cadence — validate the KB's existing state.

### M1 — URL validity

Extract `source_url` from recent articles and check HTTP status in a single Bash loop — no subagents, no model tokens:

```bash
BROKEN=()
for f in ~/.claude/knowledge/raw/2026-0[456789]*.md ~/.claude/knowledge/raw/2026-1*.md; do
  [[ -f "$f" ]] || continue
  url=$(grep -m1 '^source_url:' "$f" | sed 's/source_url: *//')
  [[ -z "$url" || "$url" == "unknown" ]] && continue
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 "$url" 2>/dev/null)
  [[ "$code" != "200" ]] && BROKEN+=("$code $url $(basename $f)")
done
printf '%s\n' "${BROKEN[@]:-none broken}"
```

For each broken URL: try adjacent paths manually (e.g. `/docs/en/X` → `/docs/en/agent-sdk/X`). If genuinely gone: add a `## Maintenance` note to the article. Don't delete — it's history.

### M2 — Lint sweep

Lint every existing article:

```bash
PASS=0; FAIL=0; FAILED_FILES=()
for f in ~/.claude/knowledge/raw/*.md; do
  ok=$(/home/$USER/.local/bin/workflow knowledge lint "$f" --strict --json | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',False))")
  if [ "$ok" = "True" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); FAILED_FILES+=("$f"); fi
done
echo "Pass: $PASS  Fail: $FAIL"
printf '%s\n' "${FAILED_FILES[@]}"
```

Fix any newly-failing articles (frontmatter drift, missing sections).

### M3 — Rubric slug refs

Use `Grep` on the raw files directly — no CLI round-trip, no Python:

```bash
RAW=~/.claude/knowledge/raw
for rubric in claude-agent-sdk-rubric claude-code-rubric claude-managed-agents-rubric codex-sdk-rubric; do
  f=$(ls "$RAW"/*-${rubric}.md 2>/dev/null | head -1)
  [[ -z "$f" ]] && echo "MISSING rubric: $rubric" && continue
  echo "--- $rubric ---"
  grep -oE '2026-[0-9]{2}-[0-9]{2}-[a-z0-9-]+' "$f" | sort -u | while read slug; do
    [[ -f "$RAW/${slug}.md" ]] || echo "BROKEN: $slug"
  done
done
echo "done"
```

Fix the rubric with `Edit` on the raw file — replace broken slugs with current ones (use `workflow knowledge search` to find). Then `workflow knowledge reindex` once.

## Operation: INGEST (user-provided drafts)

User says "add this article" or "ingest this draft":

### I1 — Lint

```bash
/home/$USER/.local/bin/workflow knowledge lint <file.md> --strict --json
```

Fix any errors. Common: missing `date_published`, missing required section, tag outside taxonomy.

### I2 — Confirm not a duplicate

```bash
/home/$USER/.local/bin/workflow knowledge search "<title keywords>" --json
```

If top result is suspiciously similar, ask user whether to merge or proceed.

### I3 — Ingest with frontmatter tags

```bash
tags=$(python3 -c "<extract tags from file frontmatter>")
/home/$USER/.local/bin/workflow knowledge ingest <file.md> --tags "$tags" --json
python3 .claude/skills/knowledge-base/scripts/build_browser.py   # refresh operator browser
```

If the article belongs to one of the four surfaces, add a row to its rubric (see RUBRIC OPS).

## Operation: OPEN

User says "open", "show the html", "open the KB browser". Open the operator browser in the default browser; regenerate first if it's missing or stale.

### O1 — Build if needed, then open

```bash
F="$HOME/.claude/knowledge/knowledge-browser.html"
[ -f "$F" ] || python3 .claude/skills/knowledge-base/scripts/build_browser.py
if grep -qi microsoft /proc/version 2>/dev/null; then
  explorer.exe "$(wslpath -w "$F")"          # WSL2 → Windows default browser
else
  (xdg-open "$F" >/dev/null 2>&1 || open "$F" >/dev/null 2>&1) &   # Linux / macOS
fi
echo "opened $F"
```

On WSL2 `explorer.exe` is the reliable launcher (`xdg-open` often no-ops). If the operator wants the latest articles guaranteed fresh, run `build_browser.py` first regardless. State the `file://` path in chat as a fallback.

## Operation: AUDIT

Same as REFRESH but skips the delta-gate. Every feature on the surface-urls map (`references/surface-urls.md`) becomes a candidate; each is searched against the KB; gaps proceed to write. Use for first-run or after a long gap (>30 days since last REFRESH).

## Operation: SEARCH

User asks "what do we know about X?" or "is there a KB article on Y?":

> **Discovery vs. retrieval — route correctly.** For *discovery* (finding which article is relevant) use `workflow knowledge search` — it ranks by BM25 relevance and is tag-aware. Do **not** `grep`/`ls` over `~/.claude/knowledge/raw/`: substring-only, unranked, misses synonyms, and reading many raw files blows context. For *retrieval* of a known article, `read <slug>` / `summary <slug>` beat a direct file `Read` (token caps + compact output). Direct file reads are acceptable only when you already hold the exact slug and need the full body. The article slug **is** the `raw/<slug>.md` basename, so the index tempts a direct read — resist it for discovery.

### S1 — Smart query

```bash
/home/$USER/.local/bin/workflow knowledge search "<user's query>" --json
```

Read top 3 results.

### S2 — Query expansion if no good hit

If top result has score < -15 (poor match), reformulate query:
- Drop common words ("the", "a")
- Add SDK-specific terms (`ClaudeAgentOptions`, `can_use_tool`)
- Try the surface's name (e.g., search `"can_use_tool agent sdk"` instead of `"can_use_tool"`)

If still no good hit, the topic may be a gap — propose REFRESH or AUDIT.

## Operation: DEDUPE

User asks "find overlapping articles" or you suspect duplication:

### D1 — List candidates

Extract titles from recent article frontmatter with `Grep` — no CLI, no model:

```bash
grep -h '^title:' ~/.claude/knowledge/raw/2026-0[456789]*.md ~/.claude/knowledge/raw/2026-1*.md 2>/dev/null \
  | sed 's/^title: *//' | sort > /tmp/kb-titles.txt
# Flag titles sharing 3+ words
awk '{for(i=1;i<=NF;i++) words[$i]++} END{for(w in words) if(words[w]>=3) print w}' /tmp/kb-titles.txt
```

Flag pairs with suspiciously similar titles for manual review.

### D2 — Manual review

Read both articles. Determine: same lever (merge), different angles (keep both, cross-reference), or one supersedes the other (mark older with `## Maintenance: superseded by <new-slug>`).

Don't auto-delete; leave history visible.

## Operation: RUBRIC OPS

The four rubrics are raw `.md` files in `~/.claude/knowledge/raw/`. Edit them directly — no CLI round-trip, no temp files.

Canonical slugs: `claude-agent-sdk-rubric`, `claude-code-rubric`, `claude-managed-agents-rubric`, `codex-sdk-rubric`.

### R1 — Find + Read

Use `Glob` to locate the file, then `Read` it directly:

```bash
# Find the file
ls ~/.claude/knowledge/raw/*-claude-agent-sdk-rubric.md
```

Then `Read` the full path returned. No CLI, no JSON parsing.

### R2 — Edit in-place

Use `Edit` on the raw file path to append rows to the relevant `### <Category>` table:

```
| <When you need to...> | <Reach for affordance> | <article slug> | <docs URL> |
```

Slug comes from: `ls ~/.claude/knowledge/raw/<date>-<slug>.md` after ingest — the filename IS the slug (minus `.md`).

### R3 — Reindex

```bash
/home/$USER/.local/bin/workflow knowledge reindex
```

Single call rebuilds the search index. No re-ingest needed — the file was already edited in place.

Verify the rubric is readable:

```bash
ls ~/.claude/knowledge/raw/*-claude-agent-sdk-rubric.md && echo "ok"
```

## Reference files

- [`references/frontmatter-schema.md`](references/frontmatter-schema.md) — Required frontmatter, sections, tag taxonomy. Read before writing any article.
- [`references/surface-urls.md`](references/surface-urls.md) — Per-feature canonical docs URLs for all four surfaces. Read before WebFetching.
- [`references/ingest-gotchas.md`](references/ingest-gotchas.md) — PATH shadow, slug renaming, lint --strict failure modes, search-score interpretation, ingest JSON quirks. Read if any phase command fails.

## Bundled scripts

- [`scripts/detect_updates.py`](scripts/detect_updates.py) — State-tracker. Two modes: `--json` (read current upstream + diff against state.json), `--commit-state` (write current versions to state.json after successful REFRESH).
- [`scripts/build_browser.py`](scripts/build_browser.py) — Regenerates the operator-facing browser `~/.claude/knowledge/knowledge-browser.html` from `raw/*.md` frontmatter. Self-contained single file (gallery design system; embeds an `#artifact-data` JSON block for cheap agent re-read — dual-surface pattern, html-artifact skill). No args, idempotent. Run after **any** KB content mutation (REFRESH Phase E, INGEST I3, MAINTAIN frontmatter fixes). The HTML is a generated view — never the canonical copy; `raw/*.md` stays canonical.

## Test prompts (evals)

See [`evals/evals.json`](evals/evals.json) for the test prompt set. Four canonical operations:

1. `"Refresh the Claude tooling KB — has anything new shipped since last week?"` → REFRESH
2. `"Audit KB URLs for staleness — re-verify the SDK feature pages still resolve."` → MAINTAIN
3. `"I have a draft article on the new Codex `mcp` feature at /tmp/article.md — ingest it."` → INGEST
4. `"Find any overlapping articles in the agent SDK section."` → DEDUPE

## Gotchas

These are the traps the maintainer hit on the first KB pass (2026-05-22). Future runs will hit them again unless flagged in [`references/ingest-gotchas.md`](references/ingest-gotchas.md).

- **PATH shadow on WSL-2.** Always use `/home/$USER/.local/bin/workflow` by full path.
- **Long titles → renamed slugs on ingest.** Rubric titles must be exactly the 4 canonical short forms.
- **`date_published: unknown` is required.** Haiku writers omit it; pre-flight grep before lint.
- **Ingest renames during re-ingest can leave orphan files.** Manually `rm` the old slug file when changing titles.
- **Search scores are negative (BM25-like).** Lower magnitude = better match.
- **Parallel Haiku writers are the cost lever.** 4 in parallel writing 10-15 articles each = 2-3 min wall-clock.
- **Don't trust `whats-new` for canonical URLs.** Week-N pages move; use per-feature sub-pages from `references/surface-urls.md`.

## Maintenance of this skill

When this skill's surface area changes:

- **New surface appears** (e.g., Anthropic releases a new SDK family): add a 5th entry to `references/surface-urls.md`, update `scripts/detect_updates.py` delta sources, write a new rubric article (`<surface>-rubric` slug). Tell user to add a 5th BEFORE trigger to `~/.claude/CLAUDE.md`.
- **Schema changes** (new required frontmatter field, new section): update `references/frontmatter-schema.md` and the example in this SKILL.md.
- **Taxonomy expansion** (new tag, user-approved): update `references/frontmatter-schema.md` § Tag taxonomy.
- **Phase command breaks** (workflow CLI flag changes, lint shape changes): update the inline bash in this SKILL.md and `references/ingest-gotchas.md`.

## Anti-patterns

- **Don't auto-ingest before lint.** Bad articles poison search results.
- **Don't write rubric rows citing slugs that don't exist yet.** Either ingest first, or cite article titles (stable) instead.
- **Don't fan subagents per article.** 1 per surface (4 total) is the right granularity.
- **Don't write speculative articles.** Every article needs a verified docs URL. If the feature is mentioned in whats-new but has no own page, defer until docs land.
- **Don't merge MAINTAIN findings into REFRESH runs without telling the user.** Validation failures + adding new articles in one PR is hard to review; do them separately.
- **Don't edit `~/.claude/CLAUDE.md` triggers from this skill.** Even if new surfaces emerge. That's user-controlled.
