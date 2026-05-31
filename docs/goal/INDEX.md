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
| Direction-audit log (frozen) | [INSIGHTS.md](INSIGHTS.md) | Historical append-only log from the retired `goal-audit`/`roadmap-audit` skills. No longer written to; `start`'s drift check still reads its last verdict. |
| This routing map | [INDEX.md](INDEX.md) | What you are reading. |

### Executable governance layer

Project-local skills are the executable side of this framework. Triggered by single-word commands; each owns a workflow that would otherwise cost recurring prompts.

| Skill | Path | Triggers / role |
| --- | --- | --- |
| Session entry (primary) | [.claude/skills/start/](../../.claude/skills/start/SKILL.md) | `/start`, "begin", "hi", "where are we", "check AGENTS.md and docs/goal/README.md". Loads framework + STATUS + drift + git log + tactical handoff when fresh. |
| Session entry (tactical-first) | [.claude/skills/resume-session/](../../.claude/skills/resume-session/SKILL.md) | `/resume-session`. Reads CURRENT.md first, then chains into `start` for the rest. |
| Session exit | [.claude/skills/save-session/](../../.claude/skills/save-session/SKILL.md) | `/save-session`. Writes tactical checkpoint to `.claude/session-data/CURRENT.md`. |
| Self-optimize | [.claude/skills/self-optimize/](../../.claude/skills/self-optimize/SKILL.md) | "self-optimize", "what mistakes am I making". Clusters recurring corrections from session transcripts → maps to target surfaces → applies operator-approved edits. |
| Knowledge base | [.claude/skills/knowledge-base/](../../.claude/skills/knowledge-base/SKILL.md) | "refresh the KB", "what's new in SDK". Maintains the global `~/.claude/knowledge/` against upstream SDK changelogs. |
| Autoresearch loop | [.claude/skills/autoresearch/](../../.claude/skills/autoresearch/SKILL.md) | "run autoresearch", "baseline", "iterate". Single entry + 3 lanes (Baseline / Iterate / Fix); owns [docs/autoresearch/](../autoresearch/) freshness via bundled `freshness_sweep.py`. |
| Design (anti-AI-slop) | `~/.claude/skills/hallmark/` (global) | Used for high-design surfaces (e.g. `autonomous-agent-builder-runtime-explainer.html`). Sibling skill `html-artifact` (also global, `~/.claude/skills/html-artifact/`) covers single-file explainer / spec / report / editor outputs — produced `docs/autoresearch/autoresearch-explainer.html`. |
| Repo automation | [.claude/skills/run-gates/](../../.claude/skills/run-gates/SKILL.md), [.claude/skills/new-migration/](../../.claude/skills/new-migration/SKILL.md) | Deterministic slash-command-only skills (disable-model-invocation). Run quality gates / scaffold Alembic migrations. |

---

## External Owner Map (the rest of the repo)

**Repo-wide owner map lives in [docs/REFERENCE.md § Owner Map](../REFERENCE.md#owner-map)** — single source for every rubric, quality-gate, workflow, reference, and design-doc owner. Don't re-list it here (drift). REFERENCE.md wins for non-`docs/goal/` concerns; this file wins for `docs/goal/` concerns. Below: only bindings REFERENCE.md doesn't carry.

### Always-on policy surfaces

| Concern | Owner |
| --- | --- |
| Claude Agent SDK runtime contract | [CLAUDE.md](../../CLAUDE.md) |
| Codex agent operating rules | [AGENTS.md](../../AGENTS.md) |
| Project mission (consumed by CLAUDE.md / AGENTS.md) | [NORTH-STAR.md](NORTH-STAR.md) |

### Memory and knowledge access

| Concern | How to access |
| --- | --- |
| Repo-local memory (corrections, decisions, patterns) | `builder memory search "<query>" --tag <tag>` — from Builder source repo only (not managed-app workspaces; IMP-005) |
| Repo-local knowledge base | `builder knowledge summary "<query>"`, `builder knowledge validate --json`, `builder knowledge extract --force` |
| Memory write / invalidate contract | [FIX-STANDARD.md § Step 7](FIX-STANDARD.md#step-7--write-memory-back-if-durable) — `builder memory add\|invalidate ...` |

### Validation workspaces (where the agent runs live tests)

| Workspace | Path | Purpose |
| --- | --- | --- |
| Builder source repo | this repo root | Code/docs/memory changes, quality gates. Never `builder init` here; no managed-app session sweeps. |
| `Builder-Workspace/devpulse` | `/home/gurusharangupta/Builder-Workspace/devpulse` | Primary managed app for live operator-flow validation (Track A target). |
| `Workspace/todo-app` | `/home/gurusharangupta/Workspace/todo-app` | Prior workspace; reverse-engineering / Tier 2.3 scenarios. |
| Fresh managed apps | via `builder init` from `/home/gurusharangupta/Builder-Workspace/` | Forward-engineering (fresh app) scenarios. |

### Track B — autoresearch (ACTIVATING)

| Concern | Owner |
| --- | --- |
| Loop contract docs + result artifacts | [docs/autoresearch/](../autoresearch/) — README, OPTIMIZE, OPTIMIZE_IDEAS, HARNESS, METRICS, COMPARE, baseline_variance, fixtures; `*.tsv`, `iterations.json`, `autoresearch-explainer.html` |
| Lane discipline + folder freshness | [autoresearch skill](../../.claude/skills/autoresearch/SKILL.md) — Baseline / Iterate / Fix + `freshness_sweep.py` |
| Runner scripts | [scripts/autoresearch/](../../scripts/autoresearch/) — `run.py`, `baseline.py`, `compare.py`, `loop.py`, `extract_context_breakdown.py` |

Activation status: [autoresearch README § Status](../autoresearch/README.md#status). Milestone: [ROADMAP § M3.5](ROADMAP.md#m35--optimization-loop-activation-autoresearch-track-b).

---

## When To Update This File

- New file in `docs/goal/` → row in [Internal Map](#internal-map-within-docsgoal).
- New rubric / gate / workflow / reference / design-doc → row in [docs/REFERENCE.md § Owner Map](../REFERENCE.md#owner-map) (this file no longer re-lists them).
- New goal-specific binding (workspace, Track B artifact, memory command) → row in the matching [External Owner Map](#external-owner-map-the-rest-of-the-repo) table.
- Ownership boundary moves → update the owner in REFERENCE.md.
