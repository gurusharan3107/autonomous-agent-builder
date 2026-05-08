"""Tests for gate feedback handler — retry loop and CAPABILITY_LIMIT."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import Task, TaskStatus
from autonomous_agent_builder.orchestrator.gate_feedback import GateFeedbackHandler
from autonomous_agent_builder.quality_gates.base import (
    AggregateGateResult,
    GateResult,
    GateStatus,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def handler(mock_db):
    settings = get_settings()
    return GateFeedbackHandler(settings, mock_db)


def _make_task(retry_count: int = 0) -> Task:
    task = Task(
        id="gate-task",
        feature_id="gate-feature",
        title="Gate test task",
        description="Testing gates",
        status=TaskStatus.QUALITY_GATES,
    )
    task.retry_count = retry_count
    project = MagicMock()
    project.language = "python"
    feature = MagicMock()
    feature.project = project
    task.feature = feature
    task.workspace = MagicMock(path="/tmp/ws")
    return task


def _make_gate_result(
    status: GateStatus = GateStatus.FAIL,
    gate_name: str = "code_quality",
    remediation_possible: bool = False,
) -> GateResult:
    return GateResult(
        gate_name=gate_name,
        status=status,
        findings_count=3,
        elapsed_ms=500,
        evidence={"findings": [{"message": "Line too long"}]},
        error_code="LINT_FAILED" if status == GateStatus.FAIL else None,
        remediation_possible=remediation_possible,
    )


def _make_aggregate(
    results: list[GateResult] | None = None,
) -> AggregateGateResult:
    if results is None:
        results = [_make_gate_result()]
    has_fail = any(r.status == GateStatus.FAIL for r in results)
    overall = GateStatus.FAIL if has_fail else GateStatus.PASS
    return AggregateGateResult(status=overall, results=results)


@pytest.mark.asyncio
class TestRetryBudget:
    """Test retry count logic."""

    async def test_first_failure_increments_retry(self, handler):
        task = _make_task(retry_count=0)
        gate_result = _make_aggregate()
        await handler.handle_gate_failure(task, gate_result)
        assert task.retry_count == 1
        assert task.status == TaskStatus.IMPLEMENTATION

    async def test_second_failure_increments_retry(self, handler):
        task = _make_task(retry_count=1)
        gate_result = _make_aggregate()
        await handler.handle_gate_failure(task, gate_result)
        assert task.retry_count == 2
        assert task.status == TaskStatus.IMPLEMENTATION

    async def test_max_retries_escalates_to_capability_limit(self, handler):
        task = _make_task(retry_count=2)
        gate_result = _make_aggregate()
        await handler.handle_gate_failure(task, gate_result)
        assert task.status == TaskStatus.CAPABILITY_LIMIT


@pytest.mark.asyncio
class TestCapabilityLimit:
    """Test CAPABILITY_LIMIT escalation."""

    async def test_sets_capability_limit_fields(self, handler):
        task = _make_task(retry_count=2)
        gate_result = _make_aggregate()
        await handler.handle_gate_failure(task, gate_result)
        assert task.capability_limit_at is not None
        assert task.capability_limit_reason is not None
        assert task.dead_letter_queued_at is not None

    async def test_capability_limit_reason_contains_gate_name(self, handler):
        task = _make_task(retry_count=2)
        gate_result = _make_aggregate()
        await handler.handle_gate_failure(task, gate_result)
        assert "code_quality" in task.capability_limit_reason


@pytest.mark.asyncio
class TestRemediation:
    """Test auto-remediation path."""

    async def test_remediable_gate_triggers_remediation(self, handler):
        task = _make_task(retry_count=0)
        gate = _make_gate_result(remediation_possible=True)
        gate_result = _make_aggregate([gate])

        handler._attempt_remediation = AsyncMock(return_value=True)
        await handler.handle_gate_failure(task, gate_result)

        handler._attempt_remediation.assert_called_once()
        assert task.status == TaskStatus.QUALITY_GATES

    async def test_failed_remediation_falls_to_retry(self, handler):
        task = _make_task(retry_count=0)
        gate = _make_gate_result(remediation_possible=True)
        gate_result = _make_aggregate([gate])

        handler._attempt_remediation = AsyncMock(return_value=False)
        await handler.handle_gate_failure(task, gate_result)

        assert task.retry_count == 1
        assert task.status == TaskStatus.IMPLEMENTATION


@pytest.mark.asyncio
class TestGateFeedbackFormat:
    """Test feedback formatting for code-gen agent."""

    async def test_retry_sets_blocked_reason(self, handler):
        task = _make_task(retry_count=0)
        gate_result = _make_aggregate()
        await handler.handle_gate_failure(task, gate_result)
        assert "Quality gate failures" in task.blocked_reason
        assert "code_quality" in task.blocked_reason

    async def test_feedback_includes_error_code(self, handler):
        task = _make_task(retry_count=0)
        gate_result = _make_aggregate()
        await handler.handle_gate_failure(task, gate_result)
        assert "LINT_FAILED" in task.blocked_reason

    async def test_feedback_includes_findings(self, handler):
        task = _make_task(retry_count=0)
        gate_result = _make_aggregate()
        await handler.handle_gate_failure(task, gate_result)
        assert "Line too long" in task.blocked_reason

    def test_format_gate_feedback_multiple_gates(self, handler):
        results = [
            _make_gate_result(gate_name="code_quality"),
            _make_gate_result(gate_name="testing"),
        ]
        aggregate = _make_aggregate(results)
        feedback = handler._format_gate_feedback(aggregate)
        assert "code_quality" in feedback
        assert "testing" in feedback


@pytest.mark.asyncio
class TestAttemptRemediation:
    """Test _attempt_remediation method."""

    async def test_remediation_success(self, handler):
        task = _make_task()
        gate = _make_gate_result(remediation_possible=True)

        mock_gate_instance = AsyncMock()
        mock_gate_instance.remediate = AsyncMock(return_value=True)
        handler._get_gate_instance = MagicMock(return_value=mock_gate_instance)

        result = await handler._attempt_remediation(task, [gate])
        assert result is True
        mock_gate_instance.remediate.assert_called_once()

    async def test_remediation_failure(self, handler):
        task = _make_task()
        gate = _make_gate_result(remediation_possible=True)

        mock_gate_instance = AsyncMock()
        mock_gate_instance.remediate = AsyncMock(return_value=False)
        handler._get_gate_instance = MagicMock(return_value=mock_gate_instance)

        result = await handler._attempt_remediation(task, [gate])
        assert result is False

    async def test_remediation_exception_handled(self, handler):
        task = _make_task()
        gate = _make_gate_result(remediation_possible=True)

        mock_gate_instance = AsyncMock()
        mock_gate_instance.remediate = AsyncMock(
            side_effect=RuntimeError("remediation crashed")
        )
        handler._get_gate_instance = MagicMock(return_value=mock_gate_instance)

        result = await handler._attempt_remediation(task, [gate])
        assert result is False

    async def test_unknown_gate_skipped(self, handler):
        task = _make_task()
        gate = _make_gate_result(
            gate_name="nonexistent", remediation_possible=True
        )
        handler._get_gate_instance = MagicMock(return_value=None)

        result = await handler._attempt_remediation(task, [gate])
        assert result is False


class TestGetGateInstance:
    """Test gate instance factory."""

    def test_code_quality_gate(self, handler):
        task = _make_task()
        gate = handler._get_gate_instance("code_quality", task)
        assert gate is not None

    def test_testing_gate(self, handler):
        task = _make_task()
        gate = handler._get_gate_instance("testing", task)
        assert gate is not None

    def test_security_gate(self, handler):
        task = _make_task()
        gate = handler._get_gate_instance("security", task)
        assert gate is not None

    def test_unknown_gate_returns_none(self, handler):
        task = _make_task()
        gate = handler._get_gate_instance("nonexistent", task)
        assert gate is None
