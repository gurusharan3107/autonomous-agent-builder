#!/usr/bin/env python3
"""Validate the public workflow shell launcher."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def resolve_control_plane_bin() -> Path | None:
    """Return the first control-plane bin directory that exists."""
    candidates = [
        Path.home() / ".codex" / "bin",
        Path.home() / ".claude" / "bin",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def validate_wrappers() -> int:
    """Validate that the workflow launcher exists and points at the right script."""
    print("=" * 60)
    print("CLI Wrapper Validation")
    print("=" * 60)

    control_plane_bin = resolve_control_plane_bin()
    local_bin = Path.home() / ".local" / "bin"

    if control_plane_bin is None:
        workflow_path = shutil.which("workflow")
        if workflow_path:
            print(f"\n✅ Managed workflow launcher found on PATH: {workflow_path}")
            print("   No control-plane bin directory present; launcher validation skipped.")
            return 0

        print("\n❌ No control-plane bin directory found under ~/.codex/bin or ~/.claude/bin")
        print("   Hint: install the workflow launcher or create the expected bin directory.")
        return 1

    workflow_script = control_plane_bin / "workflow.py"
    if not workflow_script.exists():
        print(f"\n❌ Missing workflow source script: {workflow_script}")
        return 1

    launcher = local_bin / "workflow"
    if not launcher.exists():
        print(f"\n❌ Missing workflow launcher: {launcher}")
        return 1

    content = launcher.read_text()
    if workflow_script.name not in content and str(workflow_script) not in content:
        print(f"\n❌ Launcher does not reference expected script: {workflow_script}")
        return 1

    print(f"\n✅ Launcher found: {launcher}")
    print(f"✅ Source script found: {workflow_script}")
    if workflow_script.stat().st_mode & 0o111:
        print("✅ Python source is executable")
    else:
        print("⚠️  Python source is not executable")

    print("\n✅ Workflow launcher validated")
    return 0


def main() -> int:
    """Run launcher validation."""
    return validate_wrappers()


if __name__ == "__main__":
    sys.exit(main())
