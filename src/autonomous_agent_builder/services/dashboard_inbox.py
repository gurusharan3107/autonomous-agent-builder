"""Shared dashboard inbox query helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.db.models import AgentRun, ApprovalGate, Feature, Task


async def load_dashboard_inbox_items(
    db: AsyncSession,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    stmt = (
        select(ApprovalGate)
        .options(
            selectinload(ApprovalGate.task).selectinload(Task.feature).selectinload(Feature.project)
        )
        .order_by(ApprovalGate.created_at.desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    gates = result.scalars().all()

    latest_runs_by_task = await _latest_runs_by_task(db, [gate.task_id for gate in gates])
    return [_inbox_item_payload(gate, latest_runs_by_task) for gate in gates]


async def _latest_runs_by_task(
    db: AsyncSession,
    task_ids: list[str | None],
) -> dict[str, AgentRun]:
    filtered_task_ids = [task_id for task_id in task_ids if task_id]
    if not filtered_task_ids:
        return {}

    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.task_id.in_(filtered_task_ids))
        .order_by(AgentRun.task_id, AgentRun.started_at.desc())
    )
    latest_runs_by_task: dict[str, AgentRun] = {}
    for run in result.scalars().all():
        latest_runs_by_task.setdefault(run.task_id, run)
    return latest_runs_by_task


def _inbox_item_payload(
    gate: ApprovalGate,
    latest_runs_by_task: dict[str, AgentRun],
) -> dict[str, Any]:
    task = gate.task
    feature = task.feature if task else None
    project = feature.project if feature else None
    latest_run = latest_runs_by_task.get(gate.task_id or "")
    return {
        "id": gate.id,
        "task_id": task.id if task else "",
        "task_title": task.title if task else "",
        "task_status": _status_str(task) if task else "",
        "feature_title": feature.title if feature else "",
        "project_name": project.name if project else "",
        "gate_type": gate.gate_type,
        "status": gate.status,
        "created_at": gate.created_at,
        "resolved_at": gate.resolved_at,
        "latest_run_id": latest_run.id if latest_run else None,
        "latest_run_agent": latest_run.agent_name if latest_run else None,
        "latest_run_status": latest_run.status if latest_run else None,
        "latest_run_cost_usd": latest_run.cost_usd if latest_run else 0.0,
        "latest_run_turns": latest_run.num_turns if latest_run else 0,
        "latest_run_duration_ms": latest_run.duration_ms if latest_run else 0,
        "approval_url": f"/approvals/{gate.id}",
    }


def _status_str(task: Task) -> str:
    return task.status.value if hasattr(task.status, "value") else str(task.status)
