"""Sprint-PR refactor (Phase C) — sprint-level PR opens at sprint-shipped time."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import (
    ApprovalGate,
    Feature,
    Project,
    Sprint,
    SprintPhase,
    Task,
    TaskPhase,
    TaskStatus,
)
from autonomous_agent_builder.orchestrator.orchestrator import Orchestrator
from autonomous_agent_builder.services.sprint_execution import SPRINT_EXECUTION_KEY


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)


def _init_repo(repo: Path, *, with_remote: bool = False) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("# test\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    if with_remote:
        _git(repo, "remote", "add", "origin", "https://example.invalid/owner/repo.git")


@pytest.mark.asyncio
async def test_project_has_remote_returns_false_for_local_repo(tmp_path):
    repo = tmp_path / "norepo"
    _init_repo(repo, with_remote=False)
    assert await Orchestrator._project_has_remote(repo) is False


@pytest.mark.asyncio
async def test_project_has_remote_returns_true_when_origin_configured(tmp_path):
    repo = tmp_path / "withremote"
    _init_repo(repo, with_remote=True)
    assert await Orchestrator._project_has_remote(repo) is True


def test_sprint_changes_summary_lists_task_titles():
    sprint = Sprint(id="abcd", project_id="p", label="Sprint 1")
    tasks = [
        Task(id="t1", feature_id="f", title="Implement hello", description="", status=TaskStatus.DONE),
        Task(id="t2", feature_id="f", title="Add tests", description="", status=TaskStatus.DONE),
    ]
    summary = Orchestrator._sprint_changes_summary(sprint, tasks)
    assert "Sprint 1" in summary
    assert "- Implement hello" in summary
    assert "- Add tests" in summary


def test_extract_pr_url_finds_github_pr():
    output = (
        "Created PR for sprint review\n"
        "PR: https://github.com/owner/repo/pull/42\n"
        "Done."
    )
    assert Orchestrator._extract_pr_url(output) == "https://github.com/owner/repo/pull/42"


def test_extract_pr_url_returns_none_when_absent():
    assert Orchestrator._extract_pr_url("nothing here") is None
    assert Orchestrator._extract_pr_url("") is None


@pytest.mark.asyncio
async def test_local_app_sprint_completion_ff_merges_branch_into_main(tmp_path):
    """Local-app sprint completion: sprint branch ff-merges into main and ships."""
    repo = tmp_path / "repo"
    _init_repo(repo, with_remote=False)
    # Simulate a sprint branch with one commit on top of main.
    _git(repo, "checkout", "-b", "sprint/aaaa-sprint-1")
    (repo / "feature.txt").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "feature.txt")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@e.com", "commit", "-m", "feat: hello")
    _git(repo, "checkout", "main")

    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    orch = Orchestrator(get_settings(), db)
    sprint = Sprint(
        id="aaaaaaaa",
        project_id="p",
        label="Sprint 1",
        branch="sprint/aaaa-sprint-1",
    )

    err = await orch._maybe_ff_merge_sprint_branch(sprint, repo)
    assert err is None
    head_log = _git(repo, "log", "--oneline", "-1").stdout.strip()
    assert "feat: hello" in head_log
    # main is now at the sprint branch commit.
    main_sha = _git(repo, "rev-parse", "main").stdout.strip()
    sprint_sha = _git(repo, "rev-parse", "sprint/aaaa-sprint-1").stdout.strip()
    assert main_sha == sprint_sha


@pytest.mark.asyncio
async def test_maybe_ff_merge_is_noop_without_sprint_branch(tmp_path):
    repo = tmp_path / "norepo"
    _init_repo(repo)
    db = AsyncMock()
    orch = Orchestrator(get_settings(), db)
    sprint = Sprint(id="x", project_id="p", label="Sprint", branch=None)
    assert await orch._maybe_ff_merge_sprint_branch(sprint, repo) is None


@pytest.mark.asyncio
async def test_remote_path_runs_pr_creator_and_creates_sprint_pr_gate(tmp_path):
    """Remote-PR path: agent runs once, sprint enters PR_REVIEW with one sprint_pr gate."""
    repo = tmp_path / "repo"
    _init_repo(repo, with_remote=True)
    _git(repo, "branch", "sprint/aaaa-sprint-1")

    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    orch = Orchestrator(get_settings(), db)

    async def _fake_pr_creator(task, agent_name, template_vars, **kwargs):
        assert agent_name == "pr-creator"
        return RunResult(
            session_id="s",
            cost_usd=0.01,
            tokens_input=10,
            tokens_output=10,
            num_turns=1,
            stop_reason="end_turn",
            output_text="Opened sprint PR: https://github.com/owner/repo/pull/7",
        )

    orch._run_agent = _fake_pr_creator

    sprint = Sprint(
        id="aaaaaaaa",
        project_id="p",
        label="Sprint 1",
        branch="sprint/aaaa-sprint-1",
        phase=SprintPhase.VERIFY,
    )
    feature = MagicMock()
    feature.title = "f"
    project = MagicMock()
    project.repo_url = str(repo)
    feature.project = project
    latest_task = Task(id="t1", feature_id="f", title="Hello task", description="", status=TaskStatus.DONE)
    latest_task.feature = feature
    sprint_tasks = [latest_task]

    err = await orch._open_sprint_pr(sprint, sprint_tasks, latest_task, repo, base_evidence={})
    assert err is None
    assert sprint.phase == SprintPhase.PR_REVIEW
    assert sprint.pr_url == "https://github.com/owner/repo/pull/7"

    added_gates = [
        call.args[0]
        for call in db.add.call_args_list
        if isinstance(call.args[0], ApprovalGate)
    ]
    assert len(added_gates) == 1
    gate = added_gates[0]
    assert gate.gate_type == "sprint_pr"
    assert gate.sprint_id == sprint.id
    assert gate.task_id is None
