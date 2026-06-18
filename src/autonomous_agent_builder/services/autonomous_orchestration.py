"""Deterministic follow-up work selection for builder-owned orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.backlog_items import backlog_item_reaches_board
from autonomous_agent_builder.db.models import (
    Feature,
    Sprint,
    SprintPhase,
    Task,
    TaskStatus,
    set_task_status,
)
from autonomous_agent_builder.services.provider_limits import (
    clear_provider_limit,
    provider_limit_is_ready,
    provider_limit_target_status,
)

log = structlog.get_logger()

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


async def _maybe_mark_sprint_stalled(
    db: AsyncSession,
    trigger_task: Task,
) -> bool:
    """Detect and resolve sprint implementation deadlock (P23 + 2026-05-29).

    When a task reaches a non-recoverable terminal state (FAILED, or BLOCKED
    needing an operator decision such as `quality_gate_cap_exceeded`) and the
    owning sprint still shows phase=implementation with no tasks left in active
    dispatch states, the orchestrator will never re-enter the dispatch loop —
    the dependent PENDING tasks can't run and nothing escalates. Transition the
    sprint to phase=blocked so the session reaches a terminal state the harness
    and dashboard can evaluate, instead of going silent until the watchdog.

    Stall condition: all sprint tasks are in {failed, pending, done, blocked}
    AND at least one is failed-or-blocked AND at least one is pending. Skips if
    any task is still actively dispatching or in a genuinely recoverable state
    (capability_limit → provider-limit reset, review_pending → approval).

    2026-05-29 (fuzzer-caught fixture-D hang): BLOCKED was previously assumed
    "has a path to progress" and excluded — but a `quality_gate_cap_exceeded`
    block has NO autonomous path, so the sprint quiesced silently. BLOCKED now
    counts as a stall trigger alongside FAILED.
    """
    result = await db.execute(
        select(Sprint).where(Sprint.phase == SprintPhase.IMPLEMENTATION)
    )
    sprints = result.scalars().all()

    sprint: Sprint | None = None
    for s in sprints:
        if trigger_task.feature_id in (s.approved_feature_ids or []):
            sprint = s
            break
    if sprint is None:
        return False

    task_ids = sprint.generated_task_ids or []
    if not task_ids:
        return False

    result = await db.execute(select(Task).where(Task.id.in_(task_ids)))
    sprint_tasks = result.scalars().all()
    if not sprint_tasks:
        return False

    # Only fire when every task is in a terminal-or-waiting state. An active
    # task, or one in a genuinely recoverable state (capability_limit →
    # provider reset, review_pending → approval), still has a path to progress.
    # BLOCKED is terminal-without-operator and DOES count (see docstring).
    _TERMINAL_OR_WAITING = {  # noqa: N806
        TaskStatus.FAILED, TaskStatus.PENDING, TaskStatus.DONE, TaskStatus.BLOCKED,
    }
    for task in sprint_tasks:
        ts = task.status if isinstance(task.status, TaskStatus) else TaskStatus(str(task.status))
        if ts not in _TERMINAL_OR_WAITING:
            return False

    def _is(t: Task, status: TaskStatus) -> bool:
        return (t.status if isinstance(t.status, TaskStatus) else TaskStatus(str(t.status))) == status

    failed_ids = [t.id for t in sprint_tasks if _is(t, TaskStatus.FAILED)]
    blocked_ids = [t.id for t in sprint_tasks if _is(t, TaskStatus.BLOCKED)]
    pending_ids = [t.id for t in sprint_tasks if _is(t, TaskStatus.PENDING)]
    if not (failed_ids or blocked_ids) or not pending_ids:
        return False

    sprint.phase = SprintPhase.BLOCKED
    sprint.verification_status = "blocked"
    sprint.verification_evidence = {
        "blocked_reason": "all_active_tasks_failed_or_blocked",
        "failed_task_ids": failed_ids,
        "blocked_task_ids": blocked_ids,
        "pending_task_ids": pending_ids,
    }
    await db.flush()
    log.info(
        "sprint_implementation_stall_detected",
        sprint_id=sprint.id,
        failed_count=len(failed_ids),
        blocked_count=len(blocked_ids),
        pending_count=len(pending_ids),
    )
    return True


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
        if completed_status in (TaskStatus.FAILED, TaskStatus.BLOCKED):
            # BLOCKED needing an operator (e.g. quality_gate_cap_exceeded) has no
            # autonomous path; let the stall-detector decide if the whole sprint
            # is now deadlocked (dependent pending tasks can't run) and mark it
            # blocked instead of quiescing silently. (fuzzer-caught fixture-D hang)
            await _maybe_mark_sprint_stalled(db, completed_task)
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
