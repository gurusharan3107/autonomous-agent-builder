"""Tests for deterministic pre-commit check selection."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "pre_commit_checks.py"
SPEC = importlib.util.spec_from_file_location("pre_commit_checks", MODULE_PATH)
assert SPEC and SPEC.loader
pre_commit_checks = importlib.util.module_from_spec(SPEC)
sys.modules["pre_commit_checks"] = pre_commit_checks
SPEC.loader.exec_module(pre_commit_checks)

checks_for_files = pre_commit_checks.checks_for_files
docs_sync_result = pre_commit_checks.docs_sync_result


def _codes(files: list[str]) -> set[str]:
    return {check.code for check in checks_for_files(files)}


def test_docs_sync_fails_for_product_code_without_repo_doc_update():
    payload = docs_sync_result(["src/autonomous_agent_builder/cli/commands/memory.py"])

    assert payload["status"] == "failed"
    assert payload["exit_code"] == 2
    assert payload["code_changes"] == ["src/autonomous_agent_builder/cli/commands/memory.py"]
    assert payload["doc_changes"] == []


def test_docs_sync_passes_when_product_code_has_reference_doc_update():
    payload = docs_sync_result(
        [
            "src/autonomous_agent_builder/cli/commands/memory.py",
            "docs/references/builder-cli.md",
        ]
    )

    assert payload["status"] == "passed"
    assert payload["doc_changes"] == ["docs/references/builder-cli.md"]


def test_docs_sync_does_not_require_docs_for_tests_only_change():
    payload = docs_sync_result(["tests/test_memory_cli.py"])

    assert payload["status"] == "passed"
    assert payload["code_changes"] == []


def test_memory_and_hook_changes_select_bounded_tests():
    codes = _codes(
        [
            "scripts/pre_commit_checks.py",
            ".githooks/pre-commit",
            "src/autonomous_agent_builder/cli/commands/memory.py",
            "docs/workflow-cli-usage.md",
        ]
    )

    assert "builder_lint" in codes
    assert "memory_cli_tests" in codes
    assert "memory_contract_smoke" in codes
    assert "builder_cli_surface_tests" in codes
    assert "quality_gate_contracts" in codes
