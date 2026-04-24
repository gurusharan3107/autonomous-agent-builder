"""Gate, run, and approval API routes for the embedded server."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.api.routes.dashboard_api import (
    publish_approval_snapshot,
    publish_board_snapshot,
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

router = APIRouter()


def _gate_payload(gate: GateResult) -> dict[str, object]:
    return {
        "id": gate.id,
        "task_id": gate.task_id,
        "gate_name": gate.gate_name,
        "status": gate.status.value if hasattr(gate.status, "value") else str(gate.status),
        "findings_count": gate.findings_count,
        "elapsed_ms": gate.elapsed_ms,
        "timeout": gate.timeout,
        "error_code": gate.error_code,
        "summary": gate.summary,
        "created_at": gate.created_at.isoformat() if gate.created_at else None,
    }


def _run_payload(run: AgentRun) -> dict[str, object]:
    return {
        "id": run.id,
        "task_id": run.task_id,
        "agent_name": run.agent_name,
        "status": run.status.value if hasattr(run.status, "value") else str(run.status),
        "cost_usd": run.cost_usd,
        "tokens_input": run.tokens_input,
        "tokens_output": run.tokens_output,
        "tokens_cached": run.tokens_cached,
        "num_turns": run.num_turns,
        "duration_ms": run.duration_ms,
        "stop_reason": run.stop_reason,
        "error": run.error,
        "session_id": run.session_id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _approval_payload(gate: ApprovalGate) -> dict[str, object]:
    return {
        "id": gate.id,
        "task_id": gate.task_id,
        "gate_type": gate.gate_type,
        "status": gate.status,
        "created_at": gate.created_at.isoformat() if gate.created_at else None,
        "resolved_at": gate.resolved_at.isoformat() if gate.resolved_at else None,
    }


@router.get("/tasks/{task_id}/gates")
async def list_task_gate_results(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GateResult)
        .where(GateResult.task_id == task_id)
        .order_by(GateResult.created_at.desc())
    )
    return [_gate_payload(gate) for gate in result.scalars().all()]


@router.get("/gates")
async def list_gate_results(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GateResult).order_by(GateResult.created_at.desc()))
    return [_gate_payload(gate) for gate in result.scalars().all()]


@router.get("/gates/{gate_id}")
async def get_gate_result(gate_id: str, db: AsyncSession = Depends(get_db)):
    gate = await db.get(GateResult, gate_id)
    if not gate:
        raise HTTPException(status_code=404, detail="Gate result not found")
    return _gate_payload(gate)


@router.get("/tasks/{task_id}/runs")
async def list_task_runs(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentRun).where(AgentRun.task_id == task_id).order_by(AgentRun.started_at.desc())
    )
    return [_run_payload(run) for run in result.scalars().all()]


@router.get("/runs")
async def list_runs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentRun).order_by(AgentRun.started_at.desc()))
    return [_run_payload(run) for run in result.scalars().all()]


@router.get("/runs/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return _run_payload(run)


@router.get("/tasks/{task_id}/approvals")
async def list_task_approvals(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ApprovalGate)
        .where(ApprovalGate.task_id == task_id)
        .order_by(ApprovalGate.created_at.desc())
    )
    return [_approval_payload(gate) for gate in result.scalars().all()]


@router.get("/approval-gates")
async def list_approval_gates(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ApprovalGate).order_by(ApprovalGate.created_at.desc()))
    return [_approval_payload(gate) for gate in result.scalars().all()]


@router.get("/approval-gates/{gate_id}")
async def get_approval_gate(gate_id: str, db: AsyncSession = Depends(get_db)):
    gate = await db.get(ApprovalGate, gate_id)
    if not gate:
        raise HTTPException(status_code=404, detail="Approval gate not found")
    return _approval_payload(gate)


@router.post("/approval-gates/{gate_id}/approve")
async def submit_approval(
    gate_id: str,
    data: dict,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Submit an approval decision for a gate."""
    gate = await db.get(ApprovalGate, gate_id)
    if not gate:
        raise HTTPException(status_code=404, detail="Approval gate not found")
    if gate.status != "pending":
        raise HTTPException(status_code=400, detail=f"Gate already {gate.status}")

    decision = ApprovalDecision(data["decision"])
    approval = Approval(
        approval_gate_id=gate_id,
        approver_email=data["approver_email"],
        decision=decision,
        comment=data.get("comment", ""),
    )
    db.add(approval)

    audit_entry = ApprovalLog(
        task_id=gate.task_id,
        approver_email=data["approver_email"],
        decision=decision,
        reason=data.get("reason") or data.get("comment", ""),
    )
    db.add(audit_entry)

    gate.status = data["decision"]
    gate.resolved_at = datetime.now(UTC)

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
            task.blocked_reason = data.get("comment") or "Approval rejected"

    await db.flush()
    await db.commit()

    await publish_board_snapshot(db)
    await publish_approval_snapshot(db, gate_id)

    if task and decision == ApprovalDecision.APPROVE:
        from autonomous_agent_builder.embedded.server.routes.tasks import (
            _NON_DISPATCHABLE_STATUSES,
            _run_dispatch,
        )

        task_status = task.status.value if hasattr(task.status, "value") else str(task.status)
        if task_status not in _NON_DISPATCHABLE_STATUSES:
            background.add_task(_run_dispatch, task.id)

    return {"status": "ok", "gate_status": gate.status}
