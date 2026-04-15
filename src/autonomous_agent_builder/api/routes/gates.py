"""Gate results and approval routes."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.api.schemas import (
    AgentRunResponse,
    ApprovalCreate,
    ApprovalGateResponse,
    GateResultResponse,
)
from autonomous_agent_builder.db.models import (
    AgentRun,
    Approval,
    ApprovalDecision,
    ApprovalGate,
    ApprovalLog,
    GateResult,
    Task,
    TaskStatus,
)
from autonomous_agent_builder.db.session import get_db

router = APIRouter(tags=["gates"])


# ── Gate Results ──


@router.get("/tasks/{task_id}/gates", response_model=list[GateResultResponse])
async def list_gate_results(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GateResult)
        .where(GateResult.task_id == task_id)
        .order_by(GateResult.created_at.desc())
    )
    return result.scalars().all()


# ── Agent Runs ──


@router.get("/tasks/{task_id}/runs", response_model=list[AgentRunResponse])
async def list_agent_runs(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentRun).where(AgentRun.task_id == task_id).order_by(AgentRun.started_at.desc())
    )
    return result.scalars().all()


# ── Approval Gates ──


@router.get("/tasks/{task_id}/approvals", response_model=list[ApprovalGateResponse])
async def list_approval_gates(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ApprovalGate)
        .where(ApprovalGate.task_id == task_id)
        .order_by(ApprovalGate.created_at.desc())
    )
    return result.scalars().all()


@router.post("/approval-gates/{gate_id}/approve")
async def submit_approval(gate_id: str, data: ApprovalCreate, db: AsyncSession = Depends(get_db)):
    """Submit an approval decision for a gate."""
    gate = await db.get(ApprovalGate, gate_id)
    if not gate:
        raise HTTPException(status_code=404, detail="Approval gate not found")
    if gate.status != "pending":
        raise HTTPException(status_code=400, detail=f"Gate already {gate.status}")

    # Create approval record
    decision = ApprovalDecision(data.decision)
    approval = Approval(
        approval_gate_id=gate_id,
        approver_email=data.approver_email,
        decision=decision,
        comment=data.comment,
    )
    db.add(approval)

    # Create immutable audit log entry
    audit_entry = ApprovalLog(
        task_id=gate.task_id,
        approver_email=data.approver_email,
        decision=decision,
        reason=data.reason or data.comment,
    )
    db.add(audit_entry)

    # Update gate status
    gate.status = data.decision
    gate.resolved_at = datetime.now(UTC)

    # Advance task status based on decision
    task = await db.get(Task, gate.task_id)
    if task:
        if decision == ApprovalDecision.APPROVE:
            if gate.gate_type == "planning":
                task.status = TaskStatus.DESIGN
            elif gate.gate_type == "design":
                task.status = TaskStatus.IMPLEMENTATION
            elif gate.gate_type == "pr":
                task.status = TaskStatus.BUILD_VERIFY
        elif decision in (ApprovalDecision.REJECT, ApprovalDecision.REQUEST_CHANGES):
            task.status = TaskStatus.BLOCKED
            task.blocked_reason = data.comment or "Approval rejected"

    await db.flush()
    return {"status": "ok", "gate_status": gate.status}
