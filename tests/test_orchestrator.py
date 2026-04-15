"""Tests for orchestrator dispatch logic — status transitions and phase routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import (
    ApprovalGate,
    Task,
    TaskStatus,
)
from autonomous_agent_builder.orchestrator.orchestrator import (
    BLOCKED_STATUSES,
    PHASE_DISPATCH,
    Orchestrator,
)


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


def _make_task(status: TaskStatus) -> Task:
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
    feature = MagicMock()
    feature.project = project
    feature.title = "Test feature"
    task.feature = feature
    task.workspace = MagicMock(path="/tmp/workspace")
    task.agent_runs = []
    task.approval_gates = []
    return task


class TestDispatchTable:
    """Verify the dispatch table maps every dispatchable status."""

    def test_all_dispatchable_statuses_have_handlers(self):
        expected = {
            TaskStatus.PENDING,
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

    async def test_pending_runs_planning(self, orchestrator, mock_sdk):
        task = _make_task(TaskStatus.PENDING)
        await orchestrator.dispatch(task)
        # Planning phase sets DESIGN_REVIEW on success
        assert task.status == TaskStatus.DESIGN_REVIEW

    async def test_planning_runs_planning(self, orchestrator, mock_sdk):
        task = _make_task(TaskStatus.PLANNING)
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.DESIGN_REVIEW

    async def test_design_runs_design(self, orchestrator, mock_sdk):
        task = _make_task(TaskStatus.DESIGN)
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.IMPLEMENTATION

    async def test_implementation_runs_codegen(self, orchestrator, mock_sdk):
        task = _make_task(TaskStatus.IMPLEMENTATION)
        await orchestrator.dispatch(task)
        # Code-gen success → QUALITY_GATES
        assert task.status == TaskStatus.QUALITY_GATES

    async def test_pr_creation_runs_pr_creator(self, orchestrator, mock_sdk):
        task = _make_task(TaskStatus.PR_CREATION)
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.REVIEW_PENDING

    async def test_build_verify_runs_verifier(self, orchestrator, mock_sdk):
        task = _make_task(TaskStatus.BUILD_VERIFY)
        await orchestrator.dispatch(task)
        assert task.status == TaskStatus.DONE


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
