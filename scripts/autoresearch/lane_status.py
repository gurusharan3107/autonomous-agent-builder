#!/usr/bin/env python3
"""Read-only status reporter for in-flight autoresearch lanes.

Auto-discovers running `baseline.py` / `loop.py` (and their `run.py` /
`builder start` children) from `ps -ef`. Reads each process's argv to find
its evidence-root, parses the parent's stdout log (if accessible) and the
in-progress evidence dir to compute fixture/iter progress, elapsed time,
and a rough ETA. Output is JSON by default for downstream consumption.

Use this when joining a session and the autoresearch substrate state is
changing (TSV rows appearing, builder ports busy) but the producer is not
something this session launched. Saves the next session the "wait, what's
running?" friction we hit on 2026-05-23.

Usage:
    python3 scripts/autoresearch/lane_status.py
    python3 scripts/autoresearch/lane_status.py --json
    python3 scripts/autoresearch/lane_status.py --human

Read-only. Never mutates state. Safe to run in parallel with the lane.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shlex
import subprocess
import sys
import time


LANE_PRODUCERS = ("baseline.py", "loop.py")
RUN_PY = "run.py"
BUILDER_START = "builder start"
WATCHDOG = "hang_watchdog.py"


def _ps_lines() -> list[str]:
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid,etime,user,args"],
            text=True, timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return []
    return [ln.strip() for ln in out.splitlines()[1:] if ln.strip()]


def _parse_ps_line(line: str) -> dict | None:
    parts = line.split(None, 3)
    if len(parts) < 4:
        return None
    pid, etime, user, args = parts
    try:
        pid_int = int(pid)
    except ValueError:
        return None
    return {"pid": pid_int, "etime": etime, "user": user, "args": args}


def _etime_to_seconds(etime: str) -> int | None:
    # ps etime format: [[DD-]HH:]MM:SS
    days = 0
    s = etime
    if "-" in s:
        d, _, s = s.partition("-")
        try:
            days = int(d)
        except ValueError:
            return None
    bits = s.split(":")
    try:
        bits_i = [int(b) for b in bits]
    except ValueError:
        return None
    h = m = sec = 0
    if len(bits_i) == 3:
        h, m, sec = bits_i
    elif len(bits_i) == 2:
        m, sec = bits_i
    elif len(bits_i) == 1:
        sec = bits_i[0]
    else:
        return None
    return days * 86400 + h * 3600 + m * 60 + sec


def discover_processes() -> dict:
    lines = _ps_lines()
    lanes: list[dict] = []
    runs: list[dict] = []
    builders: list[dict] = []
    watchdogs: list[dict] = []
    for line in lines:
        p = _parse_ps_line(line)
        if not p:
            continue
        args = p["args"]
        if any(prod in args for prod in LANE_PRODUCERS) and "python" in args:
            lanes.append(p)
        elif RUN_PY in args and "python" in args:
            runs.append(p)
        elif BUILDER_START in args:
            builders.append(p)
        elif WATCHDOG in args:
            watchdogs.append(p)
    return {
        "lanes": lanes,
        "runs": runs,
        "builders": builders,
        "watchdogs": watchdogs,
    }


def _argv_field(args: str, flag: str) -> str | None:
    # Match `--flag VALUE` or `--flag=VALUE`
    parts = shlex.split(args)
    for i, tok in enumerate(parts):
        if tok == flag and i + 1 < len(parts):
            return parts[i + 1]
        if tok.startswith(flag + "="):
            return tok.split("=", 1)[1]
    return None


def summarize_lane(lane: dict, runs: list[dict]) -> dict:
    args = lane["args"]
    is_baseline = "baseline.py" in args
    kind = "baseline" if is_baseline else "iterate"
    evidence_root = _argv_field(args, "--evidence-root")
    fixtures_arg = _argv_field(args, "--fixtures") or "A,B,C,D,E"
    fixtures = [f.strip() for f in fixtures_arg.split(",") if f.strip()]
    n = int(_argv_field(args, "--n") or 5)
    elapsed_s = _etime_to_seconds(lane["etime"]) or 0
    summary: dict = {
        "pid": lane["pid"],
        "kind": kind,
        "argv": args,
        "etime": lane["etime"],
        "elapsed_seconds": elapsed_s,
        "evidence_root": evidence_root,
        "fixtures": fixtures,
        "n_per_fixture": n,
        "total_runs_expected": len(fixtures) * n,
    }
    # Active run.py child (one of `runs` whose --evidence-dir lives under evidence_root)
    active_child = None
    if evidence_root:
        for r in runs:
            ev = _argv_field(r["args"], "--evidence-dir") or ""
            if ev.startswith(evidence_root):
                active_child = {
                    "pid": r["pid"],
                    "evidence_dir": ev,
                    "fixture": _argv_field(r["args"], "--fixture"),
                    "port": _argv_field(r["args"], "--port"),
                    "etime": r["etime"],
                    "elapsed_seconds": _etime_to_seconds(r["etime"]) or 0,
                }
                break
    summary["active_child"] = active_child
    # Progress from evidence dir layout (one run-N per completed iteration)
    if evidence_root and pathlib.Path(evidence_root).is_dir():
        completed_by_fixture: dict[str, int] = {}
        for f in fixtures:
            d = pathlib.Path(evidence_root) / f
            if not d.is_dir():
                continue
            run_dirs = sorted([
                p for p in d.iterdir() if p.is_dir() and p.name.startswith("run-")
            ])
            # A run-N dir is "completed" if it has metrics.json (run.py writes it
            # after the harness's capture_evidence step finishes). In-flight
            # run-N dirs typically only have builder_stdout_stderr.log + raw_bodies.
            done = sum(1 for r in run_dirs if (r / "metrics.json").exists())
            completed_by_fixture[f] = done
        summary["completed_by_fixture"] = completed_by_fixture
        summary["total_completed"] = sum(completed_by_fixture.values())
    else:
        summary["completed_by_fixture"] = {}
        summary["total_completed"] = 0
    # Rough ETA: avg time per completed run × remaining
    completed = summary["total_completed"]
    remaining = max(summary["total_runs_expected"] - completed, 0)
    if completed > 0 and elapsed_s > 0:
        avg_per_run = elapsed_s / max(completed, 1)
        summary["avg_seconds_per_run"] = int(avg_per_run)
        summary["estimated_remaining_seconds"] = int(avg_per_run * remaining)
    else:
        summary["avg_seconds_per_run"] = None
        summary["estimated_remaining_seconds"] = None
    return summary


def format_human(report: dict) -> str:
    lines = ["# Autoresearch lane status"]
    if not report["lanes"]:
        lines.append("")
        lines.append("No `baseline.py` or `loop.py` running.")
        if report["builders"]:
            lines.append(
                f"({len(report['builders'])} builder server(s) running — may be unrelated workspaces.)"
            )
        return "\n".join(lines)
    for lane in report["lanes"]:
        kind = lane["kind"]
        lines.append("")
        lines.append(f"## {kind} lane (PID {lane['pid']}, elapsed {lane['etime']})")
        lines.append(f"  evidence-root: {lane['evidence_root']}")
        lines.append(
            f"  fixtures: {','.join(lane['fixtures'])} × N={lane['n_per_fixture']}"
            f" = {lane['total_runs_expected']} runs total"
        )
        completed = lane["total_completed"]
        expected = lane["total_runs_expected"]
        lines.append(f"  progress: {completed}/{expected} runs complete")
        for f in lane["fixtures"]:
            n = lane["completed_by_fixture"].get(f, 0)
            marker = "→" if lane["active_child"] and lane["active_child"].get("fixture") == f else " "
            lines.append(f"    {marker} {f}: {n}/{lane['n_per_fixture']}")
        if lane["active_child"]:
            c = lane["active_child"]
            lines.append(
                f"  active run.py child: PID {c['pid']}, fixture {c['fixture']}, "
                f"port {c['port']}, elapsed {c['etime']}"
            )
        if lane["estimated_remaining_seconds"] is not None:
            est_min = lane["estimated_remaining_seconds"] // 60
            avg_min = lane["avg_seconds_per_run"] // 60
            lines.append(
                f"  pace: ~{avg_min} min/run avg → estimated {est_min} min remaining"
            )
    if report["watchdogs"]:
        lines.append("")
        lines.append(f"hang_watchdog: {len(report['watchdogs'])} running (PIDs {[w['pid'] for w in report['watchdogs']]})")
    return "\n".join(lines)


def build_report() -> dict:
    procs = discover_processes()
    lanes = [summarize_lane(l, procs["runs"]) for l in procs["lanes"]]
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lanes": lanes,
        "builders": [
            {"pid": b["pid"], "etime": b["etime"], "argv": b["args"]}
            for b in procs["builders"]
        ],
        "watchdogs": [
            {"pid": w["pid"], "etime": w["etime"], "argv": w["args"]}
            for w in procs["watchdogs"]
        ],
        "any_lane_active": bool(lanes),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--json", action="store_true", help="JSON output (default)")
    p.add_argument("--human", action="store_true", help="human-readable output")
    args = p.parse_args()
    report = build_report()
    if args.human:
        print(format_human(report))
    else:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
