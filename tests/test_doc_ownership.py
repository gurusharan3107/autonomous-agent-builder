from __future__ import annotations

from autonomous_agent_builder.cli.doc_ownership import check_doc_ownership
from autonomous_agent_builder.cli.quality_gates import check_quality_gate_ownership


def test_check_quality_gate_ownership_rejects_root_level_gate(tmp_path):
    repo = tmp_path
    (repo / "docs").mkdir()

    decision = check_quality_gate_ownership(
        repo / "docs" / "architecture-boundary-quality-gate.md",
        repo_root=repo,
    )

    assert decision.decision == "WRONG_SURFACE"
    assert decision.owner_path == str(repo / "docs" / "quality-gate" / "architecture-boundary.md")


def test_check_quality_gate_ownership_redirects_duplicate_surface(tmp_path):
    repo = tmp_path
    gate_dir = repo / "docs" / "quality-gate"
    gate_dir.mkdir(parents=True)
    (gate_dir / "builder-cli.md").write_text("# gate\n", encoding="utf-8")

    decision = check_quality_gate_ownership(
        gate_dir / "builder-cli-quality-gate.md",
        repo_root=repo,
    )

    assert decision.decision == "UPDATE_EXISTING"
    assert decision.owner_path == str(gate_dir / "builder-cli.md")


def test_check_quality_gate_ownership_allows_new_gate_in_reserved_dir(tmp_path):
    repo = tmp_path
    gate_dir = repo / "docs" / "quality-gate"
    gate_dir.mkdir(parents=True)

    decision = check_quality_gate_ownership(gate_dir / "new-surface.md", repo_root=repo)

    assert decision.decision == "CREATE_NEW_ALLOWED"


def test_check_doc_ownership_rejects_root_level_workflow_duplicate(tmp_path):
    repo = tmp_path
    workflow_dir = repo / "docs" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "chrome-devtools-dashboard-testing.md").write_text(
        "# workflow\n",
        encoding="utf-8",
    )

    decision = check_doc_ownership(
        repo / "docs" / "chrome-devtools-dashboard-testing.md",
        repo_root=repo,
    )

    assert decision.decision == "WRONG_SURFACE"
    assert decision.doc_class == "workflow"
    assert decision.owner_path == str(workflow_dir / "chrome-devtools-dashboard-testing.md")


def test_check_doc_ownership_rejects_root_level_workflow_suffix(tmp_path):
    repo = tmp_path
    (repo / "docs").mkdir()

    decision = check_doc_ownership(
        repo / "docs" / "task-workspace-isolation-workflow.md",
        repo_root=repo,
    )

    assert decision.decision == "WRONG_SURFACE"
    assert decision.doc_class == "workflow"
    assert decision.owner_path == str(repo / "docs" / "workflows" / "task-workspace-isolation.md")


def test_check_doc_ownership_allows_new_workflow_in_reserved_dir(tmp_path):
    repo = tmp_path
    workflow_dir = repo / "docs" / "workflows"
    workflow_dir.mkdir(parents=True)

    decision = check_doc_ownership(workflow_dir / "new-procedure.md", repo_root=repo)

    assert decision.decision == "CREATE_NEW_ALLOWED"
