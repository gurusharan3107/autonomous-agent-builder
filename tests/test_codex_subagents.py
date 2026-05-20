from __future__ import annotations

from pathlib import Path

from autonomous_agent_builder.codex_subagents import validate_project_codex_subagents


def _write_config(root: Path, body: str) -> None:
    config = root / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        body,
        encoding="utf-8",
    )


def _write_agent(root: Path, name: str, body: str) -> None:
    agents_dir = root / ".codex" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{name}.toml").write_text(body, encoding="utf-8")


def test_project_codex_subagent_validation_accepts_repo_contract(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        """
[agents.architecture_reviewer]
config_file = "agents/architecture-reviewer.toml"

[agents."code-simplifier"]
config_file = "agents/code-simplifier.toml"

[agents.code_reviewer]
config_file = "agents/code-reviewer.toml"
""",
    )
    _write_agent(
        tmp_path,
        "architecture-reviewer",
        """
name = "architecture_reviewer"
description = "Review owner boundaries."
model = "gpt-5.4"
sandbox_mode = "read-only"
developer_instructions = '''
Review autonomous-agent-builder boundaries.
This is not a Claude Agent SDK runtime agent or Builder product specialist.
Return a boundary map, findings, recommended owner surfaces, and next step.
Evidence-grounded. Actionable. Scope-boundary. Verification. Impact.
'''
""",
    )
    _write_agent(
        tmp_path,
        "code-simplifier",
        """
name = "code-simplifier"
description = "Simplifies recently modified code."
model = "gpt-5.5"
sandbox_mode = "workspace-write"
developer_instructions = '''
Simplify autonomous-agent-builder code.
This is not a Claude Agent SDK runtime agent or Builder product specialist.
Preserve functionality.
Focus on recently modified code.
Verification is required.
Evidence-grounded. Actionable. Scope-boundary. Verification. Impact.
'''
""",
    )
    _write_agent(
        tmp_path,
        "code-reviewer",
        """
name = "code_reviewer"
description = "Review changed code."
model = "gpt-5.4"
sandbox_mode = "read-only"
developer_instructions = '''
Review autonomous-agent-builder code.
This is not a Claude Agent SDK runtime agent or Builder product specialist.
Lead with findings.
Check correctness, security, regression risk, owner-surface drift, tests, and severity.
Evidence-grounded. Actionable. Scope-boundary. Verification. Impact.
'''
""",
    )

    result = validate_project_codex_subagents(tmp_path)

    assert result.ok is True
    assert result.agents == ("architecture_reviewer", "code-simplifier", "code_reviewer")
    assert result.issues == ()


def test_project_codex_subagent_validation_rejects_unsafe_contract(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        """
[agents.code_reviewer]
config_file = "agents/code-reviewer.toml"
""",
    )
    _write_agent(
        tmp_path,
        "code-reviewer",
        """
name = "code_reviewer"
description = "Review changed code."
model = "opus"
sandbox_mode = "workspace-write"
developer_instructions = "Review code."
""",
    )

    result = validate_project_codex_subagents(tmp_path)

    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "unsupported_model" in codes
    assert "reviewer_not_read_only" in codes
    assert "missing_runtime_boundary" in codes
    assert "missing_codex_only_boundary" in codes
    assert "missing_product_boundary" in codes
    assert "missing_reviewer_contract" in codes
    assert "missing_recommendation_quality_contract" in codes
    assert "missing_required_project_agent" in codes


def test_project_codex_subagent_validation_rejects_config_escape(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        """
[agents.code_reviewer]
config_file = "../code-reviewer.toml"
""",
    )
    (tmp_path / "code-reviewer.toml").write_text(
        """
name = "code_reviewer"
description = "Review changed code."
model = "gpt-5.4"
sandbox_mode = "read-only"
developer_instructions = '''
Review autonomous-agent-builder code.
This is not a Claude Agent SDK runtime agent or Builder product specialist.
Lead with findings.
Check correctness, security, regression risk, owner-surface drift, tests, and severity.
Evidence-grounded. Actionable. Scope-boundary. Verification. Impact.
'''
""",
        encoding="utf-8",
    )

    result = validate_project_codex_subagents(tmp_path)

    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "config_file_outside_agents" in codes


def test_project_codex_subagent_validation_rejects_unavailable_codex_model(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        """
[agents.code_reviewer]
config_file = "agents/code-reviewer.toml"
""",
    )
    _write_agent(
        tmp_path,
        "code-reviewer",
        """
name = "code_reviewer"
description = "Review changed code."
model = "gpt-5.3-codex-spark"
sandbox_mode = "read-only"
developer_instructions = '''
Review autonomous-agent-builder code.
This is not a Claude Agent SDK runtime agent or Builder product specialist.
Lead with findings.
Check correctness, security, regression risk, owner-surface drift, tests, and severity.
Evidence-grounded. Actionable. Scope-boundary. Verification. Impact.
'''
""",
    )

    result = validate_project_codex_subagents(tmp_path)

    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "unsupported_model" in codes


