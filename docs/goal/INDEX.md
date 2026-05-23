# Index — Owner Map

> Read [README.md](README.md) first.

Routing layer between `docs/goal/` and the rest of the repo. Answers:

1. Inside `docs/goal/` — which file owns which concern? (Internal map.)
2. Outside `docs/goal/` — which surface? (External map — references, doesn't duplicate.)

Before creating any new doc, check here. Per [docs/REFERENCE.md § Control Owner Rule](../REFERENCE.md#control-owner-rule): **one control owner per concern**.

---

## Internal Map (within `docs/goal/`)

| Concern | Owner file | Notes |
| --- | --- | --- |
| Bootstrap rules for any agent landing on the project | [README.md](README.md) | Read first, every session. Don't add content here that belongs in another `docs/goal/` file. |
| Product mission, three-fold success bar, differentiators, non-goals, design principles, agent working principles | [NORTH-STAR.md](NORTH-STAR.md) | Changes only when the mission or definition of "preferred" itself changes. |
| Three-epoch roadmap (Stabilize → Differentiate → Scale), milestones, items | [ROADMAP.md](ROADMAP.md) | The spine of all work. Items use `[ ]` / `[x]`. |
| Tiered evaluation scorecard (Tier 1 token+UX, Tier 2 lifecycle coverage, Tier 3 head-to-head) | [EVALUATION.md](EVALUATION.md) | Bars and verification commands per tier. |
| Seven-step fix standard for every non-trivial defect closure | [FIX-STANDARD.md](FIX-STANDARD.md) | Step 0 (read memory) and Step 7 (write memory) make repo learning compound. |
| Operator language contract: banned terms, good/bad prompts, operator scenarios F/E/R | [OPERATOR-LANGUAGE.md](OPERATOR-LANGUAGE.md) | Binds both sides of the operator transcript (human tester and agent reply). |
| Tuning methodology: continuous CLI monitoring + per-prompt tuning loop | [TUNING.md](TUNING.md) | Manual / interactive counterpart to the autoresearch loop. |
| Live project state: current epoch, milestone, item, next action, blockers, evidence pointers, tier snapshot | [STATUS.md](STATUS.md) | Agent-updated per milestone transition. Keep under ~120 lines. |
| Resume protocol after session drop / handover | [RESUME.md](RESUME.md) | Four modes: Continue / Continue-Track-B / Re-pick / Ask. |
| Direction-audit log (skill output) | [INSIGHTS.md](INSIGHTS.md) | Append-only log written by the `goal-audit` skill at `.claude/skills/goal-audit/`. One dated entry per invocation. |
| This routing map | [INDEX.md](INDEX.md) | What you are reading. |

### Executable governance layer

Project-local skills are the executable side of this framework. Triggered by single-word commands; each owns a workflow that would otherwise cost recurring prompts.

| Skill | Path | Triggers / role |
| --- | --- | --- |
| Session entry (primary) | [.claude/skills/start/](../../.claude/skills/start/SKILL.md) | `/start`, "begin", "hi", "where are we", "check AGENTS.md and docs/goal/README.md". Loads framework + STATUS + drift + git log + tactical handoff when fresh. |
| Session entry (tactical-first) | [.claude/skills/resume-session/](../../.claude/skills/resume-session/SKILL.md) | `/resume-session`. Reads CURRENT.md first, then chains into `start` for the rest. |
| Session exit | [.claude/skills/save-session/](../../.claude/skills/save-session/SKILL.md) | `/save-session`. Writes tactical checkpoint to `.claude/session-data/CURRENT.md`. |
| Direction audit | [.claude/skills/goal-audit/](../../.claude/skills/goal-audit/SKILL.md) | "are we aligned?", "audit goals". Writes [INSIGHTS.md](INSIGHTS.md); may reorder [docs/autoresearch/OPTIMIZE_IDEAS.md](../autoresearch/OPTIMIZE_IDEAS.md). |
| Roadmap audit | [.claude/skills/roadmap-audit/](../../.claude/skills/roadmap-audit/SKILL.md) | "revalidate the roadmap", "audit roadmap vs SDK". Cross-checks ROADMAP against the Claude Agent SDK rubric + live `grep src/`. |
| Knowledge base | [.claude/skills/knowledge-base/](../../.claude/skills/knowledge-base/SKILL.md) | "refresh the KB", "what's new in SDK". Maintains the global `~/.claude/knowledge/` against upstream SDK changelogs. |
| Autoresearch loop | [.claude/skills/autoresearch/](../../.claude/skills/autoresearch/SKILL.md) | "run autoresearch", "baseline", "iterate". Single entry + 3 lanes (Baseline / Iterate / Fix); owns [docs/autoresearch/](../autoresearch/) freshness via bundled `freshness_sweep.py`. |
| Design (anti-AI-slop) | [.claude/skills/hallmark/](../../.claude/skills/hallmark/SKILL.md) | Used to produce `docs/autoresearch/iterations.html` and `autonomous-agent-builder-runtime-explainer.html`. |
| Repo automation | [.claude/skills/run-gates/](../../.claude/skills/run-gates/SKILL.md), [.claude/skills/new-migration/](../../.claude/skills/new-migration/SKILL.md) | Deterministic slash-command-only skills (disable-model-invocation). Run quality gates / scaffold Alembic migrations. |

---

## External Owner Map (the rest of the repo)

References existing surfaces; doesn't duplicate. [docs/REFERENCE.md](../REFERENCE.md) is authoritative for doc concerns; this section binds most-used owners to `docs/goal/` use cases.

### Legacy strategic docs (still authoritative for their narrow concerns)

| Legacy file | What it owned | Migration status |
| --- | --- | --- |
| [docs/PLAN.md](../PLAN.md) | 10-bullet operating instructions. | **Migrated.** All 10 bullets now live as Hard Rules in [README.md](README.md) (rules 8-12 added in migration). PLAN.md is a deprecation stub pointing here. |
| [docs/GOAL.md](../GOAL.md) | Primary goal, testing standard, fix standard (steps 0-7), acceptance thresholds, per-agent boundaries, tuning methodology, forbidden operator language, operator scenarios (F1-F10, E1-E9, R1-R3), guiding principles. | **Migrated.** Primary goal → [NORTH-STAR.md](NORTH-STAR.md). Testing standard + thresholds → [EVALUATION.md](EVALUATION.md). Fix standard → [FIX-STANDARD.md](FIX-STANDARD.md). Tuning methodology → [TUNING.md](TUNING.md). Forbidden language + operator scenarios → [OPERATOR-LANGUAGE.md](OPERATOR-LANGUAGE.md). Guiding principles → [NORTH-STAR.md § Agent Working Principles](NORTH-STAR.md#agent-working-principles-always-on). Per-agent boundaries referenced via [docs/rubric/autonomous-builder-agents.md](../rubric/autonomous-builder-agents.md). GOAL.md is a deprecation stub pointing here. |
| [docs/MISSION.md](../MISSION.md) | Durable product mission and design principles. | **Migrated.** Mission, thesis, principles, non-goals, end state → [NORTH-STAR.md](NORTH-STAR.md). MISSION.md is a deprecation stub. |
| [docs/PROGRESS.md](../PROGRESS.md) | Historical evidence archive: every shipped fix, every decomposition pass, every dated proof. | **Stays.** [STATUS.md](STATUS.md) is the current state; PROGRESS.md is the audit-trail history. Do not write current state into PROGRESS.md; do not write history into STATUS.md. |
| [docs/IMPROVEMENTS.md](../IMPROVEMENTS.md) | Active operator-facing bug list (IMP-001 to IMP-005 today). Living document. | **Stays.** [ROADMAP § M1.1](ROADMAP.md#m11--close-the-open-operator-facing-defects) references IMP-NNN items; the bug detail itself stays in IMPROVEMENTS.md. |
| [docs/SPRINT-PROGRESS.md](../SPRINT-PROGRESS.md) | Per-sprint checklist for the active validation cycle. | **Stays.** Sprint detail stays in SPRINT-PROGRESS.md. ROADMAP.md is longer-arc; SPRINT-PROGRESS.md is the shorter-arc working doc inside the current sprint. |
| [docs/PROMPT.md](../PROMPT.md) | Operator prompt scripts for SDK-backed Agent and Realtime Voice rubric validation, in both runtime lanes. | **Stays.** [EVALUATION.md § Tier 2.5](EVALUATION.md#25--rubric--quality-gate-pass-bar) and [OPERATOR-LANGUAGE.md](OPERATOR-LANGUAGE.md) cite PROMPT.md as the source for prompt wording during tier runs. |
| [docs/QUALITY_SCORE.md](../QUALITY_SCORE.md) | Static audit snapshot of code-review/operator-validation rating (last audit 2026-05-15). | **Stays.** Snapshot evidence; reference from STATUS.md when applicable. Not duplicated. |
| [docs/REFERENCE.md](../REFERENCE.md) | Authoritative doc-type taxonomy and owner map for the whole repo. | **Stays.** This INDEX.md inherits and respects REFERENCE.md's ownership rules. If they diverge, REFERENCE.md wins for non-`docs/goal/` concerns; INDEX.md wins for `docs/goal/` concerns. |
| [CHANGELOG.md](../../CHANGELOG.md) | Compact reverse-chronological change history. | **Stays.** Reference from STATUS.md when latest changes matter; do not duplicate. |

### Runtime contracts (always-on policy)

| Concern | Owner |
| --- | --- |
| Claude Agent SDK runtime contract for this repo | [CLAUDE.md](../../CLAUDE.md) |
| Codex agent operating rules for this repo | [AGENTS.md](../../AGENTS.md) |
| Project mission (consumed by CLAUDE.md / AGENTS.md and external references) | [docs/MISSION.md](../MISSION.md) (deprecation stub) → [NORTH-STAR.md](NORTH-STAR.md) is the live source |

### Rubrics (what an agent or capability can do, must ask for, cannot do)

| Concern | Owner |
| --- | --- |
| SDK-backed Agent page behavior | [docs/rubric/sdk-backed-agent-page-agent.md](../rubric/sdk-backed-agent-page-agent.md) |
| Realtime Voice (Samantha) behavior | [docs/rubric/realtime-voice-agent-page-agent.md](../rubric/realtime-voice-agent-page-agent.md) |
| Operator capability limits | [docs/rubric/operator-limits.md](../rubric/operator-limits.md) |
| Autonomous Builder agent catalog | [docs/rubric/autonomous-builder-agents.md](../rubric/autonomous-builder-agents.md) |
| Deterministic vs model-backed agent behavior | [docs/rubric/deterministic-vs-model-backed-agent-behavior.md](../rubric/deterministic-vs-model-backed-agent-behavior.md) |
| Frontend React architecture | [docs/rubric/frontend-react-architecture.md](../rubric/frontend-react-architecture.md) |
| Backend service architecture | [docs/rubric/backend-service-architecture.md](../rubric/backend-service-architecture.md) |

### Quality gates (pass/fail expectations and verification commands)

| Concern | Owner |
| --- | --- |
| Claude Agent SDK runtime quality | [docs/quality-gate/claude-agent-sdk.md](../quality-gate/claude-agent-sdk.md) |
| Modular runtime (both-lane) integrity | [docs/quality-gate/modular-runtime.md](../quality-gate/modular-runtime.md) |
| Product lifecycle behavior | [docs/quality-gate/product-lifecycle.md](../quality-gate/product-lifecycle.md) |
| State integrity (DB / artifact / projection) | [docs/quality-gate/state-integrity.md](../quality-gate/state-integrity.md) |
| Agent quality / context efficiency | [docs/quality-gate/agent-quality.md](../quality-gate/agent-quality.md) |
| Architecture invariants | [docs/quality-gate/architecture-invariants.md](../quality-gate/architecture-invariants.md) |
| Architecture boundary | [docs/quality-gate/architecture-boundary.md](../quality-gate/architecture-boundary.md) |
| Dashboard UX | [docs/quality-gate/dashboard-ux.md](../quality-gate/dashboard-ux.md) |
| Complexity / god-file ratchet | [docs/quality-gate/complexity.md](../quality-gate/complexity.md) (baseline: [complexity-baseline.json](../quality-gate/complexity-baseline.json)) |
| Approval safety | [docs/quality-gate/approval.md](../quality-gate/approval.md) |
| Builder CLI behavior | [docs/quality-gate/builder-cli.md](../quality-gate/builder-cli.md) |
| Knowledge base format and freshness | [docs/quality-gate/knowledge-base.md](../quality-gate/knowledge-base.md) |
| Generated-app acceptance | [docs/quality-gate/generated-app-acceptance.md](../quality-gate/generated-app-acceptance.md) |
| Codex subagents | [docs/quality-gate/codex-subagents.md](../quality-gate/codex-subagents.md) |
| Documentation agent | [docs/quality-gate/documentation-agent.md](../quality-gate/documentation-agent.md) |
| Verification | [docs/quality-gate/verification.md](../quality-gate/verification.md) |
| Quality gates (meta) | [docs/quality-gate/quality-gates.md](../quality-gate/quality-gates.md) |

### Workflows (multi-step procedures)

| Concern | Owner |
| --- | --- |
| Dashboard-first lifecycle validation | [docs/workflows/autonomous-lifecycle-validation.md](../workflows/autonomous-lifecycle-validation.md) |
| Agent quality tuning loop | [docs/workflows/agent-quality-tuning-loop.md](../workflows/agent-quality-tuning-loop.md) |
| System improvement / real-user debugging | [docs/workflows/system-improvement-loop.md](../workflows/system-improvement-loop.md) |
| Architecture boundary review | [docs/workflows/architecture-boundary-review.md](../workflows/architecture-boundary-review.md) |
| Task workspace isolation | [docs/workflows/task-workspace-isolation.md](../workflows/task-workspace-isolation.md) |
| Memory retrieval | [docs/workflows/memory-retrieval-guide.md](../workflows/memory-retrieval-guide.md) |

### References (stable contracts and architecture facts)

| Concern | Owner |
| --- | --- |
| Phase model and boundaries | [docs/references/phase-model.md](../references/phase-model.md) |
| Day-0 readiness contract | [docs/references/day-0-readiness.md](../references/day-0-readiness.md) |
| Runtime settings and supported SDK lanes | [docs/references/runtime-settings.md](../references/runtime-settings.md) |
| Runtime switching dashboard behavior | [docs/references/runtime-switch-dashboard-contract.md](../references/runtime-switch-dashboard-contract.md) |
| Claude SDK telemetry and observability | [docs/references/claude-agent-sdk-telemetry-observability.md](../references/claude-agent-sdk-telemetry-observability.md) |
| Builder CLI contract | [docs/references/builder-cli.md](../references/builder-cli.md) |
| Realtime Voice integration | [docs/references/realtime-voice-integration.md](../references/realtime-voice-integration.md) |
| Filesystem trust boundaries | [docs/references/filesystem-boundaries.md](../references/filesystem-boundaries.md) |
| Documentation agent contract | [docs/references/documentation-agent.md](../references/documentation-agent.md) |

### Design docs (rationale, options, tradeoffs)

| Concern | Owner |
| --- | --- |
| Design language and dashboard visual rules | [docs/design-docs/design-language.md](../design-docs/design-language.md) |
| Agent page hierarchy | [docs/design-docs/agent-page-hierarchy.md](../design-docs/agent-page-hierarchy.md) |
| Modular runtime architecture | [docs/design-docs/modular-runtime-architecture.md](../design-docs/modular-runtime-architecture.md) |
| Knowledge graph / KB UI patterns | [docs/design-docs/knowledge-graph-ui.md](../design-docs/knowledge-graph-ui.md), [docs/design-docs/knowledge-ui-patterns.md](../design-docs/knowledge-ui-patterns.md) |

### Memory and knowledge (durable durable learnings and system docs)

| Concern | Surface | How to access |
| --- | --- | --- |
| Repo-local memory (corrections, decisions, patterns) | [.memory/](../../.memory/) under the Builder source repo | `builder memory search "<query>" --tag <tag>` (from Builder source repo, not managed-app workspaces — see IMP-005) |
| Repo-local knowledge base | Builder DB / `docs/` system docs | `builder knowledge summary "<query>"`, `builder knowledge validate --json`, `builder knowledge extract --force` |
| Memory write contract | [FIX-STANDARD.md § Step 7](FIX-STANDARD.md#step-7--write-memory-back-if-the-learning-is-durable) | `builder memory add --type correction|pattern|decision --tag <tags>` |
| Memory invalidation | [FIX-STANDARD.md § Step 7](FIX-STANDARD.md#step-7--write-memory-back-if-the-learning-is-durable) and IMP-005 in IMPROVEMENTS.md | `builder memory invalidate <slug> --reason <one-line>` |

### Validation workspaces (where the agent runs live tests)

| Workspace | Path | Purpose | Notes |
| --- | --- | --- | --- |
| Builder source repo | This repo's root | Code/docs/memory changes, complexity ratchet, source-side quality gates | Never run `builder init` here; do not use for managed-app session sweeps. |
| `Builder-Workspace/devpulse` | `/home/gurusharangupta/Builder-Workspace/devpulse` | Primary managed app for live operator-flow validation | Current Track A validation target; IMP-001 to IMP-004 surfaced here. |
| `Workspace/todo-app` | `/home/gurusharangupta/Workspace/todo-app` | Prior validation workspace; reverse-engineering scenarios | Reference for completed sprints; useful for Tier 2.3 reverse-engineering tests. |
| Fresh managed apps | Created on demand via `builder init` from `/home/gurusharangupta/Builder-Workspace/` | Forward-engineering scenarios (fresh app from scratch) | Bootstrap before any first-product test. |

### Track B (ACTIVATING — see autoresearch/README.md)

| Concern | Owner |
| --- | --- |
| Autoresearch loop contract docs | [docs/autoresearch/README.md](../autoresearch/README.md), [docs/autoresearch/OPTIMIZE.md](../autoresearch/OPTIMIZE.md), [docs/autoresearch/OPTIMIZE_IDEAS.md](../autoresearch/OPTIMIZE_IDEAS.md), [docs/autoresearch/HARNESS.md](../autoresearch/HARNESS.md), [docs/autoresearch/METRICS.md](../autoresearch/METRICS.md), [docs/autoresearch/COMPARE.md](../autoresearch/COMPARE.md), [docs/autoresearch/baseline_variance.md](../autoresearch/baseline_variance.md), [docs/autoresearch/fixtures.md](../autoresearch/fixtures.md) |
| Autoresearch lane discipline + folder freshness | [.claude/skills/autoresearch/](../../.claude/skills/autoresearch/SKILL.md) — owns Baseline / Iterate / Fix lanes + bundled `freshness_sweep.py` |
| Autoresearch runner (5 Python scripts) | [scripts/autoresearch/](../../scripts/autoresearch/) — `run.py`, `baseline.py`, `compare.py`, `loop.py`, `extract_context_breakdown.py` |
| Autoresearch result artifacts | [docs/autoresearch/optimize_results.tsv](../autoresearch/optimize_results.tsv), [docs/autoresearch/baseline_runs.tsv](../autoresearch/baseline_runs.tsv), [docs/autoresearch/per_prompt_results.tsv](../autoresearch/per_prompt_results.tsv), [docs/autoresearch/iterations.html](../autoresearch/iterations.html), [docs/autoresearch/iterations.json](../autoresearch/iterations.json), [docs/autoresearch/INTROSPECTION.md](../autoresearch/INTROSPECTION.md) |

Activation status is in [docs/autoresearch/README.md § Status](../autoresearch/README.md#status). Roadmap milestone: [ROADMAP § M3.5](ROADMAP.md#m35--optimization-loop-activation-autoresearch-track-b).

---

## When To Update This File

- New file in `docs/goal/` → row in [Internal Map](#internal-map-within-docsgoal).
- New rubric / gate / workflow / reference → row in relevant [External Owner Map](#external-owner-map-the-rest-of-the-repo) section.
- Legacy doc retired/absorbed → update its row; don't delete (history matters).
- Ownership boundary moves → update both rows.

New concern not fitting any row → also update [docs/REFERENCE.md](../REFERENCE.md) (repo-wide owner map; this inherits).
