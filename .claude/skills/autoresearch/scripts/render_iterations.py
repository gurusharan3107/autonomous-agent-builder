#!/usr/bin/env python3
"""Inject the autoresearch data snapshot into docs/autoresearch/autoresearch-explainer.html.

Run this as part of every lane closeout. The explainer uses a
<script id="autoresearch-data" type="application/json"> block that JS renders
into the four live-data panels. This script replaces that block's content with
fresh data from TSV/JSON sources.

Also writes docs/autoresearch/iterations.json for downstream tooling that
prefers structured data.

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
import sys

REPO = pathlib.Path(__file__).resolve().parents[4]
DOCS = REPO / "docs" / "autoresearch"
OPTIMIZE_TSV = DOCS / "optimize_results.tsv"
BASELINE_TSV = DOCS / "baseline_runs.tsv"
BASELINE_SUMMARY = DOCS / "baseline_runs_summary.json"
OUT_JSON = DOCS / "iterations.json"
EXPLAINER = DOCS / "autoresearch-explainer.html"

PROMO_ORDER = ["A", "B", "C", "D", "E"]
BRANCH_RE = re.compile(r"branch=(\S+)")
ITER_BRANCH_RE = re.compile(r"^autoresearch/iter-(\d+)-(.+)$")

DATA_SCRIPT_RE = re.compile(
    r'(<script\s+id="autoresearch-data"[^>]*>)(.*?)(</script>)',
    re.DOTALL,
)


# ─── data ingestion ──────────────────────────────────────────────────────────


def read_tsv_rows(path: pathlib.Path) -> list[dict]:
    if not path.exists() or path.stat().st_size <= 1:
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def parse_int(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def parse_bool(s: str | None) -> bool:
    return str(s or "").strip().lower() in {"true", "1", "yes", "pass"}


def parse_baseline() -> dict:
    """Return baseline summary (mean/stdev/2σ for fixture A + per-fixture stable count)."""
    if not BASELINE_SUMMARY.exists():
        return _empty_baseline()
    try:
        data = json.loads(BASELINE_SUMMARY.read_text())
    except (OSError, json.JSONDecodeError):
        return _empty_baseline()

    a = data.get("A") or {}
    stable = sum(1 for v in data.values() if isinstance(v, dict) and v.get("status") == "stable")
    runs_a = [r for r in parse_baseline_runs() if r.get("fixture") == "A"]
    clean = sum(1 for r in runs_a if "shipped" in (r.get("status") or ""))
    return {
        "measured_at": dt.date.today().isoformat(),
        "mean": a.get("mean"),
        "stdev": a.get("stdev"),
        "noise_floor_2sigma": a.get("noise_floor_2sigma"),
        "stable_fixtures": stable,
        "total_fixtures": len(PROMO_ORDER),
        "fixture_a_runs_clean": clean,
        "fixture_a_runs_total": len(runs_a),
        "fixture_a_runs": runs_a,
    }


def _empty_baseline() -> dict:
    return {
        "measured_at": None,
        "mean": None,
        "stdev": None,
        "noise_floor_2sigma": None,
        "stable_fixtures": 0,
        "total_fixtures": len(PROMO_ORDER),
        "fixture_a_runs_clean": 0,
        "fixture_a_runs_total": 0,
        "fixture_a_runs": [],
    }


def parse_baseline_runs() -> list[dict]:
    rows = read_tsv_rows(BASELINE_TSV)
    out = []
    for r in rows:
        notes = r.get("notes") or ""
        m = re.search(r"status=(\w+)", notes)
        status = m.group(1) if m else ""
        out.append(
            {
                "run_id": r.get("run_id"),
                "fixture": r.get("fixture_id"),
                "timestamp": r.get("timestamp"),
                "gates_passed": r.get("gates_passed"),
                "status": status,
                "wallclock_s": parse_int(r.get("wallclock_s")),
                "noncached_plus_output_tokens": parse_int(r.get("noncached_plus_output_tokens")),
                "cache_ratio": float(r.get("cache_ratio") or 0) or None,
            }
        )
    return out


def parse_all_runs() -> list[dict]:
    """Return all baseline runs across all fixtures as flat dicts for JS rendering."""
    rows = read_tsv_rows(BASELINE_TSV)
    out = []
    for r in rows:
        notes = r.get("notes") or ""
        m = re.search(r"status=(\w+)", notes)
        status = m.group(1) if m else ""
        composite_raw = parse_int(r.get("noncached_plus_output_tokens"))
        cache_ratio_raw = r.get("cache_ratio")
        try:
            cache_ratio = float(cache_ratio_raw) if cache_ratio_raw else None
        except (TypeError, ValueError):
            cache_ratio = None
        out.append(
            {
                "fixture": r.get("fixture_id"),
                "run_id": r.get("run_id"),
                "timestamp": r.get("timestamp"),
                "composite": composite_raw if composite_raw is not None else 0,
                "cache_ratio": round(cache_ratio, 1) if cache_ratio is not None else None,
                "gates": r.get("gates_passed") or "",
                "wallclock_s": parse_int(r.get("wallclock_s")),
                "status": status,
                "feature_correct": parse_bool(r.get("feature_correct")),
            }
        )
    return out


def extract_branch(notes: str | None) -> str | None:
    if not notes:
        return None
    m = BRANCH_RE.search(notes)
    return m.group(1) if m else None


def derive_iteration_index(branch: str) -> tuple[int | None, str | None]:
    m = ITER_BRANCH_RE.match(branch or "")
    if not m:
        return None, None
    return int(m.group(1)), m.group(2)


def gates_passed_count(row: dict) -> int:
    gp = row.get("gates_passed") or ""
    m = re.match(r"^(\d+)/\d+", str(gp))
    return int(m.group(1)) if m else 0


def group_iterations(rows: list[dict], baseline: dict) -> list[dict]:
    grouped: dict[int, list[dict]] = {}
    for r in rows:
        # Branch is the authoritative source (dedicated TSV column); fall back
        # to legacy `branch=<name>` prefix in notes for rows written by older
        # loop.py versions that didn't populate the column.
        branch_val = r.get("branch") or extract_branch(r.get("notes")) or ""
        idx, _ = derive_iteration_index(branch_val)
        if idx is not None:
            grouped.setdefault(idx, []).append(r)
    out = []
    for idx in sorted(grouped.keys()):
        rows_i = sorted(grouped[idx], key=lambda r: r.get("timestamp") or "")
        primary = next((r for r in rows_i if r.get("fixture_id") == "A"), rows_i[0])
        branch = primary.get("branch") or extract_branch(primary.get("notes")) or ""
        _, ref = derive_iteration_index(branch)
        composite = parse_int(primary.get("composite"))
        mean = baseline.get("mean")
        stdev = baseline.get("stdev")
        delta_pct = None
        delta_sigma = None
        if composite is not None and mean:
            delta_pct = round((composite - mean) / mean * 100.0, 2)
            if stdev:
                delta_sigma = round((composite - mean) / stdev, 2)
        out.append(
            {
                "index": idx,
                "ref": ref or "(unnamed)",
                "date": (primary.get("timestamp") or "")[:10],
                "verdict": (primary.get("decision") or "pending").strip(),
                "composite": composite,
                "delta_pct": delta_pct,
                "delta_sigma": delta_sigma,
                "gates": f"{gates_passed_count(primary)}/6",
                # Per-gate booleans (JSON string) so introspect.py can measure gate
                # discrimination; "" for rows that predate the gates_json column.
                "gates_json": primary.get("gates_json") or "",
            }
        )
    return out


# ─── page data builder ───────────────────────────────────────────────────────


def build_page_data() -> dict:
    """Build the complete data payload for the HTML page."""
    generated_at = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    baseline = parse_baseline()
    iterations = group_iterations(read_tsv_rows(OPTIMIZE_TSV), baseline)
    runs = parse_all_runs()

    # Build fixtures dict from summary JSON
    fixtures: dict[str, dict] = {}
    if BASELINE_SUMMARY.exists():
        try:
            raw = json.loads(BASELINE_SUMMARY.read_text())
        except (OSError, json.JSONDecodeError):
            raw = {}
    else:
        raw = {}

    for fix in PROMO_ORDER:
        s = raw.get(fix) or {}
        if s.get("status") == "stable":
            fixtures[fix] = {
                "status": "stable",
                "stable_runs": s.get("stable_runs", 0),
                "total_runs": s.get("total_runs", 0),
                "mean": s.get("mean"),
                "stdev": s.get("stdev"),
                "floor": s.get("noise_floor_2sigma"),
                "min": s.get("min"),
                "max": s.get("max"),
            }
        else:
            fixtures[fix] = {
                "status": "unstable",
                "stable_runs": s.get("stable_runs", 0),
                "total_runs": s.get("total_runs", 0),
                "mean": None,
                "stdev": None,
                "floor": None,
                "min": None,
                "max": None,
            }

    return {
        "generated_at": generated_at,
        "fixtures": fixtures,
        "runs": runs,
        "iterations": iterations,
    }


# ─── HTML data block rewriter ────────────────────────────────────────────────


def rewrite_data_block(html_text: str, data_json_str: str) -> tuple[str, bool]:
    """Replace content of the autoresearch-data script tag.

    Returns (new_text, found) where found indicates whether the tag was present.
    """
    found = bool(DATA_SCRIPT_RE.search(html_text))
    if not found:
        return html_text, False
    new_text = DATA_SCRIPT_RE.sub(
        lambda m: m.group(1) + "\n" + data_json_str + "\n" + m.group(3),
        html_text,
        count=1,
    )
    return new_text, True


# ─── orchestration ───────────────────────────────────────────────────────────


def architecture_drift_warnings() -> list[str]:
    """Soft check: warn if scripts on disk aren't mentioned in the explainer."""
    if not EXPLAINER.exists():
        return []
    explainer_text = EXPLAINER.read_text()
    warnings: list[str] = []
    for d in (
        REPO / "scripts" / "autoresearch",
        REPO / ".claude" / "skills" / "autoresearch" / "scripts",
    ):
        if not d.exists():
            continue
        for f in sorted(d.glob("*.py")):
            if f.name in ("__init__.py", "render_iterations.py"):
                continue
            if f.name not in explainer_text:
                warnings.append(f"  - {f.relative_to(REPO)} not mentioned in explainer")
    return warnings


