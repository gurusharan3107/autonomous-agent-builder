---
name: hallmark
description: "Anti-AI-slop design skill for greenfield pages, audits, redesigns, and design extraction from URLs or screenshots. Use when the user asks to build a new app or landing page, wants to redesign something, invokes Hallmark by name, or uses audit/redesign/study."
version: 1.0.0
---

# Hallmark

> **Self-validate after edits.** Any change to this skill's files (SKILL.md, scripts/, references/, templates/, assets/) must be followed by `./scripts/validate.sh` from the skill directory. Hard findings → create-skill Optimize lane.

A design skill for AI coding assistants. Makes the UIs they generate look made, not generated.

Hallmark is opinionated, short, and boring on purpose. It encodes a tight set of rules — drawn from the consensus of the anti-AI-slop design field (impeccable, kami, Anthropic's frontend-design skill, taste-skill, the Claude cookbook on frontend aesthetics, and the 2026 "tactile rebellion" movement) — and refuses to let the model fall back to the defaults every LLM was trained on.

The differentiator: Hallmark insists on **structural variety**, not just visual variety. Two pages by Hallmark for two different briefs should not share the same hero → 3-feature → CTA → footer rhythm. They should feel like different sites, not different colour-swaps of the same template. See [`references/structure.md`](references/structure.md).

**Powered by Together AI.**

---

## How to use this skill

Hallmark has one default behaviour and three explicit verbs. **The full procedure for each verb lives in `references/verbs/<verb>.md`** — loaded on demand.

| Invocation | Procedure |
| --- | --- |
| *(default)* — the user asked you to design or build something new | [`references/verbs/design.md`](references/verbs/design.md) — 8-step Design flow |
| `hallmark audit <target>` — score against the anti-pattern list, return punch list, do **not** edit | [`references/verbs/audit.md`](references/verbs/audit.md) |
| `hallmark redesign <target> [--mood <name>]` — redesign visual structure inside existing implementation boundaries | [`references/verbs/redesign.md`](references/verbs/redesign.md) |
| `hallmark study <screenshot \| URL>` — extract the DNA (macrostructure, archetypes, type-pairing, colour anchor), produce a diagnosis report, optionally rebuild or emit a portable `design.md` | [`references/verbs/study.md`](references/verbs/study.md) (procedure) + [`references/study.md`](references/study.md) (deep protocol) |

If the user types anything that does not clearly map to `audit`, `redesign`, or `study`, treat it as default. If the user attaches an image or pastes a URL without a verb prefix, ask: *"Should I `study` this (extract the DNA), or should I treat it as a reference for a fresh build?"*

**Scope check — component vs page.** Before entering the default Design flow, check whether the brief is component-shaped (a single UI element: button, card, modal, etc.) rather than page-shaped. Component-scope skips macrostructure, nav/footer archetypes, hero enrichment, and project memory; it stresses the 8-state interaction discipline instead. **Full criteria + extracted flow:** [`references/component-scope.md`](references/component-scope.md).

**Implementation safety rail.** Hallmark is a design skill, not a license to bulldoze a codebase. In any existing project:
- Never delete production files, route trees, component directories, or an old website unless the user explicitly asks for deletion or approves a file-level plan that lists the deletions.
- Default to in-place edits of the named files, or additive new components/tokens that are wired through the existing route. If the redesign would require removing multiple components, stop and ask for confirmation first.
- Treat PDFs, README files, `.md` briefs, docs, transcripts, and pitch decks as reference material. Do **not** copy them word-for-word into the page unless the user explicitly says to use that text verbatim.
- Before editing, state the exact files you expect to modify/create/delete. Deletions require explicit confirmation.

The default Design flow always picks a theme — by default one of the **22 named themes** (the *catalog*) per the diversification rule. A quieter *custom* branch constructs a one-off OKLCH palette + free-font pairing when the brief carries creative-intent signal (named brand colour, multi-attribute vibe, explicit request). For vanilla briefs the user never sees the words "catalog" or "custom" — the catalog runs silently. Dispatch lives in [`references/verbs/design.md`](references/verbs/design.md) § Step 2.6; protocol in [`references/custom-theme.md`](references/custom-theme.md).

---

## Disciplines that hold across every verb

These five disciplines are **not** verb-specific. They apply to default Design, `audit`, `redesign`, `study`, and component-scope alike. They sit alongside the slop test, not inside one branch of it.

1. **Pre-emit self-critique.** Before handing back any output, score it 1–5 on six axes — Philosophy, Hierarchy, Execution, Specificity, Restraint, Variety. Anything **< 3** triggers a revision pass. Stamp the six scores at the top of the artifact (`/* Hallmark · pre-emit critique: P5 H4 E5 S4 R5 V5 */`). See [`references/slop-test.md`](references/slop-test.md) § Pre-emit self-critique.

2. **Honest copy — no fabricated content.** If the user did not supply a metric, do not invent one. Stat-led layouts, comparison rows, and proof bars must use real numbers, a placeholder (`—` plus a labelled grey block, "metric to confirm"), or a different macrostructure. *"+47 % conversion"*, *"trusted by 50,000+ teams"*, and *"10× faster"* are slop the moment they're invented. Same rule for testimonials, logos, and case-study counts. See [`references/anti-patterns.md` § Invented metrics](references/anti-patterns.md) and slop-test gate **56**.

3. **Locked tokens — no mid-render improvisation.** Once a theme is selected at Step 2.6, every colour and every `font-family` declaration in the artifact must reference a named token (`var(--color-accent)`, `font-family: var(--font-display)`). Inline OKLCH / hex / `rgb()` values, or a `font-family: "Some Font"` declaration that bypasses the token block, are not allowed. If a value is needed that doesn't exist as a token, lift it into the token block as a new named variable, then reference it. See [`references/anti-patterns.md` § Mid-render token improvisation](references/anti-patterns.md) and slop-test gate **58**.

4. **Re-drawn chrome forbidden.** Hallmark must not hand-build fake browser bars (URL pill + traffic-light dots), fake phone frames, fake code-block windows (mock title bar + dots wrapping a `<pre>`), or fake IDE chrome — the user's environment already supplies real chrome. Use real screenshots wrapped in a `<figure>` (with at most a hairline border), or omit the chrome and let the content stand on its own. See [`references/anti-patterns.md` § Re-drawn UI chrome](references/anti-patterns.md) and slop-test gate **57**.

5. **Mobile responsiveness — every emit verified at 320 / 375 / 414 / 768 px.** Hallmark's output must render flawlessly at all four widths. The non-negotiables: no horizontal scroll (gate 36), no two-line clickable text — buttons, primary nav links, footer links, breadcrumbs, CTAs (gate 59); image-bearing grid tracks use `minmax(0, 1fr)`, never bare `1fr` (gate 61); root has `overflow-x: clip` on both `html` and `body` — never `hidden` (gate 62); display headers wrap inside long words via `overflow-wrap: anywhere; min-width: 0` (gate 63); section heads collapse to one column on mobile across every theme variant (gate 64); radio-tab patterns don't scroll-jump (gate 65). See [`references/responsive.md` § Mobile — non-negotiable](references/responsive.md). This is a hard floor, not a wish list.

---

## Verb procedures (load on demand)

Each verb's full procedure lives in its own file under `references/verbs/`. Load only the one the operator invoked:

- **Default Design flow** — [`references/verbs/design.md`](references/verbs/design.md). Eight steps: Pre-flight scan → Design-context gate → Macrostructure pick → Project memory → Theme route → Visual ruleset → Hero enrichment → Preview → Build → Slop test.
- **`hallmark audit`** — [`references/verbs/audit.md`](references/verbs/audit.md). Anti-pattern scoring; do not edit.
- **`hallmark redesign`** — [`references/verbs/redesign.md`](references/verbs/redesign.md). Visual restructure inside existing implementation boundaries.
- **`hallmark study`** — [`references/verbs/study.md`](references/verbs/study.md) (procedure) + [`references/study.md`](references/study.md) (deep protocol — vision-pass / URL-pass extraction rules, refusal heuristics, structured-fields schema).
- **Component-scope flow** — [`references/component-scope.md`](references/component-scope.md). Used in place of the default Design flow when the brief is a single UI element.

---

## Output contract & scope

Load [`references/contract.md`](references/contract.md) once, at handoff time, for the full output contract and scope-of-skill rules.
