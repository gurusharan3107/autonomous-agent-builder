#!/usr/bin/env python3
"""Autoresearch loop preflight validator — bundled with the autoresearch skill.

Verifies every infra dependency listed in SKILL.md before any recipe runs.
Exits 0 if all hard checks pass (warnings OK), non-zero if any hard check fails.
Output is human-readable by default, machine-readable JSON with --json.

Usage:
  python3 .claude/skills/autoresearch/scripts/preflight.py             # all checks, human output
  python3 .claude/skills/autoresearch/scripts/preflight.py --json      # all checks, JSON
  python3 .claude/skills/autoresearch/scripts/preflight.py --recipe 2  # gate on Recipe 2 prereqs
  python3 .claude/skills/autoresearch/scripts/preflight.py --recipe 3  # gate on Recipe 3 prereqs

Recipes (per SKILL.md):
  1 = first-time activation (just hard checks)
  2 = one optimization iteration (needs .seed + baseline_runs_summary.json)
  3 = compare candidate (needs baseline_runs_summary.json + a candidate run_id)
  4 = add a new optimize idea (just hard checks)
  5 = recover from stuck iteration (just hard checks)
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field

REPO = pathlib.Path(__file__).resolve().parents[4]  # .claude/skills/autoresearch/scripts/preflight.py → repo root
SEED_DST = pathlib.Path("/home/gurusharangupta/.seed/devpulse")
SEED_SRC = pathlib.Path(os.path.expanduser("~/Builder-Workspace/devpulse"))
PORT_RANGE = range(9876, 9881)
TMP_MIN_FREE_GB = 5

REQUIRED_CONTRACTS = [
    "docs/autoresearch/README.md",
    "docs/autoresearch/OPTIMIZE.md",
    "docs/autoresearch/OPTIMIZE_IDEAS.md",
    "docs/autoresearch/fixtures.md",
    "docs/autoresearch/baseline_variance.md",
]
REQUIRED_HARNESS = [
    "scripts/autoresearch/run.py",
    "scripts/autoresearch/baseline.py",
    "scripts/autoresearch/compare.py",
    "scripts/autoresearch/loop.py",
    "scripts/autoresearch/setup_seed.sh",
]


@dataclass
class Check:
    name: str
    status: str  # "pass" | "warn" | "fail"
    detail: str
    fix: str = ""


@dataclass
class Report:
    recipe: int | None
    hard: list[Check] = field(default_factory=list)
    soft: list[Check] = field(default_factory=list)
    recipe_specific: list[Check] = field(default_factory=list)

    @property
    def overall(self) -> str:
        if any(c.status == "fail" for c in self.hard + self.recipe_specific):
            return "fail"
        if any(c.status == "warn" for c in self.hard + self.soft + self.recipe_specific):
            return "warn"
        return "pass"


def check_command(name: str, cmd: str) -> Check:
    path = shutil.which(cmd)
    if path:
        return Check(name, "pass", f"found at {path}")
    return Check(name, "fail", f"{cmd!r} not on PATH", fix=f"install {cmd} and ensure it's on PATH")


def check_python_module(name: str, module: str, hard: bool) -> Check:
    try:
        __import__(module)
        return Check(name, "pass", "importable")
    except ImportError:
        status = "fail" if hard else "warn"
        fix = f"pip install {module}"
        if not hard:
            fix += "  # optional — without it the loop uses a fallback"
        return Check(name, status, "not importable", fix=fix)


def check_path_exists(name: str, path: pathlib.Path, hard: bool, *, kind: str = "directory") -> Check:
    if path.exists():
        return Check(name, "pass", f"{kind} at {path}")
    status = "fail" if hard else "warn"
    return Check(name, status, f"{kind} missing at {path}",
                 fix=f"create {path} (see SKILL.md Recipe 1 / setup_seed.sh)")


def check_repo_files(name: str, relative: list[str]) -> Check:
    missing = [r for r in relative if not (REPO / r).exists()]
    if not missing:
        return Check(name, "pass", f"all {len(relative)} files present")
    return Check(name, "fail", f"{len(missing)} missing: {', '.join(missing[:3])}{'…' if len(missing) > 3 else ''}",
                 fix="restore from git or re-run skill installation")


def check_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def check_ports() -> Check:
    busy = [p for p in PORT_RANGE if not check_port_free(p)]
    if not busy:
        return Check("ports 9876–9880 free", "pass", "all free for parallel baseline runs")
    status = "warn" if len(busy) < len(PORT_RANGE) else "fail"
    return Check("ports 9876–9880 free", status,
                 f"{len(busy)}/{len(PORT_RANGE)} in use: {busy}",
                 fix="free the ports or pass --port-base in baseline.py")


def check_tmp_disk_space() -> Check:
    try:
        usage = shutil.disk_usage("/tmp")
        free_gb = usage.free / (1024 ** 3)
        if free_gb >= TMP_MIN_FREE_GB:
            return Check("/tmp disk space", "pass", f"{free_gb:.1f} GB free (need ≥{TMP_MIN_FREE_GB})")
        return Check("/tmp disk space", "warn", f"{free_gb:.1f} GB free (need ≥{TMP_MIN_FREE_GB})",
                     fix="free disk space; long N=5 baseline runs may fill /tmp/autoresearch/<run-id>/raw_bodies/")
    except OSError as exc:
        return Check("/tmp disk space", "warn", f"could not stat /tmp ({exc})")


def check_git_state() -> Check:
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(REPO), stderr=subprocess.DEVNULL
        ).decode().strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=str(REPO), stderr=subprocess.DEVNULL
        ).decode()
        dirty = bool(status.strip())
        if branch in ("main", "master") and dirty:
            return Check("git state", "warn",
                         f"on {branch} with uncommitted changes — loop.py expects clean main",
                         fix="commit or stash before starting a baseline / iteration")
        return Check("git state", "pass", f"branch={branch} dirty={dirty}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Check("git state", "warn", "git unavailable or repo not initialized")


def check_baseline_summary(recipe: int, allow_unstable: bool = False) -> Check:
    path = REPO / "docs/autoresearch/baseline_runs_summary.json"
    if not path.exists():
        if recipe in (2, 3):
            return Check("baseline_runs_summary.json", "fail",
                         "missing — compare.py needs σ floor",
                         fix="run Recipe 1: python3 scripts/autoresearch/baseline.py --fixtures A,B,C,D,E --n 5")
        return Check("baseline_runs_summary.json", "pass", "not yet produced (OK for Recipe 1)")
    try:
        data = json.loads(path.read_text())
        # Treat both "unstable" rows and missing (not_measured) fixtures as
        # not-stable for Iterate / Compare. promotion order is A→E; a missing
        # fixture in the summary means render_iterations.py surfaces it as
        # not_measured but loop.py will still hit a wall during A→E promotion.
        all_fixtures = ["A", "B", "C", "D", "E"]
        present_status = {f: (data.get(f) or {}).get("status") for f in all_fixtures}
        not_stable = [f for f in all_fixtures if present_status[f] != "stable"]
        if not_stable:
            # Iterate-lane Hard Rule 8 ("Wins must promote A→E before merge")
            # and lanes/iterate.md preflight Hard Requirements declare every
            # fixture status=stable as a HARD precondition. Without it, any
            # real fixture-A keep is guaranteed discard at A→E promotion
            # because compare.py has no σ-floor for the next fixture. fail
            # by default; require --allow-unstable-promotion to opt in.
            severity = "warn" if allow_unstable or recipe not in (2, 3) else "fail"
            detail = f"present but {len(not_stable)}/{len(all_fixtures)} fixture(s) not stable: {not_stable}"
            fix = (
                "re-run baseline for those fixtures: "
                f"python3 scripts/autoresearch/baseline.py --fixtures {','.join(not_stable)} --n 5"
            )
            if allow_unstable:
                fix += "  (currently degraded — --allow-unstable-promotion override active)"
            return Check("baseline_runs_summary.json", severity, detail, fix=fix)
        return Check("baseline_runs_summary.json", "pass",
                     f"present, {len(data)} fixtures stable")
    except (OSError, json.JSONDecodeError) as exc:
        return Check("baseline_runs_summary.json", "warn", f"present but unreadable: {exc}")


def gather_hard_checks() -> list[Check]:
    return [
        check_command("builder CLI", "builder"),
        check_command("npm", "npm"),
        check_command("python3", "python3"),
        check_command("git", "git"),
        check_python_module("requests module", "requests", hard=True),
        check_path_exists("seed source", SEED_SRC, hard=True, kind="devpulse workspace"),
        check_repo_files("autoresearch contracts (docs/)", REQUIRED_CONTRACTS),
        check_repo_files("autoresearch harness (scripts/)", REQUIRED_HARNESS),
        check_hang_watchdog_present(),
    ]


def check_py_spy_optional() -> Check:
    """py-spy is optional — hang_watchdog.py works without it but dumps
    are richer when it's installed (Python stack traces of the stuck builder)."""
    path = shutil.which("py-spy")
    if path:
        return Check("py-spy CLI (optional)", "pass", f"found at {path}")
    return Check(
        "py-spy CLI (optional)",
        "warn",
        "not on PATH; hang_watchdog dumps will lack Python stacks",
        fix="pip install --user py-spy (with --break-system-packages on PEP668 systems)",
    )


