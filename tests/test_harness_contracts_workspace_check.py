"""Regression test for _check_workspace_ready in test_harness_contracts.py.

P26: builder doctor always returns ok:true (command success), so the old check
`data.get("ok") is True` always returned workspace-ready — even when passed:false
(not initialized). Result: contract tests ran outside a workspace, failed
spuriously, and blocked the recipe-2 preflight.

Fix: gate on `ok:true AND passed:true`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

# The skill script lives outside src/ — add its directory to the path.
_SKILL_SCRIPTS = Path(__file__).resolve().parents[1] / ".claude/skills/autoresearch/scripts"
if str(_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS))

import test_harness_contracts as thc  # noqa: E402


def _doctor_response(**kwargs) -> tuple[int, str, str]:
    """Return a (rc, stdout, stderr) triple mimicking builder doctor --json."""
    return 0, json.dumps({"ok": True, "status": "ok", **kwargs}), ""


class TestCheckWorkspaceReady:
    def test_not_initialized_workspace_returns_false(self):
        """ok:true + passed:false (not initialized) must gate → False."""
        with patch.object(thc, "_run", return_value=_doctor_response(passed=False)):
            ok, detail = thc._check_workspace_ready({})
        assert not ok
        assert "passed=False" in detail

    def test_initialized_workspace_returns_true(self):
        """ok:true + passed:true (fully ready) must pass the gate → True."""
        with patch.object(thc, "_run", return_value=_doctor_response(passed=True)):
            ok, detail = thc._check_workspace_ready({})
        assert ok
        assert detail == "workspace ready"

    def test_missing_passed_field_returns_false(self):
        """Old builder versions without a passed field must not be treated as ready."""
        with patch.object(thc, "_run", return_value=_doctor_response()):
            ok, detail = thc._check_workspace_ready({})
        assert not ok
        assert "passed=None" in detail

    def test_non_zero_exit_returns_false(self):
        """Non-zero exit from doctor → False regardless of stdout."""
        with patch.object(thc, "_run", return_value=(1, "", "some error")):
            ok, _detail = thc._check_workspace_ready({})
        assert not ok

    def test_non_json_output_returns_false(self):
        """Unparseable doctor output → False."""
        with patch.object(thc, "_run", return_value=(0, "not json", "")):
            ok, _detail = thc._check_workspace_ready({})
        assert not ok
