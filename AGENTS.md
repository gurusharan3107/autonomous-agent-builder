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
- Project-local `.claude/skills/` overrides global `~/.claude/skills/`. When
  a skill with the same name exists in both, always use the project-local
  version — it encodes repo-specific adaptations the global version lacks.
  Check `.claude/skills/` before `~/.claude/skills/`.

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

> Global `~/.claude/CLAUDE.md` is always in context and owns the cross-project
> BEFORE/AFTER triggers (AGENTS.md edits, new files/abstractions → principles
> Core/Execution, completion → Evidence, build-quality-gate, placement). Do not
> restate them here — this section holds only repo-local triggers global lacks.

- Before editing `CLAUDE.md`:
  `builder quality-gate claude-md --json` and
  `workflow --docs-dir=docs summary quality-gate/claude-md`.
  Keep runtime-contract edits inside the Claude SDK lane.
- Before materially changing docs:
  `workflow --docs-dir docs read REFERENCE`.
  Avoid duplicate control-owner docs.
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
- Writing external code (harness, scripts, tests) that calls `builder` CLI:
  Run the command live once to see real output, verify field names, and add
  shape assertions to `.claude/skills/autoresearch/scripts/test_harness_contracts.py`
  before writing extraction code. Never trust CLI output shape from memory or
  training data — drift across builder versions caused the entire P1–P15
  failure class (8 of 18 patches burned before a contract test caught it).
- Codex subagent changes:
  `builder quality-gate codex-subagents --json` and
  `python3 scripts/check_codex_subagents.py --repo-root .`.
  Keep project subagents Codex-only and bounded.
- Claude Agent SDK policy, specialists, hooks, permissions, or run evidence:
  `builder quality-gate claude-agent-sdk --json`,
  `builder quality-gate product-lifecycle --json`,
  `builder quality-gate state-integrity --json`, and
  `builder quality-gate architecture-boundary --json`.
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
- Before committing any behavioral change (condition removed or relaxed,
  event type swapped, output text changed, function deleted):
  (a) `grep -rn "old string" tests/` for every string being changed —
  update all matching assertions in the same commit;
  (b) run `pytest tests/` and ensure green before committing.
  Test updates belong in the same commit — never commit known failures.
- After any import reorganization (moving, extracting, or renaming a module):
  `python3 -c "from <changed_module> import <changed_symbol>"` before
  committing — import errors only surface at pytest collection time.
- Before staging any new untracked file (`??` in `git status`):
  `grep -rn "<filename>" src/ tests/ .claude/` — zero results = dead code,
  do not stage. A file with no callers/importers outside itself ships nothing
  and must be wired or deleted (the dead-file-committed revert class).
- Before reporting any fix or feature complete (src/ or tests/ touched):
  self-initiate `pytest tests/ -q` (must pass) and
  `builder quality-gate <surface> --json` for the touched surface.
  Do not wait for the operator to ask — verify proactively and report
  evidence in the same message as the completion claim. State the **root
  cause** the change fixes, not the symptom — if you can't name it, the fix
  is a patch and isn't done.
  Skip when the change is docs-only (no `src/` or `tests/` modified).
- When the change touches a UI/dashboard surface (`frontend/`, the embedded
  dashboard bundle, or any operator-visible page/control): the completion
  claim must also include a live `/hermes-chrome` **browser-leg** result
  (real browser, visible cursor, surface swept) — pytest + quality-gate alone
  do not prove a UI change. No browser-leg evidence ⇒ the item stays
  `T:browser:pending`, not done.
- When adding `os.environ["X"] = ...` in any non-test file:
  add `"X"` to the `isolate_runtime_settings` delenv list in
  `tests/conftest.py` in the same commit — env var side-effects leak into
  unrelated tests via pydantic BaseSettings reads.
- Before committing skill changes: run `git status` and confirm all skill
  files are staged — SKILL.md + scripts/ + references/ + evals/ + any new
  asset. A commit containing only SKILL.md leaves the skill broken for the
  next agent that tries to run it.
- No intermediate commits. Commit only when a ROADMAP item is checked off
  or a fix is complete and verified. Skill evaluation artifacts are exempt
  (never commit them).
