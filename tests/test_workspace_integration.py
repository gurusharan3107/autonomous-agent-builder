from __future__ import annotations

from autonomous_agent_builder.orchestrator.workspace_integration import (
    conflict_markers_remaining,
)


def test_conflict_markers_remaining_reports_unresolved_files(tmp_path) -> None:
    (tmp_path / "resolved.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "conflicted.py").write_text(
        "<<<<<<< HEAD\nold\n=======\nnew\n>>>>>>> branch\n",
        encoding="utf-8",
    )

    assert conflict_markers_remaining(tmp_path, ["resolved.py", "conflicted.py"]) == (
        "Integration failed: conflict resolver left git conflict markers in conflicted.py"
    )


def test_conflict_markers_remaining_ignores_missing_and_clean_files(tmp_path) -> None:
    (tmp_path / "resolved.py").write_text("print('ok')\n", encoding="utf-8")

    assert conflict_markers_remaining(tmp_path, ["resolved.py", "missing.py"]) is None
