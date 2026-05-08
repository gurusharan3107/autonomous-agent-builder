"""Tests for git-remote detection + github_repository resource builder."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from autonomous_agent_builder.runtime.managed_agents_workspace import (
    WORKSPACE_REQUIRED_ROLES,
    build_github_resource,
    detect_current_branch,
    detect_github_remote,
    resolve_github_token,
)


def _init_repo(path: Path, *, remote_url: str | None = None, branch: str = "main") -> None:
    """Initialize a tiny git repo with optional `origin` remote."""
    subprocess.run(["git", "init", "-q", "-b", branch, str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@test.com"], check=True
    )
    subprocess.run(["git", "-C", str(path), "config", "user.name", "test"], check=True)
    if remote_url is not None:
        subprocess.run(
            ["git", "-C", str(path), "remote", "add", "origin", remote_url], check=True
        )
    # One commit so HEAD resolves to a branch
    (path / "README").write_text("x")
    subprocess.run(["git", "-C", str(path), "add", "README"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "init"], check=True)


def test_detect_github_remote_returns_none_for_missing_workspace(tmp_path: Path) -> None:
    assert detect_github_remote(tmp_path / "does-not-exist") is None


def test_detect_github_remote_returns_none_when_no_origin(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    assert detect_github_remote(tmp_path) is None


def test_detect_github_remote_parses_https_url(tmp_path: Path) -> None:
    _init_repo(tmp_path, remote_url="https://github.com/owner/repo.git")
    assert detect_github_remote(tmp_path) == ("owner", "repo")


def test_detect_github_remote_parses_https_url_no_dot_git(tmp_path: Path) -> None:
    _init_repo(tmp_path, remote_url="https://github.com/owner/repo")
    assert detect_github_remote(tmp_path) == ("owner", "repo")


def test_detect_github_remote_parses_ssh_url(tmp_path: Path) -> None:
    _init_repo(tmp_path, remote_url="git@github.com:owner/repo.git")
    assert detect_github_remote(tmp_path) == ("owner", "repo")


def test_detect_github_remote_returns_none_for_non_github_remote(tmp_path: Path) -> None:
    _init_repo(tmp_path, remote_url="https://gitlab.com/owner/repo.git")
    assert detect_github_remote(tmp_path) is None


def test_detect_current_branch(tmp_path: Path) -> None:
    _init_repo(tmp_path, remote_url="https://github.com/o/r.git", branch="dev")
    assert detect_current_branch(tmp_path) == "dev"


def test_resolve_github_token_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_abc")
    assert resolve_github_token() == "ghp_abc"


def test_resolve_github_token_falls_back_to_gh_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GH_TOKEN", "gh_xyz")
    assert resolve_github_token() == "gh_xyz"


def test_resolve_github_token_returns_none_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert resolve_github_token() is None


def test_build_github_resource_returns_none_when_workspace_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
    assert build_github_resource(workspace_path=None) is None


def test_build_github_resource_returns_none_when_no_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
    _init_repo(tmp_path)  # no remote
    assert build_github_resource(workspace_path=tmp_path) is None


def test_build_github_resource_returns_none_when_token_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    _init_repo(tmp_path, remote_url="https://github.com/o/r.git")
    assert build_github_resource(workspace_path=tmp_path) is None


def test_build_github_resource_full_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
    _init_repo(tmp_path, remote_url="https://github.com/owner/myrepo.git", branch="feat/x")
    resource = build_github_resource(workspace_path=tmp_path)
    assert resource is not None
    assert resource["type"] == "github_repository"
    assert resource["url"] == "https://github.com/owner/myrepo"
    assert resource["authorization_token"] == "ghp_secret"
    assert resource["mount_path"] == "/workspace/myrepo"
    assert resource["checkout"] == {"type": "branch", "name": "feat/x"}


def test_build_github_resource_branch_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
    _init_repo(tmp_path, remote_url="https://github.com/o/r.git", branch="main")
    resource = build_github_resource(
        workspace_path=tmp_path, branch_override="release/1.0"
    )
    assert resource is not None
    assert resource["checkout"] == {"type": "branch", "name": "release/1.0"}


def test_workspace_required_roles_includes_code_gen() -> None:
    """Sanity-check that the roles needing a workspace are the obvious ones."""
    assert "code-gen" in WORKSPACE_REQUIRED_ROLES
    assert "build-verifier" in WORKSPACE_REQUIRED_ROLES
    assert "pr-creator" in WORKSPACE_REQUIRED_ROLES
    # planner / chat don't need a workspace mount
    assert "planner" not in WORKSPACE_REQUIRED_ROLES
    assert "chat" not in WORKSPACE_REQUIRED_ROLES
