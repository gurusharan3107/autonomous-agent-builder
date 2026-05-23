#!/usr/bin/env python3
"""Regenerate docs/autoresearch/iterations.html + iterations.json from live TSVs.

Run this as part of every iteration closeout — after `compare.py` writes the
verdict to `optimize_results.tsv`, this script aggregates all rows into a
per-iteration summary the static HTML page consumes.

Outputs:
- docs/autoresearch/iterations.json     — production data (HTML fetches it)
- docs/autoresearch/iterations.html     — embedded fallback block rewritten

The HTML's render code, CSS, and example data are preserved across runs.
Only the block between `__ITERATIONS_DATA_START__` and
`__ITERATIONS_DATA_END__` is replaced.

Usage:
  python3 .claude/skills/autoresearch/scripts/render_iterations.py
  python3 .claude/skills/autoresearch/scripts/render_iterations.py --json-only
  python3 .claude/skills/autoresearch/scripts/render_iterations.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[4]
DOCS = REPO / "docs" / "autoresearch"
OPTIMIZE_TSV = DOCS / "optimize_results.tsv"
BASELINE_TSV = DOCS / "baseline_runs.tsv"
BASELINE_SUMMARY = DOCS / "baseline_runs_summary.json"
OUT_JSON = DOCS / "iterations.json"
OUT_HTML = DOCS / "iterations.html"

PROMO_ORDER = ["A", "B", "C", "D", "E"]
GATE_ORDER = [
    "cache_ratio_gt_5x_after_turn_2",
    "chunk_pressure_risk_false",
    "avoidable_cost_flags_empty",
    "gate_pass_rate_full",
    "feature_correct",
    "fully_shipped",
]
BRANCH_RE = re.compile(r"branch=(\S+)")
ITER_BRANCH_RE = re.compile(r"^autoresearch/iter-(\d+)-(.+)$")


def read_tsv_rows(path: pathlib.Path) -> list[dict]:
    if not path.exists() or path.stat().st_size <= 1:
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def parse_baseline() -> dict:
    if not BASELINE_SUMMARY.exists():
        bl = {
            "measured_at": None,
            "mean_composite": None,
            "stdev_composite": None,
            "noise_floor_2sigma": None,
            "fixtures_stable": 0,
            "fixtures_total": len(PROMO_ORDER),
        }
    else:
        try:
            data = json.loads(BASELINE_SUMMARY.read_text())
        except (OSError, json.JSONDecodeError):
            bl = parse_baseline_empty()
            data = {}
        else:
            # Aggregate fixture A's stats as the headline (the cheap-proxy fixture
            # used for keep/discard decisions); record stable-count across all fixtures.
            a = data.get("A") or {}
            stable = sum(1 for v in data.values() if isinstance(v, dict) and v.get("status") == "stable")
            bl = {
                "measured_at": dt.date.today().isoformat() if data else None,
                "mean_composite": a.get("mean"),
                "stdev_composite": a.get("stdev"),
                "noise_floor_2sigma": a.get("noise_floor_2sigma"),
                "fixtures_stable": stable,
                "fixtures_total": len(PROMO_ORDER),
            }

    # Per-fixture detail (A–E) — pulled from summary; "not_measured" when absent.
    summary = {}
    try:
        if BASELINE_SUMMARY.exists():
            summary = json.loads(BASELINE_SUMMARY.read_text())
    except (OSError, json.JSONDecodeError):
        summary = {}
    fixtures = []
    for fid in PROMO_ORDER:
        s = summary.get(fid) or {}
        if not s:
            fixtures.append({"id": fid, "status": "not_measured",
                             "stable_runs": 0, "total_runs": 0,
                             "mean": None, "stdev": None,
                             "noise_floor_2sigma": None, "cv_pct": None})
            continue
        mean = s.get("mean")
        stdev = s.get("stdev")
        cv_pct = (stdev / mean * 100.0) if (mean and stdev is not None) else None
        fixtures.append({
            "id": fid,
            "status": s.get("status") or "unstable",
            "stable_runs": s.get("stable_runs", 0),
            "total_runs": s.get("total_runs", 0),
            "mean": mean,
            "stdev": stdev,
            "noise_floor_2sigma": s.get("noise_floor_2sigma"),
            "cv_pct": round(cv_pct, 1) if cv_pct is not None else None,
        })
    bl["fixtures"] = fixtures

    # Per-run detail — read baseline_runs.tsv directly so the page is useful at
    # baseline-only state (before any Iterate-lane row has landed).
    bl["runs"] = parse_baseline_runs()
    return bl


def parse_baseline_runs() -> list[dict]:
    rows = read_tsv_rows(BASELINE_TSV)
    out = []
    for r in rows:
        notes = r.get("notes") or ""
        m = re.search(r"status=(\w+)", notes)
        status = m.group(1) if m else ""
        out.append({
            "run_id": r.get("run_id"),
            "fixture": r.get("fixture_id"),
            "timestamp": r.get("timestamp"),
            "gates_passed": r.get("gates_passed"),
            "feature_correct": parse_bool(r.get("feature_correct")),
            "status": status,
            "wallclock_s": parse_int(r.get("wallclock_s")),
            "operator_turns": parse_int(r.get("operator_turns")),
            "composite": parse_int(r.get("composite")),
            "noncached_plus_output_tokens": parse_int(r.get("noncached_plus_output_tokens")),
            "cache_ratio": float(r.get("cache_ratio") or 0) or None,
            "chunk_pressure_risk": parse_bool(r.get("chunk_pressure_risk")),
        })
    return out


def parse_baseline_empty() -> dict:
    return {
        "measured_at": None,
        "mean_composite": None,
        "stdev_composite": None,
        "noise_floor_2sigma": None,
        "fixtures_stable": 0,
        "fixtures_total": len(PROMO_ORDER),
    }


def parse_int(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def parse_bool(s: str | None) -> bool:
    return str(s or "").strip().lower() in {"true", "1", "yes", "pass"}


def extract_branch(notes: str | None) -> str | None:
    if not notes:
        return None
    m = BRANCH_RE.search(notes)
    return m.group(1) if m else None


def parse_gates_field(row: dict) -> list[bool]:
    # `gates_passed` is shaped like "5/6". We don't get per-gate detail in the
    # TSV today (run.py records the aggregate). Best-effort: derive from the
    # individual columns the TSV does carry.
    return [
        # cache_ratio gate is approximated from cache_ratio column (>5)
        (lambda v: bool(v) and v > 5.0)(float(row.get("cache_ratio") or 0)),
        # chunk_pressure_risk inverted (false = pass)
        not parse_bool(row.get("chunk_pressure_risk")),
        # avoidable_cost_flags must be empty list
        (row.get("avoidable_cost_flags") or "[]").strip() in ("[]", ""),
        # gate_pass_rate raw — already encoded as "5/6" style; derive from gates_passed
        gates_passed_count(row) >= 6 or parse_bool(row.get("feature_correct")),
        parse_bool(row.get("feature_correct")),
        "shipped" in (row.get("notes") or "").lower(),
    ]


def gates_passed_count(row: dict) -> int:
    gp = row.get("gates_passed") or row.get("gates_passed", "")
    m = re.match(r"^(\d+)/\d+", str(gp))
    return int(m.group(1)) if m else 0


def derive_iteration_index(branch: str) -> tuple[int | None, str | None]:
    m = ITER_BRANCH_RE.match(branch or "")
    if not m:
        return None, None
    return int(m.group(1)), m.group(2)


def git_diff_lines(branch: str, base: str = "main") -> int | None:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--shortstat", f"{base}...{branch}"],
            cwd=str(REPO), stderr=subprocess.DEVNULL, timeout=10,
        ).decode()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    # "3 files changed, 23 insertions(+), 5 deletions(-)"
    m = re.search(r"(\d+) insertions?", out)
    n = re.search(r"(\d+) deletions?", out)
    if m or n:
        return int(m.group(1) if m else 0) + int(n.group(1) if n else 0)
    return None


def group_rows_by_iteration(rows: list[dict]) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for r in rows:
        branch = extract_branch(r.get("notes"))
        idx, _ = derive_iteration_index(branch or "")
        if idx is None:
            continue
        grouped.setdefault(idx, []).append(r)
    return grouped


def iteration_summary(idx: int, rows: list[dict], baseline: dict) -> dict:
    # Fixture A is the gating row for keep/discard. If absent (rare), fall back
    # to the first row by timestamp.
    rows = sorted(rows, key=lambda r: r.get("timestamp") or "")
    primary = next((r for r in rows if r.get("fixture_id") == "A"), rows[0])

    branch = extract_branch(primary.get("notes")) or ""
    _, ref = derive_iteration_index(branch)
    verdict = (primary.get("decision") or infer_verdict(primary)).strip() or "discard"
    reason = primary.get("notes") or "no_reason_recorded"

    composite = parse_int(primary.get("composite"))
    delta_pct, delta_sigma = compute_deltas(composite, baseline)

    promotion = {f: "skipped" for f in PROMO_ORDER}
    for r in rows:
        f = r.get("fixture_id")
        if f in promotion:
            decision = (r.get("decision") or "").strip()
            if decision == "keep":
                promotion[f] = "kept"
            elif decision == "discard":
                promotion[f] = "discarded"
            else:
                # Run completed but no compare verdict yet — treat as kept if
                # the gates pass and shipped, else discarded.
                promotion[f] = "kept" if gates_passed_count(r) >= 6 else "discarded"

    return {
        "index": idx,
        "ref": ref or "(unnamed)",
        "date": (primary.get("timestamp") or "")[:10],
        "branch": branch,
        "verdict": verdict,
        "reason": reason if "branch=" not in reason else reason.split("status=")[-1] if "status=" in reason else reason,
        "composite": composite,
        "delta_pct": delta_pct,
        "delta_sigma": delta_sigma,
        "gates": parse_gates_field(primary),
        "promotion": promotion,
        "diff_lines": git_diff_lines(branch) if branch else None,
    }


def infer_verdict(row: dict) -> str:
    # When compare.py hasn't run yet, infer from the available signals.
    if "crash" in (row.get("notes") or "").lower():
        return "crash"
    if gates_passed_count(row) < 6:
        return "discard"
    return "pending"


def compute_deltas(composite: int | None, baseline: dict) -> tuple[float | None, float | None]:
    mean = baseline.get("mean_composite")
    stdev = baseline.get("stdev_composite")
    if composite is None or mean is None or mean == 0:
        return None, None
    delta_pct = (composite - mean) / mean * 100.0
    delta_sigma = (composite - mean) / stdev if stdev else None
    return round(delta_pct, 2), round(delta_sigma, 2) if delta_sigma is not None else None


def build_iterations_payload() -> dict:
    baseline = parse_baseline()
    rows = read_tsv_rows(OPTIMIZE_TSV)
    grouped = group_rows_by_iteration(rows)
    iterations = [
        iteration_summary(idx, grouped[idx], baseline)
        for idx in sorted(grouped.keys())
    ]
    return {
        "generated_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "baseline": baseline,
        "iterations": iterations,
    }


# ─── HTML data-block rewrite ──────────────────────────────────────────────────

DATA_START = "// __ITERATIONS_DATA_START__"
DATA_END = "// __ITERATIONS_DATA_END__"


def rewrite_html(payload: dict, dry_run: bool) -> bool:
    if not OUT_HTML.exists():
        print(f"WARN: {OUT_HTML} missing — cannot rewrite embedded data block", file=sys.stderr)
        return False
    text = OUT_HTML.read_text()
    if DATA_START not in text or DATA_END not in text:
        print(f"WARN: data markers not found in {OUT_HTML}", file=sys.stderr)
        return False

    js_literal = "window.ITERATIONS = " + json.dumps(payload, indent=2) + ";"
    new_block = f"{DATA_START}\n{js_literal}\n{DATA_END}"
    pattern = re.compile(re.escape(DATA_START) + r".*?" + re.escape(DATA_END), re.DOTALL)
    new_text, n = pattern.subn(new_block, text, count=1)
    if n != 1:
        print(f"WARN: pattern replacement failed in {OUT_HTML}", file=sys.stderr)
        return False
    if dry_run:
        print(f"[dry-run] would update {OUT_HTML} ({len(text)} → {len(new_text)} bytes)")
        return True
    OUT_HTML.write_text(new_text)
    return True


def main() -> int:
    args = parse_args()
    payload = build_iterations_payload()

    print(f"Generated payload:")
    print(f"  baseline: mean={payload['baseline']['mean_composite']} "
          f"stdev={payload['baseline']['stdev_composite']} "
          f"stable={payload['baseline']['fixtures_stable']}/{payload['baseline']['fixtures_total']}")
    print(f"  iterations: {len(payload['iterations'])} total")
    for it in payload["iterations"]:
        print(f"    #{it['index']} {it['ref']:<40} → {it['verdict']:<8} "
              f"composite={it['composite']} Δ={it['delta_pct']}% ({it['delta_sigma']}σ)")

    if args.dry_run:
        print(f"\n[dry-run] would write {OUT_JSON} ({len(json.dumps(payload))} bytes)")
        rewrite_html(payload, dry_run=True)
        return 0

    OUT_JSON.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {OUT_JSON}")

    if not args.json_only:
        ok = rewrite_html(payload, dry_run=False)
        if ok:
            print(f"Updated embedded data block in {OUT_HTML}")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Regenerate autoresearch iteration map.")
    p.add_argument("--json-only", action="store_true",
                   help="Write iterations.json only; skip the embedded HTML block rewrite")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would change without writing files")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())
