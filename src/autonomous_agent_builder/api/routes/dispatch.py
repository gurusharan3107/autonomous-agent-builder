"""Dispatch route — trigger task through SDLC pipeline."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.api.schemas import DispatchRequest
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import Feature, Task
from autonomous_agent_builder.db.session import get_db, get_session_factory
from autonomous_agent_builder.orchestrator.orchestrator import Orchestrator

router = APIRouter(tags=["dispatch"])


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

    # Run dispatch in background with its own DB session
    # (the request session closes after the response)
    background.add_task(_run_dispatch, data.task_id)

    return {
        "status": "dispatched",
        "task_id": task.id,
        "current_status": task.status.value if hasattr(task.status, "value") else str(task.status),
    }


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
        except Exception as e:
            await db.rollback()
            log.error("dispatch_background_error", task_id=task_id, error=str(e))
