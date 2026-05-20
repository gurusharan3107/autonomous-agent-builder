"""Task API routes for the embedded server."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.db.models import (
    ApprovalGate,
    Feature,
    Task,
    TaskStatus,
    set_task_status,
    utcnow,
)
from autonomous_agent_builder.db.session import get_db, get_session_factory
from autonomous_agent_builder.services.autonomous_orchestration import (
    choose_followup_after_dispatch,
)
from autonomous_agent_builder.services.dispatch_chain import (
    DispatchChainState,
    mark_repeated_dispatch_state,
    run_dispatch_followup_chain,
)
from autonomous_agent_builder.services.dispatch_lock import (
    is_dispatch_reserved as _is_dispatch_reserved,
)
from autonomous_agent_builder.services.dispatch_lock import (
    release_dispatch as _release_dispatch,
)
from autonomous_agent_builder.services.dispatch_lock import (
    reserve_dispatch as _reserve_dispatch,
)
from autonomous_agent_builder.services.run_reconciliation import mark_task_running_agent_runs_failed
from autonomous_agent_builder.services.task_dispatch_policy import (
    backlog_item_not_queued_detail,
    dispatch_already_running_payload,
    dispatch_started_payload,
    task_feature_reaches_board,
    task_not_dispatchable_detail,
    task_status_blocks_dispatch,
)
from autonomous_agent_builder.services.task_recovery import recover_failed_task

router = APIRouter()
log = structlog.get_logger()


def _task_payload(task: Task) -> dict[str, object]:
    return {
        "id": task.id,
        "feature_id": task.feature_id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value if hasattr(task.status, "value") else str(task.status),
        "phase": task.phase.value if hasattr(task.phase, "value") else str(task.phase),
        "complexity": task.complexity,
        "depends_on": task.depends_on,
        "retry_count": task.retry_count,
        "blocked_reason": task.blocked_reason,
        "blocked_at": task.blocked_at.isoformat() if task.blocked_at else None,
        "capability_limit_at": (
            task.capability_limit_at.isoformat() if task.capability_limit_at else None
        ),
        "capability_limit_reason": task.capability_limit_reason,
        "provider_limit": task_not_dispatchable_detail(task).get("provider_limit"),
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


def _dispatch_failure_reason(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return f"Dispatch failed: {message[:500]}"


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
    if task_status_blocks_dispatch(task):
        raise HTTPException(
            status_code=409,
            detail=task_not_dispatchable_detail(task),
        )
    if not task_feature_reaches_board(task):
        raise HTTPException(
            status_code=409,
            detail=backlog_item_not_queued_detail(task),
        )
    if not _reserve_dispatch(task.id):
        return dispatch_already_running_payload(task)

    background.add_task(_run_dispatch, task.id)

    return dispatch_started_payload(task)


@router.post("/tasks/{task_id}/recover")
async def recover_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Reset a failed task to pending so it can be dispatched again."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return await recover_failed_task(task, db)


async def _run_dispatch(task_id: str) -> None:
    await run_dispatch_followup_chain(
        task_id,
        run_step=_run_dispatch_step,
        block_chain=_block_dispatch_chain,
    )


async def _run_dispatch_step(task_id: str, chain_state: DispatchChainState) -> str | None:
    from autonomous_agent_builder.api.routes.dashboard_api import (
        publish_approval_snapshot,
        publish_board_snapshot,
    )
    from autonomous_agent_builder.config import get_settings
    from autonomous_agent_builder.orchestrator.orchestrator import Orchestrator

    if not _is_dispatch_reserved(task_id) and not _reserve_dispatch(task_id):
        log.info("embedded_dispatch_already_running", task_id=task_id)
        return

    settings = get_settings()
    session_factory = get_session_factory()
    followup_task_id: str | None = None

    try:
        async with session_factory() as db:
            committed = False
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
                    return None
                cycle_reason = mark_repeated_dispatch_state(task, chain_state)
                if cycle_reason:
                    log.error(
                        "embedded_dispatch_followup_cycle",
                        task_id=task_id,
                        status=task.status.value,
                    )
                    await db.commit()
                    await publish_board_snapshot(db)
                    return None

                orchestrator = Orchestrator(settings, db)
                await orchestrator.dispatch(task)
                followup = await choose_followup_after_dispatch(db, task)
                if followup.action == "dispatch" and followup.task_id:
                    followup_task_id = followup.task_id
                    log.info(
                        "embedded_dispatch_followup_selected",
                        task_id=task_id,
                        followup_task_id=followup_task_id,
                        reason=followup.reason,
                    )
                await db.commit()
                committed = True
                await publish_board_snapshot(db)

                gate_result = await db.execute(
                    select(ApprovalGate.id).where(ApprovalGate.task_id == task_id)
                )
                for gate_id in gate_result.scalars():
                    await publish_approval_snapshot(db, gate_id)
            except Exception as exc:
                await db.rollback()
                log.error("embedded_dispatch_background_error", task_id=task_id, error=str(exc))
                if not committed:
                    followup_task_id = None
                    await _block_dispatch_chain(task_id, _dispatch_failure_reason(exc))
    finally:
        _release_dispatch(task_id)
    return followup_task_id


async def _block_dispatch_chain(task_id: str, reason: str) -> None:
    from autonomous_agent_builder.api.routes.dashboard_api import publish_board_snapshot

    session_factory = get_session_factory()
    async with session_factory() as db:
        task = await db.get(Task, task_id)
        if task is None:
            log.error("embedded_dispatch_chain_block_task_not_found", task_id=task_id)
            return
        _mark_task_blocked(task, reason)
        await mark_task_running_agent_runs_failed(
            db,
            task_id,
            reason,
            event_reason="dispatch_failure_blocked",
        )
        log.error("embedded_dispatch_chain_blocked", task_id=task_id, reason=reason)
        await db.commit()
        await publish_board_snapshot(db)


def _mark_task_blocked(task: Task, reason: str) -> None:
    set_task_status(task, TaskStatus.BLOCKED)
    task.blocked_reason = reason
    task.blocked_at = utcnow()
