---
name: elon
description: "Evaluate a codebase or diff through the Musk engineering algorithm — question requirements, DELETE, simplify, accelerate cycle time, automate last — scored against hard git/grep evidence, not impressions. Produces an evidence-grounded 6-criterion scorecard (deletion ratio, idiot index, requirements sanity, cycle time, automate-last, vertical ownership) plus a VERIFIED, import-checked, tiered deletion list with per-cut coupled-edit checklists. Orchestrates the built-in /code-review command (find what's broken) and /simplify command + code-simplifier agent (reduce mass, apply cuts) as phases inside the algorithm. Optionally renders the report via html-artifact. Use when the operator says 'put the Elon hat on', 'elon', 'musk hat', 'first-principles audit', 'what can we delete', 'deletion ratio', 'idiot index', 'is this codebase too big', 'what should we delete', 'audit this codebase for bloat', 'find dead/duplicate code to cut', or pairs delete/cut/prune/simplify with first-principles/Musk/should-this-exist language. NOT for finding correctness bugs alone (use /code-review), pure style cleanup (use /simplify), agent-harness scoring (agentharness-audit), or project-quality/CLAUDE.md freshness (/audit)."
allowed-tools: Read, Edit, Bash, Skill, Agent, Write
---

# elon — first-principles codebase evaluation (the Musk hat)

The operator wants the *opposite* of a conventional review: not "is this well-written?" but **"how much of this should exist at all?"** This skill scores a codebase or diff against Musk's engineering algorithm using hard git/grep evidence, then hands back a scorecard and a deletion list where every cut is import-verified and carries its coupled-edit checklist.

> **Self-validate after edits.** Run `./scripts/validate.sh` from the skill directory.

## Decision aid — the algorithm IS the phase order (run in sequence)

| # | Phase | Question | Tool / sub-skill | Evidence produced |
|---|---|---|---|---|
| 1 | **Requirements sanity** | Should this exist? Who asked? | grep dead/unused surfaces; read owner docs | unsupported lanes, orphan features |
| 2 | **Delete** | What can be removed? | `scripts/evidence.py` + **import-trace** | deletion ratio, dead code, duplicate surfaces |
| 3 | **Simplify** | Is complexity earned? | `/simplify` + `code-simplifier` agent | idiot-index hotspots, over-abstraction |
| 4 | **Accelerate** | How fast idea→prod? | time the test/build/import | cycle-time numbers |
| 5 | **Automate (last)** | Only after 1–4 | review tooling/codegen mass | automation atop deletable surfaces |
| — | **Correctness pass** | Is what remains broken? | `/code-review` | bugs in code that survives the cut |

Phases 3, 5, and the correctness pass wrap the built-in commands; phases 1, 2, 4 are the hat's own evidence work. Full procedure + exact recipes: [`references/operate.md`](references/operate.md).

**Branch out for speed.** The evidence work in phases 1–2 is embarrassingly parallel — fan it out across concurrent read-only `Explore` subagents (one subsystem each, ~5–7 per turn), each returning only `file:line` + a one-line verdict. `/simplify` and `/code-review` go through the `Skill` tool (sequential; `/simplify` already parallelizes internally). See [`references/operate.md` § Branch out](references/operate.md).

## Hard rules

1. **Evidence over impressions.** Every grade and every LOC figure traces to a command (git numstat, `wc -l`, route/import grep). No estimates in the output — if unmeasured, write `—`. This is the whole point of the hat.
2. **Import-trace before any verdict — and a grep hit is not an import.** A surface is "delete" only after grepping its importers *outside itself and tests*, and "keep" only after a *real* importer is confirmed. **Open every matching line: a hit can be a string literal, error-code, or attribute name, not an `import`.** The trap cuts both ways — the precedent run over-claimed a −3,628 LOC delete that import-tracing cut to ~1,164, *and* a later run wrongly KEPT a dead 225-LOC gate for two passes because the string literal `"missing_runtime_boundary"` matched its name. Two cross-checks that catch both: (a) a module with **0 importers while its peers have 6–19** is the dead tell; (b) before calling anything DEAD, check **dynamic dispatch** (`importlib`, by-name registry loading like `f"...{name}"`, entry points) — static grep can't see it (a script loaded by name in `executor.py` looked orphan but was live). Shared-but-mislocated ≠ dead. See [`references/agent-handbook.md`](references/agent-handbook.md).
3. **Every cut ships its coupled-edit checklist.** A delete that leaves callers, factory branches, config refs, or tests red is a break, not a delete. List the same-commit edits per cut (repo rule: behavioral change → test update in the same commit).
4. **Order is law: delete before simplify, simplify before automate.** Never praise automation built atop a surface that should be deleted (Musk's Tesla-line trap). Judge phase 5 only after 1–4.
5. **Legitimate axis ≠ duplication.** A split along a real product axis (per-runtime, per-SDK) is kept; a split that is *not* a product axis (duplicate apps, dead lanes) is a cut. Ask which axis before flagging.
6. **State the blind spots.** The hat under-weights correctness, security, and long-horizon maintainability by design. The output must carry that caveat so it pairs *with* a conventional review, not replaces it.

## Closeout — mandatory

- Emit the **scorecard** (6 criteria, each graded 0–10 with the evidence that set it) and the **tiered deletion list** (per cut: files, verified LOC, coupled-edit checklist, confirm-first caveats).
- **Always render the report as an HTML artifact** — it is a standard deliverable of this skill, not optional. Use the `html-artifact` report lane (via the `Skill` tool), save to `docs/audits/<repo>-musk-hat-<YYYY-MM-DD>.html`, embed an `#artifact-data` JSON block (scorecard + tiered list + verification refutations) so numbers stay machine-readable, and `xdg-open` it. Precedent: `docs/audits/musk-hat-audit-2026-05-30.html`.
- **Render the artifact AFTER any approved execution, not before.** If the operator approves and you execute cuts in the same session, the artifact must reflect *outcomes* (which cuts shipped, which verdicts changed under deeper tracing) — a report rendered as a recommendation snapshot then left unedited goes stale and self-contradictory (e.g. listing a "KEEP" for something you then deleted). Render last, or update it post-cut before declaring done.
- Route findings per repo convention (builder-side → `docs/goal/ROADMAP.md` or `builder backlog`; app-side → managed-app backlog). Do **not** execute deletions unless the operator approves a tier.

## Load references on need

| When | Load |
|---|---|
| Running the phases (exact recipes; how to invoke /code-review & /simplify) | [`references/operate.md`](references/operate.md) |
| Grading a criterion / what earns each score / the caveat text | [`references/best-practices.md`](references/best-practices.md) |
| Editing this skill, the precedent run, the over-claim lesson | [`references/agent-handbook.md`](references/agent-handbook.md) |
| Gathering quantitative evidence deterministically | [`scripts/evidence.py`](scripts/evidence.py) — deletion ratio, LOC, largest files, dead-import candidates |