def main() -> int:
    args = parse_args()
    page_data = build_page_data()
    generated_at = page_data["generated_at"]
    iterations = page_data["iterations"]
    fixtures = page_data["fixtures"]
    runs = page_data["runs"]

    # Legacy payload shape for iterations.json (keeps backward compat)
    baseline = parse_baseline()
    json_payload = {
        "generated_at": generated_at,
        "baseline": baseline,
        "iterations": iterations,
    }

    print(f"Generated payload at {generated_at}:")
    print(
        "  fixtures: "
        + ", ".join(
            f"{f}={fixtures[f]['status']}(runs={fixtures[f]['total_runs']})" for f in PROMO_ORDER
        )
    )
    print(f"  runs: {len(runs)} total across all fixtures")
    print(f"  iterations: {len(iterations)} total")
    for it in iterations:
        print(
            f"    #{it['index']} {it['ref']:<40} → {it['verdict']:<8}"
            f" composite={it['composite']} Δ={it['delta_pct']}% ({it['delta_sigma']}σ)"
        )

    warnings = architecture_drift_warnings()
    if warnings:
        print("\nArchitecture drift — scripts present but not mentioned in explainer:")
        for w in warnings:
            print(w)
        print(
            "  → update the architecture tables by hand; this script does NOT auto-rewrite prose."
        )

    if args.dry_run:
        data_json_str = json.dumps(page_data, indent=2)
        print(f"\n[dry-run] would write {OUT_JSON} ({len(json.dumps(json_payload))} bytes)")
        if not args.json_only:
            if not EXPLAINER.exists():
                print(
                    f"[dry-run] WARN: {EXPLAINER.relative_to(REPO)} missing — cannot preview rewrite"
                )
            else:
                text = EXPLAINER.read_text()
                new_text, found = rewrite_data_block(text, data_json_str)
                if not found:
                    print(
                        '[dry-run] FAIL: <script id="autoresearch-data"> tag missing in explainer'
                    )
                else:
                    print(
                        f"[dry-run] would rewrite {EXPLAINER.relative_to(REPO)}:"
                        f" {len(text)} → {len(new_text)} bytes"
                    )
                    print(f"[dry-run] data block updated ({len(data_json_str)} bytes of JSON)")
        return 0

    OUT_JSON.write_text(json.dumps(json_payload, indent=2))
    print(f"\nWrote {OUT_JSON}")

    if not args.json_only:
        if not EXPLAINER.exists():
            print(f"ERROR: {EXPLAINER} missing — cannot rewrite", file=sys.stderr)
            return 1
        text = EXPLAINER.read_text()
        data_json_str = json.dumps(page_data, indent=2)
        new_text, found = rewrite_data_block(text, data_json_str)
        if not found:
            print(
                f'ERROR: <script id="autoresearch-data"> tag missing in {EXPLAINER.name}.',
                file=sys.stderr,
            )
            print("  Add the tag before running this script.", file=sys.stderr)
            return 1
        EXPLAINER.write_text(new_text)
        print(f"Updated data block in {EXPLAINER.relative_to(REPO)}")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Inject autoresearch data snapshot into autoresearch-explainer.html"
        " + write iterations.json."
    )
    p.add_argument(
        "--json-only",
        action="store_true",
        help="Write iterations.json only; skip the explainer rewrite",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Show what would change without writing files"
    )
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())
