#!/usr/bin/env python3
"""Rewrite the auto-update regions inside docs/autoresearch/autoresearch-explainer.html.

Run this as part of every lane closeout. The explainer is the canonical living
artifact; this script keeps four named regions fresh:

  - AUTOUPDATE:baseline-summary    — μ / σ / 2σ-floor / clean-run count tiles
  - AUTOUPDATE:baseline-scatter    — SVG points + band + floor line
  - AUTOUPDATE:baseline-raw-rows   — <tbody> of the raw-runs table
  - AUTOUPDATE:iterations-list     — iterations history (latest 10, rest in <details>)

Everything outside the fences is hand-curated and must not be touched.

Also writes docs/autoresearch/iterations.json for downstream tooling that
prefers structured data. The explainer is the single human-readable surface;
the previously separate iterations.html was retired in favour of the fenced
regions inside the explainer.

Usage:
  python3 .claude/skills/autoresearch/scripts/render_iterations.py
  python3 .claude/skills/autoresearch/scripts/render_iterations.py --json-only
  python3 .claude/skills/autoresearch/scripts/render_iterations.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
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

INLINE_ITER_LIMIT = 10  # newest 10 stay inline; older runs collapse into <details>

# Scatter-plot axes (kept in sync with the static fence content). y scale runs
# 140k–290k mapped over y=20–170. Adjust here if the band ever needs to shift.
Y_PIX_TOP = 20.0
Y_PIX_BOTTOM = 170.0
Y_VAL_TOP = 290_000.0
Y_VAL_BOTTOM = 140_000.0
Y_VAL_RANGE = Y_VAL_TOP - Y_VAL_BOTTOM
Y_PIX_RANGE = Y_PIX_BOTTOM - Y_PIX_TOP


def y_for(val: float) -> float:
    """Map a value in the metric domain to a Y pixel coordinate in the SVG."""
    val = max(Y_VAL_BOTTOM, min(Y_VAL_TOP, val))
    return round(Y_PIX_BOTTOM - (val - Y_VAL_BOTTOM) * Y_PIX_RANGE / Y_VAL_RANGE, 2)


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
    stable = sum(1 for v in data.values()
                 if isinstance(v, dict) and v.get("status") == "stable")
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
        "measured_at": None, "mean": None, "stdev": None,
        "noise_floor_2sigma": None, "stable_fixtures": 0,
        "total_fixtures": len(PROMO_ORDER),
        "fixture_a_runs_clean": 0, "fixture_a_runs_total": 0,
        "fixture_a_runs": [],
    }


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
            "status": status,
            "wallclock_s": parse_int(r.get("wallclock_s")),
            "noncached_plus_output_tokens": parse_int(r.get("noncached_plus_output_tokens")),
            "cache_ratio": float(r.get("cache_ratio") or 0) or None,
        })
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
        idx, _ = derive_iteration_index(extract_branch(r.get("notes")) or "")
        if idx is not None:
            grouped.setdefault(idx, []).append(r)
    out = []
    for idx in sorted(grouped.keys()):
        rows_i = sorted(grouped[idx], key=lambda r: r.get("timestamp") or "")
        primary = next((r for r in rows_i if r.get("fixture_id") == "A"), rows_i[0])
        branch = extract_branch(primary.get("notes")) or ""
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
        out.append({
            "index": idx,
            "ref": ref or "(unnamed)",
            "date": (primary.get("timestamp") or "")[:10],
            "verdict": (primary.get("decision") or "pending").strip(),
            "composite": composite,
            "delta_pct": delta_pct,
            "delta_sigma": delta_sigma,
            "gates": f"{gates_passed_count(primary)}/6",
        })
    return out


# ─── HTML region renderers ────────────────────────────────────────────────────


def render_baseline_summary(bl: dict) -> str:
    mean = bl.get("mean")
    stdev = bl.get("stdev")
    floor = bl.get("noise_floor_2sigma")
    clean = bl.get("fixture_a_runs_clean", 0)
    total = bl.get("fixture_a_runs_total", 0)
    mean_disp = f"{int(round(mean)):,}" if isinstance(mean, (int, float)) else "—"
    stdev_disp = f"{int(round(stdev)):,}" if isinstance(stdev, (int, float)) else "—"
    floor_disp = f"{int(round(floor)):,}" if isinstance(floor, (int, float)) else "—"
    return (
        '<div class="stats">\n'
        f'  <div class="stat"><div class="num">{mean_disp}</div><div class="lab">μ (mean)</div></div>\n'
        f'  <div class="stat"><div class="num">{stdev_disp}</div><div class="lab">σ (stdev)</div></div>\n'
        f'  <div class="stat"><div class="num">{floor_disp}</div><div class="lab">μ − 2σ floor</div></div>\n'
        f'  <div class="stat"><div class="num">{clean} / {total or "—"}</div><div class="lab">runs clean</div></div>\n'
        '</div>'
    )


def render_baseline_scatter(bl: dict) -> str:
    mean = bl.get("mean")
    stdev = bl.get("stdev")
    floor = bl.get("noise_floor_2sigma")
    runs = bl.get("fixture_a_runs", [])

    if mean is None or stdev is None:
        # No baseline yet — show empty axes + a placeholder message.
        body = (
            '<svg viewBox="0 0 640 200" role="img" aria-label="No baseline yet"'
            ' style="width:100%; max-width:720px; margin:12px 0; background:var(--paper);'
            ' border:1.5px solid var(--gray-300); border-radius:10px;">\n'
            '  <style>.lab{font-family:var(--mono);font-size:11px;fill:var(--gray-500);}</style>\n'
            '  <text class="lab" x="320" y="100" text-anchor="middle">No baseline measured yet — run baseline.py.</text>\n'
            '</svg>'
        )
        return body

    y_mean = y_for(mean)
    y_top = y_for(mean + 2 * stdev)
    y_floor = y_for(floor if floor is not None else mean - 2 * stdev)
    band_h = round(y_floor - y_top, 2)

    # X positions: evenly spaced across runs (cap at 5 visible, in TSV order).
    xs = [120, 220, 320, 420, 520]
    points = []
    labels = []
    for i, r in enumerate(runs[:5]):
        v = r.get("noncached_plus_output_tokens")
        if v is None:
            continue
        y = y_for(v)
        x = xs[i]
        points.append(f'      <circle class="point" cx="{x}" cy="{y}" r="4"/>')
        labels.append(f'      <text class="lab" x="{x}" y="185" text-anchor="middle">r{i+1}</text>')

    mean_label_value = int(round(mean / 1000))  # e.g. 216
    floor_label_value = int(round((floor or 0) / 1000))

    return (
        '<svg viewBox="0 0 640 200" role="img" aria-label="Fixture A baseline runs with 2σ floor"'
        ' style="width:100%; max-width:720px; margin:12px 0; background:var(--paper);'
        ' border:1.5px solid var(--gray-300); border-radius:10px;">\n'
        '  <style>\n'
        '    .axis     { stroke: var(--gray-300); stroke-width: 1; }\n'
        '    .band     { fill: var(--oat); opacity: 0.35; }\n'
        '    .mean     { stroke: var(--gray-500); stroke-width: 1; stroke-dasharray: 4 3; }\n'
        '    .floor    { stroke: var(--clay); stroke-width: 1.25; }\n'
        '    .point    { fill: var(--clay); }\n'
        '    .lab      { font-family: var(--mono); font-size: 9px; fill: var(--gray-500); }\n'
        '    .lab-k    { font-family: var(--mono); font-size: 9px; fill: var(--slate); }\n'
        '    .lab-cl   { font-family: var(--mono); font-size: 9px; fill: var(--clay); }\n'
        '  </style>\n'
        f'  <rect class="band" x="56" y="{y_top}" width="544" height="{band_h}"/>\n'
        f'  <line class="mean"  x1="56" y1="{y_mean}" x2="600" y2="{y_mean}"/>\n'
        f'  <line class="floor" x1="56" y1="{y_floor}" x2="600" y2="{y_floor}"/>\n'
        '  <line class="axis"  x1="56" y1="20"  x2="56"  y2="170"/>\n'
        '  <line class="axis"  x1="56" y1="170" x2="600" y2="170"/>\n'
        '  <text class="lab"    x="50" y="173" text-anchor="end">140k</text>\n'
        '  <text class="lab"    x="50" y="123" text-anchor="end">190k</text>\n'
        f'  <text class="lab-k"  x="50" y="{y_mean + 4}" text-anchor="end">μ {mean_label_value}</text>\n'
        '  <text class="lab"    x="50" y="23"  text-anchor="end">290k</text>\n'
        f'  <text class="lab-cl" x="50" y="{y_floor + 3}" text-anchor="end">2σ {floor_label_value}</text>\n'
        + "\n".join(points) + "\n"
        + "\n".join(labels) + "\n"
        '  <text class="lab"    x="600" y="35"  text-anchor="end">μ ± 2σ band</text>\n'
        '  <text class="lab-cl" x="600" y="105" text-anchor="end">candidates land below</text>\n'
        '</svg>'
    )


def render_baseline_raw_rows(bl: dict) -> str:
    runs = bl.get("fixture_a_runs", [])
    if not runs:
        return (
            '<table style="margin-top:0;">\n'
            '  <thead><tr><th>Run</th><th>noncached + output</th><th>cache ratio</th>'
            '<th>gates</th><th>wallclock</th><th>status</th></tr></thead>\n'
            '  <tbody>\n'
            '    <tr><td colspan="6" style="text-align:center; color:var(--gray-500);'
            ' padding:14px; font-style:italic;">No baseline runs yet.</td></tr>\n'
            '  </tbody>\n'
            '</table>'
        )
    body_rows = []
    for i, r in enumerate(runs, start=1):
        v = r.get("noncached_plus_output_tokens")
        v_disp = f"{v:,}" if v is not None else "—"
        cr = r.get("cache_ratio")
        cr_disp = f"{cr:.1f}" if cr is not None else "—"
        gp = r.get("gates_passed") or "—"
        wc = r.get("wallclock_s")
        wc_disp = f"{wc} s" if wc is not None else "—"
        status = html.escape(r.get("status") or "")
        body_rows.append(
            f'    <tr><td>r{i}</td><td class="num">{v_disp}</td>'
            f'<td class="num">{cr_disp}</td><td class="num">{gp}</td>'
            f'<td class="num">{wc_disp}</td><td class="mono">{status}</td></tr>'
        )
    return (
        '<table style="margin-top:0;">\n'
        '  <thead><tr><th>Run</th><th>noncached + output</th><th>cache ratio</th>'
        '<th>gates</th><th>wallclock</th><th>status</th></tr></thead>\n'
        '  <tbody>\n'
        + "\n".join(body_rows) + "\n"
        '  </tbody>\n'
        '</table>'
    )


def render_iterations_list(iterations: list[dict]) -> str:
    if not iterations:
        return (
            '<table>\n'
            '  <thead><tr><th>#</th><th>Date</th><th>Idea</th><th>Verdict</th>'
            '<th>Composite</th><th>Δ%</th><th>Δσ</th><th>Gates</th></tr></thead>\n'
            '  <tbody>\n'
            '    <tr><td colspan="8" style="text-align:center; color:var(--gray-500);'
            ' padding:18px 12px; font-style:italic;">No iterations recorded yet — run'
            ' <code>loop.py</code> to populate.</td></tr>\n'
            '  </tbody>\n'
            '</table>'
        )

    def fmt_row(it: dict) -> str:
        v = it.get("composite")
        v_disp = f"{v:,}" if v is not None else "—"
        dp = it.get("delta_pct")
        ds = it.get("delta_sigma")
        dp_disp = f"{dp:+.1f}%" if dp is not None else "—"
        ds_disp = f"{ds:+.2f}σ" if ds is not None else "—"
        verdict = (it.get("verdict") or "pending").lower()
        verdict_color = {
            "keep": "var(--olive)",
            "discard": "var(--rust)",
            "crash": "var(--rust)",
        }.get(verdict, "var(--gray-500)")
        return (
            f'    <tr>\n'
            f'      <td class="mono">#{it["index"]}</td>\n'
            f'      <td class="mono">{html.escape(it.get("date") or "—")}</td>\n'
            f'      <td>{html.escape(it.get("ref") or "—")}</td>\n'
            f'      <td class="mono" style="color:{verdict_color}">{html.escape(verdict.upper())}</td>\n'
            f'      <td class="num">{v_disp}</td>\n'
            f'      <td class="num">{dp_disp}</td>\n'
            f'      <td class="num">{ds_disp}</td>\n'
            f'      <td class="num">{html.escape(it.get("gates") or "—")}</td>\n'
            f'    </tr>'
        )

    iterations_desc = list(reversed(iterations))  # newest first
    inline = iterations_desc[:INLINE_ITER_LIMIT]
    rest = iterations_desc[INLINE_ITER_LIMIT:]

    parts = [
        '<table>',
        '  <thead><tr><th>#</th><th>Date</th><th>Idea</th><th>Verdict</th>'
        '<th>Composite</th><th>Δ%</th><th>Δσ</th><th>Gates</th></tr></thead>',
        '  <tbody>',
        "\n".join(fmt_row(it) for it in inline),
        '  </tbody>',
        '</table>',
    ]
    if rest:
        parts.append(
            '<details style="margin-top:10px;">\n'
            f'  <summary>Show {len(rest)} older iteration(s)</summary>\n'
            '  <div class="body">\n'
            '    <table style="margin-top:0;">\n'
            '      <thead><tr><th>#</th><th>Date</th><th>Idea</th><th>Verdict</th>'
            '<th>Composite</th><th>Δ%</th><th>Δσ</th><th>Gates</th></tr></thead>\n'
            '      <tbody>\n'
            + "\n".join(fmt_row(it) for it in rest) + "\n"
            '      </tbody>\n'
            '    </table>\n'
            '  </div>\n'
            '</details>'
        )
    return "\n".join(parts)


# ─── fence rewriter ──────────────────────────────────────────────────────────


FENCE_RE = re.compile(
    r"(?P<open><!--\s*AUTOUPDATE:(?P<name>[a-z0-9-]+)\s+v=(?P<v>\d+)\s*-->)"
    r"(?P<body>.*?)"
    r"(?P<close><!--\s*/AUTOUPDATE:(?P=name)\s*-->)",
    re.DOTALL,
)


def rewrite_fences(text: str, regions: dict[str, str]) -> tuple[str, set[str]]:
    """Rewrite each named region inline. Returns (new_text, names_seen).

    Names in `regions` that don't appear in the text are reported via
    `seen` — the caller decides whether absence is fatal.
    """
    seen: set[str] = set()

    def repl(m: re.Match[str]) -> str:
        name = m.group("name")
        seen.add(name)
        if name not in regions:
            return m.group(0)
        body = "\n" + regions[name].strip() + "\n"
        return m.group("open") + body + m.group("close")

    return FENCE_RE.sub(repl, text), seen


def update_timestamp(text: str, generated_at: str) -> str:
    return re.sub(
        r'(<span data-autoupdate-ts>).*?(</span>)',
        rf'\1{html.escape(generated_at)}\2',
        text, count=1,
    )


# ─── orchestration ───────────────────────────────────────────────────────────


def architecture_drift_warnings() -> list[str]:
    """Soft check: warn if scripts on disk aren't mentioned in the explainer."""
    if not EXPLAINER.exists():
        return []
    explainer_text = EXPLAINER.read_text()
    warnings: list[str] = []
    for d in (REPO / "scripts" / "autoresearch",
              REPO / ".claude" / "skills" / "autoresearch" / "scripts"):
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
    baseline = parse_baseline()
    iterations = group_iterations(read_tsv_rows(OPTIMIZE_TSV), baseline)
    generated_at = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "generated_at": generated_at,
        "baseline": baseline,
        "iterations": iterations,
    }

    print(f"Generated payload at {generated_at}:")
    print(f"  baseline: mean={baseline.get('mean')} stdev={baseline.get('stdev')}"
          f" 2σ-floor={baseline.get('noise_floor_2sigma')}"
          f" stable={baseline.get('stable_fixtures')}/{baseline.get('total_fixtures')}"
          f" clean={baseline.get('fixture_a_runs_clean')}/{baseline.get('fixture_a_runs_total')}")
    print(f"  iterations: {len(iterations)} total")
    for it in iterations:
        print(f"    #{it['index']} {it['ref']:<40} → {it['verdict']:<8}"
              f" composite={it['composite']} Δ={it['delta_pct']}% ({it['delta_sigma']}σ)")

    warnings = architecture_drift_warnings()
    if warnings:
        print("\nArchitecture drift — scripts present but not mentioned in explainer:")
        for w in warnings:
            print(w)
        print("  → update the architecture tables by hand; this script does NOT auto-rewrite prose.")

    if args.dry_run:
        print(f"\n[dry-run] would write {OUT_JSON} ({len(json.dumps(payload))} bytes)")
        if not args.json_only:
            _explainer_dry_run(payload)
        return 0

    OUT_JSON.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {OUT_JSON}")

    if not args.json_only:
        ok = rewrite_explainer(payload)
        if not ok:
            return 1
        print(f"Updated AUTOUPDATE regions in {EXPLAINER.relative_to(REPO)}")
    return 0


