"""Deterministic follow-up work selection for builder-owned orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.backlog_items import backlog_item_reaches_board
from autonomous_agent_builder.db.models import (
    Feature,
    Task,
    TaskStatus,
    set_task_status,
)
from autonomous_agent_builder.services.provider_limits import (
    clear_provider_limit,
    provider_limit_is_ready,
    provider_limit_target_status,
)

DISPATCHABLE_STATUSES = {
    TaskStatus.PENDING,
    TaskStatus.PLANNING,
    TaskStatus.DESIGN,
    TaskStatus.IMPLEMENTATION,
    TaskStatus.QUALITY_GATES,
    TaskStatus.PR_CREATION,
    TaskStatus.BUILD_VERIFY,
}

ACTIVE_STATUSES = DISPATCHABLE_STATUSES - {TaskStatus.PENDING}
WORK_IN_PROGRESS_STATUSES = ACTIVE_STATUSES | {
    TaskStatus.BLOCKED,
    TaskStatus.CAPABILITY_LIMIT,
    TaskStatus.DESIGN_REVIEW,
    TaskStatus.REVIEW_PENDING,
}


@dataclass(frozen=True)
class FollowupDecision:
    action: str
    reason: str
    task_id: str | None = None


async def choose_followup_after_dispatch(
    db: AsyncSession,
    completed_task: Task,
    *,
    now: datetime | None = None,
) -> FollowupDecision:
    """Choose one deterministic next task after a dispatch completes.

    Default policy is serial per feature. That keeps the Agent page autonomous
    without starting parallel mutating work unless the product later encodes an
    explicit dependency graph and parallelism policy.
    """
    completed_status = _status(completed_task)
    if completed_status != TaskStatus.DONE:
        provider_task = await _recover_ready_provider_limit_task(
            db,
            completed_task.feature_id,
            now=now,
        )
        if provider_task is not None:
            return FollowupDecision(
                action="dispatch",
                reason="provider_limit_reset",
                task_id=provider_task.id,
            )
        if completed_status in DISPATCHABLE_STATUSES:
            return FollowupDecision(
                action="dispatch",
                reason=f"same_task_next_phase_{completed_status.value}",
                task_id=completed_task.id,
            )
        return FollowupDecision(action="idle", reason=f"task_status_{completed_status.value}")

    provider_task = await _recover_ready_provider_limit_task(
        db,
        completed_task.feature_id,
        now=now,
    )
    if provider_task is not None:
        return FollowupDecision(
            action="dispatch",
            reason="provider_limit_reset",
            task_id=provider_task.id,
        )

    if await _has_open_task(db, completed_task.feature_id, exclude_task_id=completed_task.id):
        return FollowupDecision(action="idle", reason="feature_has_open_task")

    next_task = await _next_pending_task(
        db,
        completed_task.feature_id,
        exclude_task_id=completed_task.id,
    )
    if next_task is None:
        return FollowupDecision(action="idle", reason="feature_complete")
    return FollowupDecision(action="dispatch", reason="next_serial_task", task_id=next_task.id)


async def _recover_ready_provider_limit_task(
    db: AsyncSession,
    feature_id: str,
    *,
    now: datetime | None,
) -> Task | None:
    result = await db.execute(
        select(Task)
        .where(Task.feature_id == feature_id)
        .where(Task.status == TaskStatus.CAPABILITY_LIMIT)
        .order_by(Task.updated_at, Task.created_at)
    )
    for task in result.scalars().all():
        if not provider_limit_is_ready(task, now=now):
            continue
        set_task_status(task, provider_limit_target_status(task))
        clear_provider_limit(task)
        await db.flush()
        return task
    return None


async def _has_open_task(
    db: AsyncSession,
    feature_id: str,
    *,
    exclude_task_id: str,
) -> bool:
    result = await db.execute(
        select(Task.id)
        .where(Task.feature_id == feature_id)
        .where(Task.id != exclude_task_id)
        .where(Task.status.in_(list(WORK_IN_PROGRESS_STATUSES)))
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _next_pending_task(
    db: AsyncSession,
    feature_id: str,
    *,
    exclude_task_id: str,
) -> Task | None:
    result = await db.execute(
        select(Task)
        .where(Task.feature_id == feature_id)
        .where(Task.id != exclude_task_id)
        .where(Task.status.in_(list(DISPATCHABLE_STATUSES)))
        .options(selectinload(Task.feature).selectinload(Feature.project))
        .order_by(Task.created_at)
        .limit(1)
    )
    task = result.scalar_one_or_none()
    if task is None or task.feature is None:
        return None
    feature_status = _feature_status(task.feature)
    if not backlog_item_reaches_board(feature_status):
        return None
    return task


def _status(task: Task) -> TaskStatus:
    status = task.status
    return status if isinstance(status, TaskStatus) else TaskStatus(str(status))


def _feature_status(feature: Feature) -> str:
    status = feature.status
    return status.value if hasattr(status, "value") else str(status)
