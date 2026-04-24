"""Gate results and approval routes."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.api.routes.dashboard_api import (
    publish_approval_snapshot,
    publish_board_snapshot,
)
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


@router.get("/gates", response_model=list[GateResultResponse])
async def list_all_gate_results(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GateResult).order_by(GateResult.created_at.desc()))
    return result.scalars().all()


@router.get("/gates/{gate_id}", response_model=GateResultResponse)
async def get_gate_result(gate_id: str, db: AsyncSession = Depends(get_db)):
    gate_result = await db.get(GateResult, gate_id)
    if not gate_result:
        raise HTTPException(status_code=404, detail="Gate result not found")
    return gate_result


# ── Agent Runs ──


@router.get("/tasks/{task_id}/runs", response_model=list[AgentRunResponse])
async def list_agent_runs(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentRun).where(AgentRun.task_id == task_id).order_by(AgentRun.started_at.desc())
    )
    return result.scalars().all()


@router.get("/runs", response_model=list[AgentRunResponse])
async def list_all_agent_runs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentRun).order_by(AgentRun.started_at.desc()))
    return result.scalars().all()


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


# ── Approval Gates ──


@router.get("/tasks/{task_id}/approvals", response_model=list[ApprovalGateResponse])
async def list_approval_gates(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ApprovalGate)
        .where(ApprovalGate.task_id == task_id)
        .order_by(ApprovalGate.created_at.desc())
    )
    return result.scalars().all()


@router.get("/approval-gates", response_model=list[ApprovalGateResponse])
async def list_all_approval_gates(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ApprovalGate).order_by(ApprovalGate.created_at.desc()))
    return result.scalars().all()


@router.get("/approval-gates/{gate_id}", response_model=ApprovalGateResponse)
async def get_approval_gate(gate_id: str, db: AsyncSession = Depends(get_db)):
    gate = await db.get(ApprovalGate, gate_id)
    if not gate:
        raise HTTPException(status_code=404, detail="Approval gate not found")
    return gate


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
    await db.commit()

    await publish_board_snapshot(db)
    await publish_approval_snapshot(db, gate_id)
    return {"status": "ok", "gate_status": gate.status}
