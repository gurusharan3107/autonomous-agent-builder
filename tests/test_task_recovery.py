from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autonomous_agent_builder.db.models import Task, TaskPhase, TaskStatus
from autonomous_agent_builder.services.task_recovery import (
    _has_completed_build_verifier,
    _verifier_output_has_failed_check,
    recover_failed_task,
    task_is_recoverable,
)


def _make_task(status: TaskStatus, blocked_reason: str = "") -> Task:
    return Task(
        id="t1",
        feature_id="f1",
        title="t",
        description="d",
        status=status,
        phase=TaskPhase.IMPLEMENTATION,
        blocked_reason=blocked_reason or None,
    )


def test_task_is_recoverable_failed_task_returns_true() -> None:
    assert task_is_recoverable(_make_task(TaskStatus.FAILED)) is True


def test_task_is_recoverable_capability_limit_returns_true() -> None:
    assert task_is_recoverable(_make_task(TaskStatus.CAPABILITY_LIMIT)) is True


def test_task_is_recoverable_blocked_scaffold_failed_returns_true() -> None:
    task = _make_task(TaskStatus.BLOCKED, "scaffold_failed: missing language")
    assert task_is_recoverable(task) is True


def test_task_is_recoverable_blocked_gate_infra_error_returns_true() -> None:
    task = _make_task(
        TaskStatus.BLOCKED,
        "Gate infrastructure error in code_quality, testing (FileNotFoundError).",
    )
    assert task_is_recoverable(task) is True


def test_task_is_recoverable_pending_returns_false() -> None:
    assert task_is_recoverable(_make_task(TaskStatus.PENDING)) is False


def test_task_is_recoverable_blocked_unknown_reason_returns_false() -> None:
    task = _make_task(TaskStatus.BLOCKED, "Waiting on operator decision")
    assert task_is_recoverable(task) is False


@pytest.mark.asyncio
async def test_recover_failed_task_clears_stale_operator_decision() -> None:
    task = Task(
        id="task-1",
        feature_id="feature-1",
        title="Verify feature",
        description="Verify the feature",
        status=TaskStatus.FAILED,
        phase=TaskPhase.IMPLEMENTATION,
        blocked_reason="implementation blocked: stale workspace question",
        depends_on={
            "operator_decision": {
                "phase": "implementation",
                "question": "Use stale workspace output?",
            },
            "phase_context": {"planning_context": "keep this"},
        },
    )
    db = AsyncMock()

    with (
        patch(
            "autonomous_agent_builder.services.task_recovery.publish_board_snapshot",
            new=AsyncMock(),
        ),
        patch(
            "autonomous_agent_builder.services.task_recovery._has_pr_change_request_gate",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "autonomous_agent_builder.services.task_recovery._enriched_final_checkout_failure",
            new=AsyncMock(return_value="npm run build FAIL"),
        ),
    ):
        result = await recover_failed_task(task, db)

    assert result["previous_status"] == "failed"
    assert result["current_status"] == "implementation"
    assert task.status == TaskStatus.IMPLEMENTATION
    assert task.blocked_reason is None
    assert task.depends_on == {"phase_context": {"planning_context": "keep this"}}


@pytest.mark.asyncio
async def test_recover_final_checkout_build_failure_returns_to_implementation() -> None:
    task = Task(
        id="task-1",
        feature_id="feature-1",
        title="Verify feature",
        description="Verify the feature",
        status=TaskStatus.BLOCKED,
        phase=TaskPhase.COMPLETE,
        blocked_reason="final_checkout_build_failed: npm run build FAIL",
    )
    db = AsyncMock()

    with (
        patch(
            "autonomous_agent_builder.services.task_recovery.publish_board_snapshot",
            new=AsyncMock(),
        ),
        patch(
            "autonomous_agent_builder.services.task_recovery._has_pr_change_request_gate",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "autonomous_agent_builder.services.task_recovery._enriched_final_checkout_failure",
            new=AsyncMock(return_value="npm run build FAIL"),
        ),
    ):
        result = await recover_failed_task(task, db)

    assert result["previous_status"] == "blocked"
    assert result["current_status"] == "implementation"
    assert task.status == TaskStatus.IMPLEMENTATION
    assert task.blocked_reason is None
    assert task.depends_on["recovery_context"]["reason"] == (
        "final_checkout_build_failed: npm run build FAIL"
    )
    assert "final materialized checkout" in task.depends_on["recovery_context"]["instruction"]


@pytest.mark.asyncio
async def test_recover_gate_infrastructure_error_returns_to_implementation() -> None:
    # Regression: tasks blocked with the legacy "Gate infrastructure error
    # ... FileNotFoundError" reason were dead-ended at 409 task_not_recoverable.
    # The scaffold step at IMPLEMENTATION entry now handles this — re-running
    # implementation runs scaffold first and registers the matching gate set.
    task = Task(
        id="task-1",
        feature_id="feature-1",
        title="Set up domain model",
        description="...",
        status=TaskStatus.BLOCKED,
        phase=TaskPhase.VERIFICATION,
        blocked_reason=(
            "Gate infrastructure error in code_quality, testing "
            "(FileNotFoundError). Configure the gate or bootstrap the workspace "
            "before retrying."
        ),
    )
    db = AsyncMock()

    with (
        patch(
            "autonomous_agent_builder.services.task_recovery.publish_board_snapshot",
            new=AsyncMock(),
        ),
        patch(
            "autonomous_agent_builder.services.task_recovery._has_pr_change_request_gate",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "autonomous_agent_builder.services.task_recovery._enriched_final_checkout_failure",
            new=AsyncMock(return_value=""),
        ),
    ):
        result = await recover_failed_task(task, db)

    assert result["previous_status"] == "blocked"
    assert result["current_status"] == "implementation"
    assert task.status == TaskStatus.IMPLEMENTATION
    assert task.blocked_reason is None


@pytest.mark.asyncio
async def test_recover_scaffold_failed_returns_to_implementation() -> None:
    task = Task(
        id="task-1",
        feature_id="feature-1",
        title="Set up domain model",
        description="...",
        status=TaskStatus.BLOCKED,
        phase=TaskPhase.IMPLEMENTATION,
        blocked_reason="scaffold_failed: SCAFFOLD_RESULT_JSON missing language",
    )
    db = AsyncMock()

    with (
        patch(
            "autonomous_agent_builder.services.task_recovery.publish_board_snapshot",
            new=AsyncMock(),
        ),
        patch(
            "autonomous_agent_builder.services.task_recovery._has_pr_change_request_gate",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "autonomous_agent_builder.services.task_recovery._enriched_final_checkout_failure",
            new=AsyncMock(return_value=""),
        ),
    ):
        result = await recover_failed_task(task, db)

    assert result["current_status"] == "implementation"
    assert task.status == TaskStatus.IMPLEMENTATION


def test_verifier_output_failed_check_detection() -> None:
    assert _verifier_output_has_failed_check("`npm test` PASS: 8/8 tests") is False
    assert (
        _verifier_output_has_failed_check(
            "`npm test` PASS: 8/8 tests\n`scripts/browser-proof.sh` FAIL: Chrome exited 134"
        )
        is True
    )


@pytest.mark.asyncio
async def test_completed_build_verifier_detection() -> None:
    task = Task(id="task-1", feature_id="feature-1", title="Task", status=TaskStatus.FAILED)
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = "run-1"
    db.execute.return_value = result

    assert await _has_completed_build_verifier(task, db) is True
