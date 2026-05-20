from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_dashboard_design_tokens_are_enforced() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/check_dashboard_design_tokens.py", "--json"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
