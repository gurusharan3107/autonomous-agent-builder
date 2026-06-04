"""Dispatch and recovery routes for task lifecycle actions."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.api.routes.dashboard_api import (
    publish_approval_snapshot,
    publish_board_snapshot,
)
from autonomous_agent_builder.api.schemas import DispatchRequest, TaskRecoveryResponse
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import (
    ApprovalGate,
    Feature,
    Task,
    TaskStatus,
    set_task_status,
    utcnow,
)
from autonomous_agent_builder.db.session import get_db, get_session_factory
from autonomous_agent_builder.orchestrator.orchestrator import Orchestrator
from autonomous_agent_builder.services.autonomous_orchestration import (
    choose_followup_after_dispatch,
)
from autonomous_agent_builder.services.dispatch_chain import (
    DispatchChainState,
    mark_repeated_dispatch_state,
    run_dispatch_followup_chain,
)
from autonomous_agent_builder.services.dispatch_lock import (
    is_dispatch_reserved,
    release_dispatch,
    reserve_dispatch,
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

# P18b (2026-05-24): SQLite WAL writer contention can hold the write lock
# during the outermost dispatch step commit (`await db.commit()` at the end
# of _run_dispatch_step). P18's fix covers persist_realtime_run_update; this
# covers the dispatch phase-transition commit. Same exponential-backoff recipe.
_DISPATCH_DB_LOCK_RETRY_ATTEMPTS = 5
_DISPATCH_DB_LOCK_RETRY_BASE_SECONDS = 0.5

router = APIRouter(tags=["dispatch"])


def _dispatch_failure_reason(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return f"Dispatch failed: {message[:500]}"


async def _block_failed_dispatch(task_id: str, reason: str) -> None:
    import structlog

    log = structlog.get_logger()
    session_factory = get_session_factory()
    async with session_factory() as db:
        task = await db.get(Task, task_id)
        if task is None:
            log.error("dispatch_block_failed_task_not_found", task_id=task_id)
            return
        set_task_status(task, TaskStatus.BLOCKED)
        task.blocked_reason = reason
        task.blocked_at = utcnow()
        await mark_task_running_agent_runs_failed(
            db,
            task_id,
            reason,
            event_reason="dispatch_failure_blocked",
        )
        await db.commit()
        await publish_board_snapshot(db)


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
    if not reserve_dispatch(task.id):
        return dispatch_already_running_payload(task)

    # Run dispatch in background with its own DB session
    # (the request session closes after the response)
    background.add_task(_run_dispatch, data.task_id)

    return dispatch_started_payload(task)


@router.post("/tasks/{task_id}/recover", response_model=TaskRecoveryResponse)
async def recover_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Reset a failed task to pending so it can be dispatched again."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return await recover_failed_task(task, db)


async def _run_dispatch(task_id: str) -> None:
    """Background task to run orchestrator dispatch with its own DB session."""
    await run_dispatch_followup_chain(
        task_id,
        run_step=_run_dispatch_step,
        block_chain=_block_failed_dispatch,
    )


async def _run_dispatch_step(task_id: str, chain_state: DispatchChainState) -> str | None:
    """Run one dispatch step and return the next follow-up task, if any."""
    import structlog

    log = structlog.get_logger()
    log.info("dispatch_background_start", task_id=task_id)
    followup_task_id: str | None = None

    if not is_dispatch_reserved(task_id) and not reserve_dispatch(task_id):
        log.info("dispatch_already_running", task_id=task_id)
        return

    settings = get_settings()
    session_factory = get_session_factory()

    try:
        for attempt in range(_DISPATCH_DB_LOCK_RETRY_ATTEMPTS):
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
                        log.error("dispatch_task_not_found", task_id=task_id)
                        return

                    cycle_reason = mark_repeated_dispatch_state(task, chain_state)
                    if cycle_reason:
                        log.error(
                            "dispatch_followup_cycle",
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
                            "dispatch_followup_selected",
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
                    break  # success
                except OperationalError as oe:
                    await db.rollback()
                    msg = str(oe).lower()
                    if "database is locked" in msg and attempt + 1 < _DISPATCH_DB_LOCK_RETRY_ATTEMPTS and not committed:
                        backoff = _DISPATCH_DB_LOCK_RETRY_BASE_SECONDS * (2 ** attempt)
                        log.warning(
                            "dispatch_db_lock_retry",
                            task_id=task_id,
                            attempt=attempt + 1,
                            max_attempts=_DISPATCH_DB_LOCK_RETRY_ATTEMPTS,
                            backoff_seconds=backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue
                    log.error("dispatch_background_error", task_id=task_id, error=str(oe))
                    if not committed:
                        followup_task_id = None
                        await _block_failed_dispatch(task_id, _dispatch_failure_reason(oe))
                    break
                except Exception as e:
                    await db.rollback()
                    log.error("dispatch_background_error", task_id=task_id, error=str(e))
                    if not committed:
                        followup_task_id = None
                        await _block_failed_dispatch(task_id, _dispatch_failure_reason(e))
                    break
    finally:
        release_dispatch(task_id)
    return followup_task_id
