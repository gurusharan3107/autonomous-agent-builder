---
name: autonomy-audit
description: "Audit any app, skill, agent, tool, script, or repo against 13 autonomy-readiness criteria — observability-first watchdog, preserved forensics, pattern catalog as data, learning-trigger signals, narrow detection predicates, cost budgets, fix propagation, durable state, honest failure, safe-to-fail, LLM-fallback diagnosis, auto-apply governance, meta-orchestrator escalation — and produce a prioritized optimization list. Each criterion has a machine-checkable predicate; the audit grades pass/partial/fail/unknown with evidence + fix_pointer per criterion. Use when the operator says 'audit this for autonomy', 'is X self-evolving', 'autonomy audit', 'is this loop autonomous', 'how autonomous is this skill', 'audit autonomy readiness', '/autonomy-audit', 'can this run unattended', 'is this self-optimizing', 'does this need an operator to drive every cycle', or names a specific target (a skill dir, a Python package, a shell harness, a repo) and asks whether it qualifies as a genuinely self-evolving system. Also use proactively when reviewing a new skill before promotion, after an operator complains a loop 'sits there doing nothing', or when an existing skill has hit the same failure twice (sign the pattern catalog is missing). Output: JSON primary (one record per criterion: {id, name, verdict, confidence, evidence, fix_pointer}) for downstream piping, plus a markdown summary report. Same output shape as .claude/skills/autoresearch/scripts/diagnose_hang.py. Audit-only — surfaces proposed fixes as suggestions; operator applies manually. Static checks always run; dynamic checks (briefly launching the target) require --dynamic and 60s wallclock cap per probe."
allowed-tools: Read, Bash, Write, AskUserQuestion
---

# autonomy-audit — does this thing actually run without me?

> **Self-validate after edits.** Any change to this skill's files (SKILL.md, scripts/, references/, templates/, assets/) must be followed by `./scripts/validate.sh` from the skill directory. Hard findings → create-skill Optimize lane.

Audits a target system against 13 narrow predicates that distinguish genuinely self-evolving loops from systems that *look* autonomous in slideware but require an operator to drive every cycle. The criteria are grounded in the autoresearch 11-cycle Fix loop of 2026-05-23 (commit `6fa9f90`) — each criterion corresponds to a real failure mode that broke that loop until the criterion was satisfied. Output is per-criterion `{id, verdict: pass|partial|fail|unknown, evidence, fix_pointer, confidence}` JSON + a markdown summary; the operator applies fixes manually.

## Entry — pick a lane

First action is `AskUserQuestion` (unless the typed prompt already names a lane):

| Lane | When to choose |
|---|---|
| **Audit** | Run the 13 predicates against a named target and emit JSON + markdown. The default and only v1 lane. |
| **Recommend** *(v2 — not yet implemented)* | Take an existing audit JSON, rank fixes by leverage × applicability, produce an ordered remediation plan. v1 falls back to Audit lane and notes "Recommend lane is v2 — see fix_pointer column for now." |

Skip the question when the typed prompt names a lane unambiguously:

| Phrase pattern | Lane | Skip? |
|---|---|---|
| "audit autonomy of X" / "/autonomy-audit X" / "is X self-evolving" / "how autonomous is X" | Audit | Yes |
| "rank the autonomy fixes" / "what should I optimize first" *(v2)* | Recommend | Yes |
| ambiguous ("look at this") | — | **No — ask.** |

After lane selection, run the Audit lane in [`references/audit.md`](references/audit.md).

## Audit at a glance

```bash
# Static-only audit of a target (skill dir, Python package, repo)
python3 .claude/skills/autonomy-audit/scripts/audit.py <target-path>

# Add dynamic probes (briefly launches target, 60s cap per probe)
python3 .claude/skills/autonomy-audit/scripts/audit.py <target-path> --dynamic

# Machine-readable
python3 .claude/skills/autonomy-audit/scripts/audit.py <target-path> --json
```

Exit 0 = audit ran cleanly (verdicts may still include `fail`). Exit 1 = the audit itself failed (target unreadable / structurally broken). Verdicts: `pass` (predicate satisfied), `partial` (some sub-checks pass), `fail` (predicate missing/broken), `unknown` (insufficient evidence — typical for dynamic checks without `--dynamic`).

The 13 criteria + their predicates + their fix_pointer templates live in [`references/criteria.md`](references/criteria.md). The audit script consults that catalog; the two must stay in sync.

## Hard rules (universal — apply to every audit)

1. **Predicates, not vibes.** Every criterion reduces to a machine-checkable predicate against the target's source/config/runtime artifacts. "Does it have observability?" is vibes. "Does the target define a watchdog or external monitor that detects idle state within a configurable threshold AND dumps artifacts to a persisted directory?" is checkable. Full predicates in [`references/criteria.md`](references/criteria.md). Do not invent new criteria during audit; if a new failure mode emerges, encode it as C14+ via `create-skill` Optimize lane.
2. **`unknown` is a valid verdict.** If the predicate can't be evaluated (target unreadable, structure unrecognized, dynamic check skipped), the verdict is `unknown` with `confidence < 0.5` and evidence describing what's missing. Forcing a pass/fail when uncertain calcifies wrong conclusions — same discipline as `diagnose_hang.py`.
3. **Audit-only — no auto-apply.** v1 surfaces `fix_pointer` strings as suggestions. Auto-apply governance is itself criterion C12; this skill is the *auditor*. Applying fixes is operator-driven or a future companion skill.
4. **The output shape is fixed.** JSON records: `{id, name, verdict, confidence, evidence: list[str], fix_pointer: str}`. Same shape as `diagnose_hang.py`. Downstream tooling depends on this — do not extend without bumping `schema_version`.
5. **Dynamic checks are optional + bounded.** Static checks always run. Dynamic probes (launching target briefly) run only when `--dynamic` is passed AND the target is runnable; each probe has a 60s wallclock cap and never modifies the target.
6. **Narrow predicates discriminate.** A predicate that would match two different failure modes is too coarse. If `match_C1` would fire on both "has a watchdog" and "has a logger," split the criterion or tighten the regex. See autoresearch P5/P6/P9 for the canonical "three different sprint-blocked bugs, three different predicates" example.

## Cross-references

- [`references/criteria.md`](references/criteria.md) — the 13 criteria, each with narrow predicate + static check + dynamic check + fix_pointer template
- [`references/audit.md`](references/audit.md) — Audit lane procedure (Preflight / Do / Closeout)
- [`scripts/audit.py`](scripts/audit.py) — deterministic audit; `<target-path>` + flags `--json`, `--dynamic`, `--criterion C7`
- [`scripts/validate.sh`](scripts/validate.sh) — self-validation wrapper around create-skill's audit.py
- Originating session: commit `6fa9f90` in this repo — autoresearch 11-cycle Fix loop that discovered the criteria
- Worked example: [`.claude/skills/autoresearch`](../autoresearch/SKILL.md) — the only known target that satisfies all 13 criteria today

## Why this skill exists

After today's autoresearch session, the autonomy criteria are concrete (11 cycles of real failure modes, each tied to a fix). But that knowledge is locked in one commit + one CHANGELOG entry. Without an executable audit, the next agent reviewing a different skill / app / loop will either reinvent the criteria from scratch or skip them — both paths produce non-autonomous systems that look autonomous on a slide. This skill makes the criteria a checkable artifact that runs against any target in <1 minute and emits structured findings. Same architectural pattern as `diagnose_hang.py`: encode the learning so the next session compounds off it instead of repeating it.