def check_hang_watchdog_present() -> Check:
    """The hang_watchdog script is part of the skill — verify it ships
    alongside the other bundled scripts so a fresh clone is self-sufficient."""
    path = pathlib.Path(__file__).resolve().parent / "hang_watchdog.py"
    if path.is_file():
        return Check("hang_watchdog.py", "pass", f"present at {path}")
    return Check(
        "hang_watchdog.py",
        "fail",
        f"missing from {path.parent}",
        fix="re-clone the skill or restore the file from version control",
    )


def gather_soft_checks() -> list[Check]:
    return [
        check_python_module("tiktoken module (optional)", "tiktoken", hard=False),
        check_py_spy_optional(),
        check_path_exists("seed snapshot", SEED_DST, hard=False, kind="immutable snapshot"),
        check_ports(),
        check_tmp_disk_space(),
        check_git_state(),
    ]


def check_no_inflight_lane() -> Check:
    """Hard-fail if another `baseline.py` or `loop.py` is already running.

    Without this, a second lane started in parallel would collide on:
    (a) `baseline_runs.tsv` / `optimize_results.tsv` append races,
    (b) `/tmp/devpulse-<uuid>/` workspace allocation,
    (c) builder server ports (run.py picks via --port; baseline.py walks
        9876–9885), and most importantly,
    (d) the operator's mental model — TSV rows from two lanes interleaved
        without a clean "this run is which lane" marker.

    The 2026-05-23 session footgun: a baseline.py from a prior session was
    still running when /start surveyed file/commit state and reported "ready
    to run baseline." The lane skill must own its own producer-process
    awareness; that's why this check is here and not in /start.
    """
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid,etime,args"], text=True, timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return Check("autoresearch lane processes", "warn",
                     "could not run `ps` to check for in-flight lanes",
                     fix="manually verify no baseline.py/loop.py is running before proceeding")
    lanes = []
    for line in out.splitlines()[1:]:
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        pid, etime, args = parts
        # Avoid matching our own preflight invocation when piped through grep wrappers
        if "preflight.py" in args or "lane_status.py" in args:
            continue
        if "python" in args and ("baseline.py" in args or "loop.py" in args):
            lanes.append((pid, etime, args))
    if not lanes:
        return Check("autoresearch lane processes", "pass",
                     "no in-flight baseline.py / loop.py")
    summary = "; ".join(f"PID {p} ({et}): {a[:80]}" for p, et, a in lanes[:3])
    return Check(
        "autoresearch lane processes", "fail",
        f"{len(lanes)} lane process(es) already running — {summary}",
        fix=(
            "another lane is in flight; run "
            "`python3 .claude/skills/autoresearch/scripts/lane_status.py --human` for progress, "
            "then either wait or `kill -TERM <PID>` (graceful) before starting a new lane"
        ),
    )


