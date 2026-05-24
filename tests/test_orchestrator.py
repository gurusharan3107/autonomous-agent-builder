"""Tests for orchestrator dispatch logic — status transitions and phase routing."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

import autonomous_agent_builder.orchestrator.orchestrator as orchestrator_module
from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import (
    ApprovalGate,
    Task,
    TaskPhase,
    TaskStatus,
    Workspace,
)
from autonomous_agent_builder.orchestrator.orchestrator import (
    BLOCKED_STATUSES,
    PHASE_DISPATCH,
    Orchestrator,
)
from autonomous_agent_builder.services.sprint_execution import SPRINT_EXECUTION_KEY


class _HangingProcess:
    def __init__(self) -> None:
        self.returncode = None
        self.pid = None
        self.terminated = False
        self.killed = False

    async def communicate(self):
        await asyncio.Event().wait()

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode or 0


@pytest.fixture
def mock_db():
    """Mock async DB session."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def orchestrator(mock_db):
    """Orchestrator with mocked DB and settings."""
    return Orchestrator(get_settings(), mock_db)


def _make_task(
    status: TaskStatus,
    *,
    workspace_path: str | None = "/tmp/workspace",
    repo_url: str = "/tmp/repo",
) -> Task:
    """Create a minimal Task with required relationships."""
    task = Task(
        id="test-task-id",
        feature_id="test-feature-id",
        title="Test task",
        description="Test description",
        status=status,
    )
    # Mock the relationships the orchestrator expects
    project = MagicMock()
    project.name = "test-project"
    project.language = "python"
    project.repo_url = repo_url
    feature = MagicMock()
    feature.project = project
    feature.title = "Test feature"
    task.feature = feature
    task.workspace = MagicMock(path=workspace_path) if workspace_path else None
    task.agent_runs = []
    task.approval_gates = []
    task.depends_on = None
    return task


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)


@pytest.mark.asyncio
async def test_project_has_remote_times_out_hung_git(monkeypatch, tmp_path):
    process = _HangingProcess()

    async def fake_create_subprocess_exec(*args, **kwargs):
        assert args[:2] == ("git", "remote")
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(orchestrator_module, "_ORCHESTRATOR_GIT_TIMEOUT_SECONDS", 0.01)

    assert await Orchestrator._project_has_remote(tmp_path) is False
    assert process.terminated is True


@pytest.mark.asyncio
async def test_run_builder_script_returns_timeout_error_for_hung_subprocess(
    orchestrator,
    monkeypatch,
    tmp_path,
):
    process = _HangingProcess()

    async def fake_create_subprocess_exec(*args, **kwargs):
        assert "script" in args
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(orchestrator_module, "_ORCHESTRATOR_SCRIPT_TIMEOUT_SECONDS", 0.01)

    ok, payload, stdout, stderr = await orchestrator._run_builder_script(
        "build_verify",
        str(tmp_path),
    )

    assert ok is False
    assert payload == {}
    assert stdout == ""
    assert "builder script build_verify timed out" in stderr
    assert process.terminated is True


class TestDispatchTable:
    """Verify the dispatch table maps every dispatchable status."""

    def test_all_dispatchable_statuses_have_handlers(self):
        expected = {
            TaskStatus.PENDING,
            TaskStatus.QUEUED,
            TaskStatus.PLANNING,
            TaskStatus.DESIGN,
            TaskStatus.IMPLEMENTATION,
            TaskStatus.QUALITY_GATES,
            TaskStatus.PR_CREATION,
            TaskStatus.BUILD_VERIFY,
        }
        assert set(PHASE_DISPATCH.keys()) == expected

    def test_blocked_statuses_complete(self):
        expected = {
            TaskStatus.DESIGN_REVIEW,
            TaskStatus.REVIEW_PENDING,
            TaskStatus.BLOCKED,
            TaskStatus.CAPABILITY_LIMIT,
            TaskStatus.DONE,
            TaskStatus.FAILED,
        }
        assert expected == BLOCKED_STATUSES

    def test_no_status_in_both_dispatch_and_blocked(self):
        overlap = set(PHASE_DISPATCH.keys()) & BLOCKED_STATUSES
        assert overlap == set(), f"Status in both dispatch and blocked: {overlap}"

    def test_all_statuses_are_either_dispatch_or_blocked(self):
        all_covered = set(PHASE_DISPATCH.keys()) | BLOCKED_STATUSES
        all_statuses = set(TaskStatus)
        assert all_covered == all_statuses


