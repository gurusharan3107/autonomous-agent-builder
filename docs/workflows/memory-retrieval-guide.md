# Memory Retrieval Guide

Single source of truth for **agent memory** (`builder memory`) in this repo: when to look, what to look for, when to save, when to invalidate, and the cwd discipline that keeps the store clean.

> "Memory" in this repo always means agent memory at `/home/gurusharangupta/code/autonomous-agent-builder/.memory/` accessed via the `builder memory` CLI. There is no other memory store. Auto-memory under `~/.claude/projects/.../memory/` is reserved for cross-project user-level notes only — do not put repo-local lessons there.

## Cwd discipline (read first)

All `builder memory` mutating commands (`add`, `invalidate`, `graduate`, `relate`, `unrelate`, `flag`, `reindex`) must run with the **builder repo** as cwd:

```bash
cd /home/gurusharangupta/code/autonomous-agent-builder    # or the active builder worktree
builder memory <subcommand> ...
```

Never run mutating memory commands from a generated app workspace (`/home/gurusharangupta/Workspace/<app>/`, `/tmp/aab-workspaces/<task>/`, or any worktree the builder dispatches code-gen into). Doing so creates an entry in the *app's* `.memory/` and pollutes the generated workspace — covered by the `workspace-ownership` correction.

Read-only commands (`search`, `show`, `list`, `summary`, `stats`, `lint`, `contract`) are safe from any cwd, but for builder-development queries always cd to the builder repo first to be sure you are searching the correct store.

## When to look

Retrieve scoped precedent first. Default `--limit` is 20; pass `--limit 100` whenever a complete view matters.

| Situation | Query |
|-----------|-------|
| Task on any surface (general precedent check at task start) | `builder memory search "<surface keyword>" --tags <surface-tag> --limit 100` |
| Browser/UI verification (board, agent page, dashboard, feature acceptance) | `builder memory search "<surface>" --tags browser-testing,playwright --limit 100` |
| Writing or evaluating a fix | `builder memory search "<symptom>" --tags fix-discipline,debugging --limit 100` |
| About to add a guard or defensive check | `builder memory search "root cause" --tags fix-discipline,root-cause --limit 100` |
| About to change runtime/SDK policy (model, effort, thinking, prompt) | `builder memory search "<topic>" --tags sdk,policy,prompt-construction --limit 100` |
| About to mutate an app workspace under `Workspace/` or `aab-workspaces/` | `builder memory search "workspace" --tags workspace-ownership --limit 100` |
| About to edit AGENTS.md or runtime contracts | `builder memory search "<surface>" --tags <surface> --limit 100` *and* the relevant `workflow quality-gate <surface>` |
| Repeated error / recurring failure | `builder memory search "<error keyword>" --tags <relevant-tag> --limit 100` |
| Test work | `builder memory search "test <topic>" --tags testing --limit 100` |
| Server/runtime startup or shutdown | `builder memory search "<runtime topic>" --tags runtime --limit 100` |

Broad unfiltered search (no `--tags`) is acceptable only at the very start of a task as a precedent sweep.

## When to save

Save when one of these is true:

- The user issued a **correction**, preference, or workflow critique that should affect future runs (`--type correction`).
- A step took **≥2 wrong attempts** or fought a tool quirk before landing the working approach (`--type pattern`).
- A **non-obvious architectural or policy decision** was made that future agents would otherwise rediscover (`--type decision`).

Do **not** save:

- Obvious facts derivable from docs/code on first read.
- Transient state — current sprint plan, task IDs, per-run costs, token counts. Those live in `builder backlog`, `builder board`, `builder metrics`.
- Anything already documented in `CLAUDE.md` or `AGENTS.md`.
- Anything that duplicates an existing entry — search first with `--limit 100`. If the lesson is the same shape but newer/sharper, update or invalidate-and-replace; do not create a parallel entry.

### Save procedure