def _explainer_dry_run(payload: dict) -> None:
    if not EXPLAINER.exists():
        print(f"[dry-run] WARN: {EXPLAINER.relative_to(REPO)} missing — cannot preview rewrite")
        return
    regions = _build_regions(payload)
    text = EXPLAINER.read_text()
    new_text, seen = rewrite_fences(text, regions)
    new_text = update_timestamp(new_text, payload["generated_at"])
    missing = set(regions) - seen
    if missing:
        print(f"[dry-run] FAIL: regions missing in explainer: {sorted(missing)}")
        return
    print(f"[dry-run] would rewrite {EXPLAINER.relative_to(REPO)}:"
          f" {len(text)} → {len(new_text)} bytes")
    print(f"[dry-run] regions touched: {sorted(seen & set(regions))}")


def _build_regions(payload: dict) -> dict[str, str]:
    return {
        "baseline-summary":  render_baseline_summary(payload["baseline"]),
        "baseline-scatter":  render_baseline_scatter(payload["baseline"]),
        "baseline-raw-rows": render_baseline_raw_rows(payload["baseline"]),
        "iterations-list":   render_iterations_list(payload["iterations"]),
    }


def rewrite_explainer(payload: dict) -> bool:
    if not EXPLAINER.exists():
        print(f"ERROR: {EXPLAINER} missing — cannot rewrite", file=sys.stderr)
        return False
    text = EXPLAINER.read_text()
    regions = _build_regions(payload)
    new_text, seen = rewrite_fences(text, regions)
    new_text = update_timestamp(new_text, payload["generated_at"])
    missing = set(regions) - seen
    if missing:
        print(f"ERROR: AUTOUPDATE regions missing in {EXPLAINER.name}:"
              f" {sorted(missing)}", file=sys.stderr)
        print("  Restore the fences before running this script.", file=sys.stderr)
        return False
    EXPLAINER.write_text(new_text)
    return True


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Refresh AUTOUPDATE regions in autoresearch-explainer.html"
                    " + write iterations.json.")
    p.add_argument("--json-only", action="store_true",
                   help="Write iterations.json only; skip the explainer rewrite")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would change without writing files")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())