@pytest.mark.asyncio
async def test_integrate_task_workspace_preserves_tracked_target_changes_before_merge(
    orchestrator, tmp_path
):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert _git(repo, "init", "-q", "-b", "main").returncode == 0
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    src_dir = repo / "src"
    src_dir.mkdir()
    app_file = src_dir / "App.jsx"
    app_file.write_text("export default function App() { return 'base'; }\n", encoding="utf-8")
    _git(repo, "add", "src/App.jsx")
    assert _git(repo, "commit", "-q", "-m", "init").returncode == 0

    workspace = tmp_path / "task-worktree"
    assert _git(repo, "worktree", "add", "-q", "-b", "task/test", str(workspace), "main").returncode == 0
    (workspace / "src" / "App.jsx").write_text(
        "export default function App() { return 'task'; }\n",
        encoding="utf-8",
    )
    app_file.write_text(
        "export default function App() { return 'local dirty'; }\n",
        encoding="utf-8",
    )

    task = _make_task(
        TaskStatus.BUILD_VERIFY,
        workspace_path=str(workspace),
        repo_url=str(repo),
    )
    task.workspace = Workspace(
        path=str(workspace),
        branch="task/test",
        is_worktree=True,
    )
    task.depends_on = None

    error = await orchestrator._integrate_task_workspace(task)

    assert error is None
    assert app_file.read_text(encoding="utf-8") == (
        "export default function App() { return 'task'; }\n"
    )
    stash_list = _git(repo, "stash", "list").stdout
    assert "builder: preserve local changes before integrating task/test" in stash_list


@pytest.mark.asyncio
class TestDispatchBlocked:
    """Blocked statuses should be no-ops."""

    async def test_done_task_not_dispatched(self, orchestrator):
        task = _make_task(TaskStatus.DONE)
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.DONE

    async def test_failed_task_not_dispatched(self, orchestrator):
        task = _make_task(TaskStatus.FAILED)
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.FAILED

    async def test_capability_limit_not_dispatched(self, orchestrator):
        task = _make_task(TaskStatus.CAPABILITY_LIMIT)
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.CAPABILITY_LIMIT

    async def test_blocked_not_dispatched(self, orchestrator):
        task = _make_task(TaskStatus.BLOCKED)
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.BLOCKED

    async def test_design_review_not_dispatched(self, orchestrator):
        task = _make_task(TaskStatus.DESIGN_REVIEW)
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.DESIGN_REVIEW

    async def test_review_pending_not_dispatched(self, orchestrator):
        task = _make_task(TaskStatus.REVIEW_PENDING)
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.REVIEW_PENDING


