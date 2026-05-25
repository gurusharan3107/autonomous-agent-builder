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
SKILL_SCRIPTS = ROOT / ".claude" / "skills" / "autoresearch" / "scripts"
SELF_HEAL = SKILL_SCRIPTS / "self_heal.py"
HANG_WATCHDOG = SKILL_SCRIPTS / "hang_watchdog.py"
DIAGNOSE_HANG = SKILL_SCRIPTS / "diagnose_hang.py"
DEFAULT_SEED_DIR = pathlib.Path("/home/gurusharangupta/.seed/devpulse")

# Per-iter wall-clock budget. The hang_watchdog detects silent hangs by WAL
# mtime at 600s (P22: Sonnet first/second-turn latency can reach 120-180s,
# so 180s was too tight); this wall-clock budget is a fallback safety net for
# cases where the watchdog itself fails or where Builder is "active" (writing
# to WAL) but not making progress (e.g., infinite retry loop). 30 min is
# generous for fixture A's dashboard-MVP rebuild.
DEFAULT_ITER_WALL_CLOCK_SECONDS = 2400

# Stuck-dump polling interval — how often baseline.py checks the watchdog's
# dump-root for new STUCK_DETECTED.json files. 15s is short enough to react
# within ~3 min of the watchdog's idle threshold, and cheap enough to not spam.
STUCK_POLL_INTERVAL_SECONDS = 15


def _spawn_hang_watchdog(dump_root: pathlib.Path,
                          workspace_pattern: str | None = None,
                          ) -> subprocess.Popen | None:
    """Start hang_watchdog.py as a daemon child for this iter.

    The watchdog walks /proc for `builder start` processes, restricts to
    autoresearch workspaces (/tmp/devpulse-<uuid>/), and dumps forensics to
    dump_root/<UTC>-pid<PID>/ when WAL mtime is stale ≥ idle-seconds.

    Returns the Popen handle (caller MUST kill it on iter completion), or
    None if the script is unavailable. None is non-fatal — the iter still
    runs, just without watchdog coverage.
    """
    if not HANG_WATCHDOG.exists():
        print(f"[baseline] hang_watchdog.py not at {HANG_WATCHDOG}; iter "
              f"runs without watchdog coverage", file=sys.stderr)
        return None
    dump_root.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(HANG_WATCHDOG),
        "--idle-seconds", "600",  # P22: Sonnet first/second-turn latency can reach 120-180s
        "--grace-seconds", "60",
        "--dump-root", str(dump_root),
    ]
    if workspace_pattern:
        cmd.extend(["--workspace-pattern", workspace_pattern])
    try:
        # Detach via start_new_session so SIGTERM to baseline.py doesn't
        # cascade (we kill the watchdog explicitly via .terminate()).
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(f"[baseline] hang_watchdog spawned (PID {proc.pid}) → {dump_root}",
              file=sys.stderr)
        return proc
    except OSError as exc:
        print(f"[baseline] hang_watchdog spawn failed: {exc}", file=sys.stderr)
        return None


