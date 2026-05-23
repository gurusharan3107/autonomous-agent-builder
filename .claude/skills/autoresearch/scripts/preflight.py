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
import urllib.error
import urllib.request
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
    "scripts/autoresearch/extract_context_breakdown.py",
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
        return Check(name, "pass", f"importable")
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
                 fix=f"free the ports or pass --port-base in baseline.py")


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


def check_docker_jaeger() -> Check:
    docker = shutil.which("docker")
    if not docker:
        return Check("docker + Jaeger (optional)", "warn",
                     "docker not on PATH — Jaeger UI unavailable; Path A file-OTEL still works",
                     fix="install docker (one-time): curl -fsSL https://get.docker.com | sudo sh; "
                         "sudo usermod -aG docker $USER; sudo chmod 666 /var/run/docker.sock")
    # docker info distinguishes "daemon down" from "no socket access"
    info_proc = subprocess.run([docker, "info"], capture_output=True, timeout=5)
    if info_proc.returncode != 0:
        err = info_proc.stderr.decode("utf-8", errors="replace").lower()
        if "permission denied" in err or "cannot connect" in err:
            return Check("docker + Jaeger (optional)", "warn", "docker socket permission denied",
                         fix="sudo usermod -aG docker $USER && sudo chmod 666 /var/run/docker.sock; "
                             "then restart shell")
        return Check("docker + Jaeger (optional)", "warn", "docker daemon unreachable",
                     fix="sudo service docker start  (or: sudo systemctl start docker)")
    try:
        out = subprocess.check_output(
            [docker, "ps", "--filter", "name=autoresearch-jaeger", "--format", "{{.Status}}"],
            stderr=subprocess.DEVNULL, timeout=5,
        ).decode().strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return Check("docker + Jaeger (optional)", "warn", "docker daemon unreachable",
                     fix="sudo service docker start (Path A file-OTEL still works without Jaeger)")
    if not out:
        return Check("docker + Jaeger (optional)", "warn",
                     "docker reachable; Jaeger container not running",
                     fix="bash .claude/skills/autoresearch/scripts/bootstrap.sh")
    # Container exists — verify it's actually reachable on the host, not just
    # "up" inside its namespace. WSL2 bridge networking has been known to drop
    # port forwarding even when the container is healthy from docker's view.
    ui_ok = _http_reachable("http://127.0.0.1:16686", expected_prefixes=("200", "302"))
    otlp_ok = _http_reachable("http://127.0.0.1:4318/v1/traces",
                              expected_prefixes=("200", "400", "415"), method="POST",
                              body=b"{}", content_type="application/json")
    if ui_ok and otlp_ok:
        return Check("docker + Jaeger", "pass",
                     f"container {out}; UI :16686 + OTLP :4318 reachable")
    return Check("docker + Jaeger", "warn",
                 f"container {out} but endpoints unreachable "
                 f"(UI:{'✓' if ui_ok else '✗'} OTLP:{'✓' if otlp_ok else '✗'})",
                 fix="docker logs autoresearch-jaeger; bootstrap.sh restarts with host networking")