- Before acting on any audit or optimization recommendation:
  `grep -rn "<the claim>" src/` or `builder quality-gate <surface> --json`
  to confirm the gap still exists in current code. Recommendations are
  point-in-time; the codebase may have moved on. Acting on a stale
  recommendation wastes API budget and introduces noise.
- Use `python3` (never bare `python`) in subprocess commands inside tests.
- For test isolation traps specific to this repo's DB layer, see repo memory:
  `builder memory search "test isolation" --tag testing`

## Skill Triggers

Project-local skills auto-fire on listed phrases. Use as named entry points; don't rebuild their workflow by hand.

| Skill | Triggers | Purpose |
|---|---|---|
| `/start` | session entry, "hi", "where are we", "check AGENTS.md and docs/goal/README.md" | Load framework + STATUS + drift + git log + tactical handoff |
| `/save-session` | "save session", "checkpoint", context >70% used | Tactical handoff to next session via `.claude/session-data/CURRENT.md` |
| `/knowledge-base` | "refresh KB", monthly | Maintain `~/.claude/knowledge/` against SDK upstream |
| `/autoresearch` | "run autoresearch", "baseline", "iterate", "fix the gap" | Three-lane optimization loop (Baseline / Iterate / Fix); owns `docs/autoresearch/` freshness |
| `/self-optimize` | "self-optimize", "what mistakes am I making", "what keeps going wrong", "analyze recurring issues", "why do I keep correcting you", "encode learnings", "self-introspect", ≥3-day gap with unresolved correction entries in memory | Analyze session transcripts + git fix-commit patterns → cluster recurring mistake themes → map to target surfaces → apply operator-approved edits; tracks last-run history to detect recurred patterns |

## Subagent Fleet (orchestrator routing)

Dev work on this repo is orchestrator-led: the main thread routes, synthesizes,
commits, and approves; mechanical/search/verify/isolated work is delegated to the
project-local fleet in `.claude/agents/` (`repo-scout`, `planner`, `implementer`,
`test-sync-verifier`, `browser-verifier`, `security-reviewer`, `session-maintainer`).
Code review uses the `/code-review` command. Routing rules, per-agent model·effort·
isolation, the no-hooks approval model, and the `permission_mode: default` keystone:
`workflow --docs-dir docs read workflows/orchestrator-routing`.

- Any `src/` change → `implementer` then `test-sync-verifier` before the orchestrator commits.
- "mine the agent sessions / fix blockers agents hit / tighten agent prompts" → `session-maintainer`.
- No hooks in this managed env: enforcement is tool allowlists + orchestrator-owned commits + CI.

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
- Finding routing: when a session surfaces a defect, improvement, or
  optimization — route it to the correct surface before acting:
  **builder-related** (orchestrator, agents, lifecycle, dashboard, CLI) →
  `docs/goal/ROADMAP.md` via `builder backlog item create --source validation`;
  **managed-app-related** (feature behavior, UI, app code) → that app's
  backlog only. Never cross-route. An app finding logged to ROADMAP clutters
  builder scope; a builder finding logged to an app backlog disappears.

## Codex Productivity Rules

- Prefer deterministic Builder and workflow evidence before model judgment.
- Keep the main thread on implementation, review, and final integration.
- Use Codex subagents only when the task is explicitly delegated or the user
  asks for parallel agent work. Keep write scopes disjoint.
- Existing project Codex setup lives in `.codex/config.toml`,
  `.codex/agents/`, and `.codex/environments/environment.toml`.
- Local environment actions are appropriate for repeated run, test, lint, logs,
  metrics, and doctor commands. Do not turn approval-driven lifecycle actions
  into shortcut buttons.
- Subprocess calls in harness, CI, and scripts: use `capture_output=True` and
  write combined stdout+stderr to a named evidence file (e.g.
  `evidence_dir/feature_check.log`). Never rely on `-q` flags or inherited fds
  on external tools called from non-interactive contexts — silent failures
  hide the root cause across multiple wasted iterations.

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
- Do not edit managed app files directly as operator — all managed-app product
  work (features, fixes, improvements) must be dispatched through the builder
  dashboard lane (Agent page → task → approve). Direct file edits in a managed
  app workspace (any workspace initialized via `builder init`) bypass the
  builder lifecycle and are invisible to board/backlog state. The operator's
  write surface is this source repo only.