@pytest.mark.asyncio
class TestDispatchPhases:
    """Each dispatchable status triggers the correct phase handler."""

    @pytest_asyncio.fixture(autouse=True)
    async def _wire_db(self, test_db):
        """Wire session module to test DB so persist_realtime_run_update can write."""
        yield

    async def test_pending_runs_planning(self, orchestrator, mock_sdk):
        task = _make_task(TaskStatus.PENDING)
        await orchestrator.dispatch(task)
        # Planning phase sets DESIGN_REVIEW on success
        assert task.status == TaskStatus.DESIGN_REVIEW

    async def test_planning_runs_planning(self, orchestrator, mock_sdk):
        task = _make_task(TaskStatus.PLANNING)
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.DESIGN_REVIEW

    async def test_queued_implementation_runs_codegen(self, orchestrator, mock_sdk, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        # Seed a language marker so scaffold is skipped — this test exercises
        # the code-gen step, not the scaffold step.
        (workspace / "pyproject.toml").touch()
        task = _make_task(TaskStatus.QUEUED, workspace_path=str(workspace))
        task.phase = TaskPhase.IMPLEMENTATION
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.QUALITY_GATES

    async def test_queued_verification_runs_quality_gates(self, orchestrator, mock_sdk):
        task = _make_task(TaskStatus.QUEUED)
        task.phase = TaskPhase.VERIFICATION
        orchestrator._phase_quality_gates = AsyncMock(
            side_effect=lambda task: setattr(task, "status", TaskStatus.PR_CREATION)
        )
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.PR_CREATION

    async def test_design_runs_design(self, orchestrator, mock_sdk, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        task = _make_task(TaskStatus.DESIGN, workspace_path=str(workspace))
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.IMPLEMENTATION

    async def test_implementation_runs_codegen(self, orchestrator, mock_sdk, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "pyproject.toml").touch()
        task = _make_task(TaskStatus.IMPLEMENTATION, workspace_path=str(workspace))
        task.depends_on = {
            "operator_decision": {
                "phase": "implementation",
                "question": "Use stale workspace output?",
            },
            "phase_context": {"design_context": "keep this"},
        }
        await orchestrator.dispatch(task)
        # Code-gen success → QUALITY_GATES
        assert task.status == TaskStatus.QUALITY_GATES
        assert task.depends_on == {"phase_context": {"design_context": "keep this"}}

    async def test_pr_creation_runs_pr_creator(self, orchestrator, mock_sdk, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        task = _make_task(TaskStatus.PR_CREATION, workspace_path=str(workspace))
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.REVIEW_PENDING

    async def test_codex_directory_sprint_pr_creation_uses_evidence_collector(
        self, orchestrator, mock_db, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        task = _make_task(TaskStatus.PR_CREATION, workspace_path=str(workspace))
        task.workspace.is_worktree = False
        task.depends_on = {
            SPRINT_EXECUTION_KEY: {
                "runtime_tool_strategy": {"runtime_sdk": "codex_sdk"},
            }
        }
        orchestrator._run_builder_script = AsyncMock(
            return_value=(
                True,
                {
                    "success": True,
                    "data": {
                        "files": [{"path": "src/main.js"}],
                        "hunks": [],
                        "files_changed": 1,
                    },
                },
                "",
                "",
            )
        )

        await orchestrator.dispatch(task)

        assert task.status == TaskStatus.BUILD_VERIFY
        added_runs = [
            call.args[0]
            for call in mock_db.add.call_args_list
            if getattr(call.args[0], "agent_name", "") == "evidence-collector"
        ]
        assert len(added_runs) == 1
        assert added_runs[0].runtime_sdk == "deterministic"
        orchestrator._run_builder_script.assert_awaited_once()

    async def test_claude_directory_sprint_pr_creation_uses_evidence_collector(
        self, orchestrator, mock_db, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        task = _make_task(TaskStatus.PR_CREATION, workspace_path=str(workspace))
        task.workspace.is_worktree = False
        task.depends_on = {
            SPRINT_EXECUTION_KEY: {
                "runtime_tool_strategy": {"runtime_sdk": "claude"},
            }
        }
        orchestrator._run_builder_script = AsyncMock(
            return_value=(
                True,
                {
                    "success": True,
                    "data": {
                        "files": [{"path": "src/main.js"}],
                        "hunks": [],
                        "files_changed": 1,
                    },
                },
                "",
                "",
            )
        )
        orchestrator._run_agent = AsyncMock()

        await orchestrator.dispatch(task)

        assert task.status == TaskStatus.BUILD_VERIFY
        orchestrator._run_agent.assert_not_awaited()
        added_runs = [
            call.args[0]
            for call in mock_db.add.call_args_list
            if getattr(call.args[0], "agent_name", "") == "evidence-collector"
        ]
        assert len(added_runs) == 1
        assert added_runs[0].runtime_sdk == "deterministic"
        orchestrator._run_builder_script.assert_awaited_once()

    async def test_quality_gates_reprovisions_missing_workspace_before_checks(
        self, orchestrator, tmp_path
    ):
        healed_workspace = tmp_path / "workspace"
        healed_workspace.mkdir()
        task = _make_task(TaskStatus.QUALITY_GATES, workspace_path=str(tmp_path / "missing"))
        workspace = MagicMock(
            path=str(healed_workspace),
            branch="task/test-task-id",
            is_worktree=True,
        )

        async def ensure_workspace(_task):
            _task.workspace = workspace
            return workspace

        orchestrator._ensure_workspace = AsyncMock(side_effect=ensure_workspace)
        orchestrator._workspace_has_task_changes = AsyncMock(return_value=False)
        orchestrator.gate_handler.handle_gate_failure = AsyncMock()

        await orchestrator._phase_quality_gates(task)

        orchestrator._ensure_workspace.assert_awaited_once_with(task)
        orchestrator._workspace_has_task_changes.assert_awaited_once_with(str(healed_workspace))

    async def test_quality_gates_cap_exceeded_blocks_task(self, orchestrator):
        cap = 3 * orchestrator.gate_handler.max_retries
        task = _make_task(TaskStatus.QUALITY_GATES)
        task.retry_count = cap

        await orchestrator._phase_quality_gates(task)

        assert task.status == TaskStatus.BLOCKED
        assert task.blocked_reason is not None
        assert task.blocked_reason.startswith("quality_gate_cap_exceeded:")
        assert str(cap) in task.blocked_reason
        orchestrator.db.flush.assert_awaited()

    async def test_quality_gates_below_cap_runs_normally(self, orchestrator, tmp_path):
        cap = 3 * orchestrator.gate_handler.max_retries
        task = _make_task(TaskStatus.QUALITY_GATES, workspace_path=str(tmp_path))
        task.retry_count = cap - 1

        orchestrator._ensure_workspace = AsyncMock()
        orchestrator._workspace_has_task_changes = AsyncMock(return_value=False)
        orchestrator.gate_handler.handle_gate_failure = AsyncMock()

        await orchestrator._phase_quality_gates(task)

        assert task.status == TaskStatus.QUALITY_GATES

    async def test_pr_creation_reprovisions_missing_workspace_before_evidence_collection(
        self, orchestrator, tmp_path
    ):
        healed_workspace = tmp_path / "workspace"
        healed_workspace.mkdir()
        task = _make_task(TaskStatus.PR_CREATION, workspace_path=str(tmp_path / "missing"))
        task.depends_on = {
            SPRINT_EXECUTION_KEY: {
                "runtime_tool_strategy": {"runtime_sdk": "codex_sdk"},
            }
        }
        workspace = MagicMock(
            path=str(healed_workspace),
            branch="task/test-task-id",
            is_worktree=True,
        )

        async def ensure_workspace(_task):
            _task.workspace = workspace
            return workspace

        orchestrator._ensure_workspace = AsyncMock(side_effect=ensure_workspace)
        orchestrator._record_deterministic_evidence = AsyncMock()

        await orchestrator._phase_pr_creation(task)

        orchestrator._ensure_workspace.assert_awaited_once_with(task)
        orchestrator._record_deterministic_evidence.assert_awaited_once_with(
            task,
            str(healed_workspace),
        )

    async def test_build_verify_reprovisions_missing_workspace_before_verification(
        self, orchestrator, tmp_path
    ):
        healed_workspace = tmp_path / "workspace"
        healed_workspace.mkdir()
        task = _make_task(TaskStatus.BUILD_VERIFY, workspace_path=str(tmp_path / "missing"))
        task.depends_on = {
            SPRINT_EXECUTION_KEY: {
                "runtime_tool_strategy": {"runtime_sdk": "codex_sdk"},
            }
        }
        workspace = MagicMock(
            path=str(healed_workspace),
            branch="task/test-task-id",
            is_worktree=True,
        )

        async def ensure_workspace(_task):
            _task.workspace = workspace
            return workspace

        orchestrator._ensure_workspace = AsyncMock(side_effect=ensure_workspace)
        orchestrator._run_feature_acceptance_gate = AsyncMock(return_value=(True, "ok"))
        orchestrator._record_deterministic_build_verification = AsyncMock(
            return_value=(True, "build ok")
        )
        orchestrator._integrate_task_workspace = AsyncMock(return_value=None)
        orchestrator._maybe_mark_sprint_shipped = AsyncMock()

        await orchestrator._phase_build_verify(task)

        orchestrator._ensure_workspace.assert_awaited_once_with(task)
        orchestrator._run_feature_acceptance_gate.assert_awaited_once_with(
            task,
            str(healed_workspace),
        )
        orchestrator._record_deterministic_build_verification.assert_awaited_once_with(
            task,
            str(healed_workspace),
        )

    async def test_worktree_sprint_pr_creation_uses_evidence_collector_without_pr_gate(
        self, orchestrator, mock_db, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        task = _make_task(TaskStatus.PR_CREATION, workspace_path=str(workspace))
        task.workspace.is_worktree = True
        task.depends_on = {
            SPRINT_EXECUTION_KEY: {
                "runtime_tool_strategy": {"runtime_sdk": "codex_sdk"},
            }
        }
        orchestrator._run_builder_script = AsyncMock(
            return_value=(
                True,
                {
                    "success": True,
                    "data": {
                        "files": [{"path": "src/main.js"}],
                        "hunks": [],
                        "files_changed": 1,
                    },
                },
                "",
                "",
            )
        )
        orchestrator._run_agent = AsyncMock()

        await orchestrator.dispatch(task)

        assert task.status == TaskStatus.BUILD_VERIFY
        orchestrator._run_agent.assert_not_awaited()
        added_runs = [
            call.args[0]
            for call in mock_db.add.call_args_list
            if getattr(call.args[0], "agent_name", "") == "evidence-collector"
        ]
        approvals = [
            call.args[0]
            for call in mock_db.add.call_args_list
            if isinstance(call.args[0], ApprovalGate)
        ]
        assert len(added_runs) == 1
        assert added_runs[0].runtime_sdk == "deterministic"
        assert approvals == []
        orchestrator._run_builder_script.assert_awaited_once()

    async def test_build_verify_runs_verifier(self, orchestrator, mock_sdk, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        task = _make_task(TaskStatus.BUILD_VERIFY, workspace_path=str(workspace))
        orchestrator._integrate_task_workspace = AsyncMock(return_value=None)
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.DONE

    async def test_codex_directory_sprint_build_verify_uses_deterministic_script(
        self, orchestrator, mock_db, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        task = _make_task(TaskStatus.BUILD_VERIFY, workspace_path=str(workspace))
        task.workspace.is_worktree = False
        task.depends_on = {
            SPRINT_EXECUTION_KEY: {
                "runtime_tool_strategy": {"runtime_sdk": "codex_sdk"},
            }
        }
        orchestrator._record_deterministic_build_verification = AsyncMock(
            return_value=(True, "build ok")
        )
        orchestrator._integrate_task_workspace = AsyncMock(return_value=None)
        orchestrator._run_agent = AsyncMock()

        await orchestrator.dispatch(task)

        assert task.status == TaskStatus.DONE
        orchestrator._run_agent.assert_not_awaited()
        orchestrator._record_deterministic_build_verification.assert_awaited_once_with(
            task,
            str(workspace),
        )

    async def test_claude_directory_sprint_build_verify_uses_deterministic_script(
        self, orchestrator, mock_db, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        task = _make_task(TaskStatus.BUILD_VERIFY, workspace_path=str(workspace))
        task.workspace.is_worktree = False
        task.depends_on = {
            SPRINT_EXECUTION_KEY: {
                "runtime_tool_strategy": {"runtime_sdk": "claude"},
            }
        }
        orchestrator._record_deterministic_build_verification = AsyncMock(
            return_value=(True, "build ok")
        )
        orchestrator._integrate_task_workspace = AsyncMock(return_value=None)
        orchestrator._run_agent = AsyncMock()

        await orchestrator.dispatch(task)

        assert task.status == TaskStatus.DONE
        orchestrator._run_agent.assert_not_awaited()
        orchestrator._record_deterministic_build_verification.assert_awaited_once_with(
            task,
            str(workspace),
        )

    async def test_worktree_sprint_build_verify_uses_deterministic_script(
        self, orchestrator, mock_db, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        task = _make_task(TaskStatus.BUILD_VERIFY, workspace_path=str(workspace))
        task.workspace.is_worktree = True
        task.depends_on = {
            SPRINT_EXECUTION_KEY: {
                "runtime_tool_strategy": {"runtime_sdk": "codex_sdk"},
            }
        }
        orchestrator._record_deterministic_build_verification = AsyncMock(
            return_value=(True, "build ok")
        )
        orchestrator._integrate_task_workspace = AsyncMock(return_value=None)
        orchestrator._run_agent = AsyncMock()

        await orchestrator.dispatch(task)

        assert task.status == TaskStatus.DONE
        orchestrator._run_agent.assert_not_awaited()
        orchestrator._record_deterministic_build_verification.assert_awaited_once_with(
            task,
            str(workspace),
        )

    async def test_build_verify_fails_when_verifier_reports_failed_check(
        self, orchestrator, mock_db, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        task = _make_task(TaskStatus.BUILD_VERIFY, workspace_path=str(workspace))
        orchestrator._run_agent = AsyncMock(
            return_value=RunResult(
                output_text=(
                    "`npm test` PASS: 8/8 tests\n"
                    "`scripts/browser-proof.sh` FAIL: Chrome exited 134"
                )
            )
        )
        orchestrator._integrate_task_workspace = AsyncMock()

        await orchestrator.dispatch(task)

        assert task.status == TaskStatus.FAILED
        assert task.blocked_reason == (
            "build_verification_failed: "
            "`scripts/browser-proof.sh` FAIL: Chrome exited 134"
        )
        orchestrator._integrate_task_workspace.assert_not_awaited()

    async def test_build_verify_ignores_non_git_directory_advisory(
        self, orchestrator, mock_db, tmp_path
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        task = _make_task(TaskStatus.BUILD_VERIFY, workspace_path=str(workspace))
        orchestrator._run_agent = AsyncMock(
            return_value=RunResult(
                output_text=(
                    "`git status --short --branch` -> FAIL: not a git repository.\n"
                    "`npm test` -> PASS: 8 tests, 8 pass, 0 fail.\n"
                    "`npm run lint` -> PASS: lint passed."
                )
            )
        )
        orchestrator._integrate_task_workspace = AsyncMock(return_value=None)

        await orchestrator.dispatch(task)

        assert task.status == TaskStatus.DONE

    async def test_design_provisions_workspace_before_implementation(
        self, orchestrator, mock_db, mock_sdk, tmp_path
    ):
        task = _make_task(
            TaskStatus.DESIGN,
            workspace_path=None,
            repo_url=str(tmp_path),
        )

        workspace_info = MagicMock(
            path=str(tmp_path / "workspaces" / "test-task-id"),
            branch="task/test-task-id",
            is_worktree=True,
        )
        Path(workspace_info.path).mkdir(parents=True)
        orchestrator._provision_workspace_info = AsyncMock(return_value=workspace_info)

        await orchestrator.dispatch(task)

        assert task.status == TaskStatus.IMPLEMENTATION
        assert isinstance(task.workspace, Workspace)
        assert task.workspace.path == workspace_info.path
        assert task.workspace.branch == workspace_info.branch
        added_workspaces = [
            call.args[0]
            for call in mock_db.add.call_args_list
            if isinstance(call.args[0], Workspace)
        ]
        assert len(added_workspaces) == 1

    async def test_implementation_provisions_missing_workspace_for_legacy_task(
        self, orchestrator, mock_db, mock_sdk, tmp_path
    ):
        task = _make_task(
            TaskStatus.IMPLEMENTATION,
            workspace_path=None,
            repo_url=str(tmp_path),
        )

        workspace_info = MagicMock(
            path=str(tmp_path / "workspaces" / "test-task-id"),
            branch="task/test-task-id",
            is_worktree=True,
        )
        Path(workspace_info.path).mkdir(parents=True)
        (Path(workspace_info.path) / "pyproject.toml").touch()
        orchestrator._provision_workspace_info = AsyncMock(return_value=workspace_info)

        await orchestrator.dispatch(task)

        assert task.status == TaskStatus.QUALITY_GATES
        assert isinstance(task.workspace, Workspace)
        assert task.workspace.path == workspace_info.path
        assert task.workspace.branch == workspace_info.branch

    async def test_implementation_reprovisions_missing_persisted_workspace(
        self, orchestrator, mock_db, mock_sdk, tmp_path
    ):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        missing_workspace = tmp_path / "missing-workspace"
        task = _make_task(
            TaskStatus.IMPLEMENTATION,
            workspace_path=str(missing_workspace),
            repo_url=str(repo_root),
        )
        task.workspace = Workspace(
            task_id=task.id,
            path=str(missing_workspace),
            branch="task/test-task-id",
            is_worktree=True,
        )

        workspace_info = MagicMock(
            path=str(tmp_path / "workspaces" / "test-task-id"),
            branch="task/test-task-id",
            is_worktree=True,
        )
        Path(workspace_info.path).mkdir(parents=True)
        (Path(workspace_info.path) / "pyproject.toml").touch()
        orchestrator._provision_workspace_info = AsyncMock(return_value=workspace_info)

        await orchestrator.dispatch(task)

        assert task.status == TaskStatus.QUALITY_GATES
        assert task.workspace.path == workspace_info.path
        assert task.workspace.branch == workspace_info.branch
        orchestrator._provision_workspace_info.assert_awaited_once()

    async def test_directory_workspace_excludes_builder_internals(
        self,
        orchestrator,
        monkeypatch,
        tmp_path,
    ):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / "AGENTS.md").write_text("runtime guidance", encoding="utf-8")
        (repo_root / "README.md").write_text("app readme", encoding="utf-8")
        (repo_root / ".env").write_text("SECRET=value", encoding="utf-8")
        (repo_root / ".venv").mkdir()
        (repo_root / ".venv" / "pyvenv.cfg").write_text("venv", encoding="utf-8")
        (repo_root / "node_modules").mkdir()
        (repo_root / "node_modules" / "package.txt").write_text("dependency", encoding="utf-8")
        (repo_root / ".agent-builder" / "dashboard").mkdir(parents=True)
        (repo_root / ".agent-builder" / "agent_builder.db").write_text("db", encoding="utf-8")
        (repo_root / ".claude" / "progress").mkdir(parents=True)
        (repo_root / ".claude" / "progress" / "feature-list.json").write_text(
            "{}",
            encoding="utf-8",
        )
        workspace_root = tmp_path / "workspaces"
        monkeypatch.setattr(orchestrator.settings, "workspace_root", str(workspace_root))

        workspace_info = await orchestrator._provision_workspace_info(
            MagicMock(),
            repo_root,
            "task-1",
        )
        workspace = Path(workspace_info.path)

        assert workspace == workspace_root / "task-1"
        assert (workspace / "AGENTS.md").exists()
        assert (workspace / "README.md").exists()
        assert not (workspace / ".agent-builder").exists()
        assert not (workspace / ".claude").exists()
        assert not (workspace / ".env").exists()
        assert not (workspace / ".venv").exists()
        assert not (workspace / "node_modules").exists()

    async def test_directory_workspace_uses_clean_path_when_base_exists(
        self,
        orchestrator,
        monkeypatch,
        tmp_path,
    ):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        (repo_root / "README.md").write_text("app readme", encoding="utf-8")
        workspace_root = tmp_path / "workspaces"
        existing = workspace_root / "task-1"
        existing.mkdir(parents=True)
        (existing / ".agent-builder").mkdir()
        monkeypatch.setattr(orchestrator.settings, "workspace_root", str(workspace_root))

        workspace_info = await orchestrator._provision_workspace_info(
            MagicMock(),
            repo_root,
            "task-1",
        )

        assert Path(workspace_info.path) == workspace_root / "task-1-clean-1"
        assert existing.exists()
        assert not (Path(workspace_info.path) / ".agent-builder").exists()

    async def test_existing_git_worktree_is_sanitized_before_agent_reuse(
        self,
        orchestrator,
        tmp_path,
    ):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        _git(repo_root, "init", "-q", "-b", "main")
        _git(repo_root, "config", "user.email", "test@example.com")
        _git(repo_root, "config", "user.name", "Test")
        (repo_root / "package.json").write_text('{"scripts":{"test":"node --test"}}\n')
        artifact = repo_root / ".agent-builder" / "runtime-artifacts" / "run.jsonl"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("{}\n", encoding="utf-8")
        test_result = repo_root / "test-results" / ".last-run.json"
        test_result.parent.mkdir()
        test_result.write_text("{}\n", encoding="utf-8")
        _git(repo_root, "add", ".")
        _git(repo_root, "commit", "-q", "-m", "tracked runtime artifacts")

        workspace_path = tmp_path / "worktree"
        result = _git(repo_root, "worktree", "add", "-b", "task/test-task-id", str(workspace_path))
        assert result.returncode == 0, result.stderr
        (workspace_path / "node_modules").mkdir()
        (workspace_path / "node_modules" / "dependency.txt").write_text(
            "dependency",
            encoding="utf-8",
        )
        (workspace_path / ".codex").mkdir()
        (workspace_path / ".codex" / "config.toml").write_text("model='test'\n")

        task = _make_task(
            TaskStatus.IMPLEMENTATION,
            workspace_path=str(workspace_path),
            repo_url=str(repo_root),
        )
        task.workspace.is_worktree = True
        task.workspace.branch = "task/test-task-id"

        workspace = await orchestrator._ensure_workspace(task)

        assert workspace.path == str(workspace_path)
        assert not (workspace_path / ".agent-builder").exists()
        assert not (workspace_path / "test-results").exists()
        assert not (workspace_path / "node_modules").exists()
        assert not (workspace_path / ".codex").exists()
        status = _git(workspace_path, "status", "--short").stdout
        assert "D  .agent-builder/runtime-artifacts/run.jsonl" in status
        assert "D  test-results/.last-run.json" in status


@pytest.mark.asyncio
class TestDispatchErrorHandling:
    """Phase errors should mark task FAILED."""

    async def test_phase_exception_marks_failed(self, orchestrator):
        task = _make_task(TaskStatus.PENDING)

        async def _explode(t):
            raise RuntimeError("Agent crashed")

        orchestrator._phase_planning = _explode
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.FAILED
        assert "Agent crashed" in task.blocked_reason

@pytest.mark.asyncio
class TestPlanningPhase:
    """Planning phase creates approval gate on success."""

    @pytest_asyncio.fixture(autouse=True)
    async def _wire_db(self, test_db):
        """Wire session module to test DB so persist_realtime_run_update can write."""
        yield

    async def test_planning_creates_approval_gate(
        self, orchestrator, mock_db, mock_sdk
    ):
        task = _make_task(TaskStatus.PENDING)
        await orchestrator.dispatch(task)
        # db.add should have been called with an ApprovalGate
        added = [
            call.args[0]
            for call in mock_db.add.call_args_list
            if isinstance(call.args[0], ApprovalGate)
        ]
        assert len(added) >= 1
        assert added[0].gate_type == "planning"


@pytest.mark.asyncio
class TestPhaseFailureDiagnostics:
    """Planner/designer error paths must record a real diagnostic, not a NameError."""

    async def test_phase_planning_error_preserves_diagnostic_without_workspace(
        self, orchestrator
    ):
        task = _make_task(TaskStatus.PENDING, workspace_path=None)

        async def _errored_run(*args, **kwargs):
            return RunResult(
                error="planner blew up",
                stop_reason="runtime_error",
                output_text="",
            )

        orchestrator._run_agent = _errored_run
        await orchestrator.dispatch(task)

        assert task.status == TaskStatus.FAILED
        assert task.blocked_reason
        assert "planner blew up" in task.blocked_reason
        assert "NameError" not in task.blocked_reason

    async def test_phase_design_error_preserves_diagnostic_without_workspace(
        self, orchestrator
    ):
        task = _make_task(TaskStatus.DESIGN, workspace_path=None)

        async def _errored_run(*args, **kwargs):
            return RunResult(
                error="designer hit an issue",
                stop_reason="runtime_error",
                output_text="",
            )

        orchestrator._run_agent = _errored_run
        orchestrator._get_last_run = AsyncMock(return_value=None)
        await orchestrator.dispatch(task)

        assert task.status == TaskStatus.FAILED
        assert task.blocked_reason
        assert "designer hit an issue" in task.blocked_reason
        assert "NameError" not in task.blocked_reason
