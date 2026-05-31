# agent-handbook — modifying the elon skill

## Architecture

```
elon/
├── SKILL.md              router: the master question, the 5-phase decision aid, 6 hard rules, closeout
├── scripts/
│   ├── evidence.py       deterministic metric gathering (no model judgment): deletion ratio, LOC,
│   │                     largest files, dead-import candidates → JSON or text
│   └── validate.sh       canonical audit wrapper (do not customize)
└── references/
    ├── operate.md        the phases, question-first, with exact recipes + sub-skill invocation
    ├── best-practices.md the 6-criterion rubric, deletion-ratio bands, the mandatory caveat
    └── agent-handbook.md (this file)
```

No `optimize.md` — this skill has no runtime services to debug; failure recovery (a deletion claim that import-trace contradicts) is a *procedure* step, so it lives in `operate.md` phase 2.

## Design rationale

- **The question is the product, the tools are servants.** `evidence.py`, `/code-review`, `/simplify` only exist to answer the phase questions with evidence. The skill is structured question-first because a grade without a stated question is just an opinion. This is the operator's explicit emphasis — keep it central in any edit.
- **The algorithm dictates phase order**, not convenience. Delete (2) before simplify (3) before automate (5); correctness pass last so review effort isn't spent on doomed code. Reordering breaks the doctrine (Musk's Tesla-line trap: he automated before deleting and had to rip it out).
- **Orchestration over reimplementation.** Phases 3 and correctness *delegate* to the built-in `/simplify` and `/code-review` commands rather than re-encoding their logic — that's the "scaffolded in" design the skill was asked for. If those commands change, this skill inherits the change for free.
- **Branch out, don't serialize.** Phase 1–2 evidence is fanned across concurrent read-only `Explore` subagents (claude-code-guide-confirmed: parallel `Agent` calls in one turn, cap ~5–7, each returns only its final message). `evidence.py` runs once up front to seed them so they *verify* rather than re-discover. `Plan` agent drafts a tier's migration. `/simplify`/`/code-review` stay on the `Skill` tool (sequential — Skill calls don't parallelize; `/simplify` already spawns 3 reviewers internally).
- **No custom `.claude/agents/` files — on purpose.** The built-in `Explore`/`Plan` agents cover the fan-out; adding bespoke agent files would be exactly the unnecessary mass this skill exists to cut. If a future repeatable specialist need emerges, that's when to add one (claude-code-guide: custom subagents suit repeatable specialist tasks) — not before.

## Hard-won lessons

1. **Import-trace before sizing any delete (Hard rule 2).** The precedent run (`docs/audits/musk-hat-audit-2026-05-30.html`) first claimed "delete `api/` · −3,628 LOC." Import-tracing revealed `api/` was *mostly shared infrastructure the embedded server imports* — only ~1,164 LOC was a true duplicate shell. The verified total dropped from 4,566 to ~2,100. **A grep of importers outside the file+tests is non-negotiable before the word "delete" appears.** Shared-but-mislocated → KEEP (rename), never delete.
2. **A delete without its coupled-edit checklist is a break.** Dead runtime adapters were woven into a factory dispatch, 4 config refs, and ~6 tests. Listing the same-commit edits per cut is part of the deliverable, not a follow-up.
3. **Distinguish the real product axis from duplication.** When the operator said "I have 2 lanes (Claude SDK + Codex SDK)," that *confirmed* the cut (5 runtime adapters → 2 lanes means 3 are excess) rather than excusing it — but only because lane-split (legitimate) was separated from app-split (duplication). Always ask "is this split a product axis?" first.
4. **A grep hit is not an import — the over-KEEP trap is symmetric to the over-delete one (Hard rule 2).** Second pass (`docs/audits/autonomous-agent-builder-musk-hat-2026-05-31.html`): `quality_gates/runtime_boundary.py` (225 LOC) was marked **KEEP** by the prior audit *and* the first trace of this run because `codex_subagents.py` contained the *string literal* `"missing_runtime_boundary"` — an error-code, not an `import`. It actually had 0 importers vs 6–19 for its 4 sibling gates (the peer-count tell). Lesson: open every matching line; a `grep -rln` filename hit proves nothing until you see the line is an `import`. The fix is encoded in Hard rule 2 + `operate.md` phase 2 (peer-count + open-the-line + dynamic-dispatch checks).
5. **`evidence.py` orphan heuristic under-reported — self-exclusion bug, now fixed.** Its dead-import scan removed only the `# FILE <path>` *marker line* from the corpus, leaving the file's own body in — so a module that names itself in a string (e.g. `architecture_evidence.py`'s own path strings) counted as self-referenced and hid from the heuristic (it surfaced only via a manual per-module sweep). Fixed to excise the whole own-file segment (marker → next marker). If a candidate looks suspiciously absent from the script output, run the manual sweep in `operate.md` phase 2.
6. **Static grep can't see dynamic dispatch — check before DEAD.** `embedded/scripts/ask_user.py` had 0 static importers but is loaded by name (`executor.py` builds the module path from a string). Rule out `importlib` / by-name registry / entry-point loading before any DEAD verdict. Encoded in Hard rule 2 + phase-2 recipe.
7. **Render the HTML artifact last.** The second pass rendered the report as a *recommendation* snapshot, then the operator approved and cuts were executed in the same session — leaving the artifact listing a "KEEP" for a module that had just been deleted. Render after execution, or update the artifact post-cut before declaring done (encoded in SKILL.md closeout + `operate.md` assembling-the-output).

## Editing conventions

- Keep SKILL.md a router (≤ ~150 lines). New procedure → `operate.md`; new rubric nuance → `best-practices.md`; new lesson → here.
- After any edit: `./scripts/validate.sh` must exit 0.
- The precedent artifact path is the canonical worked example — update it here if a better run supersedes it.
- `scripts/evidence.py` stays deterministic. Anything needing judgment (classifying dead vs shared) is a *procedure*, not a script — it belongs in `operate.md`.
