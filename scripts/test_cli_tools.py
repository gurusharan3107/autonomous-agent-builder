#!/usr/bin/env python3
"""CLI smoke tests for workflow and builder commands."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def command_env() -> dict[str, str]:
    """Return an env that can run the repo-local CLI without editable install."""
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )
    return env


def workflow_command(*args: str) -> list[str]:
    """Resolve the workflow command for the current machine."""
    workflow = shutil.which("workflow")
    if workflow:
        return [workflow, *args]

    for candidate in (
        Path.home() / ".codex" / "bin" / "workflow.py",
        Path.home() / ".claude" / "bin" / "workflow.py",
    ):
        if candidate.exists():
            return [sys.executable, str(candidate), *args]

    raise FileNotFoundError("workflow")


def builder_command(*args: str) -> list[str]:
    """Run the repo-local builder CLI through Python module execution."""
    return [sys.executable, "-m", "autonomous_agent_builder.cli.main", *args]


def run_command(cmd: list[str], expect_success: bool = True) -> tuple[bool, str]:
    """Run a command and check if it succeeded."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=REPO_ROOT,
            env=command_env(),
        )

        success = (result.returncode == 0) == expect_success

        if not success:
            msg = f"Command: {' '.join(cmd)}\n"
            msg += f"Expected {'success' if expect_success else 'failure'}, "
            msg += f"got exit code {result.returncode}\n"
            if result.stderr:
                msg += f"stderr: {result.stderr[:200]}\n"
            return False, msg

        return True, f"✓ {' '.join(cmd[:4])}"

    except subprocess.TimeoutExpired:
        return False, f"✗ Timeout: {' '.join(cmd)}"
    except FileNotFoundError:
        return False, f"✗ Command not found: {cmd[0]}"
    except Exception as exc:
        return False, f"✗ Error running {' '.join(cmd)}: {exc}"


def test_workflow_cli() -> tuple[int, int]:
    """Test workflow CLI basic functionality."""
    print("\n🔍 Testing workflow CLI...")

    try:
        tests = [
            (workflow_command("--help"), True),
            (workflow_command("memory", "list"), True),
        ]
    except FileNotFoundError:
        print("  ⊘ Skipped (workflow command not available)")
        return 0, 0

    passed = 0
    failed = 0

    for cmd, expect_success in tests:
        success, msg = run_command(cmd, expect_success)
        if success:
            print(f"  {msg}")
            passed += 1
        else:
            print(f"  {msg}")
            failed += 1

    return passed, failed


def test_builder_memory() -> tuple[int, int]:
    """Test builder memory commands."""
    print("\n🔍 Testing builder memory CLI...")

    tests = [
        (builder_command("memory", "list"), True),
        (builder_command("memory", "search", "test"), True),
    ]

    passed = 0
    failed = 0

    for cmd, expect_success in tests:
        success, msg = run_command(cmd, expect_success)
        if success:
            print(f"  {msg}")
            passed += 1
        else:
            print(f"  {msg}")
            failed += 1

    return passed, failed


def test_builder_script() -> tuple[int, int]:
    """Test builder script commands."""
    print("\n🔍 Testing builder script CLI...")

    if not (REPO_ROOT / ".agent-builder").exists():
        print("  ⊘ Skipped (project not initialized)")
        return 0, 0

    tests = [
        (builder_command("script", "list"), True),
    ]

    passed = 0
    failed = 0

    for cmd, expect_success in tests:
        success, msg = run_command(cmd, expect_success)
        if success:
            print(f"  {msg}")
            passed += 1
        else:
            print(f"  {msg}")
            failed += 1

    return passed, failed


def main() -> int:
    """Run all CLI smoke tests."""
    print("=" * 60)
    print("CLI Tools Smoke Tests")
    print("=" * 60)

    total_passed = 0
    total_failed = 0

    passed, failed = test_workflow_cli()
    total_passed += passed
    total_failed += failed

    passed, failed = test_builder_memory()
    total_passed += passed
    total_failed += failed

    passed, failed = test_builder_script()
    total_passed += passed
    total_failed += failed

    print("\n" + "=" * 60)
    print(f"Results: {total_passed} passed, {total_failed} failed")
    print("=" * 60)

    if total_failed > 0:
        print("\n❌ Some CLI tests failed")
        return 1

    print("\n✅ All CLI tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
