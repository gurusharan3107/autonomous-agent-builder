"""Dashboard API routes for embedded server."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.db.models import (
    AgentRun,
    Approval,
    ApprovalGate,
    Feature,
    GateResult,
    Project,
    Task,
)
from autonomous_agent_builder.db.session import get_db

router = APIRouter()

# Status groupings
_PENDING = {"pending"}
_ACTIVE = {
    "planning", "design", "implementation",
    "quality_gates", "pr_creation", "build_verify",
}
_REVIEW = {"design_review", "review_pending"}
_DONE = {"done"}
_BLOCKED = {"blocked", "capability_limit", "failed"}


def _status_str(t: Task) -> str:
    return t.status.value if hasattr(t.status, "value") else str(t.status)


def _read_feature_list(project_root: Path) -> dict:
    """Read features from .claude/progress/feature-list.json."""
    feature_list_path = project_root / ".claude" / "progress" / "feature-list.json"
    
    if not feature_list_path.exists():
        return {"features": [], "metadata": {}}
    
    try:
        with open(feature_list_path) as f:
            return json.load(f)
    except Exception:
        return {"features": [], "metadata": {}}


# ── Response Schemas ──


class TaskBoardItem(BaseModel):
    id: str
    title: str
    status: str
    feature_title: str
    agent_name: str
    cost_usd: float
    total_cost: float
    num_turns: int
    duration_ms: int
    approval_gate_id: str
    blocked_reason: str


class BoardResponse(BaseModel):
    pending: list[TaskBoardItem]
    active: list[TaskBoardItem]
    review: list[TaskBoardItem]
    done: list[TaskBoardItem]
    blocked: list[TaskBoardItem]


class MetricsRunItem(BaseModel):
    id: str
    task_id: str
    agent_name: str
    cost_usd: float
    tokens_input: int
    tokens_output: int
    tokens_cached: int
    num_turns: int
    duration_ms: int
    stop_reason: str | None
    status: str
    error: str | None
    started_at: datetime
    completed_at: datetime | None


class MetricsResponse(BaseModel):
    total_cost: float
    total_tokens: int
    total_runs: int
    gate_pass_rate: float
    runs: list[MetricsRunItem]


class ThreadEntry(BaseModel):
    role: str
    agent_name: str
    author: str
    content: str
    timestamp: datetime


class ApprovalDetailsResponse(BaseModel):
    gate_id: str
    gate_type: str
    gate_status: str
    task_id: str
    task_title: str
    task_status: str
    task_description: str
    feature_title: str
    project_name: str
    thread: list[ThreadEntry]
    runs: list[MetricsRunItem]
    gate_results: list[dict]


class FeatureListItem(BaseModel):
    id: str
    title: str
    description: str
    status: str
    priority: str


class FeatureListResponse(BaseModel):
    project_name: str
    total: int
    done: int
    pending: int
    features: list[FeatureListItem]


# ── Endpoints ──


@router.get("/dashboard/features", response_model=FeatureListResponse)
async def features_json(request: Request):
    """Feature list from .claude/progress/feature-list.json."""
    project_root = request.app.state.project_root
    data = _read_feature_list(project_root)
    metadata = data.get("metadata", {})
    features_data = data.get("features", [])
    
    return FeatureListResponse(
        project_name=metadata.get("project", "unknown"),
        total=len(features_data),
        done=metadata.get("done", 0),
        pending=metadata.get("pending", 0),
        features=[
            FeatureListItem(
                id=f.get("id", ""),
                title=f.get("title", ""),
                description=f.get("description", ""),
                status=f.get("status", "pending"),
                priority=f.get("priority", "P1"),
            )
            for f in features_data
        ],
    )


def _build_task_item(t: Task) -> TaskBoardItem:
    latest_run = t.agent_runs[-1] if t.agent_runs else None
    total_cost = sum(r.cost_usd for r in t.agent_runs)
    pending_gate = next(
        (g for g in t.approval_gates if g.status == "pending"), None
    )
    return TaskBoardItem(
        id=t.id,
        title=t.title,
        status=_status_str(t),
        feature_title=t.feature.title if t.feature else "",
        agent_name=latest_run.agent_name if latest_run else "",
        cost_usd=latest_run.cost_usd if latest_run else 0,
        total_cost=total_cost,
        num_turns=latest_run.num_turns if latest_run else 0,
        duration_ms=latest_run.duration_ms if latest_run else 0,
        approval_gate_id=pending_gate.id if pending_gate else "",
        blocked_reason=t.blocked_reason or "",
    )


@router.get("/dashboard/board", response_model=BoardResponse)
async def board_json(db: AsyncSession = Depends(get_db)):
    """Board data as JSON — consumed by React frontend."""
    # For project-level agent builder, read from .claude/progress/feature-list.json
    # instead of database. The database is only used for agent runs and approvals.
    
    # For now, return empty board since features come from feature-list.json
    # Tasks are created dynamically when agents run
    result = await db.execute(
        select(Task).options(
            selectinload(Task.feature).selectinload(Feature.project),
            selectinload(Task.agent_runs),
            selectinload(Task.approval_gates),
        )
    )
    all_tasks = result.scalars().all()
    return BoardResponse(
        pending=[_build_task_item(t) for t in all_tasks if _status_str(t) in _PENDING],
        active=[_build_task_item(t) for t in all_tasks if _status_str(t) in _ACTIVE],
        review=[_build_task_item(t) for t in all_tasks if _status_str(t) in _REVIEW],
        done=[_build_task_item(t) for t in all_tasks if _status_str(t) in _DONE],
        blocked=[_build_task_item(t) for t in all_tasks if _status_str(t) in _BLOCKED],
    )


@router.get("/dashboard/metrics", response_model=MetricsResponse)
async def metrics_json(db: AsyncSession = Depends(get_db)):
    """Metrics data as JSON — consumed by React frontend."""
    result = await db.execute(select(AgentRun).order_by(AgentRun.started_at.desc()))
    runs = result.scalars().all()

    total_cost = sum(r.cost_usd for r in runs)
    total_tokens = sum(r.tokens_input + r.tokens_output for r in runs)

    result = await db.execute(select(GateResult))
    gates = result.scalars().all()
    gate_pass_rate = (
        len([g for g in gates if g.status == "pass"]) / len(gates) * 100
        if gates
        else 0
    )

    return MetricsResponse(
        total_cost=total_cost,
        total_tokens=total_tokens,
        total_runs=len(runs),
        gate_pass_rate=gate_pass_rate,
        runs=[
            MetricsRunItem(
                id=r.id,
                task_id=r.task_id,
                agent_name=r.agent_name,
                cost_usd=r.cost_usd,
                tokens_input=r.tokens_input,
                tokens_output=r.tokens_output,
                tokens_cached=r.tokens_cached,
                num_turns=r.num_turns,
                duration_ms=r.duration_ms,
                stop_reason=r.stop_reason,
                status=r.status,
                error=r.error,
                started_at=r.started_at,
                completed_at=r.completed_at,
            )
            for r in runs
        ],
    )


@router.get(
    "/dashboard/approvals/{gate_id}",
    response_model=ApprovalDetailsResponse,
)
async def approval_details_json(
    gate_id: str, db: AsyncSession = Depends(get_db)
):
    """Approval gate details as JSON — consumed by React frontend."""
    gate = await db.get(ApprovalGate, gate_id)
    if not gate:
        raise HTTPException(status_code=404, detail="Approval gate not found")

    task = await db.get(Task, gate.task_id)
    feature = await db.get(Feature, task.feature_id) if task else None
    project = await db.get(Project, feature.project_id) if feature else None

    # Gate results
    result = await db.execute(
        select(GateResult).where(GateResult.task_id == gate.task_id)
    )
    gate_results = result.scalars().all()

    # Agent runs
    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.task_id == gate.task_id)
        .order_by(AgentRun.started_at)
    )
    runs = result.scalars().all()

    # Approvals
    result = await db.execute(
        select(Approval)
        .where(Approval.approval_gate_id == gate_id)
        .order_by(Approval.created_at)
    )
    approvals = result.scalars().all()

    # Build thread
    thread: list[ThreadEntry] = []
    for run in runs:
        thread.append(ThreadEntry(
            role="agent",
            agent_name=run.agent_name,
            author=run.agent_name,
            content=(
                f"Completed {run.agent_name} phase "
                f"({run.num_turns} turns, ${run.cost_usd:.4f})"
            ),
            timestamp=run.completed_at or run.started_at,
        ))
    for a in approvals:
        comment = (
            f"[{a.decision.upper()}] {a.comment}" if a.comment
            else f"[{a.decision.upper()}]"
        )
        thread.append(ThreadEntry(
            role="human",
            agent_name="",
            author=a.approver_email,
            content=comment,
            timestamp=a.created_at,
        ))
    thread.sort(key=lambda x: x.timestamp)

    task_status = _status_str(task) if task else ""

    return ApprovalDetailsResponse(
        gate_id=gate.id,
        gate_type=gate.gate_type,
        gate_status=gate.status,
        task_id=task.id if task else "",
        task_title=task.title if task else "",
        task_status=task_status,
        task_description=task.description if task else "",
        feature_title=feature.title if feature else "",
        project_name=project.name if project else "",
        thread=thread,
        runs=[
            MetricsRunItem(
                id=r.id,
                task_id=r.task_id,
                agent_name=r.agent_name,
                cost_usd=r.cost_usd,
                tokens_input=r.tokens_input,
                tokens_output=r.tokens_output,
                tokens_cached=r.tokens_cached,
                num_turns=r.num_turns,
                duration_ms=r.duration_ms,
                stop_reason=r.stop_reason,
                status=r.status,
                error=r.error,
                started_at=r.started_at,
                completed_at=r.completed_at,
            )
            for r in runs
        ],
        gate_results=[
            {
                "id": g.id,
                "gate_name": g.gate_name,
                "status": g.status.value if hasattr(g.status, "value") else str(g.status),
                "findings_count": g.findings_count,
                "elapsed_ms": g.elapsed_ms,
                "timeout": g.timeout,
            }
            for g in gate_results
        ],
    )