def gather_recipe_checks(recipe: int, allow_unstable: bool = False) -> list[Check]:
    """Recipe-specific preflight. The substrate identity contract
    (seed_manifest.json) is checked by `check_seed_manifest_conformance`
    which subsumes the older ad-hoc seed checks. The legacy checks
    (`check_seed_pytest_collect`, `check_seed_git_clean`) are retained as
    defense-in-depth — they may catch failure shapes the manifest doesn't
    yet declare. `check_harness_contracts` validates the Builder CLI/API
    output shapes the harness consumes (P1–P15 class)."""
    if recipe in (2, 3):
        seed = check_path_exists("seed snapshot (required for recipe)", SEED_DST, hard=True,
                                  kind="immutable snapshot")
        baseline = check_baseline_summary(recipe, allow_unstable=allow_unstable)
        return [check_no_inflight_lane(), seed, baseline,
                check_tsv_schema_alignment(), check_workspace_stack(),
                check_seed_manifest_conformance(),
                check_harness_contracts(),
                check_agent_registry_contract(),
                # Legacy probes — defense-in-depth alongside manifest verifier
                check_seed_pytest_collect(), check_seed_git_clean()]
    if recipe == 1:
        return [check_no_inflight_lane(), check_baseline_summary(1),
                check_tsv_schema_alignment(), check_workspace_stack(),
                check_seed_manifest_conformance(),
                check_harness_contracts(),
                check_agent_registry_contract(),
                check_seed_pytest_collect(), check_seed_git_clean()]
    return []


