# autonomous-agent-builder AGENTS.md

Codex: read `~/.codex/AGENTS.md` first, then this file. Claude: routed here by `.claude/CLAUDE.md` when doing dev work on this repo.

This file is the primary instruction surface for any agent doing dev work on `autonomous-agent-builder`. Keep it short: triggers, routing, boundaries, and dead ends only. Detailed policy belongs in `docs/`, `builder` quality gates, repo memory, or `.claude/skills/`.

`CLAUDE.md` is the Builder runtime contract for the Claude Agent SDK lane. It is product truth for runtime behavior, not the place for dev-on-source-repo operating rules.

## Builder Workspace

The canonical workspace for creating apps with this builder is:

```
/home/gurusharangupta/Builder-Workspace
```

Always initialize new apps (`builder init`) from that directory, not from
this source repo. Run all generated-app lifecycle work from there.

## Session Entry

Type `/start` at session start. Skill at `.claude/skills/start/SKILL.md` loads framework + STATUS Current Position + drift warnings + recent git log + prior CURRENT.md (when fresh) in one pass — replaces the per-session "check AGENTS.md and docs/goal/README.md" re-prompt. Use `/save-session` before exit.

## Start Here

Before non-trivial work, retrieve repo precedent from the builder repo root:

```bash
builder memory search "<task query>" --tag <relevant-tag> --limit 100
```

If the lane is unfamiliar, load the owner workflow or gate instead of guessing:

```bash
workflow --docs-dir docs summary <workflow-name>
builder quality-gate <surface> --json
```

For docs placement, read the owner map first:

```bash
workflow --docs-dir docs read REFERENCE
```

## Surface Ownership

- `AGENTS.md` owns Codex routing, validation entrypoints, and repo-local
  boundaries.
- `CLAUDE.md` owns Builder runtime behavior, phase/state contracts, and Claude
  Agent SDK lane invariants.
- `docs/REFERENCE.md` owns documentation placement and single-control-owner
  routing.
- `docs/PROMPT.md` owns operator prompt scripts.
- `docs/workflows/` owns multi-step procedures.
- `docs/quality-gate/` owns pass/fail checks.
- `builder knowledge` owns repo-local system docs and freshness checks.
- `builder memory` owns reusable repo corrections, decisions, and patterns.
- `.claude/skills/` owns executable governance: session entry/exit, audit, optimization, knowledge-freshness. Skills auto-trigger on operator phrases; closeouts self-schedule via `CronCreate`.

Do not move Builder runtime responsibilities into `~/.codex`. Do not copy
Codex-only guidance into `CLAUDE.md`.

## Library Documentation — Retrieval Policy

Never rely on training data for versioned libraries. Run `ctx7 docs <id> "<query>"` before writing code that touches any library surface. These five IDs are the highest-risk areas where training data produces silently wrong code:

| Surface | ctx7 ID |
|---|---|
| Claude Agent SDK (Python) | `/anthropics/claude-agent-sdk-python` |
| Codex SDK / Codex CLI | `/openai/codex` |
| Pydantic v2 | `/pydantic/pydantic` |
| SQLAlchemy 2.0 async ORM | `/websites/sqlalchemy_en_20_orm` |
| FastAPI | `/fastapi/fastapi` |

Full library map (all IDs, surface → library routing, key queries):
`workflow --docs-dir docs read references/library-retrieval-map`

## Required Triggers

- Before editing `AGENTS.md`:
  `workflow quality-gate agents-md`.
  Keep this surface compressed and correctly owned.
- Before editing `CLAUDE.md`:
  `builder quality-gate claude-md --json` and
  `workflow --docs-dir=docs summary quality-gate/claude-md`.
  Keep runtime-contract edits inside the Claude SDK lane.
- Before materially changing docs:
  `workflow --docs-dir docs read REFERENCE`.
  Avoid duplicate control-owner docs.
- Before new files, dirs, or abstractions:
  `workflow read principles --section Execution`.
  Check placement and enforcement doctrine.
- Before completion:
  `workflow read principles --section Evidence`.
  Verify with real evidence, not intent.
- Dashboard/frontend work:
  `workflow --docs-dir docs summary design-language` and
  `builder quality-gate dashboard-ux --json`.
  Preserve visible state/action/evidence contract.
- Lifecycle, Agent page, Board, Backlog, runtime, metrics, or generated-app
  troubleshooting:
  `workflow --docs-dir docs summary autonomous-lifecycle-validation`.
  Use dashboard-first validation and builder-owned evidence.
- Agent quality, context efficiency, model/tool/subagent tuning, or prompt
  shaping:
  `workflow --docs-dir docs summary agent-quality-tuning-loop` and
  `builder quality-gate agent-quality --json`.
  Start from real Builder session evidence before changing runtime guidance.
- Runtime failure or opaque Agent-page behavior:
  `builder logs --error --json`,
  `builder logs --info --compact --json`,
  `builder logs analyze --session <id-or-prefix> --json`, and
  `builder metrics show --json`.
  Diagnose from canonical Builder evidence.
- Repo-local KB checks:
  `builder knowledge validate --json`, then
  `builder knowledge summary "<query>"` or
  `builder knowledge show <doc> --section "Change guidance"`.
  Verify trust/freshness before relying on KB output.
- Builder CLI changes:
  `workflow quality-gate cli-for-agents`,
  `builder quality-gate builder-cli --json`, and `builder map`.
  Keep CLI agent-friendly and page-aligned.
