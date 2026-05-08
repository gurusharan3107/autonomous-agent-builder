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
    ApprovalLog,
    GateResult,
    Sprint,
    Task,
)
from autonomous_agent_builder.db.session import get_db
from autonomous_agent_builder.orchestrator.orchestrator import (
    apply_approval_outcome,
    apply_sprint_approval_outcome,
)
from autonomous_agent_builder.services.dispatch_lock import reserve_dispatch

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

    # Sprint-PR refactor (Phase D): a sprint-level gate fans out to the
    # sprint-state helper instead of the per-task one. Per-task gates keep
    # the existing path. The single-writer invariant from CLAUDE.md still
    # holds: gates persist approval rows; orchestrator owns state mutation.
    follow_up_task_ids: list[str] = []
    if gate.sprint_id and gate.gate_type == "sprint_pr":
        sprint = await db.get(Sprint, gate.sprint_id)
        sprint_tasks: list[Task] = []
        if sprint and sprint.generated_task_ids:
            generated = [str(tid) for tid in sprint.generated_task_ids if str(tid).strip()]
            if generated:
                result = await db.execute(select(Task).where(Task.id.in_(generated)))
                sprint_tasks = list(result.scalars().all())
        if sprint:
            apply_sprint_approval_outcome(
                sprint,
                decision,
                reason=outcome_reason,
                sprint_tasks=sprint_tasks,
            )
            if decision == ApprovalDecision.REQUEST_CHANGES:
                follow_up_task_ids = [t.id for t in sprint_tasks]

        # Sprint-level audit row: ``ApprovalLog.task_id`` is nullable now, so
        # we record ``sprint_id`` as the canonical anchor.
        db.add(
            ApprovalLog(
                task_id=None,
                sprint_id=gate.sprint_id,
                approver_email=data.approver_email,
                decision=decision,
                reason=outcome_reason,
            )
        )

        await db.flush()
        await db.commit()
        await publish_board_snapshot(db)
        await publish_approval_snapshot(db, gate_id)

        if follow_up_task_ids:
            from autonomous_agent_builder.api.routes.dispatch import (
                _NON_DISPATCHABLE_STATUSES,
                _run_dispatch,
            )

            for tid in follow_up_task_ids:
                follow_up = await db.get(Task, tid)
                if follow_up is None:
                    continue
                follow_up_status = (
                    follow_up.status.value
                    if hasattr(follow_up.status, "value")
                    else str(follow_up.status)
                )
                if follow_up_status in _NON_DISPATCHABLE_STATUSES:
                    continue
                if reserve_dispatch(follow_up.id):
                    background.add_task(_run_dispatch, follow_up.id)

        return {"status": "ok", "gate_status": gate.status}

    # Per-task gate path (planning/design/pr) — legacy behavior preserved.
    db.add(
        ApprovalLog(
            task_id=gate.task_id,
            approver_email=data.approver_email,
            decision=decision,
            reason=outcome_reason,
        )
    )

    task = await db.get(Task, gate.task_id) if gate.task_id else None
    should_dispatch = False
    if task:
        should_dispatch = apply_approval_outcome(
            task,
            gate.gate_type,
            decision,
            reason=outcome_reason,
        )

    await db.flush()
    await db.commit()

    await publish_board_snapshot(db)
    await publish_approval_snapshot(db, gate_id)

    if task and should_dispatch:
        from autonomous_agent_builder.api.routes.dispatch import (
            _NON_DISPATCHABLE_STATUSES,
            _run_dispatch,
        )

        task_status = task.status.value if hasattr(task.status, "value") else str(task.status)
        if task_status not in _NON_DISPATCHABLE_STATUSES and reserve_dispatch(task.id):
            background.add_task(_run_dispatch, task.id)

    return {"status": "ok", "gate_status": gate.status}