def check_tsv_schema_alignment() -> Check:
    """Verify run.py's SESSION_HEADERS exactly matches the existing
    optimize_results.tsv + baseline_runs.tsv header. Drift here causes silent
    data corruption — we hit this in the v1 fixture-A test where the writer
    skipped 6 columns and shifted every value left, making downstream gates
    parse 'gate_pass_rate' from the 'noncached_plus_output_tokens' column."""
    run_py = REPO / "scripts" / "autoresearch" / "run.py"
    tsvs = [REPO / "docs" / "autoresearch" / "optimize_results.tsv",
            REPO / "docs" / "autoresearch" / "baseline_runs.tsv"]
    if not run_py.exists():
        return Check("TSV header alignment", "warn", "run.py not found — cannot verify alignment")
    # Pull SESSION_HEADERS by importing the module
    try:
        spec = __import__("importlib.util", fromlist=["spec_from_file_location"]).spec_from_file_location(
            "_run_py", str(run_py))
        mod = __import__("importlib.util", fromlist=["module_from_spec"]).module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        writer_headers = list(mod.SESSION_HEADERS)
    except Exception as exc:
        return Check("TSV header alignment", "warn",
                     f"could not load SESSION_HEADERS from run.py ({type(exc).__name__})")
    mismatches: list[str] = []
    for tsv in tsvs:
        if not tsv.exists():
            continue
        try:
            tsv_header = tsv.read_text().splitlines()[0].split("\t")
        except (OSError, IndexError):
            continue
        if tsv_header != writer_headers:
            extra_in_tsv = set(tsv_header) - set(writer_headers)
            extra_in_writer = set(writer_headers) - set(tsv_header)
            detail = []
            if extra_in_tsv:
                detail.append(f"TSV has extras: {sorted(extra_in_tsv)}")
            if extra_in_writer:
                detail.append(f"writer has extras: {sorted(extra_in_writer)}")
            mismatches.append(f"{tsv.name}: {'; '.join(detail) or 'order differs'}")
    if mismatches:
        return Check("TSV header alignment", "fail",
                     "; ".join(mismatches),
                     fix="align run.py:SESSION_HEADERS to match the TSV header exactly "
                         "(or regenerate the TSV from the writer schema)")
    return Check("TSV header alignment", "pass",
                 f"writer ({len(writer_headers)} cols) matches all checked TSVs")


