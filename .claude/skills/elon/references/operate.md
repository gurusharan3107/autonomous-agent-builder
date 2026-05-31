# operate — running the Musk-hat evaluation

Loaded when actually running the phases. **The questions are the skill.** The tools below only exist to answer them with evidence; never let a command run without knowing which question it answers.

## The one question, then five

> **Master question: "How much of this should exist at all?"**

Every phase is a refinement of it. Lead each phase by *stating the question out loud in the output*, then answer it with the cited evidence. A grade with no question is noise; a question with no evidence is an opinion.

| Phase | The question to ask | Answered by |
|---|---|---|
| 1 Requirements | "Why does this exist, and **who** asked for it?" | owner docs + dead-surface grep |
| 2 Delete | "What can be removed without anyone noticing?" | `evidence.py` + import-trace |
| 3 Simplify | "Is the complexity **earned** by the problem's physics?" | `/simplify` + code-simplifier |
| 4 Accelerate | "How fast can idea → running-in-prod?" | timing the loop |
| 5 Automate | "Are we automating a process that should be **deleted**?" | tooling review (last) |
| Correctness | "Is what survives the cut actually **correct**?" | `/code-review` |

## Branch out — harness Claude Code parallelism

The phases are sequenced, but the *evidence gathering inside* phases 1–2 is embarrassingly parallel. On any non-trivial codebase, **fan it out**. (Rules confirmed via claude-code-guide / Agent SDK docs.)

| Lever | How | When |
|---|---|---|
| **Parallel subagents** | Issue several `Agent` calls in **one assistant turn** → they run concurrently | dead-surface / duplicate hunt across subsystems |
| **Explore agent** (read-only) | `subagent_type: Explore`; sweeps many files, returns the conclusion not the dumps | phase 1–2 fan-out — the workhorse |
| **Plan agent** | `subagent_type: Plan` | drafting a tier's coupled-edit migration |
| **Skill tool** | `/simplify`, `/code-review` — **sequential**, not parallel | phases 3 + correctness |

