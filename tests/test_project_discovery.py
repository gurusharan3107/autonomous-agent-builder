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


def _write_builder_source_marker(repo_root: Path) -> None:
    (repo_root / "src" / "autonomous_agent_builder" / "cli").mkdir(parents=True)
    (repo_root / "src" / "autonomous_agent_builder" / "cli" / "main.py").write_text(
        "app = None\n",
        encoding="utf-8",
    )
    (repo_root / "pyproject.toml").write_text(
        '[project]\nname = "autonomous-agent-builder"\n',
        encoding="utf-8",
    )


def test_find_agent_builder_dir_rejects_builder_source_repo(tmp_path: Path) -> None:
    _write_builder_source_marker(tmp_path)
    (tmp_path / ".agent-builder").mkdir()

    with pytest.raises(ProjectNotFoundError) as exc_info:
        find_agent_builder_dir(tmp_path)

    assert "not a builder-managed app project" in exc_info.value.message
