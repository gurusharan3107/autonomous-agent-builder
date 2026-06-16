#!/usr/bin/env python3
"""Self-introspection on the autoresearch loop — runs at iteration close-out.

Focused on **token economics**: how do we improve where we improve while
consuming fewer tokens? Reads accumulated iteration evidence and external
knowledge to surface lean improvements.

Sections in the generated report at docs/autoresearch/INTROSPECTION.md:

  1. Token economics       — tokens per iteration, breakdown by agent/phase, per-iteration cost
  2. Cumulative ROI        — total $ spent on the loop vs total composite savings achieved
  3. What worked           — kept iterations, compound effect
  4. What didn't           — discard reasons; cost of each discard
  5. What's redundant      — fixtures/gates/iteration steps that don't discriminate (= wasted tokens)
  6. What's noisy          — fixtures with σ > 25% of mean (low signal-to-noise = wasted tokens)
  7. KB-grounded leads     — articles from `workflow knowledge` tagged for token cost / caching /
                              context engineering, ranked by recency
  8. Lean recommendations  — ranked by expected (token reduction × applicability)

The report is overwritten each close-out. Historical introspection lives in
git — `git log docs/autoresearch/INTROSPECTION.md` shows how the
recommendations evolved.

Usage:
  python3 .claude/skills/autoresearch/scripts/introspect.py
  python3 .claude/skills/autoresearch/scripts/introspect.py --stdout-only
  python3 .claude/skills/autoresearch/scripts/introspect.py --quiet
  python3 .claude/skills/autoresearch/scripts/introspect.py --skip-kb   # don't query workflow knowledge
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
from collections import Counter, defaultdict
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[4]
DOCS = REPO / "docs" / "autoresearch"
ITERATIONS_JSON = DOCS / "iterations.json"
OPTIMIZE_TSV = DOCS / "optimize_results.tsv"
PROMPTS_TSV = DOCS / "per_prompt_results.tsv"
BASELINE_SUMMARY = DOCS / "baseline_runs_summary.json"
IDEAS_MD = DOCS / "OPTIMIZE_IDEAS.md"
REPORT_OUT = DOCS / "INTROSPECTION.md"
WORKFLOW_BIN = pathlib.Path.home() / ".claude" / "bin" / "workflow.py"

GATE_NAMES = ["cache", "chunk", "avoid", "rate", "build", "ship"]
FIXTURES = ["A", "B", "C", "D", "E"]

# KB queries we run on every close-out. Tags + keywords aimed at "make the
# loop leaner" rather than "find new optimizations to try". Pinning the queries
# keeps the report stable iteration to iteration so the operator can spot when
# a new article lands.
KB_QUERIES = [
    "prompt caching token cost",
    "context engineering token reduction",
    "agent skill bundle minimal context",
    "fixture redundancy benchmark variance",
]


def load_json(path: pathlib.Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def load_tsv(path: pathlib.Path) -> list[dict]:
    if not path.exists() or path.stat().st_size <= 1:
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


# ─── Findings ─────────────────────────────────────────────────────────────────


def analyze_verdict_distribution(iterations: list[dict]) -> dict:
    counts = Counter(i.get("verdict", "unknown") for i in iterations)
    total = len(iterations)
    return {
        "total": total,
        "kept": counts.get("keep", 0),
        "discarded": counts.get("discard", 0),
        "crashed": counts.get("crash", 0),
        "pending": counts.get("pending", 0),
        "keep_rate": counts.get("keep", 0) / total if total else 0,
    }


def analyze_compound_effect(iterations: list[dict], baseline: dict) -> dict:
    kept = [i for i in iterations if i.get("verdict") == "keep"]
    mean = baseline.get("mean_composite")
    if not kept or mean is None:
        return {"applicable": False}
    last = kept[-1]
    cumulative_pct = ((last.get("composite", 0) - mean) / mean * 100) if mean else 0
    per_iter_delta = [i.get("delta_pct") or 0 for i in kept]
    return {
        "applicable": True,
        "kept_count": len(kept),
        "cumulative_pct": round(cumulative_pct, 1),
        "best_single": min(per_iter_delta) if per_iter_delta else 0,
        "worst_kept": max(per_iter_delta) if per_iter_delta else 0,
        "diminishing_returns": _detect_diminishing_returns(per_iter_delta),
    }


def _detect_diminishing_returns(deltas: list) -> bool:
    """True if the last 3 kept iterations averaged less than half the first 3."""
    if len(deltas) < 6:
        return False
    early = sum(abs(d) for d in deltas[:3]) / 3
    late = sum(abs(d) for d in deltas[-3:]) / 3
    return late < early * 0.5


def analyze_discard_reasons(iterations: list[dict]) -> Counter:
    discarded = [i for i in iterations if i.get("verdict") == "discard"]
    reasons = Counter()
    for i in discarded:
        reason = i.get("reason") or "no_reason_recorded"
        # Collapse compound reasons to first phrase before colon/comma
        canonical = re.split(r"[:,;]", reason, maxsplit=1)[0].strip()
        reasons[canonical] += 1
    return reasons


def _per_gate_bools(iteration: dict) -> list[bool] | None:
    """Extract the 6 per-gate booleans from an iteration record, or None when
    the record only carries the aggregate ``gates_passed`` string.

    The runner persists per-gate booleans as ``gates_json`` (a JSON object
    keyed by the full gate name) on each ``optimize_results.tsv`` row. Older
    rows predate that column and only have ``gates``/``gates_passed`` as a
    ``"N/6"`` string — there is no way to recover per-gate signal from that, so
    return None and let the caller mark utility unmeasurable."""
    raw = iteration.get("gates_json")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = None
    if isinstance(raw, dict) and raw:
        return [bool(v) for v in raw.values()]
    if isinstance(raw, list) and len(raw) == len(GATE_NAMES):
        return [bool(v) for v in raw]
    gates = iteration.get("gates")
    if isinstance(gates, list) and len(gates) == len(GATE_NAMES):
        return [bool(v) for v in gates]
    return None  # only the "N/6" aggregate is available


def analyze_gate_utility(iterations: list[dict]) -> dict:
    """Which hard gates actually discriminate? A gate that always passes (or
    always fails) isn't gating anything; it's noise in the verdict logic.

    Per-gate discrimination is only computable when per-gate booleans are
    persisted (``gates_json``). When every iteration carries only the ``N/6``
    aggregate, utility is *unmeasurable* — we must say so rather than report a
    spurious ``discriminating: false`` (which an n<measurable run would emit for
    every gate purely from absence of data)."""
    per_gate = [b for b in (_per_gate_bools(i) for i in iterations) if b is not None]
    measurable = len(per_gate) > 0
    out: dict[str, Any] = {"_measurable": measurable, "_measured_n": len(per_gate)}
    for idx, name in enumerate(GATE_NAMES):
        if measurable:
            pass_count = sum(1 for bools in per_gate if bools[idx])
            fail_count = len(per_gate) - pass_count
            discriminating = fail_count > 0 and pass_count > 0
        else:
            pass_count = fail_count = 0
            discriminating = None  # unknown, not False
        out[name] = {
            "pass": pass_count,
            "fail": fail_count,
            "discriminating": discriminating,
        }
    return out


def analyze_fixture_agreement(iterations: list[dict]) -> dict:
    """Across kept iterations, do fixtures A→E ever disagree? If A and E
    always reach the same verdict, intermediate fixtures may be redundant."""
    # We only have promotion outcome ("kept"/"discarded"/"skipped") not raw composite per fixture in iterations.json.
    pair_agreement = defaultdict(lambda: {"agree": 0, "disagree": 0})
    for i in iterations:
        promo = i.get("promotion") or {}
        for a in FIXTURES:
            for b in FIXTURES:
                if a >= b:
                    continue
                pa, pb = promo.get(a), promo.get(b)
                if not pa or pa == "skipped" or not pb or pb == "skipped":
                    continue
                if pa == pb:
                    pair_agreement[(a, b)]["agree"] += 1
                else:
                    pair_agreement[(a, b)]["disagree"] += 1
    return {
        "pairs": dict(pair_agreement),
        "redundant_pairs": [
            (a, b) for (a, b), stats in pair_agreement.items()
            if stats["disagree"] == 0 and stats["agree"] >= 3
        ],
    }


def analyze_baseline_noise(baseline: dict) -> dict:
    """σ / mean per fixture — fixtures above 25% are too noisy to gate on."""
    full = load_json(BASELINE_SUMMARY, {})
    noisy: list[tuple[str, float]] = []
    if isinstance(full, dict):
        for fixture, entry in full.items():
            if not isinstance(entry, dict) or entry.get("status") != "stable":
                continue
            mean = entry.get("mean") or 0
            stdev = entry.get("stdev") or 0
            if mean == 0:
                continue
            ratio = stdev / mean
            if ratio > 0.25:
                noisy.append((fixture, round(ratio * 100, 1)))
    return {"noisy_fixtures": noisy, "stable_count": baseline.get("fixtures_stable", 0)}


def analyze_token_economics(optimize_rows: list[dict], per_prompt: list[dict]) -> dict:
    """Where did tokens go? Aggregate by agent/phase across all iterations.

    Surfaces the highest-token-cost agents so we can target lean improvements
    at the most expensive lanes — improving cache for `chat` (cheap) is less
    valuable than improving cache for `code-gen` (expensive)."""
    by_agent: dict[str, dict[str, float]] = defaultdict(
        lambda: {"runs": 0, "noncached_plus_output": 0, "cached": 0, "output": 0, "cost_usd": 0.0}
    )
    by_phase: dict[str, dict[str, float]] = defaultdict(
        lambda: {"runs": 0, "noncached_plus_output": 0}
    )

    for row in per_prompt:
        agent = (row.get("agent_name") or "").strip() or "unknown"
        phase = (row.get("phase") or "").strip() or "unknown"
        try:
            ncpo = int(row.get("noncached_plus_output_tokens") or 0)
            cached = int(row.get("tokens_cached") or 0)
            output = int(row.get("tokens_output") or 0)
            cost = float(row.get("cost_usd") or 0)
        except (TypeError, ValueError):
            continue
        by_agent[agent]["runs"] += 1
        by_agent[agent]["noncached_plus_output"] += ncpo
        by_agent[agent]["cached"] += cached
        by_agent[agent]["output"] += output
        by_agent[agent]["cost_usd"] += cost
        by_phase[phase]["runs"] += 1
        by_phase[phase]["noncached_plus_output"] += ncpo

    # Iteration-level aggregate from optimize_results.tsv. The TSV column
    # layout has drifted in some setups (run.py vs docs/autoresearch template
    # disagreement), so be tolerant of non-numeric cells — log a warning, don't
    # crash. The introspection report flags the schema drift separately.
    total_iterations = len(optimize_rows)
    total_ncpo = 0
    schema_drift_rows = 0
    for r in optimize_rows:
        raw = r.get("noncached_plus_output_tokens")
        try:
            total_ncpo += int(float(raw)) if raw not in (None, "") else 0
        except (TypeError, ValueError):
            schema_drift_rows += 1
    avg_per_iter = total_ncpo // total_iterations if total_iterations else 0

    # Ranked by descending non-cached + output (i.e., the costly stuff)
    top_agents = sorted(
        ((a, v) for a, v in by_agent.items() if v["noncached_plus_output"] > 0),
        key=lambda p: p[1]["noncached_plus_output"], reverse=True,
    )[:5]
    return {
        "total_iterations": total_iterations,
        "total_noncached_plus_output": total_ncpo,
        "avg_per_iteration": avg_per_iter,
        "top_agents_by_cost": [{"agent": a, **v} for a, v in top_agents],
        "by_phase": dict(by_phase),
        "schema_drift_rows": schema_drift_rows,
    }


def analyze_loop_roi(optimize_rows: list[dict], iterations: list[dict],
                     baseline: dict) -> dict:
    """Cumulative cost paid to run the loop vs cumulative composite savings.

    "Was the loop net-positive?" answers a question the user genuinely cares
    about — every API token spent introspecting must be earned back.
    """
    # cost_usd isn't a direct column on the session row today. As an
    # approximation, sum cost_usd across per_prompt_results.tsv rows — that's
    # the closest we get without re-instrumenting run.py. TODO: surface
    # iteration-level cost on the session row in a future run.py edit.
    _ = optimize_rows  # reserved for future per-iteration cost summation
    total_cost = _sum_per_prompt_cost()
    kept = [i for i in iterations if i.get("verdict") == "keep"]
    mean = baseline.get("mean_composite") or 0
    savings_pct = 0.0
    if kept and mean:
        last = kept[-1]
        savings_pct = abs((last.get("composite", mean) - mean) / mean) * 100
    return {
        "total_loop_cost_usd": round(total_cost, 2),
        "kept_iterations": len(kept),
        "cumulative_savings_pct": round(savings_pct, 1),
        "break_even_remark": _break_even_remark(total_cost, savings_pct, kept),
    }


def _sum_per_prompt_cost() -> float:
    if not PROMPTS_TSV.exists():
        return 0.0
    total = 0.0
    try:
        with PROMPTS_TSV.open(newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                try:
                    total += float(row.get("cost_usd") or 0)
                except (TypeError, ValueError):
                    continue
    except OSError:
        return 0.0
    return total


def _break_even_remark(cost_usd: float, savings_pct: float, kept: list[dict]) -> str:
    if cost_usd == 0:
        return "no cost recorded yet"
    if not kept:
        return f"${cost_usd:.2f} spent, no kept iterations yet — loop is net-negative"
    if savings_pct == 0:
        return f"${cost_usd:.2f} spent, kept iterations recorded but composite unchanged"
    # Rough break-even: if a typical Builder dispatch costs $0.50, savings_pct of 20%
    # means each future feature saves $0.10. So break-even is cost / saved-per-feature.
    avg_dispatch = 0.50
    saved_per_feature = avg_dispatch * (savings_pct / 100)
    features_to_breakeven = int(cost_usd / saved_per_feature) if saved_per_feature else 0
    return (f"${cost_usd:.2f} spent, {savings_pct:.1f}% composite savings — "
            f"break-even after ~{features_to_breakeven} future feature ships")


def query_workflow_knowledge(queries: list[str], skip: bool) -> dict:
    """Surface KB articles relevant to making the loop leaner."""
    if skip:
        return {"skipped": True, "results": []}
    if not WORKFLOW_BIN.exists():
        return {"skipped": True, "error": f"workflow.py not found at {WORKFLOW_BIN}",
                "results": []}
    results: list[dict] = []
    env = dict(os.environ)
    env["CODEX_WORKFLOW_PUBLIC_ENTRYPOINT"] = "1"
    for q in queries:
        try:
            out = subprocess.check_output(
                ["python3", str(WORKFLOW_BIN), "knowledge", "search", q],
                env=env, stderr=subprocess.DEVNULL, timeout=10,
            ).decode()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            continue
        # Parse text output: lines starting with 2-space indent are slugs;
        # following 4-space lines are the snippet preview.
        articles: list[dict] = []
        current: dict | None = None
        for line in out.splitlines():
            if re.match(r"^  [^ ]", line):
                if current:
                    articles.append(current)
                current = {"slug": line.strip(), "preview": ""}
            elif re.match(r"^    ", line) and current:
                current["preview"] = line.strip()[:160]
        if current:
            articles.append(current)
        if articles:
            results.append({"query": q, "articles": articles[:3]})
    return {"skipped": False, "results": results}


def analyze_idea_velocity(ideas_md: pathlib.Path) -> dict:
    """How many ideas remain vs attempted? Velocity = ideas/week, time to exhaust."""
    if not ideas_md.exists():
        return {"applicable": False}
    text = ideas_md.read_text()
    # Current format: each idea is an H2 header `## N. Title`; attempts are
    # recorded as `- Attempted YYYY-MM-DD ...` lines under that idea's
    # `- **Attempts**:` block. Split on the H2 idea headers and count how many
    # idea blocks contain at least one attempt line (an idea with 3 attempt
    # rows is still one attempted idea, not three).
    idea_blocks = re.split(r"(?m)^##\s+\d+\.\s+", text)[1:]  # drop preamble
    attempted = sum(
        1 for block in idea_blocks
        if re.search(r"(?im)^\s*-\s*Attempted\b", block)
    )
    total = len(idea_blocks)
    return {
        "applicable": True,
        "total_ideas": total,
        "attempted": attempted,
        "remaining": max(total - attempted, 0),
    }


# ─── Recommendations ──────────────────────────────────────────────────────────


def build_recommendations(findings: dict) -> list[str]:
    recs: list[str] = []
    verdict = findings["verdict_distribution"]
    compound = findings["compound_effect"]
    gates = findings["gate_utility"]
    fixtures = findings["fixture_agreement"]
    noise = findings["baseline_noise"]
    velocity = findings["idea_velocity"]
    econ = findings.get("token_economics") or {}
    roi = findings.get("loop_roi") or {}

    # Schema drift detection — if cells in optimize_results.tsv can't be parsed
    # as numbers, run.py is writing columns out of order vs the TSV header.
    # This silently breaks every downstream gate. Surface it first.
    if econ.get("schema_drift_rows", 0) > 0:
        recs.append(
            f"**Schema drift detected:** {econ['schema_drift_rows']} row(s) in "
            "`optimize_results.tsv` have non-numeric values where numbers belong. "
            "Likely cause: `run.py`'s SESSION_HEADERS doesn't match the existing TSV "
            "header (extra columns: branch/idea_ref/files_touched/lines_added/"
            "lines_deleted). Until fixed, all downstream gates and "
            "introspection will silently truncate. Fix: align "
            "`SESSION_HEADERS` in `scripts/autoresearch/run.py` with the TSV header, "
            "or regenerate the TSV from the runner's schema."
        )

    # Lean recommendations — token-cost focused, ranked first because they
    # directly answer "how do we improve while consuming fewer tokens?"
    top_agents = econ.get("top_agents_by_cost") or []
    if top_agents:
        worst = top_agents[0]
        share = (worst["noncached_plus_output"] / econ["total_noncached_plus_output"] * 100
                 if econ.get("total_noncached_plus_output") else 0)
        if share > 40:
            recs.append(
                f"**Agent `{worst['agent']}` consumes {share:.0f}% of loop tokens.** "
                "Any lean idea targeting this agent's prompt has the highest leverage."
            )

    # Per-iteration cost trajectory: if average iteration cost is creeping up,
    # the loop is getting more expensive per attempt — bad sign.
    if econ.get("avg_per_iteration", 0) > 50_000:
        recs.append(
            f"**Average iteration is {econ['avg_per_iteration']:,} non-cached+output tokens.** "
            "At ~$3/Mtok blended, that's >$0.15 per iteration just on the LLM side. "
            "Targets to cut: per-turn re-reads of unchanged docs, repeated tool-call output "
            "re-injection."
        )

    # ROI signal — if total cost > 10x cumulative savings basis, the loop is bleeding
    if roi.get("total_loop_cost_usd", 0) > 0 and roi.get("kept_iterations", 0) == 0:
        recs.append(
            f"**Loop has spent ${roi['total_loop_cost_usd']:.2f} with zero kept iterations.** "
            "Either the 2σ bar is too tight (re-run baseline with N=10 to tighten σ) or "
            "ideas are systematically over-ambitious. Try smaller, more targeted ideas; the "
            "best ideas usually touch <50 lines."
        )

    if verdict["total"] == 0:
        recs.append(
            "**No iterations recorded yet.** Run Recipe 1 + Recipe 2 first; introspection "
            "becomes useful after ≥5 iterations."
        )
        return recs

    # Keep rate signal
    if verdict["total"] >= 5:
        if verdict["keep_rate"] < 0.20:
            recs.append(
                f"**Keep rate is {verdict['keep_rate']:.0%} ({verdict['kept']}/{verdict['total']}).** "
                "Either ideas in `OPTIMIZE_IDEAS.md` are too speculative, or the 2σ bar is "
                "tighter than the actual signal. Consider tightening fixture timing variance "
                "to lower σ before adding more speculative ideas."
            )
        elif verdict["keep_rate"] > 0.70:
            recs.append(
                f"**Keep rate is {verdict['keep_rate']:.0%}** — suspiciously high. Either ideas "
                "are obvious wins (good — keep going) or the 2σ gate is too loose. Re-run the "
                "baseline with N=10 to tighten σ and re-check the next iteration's verdict."
            )

    # Compound effect signal
    if compound.get("applicable"):
        if compound.get("diminishing_returns"):
            recs.append(
                f"**Diminishing returns detected** — recent 3 kept iterations averaged less than "
                f"half the impact of the first 3. Cumulative is {compound['cumulative_pct']}%. "
                "Time to refresh `OPTIMIZE_IDEAS.md` with new categories (e.g., move from "
                "prompt-shape to tool-design or runtime policy)."
            )
        elif compound["kept_count"] >= 3:
            recs.append(
                f"**Compound effect is healthy:** {compound['kept_count']} kept iterations, "
                f"cumulative composite −{abs(compound['cumulative_pct'])}% vs original baseline. "
                "Keep going with current idea categories."
            )

    # Gate utility signal — gates that never fire are dead code. Only assessable
    # when per-gate booleans are persisted (gates.get("_measurable")) AND there
    # are enough iterations to trust the signal; below that we say nothing rather
    # than flag every gate from absence of data.
    gate_stats = {n: s for n, s in gates.items() if not n.startswith("_")}
    non_discriminating = [
        name for name, stats in gate_stats.items() if stats["discriminating"] is False
    ]
    if gates.get("_measurable") and non_discriminating and verdict["total"] >= 10:
        all_pass = [g for g in non_discriminating if gate_stats[g]["fail"] == 0]
        if all_pass:
            recs.append(
                f"**Hard gates `{', '.join(all_pass)}` never failed across {verdict['total']} "
                "iterations.** They aren't gating anything. Either tighten them (raise the "
                "threshold) or remove them from `compare.py` — every gate evaluated is wallclock "
                "cost on every iteration."
            )

    # Fixture redundancy signal
    redundant = fixtures.get("redundant_pairs") or []
    if redundant:
        worst = redundant[0]
        recs.append(
            f"**Fixtures {worst[0]} and {worst[1]} always agree** across iterations where both "
            f"ran. If this holds for 5+ more iterations, consider dropping one — currently they "
            "double the wallclock + API cost of every promotion without adding discriminative "
            "signal."
        )

    # Noisy baseline signal
    noisy = noise.get("noisy_fixtures") or []
    if noisy:
        worst_fix, worst_pct = max(noisy, key=lambda p: p[1])
        recs.append(
            f"**Fixture {worst_fix} σ is {worst_pct}% of mean** (threshold: 25%). It's too "
            "timing-fragile to gate verdicts on. Either raise its `timeout_s` in `run.py` "
            "FIXTURES dict (catches slow-but-correct runs that currently look like noise), or "
            "drop it from the baseline set."
        )

    # Idea velocity signal
    if velocity.get("applicable"):
        remaining = velocity["remaining"]
        if remaining < 3:
            recs.append(
                f"**Only {remaining} unattempted ideas remaining in `OPTIMIZE_IDEAS.md`.** "
                "Add new candidates to `OPTIMIZE_IDEAS.md` before the loop stalls."
            )

    return recs


# ─── Report rendering ─────────────────────────────────────────────────────────


def render_report(findings: dict, recommendations: list[str]) -> str:
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    verdict = findings["verdict_distribution"]
    compound = findings["compound_effect"]
    gates = findings["gate_utility"]
    fixtures = findings["fixture_agreement"]
    noise = findings["baseline_noise"]
    velocity = findings["idea_velocity"]

    econ = findings["token_economics"]
    roi = findings["loop_roi"]
    kb = findings["kb_leads"]

    lines = [
        "# Autoresearch loop introspection",
        "",
        f"*Generated {now} by `.claude/skills/autoresearch/scripts/introspect.py`. "
        "Overwritten each close-out — `git log` for history.*",
        "",
        "## 1. Token economics — where do tokens go?",
        "",
    ]
    if econ["total_iterations"] == 0:
        lines += ["- No per-prompt rows yet (zero iterations). Section becomes "
                  "meaningful once `optimize_results.tsv` has rows.", ""]
    else:
        lines += [
            f"- **{econ['total_iterations']} iterations recorded** consuming "
            f"~{econ['total_noncached_plus_output']:,} non-cached+output tokens total.",
            f"- **Average per iteration:** {econ['avg_per_iteration']:,} non-cached+output tokens.",
            "",
            "Top agents by cumulative cost (the ones to target with lean ideas first):",
            "",
        ]
        if econ["top_agents_by_cost"]:
            lines.append("| Agent | Runs | Non-cached+output | Cached | Output | $ |")
            lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
            for a in econ["top_agents_by_cost"]:
                lines.append(
                    f"| `{a['agent']}` | {int(a['runs'])} | "
                    f"{int(a['noncached_plus_output']):,} | "
                    f"{int(a['cached']):,} | {int(a['output']):,} | "
                    f"${a['cost_usd']:.2f} |"
                )
        else:
            lines.append("(no per-prompt rows have non-zero token counts)")
        lines.append("")

    lines += [
        "## 2. Cumulative loop ROI",
        "",
        f"- **Spent:** ${roi['total_loop_cost_usd']} across all iterations (per-prompt cost sum).",
        f"- **Kept iterations:** {roi['kept_iterations']}.",
        f"- **Cumulative composite savings:** {roi['cumulative_savings_pct']}% vs original baseline.",
        f"- **Break-even:** {roi['break_even_remark']}.",
        "",
        "## 3. What worked",
        "",
    ]

    if not verdict["total"]:
        lines += [
            "No iterations recorded yet. This report becomes meaningful after the first iteration",
            "lands a row in `optimize_results.tsv`. Re-run `introspect.py` after iteration #1.",
            "",
        ]
    else:
        lines += [
            f"- **{verdict['kept']}/{verdict['total']} iterations kept** "
            f"({verdict['keep_rate']:.0%} keep rate).",
        ]
        if compound.get("applicable"):
            lines += [
                f"- **Cumulative composite vs original baseline: "
                f"{compound['cumulative_pct']:.1f}%** "
                f"({'improvement' if compound['cumulative_pct'] < 0 else 'regression'} "
                f"across {compound['kept_count']} kept iterations).",
                f"- **Best single iteration:** {compound['best_single']:.1f}% delta.",
            ]
        lines.append("")

    lines += ["## 4. What didn't", ""]
    reasons = analyze_discard_reasons_table(findings["discard_reasons"], verdict["discarded"])
    lines += reasons + [""]

    lines += ["## 5. What's redundant", ""]
    redundancy = []
    gate_stats = {n: s for n, s in gates.items() if not n.startswith("_")}
    GATE_MEASURE_MIN_N = 10  # noqa: N806
    if not gates.get("_measurable"):
        redundancy.append(
            "- **Gate discrimination not measurable** — per-gate booleans aren't "
            "persisted on `optimize_results.tsv` (only the `N/6` aggregate). The "
            "runner now writes a `gates_json` column; discrimination becomes "
            "assessable once iterations accumulate rows carrying it. *Do not prune "
            "gates until then — absence of data is not evidence a gate is dead.*"
        )
    elif verdict["total"] < GATE_MEASURE_MIN_N:
        redundancy.append(
            f"- **Too few iterations ({verdict['total']}/{GATE_MEASURE_MIN_N}) to "
            "assess gate discrimination.** Per-gate signal is recorded but not yet "
            "statistically meaningful."
        )
    else:
        non_disc = [n for n, s in gate_stats.items() if s["discriminating"] is False]
        if non_disc:
            redundancy.append(
                f"- **Hard gates {', '.join(f'`{n}`' for n in non_disc)} never discriminated** "
                f"across {verdict['total']} iterations (always pass or always fail). "
                "Worth tightening or removing."
            )
    redundant_pairs = fixtures.get("redundant_pairs") or []
    if redundant_pairs:
        redundancy.append(
            "- **Fixture pairs that always agree:** "
            + ", ".join(f"{a}↔{b}" for a, b in redundant_pairs)
            + ". Consider dropping the slower one from the promotion chain."
        )
    if not redundancy:
        redundancy.append("- Nothing detected yet — too few iterations to identify redundancy.")
    lines += redundancy + [""]

    lines += ["## 6. What's noisy", ""]
    noisy = noise.get("noisy_fixtures") or []
    if not noisy:
        lines.append("- All fixtures within 25% σ/mean threshold (good).")
    else:
        for f, pct in noisy:
            lines.append(f"- **Fixture {f}**: σ/mean = {pct}% (target: <25%). Timing-fragile.")
    lines.append("")

    if velocity.get("applicable"):
        lines += [
            "## 7. Idea backlog",
            "",
            f"- **{velocity['attempted']} attempted / {velocity['remaining']} remaining** "
            f"of {velocity['total_ideas']} total in `OPTIMIZE_IDEAS.md`.",
            "",
        ]

    lines += ["## 8. Lean recommendations", "",
              "*Ranked by `(expected token reduction × applicability)`. Each item is "
              "actionable today — no speculation.*", ""]
    if recommendations:
        for r in recommendations:
            lines.append(f"- {r}")
    else:
        lines.append("- Not enough iteration evidence to recommend anything specific yet.")
    lines.append("")

    # KB-grounded leads section
    lines += ["## 9. KB leads (from `workflow knowledge`)", ""]
    if kb.get("skipped"):
        reason = kb.get("error") or "skipped via --skip-kb"
        lines += [f"*KB query skipped: {reason}*", ""]
    elif not kb.get("results"):
        lines += ["*No matching articles found. KB may be empty or queries returned nothing.*", ""]
    else:
        lines += [
            "Articles relevant to making the loop leaner. Read with: "
            "`workflow knowledge read <slug>`.",
            "",
        ]
        for entry in kb["results"]:
            lines.append(f"**Query:** `{entry['query']}`")
            lines.append("")
            for art in entry["articles"]:
                lines.append(f"- `{art['slug']}`")
                if art.get("preview"):
                    lines.append(f"    > {art['preview']}")
            lines.append("")

    lines += [
        "## Raw stats",
        "",
        "```json",
        json.dumps(
            {
                "verdict_distribution": verdict,
                "compound_effect": compound,
                "gate_utility": gates,
                "baseline_noise": noise,
                "idea_velocity": velocity,
            },
            indent=2,
        ),
        "```",
        "",
    ]
    return "\n".join(lines)


def analyze_discard_reasons_table(reasons: Counter, total_discarded: int) -> list[str]:
    if not reasons:
        return ["- No discarded iterations yet."]
    rows = [f"- **{total_discarded} discarded** iterations grouped by reason:"]
    for reason, count in reasons.most_common():
        rows.append(f"  - `{reason}`: {count}")
    return rows


def _iter_from_optimize_row(r: dict) -> dict:
    """Project an `optimize_results.tsv` row onto the iteration shape the
    verdict/gate/compound analyses expect. The TSV is the authoritative ledger
    (the runner appends one row per completed iteration); `iterations.json` is a
    derived render artifact that can lag it."""
    def _num(key: str) -> float:
        try:
            return float(r.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0
    return {
        "verdict": (r.get("decision") or "").strip().lower() or "unknown",
        "composite": int(_num("composite")),
        "delta_pct": _num("composite_delta_pct"),
        "gates_passed": r.get("gates_passed") or "",
        "gates_json": r.get("gates_json") or "",
        "ref": (r.get("idea_ref") or "").strip(),
        "reason": (r.get("notes") or "").strip(),
    }


def main() -> int:
    args = parse_args()
    iterations = load_json(ITERATIONS_JSON, {}).get("iterations") or []
    optimize_rows = load_tsv(OPTIMIZE_TSV)
    per_prompt = load_tsv(PROMPTS_TSV)
    baseline = load_json(ITERATIONS_JSON, {}).get("baseline") or {}

    # Single source of truth: when the rendered iterations.json is empty or has
    # fewer rows than the authoritative optimize_results.tsv ledger, derive the
    # iteration list from the TSV so verdict/gate/ROI counts can't contradict
    # the token-economics section (which already reads the TSV).
    if len(iterations) < len(optimize_rows):
        iterations = [_iter_from_optimize_row(r) for r in optimize_rows]

    findings = {
        "verdict_distribution": analyze_verdict_distribution(iterations),
        "compound_effect": analyze_compound_effect(iterations, baseline),
        "discard_reasons": analyze_discard_reasons(iterations),
        "gate_utility": analyze_gate_utility(iterations),
        "fixture_agreement": analyze_fixture_agreement(iterations),
        "baseline_noise": analyze_baseline_noise(baseline),
        "idea_velocity": analyze_idea_velocity(IDEAS_MD),
        "optimize_row_count": len(optimize_rows),
        "token_economics": analyze_token_economics(optimize_rows, per_prompt),
        "loop_roi": analyze_loop_roi(optimize_rows, iterations, baseline),
        "kb_leads": query_workflow_knowledge(KB_QUERIES, skip=args.skip_kb),
    }
    recommendations = build_recommendations(findings)
    report = render_report(findings, recommendations)

    if not args.quiet:
        # Always emit recommendations to stdout — that's the actionable signal
        print("autoresearch introspection:")
        if not recommendations:
            print("  (no recommendations — not enough iteration evidence)")
        else:
            for r in recommendations:
                # Strip markdown for stdout
                plain = re.sub(r"[*`]", "", r)
                print(f"  - {plain}")

    if args.stdout_only:
        print()
        print(report)
        return 0

    REPORT_OUT.write_text(report)
    if not args.quiet:
        print(f"\nReport written to: {REPORT_OUT}")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Autoresearch loop self-introspection.")
    p.add_argument("--stdout-only", action="store_true",
                   help="Emit report to stdout, don't overwrite INTROSPECTION.md")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress stdout summary; just write the report file")
    p.add_argument("--skip-kb", action="store_true",
                   help="Don't query `workflow knowledge` for KB-grounded leads")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())