def _kill_watchdog(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def _latest_stuck_dump(dump_root: pathlib.Path,
                        since_ts: float) -> pathlib.Path | None:
    """Returns the newest STUCK_DETECTED.json's parent dir created after
    since_ts, or None if no new dumps. Watchdog writes one dir per stuck
    detection: <UTC>-pid<PID>/STUCK_DETECTED.json + sibling artifacts."""
    if not dump_root.exists():
        return None
    candidates: list[tuple[float, pathlib.Path]] = []
    for child in dump_root.iterdir():
        if not child.is_dir():
            continue
        stuck_json = child / "STUCK_DETECTED.json"
        if not stuck_json.exists():
            continue
        try:
            mtime = stuck_json.stat().st_mtime
        except OSError:
            continue
        if mtime > since_ts:
            candidates.append((mtime, child))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _invoke_diagnose_hang(dump_dir: pathlib.Path) -> dict:
    """Run diagnose_hang.py against a watchdog dump; return the diagnosis JSON.

    diagnose_hang prints a JSON object with `top_match` (best matcher result
    or None) + `verdict` (matched|unknown). Each Match record now carries a
    `category` field (transient|persistent|substrate|unknown) that the loop
    uses to route remediation.
    """
    if not DIAGNOSE_HANG.exists():
        return {"verdict": "unknown",
                "error": f"diagnose_hang.py missing at {DIAGNOSE_HANG}"}
    try:
        r = subprocess.run(
            [sys.executable, str(DIAGNOSE_HANG), str(dump_dir), "--json"],
            capture_output=True, text=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"verdict": "unknown",
                "error": f"diagnose_hang invocation failed: {type(exc).__name__}: {exc}"}
    try:
        return json.loads(r.stdout)
    except (ValueError, json.JSONDecodeError):
        return {"verdict": "unknown",
                "error": f"diagnose_hang non-JSON output: {r.stdout[:300]}",
                "stderr_tail": r.stderr[-300:]}


def _kill_iter_processes(port: int) -> None:
    """SIGTERM (then SIGKILL after 5s) any run.py + Builder process for this
    iter. Best-effort; if processes are already gone, no error."""
    for pattern in [f"run.py.*--port {port}", f"builder.*--port {port}"]:
        subprocess.run(["pkill", "-TERM", "-f", pattern],
                       capture_output=True, timeout=5)
    time.sleep(2)
    for pattern in [f"run.py.*--port {port}", f"builder.*--port {port}"]:
        subprocess.run(["pkill", "-KILL", "-f", pattern],
                       capture_output=True, timeout=5)


def run_one_fixture(
    fixture: str, branch: str, port: int, evidence_dir: pathlib.Path,
    dry_run: bool, wall_clock_seconds: int = DEFAULT_ITER_WALL_CLOCK_SECONDS,
    enable_watchdog: bool = True,
) -> dict:
    """Run one fixture iteration with watchdog + wall-clock budget.

    Returns either:
      - {normal run.py result fields} on success/completion (existing contract)
      - {"_stuck": True, "dump_dir": str, "diagnosis": dict, "reason": str,
         "feature_correct": False, "decision_status": "stuck",
         "gates_passed": "0/6"} on watchdog-detected hang OR wall-clock timeout.
        Caller dispatches on `diagnosis.top_match.category` for transient retry
        vs persistent escalation.
    """
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

    dump_root = evidence_dir / "stuck_dumps"
    watchdog = _spawn_hang_watchdog(dump_root) if (enable_watchdog and not dry_run) else None
    start_ts = time.time()
    proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True,
                             start_new_session=True)
    try:
        while True:
            try:
                stdout, stderr = proc.communicate(timeout=STUCK_POLL_INTERVAL_SECONDS)
            except subprocess.TimeoutExpired:
                stdout, stderr = "", ""
                # Check 1: watchdog detected a hang since iter start
                dump = _latest_stuck_dump(dump_root, start_ts)
                if dump is not None:
                    diagnosis = _invoke_diagnose_hang(dump)
                    _kill_iter_processes(port)
                    return {
                        "_stuck": True,
                        "dump_dir": str(dump),
                        "diagnosis": diagnosis,
                        "reason": "watchdog_dump_detected",
                        "feature_correct": False,
                        "decision_status": "stuck",
                        "gates_passed": "0/6",
                        "elapsed_seconds": int(time.time() - start_ts),
                    }
                # Check 2: wall-clock budget exceeded (safety net even if
                # watchdog didn't fire; e.g., watchdog itself crashed)
                if time.time() - start_ts > wall_clock_seconds:
                    _kill_iter_processes(port)
                    # Watchdog may still have produced a partial dump even
                    # without flagging STUCK — check one last time.
                    dump = _latest_stuck_dump(dump_root, start_ts)
                    if dump is None:
                        # No watchdog dump. Write a synthetic STUCK_DETECTED.json
                        # to evidence_dir so diagnose_hang.py can run its matchers
                        # against the builder log (P21: hook stream closed on
                        # graceful shutdown, P18b: dispatch DB lock, etc.).
                        synthetic = evidence_dir / "STUCK_DETECTED.json"
                        synthetic.write_text(json.dumps({
                            "reason": "wall_clock_budget_exceeded",
                            "elapsed_seconds": int(time.time() - start_ts),
                            "evidence_dir": str(evidence_dir),
                            "synthesized": True,
                        }))
                        dump = evidence_dir
                    diagnosis = _invoke_diagnose_hang(dump)
                    return {
                        "_stuck": True,
                        "dump_dir": str(dump) if dump else "",
                        "diagnosis": diagnosis,
                        "reason": "wall_clock_budget_exceeded",
                        "feature_correct": False,
                        "decision_status": "stuck",
                        "gates_passed": "0/6",
                        "elapsed_seconds": int(time.time() - start_ts),
                    }
                # Neither — keep waiting
                continue
            # communicate() returned: run.py finished normally
            break
    finally:
        _kill_watchdog(watchdog)
    if proc.returncode != 0:
        # Preserve historical CalledProcessError contract for non-stuck failures
        raise subprocess.CalledProcessError(proc.returncode, cmd,
                                             output=stdout, stderr=stderr)
    # Final JSON line in stdout is run.py's structured result (existing contract)
    try:
        return json.loads((stdout or "").strip().splitlines()[-1])
    except (IndexError, ValueError, json.JSONDecodeError) as exc:
        raise subprocess.CalledProcessError(
            1, cmd, output=stdout,
            stderr=f"run.py exit=0 but output not JSON: {exc}; stdout tail={(stdout or '')[-300:]}"
        )


