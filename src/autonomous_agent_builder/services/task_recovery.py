"""Shared task lifecycle recovery helpers."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.api.routes.dashboard_api import publish_board_snapshot
from autonomous_agent_builder.db.models import Task, TaskStatus


async def recover_failed_task(task: Task, db: AsyncSession) -> dict[str, str]:
    """Reset an explicitly failed task back to pending for operator-driven redispatch."""
    task_status = task.status.value if hasattr(task.status, "value") else str(task.status)
    if task_status != TaskStatus.FAILED.value:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "task_not_recoverable",
                "task_id": task.id,
                "status": task_status,
                "blocked_reason": task.blocked_reason,
                "message": "Only failed tasks can be recovered. Dispatchable tasks should be dispatched directly.",
            },
        )

    task.status = TaskStatus.PENDING
    task.blocked_reason = None
    task.blocked_at = None
    task.capability_limit_at = None
    task.capability_limit_reason = None
    task.dead_letter_queued_at = None
    await db.flush()
    await db.refresh(task)
    await db.commit()
    await publish_board_snapshot(db)
    return {
        "status": "ok",
        "task_id": task.id,
        "previous_status": task_status,
        "current_status": task.status.value if hasattr(task.status, "value") else str(task.status),
        "next_step": f"builder backlog task dispatch {task.id} --yes --json",
    }