def test_project_codex_subagent_validation_rejects_runtime_agent_drift(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        """
[agents.code_reviewer]
config_file = "agents/code-reviewer.toml"
""",
    )
    _write_agent(
        tmp_path,
        "code-reviewer",
        """
name = "code_reviewer"
description = "Review changed code."
model = "gpt-5.4"
sandbox_mode = "read-only"
developer_instructions = '''
This is a Claude Agent SDK runtime agent for autonomous-agent-builder.
Lead with findings.
Check correctness, security, regression risk, owner-surface drift, tests, and severity.
Evidence-grounded. Actionable. Scope-boundary. Verification. Impact.
'''
""",
    )

    result = validate_project_codex_subagents(tmp_path)

    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "missing_codex_only_boundary" in codes


def test_project_codex_subagent_validation_rejects_product_specialist_drift(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        """
[agents."code-simplifier"]
config_file = "agents/code-simplifier.toml"
""",
    )
    _write_agent(
        tmp_path,
        "code-simplifier",
        """
name = "code-simplifier"
description = "Simplifies recently modified code."
model = "gpt-5.5"
sandbox_mode = "workspace-write"
developer_instructions = '''
Simplify autonomous-agent-builder code.
This is not a Claude Agent SDK runtime agent.
Preserve functionality.
Focus on recently modified code.
Verification is required.
Evidence-grounded. Actionable. Scope-boundary. Verification. Impact.
'''
""",
    )

    result = validate_project_codex_subagents(tmp_path)

    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "missing_product_boundary" in codes


def test_project_codex_subagent_validation_rejects_weak_reviewer_contract(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        """
[agents.code_reviewer]
config_file = "agents/code-reviewer.toml"
""",
    )
    _write_agent(
        tmp_path,
        "code-reviewer",
        """
name = "code_reviewer"
description = "Review changed code."
model = "gpt-5.4"
sandbox_mode = "read-only"
developer_instructions = '''
Review autonomous-agent-builder code.
This is not a Claude Agent SDK runtime agent or Builder product specialist.
'''
""",
    )

    result = validate_project_codex_subagents(tmp_path)

    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "missing_reviewer_contract" in codes


def test_project_codex_subagent_validation_rejects_missing_recommendation_quality(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        """
[agents."code-simplifier"]
config_file = "agents/code-simplifier.toml"
""",
    )
    _write_agent(
        tmp_path,
        "code-simplifier",
        """
name = "code-simplifier"
description = "Simplifies recently modified code."
model = "gpt-5.5"
sandbox_mode = "workspace-write"
developer_instructions = '''
Simplify autonomous-agent-builder code.
This is not a Claude Agent SDK runtime agent or Builder product specialist.
Preserve functionality.
Focus on recently modified code.
Verification is required.
'''
""",
    )

    result = validate_project_codex_subagents(tmp_path)

    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "missing_recommendation_quality_contract" in codes


def test_project_codex_subagent_validation_rejects_weak_architecture_contract(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        """
[agents.architecture_reviewer]
config_file = "agents/architecture-reviewer.toml"
""",
    )
    _write_agent(
        tmp_path,
        "architecture-reviewer",
        """
name = "architecture_reviewer"
description = "Review owner boundaries."
model = "gpt-5.4"
sandbox_mode = "read-only"
developer_instructions = '''
Review autonomous-agent-builder boundaries.
This is not a Claude Agent SDK runtime agent or Builder product specialist.
Evidence-grounded. Actionable. Scope-boundary. Verification. Impact.
'''
""",
    )

    result = validate_project_codex_subagents(tmp_path)

    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "missing_architecture_reviewer_contract" in codes


def test_project_codex_subagent_validation_rejects_missing_config_file_entry(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        """
[agents.code_reviewer]
description = "Review changed code."
""",
    )

    result = validate_project_codex_subagents(tmp_path)

    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "missing_config_file_entry" in codes


def test_project_codex_subagent_validation_rejects_config_description_boundary_drift(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        """
[agents.code_reviewer]
description = "Claude Agent SDK runtime specialist for Builder product runs."
config_file = "agents/code-reviewer.toml"
""",
    )
    _write_agent(
        tmp_path,
        "code-reviewer",
        """
name = "code_reviewer"
description = "Review changed code."
model = "gpt-5.4"
sandbox_mode = "read-only"
developer_instructions = '''
Review autonomous-agent-builder code.
This is not a Claude Agent SDK runtime agent or Builder product specialist.
Lead with findings.
Check correctness, security, regression risk, owner-surface drift, tests, and severity.
Evidence-grounded. Actionable. Scope-boundary. Verification. Impact.
'''
""",
    )

    result = validate_project_codex_subagents(tmp_path)

    assert result.ok is False
    codes = {issue.code for issue in result.issues}
    assert "config_description_boundary_drift" in codes
