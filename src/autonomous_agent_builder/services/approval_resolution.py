"""Shared approval-gate resolution for API and embedded route adapters."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.models import (
    ApprovalDecision,
    ApprovalGate,
    ApprovalLog,
    Sprint,
    Task,
)
from autonomous_agent_builder.orchestrator.orchestrator import (
    apply_approval_outcome,
    apply_sprint_approval_outcome,
)


@dataclass(frozen=True)
class ApprovalResolution:
    dispatch_task_ids: list[str]


async def apply_gate_approval_resolution(
    db: AsyncSession,
    gate: ApprovalGate,
    decision: ApprovalDecision,
    *,
    approver_email: str,
    reason: str,
) -> ApprovalResolution:
    """Apply approval state changes and return task IDs that should be dispatched."""
    if gate.sprint_id and gate.gate_type == "sprint_pr":
        return await _apply_sprint_gate_resolution(
            db,
            gate,
            decision,
            approver_email=approver_email,
            reason=reason,
        )
    return await _apply_task_gate_resolution(
        db,
        gate,
        decision,
        approver_email=approver_email,
        reason=reason,
    )


async def _apply_sprint_gate_resolution(
    db: AsyncSession,
    gate: ApprovalGate,
    decision: ApprovalDecision,
    *,
    approver_email: str,
    reason: str,
) -> ApprovalResolution:
    sprint = await db.get(Sprint, gate.sprint_id)
    sprint_tasks: list[Task] = []
    if sprint and sprint.generated_task_ids:
        generated = [str(task_id) for task_id in sprint.generated_task_ids if str(task_id).strip()]
        if generated:
            result = await db.execute(select(Task).where(Task.id.in_(generated)))
            sprint_tasks = list(result.scalars().all())
    if sprint:
        apply_sprint_approval_outcome(
            sprint,
            decision,
            reason=reason,
            sprint_tasks=sprint_tasks,
        )

    db.add(
        ApprovalLog(
            task_id=None,
            sprint_id=gate.sprint_id,
            approver_email=approver_email,
            decision=decision,
            reason=reason,
        )
    )
    if decision != ApprovalDecision.REQUEST_CHANGES:
        return ApprovalResolution(dispatch_task_ids=[])
    return ApprovalResolution(dispatch_task_ids=[task.id for task in sprint_tasks])


async def _apply_task_gate_resolution(
    db: AsyncSession,
    gate: ApprovalGate,
    decision: ApprovalDecision,
    *,
    approver_email: str,
    reason: str,
) -> ApprovalResolution:
    db.add(
        ApprovalLog(
            task_id=gate.task_id,
            approver_email=approver_email,
            decision=decision,
            reason=reason,
        )
    )
    task = await db.get(Task, gate.task_id) if gate.task_id else None
    should_dispatch = False
    if task:
        should_dispatch = apply_approval_outcome(
            task,
            gate.gate_type,
            decision,
            reason=reason,
        )
    if not task or not should_dispatch:
        return ApprovalResolution(dispatch_task_ids=[])
    return ApprovalResolution(dispatch_task_ids=[task.id])
