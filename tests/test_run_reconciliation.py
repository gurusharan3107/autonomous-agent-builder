"""Tests for startup recovery of interrupted agent runs."""

from __future__ import annotations

import asyncio
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import autonomous_agent_builder.services.run_reconciliation as reconciliation_module
from autonomous_agent_builder.db.models import (
    AgentRun,
    Feature,
    Project,
    Sprint,
    SprintPhase,
    Task,
    TaskStatus,
    Workspace,
)
from autonomous_agent_builder.services.run_reconciliation import (
    _run_git,
    _workspace_status,
    reconcile_blocked_sprints_with_materialized_main,
    reconcile_completed_tasks_with_unintegrated_workspace_changes,
    reconcile_orphaned_running_agent_runs,
    reconcile_shipped_sprints_with_failed_materialized_checkout,
)
from autonomous_agent_builder.services.sprint_execution import SPRINT_EXECUTION_KEY


class _HangingProcess:
    def __init__(self) -> None:
        self.returncode = None
        self.pid = None
        self.terminated = False

    async def communicate(self):
        await asyncio.Event().wait()

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode or 0


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


@pytest.mark.asyncio
async def test_workspace_status_times_out_hung_git(monkeypatch, tmp_path):
    process = _HangingProcess()

    async def fake_create_subprocess_exec(*args, **kwargs):
        assert args[:3] == ("git", "status", "--short")
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(reconciliation_module, "_RECONCILIATION_GIT_TIMEOUT_SECONDS", 0.01)

    code, output = await _workspace_status(str(tmp_path))

    assert code == 124
    assert "reconciliation git status timed out" in output
    assert process.terminated is True


@pytest.mark.asyncio
async def test_run_git_times_out_hung_git(monkeypatch, tmp_path):
    process = _HangingProcess()

    async def fake_create_subprocess_exec(*args, **kwargs):
        assert args[:2] == ("git", "status")
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(reconciliation_module, "_RECONCILIATION_GIT_TIMEOUT_SECONDS", 0.01)

    code, output = await _run_git(tmp_path, "status")

    assert code == 124
    assert "reconciliation git timed out" in output
    assert process.terminated is True


@pytest.mark.asyncio
async def test_reconcile_orphaned_running_agent_run_blocks_active_task(test_db):
    _, factory = test_db
    started_at = datetime.now(UTC) - timedelta(minutes=15)

    async with factory() as session:
        project = Project(name="todo-app", language="typescript")
        session.add(project)
        await session.flush()
        feature = Feature(project_id=project.id, title="Deterministic tests")
        session.add(feature)
        await session.flush()
        task = Task(
            feature_id=feature.id,
            title="Verify Deterministic tests and build script for shipping",
            status=TaskStatus.IMPLEMENTATION,
        )
        session.add(task)
        await session.flush()
        run = AgentRun(
            task_id=task.id,
            agent_name="code-gen",
            runtime_sdk="claude",
            status="running",
            started_at=started_at,
        )
        session.add(run)
        await session.commit()

        count = await reconcile_orphaned_running_agent_runs(session)
        await session.commit()

        assert count == 1
        refreshed_task = await session.get(Task, task.id)
        refreshed_run = await session.get(AgentRun, run.id)
        assert refreshed_task is not None
        assert refreshed_run is not None
        assert refreshed_task.status == TaskStatus.FAILED
        assert refreshed_task.blocked_reason == refreshed_run.error
        assert refreshed_task.blocked_at is not None
        assert refreshed_run.status == "failed"
        assert refreshed_run.completed_at is not None
        assert refreshed_run.duration_ms > 0
        assert "server restart" in (refreshed_run.error or "")


