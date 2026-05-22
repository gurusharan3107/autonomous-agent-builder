#!/usr/bin/env python3
"""N=5 baseline driver per docs/autoresearch/baseline_variance.md.

Runs each fixture N times against `main` (or whatever branch is checked out),
appends rows to baseline_runs.tsv, and computes per-fixture mean/σ for
composite, noncached_plus_output_tokens, operator_turns, and wallclock_s.

Output: docs/autoresearch/baseline_runs_summary.json — the 2σ floor that
compare.py reads when deciding keep/discard.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
TSV_ROOT = ROOT / "docs" / "autoresearch"


def run_one_fixture(
    fixture: str, branch: str, port: int, evidence_dir: pathlib.Path, dry_run: bool
) -> dict:
    cmd = [
        sys.executable, str(ROOT / "scripts" / "autoresearch" / "run.py"),
        "--fixture", fixture,
        "--branch", branch,
        "--port", str(port),
        "--evidence-dir", str(evidence_dir),
        "--baseline",
    ]
    if dry_run:
        cmd.append("--dry-run")
    out = subprocess.check_output(cmd, cwd=str(ROOT))
    return json.loads(out.decode().strip().splitlines()[-1])


def compute_summary(runs_by_fixture: dict[str, list[dict]]) -> dict:
    summary: dict[str, dict] = {}
    for fixture, runs in runs_by_fixture.items():
        clean = [r for r in runs if r.get("gates_passed", "").startswith("6/6")]
        composites = [r["composite"] for r in clean if r.get("composite")]
        if len(composites) < 3:
            summary[fixture] = {
                "status": "unstable",
                "stable_runs": len(composites),
                "total_runs": len(runs),
                "note": "Fewer than 3 clean baseline runs — σ unreliable.",
            }
            continue
        m = statistics.mean(composites)
        s = statistics.stdev(composites)
        summary[fixture] = {
            "status": "stable",
            "stable_runs": len(composites),
            "total_runs": len(runs),
            "mean": m,
            "stdev": s,
            "min": min(composites),
            "max": max(composites),
            "noise_floor_2sigma": m - 2 * s,
        }
    return summary


def append_variance_doc(summary: dict, out_md: pathlib.Path) -> None:
    section = ["\n## Recorded baselines\n", f"\nRun date: {time.strftime('%Y-%m-%d')}\n\n"]
    section.append("| Fixture | Status | Stable Runs | Mean Composite | σ | 2σ Noise Floor |\n")
    section.append("| --- | --- | --- | --- | --- | --- |\n")
    for f, s in sorted(summary.items()):
        if s.get("status") == "stable":
            section.append(
                f"| {f} | stable | {s['stable_runs']}/{s['total_runs']} | "
                f"{s['mean']:.0f} | {s['stdev']:.0f} | {s['noise_floor_2sigma']:.0f} |\n"
            )
        else:
            section.append(
                f"| {f} | {s.get('status')} | {s.get('stable_runs',0)}/{s.get('total_runs',0)} | — | — | — |\n"
            )
    with out_md.open("a") as f:
        f.writelines(section)


def main() -> int:
    args = parse_args()
    fixtures = [f.strip() for f in args.fixtures.split(",") if f.strip()]
    evidence_root = pathlib.Path(args.evidence_root)
    evidence_root.mkdir(parents=True, exist_ok=True)

    runs_by_fixture: dict[str, list[dict]] = {f: [] for f in fixtures}
    for fixture in fixtures:
        for i in range(args.n):
            ev = evidence_root / fixture / f"run-{i}"
            port = args.port_base + i
            print(f"[baseline] fixture={fixture} iter={i+1}/{args.n} port={port} evidence={ev}", file=sys.stderr)
            try:
                result = run_one_fixture(fixture, args.branch, port, ev, args.dry_run)
                runs_by_fixture[fixture].append(result)
            except subprocess.CalledProcessError as exc:
                print(f"[baseline] iter failed: {exc}", file=sys.stderr)
                runs_by_fixture[fixture].append({"run_id": None, "error": str(exc)})

    summary = compute_summary(runs_by_fixture)
    out_json = TSV_ROOT / "baseline_runs_summary.json"
    out_json.write_text(json.dumps(summary, indent=2))
    append_variance_doc(summary, TSV_ROOT / "baseline_variance.md")
    print(json.dumps(summary, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="N=5 baseline driver.")
    p.add_argument("--fixtures", default="A,B,C,D,E")
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--evidence-root", default="/tmp/autoresearch/baseline")
    p.add_argument("--branch", default="main")
    p.add_argument("--port-base", type=int, default=9876)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())