def check_workspace_stack() -> Check:
    """Confirm the seed has a recognizable app stack so `run_feature_check()`
    won't silently fail. We hit this in the v1 test where devpulse turned out
    to be a Python app but run.py assumed Node — npm couldn't find package.json
    and feature_correct was always False."""
    if not SEED_DST.exists():
        return Check("workspace stack detection", "warn",
                     "seed missing — stack detection deferred to first run",
                     fix="bash scripts/autoresearch/setup_seed.sh")
    app = SEED_DST / "app"
    candidates: list[tuple[str, pathlib.Path]] = [
        ("Node (package.json)", app / "package.json"),
        ("Node (root package.json)", SEED_DST / "package.json"),
        ("Python (pyproject.toml)", SEED_DST / "pyproject.toml"),
        ("Python (app/pyproject.toml)", app / "pyproject.toml"),
    ]
    found = [name for name, p in candidates if p.exists()]
    if not found:
        return Check("workspace stack detection", "fail",
                     "no recognizable stack (no package.json or pyproject.toml found)",
                     fix="confirm seed source has a package.json or pyproject.toml; "
                         "extend run_feature_check() in scripts/autoresearch/run.py "
                         "if the stack is something else (Go/Rust/etc.)")
    return Check("workspace stack detection", "pass",
                 f"stack(s) found: {', '.join(found)}")