def _http_reachable(url: str, *, expected_prefixes: tuple[str, ...] = ("200",),
                    method: str = "GET", body: bytes | None = None,
                    content_type: str | None = None, timeout: float = 3.0) -> bool:
    """Best-effort reachability probe. Returns True iff a response arrived with
    an HTTP status in `expected_prefixes` (accepts e.g. 400/415 as 'server is
    there, just rejected our payload')."""
    try:
        req = urllib.request.Request(url, method=method, data=body)
        if content_type:
            req.add_header("Content-Type", content_type)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return any(str(resp.status).startswith(p) for p in expected_prefixes)
    except urllib.error.HTTPError as e:
        return any(str(e.code).startswith(p) for p in expected_prefixes)
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def check_otel_port_holders() -> Check:
    """Like check_ports() but classifies holders. Builder processes blocking
    OTEL ports are auto-fixable via bootstrap.sh --auto-free-ports; other
    listeners need operator action."""
    held: list[tuple[int, str, str]] = []  # (port, pid, cmd)
    for port in (4317, 4318, 16686):
        if check_port_free(port):
            continue
        try:
            out = subprocess.check_output(
                ["ss", "-tlnp"], stderr=subprocess.DEVNULL, timeout=3
            ).decode()
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            held.append((port, "?", "?"))
            continue
        for line in out.splitlines():
            if f":{port} " in line or f":{port}\t" in line:
                import re as _re
                pid_m = _re.search(r"pid=(\d+)", line)
                cmd_m = _re.search(r'users:\(\("([^"]+)"', line)
                held.append((port, pid_m.group(1) if pid_m else "?",
                             cmd_m.group(1) if cmd_m else "?"))
                break
    if not held:
        return Check("OTEL ports (4317/4318/16686)", "pass", "all free")
    # If Jaeger container is running, attribute "?" holders to it (ss -tlnp
    # can't see inside Docker namespaces without sudo, so the holder appears
    # as unknown — but if we know Jaeger is up, that's the expected source).
    jaeger_up = _jaeger_container_running()
    builder_holders = [(p, pid, cmd) for p, pid, cmd in held if cmd == "builder"]
    other_holders = [
        (p, pid, cmd) for p, pid, cmd in held
        if cmd not in ("builder", "jaeger", "all-in-one")
        and not (jaeger_up and cmd == "?")
    ]
    detail = "; ".join(f":{p}=pid {pid} ({cmd})" for _, _, _ in [(0, 0, 0)] for p, pid, cmd in held)
    if builder_holders and not other_holders:
        return Check("OTEL ports (4317/4318/16686)", "warn",
                     f"held by builder process(es): {detail}",
                     fix="bash .claude/skills/autoresearch/scripts/bootstrap.sh --auto-free-ports")
    if other_holders:
        return Check("OTEL ports (4317/4318/16686)", "fail",
                     f"held by non-builder process(es): {detail}",
                     fix="stop the listed process(es) manually before running the loop")
    # All holders attributable to Jaeger (or look like it) — that's the
    # expected steady state after bootstrap.
    return Check("OTEL ports (4317/4318/16686)", "pass",
                 f"held by Jaeger container: {detail}" if jaeger_up
                 else f"held but appears intentional: {detail}")


def _jaeger_container_running() -> bool:
    docker = shutil.which("docker")
    if not docker:
        return False
    try:
        out = subprocess.check_output(
            [docker, "ps", "--filter", "name=autoresearch-jaeger", "--format", "{{.Names}}"],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode().strip()
        return bool(out)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


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
        check_otel_port_holders(),
        check_tmp_disk_space(),
        check_docker_jaeger(),
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
    if recipe in (2, 3):
        seed = check_path_exists("seed snapshot (required for recipe)", SEED_DST, hard=True,
                                  kind="immutable snapshot")
        baseline = check_baseline_summary(recipe, allow_unstable=allow_unstable)
        # Iterate lanes also need seed pytest-collect + git-clean — they ride on
        # the same fragile feature_check path baseline does.
        return [check_no_inflight_lane(), seed, baseline,
                check_tsv_schema_alignment(), check_workspace_stack(),
                check_seed_pytest_collect(), check_seed_git_clean()]
    if recipe == 1:
        # Recipe 1 produces the seed and baseline; we still want to catch the
        # schema-drift and stack-mismatch bugs early, before a 10-minute run
        # discovers them the painful way. P17 (2026-05-23) added the
        # pytest-collect + git-clean probes after a $5 / 1.5h doomed-iter burn
        # caused by seed .venv missing jinja2 + uncommitted requirements.txt.
        return [check_no_inflight_lane(), check_baseline_summary(1),
                check_tsv_schema_alignment(), check_workspace_stack(),
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
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return Check("seed git clean", "warn",
                     f"git status failed: {type(exc).__name__}", fix="")
    if r.returncode != 0:
        return Check("seed git clean", "warn",
                     f"git status returned {r.returncode}", fix="")
    # Filter to non-.venv tracked-file changes — .venv churn (.pyc etc.) is noise
    dirty = [ln for ln in r.stdout.splitlines()
             if ln and not ln[3:].startswith(".venv/")
             and not ln[3:].startswith(".claude/")]
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
