from __future__ import annotations

from pathlib import Path

import pytest

from autonomous_agent_builder.cli.project_discovery import (
    ProjectNotFoundError,
    find_agent_builder_dir,
)


def test_find_agent_builder_dir_stops_at_git_repo_boundary(tmp_path: Path) -> None:
    shared_parent = tmp_path / "shared-parent"
    shared_parent.mkdir()
    (shared_parent / ".agent-builder").mkdir()

    repo_root = shared_parent / "external-repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    with pytest.raises(ProjectNotFoundError):
        find_agent_builder_dir(repo_root)


def test_find_agent_builder_dir_finds_repo_local_dir_from_nested_subdir(tmp_path: Path) -> None:
    repo_root = tmp_path / "external-repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    agent_builder_dir = repo_root / ".agent-builder"
    agent_builder_dir.mkdir()

    nested = repo_root / "app" / "views"
    nested.mkdir(parents=True)

    assert find_agent_builder_dir(nested) == agent_builder_dir