@pytest.mark.asyncio
async def test_reconcile_orphaned_running_agent_run_keeps_completed_latest_task_status(test_db):
    _, factory = test_db
    now = datetime.now(UTC)

    async with factory() as session:
        project = Project(name="todo-app", language="typescript")
        session.add(project)
        await session.flush()
        feature = Feature(project_id=project.id, title="Deterministic tests")
        session.add(feature)
        await session.flush()
        task = Task(
            feature_id=feature.id,
            title="Verify Deterministic tests and build script for shipping",
            status=TaskStatus.IMPLEMENTATION,
        )
        session.add(task)
        await session.flush()
        old_run = AgentRun(
            task_id=task.id,
            agent_name="code-gen",
            status="running",
            started_at=now - timedelta(minutes=10),
        )
        latest_run = AgentRun(
            task_id=task.id,
            agent_name="build-verifier",
            status="completed",
            started_at=now,
            completed_at=now + timedelta(seconds=1),
        )
        session.add_all([old_run, latest_run])
        await session.commit()

        count = await reconcile_orphaned_running_agent_runs(session)
        await session.commit()

        assert count == 1
        refreshed_task = await session.get(Task, task.id)
        refreshed_old_run = await session.get(AgentRun, old_run.id)
        assert refreshed_task is not None
        assert refreshed_old_run is not None
        assert refreshed_task.status == TaskStatus.IMPLEMENTATION
        assert refreshed_task.blocked_reason is None
        assert refreshed_old_run.status == "failed"


@pytest.mark.asyncio
async def test_reconcile_completed_task_with_dirty_workspace_blocks_shipped_sprint(
    test_db, tmp_path
):
    _, factory = test_db
    repo = tmp_path / "repo"
    _init_repo(repo)
    worktree = tmp_path / "task-worktree"
    result = _git(repo, "worktree", "add", "-b", "task/task-1", str(worktree), "main")
    assert result.returncode == 0, result.stderr
    (worktree / "package.json").write_text('{"scripts":{"test":"node --test"}}\n', encoding="utf-8")

    async with factory() as session:
        project = Project(name="todo-app", language="typescript", repo_url=str(repo))
        session.add(project)
        await session.flush()
        feature = Feature(project_id=project.id, title="Todo app")
        session.add(feature)
        await session.flush()
        sprint = Sprint(
            project_id=project.id,
            label="Sprint 1",
            phase=SprintPhase.SHIPPED,
            verification_status="passed",
            verification_evidence={"status": "passed"},
        )
        session.add(sprint)
        await session.flush()
        task = Task(
            feature_id=feature.id,
            title="Verify generated app",
            status=TaskStatus.DONE,
            depends_on={SPRINT_EXECUTION_KEY: {"sprint_id": sprint.id}},
        )
        session.add(task)
        await session.flush()
        session.add(
            Workspace(
                task_id=task.id,
                path=str(worktree),
                branch="task/task-1",
                is_worktree=True,
            )
        )
        await session.commit()

        count = await reconcile_completed_tasks_with_unintegrated_workspace_changes(session)
        await session.commit()

        assert count == 1
        refreshed_task = await session.get(Task, task.id)
        refreshed_sprint = await session.get(Sprint, sprint.id)
        assert refreshed_task is not None
        assert refreshed_sprint is not None
        assert refreshed_task.status == TaskStatus.FAILED
        assert "unintegrated changes" in (refreshed_task.blocked_reason or "")
        assert "package.json" in (refreshed_task.blocked_reason or "")
        assert refreshed_sprint.phase == SprintPhase.BLOCKED
        assert refreshed_sprint.verification_status == "blocked"
        evidence = refreshed_sprint.verification_evidence or {}
        assert evidence["unintegrated_task_workspace"]["task_id"] == task.id


@pytest.mark.asyncio
async def test_reconcile_completed_task_ignores_only_runtime_guidance_dirty(test_db, tmp_path):
    _, factory = test_db
    repo = tmp_path / "repo"
    _init_repo(repo)
    worktree = tmp_path / "task-worktree"
    result = _git(repo, "worktree", "add", "-b", "task/task-1", str(worktree), "main")
    assert result.returncode == 0, result.stderr
    (worktree / "CLAUDE.md").write_text("# builder guidance\n", encoding="utf-8")

    async with factory() as session:
        project = Project(name="todo-app", language="typescript", repo_url=str(repo))
        session.add(project)
        await session.flush()
        feature = Feature(project_id=project.id, title="Todo app")
        session.add(feature)
        await session.flush()
        task = Task(feature_id=feature.id, title="Verify generated app", status=TaskStatus.DONE)
        session.add(task)
        await session.flush()
        session.add(
            Workspace(
                task_id=task.id,
                path=str(worktree),
                branch="task/task-1",
                is_worktree=True,
            )
        )
        await session.commit()

        count = await reconcile_completed_tasks_with_unintegrated_workspace_changes(session)
        await session.commit()

        refreshed_task = await session.get(Task, task.id)
        assert count == 0
        assert refreshed_task is not None
        assert refreshed_task.status == TaskStatus.DONE


