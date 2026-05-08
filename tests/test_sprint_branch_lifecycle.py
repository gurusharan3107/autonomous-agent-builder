"""Sprint-PR refactor (Phase B) — sprint branch lifecycle and per-task integration target."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import (
    Sprint,
    SprintPhase,
)
from autonomous_agent_builder.orchestrator.orchestrator import Orchestrator


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("# test\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")


@pytest.fixture
def orchestrator():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return Orchestrator(get_settings(), db)


def test_sprint_branch_name_is_deterministic(orchestrator):
    sprint = Sprint(id="abcdef0123456789", project_id="p", label="Sprint 1")
    assert orchestrator._sprint_branch_name(sprint) == "sprint/abcdef01-sprint-1"


def test_sprint_branch_name_handles_blank_label(orchestrator):
    sprint = Sprint(id="zzz12345", project_id="p", label="")
    name = orchestrator._sprint_branch_name(sprint)
    assert name.startswith("sprint/zzz12345-")
    assert name.endswith("-sprint")


def test_sprint_branch_name_slugifies_complex_labels(orchestrator):
    sprint = Sprint(id="11111111", project_id="p", label="Sprint #2 — auth flow")
    name = orchestrator._sprint_branch_name(sprint)
    # Non-alphanum runs collapse to single dashes; trailing dashes are trimmed.
    assert name == "sprint/11111111-sprint-2-auth-flow"


@pytest.mark.asyncio
async def test_ensure_sprint_branch_creates_branch_when_missing(tmp_path, orchestrator):
    repo = tmp_path / "repo"
    _init_repo(repo)
    sprint = Sprint(
        id="abcdef0123456789",
        project_id="p",
        label="Sprint 1",
        phase=SprintPhase.IMPLEMENTATION,
    )

    async def run_git(*args: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=str(repo),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode, out.decode() + err.decode()

    branch = await orchestrator._ensure_sprint_branch(sprint, repo, run_git)

    assert branch == "sprint/abcdef01-sprint-1"
    assert sprint.branch == branch
    branches = _git(repo, "branch", "--list", branch).stdout
    assert branch in branches


@pytest.mark.asyncio
async def test_ensure_sprint_branch_is_idempotent(tmp_path, orchestrator):
    repo = tmp_path / "repo"
    _init_repo(repo)
    sprint = Sprint(
        id="abcdef0123456789",
        project_id="p",
        label="Sprint 1",
        phase=SprintPhase.IMPLEMENTATION,
    )

    async def run_git(*args: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=str(repo),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode, out.decode() + err.decode()

    first = await orchestrator._ensure_sprint_branch(sprint, repo, run_git)
    second = await orchestrator._ensure_sprint_branch(sprint, repo, run_git)
    assert first == second
    # Only one matching branch exists.
    out = _git(repo, "branch", "--list", first).stdout.strip().splitlines()
    assert len(out) == 1


@pytest.mark.asyncio
async def test_ensure_sprint_branch_returns_none_on_unborn_head(tmp_path, orchestrator):
    repo = tmp_path / "unborn"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    sprint = Sprint(id="abcdef01", project_id="p", label="Sprint 1")

    async def run_git(*args: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=str(repo),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        return proc.returncode, out.decode() + err.decode()

    branch = await orchestrator._ensure_sprint_branch(sprint, repo, run_git)
    assert branch is None
    assert sprint.branch is None


@pytest.mark.asyncio
async def test_workspace_manager_create_workspace_honors_start_point(tmp_path):
    """The new ``start_point`` parameter must thread through to ``git worktree add``."""
    from autonomous_agent_builder.workspace.manager import WorkspaceManager

    repo = tmp_path / "repo"
    _init_repo(repo)
    # Create a sprint branch ahead of the worktree call.
    _git(repo, "branch", "sprint/test-1")

    workspaces_root = tmp_path / "workspaces"
    manager = WorkspaceManager(str(workspaces_root))

    info = await manager.create_workspace(
        str(repo),
        task_id="task-1",
        start_point="sprint/test-1",
    )

    assert info.is_worktree is True
    assert info.branch == "task/task-1"
    # The new task branch should descend from sprint/test-1, so its merge-base
    # with sprint/test-1 equals the sprint/test-1 commit itself.
    sprint_sha = _git(repo, "rev-parse", "sprint/test-1").stdout.strip()
    base_sha = _git(repo, "merge-base", "task/task-1", "sprint/test-1").stdout.strip()
    assert base_sha == sprint_sha
