"""Tests for builder verify changed-surface contracts."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from autonomous_agent_builder.cli.commands import verify as verify_module
from autonomous_agent_builder.cli.main import app

runner = CliRunner()


def test_verify_changed_files_ignore_local_codex_environment(monkeypatch):
    class FakeStatus:
        stdout = "?? .codex/environments/\n M src/autonomous_agent_builder/cli/main.py\n"

    monkeypatch.setattr(verify_module, "_run_git", lambda args: FakeStatus())

    assert verify_module._changed_files() == ["src/autonomous_agent_builder/cli/main.py"]


def test_verify_changed_files_ignore_local_codex_environment_file(monkeypatch):
    class FakeStatus:
        stdout = "?? .codex/environments/environment.toml\n"

    monkeypatch.setattr(verify_module, "_run_git", lambda args: FakeStatus())

    assert verify_module._changed_files() == []
    assert verify_module._surfaces_from_changes([]) == []


def test_verify_changed_with_only_ignored_local_files_needs_no_proof(monkeypatch):
    class FakeStatus:
        stdout = "?? .codex/environments/environment.toml\n"

    monkeypatch.setattr(verify_module, "_run_git", lambda args: FakeStatus())

    result = runner.invoke(app, ["verify", "--changed", "--execute", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["changed_files"] == []
    assert payload["selected_surfaces"] == []
    assert payload["required_proof"] == []
    assert payload["execution_results"] == []
    assert payload["next_step"] == "no_changed_files"


def test_verify_changed_files_classify_sprint_execution_as_product_lifecycle():
    assert verify_module._surfaces_from_changes(
        [
            "src/autonomous_agent_builder/orchestrator/orchestrator.py",
            "tests/test_sprint_execution.py",
        ]
    ) == ["product-lifecycle"]


def test_verify_product_lifecycle_changes_require_focused_lifecycle_tests():
    proofs = verify_module._proofs_for_surfaces(["builder-cli", "product-lifecycle"])

    assert any(proof.code == "builder_cli_surface_tests" for proof in proofs)
    lifecycle_proof = next(
        proof for proof in proofs if proof.code == "product_lifecycle_optimization_tests"
    )
    assert "test_post_ship_optimization_probe_summarizes_cli_evidence" in lifecycle_proof.command
    assert (
        "test_post_ship_optimization_refreshes_generated_app_sdk_guidance"
        in lifecycle_proof.command
    )


def test_verify_changed_files_classify_agent_definitions_as_agent_quality():
    assert verify_module._surfaces_from_changes(
        ["src/autonomous_agent_builder/agents/definitions.py"]
    ) == ["agent-quality"]


def test_verify_changed_files_classify_pre_commit_checks_as_builder_cli():
    assert verify_module._surfaces_from_changes(["scripts/pre_commit_checks.py"]) == ["builder-cli"]


def test_verify_changed_files_classify_claude_agent_sdk_runtime_changes():
    assert verify_module._surfaces_from_changes(
        [
            "src/autonomous_agent_builder/agents/runner.py",
            "src/autonomous_agent_builder/agents/execution_policy.py",
            "tests/test_agent_runner.py",
            "tests/test_execution_policy.py",
        ]
    ) == ["runtime"]


def test_verify_agent_quality_changes_require_definition_tests():
    proofs = verify_module._proofs_for_surfaces(["agent-quality"])

    agent_proof = next(proof for proof in proofs if proof.code == "agent_quality_definition_tests")
    assert (
        "test_optimization_agent_is_post_ship_bounded_and_observability_grounded"
        in agent_proof.command
    )
    assert "test_all_have_prompt_templates" in agent_proof.command


def test_verify_changed_files_classify_pre_commit_check_tests_as_builder_cli():
    assert verify_module._surfaces_from_changes(
        ["scripts/pre_commit_checks.py", "tests/test_pre_commit_checks.py"]
    ) == ["builder-cli"]


def test_verify_changed_files_classify_codex_subagent_changes():
    assert verify_module._surfaces_from_changes(
        [
            ".codex/agents/code-reviewer.toml",
            ".codex/config.toml",
            "docs/quality-gate/codex-subagents.md",
            "src/autonomous_agent_builder/codex_subagents.py",
            "tests/test_codex_subagents.py",
        ]
    ) == ["codex-subagents", "docs"]


def test_verify_codex_subagent_changes_require_owned_gate_and_tests():
    proofs = verify_module._proofs_for_surfaces(["codex-subagents"])

    codes = {proof.code for proof in proofs}
    docs_proof = next(
        proof for proof in proofs if proof.code == "codex_subagent_quality_gate_contract"
    )
    assert "codex_subagent_gate" in codes
    assert "codex_subagent_tests" in codes
    assert "docs/quality-gate/codex-subagents.md" in docs_proof.command


def test_verify_codex_subagent_owner_surfaces_require_owned_gate_and_docs_proof():
    assert verify_module._surfaces_from_changes(["AGENTS.md", "docs/REFERENCE.md"]) == [
        "codex-subagents",
        "docs",
    ]

    proofs = verify_module._proofs_for_surfaces(["codex-subagents", "docs"])
    codes = {proof.code for proof in proofs}
    docs_proof = next(
        proof for proof in proofs if proof.code == "codex_subagent_quality_gate_contract"
    )
    assert "codex_subagent_gate" in codes
    assert "codex_subagent_tests" in codes
    assert "docs/quality-gate/codex-subagents.md" in docs_proof.command


def test_verify_runtime_changes_require_agent_runner_tests():
    proofs = verify_module._proofs_for_surfaces(["runtime"])

    runtime_proof = next(proof for proof in proofs if proof.code == "runtime_tests")
    assert "tests/test_agent_runner.py" in runtime_proof.command
