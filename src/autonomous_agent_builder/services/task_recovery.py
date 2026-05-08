"""Shared task lifecycle recovery helpers."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.api.routes.dashboard_api import publish_board_snapshot
from autonomous_agent_builder.db.models import (
    AgentRun,
    ApprovalGate,
    Task,
    TaskPhase,
    TaskStatus,
    set_task_status,
)
from autonomous_agent_builder.services.provider_limits import (
    clear_provider_limit,
    provider_limit_target_status,
)

_DOC_GATE_BLOCK_PREFIX = "documentation refresh gate blocked:"


def _verifier_output_has_failed_check(output_text: str) -> bool:
    return any(
        "FAIL" in line.split(":", 1)[0] or " FAIL" in line
        for line in str(output_text or "").splitlines()
    )


async def _latest_verifier_reported_failed_check(task: Task, db: AsyncSession) -> bool:
    result = await db.execute(
        select(AgentRun.output_text)
        .where(AgentRun.task_id == task.id)
        .where(AgentRun.agent_name == "build-verifier")
        .where(AgentRun.status == "completed")
        .order_by(AgentRun.started_at.desc())
        .limit(1)
    )
    output_text = result.scalar_one_or_none()
    return _verifier_output_has_failed_check(str(output_text or ""))


async def _has_completed_build_verifier(task: Task, db: AsyncSession) -> bool:
    result = await db.execute(
        select(AgentRun.id)
        .where(AgentRun.task_id == task.id)
        .where(AgentRun.agent_name == "build-verifier")
        .where(AgentRun.status == "completed")
        .order_by(AgentRun.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none() is not None

async def _has_pr_change_request_gate(task: Task, db: AsyncSession) -> bool:
    result = await db.execute(
        select(ApprovalGate.id)
        .where(ApprovalGate.task_id == task.id)
        .where(ApprovalGate.gate_type == "pr")
        .where(ApprovalGate.status == "request_changes")
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _recovery_target_status(task: Task, db: AsyncSession) -> tuple[str, TaskStatus]:
    task_status = task.status.value if hasattr(task.status, "value") else str(task.status)
    blocked_reason = str(task.blocked_reason or "").strip()

    if task_status == TaskStatus.FAILED.value:
        task_phase = task.phase if isinstance(task.phase, TaskPhase) else TaskPhase(str(task.phase))
        if task_phase == TaskPhase.INTEGRATION:
            return task_status, TaskStatus.BUILD_VERIFY
        if task_phase == TaskPhase.COMPLETE and await _has_completed_build_verifier(task, db):
            return task_status, TaskStatus.BUILD_VERIFY
        if task_phase == TaskPhase.IMPLEMENTATION:
            return task_status, TaskStatus.IMPLEMENTATION
        if task_phase == TaskPhase.VERIFICATION:
            return task_status, TaskStatus.QUALITY_GATES
        return task_status, TaskStatus.PENDING

    if task_status == TaskStatus.BLOCKED.value and blocked_reason.startswith(
        _DOC_GATE_BLOCK_PREFIX
    ):
        return task_status, TaskStatus.QUALITY_GATES

    if task_status == TaskStatus.BLOCKED.value and await _has_pr_change_request_gate(task, db):
        return task_status, TaskStatus.IMPLEMENTATION

    if task_status == TaskStatus.BLOCKED.value and blocked_reason.startswith(
        "implementation blocked:"
    ):
        return task_status, TaskStatus.IMPLEMENTATION

    if task_status == TaskStatus.DONE.value and await _latest_verifier_reported_failed_check(
        task, db
    ):
        return task_status, TaskStatus.BUILD_VERIFY

    if task_status == TaskStatus.PENDING.value and await _has_completed_build_verifier(task, db):
        return task_status, TaskStatus.BUILD_VERIFY

    if task_status == TaskStatus.CAPABILITY_LIMIT.value:
        return task_status, provider_limit_target_status(task)

    raise HTTPException(
        status_code=409,
        detail={
            "code": "task_not_recoverable",
            "task_id": task.id,
            "status": task_status,
            "blocked_reason": task.blocked_reason,
            "message": (
                "Only failed tasks, capability-limit tasks, documentation-gate blocked tasks, "
                "invalid pending verifier tasks, or PR change-request blocked tasks can be recovered. "
                "Dispatchable tasks should be dispatched directly."
            ),
        },
    )


async def recover_failed_task(task: Task, db: AsyncSession) -> dict[str, str]:
    """Reset a recoverable task so the operator can re-dispatch it."""
    task_status, target_status = await _recovery_target_status(task, db)

    set_task_status(task, target_status)
    if task_status == TaskStatus.CAPABILITY_LIMIT.value:
        clear_provider_limit(task)
    else:
        task.blocked_reason = None
        task.blocked_at = None
        task.capability_limit_at = None
        task.capability_limit_reason = None
        task.dead_letter_queued_at = None
        if isinstance(task.depends_on, dict) and "operator_decision" in task.depends_on:
            depends_on = dict(task.depends_on)
            depends_on.pop("operator_decision", None)
            task.depends_on = depends_on
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
