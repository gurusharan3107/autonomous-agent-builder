# Output-quality eval — does the skill beat no-skill?

Loaded when VALIDATE needs to prove the skill *adds value*, not just that it
activates. Triggering accuracy lives in [description-testing.md](description-testing.md);
this file measures **output quality against a baseline**.

The core question: run each test case **with the skill** and **without it**, then
compare. A skill that doesn't beat the no-skill baseline isn't earning its context.

---

## When to run

After the description triggers reliably (description-testing passed) and
`evals/evals.json` has 2-3 cases with assertions. Skip only for trivial prose
skills where a baseline run is obviously wasteful — but state that you skipped it.

---

## Step 1 — Workspace layout

One directory per iteration, each eval split into `with_skill/` and `without_skill/`:

```
<skill-name>-workspace/
└── iteration-1/
    ├── <eval-id>/
    │   ├── with_skill/    { outputs/  timing.json  grading.json }
    │   └── without_skill/ { outputs/  timing.json  grading.json }
    └── benchmark.json
```

When refining an existing skill, snapshot the old version
(`cp -r <skill> <workspace>/skill-snapshot/`) and use it as the baseline instead
of no-skill — save to `old_skill/` rather than `without_skill/`.

---

## Step 2 — Spawn paired runs

Each run starts with **clean context** so the agent follows only the SKILL.md —
use a subagent (Claude Code spawns fresh) or a separate session per run. For each
eval case, run twice with the same prompt + input files:

- **with_skill**: provide the skill path → save to `<eval>/with_skill/outputs/`
- **without_skill**: no skill path → save to `<eval>/without_skill/outputs/`

Capture cost per run in `timing.json`:

```json
{ "total_tokens": 84852, "duration_ms": 23332 }
```

In Claude Code these come from the subagent task-completion notification and are
**not persisted elsewhere** — record them immediately.

---

## Step 3 — Grade assertions

Evaluate each assertion from `evals/evals.json` against the actual outputs.
Use a **script** for mechanical checks (valid JSON, row count, file exists) and
an LLM for judgment. Require concrete evidence for every PASS — quote the output,
don't give benefit of the doubt. Write `grading.json` per run:

```json
{
  "assertion_results": [
    { "text": "output is valid JSON", "passed": true, "evidence": "parsed 412 records" },
    { "text": "both axes labeled", "passed": false, "evidence": "X-axis has no label" }
  ],
  "summary": { "passed": 1, "failed": 1, "total": 2, "pass_rate": 0.5 }
}
```

For version-vs-version refines, also try **blind comparison**: give both outputs
to an LLM judge without revealing which is which, scored on holistic quality.

---

## Step 4 — Aggregate the delta

Roll up to `benchmark.json`. The **delta** is the decision metric — what the skill
costs (time, tokens) vs. what it buys (pass-rate lift):

```json
{
  "with_skill":    { "pass_rate": 0.83, "tokens": 3800, "time_seconds": 45 },
  "without_skill": { "pass_rate": 0.33, "tokens": 2100, "time_seconds": 32 },
  "delta":         { "pass_rate": 0.50, "tokens": 1700, "time_seconds": 13 }
}
```

Decision rule: a +50pt pass-rate lift for +1700 tokens is worth it; a +2pt lift
that doubles tokens is not — cut or rescope the skill.

---

## Step 5 — Pattern analysis (turn results into fixes)

- **Drop assertions that pass in both** configs — the model handles them without
  the skill; they inflate the with-skill rate without reflecting value.
- **Investigate assertions that fail in both** — broken assertion, too-hard case,
  or checking the wrong thing.
- **Study assertions that pass-with / fail-without** — this is exactly where the
  skill earns its keep; understand *which instruction* made the difference.
- **Tighten instructions on high-variance evals** — same case passing sometimes
  and failing others means ambiguous SKILL.md guidance; add an example or default.
- **Bundle repeated work** — if every run reinvents the same helper, write it once
  into `scripts/` (design it per [templates.md](templates.md#scripts--design-for-agentic-use)).

Feed failed assertions + transcripts + current SKILL.md back into the next
iteration. Stop when the delta is satisfying or stops improving.
