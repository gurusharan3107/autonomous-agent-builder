"""Owned Python workspace environment provisioning.

Single source of truth for *how a generated Python app's tests are run*. Before
this module, every phase that ran pytest (testing gate, build_verify, the
materialized final checkout, the workspace test tool) independently invoked bare
``pytest`` / ``sys.executable`` against an interpreter where the app's
third-party deps were never installed → ``ModuleNotFoundError`` → the LLM
gate-remediator burned its retry cap trying to "fix" an environmental problem it
cannot fix by editing code.

The Node lane already provisioned deps (``npm install`` guards in
``code_quality``/``testing``/``build_verify``). This module is the missing
Python-lane peer: provision a virtualenv + install the project once
(idempotent), then run pytest under *that* interpreter everywhere.

Deterministic by design — no model. Provisioning is mechanical and reproducible;
it must never be delegated to an agent.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

_PYPROJECT = "pyproject.toml"
_REQUIREMENTS = "requirements.txt"


def is_python_workspace(project_root: Path) -> bool:
    """True when the workspace is a Python project (has a recognised marker)."""
    return any(
        (project_root / marker).exists()
        for marker in (_PYPROJECT, "setup.py", "setup.cfg", _REQUIREMENTS)
    )


def venv_python(project_root: Path) -> Path:
    """Path to the workspace virtualenv interpreter (may not exist yet)."""
    return project_root / ".venv" / "bin" / "python"


def _venv_pip(project_root: Path) -> Path:
    return project_root / ".venv" / "bin" / "pip"


def _has_dev_extra(project_root: Path) -> bool:
    """True when pyproject declares a ``dev`` optional-dependencies extra."""
    pyproject = project_root / _PYPROJECT
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return False
    if "[project.optional-dependencies]" not in text:
        return False
    return any(line.strip().replace(" ", "").startswith("dev=[") for line in text.splitlines())


def setup_commands(project_root: Path) -> list[list[str]]:
    """Provisioning commands to create the venv + install deps.

    Returns ``[]`` when the venv already exists (idempotent — safe to call before
    every test run). Mirrors the Node ``npm install`` guard for the Python lane.
    """
    if venv_python(project_root).exists():
        return []
    has_pyproject = (project_root / _PYPROJECT).exists()
    has_requirements = (project_root / _REQUIREMENTS).exists()
    if not (has_pyproject or has_requirements):
        # No dependency manifest → nothing to install; bare pytest is sufficient.
        return []
    pip = str(_venv_pip(project_root))
    cmds: list[list[str]] = [[sys.executable, "-m", "venv", str(project_root / ".venv")]]
    if has_pyproject:
        if _has_dev_extra(project_root):
            cmds.append([pip, "install", "-e", ".[dev]", "-q"])
        else:
            cmds.append([pip, "install", "-e", ".", "-q"])
            cmds.append([pip, "install", "pytest", "-q"])
    else:  # requirements.txt
        cmds.append([pip, "install", "-r", _REQUIREMENTS, "-q"])
        cmds.append([pip, "install", "pytest", "-q"])
    return cmds


def pytest_argv(
    project_root: Path, *, extra: list[str] | None = None, venv_required: bool = False
) -> list[str]:
    """Canonical pytest invocation under the workspace venv.

    Falls back to ``sys.executable`` only when no venv exists. Pass
    ``venv_required=True`` for *plan-time* callers (e.g. build_verify, which
    schedules ``venv_create`` to run before this command) so the command targets
    the venv interpreter that provisioning will create, even though it does not
    exist yet. All test-running phases MUST use this rather than bare ``pytest``
    so the app's installed deps are visible.
    """
    vpy = venv_python(project_root)
    python = str(vpy) if (venv_required or vpy.exists()) else sys.executable
    return [python, "-m", "pytest", *(extra or [])]


async def ensure_python_env(
    project_root: Path, *, force: bool = False, timeout_per_step: float = 180.0
) -> None:
    """Provision the venv + install deps (idempotent, no-op when present).

    For inline async consumers (the testing gate). Check-list consumers
    (build_verify) should instead prepend :func:`setup_commands` to their checks.
    With ``force=True`` an existing (possibly corrupt / incompletely-installed)
    venv is removed and rebuilt — used by deterministic env re-provisioning when
    a test gate fails with an environmental signature. Best-effort: provisioning
    failures surface downstream as the test run's own error rather than raising.
    """
    if force:
        shutil.rmtree(project_root / ".venv", ignore_errors=True)
    for cmd in setup_commands(project_root):
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=timeout_per_step)
        except (OSError, TimeoutError):
            return


async def ensure_node_env(project_root: Path, *, timeout_per_step: int = 300) -> None:
    """Provision Node deps for the workspace (idempotent, best-effort).

    No-op when ``package.json`` is absent. Runs ``npm ci`` when a lockfile is
    present, otherwise ``npm install``. Mirrors the ``npm install`` guards that
    ``code_quality`` and ``testing`` run INSIDE their gate timeout; this variant
    runs OUT-OF-BAND so a cold workspace does not trigger DEADLINE_EXCEEDED.
    Best-effort: on ``OSError`` (npm not found) or ``TimeoutError`` the child is
    killed + awaited before returning so the subprocess is never leaked.
    Idempotent — does NOT delete node_modules (no rmtree).
    """
    if not (project_root / "package.json").exists():
        return
    cmd = ["npm", "ci"] if (project_root / "package-lock.json").exists() else ["npm", "install"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(proc.communicate(), timeout=timeout_per_step)
        except TimeoutError:
            proc.kill()
            await proc.wait()
    except OSError:
        return


_ENV_FAILURE_SIGNATURES = (
    "ModuleNotFoundError",
    "No module named",
    "ImportError while importing",
    "ImportError: cannot import name",
    "command not found: pytest",
    "No module named pytest",
    # Node corruption: npm install exits 0 with tar errors → node_modules present
    # but packages incomplete → eslint/build tools emit "Cannot find module".
    # "MODULE_NOT_FOUND" is the Node.js error code — low false-positive risk.
    # "Cannot find module" is broader; accepted here because it appears in Node
    # runtime output (not in Python test assertion strings) and is the canonical
    # signal that node_modules are incomplete — not a source-level import typo.
    "Cannot find module",
    "MODULE_NOT_FOUND",
)


def is_environmental_failure(output: str) -> bool:
    """True when test output indicates a missing-dependency / interpreter problem.

    Such failures are NOT fixable by editing source — they must be resolved by
    deterministic re-provisioning, never by dispatching the LLM gate-remediator.
    """
    if not output:
        return False
    return any(sig in output for sig in _ENV_FAILURE_SIGNATURES)
