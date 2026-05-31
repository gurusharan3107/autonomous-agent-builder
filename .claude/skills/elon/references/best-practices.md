# best-practices — scoring rubric, the central question, caveats

## The hat's one belief

> **Every line of code is a liability carried forever, not an asset banked once.**
> So the first question is never "is this well-written?" — it's **"how much of this should exist at all?"**

A beautifully-engineered module solving a fake requirement scores **zero**. The grade rewards *absence of unnecessary mass*, not craftsmanship. Hold this belief or the skill degrades into a normal review.

## The 6-criterion scorecard

Grade each 0–10 from cited evidence. The composite is **not** an average — the hat fixates on the lowest bar that represents *unnecessary mass* (usually criterion 2).

| # | Criterion | The question | 9–10 looks like | 0–3 looks like |
|---|---|---|---|---|
| 1 | Requirements sanity | "Who asked for this?" | every surface traces to a named owner/requirement | engineering invested in unsupported/compat/dead lanes |
| 2 | **Deletion ratio** | "What can be removed?" | recent history removes mass; ≥10% add-back | grows-only; <0.15 del:add; dead + duplicate surfaces |
| 3 | Idiot index / simplicity | "Is complexity earned?" | complexity ≈ problem's physics | indirection, dup apps, framework-on-framework |
| 4 | Cycle time | "Idea → prod, how fast?" | one-line change reaches prod in minutes | slow CI + multi-day release gates a 1-line fix |
| 5 | Automate (last) | "Automating something deletable?" | automation sits atop a minimal, deleted-down base | clever tooling wrapped around doomed surfaces |
| 6 | Vertical ownership | "Can one person reason end-to-end?" | clear owner per concern; no diffusion | "the framework decided"; sync-coupled twins |

### Deletion-ratio bands (criterion 2)
`del:add` over the last 90 days (`evidence.py` reports it).

| Ratio | Grade band | Reading |
|---|---|---|
| ≥ 0.30 | 8–10 | healthy pruning pressure |
| 0.15–0.30 | 5–7 | grows faster than it prunes, but alive |
| < 0.15 | 0–4 | grows-only — the cardinal sin (Musk: "didn't delete enough") |

## What the hat de-prioritizes (say so in the output)

Test coverage %, style conformance, doc volume, design-pattern orthodoxy, future-proofing. Not worthless — *downstream*. You don't polish a part you're about to delete.

## The mandatory caveat (Hard rule 6)

End every report with a version of:

> This is a synthesis of Musk's stated engineering algorithm (Starbase/Tesla) mapped onto software — a deliberately provocative lens, not a balanced rubric. It under-weights correctness, security, and long-horizon maintainability by design. Pair it *with* a conventional review (`/code-review`), don't let it replace one.

## When NOT to reach for this skill

| Situation | Use instead |
|---|---|
| "Find the bug" / correctness only | `/code-review` |
| "Clean up this diff's style" | `/simplify` |
| Score an agent harness | `agentharness-audit` |
| Project quality + CLAUDE.md freshness | `/audit` |
| Greenfield — nothing exists yet to delete | just build; the hat needs mass to cut |

## Calibration notes

- **Praise is rare but real.** Strong cycle time (criterion 4) is exactly what makes aggressive deletion *safe* — call it out, because it de-risks the cuts.
- **One legitimate axis is not duplication.** Per-SDK / per-runtime splits are kept; only non-product-axis splits (duplicate apps, dead lanes) are cuts. (Hard rule 5.)
