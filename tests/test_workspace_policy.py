from __future__ import annotations

from pathlib import Path

import pytest

from autonomous_agent_builder.orchestrator.workspace_policy import (
    directory_workspace_is_stale,
    is_builder_source_repo,
    is_fast_forward_divergence,
    next_clean_directory_workspace_path,
    tracked_overwrite_paths,
    untracked_overwrite_paths,
    workspace_copy_excluded,
)


def test_tracked_overwrite_paths_extracts_safe_relative_paths() -> None:
    output = """Updating 4236205..d3703f8
error: Your local changes to the following files would be overwritten by merge:
\tsrc/App.jsx
\t"src/store/todos.js"
\t../escape.txt
\t/tmp/absolute.txt
Please commit your changes or stash them before you merge.
Aborting
"""

    assert tracked_overwrite_paths(output) == ["src/App.jsx", "src/store/todos.js"]


def test_untracked_overwrite_paths_extracts_safe_relative_paths() -> None:
    output = """error: The following untracked working tree files would be overwritten by merge:
\tCLAUDE.md
\t"docs/notes.md"
Please move or remove them before you merge.
Aborting
"""

    assert untracked_overwrite_paths(output) == ["CLAUDE.md", "docs/notes.md"]


def test_workspace_copy_excluded_matches_exact_and_prefix_patterns() -> None:
    assert workspace_copy_excluded(Path(".agent-builder/dashboard/bundle.js")) is True
    assert workspace_copy_excluded(Path(".env.local")) is True
    assert workspace_copy_excluded(Path("src/App.jsx")) is False


def test_directory_workspace_is_stale_detects_missing_package_marker(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text("{}", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert directory_workspace_is_stale(str(workspace), str(repo)) is True
    (workspace / "package.json").write_text("{}", encoding="utf-8")
    assert directory_workspace_is_stale(str(workspace), str(repo)) is False
    assert directory_workspace_is_stale("", str(repo)) is False


def test_next_clean_directory_workspace_path_skips_existing_candidates(tmp_path) -> None:
    base_path = tmp_path / "task-workspace"
    (tmp_path / "task-workspace-clean-1").mkdir()

    assert next_clean_directory_workspace_path(base_path) == tmp_path / "task-workspace-clean-2"


def test_next_clean_directory_workspace_path_errors_when_no_candidate(tmp_path) -> None:
    base_path = tmp_path / "task-workspace"
    for index in range(1, 100):
        (tmp_path / f"task-workspace-clean-{index}").mkdir()

    with pytest.raises(RuntimeError, match="Could not allocate clean task workspace path"):
        next_clean_directory_workspace_path(base_path)


def test_is_builder_source_repo_requires_backend_and_frontend_markers(tmp_path) -> None:
    assert is_builder_source_repo(tmp_path) is False
    (tmp_path / "src" / "autonomous_agent_builder").mkdir(parents=True)
    assert is_builder_source_repo(tmp_path) is False
    (tmp_path / "frontend" / "src").mkdir(parents=True)
    assert is_builder_source_repo(tmp_path) is True


def test_is_fast_forward_divergence_matches_git_messages() -> None:
    assert is_fast_forward_divergence("fatal: Not possible to fast-forward, aborting.") is True
    assert is_fast_forward_divergence("hint: You have diverging branches") is True
    assert is_fast_forward_divergence("Already up to date.") is False
