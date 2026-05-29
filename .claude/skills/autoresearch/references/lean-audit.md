# Lean audit — idiot index + retention boundary

> Loaded on demand from [SKILL.md](../SKILL.md) Hard Rule 17. The governing lens for what the loop is allowed to carry.

**Idiot index** = (cost of the built thing) ÷ (cost of the irreducible material). High = markup; drive toward 1.

**Raw material of one experiment** (index ≈ 1): run a fixture → read `noncached_plus_output_tokens` from `builder analyze` → compare to baseline ± noise. ~50 lines + the API cost of the run. Everything below is measured against that.

Current apparatus: **~13,000 lines** (+ a Docker dep, now cut) to extract one integer and subtract it. The cut is not finished.

## Per-item idiot index (highest markup first = cut first)

| Item | LOC | Index | Elon verdict | Action |
|---|---|---|---|---|
| ~~`diagnose_hang.py` + `KNOWN_PATTERNS.md` + `hang-detection.md`~~ ✅ **CUT 2026-05-29** | ~2100 deleted | **extreme** | "You built a 2,300-line autopsy kit because your runs hang. Why do they hang? Fix the hang. Delete the coroner." | **Done:** matcher library + catalog deleted; `baseline.py` classifier → inline `unknown` stub; stuck == abort + escalate (operator inspects the dump, fixes the hang at source). `hang_watchdog.py` kept as the WAL-idle detector. |
| `introspect.py` + `render_iterations.py` + `autoresearch-explainer.html` + `INTROSPECTION.md` | ~2800 | **extreme** | "A dashboard with one dot. Does any chart change a decision? Then it's markup. Build it after 20 wins, not before." | Keep a 1-line ROI print. Defer the HTML/introspection until ≥10 kept iterations exist to report. |
| `self_heal.py` + `seed_verify.py` + `test_harness_contracts.py` + `seed_manifest.json` | ~1335 | **high** | "You built a bureaucracy to survive a breakable seed. Make the seed unbreakable; the bureaucracy evaporates." | Immutable seed + DB-wipe on restore is the fix. Shrink the contract/self-heal layer to what that can't cover. |
| ~~`HARNESS.md`~~ ✅ **SHRUNK 2026-05-29** (619→~20) | 619 | **high** | "The code is the spec. A 619-line doc describing the program is a second program to keep in sync." | **Done:** stubbed to ~20 lines (pointer to `run.py` + the `session_scoped` invariant the freshness gate owns). Shrunk not deleted — 15 inbound refs + a freshness hard-check made deletion higher-index than the stub. |
| `preflight.py` | 714 | **high** | "700 lines to check the room is tidy. Half you just deleted. Keep the $0 substrate gate; question the rest." | Keep seed-pytest-collect + TSV-header + ports. Cut the rest. |
| `COMPARE.md` / `METRICS.md` / `fixtures.md` / `baseline_variance.md` | ~775 | **high** | "Markup. `compare.py` is the verdict; the `FIXTURES` dict is the fixtures. Don't document the code — read it." | Delete or fold; keep only the `session_scoped` contract note (freshness gate). |
| 6 hard gates | — | **med** | "Which ever fired? Delete the ones that never bind." | Per Hard Rule 17 + introspect: prune non-discriminating gates once n≥10. |
| 5 fixtures (A–E) | — | **med** | "Do A and E ever disagree? If not you have one fixture pretending to be five." | Measure fixture agreement; drop redundant ones. |
| σ-floor + N=5 baseline | — | **med** | "Is N=5 needed, or would N=2 catch the same wins?" | Justify N against observed CV; lower if signal allows. |
| `run.py` (940) + `baseline.py` (711) | ~1650 | **low-ish** | "This is the actual work — but 940 lines to drive one fixture and read one number? Halve it." | Keep; simplify. The irreducible core. |
| `compare.py` (190) + `loop.py` (231) | ~420 | **low** | "Close to raw material. Leave it." | Keep. |

## `docs/autoresearch/` retention boundary

The folder holds the loop's **contract, living state, and data** — never prose that re-narrates code.

**Stays** (read or written by the loop):
- `OPTIMIZE.md` — the loop contract (composite, gates, stop conditions). The agent's `program.md`.
- `OPTIMIZE_IDEAS.md` — the backlog the loop reads top-down.
- `PROGRESS.md` — the per-iteration log.
- Data: `*.tsv`, `baseline_runs_summary.json`, `iterations.json`.
- `README.md` — status/entry, trimmed.
- `INTROSPECTION.md` — generated artifact (regenerates; zero maintenance cost).

**Goes / shrinks** (markup that narrates code):
- `HARNESS.md` — `run.py` is the spec.
- `COMPARE.md` — `compare.py` is the verdict logic.
- `METRICS.md` — shrink to the `session_scoped` contract note only.
- `fixtures.md` — the `FIXTURES` dict in `run.py` is canonical.
- `baseline_variance.md` — fold the live σ into `baseline_runs_summary.json`.
- `autoresearch-explainer.html` — keep only if a panel changes a decision; otherwise markup.

**The rule:** if a doc describes *how a script works*, the script is the source of truth — delete the doc. A doc stays only if the loop reads it to run, writes it as state, or it's the human-owned contract/backlog.