```bash
cd /home/gurusharangupta/code/autonomous-agent-builder           # mandatory cwd
builder memory search "<keywords>" --limit 100                   # confirm no duplicate
builder memory contract                                          # if unsure of frontmatter shape
# write content file with required sections (see below)
builder memory add --type correction|pattern|decision \
    --phase <phase> --entity <entity> \
    --tags <tag1>,<tag2>,<tag3> \
    --title "<title>" \
    --content-file /tmp/<file>.md --json
builder memory reindex --json                                    # rebuild routing.json
builder memory lint --json                                       # 0 errors required
builder memory list --limit 100                                  # verify the new slug landed
```

Required body sections (lint catches missing ones): `## <Decision|Pattern|Correction>`, `## Agent Retrieval Summary`, `## User-Facing Summary`, `## Reusable Guidance`, `## When To Apply`, `## Retrieval Queries`.

### Type → trigger mapping

| Trigger | Type | Tags (in order of relevance) |
|---|---|---|
| User corrected my approach or stated a preference | `correction` | the surface + `fix-discipline` / `workspace-ownership` / `memory-discipline` / `tool-quirk` |
| Found the only working interaction for a UI element / fix recipe (≥2 attempts) | `pattern` | the surface + technique tag (`testing`, `runtime`, `playwright`, `browser-testing`) |
| Non-obvious architecture, runtime policy, or SDK choice | `decision` | `sdk`, `policy`, `runtime`, or repo-area |
| Closeout finding from a validation run that materially shifts future testing | `pattern` with `--phase testing` | the surface + `testing` |

## Tag taxonomy

| Tag | Covers |
|-----|--------|
| `browser-testing` | Feature acceptance, dashboard verification — the browser slice |
| `playwright` | Playwright CLI wrapper interactions (the active browser tool) |
| `chrome-devtools` | Historical / superseded chrome-devtools-mcp patterns. Use only for archaeology, not for new patterns. |
| `agent-page` / `board` | Specific dashboard surfaces (composes with `browser-testing`) |
| `testing` | Test file patterns, fixture setup, missing deps, gate behavior |
| `sdk` | Claude Agent SDK runtime: execution policy, thinking, effort, autocompact |
| `policy` | Model routing, effort levels, task-budget decisions |
| `runtime` | Server start/stop, port management, restart, workspace bootstrap |
| `fix-discipline` | Verify-before-fix, root-cause-not-stacked-patches |
| `root-cause` | Origin-fix discipline (sibling of `fix-discipline`) |
| `debugging` | Reproduction, evidence-gathering, telemetry-first analysis |
| `tool-quirk` | Tooling artifacts that can masquerade as app bugs |
| `workspace-ownership` | The "never mutate app workspace" rule and its corollaries |
| `memory-discipline` | Rules about the memory system itself (this doc) |
| `prompt-construction` | Code-gen / agent prompt scope, ownership boundaries, cache discipline |

When inventing a new tag, first check whether an existing one fits. Two narrow tags compose better than one over-broad tag.

## Lifecycle: invalidate, graduate, replace

A stale active entry is worse than no entry. As soon as a memory becomes outdated, mark its lifecycle through the CLI; do not edit the markdown file directly.

| Situation | Command |
|---|---|
| Tool replaced, convention reversed, lesson no longer applicable | `builder memory invalidate <slug> --reason "<why> — see <replacement-slug>"` |
| Lesson moved into AGENTS.md, CLAUDE.md, or a workflow doc and no longer needs memory residency | `builder memory graduate <slug>` |
| New entry refines an old one substantially | save the new entry first, then `builder memory invalidate <old-slug> --reason "Superseded by <new-slug>"` |
| Two entries should be linked (e.g. correction + the pattern that resolves it) | `builder memory relate <slug-a> <slug-b>` |

After any lifecycle change: `builder memory reindex --json`, then verify with `builder memory list --limit 100`.

## What does NOT belong here

- Current sprint plan or task list — lives in `builder backlog`/`builder board`
- Per-run cost or token counts — lives in `builder metrics`
- Code patterns or architecture derivable from source
- Anything already in `CLAUDE.md` or `AGENTS.md`
- Cross-project user-level notes (those go in auto-memory at `~/.claude/projects/<slug>/memory/`)
- Generated-app workspace lessons (those should not exist; if a workspace has a defect, fix the builder surface that produced it)