@pytest.mark.asyncio
async def test_reconcile_completed_task_undoes_package_lock_only_false_positive(test_db, tmp_path):
    _, factory = test_db
    repo = tmp_path / "repo"
    _init_repo(repo)
    worktree = tmp_path / "task-worktree"
    result = _git(repo, "worktree", "add", "-b", "task/task-1", str(worktree), "main")
    assert result.returncode == 0, result.stderr
    (worktree / "package-lock.json").write_text('{"lockfileVersion":3}\n', encoding="utf-8")

    async with factory() as session:
        project = Project(name="todo-app", language="typescript", repo_url=str(repo))
        session.add(project)
        await session.flush()
        feature = Feature(project_id=project.id, title="Todo app")
        session.add(feature)
        await session.flush()
        task = Task(
            feature_id=feature.id,
            title="Verify generated app",
            status=TaskStatus.FAILED,
            blocked_reason=(
                "Task workspace still has unintegrated changes after Builder marked "
                "the task done: ?? package-lock.json"
            ),
        )
        session.add(task)
        await session.flush()
        session.add(
            Workspace(
                task_id=task.id,
                path=str(worktree),
                branch="task/task-1",
                is_worktree=True,
            )
        )
        await session.commit()

        count = await reconcile_completed_tasks_with_unintegrated_workspace_changes(session)
        await session.commit()

        refreshed_task = await session.get(Task, task.id)
        assert count == 1
        assert refreshed_task is not None
        assert refreshed_task.status == TaskStatus.DONE
        assert refreshed_task.blocked_reason is None


@pytest.mark.asyncio
async def test_reconcile_blocked_sprint_materializes_missing_head_files(test_db, tmp_path):
    _, factory = test_db
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "package.json").write_text('{"scripts":{"test":"node --test"}}\n', encoding="utf-8")
    _git(repo, "add", "package.json")
    _git(repo, "commit", "-q", "-m", "ship app")
    _git(repo, "branch", "sprint/test-1")
    (repo / "package.json").unlink()

    async with factory() as session:
        project = Project(name="todo-app", language="typescript", repo_url=str(repo))
        session.add(project)
        await session.flush()
        feature = Feature(project_id=project.id, title="Todo app")
        session.add(feature)
        await session.flush()
        task = Task(feature_id=feature.id, title="Verify generated app", status=TaskStatus.DONE)
        session.add(task)
        await session.flush()
        sprint = Sprint(
            project_id=project.id,
            label="Sprint 1",
            phase=SprintPhase.BLOCKED,
            branch="sprint/test-1",
            generated_task_ids=[task.id],
            verification_status="blocked",
            verification_evidence={
                "status": "blocked",
                "sprint_merge_error": (
                    "Sprint completion failed: local app checkout still has tracked "
                    "non-guidance changes after sprint merge:  D package.json"
                ),
            },
        )
        session.add(sprint)
        await session.commit()

        count = await reconcile_blocked_sprints_with_materialized_main(session)
        await session.commit()

        refreshed_sprint = await session.get(Sprint, sprint.id)
        assert count == 1
        assert refreshed_sprint is not None
        assert refreshed_sprint.phase == SprintPhase.SHIPPED
        assert refreshed_sprint.verification_status == "passed"
        assert (repo / "package.json").is_file()


