---
name: knowledge-base
description: "All operations on the user's global Claude-tooling knowledge base at ~/.claude/knowledge/. The KB is the coding agent's first-stop discovery surface for SDK levers across Claude Code, Claude Agent SDK (Python+TS), Claude Managed Agents, and the OpenAI Codex SDK — when it's stale, the next session reinvents what already exists (see INSIGHTS Run #7's 13-IMP cost of context blindness). This skill handles every KB operation: REFRESH (detect upstream deltas + write gap articles for new features), MAINTAIN (validate URLs + lint + check rubric slug refs + flag staleness), INGEST (lint and add user-provided drafts with correct tags), AUDIT (full coverage re-check across all four surfaces), SEARCH (smart query expansion), DEDUPE (find overlapping articles), and RUBRIC OPS (read/edit/re-ingest the four surface rubrics). Use this skill proactively whenever the user says 'refresh the KB', 'audit the KB', 'is our KB current?', 'what's new in Claude SDK / Codex SDK?', 'update the rubrics', 'add this article to the KB', 'check if our KB has X', 'find overlapping KB articles', 'are KB URLs still valid?', 'have new features landed since last sweep?', or asks about adopting any Claude or Codex feature that may not yet be indexed. ALSO use proactively on a monthly cadence and after any major upstream release (new Anthropic Claude Code week, new Python/TS SDK minor version, new Codex CLI minor version). The four surface rubrics live at predictable slugs: claude-agent-sdk-rubric, claude-code-rubric, claude-managed-agents-rubric, codex-sdk-rubric. Skip this skill ONLY if the user explicitly says 'don't touch the KB' or asks a question that's already answered by the rubrics."
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

Pick the operation that matches the user's ask. If unclear, run REFRESH (most common entry point).

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

Then ingest each, extracting tags from frontmatter:

```bash
for f in /tmp/kb-drafts/<date>-*.md; do
  tags=$(python3 -c "
import re
with open('$f') as fh: head=fh.read()[:2000]
m=re.search(r'tags:\s*\[([^\]]+)\]', head)
print(','.join([p.strip().strip(chr(34)).strip(chr(39)) for p in m.group(1).split(',')]) if m else '')
")
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

Then persist state:

```bash
python3 .claude/skills/knowledge-base/scripts/detect_updates.py --commit-state
```

If new surfaces emerged (e.g., new SDK family), surface to user — DO NOT auto-edit `~/.claude/CLAUDE.md` triggers.

## Operation: MAINTAIN

Quarterly cadence — validate the KB's existing state.

### M1 — URL validity

For each article tagged `agents` or `coding-agents` written in the last 90 days, WebFetch `source_url` and check for 200 + content match. Use Haiku Explore subagents for parallelism (1 per surface).

If a URL 404s:
1. Search adjacent paths (e.g., `/docs/en/X` → `/docs/en/agent-sdk/X`)
2. If genuinely removed: add a `## Maintenance` note to the article explaining the docs deprecation, update the surface rubric to remove the row.
3. Don't delete the article — it's history.

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

For each of the 4 rubrics, read the body, extract slug references (pattern: `2026-XX-XX-<slug>`), and verify each resolves via `workflow knowledge read`. Flag mismatches — these happen when titles get renamed and rubric tables aren't updated.

```bash
/home/$USER/.local/bin/workflow knowledge read claude-agent-sdk-rubric --json | python3 -c "
import sys, json, re
content = json.load(sys.stdin).get('content','')
slugs = re.findall(r'2026-\\d{2}-\\d{2}-[\\w-]+', content)
print(f'{len(slugs)} slug refs')
for s in slugs[:20]: print(s)
" | while read slug; do
  status=$(/home/$USER/.local/bin/workflow knowledge read "$slug" --json 2>&1 | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))")
  if [ "$status" != "ok" ]; then echo "BROKEN: $slug"; fi
done
```

Fix the rubric by replacing broken slugs with current ones (use `workflow knowledge search` to find).

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
```

If the article belongs to one of the four surfaces, add a row to its rubric (see RUBRIC OPS).

## Operation: AUDIT

Same as REFRESH but skips the delta-gate. Every feature on the surface-urls map (`references/surface-urls.md`) becomes a candidate; each is searched against the KB; gaps proceed to write. Use for first-run or after a long gap (>30 days since last REFRESH).

## Operation: SEARCH

User asks "what do we know about X?" or "is there a KB article on Y?":

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

For each pair of recently-ingested articles, compute title-token overlap via `workflow knowledge list --json`. Flag pairs with >50% overlap.

### D2 — Manual review

Read both articles. Determine: same lever (merge), different angles (keep both, cross-reference), or one supersedes the other (mark older with `## Maintenance: superseded by <new-slug>`).

Don't auto-delete; leave history visible.

## Operation: RUBRIC OPS

The four rubrics are index articles with a `## Evidence` section containing rubric tables. Predictable slugs:

- `claude-agent-sdk-rubric`
- `claude-code-rubric`
- `claude-managed-agents-rubric`
- `codex-sdk-rubric`

### R1 — Read

```bash
/home/$USER/.local/bin/workflow knowledge read claude-agent-sdk-rubric --json | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('content', d.get('article',{}).get('content','')))
" > /tmp/rubric.md
```

### R2 — Edit

Open `/tmp/rubric.md`, find the relevant `### <Category>` table, append rows:

```
| <When you need to...> | <Reach for affordance> | <article slug> | <docs URL> |
```

Use the ingested slug — read from `workflow knowledge read <slug>` post-ingest. For long lever-article titles, the slug is auto-truncated; cite the actual ingested slug, not the file basename.

### R3 — Re-ingest

```bash
# Title is unchanged → slug is unchanged → ingest overwrites
/home/$USER/.local/bin/workflow knowledge ingest /tmp/rubric.md --tags agents,coding-agents,architecture,tools
```

Re-verify by reading:

```bash
/home/$USER/.local/bin/workflow knowledge read claude-agent-sdk-rubric --json | python3 -c "import sys,json; print(json.load(sys.stdin).get('status'))"
```

## Reference files

- [`references/frontmatter-schema.md`](references/frontmatter-schema.md) — Required frontmatter, sections, tag taxonomy. Read before writing any article.
- [`references/surface-urls.md`](references/surface-urls.md) — Per-feature canonical docs URLs for all four surfaces. Read before WebFetching.
- [`references/ingest-gotchas.md`](references/ingest-gotchas.md) — PATH shadow, slug renaming, lint --strict failure modes, search-score interpretation, ingest JSON quirks. Read if any phase command fails.

## Bundled scripts

- [`scripts/detect_updates.py`](scripts/detect_updates.py) — State-tracker. Two modes: `--json` (read current upstream + diff against state.json), `--commit-state` (write current versions to state.json after successful REFRESH).

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
