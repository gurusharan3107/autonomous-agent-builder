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
changed_files = pre_commit_checks.changed_files
changelog_sync_result = pre_commit_checks.changelog_sync_result
docs_sync_result = pre_commit_checks.docs_sync_result
# NB: do not bind tests_sync_result to a module-level name starting with "test" —
# pytest's python_functions=test* glob would collect the alias as a test case.
run_tests_sync = pre_commit_checks.tests_sync_result


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


def test_changelog_sync_fails_for_product_code_without_changelog_update():
    payload = changelog_sync_result(["src/autonomous_agent_builder/cli/commands/memory.py"])

    assert payload["status"] == "failed"
    assert payload["exit_code"] == 3
    assert payload["tracked_changes"] == ["src/autonomous_agent_builder/cli/commands/memory.py"]
    assert payload["changelog_changed"] is False


def test_changelog_sync_passes_when_changelog_is_updated_with_product_code():
    payload = changelog_sync_result(
        [
            "src/autonomous_agent_builder/cli/commands/memory.py",
            "CHANGELOG.md",
        ]
    )

    assert payload["status"] == "passed"
    assert payload["changelog_changed"] is True


def test_changelog_sync_requires_changelog_for_docs_and_hooks():
    payload = changelog_sync_result(["docs/quality-gate/builder-cli.md", ".githooks/pre-commit"])

    assert payload["status"] == "failed"
    assert payload["tracked_changes"] == [
        ".githooks/pre-commit",
        "docs/quality-gate/builder-cli.md",
    ]


def test_changelog_sync_does_not_require_changelog_for_tests_only_change():
    payload = changelog_sync_result(["tests/test_memory_cli.py"])

    assert payload["status"] == "passed"
    assert payload["tracked_changes"] == []


def test_tests_sync_fails_for_behavioral_src_without_test_update():
    payload = run_tests_sync(["src/autonomous_agent_builder/agents/definitions.py"])

    assert payload["status"] == "failed"
    assert payload["exit_code"] == 4
    assert payload["code_changes"] == ["src/autonomous_agent_builder/agents/definitions.py"]
    assert payload["test_changes"] == []


def test_tests_sync_passes_when_src_ships_with_a_test_change():
    payload = run_tests_sync(
        [
            "src/autonomous_agent_builder/agents/definitions.py",
            "tests/test_definitions.py",
        ]
    )

    assert payload["status"] == "passed"
    assert payload["test_changes"] == ["tests/test_definitions.py"]


def test_tests_sync_does_not_require_test_for_tests_only_change():
    payload = run_tests_sync(["tests/test_memory_cli.py"])

    assert payload["status"] == "passed"
    assert payload["code_changes"] == []


def test_tests_sync_ignores_non_src_and_static_changes():
    payload = run_tests_sync(
        [
            "docs/goal/ROADMAP.md",
            "scripts/seed_demo.py",
            "src/autonomous_agent_builder/dashboard/static/app.js",
        ]
    )

    assert payload["status"] == "passed"
    assert payload["code_changes"] == []


def test_memory_and_hook_changes_select_bounded_tests():
    codes = _codes(
        [
            "scripts/pre_commit_checks.py",
            ".githooks/pre-commit",
            "src/autonomous_agent_builder/cli/commands/memory.py",
            "docs/workflows/autonomous-lifecycle-validation.md",
        ]
    )

    assert "builder_lint" in codes
    assert "memory_cli_tests" in codes
    assert "memory_contract_smoke" in codes
    assert "builder_cli_surface_tests" in codes
    assert "quality_gate_contracts" in codes


def test_agent_quality_and_product_lifecycle_changes_select_owned_tests():
    codes = _codes(
        [
            "src/autonomous_agent_builder/agents/definitions.py",
            "src/autonomous_agent_builder/orchestrator/orchestrator.py",
            "tests/test_sprint_execution.py",
        ]
    )

    assert "agent_quality_definition_tests" in codes
    assert "product_lifecycle_optimization_tests" in codes
    assert "general_smoke_tests" not in codes


def test_claude_agent_sdk_runtime_changes_select_runtime_tests():
    codes = _codes(
        [
            "src/autonomous_agent_builder/agents/runner.py",
            "src/autonomous_agent_builder/agents/execution_policy.py",
            "tests/test_agent_runner.py",
            "tests/test_execution_policy.py",
        ]
    )

    assert "runtime_tests" in codes
    assert "general_smoke_tests" not in codes


def test_codex_subagent_changes_select_owned_gate_and_tests():
    codes = _codes(
        [
            ".codex/agents/code-reviewer.toml",
            ".codex/config.toml",
            "docs/quality-gate/codex-subagents.md",
            "src/autonomous_agent_builder/codex_subagents.py",
            "tests/test_codex_subagents.py",
        ]
    )

    command_by_code = {
        check.code: " ".join(check.command)
        for check in checks_for_files(["docs/quality-gate/codex-subagents.md"])
    }
    assert "codex_subagent_gate" in codes
    assert "codex_subagent_tests" in codes
    assert "codex_subagent_quality_gate_contract" in codes
    assert (
        "scripts/check_quality_gate_contracts.py --target docs/quality-gate/codex-subagents.md"
        in command_by_code["codex_subagent_quality_gate_contract"]
    )
    assert "general_smoke_tests" not in codes


def test_codex_subagent_owner_surfaces_select_owned_gate_and_tests():
    codes = _codes(["AGENTS.md", "docs/REFERENCE.md"])

    assert "codex_subagent_gate" in codes
    assert "codex_subagent_tests" in codes
    assert "codex_subagent_quality_gate_contract" in codes


def test_changed_files_ignores_local_codex_environment(monkeypatch, tmp_path):
    def fake_git_lines(args, repo_root):
        assert repo_root == tmp_path
        if args == ["diff", "--cached", "--name-only"]:
            return []
        if args == ["status", "--short", "--untracked-files=all"]:
            return [
                "?? .codex/environments/environment.toml",
                " M src/autonomous_agent_builder/agents/definitions.py",
            ]
        return []

    monkeypatch.setattr(pre_commit_checks, "_git_lines", fake_git_lines)

    assert changed_files(tmp_path) == ["src/autonomous_agent_builder/agents/definitions.py"]
