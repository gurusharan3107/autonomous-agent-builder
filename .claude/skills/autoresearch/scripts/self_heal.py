#!/usr/bin/env python3
"""Self-healing diagnostic + remediation for autoresearch baseline failures.

Triggered by `baseline.py` when an iter's strict per-iter sanity gate fires.
Parses `evidence_dir/feature_check.log` (and seed state) for known failure
signatures, applies the mechanical fix, returns a JSON record describing
what happened. Designed to be cheap (no LLM calls), safe (only well-known
patterns auto-apply), and observable (every action logged).

Patterns:
  - missing-python-module: pytest collection error
      "ModuleNotFoundError: No module named 'X'" → pip-install X into seed .venv
  - seed-uncommitted-requirements: seed has uncommitted requirements.txt
      → commit the seed working-tree change so HEAD == working tree
  - missing-pytest-plugin: warning surfaces an unknown pytest config option
      → pip-install the plugin that owns that option

Anything outside the catalog returns `applied=False`, leaving the operator
to investigate. False fixes are worse than no fix.

Usage (from baseline.py):
    res = run_self_heal(evidence_dir, seed_dir)
    if res["applied"]:
        # retry the iter
    else:
        # abort, surface res["detail"] to operator

Usage (CLI):
    python3 scripts/autoresearch/self_heal.py --evidence-dir DIR --seed-dir DIR
    # exit 0 if fix applied, 1 if no match, 2 on error
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from typing import Callable

# Map pytest config-option names to the plugin packages that own them.
# Extend as patterns surface.
PYTEST_PLUGIN_FOR_OPTION = {
    "asyncio_mode": "pytest-asyncio",
    "anyio_mode": "anyio",
}


def _make_seed_writable(seed_dir: pathlib.Path) -> bool:
    try:
        subprocess.run(["chmod", "-R", "u+w", str(seed_dir)], check=True, timeout=10)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def _restore_seed_readonly(seed_dir: pathlib.Path) -> None:
    subprocess.run(["chmod", "-R", "a-w", str(seed_dir)], check=False, timeout=10)


def _pip_install_into_seed(seed_dir: pathlib.Path, packages: list[str]) -> tuple[bool, str]:
    """Install packages into seed `.venv` with chmod dance. Returns (ok, log)."""
    if not _make_seed_writable(seed_dir):
        return False, f"chmod -R u+w {seed_dir} failed"
    try:
        venv_py = seed_dir / ".venv" / "bin" / "python"
        if not venv_py.exists():
            return False, f"seed venv missing at {venv_py}"
        r = subprocess.run(
            [str(venv_py), "-m", "pip", "install", "-q", *packages],
            capture_output=True, text=True, timeout=180,
        )
        if r.returncode != 0:
            return False, f"pip install failed: {(r.stderr or r.stdout)[:400]}"
        return True, f"pip-installed {packages} into seed .venv"
    finally:
        _restore_seed_readonly(seed_dir)


def fix_missing_python_module(
    seed_dir: pathlib.Path, module: str
) -> dict:
    """Install the missing module into seed `.venv`. PyPI name often equals
    import name; map known aliases."""
    pypi_name = {
        "jinja2": "jinja2",
        "pytest_asyncio": "pytest-asyncio",
        # extend as patterns surface
    }.get(module, module)
    ok, log = _pip_install_into_seed(seed_dir, [pypi_name])
    return {
        "applied": ok,
        "pattern": "missing-python-module",
        "module": module,
        "package": pypi_name,
        "detail": log,
    }


def fix_missing_pytest_plugin(
    seed_dir: pathlib.Path, option: str
) -> dict:
    plugin = PYTEST_PLUGIN_FOR_OPTION.get(option)
    if not plugin:
        return {
            "applied": False,
            "pattern": "missing-pytest-plugin",
            "option": option,
            "detail": f"no plugin mapping for pytest option {option!r}; extend PYTEST_PLUGIN_FOR_OPTION",
        }
    ok, log = _pip_install_into_seed(seed_dir, [plugin])
    return {
        "applied": ok,
        "pattern": "missing-pytest-plugin",
        "option": option,
        "plugin": plugin,
        "detail": log,
    }


def fix_seed_uncommitted(seed_dir: pathlib.Path) -> dict:
    """Commit seed working-tree changes for tracked files outside `.venv/`
    and `.claude/`. Caller is responsible for verifying the changes are
    expected (this only auto-applies because the alternative is silently
    losing them on the next `git checkout` inside a Builder task workspace)."""
    if not _make_seed_writable(seed_dir):
        return {"applied": False, "pattern": "seed-uncommitted",
                "detail": f"chmod -R u+w {seed_dir} failed"}
    try:
        r = subprocess.run(
            ["git", "-C", str(seed_dir), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return {"applied": False, "pattern": "seed-uncommitted",
                    "detail": f"git status returned {r.returncode}"}
        dirty = [ln for ln in r.stdout.splitlines()
                 if ln and not ln[3:].startswith(".venv/")
                 and not ln[3:].startswith(".claude/")]
        if not dirty:
            return {"applied": False, "pattern": "seed-uncommitted",
                    "detail": "no tracked-file divergence; nothing to commit"}
        # Stage only the dirty tracked files (not .venv/.claude noise).
        files = [ln[3:].strip() for ln in dirty]
        subprocess.run(
            ["git", "-C", str(seed_dir), "add", *files],
            check=True, timeout=10,
        )
        subprocess.run(
            ["git", "-C", str(seed_dir), "commit",
             "-m", "self_heal: commit seed working-tree divergence"],
            check=True, capture_output=True, timeout=10,
        )
        return {"applied": True, "pattern": "seed-uncommitted",
                "files": files,
                "detail": f"committed {len(files)} file(s): {', '.join(files[:3])}"}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return {"applied": False, "pattern": "seed-uncommitted",
                "detail": f"{type(exc).__name__}: {exc}"}
    finally:
        _restore_seed_readonly(seed_dir)


# Regexes ordered by specificity — first match wins.
LOG_PATTERNS: list[tuple[str, str, Callable]] = [
    (
        "missing-python-module",
        r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]",
        lambda seed, match: fix_missing_python_module(seed, match.group(1)),
    ),
    (
        "missing-python-module-import",
        r"ImportError: ([\w_]+) must be installed",
        lambda seed, match: fix_missing_python_module(seed, match.group(1).lower()),
    ),
    (
        "missing-pytest-plugin",
        r"PytestConfigWarning: Unknown config option: (\w+)",
        lambda seed, match: fix_missing_pytest_plugin(seed, match.group(1)),
    ),
]


def diagnose_and_fix_from_log(
    log_path: pathlib.Path, seed_dir: pathlib.Path
) -> dict | None:
    if not log_path.exists():
        return None
    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        return None
    for entry in LOG_PATTERNS:
        regex, fixer = entry[1], entry[2]
        m = re.search(regex, text)
        if m:
            return fixer(seed_dir, m)
    return None


def run_self_heal(
    evidence_dir: pathlib.Path, seed_dir: pathlib.Path
) -> dict:
    """Top-level: try every catalog pattern; return the first applied fix.

    Layered detection:
      1. Log-based: parse feature_check.log for known error regex patterns.
      2. State-based: seed git divergence (independent of log content).
    """
    log_path = evidence_dir / "feature_check.log"
    result = diagnose_and_fix_from_log(log_path, seed_dir)
    if result and result.get("applied"):
        return result
    # State-based: seed git uncommitted (an independent failure mode that
    # might coexist with — or hide — the log signal).
    if (seed_dir / ".git").exists():
        r = subprocess.run(
            ["git", "-C", str(seed_dir), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            dirty = [ln for ln in r.stdout.splitlines()
                     if ln and not ln[3:].startswith(".venv/")
                     and not ln[3:].startswith(".claude/")]
            if dirty:
                return fix_seed_uncommitted(seed_dir)
    # No pattern matched.
    return result or {
        "applied": False,
        "pattern": None,
        "detail": f"no known pattern matched in {log_path}",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence-dir", required=True, type=pathlib.Path)
    p.add_argument("--seed-dir", required=True, type=pathlib.Path)
    args = p.parse_args()
    res = run_self_heal(args.evidence_dir, args.seed_dir)
    print(json.dumps(res, indent=2))
    return 0 if res.get("applied") else 1


if __name__ == "__main__":
    sys.exit(main())
