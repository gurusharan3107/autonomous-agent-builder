"""Dispatch and recovery routes for task lifecycle actions."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.api.routes.dashboard_api import (
    publish_approval_snapshot,
    publish_board_snapshot,
)
from autonomous_agent_builder.api.schemas import DispatchRequest, TaskRecoveryResponse
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import ApprovalGate, Feature, Task
from autonomous_agent_builder.db.session import get_db, get_session_factory
from autonomous_agent_builder.orchestrator.orchestrator import Orchestrator
from autonomous_agent_builder.services.task_recovery import recover_failed_task

router = APIRouter(tags=["dispatch"])
_NON_DISPATCHABLE_STATUSES = {
    "design_review",
    "review_pending",
    "blocked",
    "capability_limit",
    "done",
    "failed",
}


@router.post("/dispatch")
async def dispatch_task(
    data: DispatchRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Dispatch a task through the SDLC pipeline.

    The orchestrator runs the task's next phase asynchronously.
    """
    result = await db.execute(
        select(Task)
        .where(Task.id == data.task_id)
        .options(
            selectinload(Task.feature).selectinload(Feature.project),
            selectinload(Task.workspace),
            selectinload(Task.agent_runs),
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task_status = task.status.value if hasattr(task.status, "value") else str(task.status)
    if task_status in _NON_DISPATCHABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "task_not_dispatchable",
                "task_id": task.id,
                "status": task_status,
                "blocked_reason": task.blocked_reason,
                "message": "Task is in a terminal or approval-blocked state and cannot be dispatched.",
            },
        )

    # Run dispatch in background with its own DB session
    # (the request session closes after the response)
    background.add_task(_run_dispatch, data.task_id)

    return {
        "status": "dispatched",
        "task_id": task.id,
        "current_status": task.status.value if hasattr(task.status, "value") else str(task.status),
    }


@router.post("/tasks/{task_id}/recover", response_model=TaskRecoveryResponse)
async def recover_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Reset a failed task to pending so it can be dispatched again."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return await recover_failed_task(task, db)


async def _run_dispatch(task_id: str) -> None:
    """Background task to run orchestrator dispatch with its own DB session."""
    import structlog

    log = structlog.get_logger()
    log.info("dispatch_background_start", task_id=task_id)

    settings = get_settings()
    session_factory = get_session_factory()

    async with session_factory() as db:
        try:
            result = await db.execute(
                select(Task)
                .where(Task.id == task_id)
                .options(
                    selectinload(Task.feature).selectinload(Feature.project),
                    selectinload(Task.workspace),
                    selectinload(Task.agent_runs),
                    selectinload(Task.approval_gates),
                )
            )
            task = result.scalar_one_or_none()
            if not task:
                log.error("dispatch_task_not_found", task_id=task_id)
                return

            orchestrator = Orchestrator(settings, db)
            await orchestrator.dispatch(task)
            await db.commit()
            await publish_board_snapshot(db)

            gate_result = await db.execute(
                select(ApprovalGate.id).where(ApprovalGate.task_id == task_id)
            )
            for gate_id in gate_result.scalars():
                await publish_approval_snapshot(db, gate_id)
        except Exception as e:
            await db.rollback()
            log.error("dispatch_background_error", task_id=task_id, error=str(e))