def _stuck_proposed_questions(pattern_id: str, category: str,
                                top_match: dict | None) -> list[dict]:
    """Build AskUserQuestion-shaped escalation payload for stuck iters that
    couldn't be auto-recovered (category=persistent / unknown / substrate, or
    transient that exhausted retries). The calling agent surfaces these to
    the operator instead of dumping raw logs."""
    fix_pointer = (top_match or {}).get("fix_pointer", "")
    name = (top_match or {}).get("name", "unknown stuck pattern")
    if category == "transient":
        # Exhausted retries on a transient — operator probably wants to
        # extend MAX_HEAL_ATTEMPTS or treat the underlying class as persistent
        # via source fix.
        return [{
            "header": "Transient hang exhausted retries",
            "question": (
                f"Iter hit {pattern_id} ({name}) repeatedly across "
                "all retry attempts. The transient class should resolve on "
                "fresh state but didn't here. How to proceed?"
            ),
            "options": [
                {"label": "Investigate why retries didn't help",
                 "description": f"Inspect dump_dir for evidence; {fix_pointer}"},
                {"label": "Treat as persistent — source fix Builder",
                 "description": "The 'transient' hypothesis is wrong; the "
                                "underlying bug is recurring. Open Fix-lane "
                                "on Builder source per pattern's fix_pointer."},
                {"label": "Run with --allow-imperfect-iter for now",
                 "description": "Accept the flake into σ-floor numbers and "
                                "proceed (degrades baseline quality but unblocks)."},
            ],
        }]
    if category == "persistent":
        return [{
            "header": "Persistent Builder/harness defect",
            "question": (
                f"Iter hit persistent pattern {pattern_id} ({name}). "
                "Cannot be auto-retried. How to recover?"
            ),
            "options": [
                {"label": "Open Fix-lane against source",
                 "description": f"Source fix per pattern: {fix_pointer}"},
                {"label": "Investigate manually",
                 "description": "Inspect dump_dir + Builder logs; not yet "
                                "catalogued or remediation unclear."},
                {"label": "Skip this iter (degrade baseline)",
                 "description": "Continue with --allow-imperfect-iter; the "
                                "fixture's σ-floor will reflect the defect."},
            ],
        }]
    if category == "substrate":
        return [{
            "header": "Substrate-state stuck",
            "question": (
                f"Iter stuck on substrate-class pattern {pattern_id}. "
                "Substrate auto-remediation failed. How to proceed?"
            ),
            "options": [
                {"label": "Re-snapshot seed from upstream",
                 "description": "bash scripts/autoresearch/setup_seed.sh"},
                {"label": "Investigate substrate manually",
                 "description": f"{fix_pointer}"},
            ],
        }]
    # unknown
    return [{
        "header": "Unknown stuck pattern",
        "question": (
            f"Iter is stuck but no catalog pattern matched (verdict=unknown). "
            "Forensic dump preserved. How to proceed?"
        ),
        "options": [
            {"label": "Inspect dump_dir + extend catalog",
             "description": "Diagnose manually, then add matcher to "
                            "diagnose_hang.py + KNOWN_PATTERNS.md so next "
                            "session benefits."},
            {"label": "Skip this iter",
             "description": "Continue with --allow-imperfect-iter."},
        ],
    }]


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

            # Strict per-iter gate (P17 2026-05-23) + watchdog-driven autonomous
            # remediation (2026-05-24, INSIGHTS Run #10):
            #
            # 1. Each iter spawns hang_watchdog.py as a sibling process.
            #    Watchdog dumps forensics if Builder's WAL mtime is stale
            #    ≥180s, OR if wall-clock budget exceeds DEFAULT_ITER_WALL_CLOCK_SECONDS.
            # 2. If iter ships 6/6 gates with feature_correct=True → record + advance.
            # 3. If iter is "stuck" (watchdog fired OR wall-clock exceeded) →
            #    diagnose_hang categorizes the failure:
            #      • transient (e.g., P18 DB-lock race) → retry on fresh
            #        evidence subdir, no operator involvement
            #      • persistent (real Builder/harness defect) → emit
            #        SELF_HEAL_ESCALATION with proposed_questions, abort
            #      • substrate / unknown → escalate
            # 4. If iter completes but imperfect (gates fail) → self_heal.py
            #    probes evidence_dir/feature_check.log + seed state for
            #    catalogued substrate fixes (missing deps, untracked files).
            #    Auto-applies mechanical fix + retries. If no catalog match,
            #    escalates via SELF_HEAL_ESCALATION.
            #
            # MAX_HEAL_ATTEMPTS bounds total retries per iter; each retry uses
            # a fresh evidence subdir (run-{i}.heal{N}) so forensics survive.
            for attempt in range(MAX_HEAL_ATTEMPTS):
                ev = ev_base if attempt == 0 else (ev_base.parent / f"run-{i}.heal{attempt}")
                print(f"[baseline] fixture={fixture} iter={i+1}/{args.n} port={port} evidence={ev}"
                      + (f" (heal-attempt {attempt})" if attempt else ""),
                      file=sys.stderr)
                try:
                    result = run_one_fixture(
                        fixture, args.branch, port, ev, args.dry_run,
                        wall_clock_seconds=args.iter_wall_clock_seconds,
                    )
                except subprocess.CalledProcessError as exc:
                    print(f"[baseline] iter crashed: {exc}", file=sys.stderr)
                    result = {"run_id": None, "error": str(exc),
                              "feature_correct": False, "decision_status": "crash",
                              "gates_passed": "0/6"}

                # In dry-run or --allow-imperfect mode, skip the gate.
                if args.dry_run or args.allow_imperfect_iter:
                    runs_by_fixture[fixture].append(result)
                    break

                # NEW (2026-05-24): Stuck handler — watchdog or wall-clock fired.
                # Route by diagnose_hang category before falling through to the
                # gate-based imperfect path (gate-issues logic doesn't apply
                # when the iter never reached gate evaluation).
                if result.get("_stuck"):
                    diagnosis = result.get("diagnosis", {}) or {}
                    top = diagnosis.get("top_match")
                    category = (top or {}).get("category", "unknown")
                    pattern_id = (top or {}).get("pattern_id", "none")
                    confidence = (top or {}).get("confidence", 0)
                    print(
                        f"[baseline] iter STUCK: reason={result.get('reason')} "
                        f"elapsed={result.get('elapsed_seconds')}s "
                        f"diagnose: pattern={pattern_id} category={category} "
                        f"confidence={confidence}",
                        file=sys.stderr,
                    )
                    if category == "transient" and attempt + 1 < MAX_HEAL_ATTEMPTS:
                        # Autonomous retry: don't record this result, don't
                        # invoke self_heal, just kick off a fresh attempt on a
                        # new evidence subdir. The transient fix is "try again
                        # on a clean workspace copy" — no operator needed.
                        print(
                            f"[baseline] category=transient — auto-retry on "
                            f"fresh evidence subdir (attempt {attempt+2}/{MAX_HEAL_ATTEMPTS})",
                            file=sys.stderr,
                        )
                        continue
                    # Persistent / unknown / out-of-retries — escalate.
                    runs_by_fixture[fixture].append(result)
                    remaining = (len(fixtures) - f_idx) * args.n - (i + 1)
                    escalation = {
                        "type": "stuck_iter_escalation",
                        "fixture": fixture,
                        "iter": i + 1,
                        "evidence_dir": str(ev),
                        "dump_dir": result.get("dump_dir", ""),
                        "reason": result.get("reason"),
                        "elapsed_seconds": result.get("elapsed_seconds"),
                        "diagnose_verdict": diagnosis.get("verdict"),
                        "top_match": top,
                        "category": category,
                        "remaining_iters_skipped": remaining,
                        "proposed_questions": _stuck_proposed_questions(
                            pattern_id, category, top
                        ),
                    }
                    print("SELF_HEAL_ESCALATION " + json.dumps(escalation),
                          file=sys.stderr)
                    # Persist to evidence_root for deterministic post-baseline
                    # discovery. SKILL.md Hard Rule 14: the calling agent MUST
                    # check this file after baseline exits; if present, invoke
                    # AskUserQuestion with proposed_questions BEFORE any other
                    # action. Avoids the "operator types 'check status'"
                    # round-trip seen in 2026-05-24 A1 runs.
                    try:
                        escalation_file = evidence_root / "SELF_HEAL_ESCALATION.json"
                        escalation_file.write_text(json.dumps(escalation, indent=2))
                        print(f"[baseline] escalation persisted: {escalation_file}",
                              file=sys.stderr)
                    except OSError:
                        pass  # best-effort; stderr marker is canonical source
                    print(
                        f"[baseline] ABORT — fixture={fixture} iter={i+1}/{args.n} "
                        f"stuck after {attempt+1} attempt(s). category={category!r}. "
                        f"Saved ~{remaining} more iters. Calling agent should "
                        f"parse SELF_HEAL_ESCALATION.json in evidence-root and "
                        f"surface via AskUserQuestion, OR extend pattern catalog "
                        f"at .claude/skills/autoresearch/scripts/diagnose_hang.py "
                        f"+ KNOWN_PATTERNS.md, OR re-run with "
                        f"--allow-imperfect-iter if flake is acceptable.",
                        file=sys.stderr,
                    )
                    aborted = True
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

                # When self_heal returned structured escalation, surface the
                # proposed_questions and confidence so the calling agent can
                # decide whether to apply a candidate fix, extend the catalog,
                # or escalate to operator via AskUserQuestion — instead of
                # forcing a blind abort.
                escalation = {
                    "type": "self_heal_escalation",
                    "fixture": fixture,
                    "iter": i + 1,
                    "evidence_dir": str(ev),
                    "pattern": heal.get("pattern"),
                    "confidence": heal.get("confidence", "low"),
                    "diagnosis": heal.get("diagnosis", heal.get("detail", "")),
                    "evidence": heal.get("evidence", []),
                    "proposed_questions": heal.get("proposed_questions", []),
                    "inspect_files": hints,
                    "remaining_iters_skipped": remaining,
                }
                # Machine-readable marker on its own line so the calling agent
                # can parse it deterministically from baseline stdout/stderr.
                print("SELF_HEAL_ESCALATION " + json.dumps(escalation),
                      file=sys.stderr)
                # Persist to evidence_root for deterministic post-baseline
                # discovery (SKILL.md Hard Rule 14).
                try:
                    escalation_file = evidence_root / "SELF_HEAL_ESCALATION.json"
                    escalation_file.write_text(json.dumps(escalation, indent=2))
                    print(f"[baseline] escalation persisted: {escalation_file}",
                          file=sys.stderr)
                except OSError:
                    pass  # best-effort; stderr marker is canonical source
                print(
                    f"[baseline] ABORT — fixture={fixture} iter={i+1}/{args.n} "
                    f"imperfect after {attempt+1} self_heal attempt(s). "
                    f"Saved ~{remaining} more iters. "
                    f"Inspect: {'; '.join(hints)}. "
                    f"Pattern={heal.get('pattern')!r}, "
                    f"confidence={heal.get('confidence','low')!r}, "
                    f"{len(heal.get('proposed_questions', []))} proposed_question(s). "
                    f"Calling agent: parse SELF_HEAL_ESCALATION line above and "
                    f"surface via AskUserQuestion, OR extend self_heal pattern "
                    f"catalog at .claude/skills/autoresearch/scripts/self_heal.py, "
                    f"OR re-run with --allow-imperfect-iter if flake is acceptable.",
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
    p.add_argument(
        "--iter-wall-clock-seconds", type=int,
        default=DEFAULT_ITER_WALL_CLOCK_SECONDS,
        help=(
            "Per-iter wall-clock budget. If exceeded, baseline kills the run.py + "
            "Builder for this iter and invokes diagnose_hang to route remediation. "
            "Default: 1800s (30 min). Hang_watchdog's WAL-mtime check (180s) usually "
            "fires first; this is the safety net for cases where Builder is 'active' "
            "but not making progress."
        ),
    )
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())
