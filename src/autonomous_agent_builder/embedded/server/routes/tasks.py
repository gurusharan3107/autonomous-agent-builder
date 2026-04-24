"""Task API routes for the embedded server."""

from __future__ import annotations

import structlog

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.db.models import ApprovalGate, Feature, Task
from autonomous_agent_builder.db.session import get_db, get_session_factory
from autonomous_agent_builder.services.task_recovery import recover_failed_task

router = APIRouter()
log = structlog.get_logger()
_NON_DISPATCHABLE_STATUSES = {
    "design_review",
    "review_pending",
    "blocked",
    "capability_limit",
    "done",
    "failed",
}


def _task_payload(task: Task) -> dict[str, object]:
    return {
        "id": task.id,
        "feature_id": task.feature_id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value if hasattr(task.status, "value") else str(task.status),
        "complexity": task.complexity,
        "depends_on": task.depends_on,
        "retry_count": task.retry_count,
        "blocked_reason": task.blocked_reason,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


@router.get("/tasks")
async def list_tasks(db: AsyncSession = Depends(get_db)):
    """List all tasks for the current project."""
    result = await db.execute(select(Task).order_by(Task.created_at.desc()))
    return [_task_payload(task) for task in result.scalars().all()]


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Return one task by ID."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_payload(task)


@router.post("/tasks/{task_id}/dispatch")
async def dispatch_task(
    task_id: str,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Dispatch a task through the orchestrator."""
    result = await db.execute(
        select(Task)
        .where(Task.id == task_id)
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

    background.add_task(_run_dispatch, task.id)

    return {
        "task_id": task.id,
        "status": "dispatched",
        "current_status": task.status.value if hasattr(task.status, "value") else str(task.status),
    }


@router.post("/tasks/{task_id}/recover")
async def recover_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Reset a failed task to pending so it can be dispatched again."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return await recover_failed_task(task, db)


async def _run_dispatch(task_id: str) -> None:
    from autonomous_agent_builder.api.routes.dashboard_api import (
        publish_approval_snapshot,
        publish_board_snapshot,
    )
    from autonomous_agent_builder.config import get_settings
    from autonomous_agent_builder.orchestrator.orchestrator import Orchestrator

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
                log.error("embedded_dispatch_task_not_found", task_id=task_id)
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
        except Exception as exc:
            await db.rollback()
            log.error("embedded_dispatch_background_error", task_id=task_id, error=str(exc))