@pytest.mark.asyncio
async def test_reconcile_blocked_sprint_with_passed_evidence_and_done_tasks(test_db):
    _, factory = test_db

    async with factory() as session:
        project = Project(name="todo-app", language="typescript")
        session.add(project)
        await session.flush()
        feature = Feature(project_id=project.id, title="Todo app")
        session.add(feature)
        await session.flush()
        task = Task(feature_id=feature.id, title="Verify generated app", status=TaskStatus.DONE)
        session.add(task)
        await session.flush()
        sprint = Sprint(
            project_id=project.id,
            label="Sprint 1",
            phase=SprintPhase.BLOCKED,
            generated_task_ids=[task.id],
            verification_status="blocked",
            verification_evidence={
                "status": "passed",
                "source_task_id": task.id,
                "summary": "All generated sprint tasks completed.",
            },
        )
        session.add(sprint)
        await session.commit()

        count = await reconcile_blocked_sprints_with_materialized_main(session)
        await session.commit()

        refreshed_sprint = await session.get(Sprint, sprint.id)
        assert count == 1
        assert refreshed_sprint is not None
        assert refreshed_sprint.phase == SprintPhase.SHIPPED
        assert refreshed_sprint.verification_status == "passed"
        evidence = refreshed_sprint.verification_evidence or {}
        assert evidence["status"] == "passed"
        assert evidence["stale_blocked_state_reconciled_at"]


@pytest.mark.asyncio
async def test_reconcile_shipped_sprint_blocks_failed_materialized_checkout(
    test_db, tmp_path, monkeypatch
):
    _, factory = test_db
    repo = tmp_path / "repo"
    _init_repo(repo)

    def fail_build_verify(self, **kwargs):
        return {
            "success": False,
            "data": {
                "checks": [
                    {
                        "code": "npm_build",
                        "command": ["npm", "run", "build"],
                        "status": "failed",
                        "stderr_tail": "Cannot find module '@tailwindcss/postcss'",
                    }
                ]
            },
            "error": "One or more deterministic verification checks failed",
        }

    monkeypatch.setattr(
        "autonomous_agent_builder.services.run_reconciliation.BuildVerifyScript.run",
        fail_build_verify,
    )

    async with factory() as session:
        project = Project(name="todo-app", language="typescript", repo_url=str(repo))
        session.add(project)
        await session.flush()
        feature = Feature(project_id=project.id, title="Todo app")
        session.add(feature)
        await session.flush()
        task = Task(feature_id=feature.id, title="Verify generated app", status=TaskStatus.DONE)
        session.add(task)
        await session.flush()
        sprint = Sprint(
            project_id=project.id,
            label="Sprint 1",
            phase=SprintPhase.SHIPPED,
            generated_task_ids=[task.id],
            verification_status="passed",
            verification_evidence={
                "status": "passed",
                "source_task_id": task.id,
            },
        )
        session.add(sprint)
        await session.commit()

        count = await reconcile_shipped_sprints_with_failed_materialized_checkout(session)
        await session.commit()

        refreshed_task = await session.get(Task, task.id)
        refreshed_sprint = await session.get(Sprint, sprint.id)
        assert count == 1
        assert refreshed_task is not None
        assert refreshed_sprint is not None
        assert refreshed_task.status == TaskStatus.BLOCKED
        # Routing prefix preserved (task_recovery keys off it)...
        assert (refreshed_task.blocked_reason or "").startswith("final_checkout_build_failed:")
        # ...but the operator-facing reason is SUMMARIZED, not the raw tool dump:
        # names the failed command, points to evidence, and does NOT leak the
        # raw stderr_tail onto the Board (M2.4 no-internals-leakage).
        assert "`npm run build`" in (refreshed_task.blocked_reason or "")
        assert "run evidence" in (refreshed_task.blocked_reason or "")
        assert "@tailwindcss/postcss" not in (refreshed_task.blocked_reason or "")
        assert refreshed_sprint.phase == SprintPhase.BLOCKED
        assert refreshed_sprint.verification_status == "blocked"
        evidence = refreshed_sprint.verification_evidence or {}
        assert evidence["materialized_checkout_verification"]["status"] == "failed"
        # Raw detail is still preserved in evidence for diagnosis/remediation.
        assert "@tailwindcss/postcss" in evidence["sprint_merge_error"]
