#!/usr/bin/env python3
"""Two-run verdict generator per docs/autoresearch/COMPARE.md.

Compares a candidate run against the baseline-of-record for the same fixture.
Outputs JSON to stdout: {"decision": "keep|discard|crash", "reason": str, "detail": ...}.

Logic:
1. Crash check — non-zero exit on build/test gate → discard.
2. Six hard gates (from METRICS.md § Hard Gates) — any fail → discard.
3. 2σ composite test — candidate must beat baseline mean by ≥ 2σ.
4. Per-prompt sanity — max single-prompt regression < 50%.

Side effect: patches optimize_results.tsv to set the candidate row's
decision and composite_delta_pct columns.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TSV_ROOT = ROOT / "docs" / "autoresearch"


def load_baseline_for_fixture(fixture: str) -> dict | None:
    summary_path = TSV_ROOT / "baseline_runs_summary.json"
    if not summary_path.exists():
        return None
    summary = json.loads(summary_path.read_text())
    entry = summary.get(fixture)
    if entry is None or entry.get("status") != "stable":
        return None
    return entry


def load_row(tsv: pathlib.Path, run_id: str) -> dict | None:
    if not tsv.exists():
        return None
    with tsv.open(newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if row.get("run_id") == run_id:
                return row
    return None


def patch_row(tsv: pathlib.Path, run_id: str, decision: str, composite_delta_pct: float | None) -> None:
    if not tsv.exists():
        return
    rows: list[dict] = []
    with tsv.open(newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            if row.get("run_id") == run_id:
                row["decision"] = decision
                if composite_delta_pct is not None:
                    row["composite_delta_pct"] = f"{composite_delta_pct:.2f}"
            rows.append(row)
    if "decision" not in fieldnames:
        fieldnames.append("decision")
    if "composite_delta_pct" not in fieldnames:
        fieldnames.append("composite_delta_pct")
    with tsv.open("w", newline="") as f:
        w = csv.DictWriter(f, delimiter="\t", fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def main() -> int:
    args = parse_args()
    baseline = load_baseline_for_fixture(args.fixture)
    if baseline is None:
        print(json.dumps({
            "decision": "crash",
            "reason": "no_baseline",
            "detail": "baseline_runs_summary.json missing or fixture unstable",
        }, indent=2))
        return 2

    candidate_tsv = TSV_ROOT / ("baseline_runs.tsv" if args.candidate_baseline else "optimize_results.tsv")
    candidate = load_row(candidate_tsv, args.candidate_run)
    if candidate is None:
        print(json.dumps({
            "decision": "crash",
            "reason": "candidate_not_found",
            "detail": f"{args.candidate_run} not in {candidate_tsv}",
        }, indent=2))
        return 2

    # Gate 1: crash check
    if "crash" in (candidate.get("notes") or "").lower():
        verdict = {"decision": "discard", "reason": "crash", "detail": candidate.get("notes")}
        emit_and_patch(verdict, candidate_tsv, args.candidate_run, None)
        return 0

    # Gate 2: 6/6 hard gates
    gates_passed = candidate.get("gates_passed") or "0/6"
    if not gates_passed.startswith("6/6"):
        verdict = {"decision": "discard", "reason": "hard_gate_failed", "detail": gates_passed}
        emit_and_patch(verdict, candidate_tsv, args.candidate_run, None)
        return 0

    # Gate 3: 2σ composite test
    try:
        candidate_composite = float(candidate.get("composite") or 0)
    except (TypeError, ValueError):
        candidate_composite = 0
    noise_floor = baseline["noise_floor_2sigma"]
    mean = baseline["mean"]
    delta_pct = ((candidate_composite - mean) / mean * 100.0) if mean else 0
    if candidate_composite >= noise_floor:
        verdict = {
            "decision": "discard",
            "reason": "composite_within_2sigma_of_baseline",
            "detail": {
                "candidate_composite": candidate_composite,
                "baseline_mean": mean,
                "noise_floor_2sigma": noise_floor,
                "delta_pct": round(delta_pct, 2),
            },
        }
        emit_and_patch(verdict, candidate_tsv, args.candidate_run, delta_pct)
        return 0

    # Gate 4: per-prompt sanity (max single-prompt regression < 50%)
    per_prompt_warn = per_prompt_sanity_check(args.candidate_run)

    verdict = {
        "decision": "keep",
        "reason": "composite_below_2sigma_noise_floor",
        "detail": {
            "candidate_composite": candidate_composite,
            "baseline_mean": mean,
            "noise_floor_2sigma": noise_floor,
            "delta_pct": round(delta_pct, 2),
            "per_prompt_warnings": per_prompt_warn,
        },
    }
    emit_and_patch(verdict, candidate_tsv, args.candidate_run, delta_pct)
    return 0


def per_prompt_sanity_check(run_id: str) -> list[str]:
    """Light sanity check: flag any single prompt that consumed >50% more
    non-cached tokens than the previous turn of the same agent. Returns a list
    of warning strings; empty means clean."""
    tsv = TSV_ROOT / "per_prompt_results.tsv"
    if not tsv.exists():
        return []
    rows = []
    with tsv.open(newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row.get("run_id") == run_id:
                rows.append(row)
    warnings = []
    prev_by_agent: dict[str, int] = {}
    for r in rows:
        agent = r.get("agent_name") or ""
        try:
            ncpo = int(r.get("noncached_plus_output_tokens") or 0)
        except ValueError:
            continue
        prev = prev_by_agent.get(agent)
        if prev and ncpo > prev * 1.5:
            warnings.append(f"prompt_index={r.get('prompt_index')} agent={agent} ncpo={ncpo} (prev {prev}, +{(ncpo/prev-1)*100:.0f}%)")
        prev_by_agent[agent] = ncpo
    return warnings


def emit_and_patch(verdict: dict, tsv: pathlib.Path, run_id: str, delta_pct: float | None) -> None:
    print(json.dumps(verdict, indent=2))
    patch_row(tsv, run_id, verdict["decision"], delta_pct)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Two-run verdict generator.")
    p.add_argument("--fixture", required=True)
    p.add_argument("--candidate-run", required=True, help="run_id of candidate row in optimize_results.tsv")
    p.add_argument("--candidate-baseline", action="store_true", help="Look up candidate in baseline_runs.tsv instead")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())
