"""Dashboard routes — HTMX-powered board and approval UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
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

TEMPLATE_DIR = Path(__file__).parent / "templates"

# Jinja2 directly with cache_size=0 — workaround for Jinja2 3.1.6 + Python 3.14 LRUCache bug

_jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), cache_size=0)

router = APIRouter()

# Status groupings for board columns
_PENDING = {"pending"}
_ACTIVE = {"planning", "design", "implementation", "quality_gates", "pr_creation", "build_verify"}
_REVIEW = {"design_review", "review_pending"}
_DONE = {"done"}
_BLOCKED = {"blocked", "capability_limit", "failed"}


def _get_status(t: Task) -> str:
    return t.status.value if hasattr(t.status, "value") else str(t.status)


def _task_view(t: Task) -> dict:
    latest_run = t.agent_runs[-1] if t.agent_runs else None
    total_cost = sum(r.cost_usd for r in t.agent_runs)
    pending_gate = next((g for g in t.approval_gates if g.status == "pending"), None)
    status = _get_status(t)
    return {
        "id": t.id,
        "title": t.title,
        "status": status,
        "feature_title": t.feature.title if t.feature else "",
        "agent_name": latest_run.agent_name if latest_run else "",
        "cost_usd": latest_run.cost_usd if latest_run else 0,
        "total_cost": total_cost,
        "num_turns": latest_run.num_turns if latest_run else 0,
        "duration_ms": latest_run.duration_ms if latest_run else 0,
        "approval_gate_id": pending_gate.id if pending_gate else "",
        "blocked_reason": t.blocked_reason or "",
    }


async def _build_board_data(db: AsyncSession) -> dict:
    """Build board data from DB — shared by full page and HTMX fragment."""
    result = await db.execute(
        select(Task).options(
            selectinload(Task.feature).selectinload(Feature.project),
            selectinload(Task.agent_runs),
            selectinload(Task.approval_gates),
        )
    )
    all_tasks = result.scalars().all()
    return {
        "pending": [_task_view(t) for t in all_tasks if _get_status(t) in _PENDING],
        "active": [_task_view(t) for t in all_tasks if _get_status(t) in _ACTIVE],
        "review": [_task_view(t) for t in all_tasks if _get_status(t) in _REVIEW],
        "done": [_task_view(t) for t in all_tasks if _get_status(t) in _DONE],
        "blocked": [_task_view(t) for t in all_tasks if _get_status(t) in _BLOCKED],
    }


@router.get("/", response_class=HTMLResponse)
async def board(request: Request, db: AsyncSession = Depends(get_db)):
    """Pipeline board — main dashboard view."""
    tasks = await _build_board_data(db)
    html = _jinja_env.get_template("board.html").render(tasks=tasks, active_page="board")
    return HTMLResponse(html)


@router.get("/api/board", response_class=HTMLResponse)
async def board_fragment(request: Request, db: AsyncSession = Depends(get_db)):
    """HTMX fragment — returns only the board inner HTML for polling swap."""
    tasks = await _build_board_data(db)
    html = _jinja_env.get_template("partials/board-fragment.html").render(tasks=tasks)
    return HTMLResponse(html)


@router.get("/api/approval-gates/{gate_id}/thread", response_class=HTMLResponse)
async def approval_thread(gate_id: str, db: AsyncSession = Depends(get_db)):
    """HTMX fragment — returns chat thread HTML for approval gate polling."""
    gate = await db.get(ApprovalGate, gate_id)
    if not gate:
        return HTMLResponse("")

    # Get approval records (human decisions)
    result = await db.execute(
        select(Approval)
        .where(Approval.approval_gate_id == gate_id)
        .order_by(Approval.created_at)
    )
    approvals = result.scalars().all()

    # Get agent runs for context
    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.task_id == gate.task_id)
        .order_by(AgentRun.started_at)
    )
    runs = result.scalars().all()

    # Build thread entries from runs + approvals, sorted by time
    thread = []
    for run in runs:
        thread.append({
            "role": "agent",
            "agent_name": run.agent_name,
            "author": run.agent_name,
            "content": f"Completed {run.agent_name} phase ({run.num_turns} turns, "
            f"${run.cost_usd:.4f})",
            "timestamp": run.completed_at or run.started_at,
        })
    for a in approvals:
        thread.append({
            "role": "human",
            "agent_name": "",
            "author": a.approver_email,
            "content": (
                f"[{a.decision.upper()}] {a.comment}" if a.comment
                else f"[{a.decision.upper()}]"
            ),
            "timestamp": a.created_at,
        })
    thread.sort(key=lambda x: x["timestamp"])

    # Render inline — no separate template needed for this small fragment
    parts = []
    for entry in thread:
        badge_class = "badge-agent" if entry["role"] == "agent" else "badge-human"
        author = entry["author"]
        content = entry["content"]
        parts.append(
            f'<div class="chat-entry">'
            f'<div class="chat-author">'
            f'<span class="badge {badge_class}">{author}</span>'
            f'</div>'
            f'<div class="chat-content">{content}</div>'
            f'</div>'
        )
    return HTMLResponse("".join(parts))


@router.get("/approvals/{gate_id}", response_class=HTMLResponse)
async def approval_review(request: Request, gate_id: str, db: AsyncSession = Depends(get_db)):
    """Group chat approval review page."""
    gate = await db.get(ApprovalGate, gate_id)
    if not gate:
        return HTMLResponse("Approval gate not found", status_code=404)

    task = await db.get(Task, gate.task_id)
    feature = await db.get(Feature, task.feature_id) if task else None
    project = await db.get(Project, feature.project_id) if feature else None

    # Get gate results for this task
    result = await db.execute(select(GateResult).where(GateResult.task_id == gate.task_id))
    gate_results = result.scalars().all()

    # Get agent runs for this task
    result = await db.execute(select(AgentRun).where(AgentRun.task_id == gate.task_id))
    runs = result.scalars().all()

    html = _jinja_env.get_template("approvals/review.html").render(
        gate=gate,
        task=task,
        feature=feature,
        project=project,
        gate_results=gate_results,
        runs=runs,
        thread=[],
        current_user="developer@accenture.com",
        active_page="approvals",
    )
    return HTMLResponse(html)


@router.get("/metrics", response_class=HTMLResponse)
async def metrics(request: Request, db: AsyncSession = Depends(get_db)):
    """Metrics dashboard — cost tracking, gate pass rates."""
    result = await db.execute(select(AgentRun))
    runs = result.scalars().all()

    total_cost = sum(r.cost_usd for r in runs)
    total_tokens = sum(r.tokens_input + r.tokens_output for r in runs)
    total_runs = len(runs)

    result = await db.execute(select(GateResult))
    gates = result.scalars().all()
    gate_pass_rate = (
        len([g for g in gates if g.status == "pass"]) / len(gates) * 100 if gates else 0
    )

    html = _jinja_env.get_template("metrics.html").render(
        total_cost=total_cost,
        total_tokens=total_tokens,
        total_runs=total_runs,
        gate_pass_rate=gate_pass_rate,
        runs=runs,
        active_page="metrics",
    )
    return HTMLResponse(html)
