from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autonomous_agent_builder.db.models import Task, TaskPhase, TaskStatus
from autonomous_agent_builder.services.task_recovery import (
    _has_completed_build_verifier,
    _verifier_output_has_failed_check,
    recover_failed_task,
)


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

    with patch(
        "autonomous_agent_builder.services.task_recovery.publish_board_snapshot",
        new=AsyncMock(),
    ):
        result = await recover_failed_task(task, db)

    assert result["previous_status"] == "failed"
    assert result["current_status"] == "implementation"
    assert task.status == TaskStatus.IMPLEMENTATION
    assert task.blocked_reason is None
    assert task.depends_on == {"phase_context": {"planning_context": "keep this"}}


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
