"""Gate results and approval routes."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
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
    GateResult,
    Task,
)
from autonomous_agent_builder.db.session import get_db
from autonomous_agent_builder.services.approval_resolution import apply_gate_approval_resolution
from autonomous_agent_builder.services.dispatch_lock import reserve_dispatch
from autonomous_agent_builder.services.task_dispatch_policy import task_status_blocks_dispatch

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
async def submit_approval(
    gate_id: str,
    data: ApprovalCreate,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
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

    outcome_reason = data.reason or data.comment

    # Update gate status
    gate.status = data.decision
    gate.resolved_at = datetime.now(UTC)

    resolution = await apply_gate_approval_resolution(
        db,
        gate,
        decision,
        approver_email=data.approver_email,
        reason=outcome_reason,
    )

    await db.flush()
    await db.commit()

    await publish_board_snapshot(db)
    await publish_approval_snapshot(db, gate_id)

    if resolution.dispatch_task_ids:
        from autonomous_agent_builder.api.routes.dispatch import _run_dispatch

        for task_id in resolution.dispatch_task_ids:
            task = await db.get(Task, task_id)
            if task is None:
                continue
            if task_status_blocks_dispatch(task):
                continue
            if reserve_dispatch(task.id):
                background.add_task(_run_dispatch, task.id)

    return {"status": "ok", "gate_status": gate.status}
