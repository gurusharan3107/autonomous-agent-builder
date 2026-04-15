"""Tests for orchestrator quality_gates phase and agent run recording."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import Task, TaskStatus
from autonomous_agent_builder.orchestrator.orchestrator import Orchestrator
from autonomous_agent_builder.quality_gates.base import (
    AggregateGateResult,
    GateResult,
    GateStatus,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def orchestrator(mock_db):
    return Orchestrator(get_settings(), mock_db)


def _make_task(status: TaskStatus = TaskStatus.QUALITY_GATES) -> Task:
    task = Task(
        id="gate-test",
        feature_id="feat-1",
        title="Gate test",
        description="Testing quality gates",
        status=status,
    )
    project = MagicMock()
    project.name = "test"
    project.language = "python"
    feature = MagicMock()
    feature.project = project
    task.feature = feature
    task.workspace = MagicMock(path="/tmp/ws")
    task.agent_runs = []
    task.approval_gates = []
    return task


@pytest.mark.asyncio
class TestQualityGatesPhase:
    """Test _phase_quality_gates dispatching."""

    async def test_all_gates_pass_advances_to_pr(self, orchestrator):
        task = _make_task()
        pass_result = AggregateGateResult(
            status=GateStatus.PASS,
            results=[
                GateResult(
                    gate_name="code_quality",
                    status=GateStatus.PASS,
                    findings_count=0,
                    elapsed_ms=100,
                ),
                GateResult(
                    gate_name="testing",
                    status=GateStatus.PASS,
                    findings_count=0,
                    elapsed_ms=200,
                ),
            ],
        )
        with patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_quality_gates",
            new_callable=AsyncMock,
            return_value=pass_result,
        ):
            await orchestrator._phase_quality_gates(task)
        assert task.status == TaskStatus.PR_CREATION

    async def test_gate_warn_still_advances(self, orchestrator):
        task = _make_task()
        warn_result = AggregateGateResult(
            status=GateStatus.WARN,
            results=[
                GateResult(
                    gate_name="code_quality",
                    status=GateStatus.WARN,
                    findings_count=2,
                    elapsed_ms=100,
                ),
            ],
        )
        with patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_quality_gates",
            new_callable=AsyncMock,
            return_value=warn_result,
        ):
            await orchestrator._phase_quality_gates(task)
        assert task.status == TaskStatus.PR_CREATION

    async def test_gate_fail_triggers_feedback(self, orchestrator):
        task = _make_task()
        fail_result = AggregateGateResult(
            status=GateStatus.FAIL,
            results=[
                GateResult(
                    gate_name="code_quality",
                    status=GateStatus.FAIL,
                    findings_count=5,
                    elapsed_ms=100,
                    error_code="LINT_FAILED",
                ),
            ],
        )
        orchestrator.gate_handler.handle_gate_failure = AsyncMock()
        with patch(
            "autonomous_agent_builder.orchestrator.orchestrator.run_quality_gates",
            new_callable=AsyncMock,
            return_value=fail_result,
        ):
            await orchestrator._phase_quality_gates(task)
        orchestrator.gate_handler.handle_gate_failure.assert_called_once()


@pytest.mark.asyncio
class TestAgentRunRecording:
    """Test _run_agent records AgentRun to DB."""

    async def test_run_agent_saves_agent_run(
        self, orchestrator, mock_db, mock_sdk
    ):
        task = _make_task(TaskStatus.PENDING)
        result = await orchestrator._run_agent(
            task,
            "planner",
            {"feature_description": "test", "project_name": "test", "language": "python"},
        )
        assert result is not None
        assert result.session_id is not None
        # Verify AgentRun was added to DB
        from autonomous_agent_builder.db.models import AgentRun

        added_runs = [
            call.args[0]
            for call in mock_db.add.call_args_list
            if isinstance(call.args[0], AgentRun)
        ]
        assert len(added_runs) >= 1
        assert added_runs[0].agent_name == "planner"
        assert added_runs[0].cost_usd > 0

    async def test_run_agent_error_returns_error_result(
        self, orchestrator, mock_db
    ):
        task = _make_task(TaskStatus.PENDING)

        async def _fail(*args, **kwargs):
            raise RuntimeError("SDK error")

        orchestrator.runner._execute_query = _fail
        result = await orchestrator._run_agent(
            task,
            "planner",
            {"feature_description": "test", "project_name": "test", "language": "python"},
        )
        assert result.error is not None
        assert "SDK error" in result.error
