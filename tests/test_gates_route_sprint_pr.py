"""Sprint-PR refactor (Phase D) — gates route fans sprint_pr decisions to the sprint helper."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autonomous_agent_builder.api.routes.gates import submit_approval
from autonomous_agent_builder.api.schemas import ApprovalCreate
from autonomous_agent_builder.db.models import (
    ApprovalDecision,
    ApprovalGate,
    Sprint,
    SprintPhase,
    Task,
    TaskStatus,
)
from autonomous_agent_builder.embedded.server.routes.gates import (
    submit_approval as embedded_submit_approval,
)


def _approval_create(decision: str, *, reason: str = "") -> ApprovalCreate:
    return ApprovalCreate(
        decision=decision,
        approver_email="op@example.com",
        comment="comment",
        reason=reason,
    )


def _embedded_approval_data(decision: str, *, reason: str = "") -> dict[str, str]:
    return {
        "decision": decision,
        "approver_email": "op@example.com",
        "comment": "comment",
        "reason": reason,
    }


@pytest.mark.asyncio
async def test_sprint_pr_approve_routes_to_apply_sprint_approval_outcome():
    """A sprint_pr gate must call ``apply_sprint_approval_outcome`` and skip the per-task path."""
    sprint = Sprint(
        id="sprint-1",
        project_id="p",
        label="Sprint 1",
        phase=SprintPhase.PR_REVIEW,
        generated_task_ids=["task-1"],
    )
    sprint.verification_evidence = {}
    task = Task(id="task-1", feature_id="f", title="t", description="d", status=TaskStatus.DONE)

    gate = ApprovalGate(
        id="gate-1",
        task_id=None,
        sprint_id=sprint.id,
        gate_type="sprint_pr",
        status="pending",
        created_at=datetime.now(UTC),
    )

    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    # ``db.get`` is awaited for ApprovalGate, Sprint, and (in the per-task path) Task.
    async def _db_get(model, ident):
        if model is ApprovalGate:
            return gate
        if model is Sprint:
            return sprint
        if model is Task:
            return task
        return None

    db.get = AsyncMock(side_effect=_db_get)

    # ``db.execute`` returns sprint tasks via ``select(Task).where(...)``.
    async def _db_execute(_stmt):
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [task]
        result.scalars.return_value = scalars
        return result

    db.execute = AsyncMock(side_effect=_db_execute)

    background = MagicMock()
    background.add_task = MagicMock()

    with (
        patch(
            "autonomous_agent_builder.api.routes.gates.publish_board_snapshot",
            new=AsyncMock(),
        ),
        patch(
            "autonomous_agent_builder.api.routes.gates.publish_approval_snapshot",
            new=AsyncMock(),
        ),
        patch(
            "autonomous_agent_builder.services.approval_resolution.apply_sprint_approval_outcome",
            wraps=__import__(
                "autonomous_agent_builder.orchestrator.orchestrator",
                fromlist=["apply_sprint_approval_outcome"],
            ).apply_sprint_approval_outcome,
        ) as sprint_helper_spy,
        patch(
            "autonomous_agent_builder.services.approval_resolution.apply_approval_outcome"
        ) as task_helper_spy,
    ):
        response = await submit_approval(
            "gate-1",
            _approval_create(ApprovalDecision.APPROVE.value),
            background,
            db=db,
        )

    assert response == {"status": "ok", "gate_status": ApprovalDecision.APPROVE.value}
    sprint_helper_spy.assert_called_once()
    task_helper_spy.assert_not_called()
    assert sprint.phase == SprintPhase.SHIPPED


@pytest.mark.asyncio
async def test_sprint_pr_request_changes_redispatches_sprint_tasks():
    sprint = Sprint(
        id="sprint-2",
        project_id="p",
        label="Sprint 2",
        phase=SprintPhase.PR_REVIEW,
        generated_task_ids=["task-1", "task-2"],
    )
    sprint.verification_evidence = {}
    tasks = [
        Task(id="task-1", feature_id="f", title="a", description="d", status=TaskStatus.DONE),
        Task(id="task-2", feature_id="f", title="b", description="d", status=TaskStatus.DONE),
    ]
    gate = ApprovalGate(
        id="gate-2",
        task_id=None,
        sprint_id=sprint.id,
        gate_type="sprint_pr",
        status="pending",
        created_at=datetime.now(UTC),
    )
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    by_id = {"task-1": tasks[0], "task-2": tasks[1]}

    async def _db_get(model, ident):
        if model is ApprovalGate:
            return gate
        if model is Sprint:
            return sprint
        if model is Task:
            return by_id.get(ident)
        return None

    db.get = AsyncMock(side_effect=_db_get)

    async def _db_execute(_stmt):
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = tasks
        result.scalars.return_value = scalars
        return result

    db.execute = AsyncMock(side_effect=_db_execute)

    background = MagicMock()
    background.add_task = MagicMock()

    with (
        patch(
            "autonomous_agent_builder.api.routes.gates.publish_board_snapshot",
            new=AsyncMock(),
        ),
        patch(
            "autonomous_agent_builder.api.routes.gates.publish_approval_snapshot",
            new=AsyncMock(),
        ),
        patch(
            "autonomous_agent_builder.api.routes.gates.reserve_dispatch",
            return_value=True,
        ),
    ):
        await submit_approval(
            "gate-2",
            _approval_create(ApprovalDecision.REQUEST_CHANGES.value, reason="fix tests"),
            background,
            db=db,
        )

    # Both sprint tasks should have been re-dispatched.
    dispatched_ids = sorted(call.args[1] for call in background.add_task.call_args_list)
    assert dispatched_ids == ["task-1", "task-2"]
    # Sprint phase rolled back to VERIFY for the re-implementation cycle.
    assert sprint.phase == SprintPhase.VERIFY
    # Tasks reset to IMPLEMENTATION.
    assert all(t.status == TaskStatus.IMPLEMENTATION for t in tasks)


@pytest.mark.asyncio
async def test_per_task_pr_gate_path_unchanged_for_legacy_gates():
    """Per-task gate (sprint_id is None) keeps the existing helper path."""
    task = Task(
        id="task-x",
        feature_id="f",
        title="t",
        description="d",
        status=TaskStatus.REVIEW_PENDING,
    )
    gate = ApprovalGate(
        id="gate-x",
        task_id="task-x",
        sprint_id=None,
        gate_type="pr",
        status="pending",
        created_at=datetime.now(UTC),
    )
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    async def _db_get(model, ident):
        if model is ApprovalGate:
            return gate
        if model is Task:
            return task
        return None

    db.get = AsyncMock(side_effect=_db_get)
    background = MagicMock()
    background.add_task = MagicMock()

    with (
        patch(
            "autonomous_agent_builder.api.routes.gates.publish_board_snapshot",
            new=AsyncMock(),
        ),
        patch(
            "autonomous_agent_builder.api.routes.gates.publish_approval_snapshot",
            new=AsyncMock(),
        ),
        patch(
            "autonomous_agent_builder.services.approval_resolution.apply_sprint_approval_outcome"
        ) as sprint_helper_spy,
        patch(
            "autonomous_agent_builder.services.approval_resolution.apply_approval_outcome"
        ) as task_helper_spy,
    ):
        task_helper_spy.return_value = False
        await submit_approval(
            "gate-x",
            _approval_create(ApprovalDecision.APPROVE.value),
            background,
            db=db,
        )

    sprint_helper_spy.assert_not_called()
    task_helper_spy.assert_called_once()


@pytest.mark.asyncio
async def test_embedded_sprint_pr_approve_applies_sprint_outcome():
    """Embedded sprint_pr approvals must take the same sprint-level path as the API route."""
    sprint = Sprint(
        id="sprint-embedded-1",
        project_id="p",
        label="Sprint 1",
        phase=SprintPhase.PR_REVIEW,
        generated_task_ids=["task-1"],
    )
    sprint.verification_evidence = {}
    task = Task(id="task-1", feature_id="f", title="t", description="d", status=TaskStatus.DONE)
    gate = ApprovalGate(
        id="gate-embedded-1",
        task_id=None,
        sprint_id=sprint.id,
        gate_type="sprint_pr",
        status="pending",
        created_at=datetime.now(UTC),
    )

    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()

    async def _db_get(model, ident):
        if model is ApprovalGate:
            return gate
        if model is Sprint:
            return sprint
        if model is Task:
            return task
        return None

    db.get = AsyncMock(side_effect=_db_get)

    async def _db_execute(_stmt):
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = [task]
        result.scalars.return_value = scalars
        return result

    db.execute = AsyncMock(side_effect=_db_execute)

    background = MagicMock()
    background.add_task = MagicMock()

    with (
        patch(
            "autonomous_agent_builder.embedded.server.routes.gates.publish_board_snapshot",
            new=AsyncMock(),
        ),
        patch(
            "autonomous_agent_builder.embedded.server.routes.gates.publish_approval_snapshot",
            new=AsyncMock(),
        ),
        patch(
            "autonomous_agent_builder.services.approval_resolution.apply_approval_outcome"
        ) as task_helper_spy,
    ):
        response = await embedded_submit_approval(
            "gate-embedded-1",
            _embedded_approval_data(ApprovalDecision.APPROVE.value, reason="ship it"),
            background,
            db=db,
        )

    assert response == {"status": "ok", "gate_status": ApprovalDecision.APPROVE.value}
    assert sprint.phase == SprintPhase.SHIPPED
    assert "sprint_pr_approved_at" in sprint.verification_evidence
    task_helper_spy.assert_not_called()
    background.add_task.assert_not_called()


@pytest.mark.asyncio
async def test_embedded_sprint_pr_request_changes_redispatches_sprint_tasks():
    """Embedded sprint_pr request-changes must reset and dispatch generated tasks."""
    sprint = Sprint(
        id="sprint-embedded-2",
        project_id="p",
        label="Sprint 2",
        phase=SprintPhase.PR_REVIEW,
        generated_task_ids=["task-1", "task-2"],
    )
    sprint.verification_evidence = {}
    tasks = [
        Task(id="task-1", feature_id="f", title="t1", description="d", status=TaskStatus.DONE),
        Task(id="task-2", feature_id="f", title="t2", description="d", status=TaskStatus.DONE),
    ]
    gate = ApprovalGate(
        id="gate-embedded-2",
        task_id=None,
        sprint_id=sprint.id,
        gate_type="sprint_pr",
        status="pending",
        created_at=datetime.now(UTC),
    )

    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    by_id = {task.id: task for task in tasks}

    async def _db_get(model, ident):
        if model is ApprovalGate:
            return gate
        if model is Sprint:
            return sprint
        if model is Task:
            return by_id.get(ident)
        return None

    db.get = AsyncMock(side_effect=_db_get)

    async def _db_execute(_stmt):
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = tasks
        result.scalars.return_value = scalars
        return result

    db.execute = AsyncMock(side_effect=_db_execute)

    background = MagicMock()
    background.add_task = MagicMock()

    with (
        patch(
            "autonomous_agent_builder.embedded.server.routes.gates.publish_board_snapshot",
            new=AsyncMock(),
        ),
        patch(
            "autonomous_agent_builder.embedded.server.routes.gates.publish_approval_snapshot",
            new=AsyncMock(),
        ),
        patch(
            "autonomous_agent_builder.embedded.server.routes.gates.reserve_dispatch",
            return_value=True,
        ),
    ):
        await embedded_submit_approval(
            "gate-embedded-2",
            _embedded_approval_data(ApprovalDecision.REQUEST_CHANGES.value, reason="fix tests"),
            background,
            db=db,
        )

    dispatched_ids = sorted(call.args[1] for call in background.add_task.call_args_list)
    assert dispatched_ids == ["task-1", "task-2"]
    assert sprint.phase == SprintPhase.VERIFY
    assert all(task.status == TaskStatus.IMPLEMENTATION for task in tasks)
