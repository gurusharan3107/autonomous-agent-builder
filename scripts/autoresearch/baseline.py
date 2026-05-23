#!/usr/bin/env python3
"""N=5 baseline driver per docs/autoresearch/baseline_variance.md.

Runs each fixture N times against `main` (or whatever branch is checked out),
appends rows to baseline_runs.tsv, and computes per-fixture mean/σ for
composite (= `noncached_plus_output_tokens` per P16, 2026-05-23).

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
SELF_HEAL = ROOT / ".claude" / "skills" / "autoresearch" / "scripts" / "self_heal.py"
DEFAULT_SEED_DIR = pathlib.Path("/home/gurusharangupta/.seed/devpulse")


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


def invoke_self_heal(evidence_dir: pathlib.Path, seed_dir: pathlib.Path) -> dict:
    """Run the skill-owned self_heal probe; return the fix record.

    Skill at .claude/skills/autoresearch/scripts/self_heal.py owns the
    pattern catalog and remediations. Harness invokes it as a subprocess
    to preserve the harness/skill boundary (Hard Rule 3: harness must not
    import from skill or builder)."""
    if not SELF_HEAL.exists():
        return {"applied": False, "pattern": None,
                "detail": f"self_heal.py missing at {SELF_HEAL}"}
    try:
        r = subprocess.run(
            [sys.executable, str(SELF_HEAL),
             "--evidence-dir", str(evidence_dir),
             "--seed-dir", str(seed_dir)],
            capture_output=True, text=True, timeout=300,
        )
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError:
            return {"applied": False, "pattern": None,
                    "detail": f"self_heal returned non-JSON: {r.stdout[:200]} stderr={r.stderr[:200]}"}
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"applied": False, "pattern": None,
                "detail": f"self_heal failed: {type(exc).__name__}: {exc}"}


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
    aborted = False
    # Per-iter self-heal attempt cap: prevents an unfixable error from looping
    # forever (e.g., self_heal applies the wrong fix and the iter keeps failing).
    # 2 = at most one auto-fix + one retry per iter.
    MAX_HEAL_ATTEMPTS = 2

    def _gate_issues(res: dict) -> list[str]:
        """Return the list of imperfections in an iter result. Empty = clean."""
        out = []
        if res.get("feature_correct") is not True:
            out.append(f"feature_correct={res.get('feature_correct')!r}")
        if not (res.get("gates_passed") or "").startswith("6/"):
            out.append(f"gates_passed={res.get('gates_passed') or '?'}")
        if res.get("decision_status") != "shipped":
            out.append(f"decision_status={res.get('decision_status') or '?'}")
        return out

    seed_dir = pathlib.Path(args.seed_dir) if args.seed_dir else DEFAULT_SEED_DIR

    for f_idx, fixture in enumerate(fixtures):
        if aborted:
            break
        for i in range(args.n):
            ev_base = evidence_root / fixture / f"run-{i}"
            port = args.port_base + i

            # Strict per-iter gate (P17 2026-05-23): every iter must ship 6/6
            # gates with feature_correct=True. If the gate fires, the skill's
            # self_heal.py probes evidence_dir/feature_check.log + seed git
            # state for known patterns (missing seed deps, uncommitted seed
            # working-tree) and auto-applies the mechanical fix. The iter is
            # then retried in a FRESH evidence subdir. If self_heal can't
            # match a pattern, baseline aborts with diagnostic pointers —
            # autonomous when possible, transparent when not.
            for attempt in range(MAX_HEAL_ATTEMPTS):
                ev = ev_base if attempt == 0 else (ev_base.parent / f"run-{i}.heal{attempt}")
                print(f"[baseline] fixture={fixture} iter={i+1}/{args.n} port={port} evidence={ev}"
                      + (f" (heal-attempt {attempt})" if attempt else ""),
                      file=sys.stderr)
                try:
                    result = run_one_fixture(fixture, args.branch, port, ev, args.dry_run)
                except subprocess.CalledProcessError as exc:
                    print(f"[baseline] iter crashed: {exc}", file=sys.stderr)
                    result = {"run_id": None, "error": str(exc),
                              "feature_correct": False, "decision_status": "crash",
                              "gates_passed": "0/6"}

                # In dry-run or --allow-imperfect mode, skip the gate.
                if args.dry_run or args.allow_imperfect_iter:
                    runs_by_fixture[fixture].append(result)
                    break

                issues = _gate_issues(result)
                if not issues:
                    runs_by_fixture[fixture].append(result)
                    break

                # Imperfect — try self_heal before recording the result.
                heal = invoke_self_heal(ev, seed_dir)
                print(
                    f"[baseline] iter imperfect: {', '.join(issues)}. "
                    f"self_heal: applied={heal.get('applied')} "
                    f"pattern={heal.get('pattern')} detail={(heal.get('detail') or '')[:200]}",
                    file=sys.stderr,
                )
                if heal.get("applied") and attempt + 1 < MAX_HEAL_ATTEMPTS:
                    # Don't append this result — retry the iter from scratch
                    # on a fresh evidence dir. The applied fix should make
                    # the next attempt clean.
                    continue

                # Either self_heal had no fix, or we've exhausted heal attempts.
                runs_by_fixture[fixture].append(result)
                remaining = (len(fixtures) - f_idx) * args.n - (i + 1)
                hints = []
                if result.get("feature_correct") is not True:
                    hints.append(f"{ev}/feature_check.log (pip/pytest stderr)")
                if not (result.get("gates_passed") or "").startswith("6/"):
                    hints.append(f"{ev}/analyze.json+metrics.json+board.json")
                if result.get("decision_status") != "shipped":
                    hints.append(f"{ev}/builder_stdout_stderr.log+crash.log")
                print(
                    f"[baseline] ABORT — fixture={fixture} iter={i+1}/{args.n} "
                    f"imperfect after {attempt+1} self_heal attempt(s). "
                    f"Saved ~{remaining} more iters. "
                    f"Inspect: {'; '.join(hints)}. "
                    f"Extend self_heal pattern catalog at "
                    f".claude/skills/autoresearch/scripts/self_heal.py, "
                    f"or re-run with --allow-imperfect-iter if flake is acceptable.",
                    file=sys.stderr,
                )
                aborted = True
                break

            if aborted:
                break

    summary = compute_summary(runs_by_fixture)
    out_json = TSV_ROOT / "baseline_runs_summary.json"
    # P17 (2026-05-23): merge with existing summary so partial re-baselines
    # (e.g., `--fixtures B,C,D,E` after A is already stable) don't clobber
    # the unrelated fixture entries. Operator can still force a full reset by
    # deleting baseline_runs_summary.json before launching.
    merged: dict[str, dict] = {}
    if out_json.exists():
        try:
            merged = json.loads(out_json.read_text())
        except (OSError, json.JSONDecodeError):
            merged = {}
    merged.update(summary)
    out_json.write_text(json.dumps(merged, indent=2))
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
    p.add_argument(
        "--seed-dir", default=None,
        help="Path to the read-only seed snapshot. Default: ~/.seed/devpulse. "
             "Used by self_heal.py when an imperfect iter triggers auto-fix.",
    )
    p.add_argument(
        "--allow-imperfect-iter", action="store_true",
        help=(
            "Continue past iters that don't ship 6/6 gates with feature_correct=True. "
            "Default: abort and require operator investigation. Use only when the "
            "imperfect-iter pattern is known-acceptable flake (e.g., a specific "
            "fixture has 1-in-5 timeout characteristic by design) and you accept "
            "the noise in σ-floor numbers."
        ),
    )
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())