**Orchestration rules (encode, don't improvise):**
1. **Cap concurrency at ~5–7** Agent calls per turn; more just queue.
2. **One subsystem per Explore agent.** Split `src/` by top-level package, give each agent one directory + one question.
3. **Mandate the return shape in every subagent prompt:** "Return only `file:line` refs + a 1-line conclusion per finding. Do NOT paste file contents." The parent inherits only the final message — keep it tiny (repo rule: context efficiency).
4. **Foreground, not background.** Orchestrated audits need the results inline; background-task completion is unreliable when several finish at once. Reserve `run_in_background` for one genuinely-independent long job.
5. **`/simplify` already parallelizes internally** (3 review subagents) — don't wrap it in more.
6. Deterministic first: run `scripts/evidence.py` *once* up front; it gives every Explore agent the LOC/dead-candidate seed list so they verify rather than re-discover.

## Phase 1 — Requirements sanity · *"Who asked?"*

Before judging quality, judge whether the code should be there. A beautifully-engineered module solving a fake requirement scores **zero**.

```bash
ROOT="$(git rev-parse --show-toplevel)"; cd "$ROOT"
# orphans: modules with no importer outside themselves + tests
# (run evidence.py --dead for the full sweep)
grep -rln "TODO\|FIXME\|deprecated" src --include='*.py' | head
# read the owner/boundary docs to learn the SUPPORTED surfaces
ls AGENTS.md CLAUDE.md docs/**/boundaries* 2>/dev/null
```

Trace each major surface to a named owner/requirement. Flag any surface the project's own docs say is unsupported, compat-only, or "kept in sync" — those are requirement-sanity failures.

## Phase 2 — Delete · *"What can be removed?"* (the cardinal phase)

```bash
python3 .claude/skills/elon/scripts/evidence.py --json   # ratio, LOC, largest, dead candidates
```

Then **import-trace every candidate before calling it deletable** (Hard rule 2):

```bash
M=<module>            # e.g. api/routes/features
grep -rln "$M" src --include='*.py' | grep -v "$M.py" | grep -v "/app.py"   # real importers?
grep -rln "$M" tests --include='*.py' | wc -l                               # test coupling
```

**A grep hit is not an import — open the line.** `grep -rln` counts string literals, error-codes, and attribute names too. Before any verdict, confirm each hit is an actual `import`/`from … import`:

```bash
grep -rn "$M" src --include='*.py' | grep -v "$M.py"        # see the actual lines, not just filenames
# a peer-count sanity check — a module with 0 importers while its siblings have many is the dead tell:
for s in <sibling1> <sibling2> $M; do echo -n "$s: "; grep -rln "\b$s\b" src --include='*.py' | grep -v "$s.py" | wc -l; done
```

**Then rule out dynamic dispatch before DEAD.** Static grep cannot see by-name loading. A module with 0 static importers may still be live:

```bash
grep -rn "importlib\|f\".*{.*}\"\|getattr(\|entry_points\|/$M\b\|\"$M\"" src --include='*.py' | head   # registries, by-name loaders
```

> Both failure directions are real (Hard rule 2): the precedent run over-claimed a delete; a later run wrongly KEPT a dead 225-LOC gate because a string literal matched its name, and nearly cut a live script that a registry loads by name. Open the line; count the peers; check dispatch.

**Fan out the trace.** Don't import-trace candidates serially — split the seed list from `evidence.py` by subsystem and dispatch parallel read-only Explore agents in one turn, e.g.:

```text
Agent(Explore, "Candidates from src/<pkgA>: <candidates>. For EACH, grep importers
  across ALL of src/ (NOT just src/<pkgA> — an importer can live anywhere),
  excluding only the candidate's own file and tests/. OPEN each matching line to
  confirm it's an actual import, not a string literal / error-code / attribute.
  Return file:line of each real importer + one verdict: DEAD / DUPLICATE-of-X /
  SHARED. No file contents.")
Agent(Explore, "...candidates from src/<pkgB>...")   # same turn → runs concurrently
```

> **Scope = which candidates, not where importers live.** The package split assigns *which modules each agent checks*; the importer search must still sweep all of `src/`. A run that scoped the importer grep to the assigned package returned false DEAD verdicts for modules used by a sibling package one directory over.

Classify each candidate from the returned verdicts:
- **DEAD** — 0 importers anywhere → clean delete.
- **DUPLICATE** — superseded by another surface that already covers it → delete after confirming coverage.
- **SHARED-BUT-MISLOCATED** — imported across the product → **KEEP** (rename/move, do not delete).

For every DEAD/DUPLICATE cut, write the **coupled-edit checklist**: callers to repoint, factory/registry branches to trim, config refs, tests to delete/rewrite — all same commit.

## Phase 3 — Simplify · *"Is the complexity earned?"*

Hand the surviving (non-deleted) code to the simplifier. Delete first so you don't polish parts about to be cut.

```text
Skill(simplify)          # /simplify — reuse/altitude/efficiency cleanup, applies fixes
Agent(code-simplifier)   # for a larger, multi-file simplification pass
```

Capture the idiot-index hotspots: files where complexity ≫ the fundamental difficulty of the problem (indirection, premature genericization, framework-on-framework).

## Phase 4 — Accelerate · *"How fast idea → prod?"*

```bash
python3 -m pytest --collect-only -q 2>&1 | tail -1     # collection time
time python3 -c "import <top_package>"                 # import time
# note build + deploy + CI time from project config if present
```

Cycle time gates the rate of learning — grade it high only if a one-line change reaches prod fast.

## Phase 5 — Automate (LAST) · *"Automating something that should be deleted?"*

Only now review codegen, tooling, CI elaborateness. Automation wrapped around a phase-2 deletion candidate is a *red* flag, not a green one. Never score this before 1–4.

## Correctness pass — *"Is what remains broken?"*

```text
Skill(code-review)       # /code-review on the post-deletion diff/tree — bugs only
```

Run on what *survives* the cut, so review effort isn't spent on doomed code.

## Assembling the output

1. **Scorecard** — 6 criteria (see [`best-practices.md`](best-practices.md) for the rubric), each: grade 0–10 + the cited command/number that set it.
2. **Tiered deletion list** — ordered by risk: clean deletes first, after-check deletes next, structural/refactor last. Each row: files · verified LOC · coupled-edit checklist · confirm-first caveats.
3. **Caveat** — the blind-spot paragraph (Hard rule 6).
4. **HTML artifact (standard, not optional)** — render via `html-artifact` report lane (`Skill` tool), save to `docs/audits/<repo>-musk-hat-<YYYY-MM-DD>.html`, `xdg-open` it. Must include: the scorecard table, the tiered deletion list with coupled-edit checklists, **the verification refutations** (candidates the script flagged that import-trace rejected — proof the discipline ran, in *both* directions: false-DEAD that were KEPT, false-orphans live via dynamic dispatch), and an `#artifact-data` JSON block mirroring every number. Reuse the precedent file's design system; don't re-derive tokens. **Render this LAST.** If the operator approved cuts and you executed them this session, the artifact must show outcomes (what shipped, which verdicts flipped under deeper tracing) — a snapshot rendered before execution and left unedited goes stale and self-contradictory.