def check_seed_pytest_collect() -> Check:
    """P17 (2026-05-23): actually run pytest --collect-only against the seed.

    Why this exists: 2026-05-23 N=5 baseline burned 3 doomed iters of fixture B
    (~$3-5, ~1.5h wallclock) before the operator noticed every iter had
    feature_correct=False. Root cause was seed .venv missing jinja2 and
    pytest-asyncio — pytest collection errored with ModuleNotFoundError. The
    harness's `pip install -r requirements.txt` in run_feature_check was
    supposed to fix it but silently didn't (now logged to evidence_dir/
    feature_check.log per the same patch). This preflight catches it for $0
    by running the same pytest invocation against the seed itself, before
    a single iter spends any tokens.
    """
    if not SEED_DST.exists():
        return Check("seed pytest collects", "warn",
                     "seed missing — collect check deferred",
                     fix="bash scripts/autoresearch/setup_seed.sh")
    venv_py = SEED_DST / ".venv" / "bin" / "python"
    tests_dir = SEED_DST / "tests"
    if not venv_py.exists() or not tests_dir.exists():
        return Check("seed pytest collects", "warn",
                     "seed has no .venv or tests/ — non-Python stack or first-run",
                     fix="")
    try:
        r = subprocess.run(
            [str(venv_py), "-m", "pytest", str(tests_dir), "--collect-only", "-q",
             "--ignore-glob=*playwright*", "--ignore-glob=*test_github*"],
            capture_output=True, text=True, timeout=60, cwd=str(SEED_DST),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return Check("seed pytest collects", "fail",
                     f"pytest --collect-only failed to start: {type(exc).__name__}",
                     fix="verify seed .venv is intact; run scripts/autoresearch/setup_seed.sh "
                         "to regenerate if corrupt")
    if r.returncode != 0:
        # Extract the first ModuleNotFoundError / ImportError / ERROR line for clarity
        tail = (r.stderr or r.stdout).strip().splitlines()
        signature = next((ln for ln in tail
                          if "ModuleNotFoundError" in ln or "ImportError" in ln
                          or ln.startswith("ERROR")), tail[-1] if tail else "unknown")
        return Check("seed pytest collects", "fail",
                     f"pytest collection errored: {signature[:200]}",
                     fix="install missing deps into the seed .venv: "
                         f"chmod -R u+w {SEED_DST} && "
                         f"{venv_py} -m pip install -r {SEED_DST}/requirements.txt && "
                         f"chmod -R a-w {SEED_DST}. "
                         "Then re-run this preflight.")
    return Check("seed pytest collects", "pass",
                 f"pytest --collect-only OK against {tests_dir.name}/")


def check_seed_manifest_conformance() -> Check:
    """Run seed_verify.py against the manifest. Single source of truth for
    substrate identity — subsumes ad-hoc checks (deps, db pollution,
    forbidden files, forbidden commit subjects). When this fails, self_heal
    can usually remediate deterministically (db wipe, file rm, dep install)
    or escalate model-backed (history pollution requires re-snapshot decision).
    """
    seed_verify = pathlib.Path(__file__).resolve().parent / "seed_verify.py"
    if not seed_verify.exists():
        return Check("seed manifest conformance", "warn",
                     f"seed_verify.py missing at {seed_verify}",
                     fix="restore the skill from version control")
    try:
        r = subprocess.run(
            [sys.executable, str(seed_verify), "--json"],
            capture_output=True, text=True, timeout=180,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return Check("seed manifest conformance", "warn",
                     f"seed_verify.py failed to run: {type(exc).__name__}",
                     fix="run manually: python3 .claude/skills/autoresearch/scripts/seed_verify.py")
    try:
        report = json.loads(r.stdout)
    except (ValueError, json.JSONDecodeError):
        # Subprocess crashed or wrote to stderr only; surface that so it's debuggable.
        err_tail = (r.stderr or "")[-300:]
        return Check("seed manifest conformance", "warn",
                     f"seed_verify.py produced non-JSON output (exit={r.returncode}); "
                     f"stderr tail: {err_tail}",
                     fix="run manually: python3 .claude/skills/autoresearch/scripts/seed_verify.py")
    overall = report.get("overall", "warn")
    if overall == "pass":
        n = len([f for f in report.get("findings", []) if f.get("status") == "pass"])
        return Check("seed manifest conformance", "pass",
                     f"all {n} substrate invariants satisfied")
    failures = [f for f in report.get("findings", []) if f.get("status") == "fail"]
    detail = "; ".join(f"{f['clause']}: {f.get('detail', '')[:80]}" for f in failures[:3])
    hint = "; ".join(set(f.get("remediation_hint", "") for f in failures
                          if f.get("remediation_hint")))[:300]
    return Check("seed manifest conformance",
                 "fail" if overall == "fail" else "warn",
                 f"{len(failures)} substrate violation(s): {detail}",
                 fix=f"run self_heal.py to auto-remediate where catalogued; "
                     f"escalate via AskUserQuestion for substrate-identity issues. "
                     f"Hints: {hint}" if hint else
                     "run python3 .claude/skills/autoresearch/scripts/seed_verify.py for details")


def check_agent_registry_contract() -> Check:
    """Run tests/test_agent_registry_contract.py — asserts every agent's
    declared tools have ToolSchema entries in _SDK_BUILTINS. P19 (autoresearch
    INSIGHTS Run #10 / 2026-05-24) cost ~$0.50 + 21 min wallclock to surface
    via a real baseline; this preflight catches the same class in <2s for $0.

    The harness invokes pytest as a subprocess (the test imports Builder
    modules, which the harness is forbidden from doing per Hard Rule 3).
    """
    test_file = REPO / "tests" / "test_agent_registry_contract.py"
    if not test_file.exists():
        return Check("agent registry contract", "warn",
                     f"test file missing at {test_file}",
                     fix="restore from version control")
    try:
        r = subprocess.run(
            ["python3", "-m", "pytest", str(test_file), "-q", "--no-header"],
            capture_output=True, text=True, timeout=60, cwd=str(REPO),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return Check("agent registry contract", "warn",
                     f"pytest invocation failed: {type(exc).__name__}",
                     fix="run manually: python3 -m pytest tests/test_agent_registry_contract.py")
    if r.returncode == 0:
        # Pull "N passed" from pytest output for a useful detail
        import re as _re
        m = _re.search(r"(\d+) passed", r.stdout)
        n = m.group(1) if m else "?"
        return Check("agent registry contract", "pass",
                     f"{n} parametric assertions passed — zero contract drift")
    # Test failure — surface the assertion messages for actionability
    failure_tail = "\n".join(
        ln for ln in (r.stdout or "").splitlines()
        if "AssertionError" in ln or "FAILED" in ln or "missing from" in ln
    )[:500]
    return Check("agent registry contract", "fail",
                 "agent.tools references missing schemas (P19-class)",
                 fix=f"Run `python3 -m pytest tests/test_agent_registry_contract.py -v` "
                     f"for details. Excerpt: {failure_tail[:300]}")


def check_harness_contracts() -> Check:
    """Run test_harness_contracts.py against Builder CLI surfaces. Catches
    output-shape drift before any iter burns tokens (covers P1–P15 class)."""
    script = pathlib.Path(__file__).resolve().parent / "test_harness_contracts.py"
    if not script.exists():
        return Check("harness ↔ builder contracts", "warn",
                     f"test_harness_contracts.py missing at {script}",
                     fix="restore the skill from version control")
    try:
        r = subprocess.run(
            [sys.executable, str(script), "--json"],
            capture_output=True, text=True, timeout=180,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return Check("harness ↔ builder contracts", "warn",
                     f"contract script failed to run: {type(exc).__name__} "
                     f"(may be slow when Builder is active on the workspace)",
                     fix="run manually: python3 .claude/skills/autoresearch/scripts/test_harness_contracts.py")
    try:
        report = json.loads(r.stdout)
    except (ValueError, json.JSONDecodeError):
        return Check("harness ↔ builder contracts", "warn",
                     f"non-JSON output: {r.stdout[:200]}", fix="")
    overall = report.get("overall", "warn")
    if overall == "pass":
        n = len([x for x in report.get("results", []) if x.get("status") == "pass"])
        return Check("harness ↔ builder contracts", "pass",
                     f"all {n} contract(s) match manifest declarations")
    fails = [x for x in report.get("results", []) if x.get("status") == "fail"]
    if not fails and overall == "warn":
        return Check("harness ↔ builder contracts", "warn",
                     "some contracts skipped (likely no sample session_id available)",
                     fix="")
    detail = "; ".join(f"{x['contract']}: {x.get('detail', '')[:80]}" for x in fails[:3])
    hints = "; ".join(set(x.get("remediation_hint", "") for x in fails
                           if x.get("remediation_hint")))[:300]
    return Check("harness ↔ builder contracts", "fail",
                 f"{len(fails)} contract violation(s): {detail}",
                 fix=hints or "update harness consumers in scripts/autoresearch/run.py")


def check_seed_git_clean() -> Check:
    """P17 (2026-05-23): seed's git status must be clean (HEAD == working tree).

    Why this exists: 2026-05-23 we discovered the seed had `M requirements.txt`
    — pytest-asyncio was added to working-tree requirements.txt but never
    committed. Any Builder operation that runs `git checkout` or `git reset`
    inside a task workspace reverts requirements.txt to HEAD (which is missing
    pytest-asyncio), so subsequent pip install --requirements gets the wrong
    dep list. Symptom: feature_correct=False with no surfaced reason. This
    preflight catches the divergence before the baseline burns iters.
    """
    if not SEED_DST.exists():
        return Check("seed git clean", "warn",
                     "seed missing — git-clean check deferred",
                     fix="")
    if not (SEED_DST / ".git").exists():
        return Check("seed git clean", "warn",
                     "seed is not a git repo — divergence check skipped",
                     fix="")
    try:
        r = subprocess.run(
            ["git", "-C", str(SEED_DST), "status", "--porcelain"],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return Check("seed git clean", "warn",
                     f"git status failed: {type(exc).__name__} "
                     f"(seed may be under heavy I/O — Builder running?)",
                     fix="retry when seed I/O is quiet")
    if r.returncode != 0:
        return Check("seed git clean", "warn",
                     f"git status returned {r.returncode}", fix="")
    # Filter noise: .venv churn, .claude workspace, and __pycache__/*.pyc
    # (bytecode regenerates per pytest run; not part of substrate identity).
    # Matches seed_verify's filter for consistency.
    dirty = [ln for ln in r.stdout.splitlines()
             if ln
             and not ln[3:].startswith(".venv/")
             and not ln[3:].startswith(".claude/")
             and "__pycache__/" not in ln[3:]
             and not ln[3:].endswith(".pyc")]
    if dirty:
        return Check("seed git clean", "fail",
                     f"{len(dirty)} tracked file(s) diverge from HEAD: " +
                     ", ".join(ln.strip() for ln in dirty[:3]) +
                     ("..." if len(dirty) > 3 else ""),
                     fix=f"commit the divergence so HEAD == working tree: "
                         f"chmod -R u+w {SEED_DST} && "
                         f"git -C {SEED_DST} add <files> && "
                         f"git -C {SEED_DST} commit -m '...' && "
                         f"chmod -R a-w {SEED_DST}")
    return Check("seed git clean", "pass",
                 "HEAD == working tree (no tracked-file divergence)")


def format_human(report: Report) -> str:
    lines = []
    glyph = {"pass": "✓", "warn": "⚠", "fail": "✗"}

    def render(title: str, checks: list[Check]) -> None:
        if not checks:
            return
        lines.append(f"\n{title}")
        lines.append("-" * len(title))
        for c in checks:
            lines.append(f"  [{glyph[c.status]}] {c.name}: {c.detail}")
            if c.status != "pass" and c.fix:
                lines.append(f"      fix: {c.fix}")

    lines.append(f"autoresearch preflight — overall: {glyph[report.overall]} {report.overall.upper()}")
    if report.recipe is not None:
        lines.append(f"(gated for recipe {report.recipe})")
    render("Hard requirements", report.hard)
    if report.recipe_specific:
        render(f"Recipe {report.recipe} requirements", report.recipe_specific)
    render("Soft / optional", report.soft)
    lines.append("")
    return "\n".join(lines)


def format_json(report: Report) -> str:
    def serialize(check: Check) -> dict:
        return {"name": check.name, "status": check.status, "detail": check.detail, "fix": check.fix}

    return json.dumps({
        "overall": report.overall,
        "recipe": report.recipe,
        "hard": [serialize(c) for c in report.hard],
        "recipe_specific": [serialize(c) for c in report.recipe_specific],
        "soft": [serialize(c) for c in report.soft],
    }, indent=2)


def main() -> int:
    args = parse_args()
    report = Report(recipe=args.recipe)
    report.hard = gather_hard_checks()
    report.soft = gather_soft_checks()
    if args.recipe is not None:
        report.recipe_specific = gather_recipe_checks(args.recipe, allow_unstable=args.allow_unstable_promotion)

    out = format_json(report) if args.json else format_human(report)
    print(out)
    return 0 if report.overall != "fail" else 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Autoresearch loop preflight validator (bundled with skill).")
    p.add_argument("--recipe", type=int, choices=[1, 2, 3, 4, 5], default=None,
                   help="Gate against a specific recipe's prereqs (see SKILL.md)")
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    p.add_argument(
        "--allow-unstable-promotion",
        action="store_true",
        help=(
            "Downgrade the 'all fixtures status=stable' check from fail to warn. "
            "Use only when knowingly iterating against a partial baseline; real "
            "keeps cannot ship in this mode (A→E promotion will discard)."
        ),
    )
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())