- Codex subagent changes:
  `builder quality-gate codex-subagents --json` and
  `python3 scripts/check_codex_subagents.py --repo-root .`.
  Keep project subagents Codex-only and bounded.
- Claude Agent SDK policy, specialists, hooks, permissions, or run evidence:
  `builder quality-gate claude-agent-sdk --json`,
  `builder quality-gate product-lifecycle --json`,
  `builder quality-gate state-integrity --json`, and
  `builder quality-gate architecture-invariants --json`.
  Keep runtime mechanics subordinate to Builder state and lifecycle contracts.
- Phase-boundary or operator-question changes:
  `workflow --docs-dir docs summary phase-model`.
  Preserve canonical phase semantics.
- Task isolation or resume behavior:
  `workflow --docs-dir docs summary task-workspace-isolation`.
  Preserve workspace identity and resume semantics.
- System-wide product improvement or real-user debugging:
  `workflow --docs-dir docs summary system-improvement-loop`.
  Reproduce, trace true owner, fix, and retest.

## Skill Triggers

Project-local skills auto-fire on listed phrases. Use as named entry points; don't rebuild their workflow by hand.

| Skill | Triggers | Purpose |
|---|---|---|
| `/start` | session entry, "hi", "where are we", "check AGENTS.md and docs/goal/README.md" | Load framework + STATUS + drift + git log + tactical handoff |
| `/save-session` | "save session", "checkpoint", context >70% used | Tactical handoff to next session via `.claude/session-data/CURRENT.md` |
| `/goal-audit` | "are we aligned?", "audit goals", ≥2-day gap | Intent ↔ direction audit; writes `docs/goal/INSIGHTS.md`; may reorder `docs/autoresearch/OPTIMIZE_IDEAS.md` |
| `/roadmap-audit` | "audit roadmap vs SDK", after KB rubric delta | Cross-check `docs/goal/ROADMAP.md` against KB rubric + live `grep src/` |
| `/knowledge-base` | "refresh KB", monthly | Maintain `~/.claude/knowledge/` against SDK upstream |
| `/autoresearch` | "run autoresearch", "baseline", "iterate", "fix the gap" | Three-lane optimization loop (Baseline / Iterate / Fix); owns `docs/autoresearch/` freshness |

## Product Validation Rules

- Dashboard lifecycle validation is browser-visible. Use Chrome first for the
  operator profile; use the Browser plugin second; use Computer Use third when
  direct browser control is blocked.
- After bootstrap and launch, lifecycle actions go through visible product
  surfaces: Agent page, Backlog, Board, Inbox, approvals, Metrics, and
  Observability.
- `builder` CLI commands are evidence, diagnosis, readiness, quality-gate, and
  maintainer-closeout lanes. Do not substitute CLI mutations, curl, raw API
  calls, database writes, or generated-app hand patches for dashboard lifecycle
  actions.
- Reverse-engineering validation uses a disposable external repo clone. Do not
  use `autonomous-agent-builder` itself as the reverse-engineering target.
- Generated-app troubleshooting must trace symptoms back to the Builder-owned
  cause. Do not patch generated apps by hand unless the task explicitly asks for
  generated-app source edits.

## Codex Productivity Rules

- Docs are agent-audience by default (see global `~/.claude/CLAUDE.md` Rules). Operator-friendly only on explicit request.
- Prefer deterministic Builder and workflow evidence before model judgment.
- Keep the main thread on implementation, review, and final integration.
- Use Codex subagents only when the task is explicitly delegated or the user
  asks for parallel agent work. Keep write scopes disjoint.
- Existing project Codex setup lives in `.codex/config.toml`,
  `.codex/agents/`, and `.codex/environments/environment.toml`.
- Local environment actions are appropriate for repeated run, test, lint, logs,
  metrics, and doctor commands. Do not turn approval-driven lifecycle actions
  into shortcut buttons.
- Prefer official plugins or native MCP before custom MCP. Avoid local
  stdio/process MCP unless the user explicitly approves local process and memory
  cost and no remote option fits.
- Do not add hooks or automations for unstable workflows. First prove the manual
  lane, then automate the narrow repeated edge.

## Memory And Closeout

After a user correction, two-attempt debugging friction, or a non-obvious
decision worth preserving, add repo memory from the builder repo root:

```bash
builder memory add --type correction|pattern|decision ... --json
```

For lifecycle-validation closeout after the product run, track durable findings
through Builder surfaces:

```bash
builder backlog item create --type incident|improvement|optimization \
  --source validation ... --json
builder memory contract --json
builder memory add --type pattern --phase testing ... --json
```

Memory writes must return passing post-mutation evidence. They do not count as
lifecycle-validation evidence.

For tactical session handoff — current intent, next action, blockers, mid-session learnings, NOT durable enough for memory or STATUS Recent Decisions — use `/save-session`. `/start` reads the resulting `.claude/session-data/CURRENT.md` on the next session.

## Dead Ends

- Do not create parallel control docs when `docs/REFERENCE.md` maps an owner.
- Do not put long procedures in `AGENTS.md`.
- Do not put Codex-only setup in `CLAUDE.md`.
- Do not use Codex CLI as a user-facing sprint validation lane.
- Do not bypass the dashboard with raw API, database, curl, or CLI mutations for
  lifecycle actions.
- Do not treat assistant summaries as transcript-audit evidence; use raw Codex
  JSONL user messages.
- Do not rely on stale counts, inventories, or session-analysis summaries as
  always-loaded rules.
