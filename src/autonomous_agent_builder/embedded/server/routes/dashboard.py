"""Dashboard API routes for embedded server."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from autonomous_agent_builder.api.dashboard_streams import get_dashboard_stream_hub
from autonomous_agent_builder.db.models import (
    AgentRun,
    Approval,
    ApprovalGate,
    ChatEvent,
    ChatSession,
    Feature,
    GateResult,
    Project,
    Task,
)
from autonomous_agent_builder.db.session import get_db
from autonomous_agent_builder.onboarding import load_feature_list_from_db

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
    phase: str
    feature_title: str
    agent_name: str
    cost_usd: float
    total_cost: float
    num_turns: int
    duration_ms: int
    approval_gate_id: str
    approval_gate_type: str
    pending_approval_count: int
    blocked_reason: str
    latest_run_status: str
    updated_at: datetime | None


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
    confidence: float | None = None
    diff_summary: dict | None = None
    started_at: datetime
    completed_at: datetime | None


class MetricsResponse(BaseModel):
    total_cost: float
    total_tokens: int
    total_runs: int
    gate_pass_rate: float
    runs: list[MetricsRunItem]


def _serialize_run(run: AgentRun) -> MetricsRunItem:
    return MetricsRunItem(
        id=run.id,
        task_id=run.task_id,
        agent_name=run.agent_name,
        cost_usd=run.cost_usd,
        tokens_input=run.tokens_input,
        tokens_output=run.tokens_output,
        tokens_cached=run.tokens_cached,
        num_turns=run.num_turns,
        duration_ms=run.duration_ms,
        stop_reason=run.stop_reason,
        status=run.status,
        error=run.error,
        confidence=run.confidence,
        diff_summary=run.diff_summary,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


async def _load_metrics_response(db: AsyncSession) -> MetricsResponse:
    result = await db.execute(select(AgentRun).order_by(AgentRun.started_at.desc()))
    orchestrator_runs = result.scalars().all()

    event_result = await db.execute(
        select(ChatEvent)
        .where(ChatEvent.event_type == "run_status")
        .order_by(ChatEvent.created_at.asc())
    )
    run_events = event_result.scalars().all()
    pending_chat_starts: dict[str, datetime] = {}
    chat_runs: list[MetricsRunItem] = []
    for event in run_events:
        payload = event.payload_json if isinstance(event.payload_json, dict) else {}
        running_flag = payload.get("running")
        if running_flag is True or event.status == "running":
            pending_chat_starts[event.session_id] = event.created_at
            continue
        if running_flag is not False and event.status not in {"completed", "failed", "error"}:
            continue
        started_at = pending_chat_starts.pop(event.session_id, event.created_at)
        duration_ms = max(int((event.created_at - started_at).total_seconds() * 1000), 0)
        total_tokens = int(payload.get("tokens_used", 0) or 0)
        chat_runs.append(
            MetricsRunItem(
                id=event.id,
                task_id=event.session_id,
                agent_name="agent-chat",
                cost_usd=float(payload.get("cost_usd", 0.0) or 0.0),
                tokens_input=0,
                tokens_output=total_tokens,
                tokens_cached=0,
                num_turns=int(payload.get("current_turn", 0) or 0),
                duration_ms=duration_ms,
                stop_reason=None,
                status="failed" if event.status in {"failed", "error"} else "completed",
                error=None,
                started_at=started_at,
                completed_at=event.created_at,
            )
        )

    total_cost = sum(r.cost_usd for r in orchestrator_runs) + sum(r.cost_usd for r in chat_runs)
    total_tokens = sum(r.tokens_input + r.tokens_output for r in orchestrator_runs) + sum(
        r.tokens_input + r.tokens_output for r in chat_runs
    )

    result = await db.execute(select(GateResult))
    gates = result.scalars().all()
    gate_pass_rate = (
        len([g for g in gates if g.status == "pass"]) / len(gates) * 100
        if gates
        else 0
    )

    all_runs = [
        *[_serialize_run(r) for r in orchestrator_runs],
        *chat_runs,
    ]
    all_runs.sort(key=lambda run: run.completed_at or run.started_at, reverse=True)

    return MetricsResponse(
        total_cost=total_cost,
        total_tokens=total_tokens,
        total_runs=len(all_runs),
        gate_pass_rate=gate_pass_rate,
        runs=all_runs,
    )


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
    acceptance_criteria: list[str]
    dependencies: list[str]


class FeatureListResponse(BaseModel):
    project_name: str
    total: int
    done: int
    pending: int
    features: list[FeatureListItem]


class TodoItem(BaseModel):
    content: str
    status: str
    active_form: str | None = None


class TodoSnapshotResponse(BaseModel):
    session_id: str
    pending_count: int
    in_progress_count: int
    completed_count: int
    updated_at: datetime
    todos: list[TodoItem]


class ShellSummaryResponse(BaseModel):
    active_session_id: str | None
    active_session_ids: list[str]
    active_run_count: int
    pending_approvals: int
    pending_questions: int
    running_label: str
    total_cost: float
    total_tokens: int
    permission_mode: str
    mcp_servers: list[str]
    mcp_tools: list[str]
    todo_snapshots: list[TodoSnapshotResponse]


class InboxItem(BaseModel):
    id: str
    task_id: str
    task_title: str
    task_status: str
    feature_title: str
    project_name: str
    gate_type: str
    status: str
    created_at: datetime | None
    resolved_at: datetime | None
    latest_run_id: str | None
    latest_run_agent: str | None
    latest_run_status: str | None
    latest_run_cost_usd: float
    latest_run_turns: int
    latest_run_duration_ms: int
    approval_url: str


class CompareRunSide(BaseModel):
    id: str
    task_id: str
    task_title: str
    feature_title: str
    project_name: str
    agent_name: str
    session_id: str | None
    status: str
    stop_reason: str | None
    error: str | None
    confidence: float | None = None
    diff_summary: dict | None = None
    cost_usd: float
    tokens_input: int
    tokens_output: int
    tokens_cached: int
    num_turns: int
    duration_ms: int
    started_at: datetime
    completed_at: datetime | None
    gate_results: list[dict]
    approvals: list[dict]


class CompareResponse(BaseModel):
    same_task: bool
    left: CompareRunSide
    right: CompareRunSide


class CommandPaletteItem(BaseModel):
    id: str
    kind: str
    label: str
    description: str
    route: str | None = None
    action: str | None = None
    task_id: str | None = None
    gate_id: str | None = None
    session_id: str | None = None


class CommandIndexResponse(BaseModel):
    items: list[CommandPaletteItem]


def _serialize_gate_result(gate_result: GateResult) -> dict[str, object]:
    return {
        "id": gate_result.id,
        "gate_name": gate_result.gate_name,
        "status": (
            gate_result.status.value
            if hasattr(gate_result.status, "value")
            else str(gate_result.status)
        ),
        "findings_count": gate_result.findings_count,
        "elapsed_ms": gate_result.elapsed_ms,
        "timeout": gate_result.timeout,
        "evidence": gate_result.evidence or {},
        "error_code": gate_result.error_code,
        "remediation_attempted": gate_result.remediation_attempted,
        "remediation_succeeded": gate_result.remediation_succeeded,
        "analysis_depth": gate_result.analysis_depth,
    }


def _serialize_approval(gate: ApprovalGate) -> dict[str, object]:
    return {
        "id": gate.id,
        "gate_type": gate.gate_type,
        "status": gate.status,
        "created_at": gate.created_at,
        "resolved_at": gate.resolved_at,
    }


async def _load_latest_todo_snapshots(db: AsyncSession, *, limit: int = 3) -> list[TodoSnapshotResponse]:
    result = await db.execute(
        select(ChatEvent)
        .where(ChatEvent.event_type == "todo_snapshot")
        .order_by(ChatEvent.created_at.desc())
    )
    events = result.scalars().all()
    snapshots: list[TodoSnapshotResponse] = []
    seen_sessions: set[str] = set()
    for event in events:
        if event.session_id in seen_sessions:
            continue
        payload = event.payload_json if isinstance(event.payload_json, dict) else {}
        todos = payload.get("todos", []) or []
        snapshots.append(
            TodoSnapshotResponse(
                session_id=event.session_id,
                pending_count=int(payload.get("pending_count", 0) or 0),
                in_progress_count=int(payload.get("in_progress_count", 0) or 0),
                completed_count=int(payload.get("completed_count", 0) or 0),
                updated_at=event.created_at,
                todos=[
                    TodoItem(
                        content=str(todo.get("content", "") or ""),
                        status=str(todo.get("status", "pending") or "pending"),
                        active_form=(
                            str(todo.get("activeForm", "")).strip() or None
                            if isinstance(todo, dict)
                            else None
                        ),
                    )
                    for todo in todos
                    if isinstance(todo, dict)
                ],
            )
        )
        seen_sessions.add(event.session_id)
        if len(snapshots) >= limit:
            break
    return snapshots


# ── Endpoints ──


@router.get("/dashboard/features", response_model=FeatureListResponse)
async def features_json(request: Request, db: AsyncSession = Depends(get_db)):
    """Feature list from the repo artifact when present, else builder-managed state."""
    project_root = request.app.state.project_root
    data = _read_feature_list(project_root)
    features_data = data.get("features", [])
    metadata = data.get("metadata", {})
    if features_data:
        return FeatureListResponse(
            project_name=metadata.get("project", project_root.name),
            total=len(features_data),
            done=metadata.get("done", 0),
            pending=metadata.get("pending", len(features_data)),
            features=[
                FeatureListItem(
                    id=f.get("id", ""),
                    title=f.get("title", ""),
                    description=f.get("description", ""),
                    status=f.get("status", "pending"),
                    priority=f.get("priority", "P1"),
                    acceptance_criteria=f.get("acceptance_criteria", []),
                    dependencies=f.get("dependencies", []),
                )
                for f in features_data
            ],
        )

    payload = await load_feature_list_from_db(db, project_root)
    if payload["total"] > 0:
        return FeatureListResponse(**payload)
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
                acceptance_criteria=f.get("acceptance_criteria", []),
                dependencies=f.get("dependencies", []),
            )
            for f in features_data
        ],
    )


def _build_task_item(t: Task) -> TaskBoardItem:
    latest_run = t.agent_runs[-1] if t.agent_runs else None
    total_cost = sum(r.cost_usd for r in t.agent_runs)
    pending_gates = [g for g in t.approval_gates if g.status == "pending"]
    pending_gate = pending_gates[0] if pending_gates else None
    return TaskBoardItem(
        id=t.id,
        title=t.title,
        status=_status_str(t),
        phase=t.phase.value if hasattr(t.phase, "value") else str(t.phase),
        feature_title=t.feature.title if t.feature else "",
        agent_name=latest_run.agent_name if latest_run else "",
        cost_usd=latest_run.cost_usd if latest_run else 0,
        total_cost=total_cost,
        num_turns=latest_run.num_turns if latest_run else 0,
        duration_ms=latest_run.duration_ms if latest_run else 0,
        approval_gate_id=pending_gate.id if pending_gate else "",
        approval_gate_type=pending_gate.gate_type if pending_gate else "",
        pending_approval_count=len(pending_gates),
        blocked_reason=t.blocked_reason or "",
        latest_run_status=latest_run.status if latest_run else "",
        updated_at=t.updated_at,
    )


async def load_board_response(db: AsyncSession) -> BoardResponse:
    """Build the current board snapshot."""
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


@router.get("/dashboard/board", response_model=BoardResponse)
async def board_json(db: AsyncSession = Depends(get_db)):
    """Board data as JSON — consumed by React frontend."""
    return await load_board_response(db)


@router.get("/dashboard/metrics", response_model=MetricsResponse)
async def metrics_json(db: AsyncSession = Depends(get_db)):
    """Metrics data as JSON — consumed by React frontend."""
    return await _load_metrics_response(db)


async def load_approval_details_response(
    gate_id: str,
    db: AsyncSession,
) -> ApprovalDetailsResponse:
    """Build the current approval details snapshot."""
    gate = await db.get(ApprovalGate, gate_id)
    if not gate:
        raise HTTPException(status_code=404, detail="Approval gate not found")

    task = await db.get(Task, gate.task_id)
    feature = await db.get(Feature, task.feature_id) if task else None
    project = await db.get(Project, feature.project_id) if feature else None

    result = await db.execute(
        select(GateResult).where(GateResult.task_id == gate.task_id)
    )
    gate_results = result.scalars().all()

    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.task_id == gate.task_id)
        .order_by(AgentRun.started_at)
    )
    runs = result.scalars().all()

    result = await db.execute(
        select(Approval)
        .where(Approval.approval_gate_id == gate_id)
        .order_by(Approval.created_at)
    )
    approvals = result.scalars().all()

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
    for approval in approvals:
        comment = (
            f"[{approval.decision.upper()}] {approval.comment}"
            if approval.comment
            else f"[{approval.decision.upper()}]"
        )
        thread.append(ThreadEntry(
            role="human",
            agent_name="",
            author=approval.approver_email,
            content=comment,
            timestamp=approval.created_at,
        ))
    thread.sort(key=lambda entry: entry.timestamp)

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
        runs=[_serialize_run(run) for run in runs],
        gate_results=[_serialize_gate_result(gate_result) for gate_result in gate_results],
    )


@router.get(
    "/dashboard/approvals/{gate_id}",
    response_model=ApprovalDetailsResponse,
)
async def approval_details_json(
    gate_id: str, db: AsyncSession = Depends(get_db)
):
    """Approval gate details as JSON — consumed by React frontend."""
    return await load_approval_details_response(gate_id, db)


async def _load_shell_summary_response(request: Request, db: AsyncSession) -> ShellSummaryResponse:
    metrics = await _load_metrics_response(db)
    pending_approvals_result = await db.execute(
        select(ApprovalGate).where(ApprovalGate.status == "pending")
    )
    pending_approvals = pending_approvals_result.scalars().all()

    pending_questions_result = await db.execute(
        select(ChatEvent).where(
            ChatEvent.event_type.in_(["ask_user_question", "tool_approval_request"]),
            ChatEvent.status == "pending",
        )
    )
    pending_questions = pending_questions_result.scalars().all()

    active_run_result = await db.execute(select(AgentRun).where(AgentRun.status == "running"))
    active_runs = active_run_result.scalars().all()

    hub = request.app.state.chat_hub
    active_session_ids = await hub.snapshot_active_session_ids()
    todo_snapshots = await _load_latest_todo_snapshots(db)

    return ShellSummaryResponse(
        active_session_id=active_session_ids[0] if active_session_ids else None,
        active_session_ids=active_session_ids,
        active_run_count=len(active_runs) + len(active_session_ids),
        pending_approvals=len(pending_approvals),
        pending_questions=len(pending_questions),
        running_label=f"{len(active_runs) + len(active_session_ids)} running",
        total_cost=metrics.total_cost,
        total_tokens=metrics.total_tokens,
        permission_mode="unknown",
        mcp_servers=[],
        mcp_tools=[],
        todo_snapshots=todo_snapshots,
    )


async def _load_inbox_response(db: AsyncSession) -> list[InboxItem]:
    result = await db.execute(
        select(ApprovalGate).order_by(ApprovalGate.created_at.desc())
    )
    gates = result.scalars().all()
    items: list[InboxItem] = []
    for gate in gates:
        task = await db.get(Task, gate.task_id)
        feature = await db.get(Feature, task.feature_id) if task else None
        project = await db.get(Project, feature.project_id) if feature else None
        run_result = await db.execute(
            select(AgentRun)
            .where(AgentRun.task_id == gate.task_id)
            .order_by(AgentRun.started_at.desc())
        )
        latest_run = run_result.scalars().first()
        items.append(
            InboxItem(
                id=gate.id,
                task_id=task.id if task else "",
                task_title=task.title if task else "",
                task_status=_status_str(task) if task else "",
                feature_title=feature.title if feature else "",
                project_name=project.name if project else "",
                gate_type=gate.gate_type,
                status=gate.status,
                created_at=gate.created_at,
                resolved_at=gate.resolved_at,
                latest_run_id=latest_run.id if latest_run else None,
                latest_run_agent=latest_run.agent_name if latest_run else None,
                latest_run_status=latest_run.status if latest_run else None,
                latest_run_cost_usd=latest_run.cost_usd if latest_run else 0.0,
                latest_run_turns=latest_run.num_turns if latest_run else 0,
                latest_run_duration_ms=latest_run.duration_ms if latest_run else 0,
                approval_url=f"/approvals/{gate.id}",
            )
        )
    return items


async def _load_compare_response(
    left_run_id: str,
    right_run_id: str,
    db: AsyncSession,
) -> CompareResponse:
    left_run = await db.get(AgentRun, left_run_id)
    right_run = await db.get(AgentRun, right_run_id)
    if left_run is None or right_run is None:
        raise HTTPException(status_code=404, detail="Compare run not found")

    async def _side(run: AgentRun) -> CompareRunSide:
        task = await db.get(Task, run.task_id)
        feature = await db.get(Feature, task.feature_id) if task else None
        project = await db.get(Project, feature.project_id) if feature else None
        gate_result = await db.execute(
            select(GateResult).where(GateResult.task_id == run.task_id)
        )
        approval_result = await db.execute(
            select(ApprovalGate)
            .where(ApprovalGate.task_id == run.task_id)
            .order_by(ApprovalGate.created_at.desc())
        )
        return CompareRunSide(
            id=run.id,
            task_id=run.task_id,
            task_title=task.title if task else "",
            feature_title=feature.title if feature else "",
            project_name=project.name if project else "",
            agent_name=run.agent_name,
            session_id=run.session_id,
            status=run.status,
            stop_reason=run.stop_reason,
            error=run.error,
            confidence=run.confidence,
            diff_summary=run.diff_summary,
            cost_usd=run.cost_usd,
            tokens_input=run.tokens_input,
            tokens_output=run.tokens_output,
            tokens_cached=run.tokens_cached,
            num_turns=run.num_turns,
            duration_ms=run.duration_ms,
            started_at=run.started_at,
            completed_at=run.completed_at,
            gate_results=[_serialize_gate_result(item) for item in gate_result.scalars().all()],
            approvals=[_serialize_approval(item) for item in approval_result.scalars().all()],
        )

    return CompareResponse(
        same_task=left_run.task_id == right_run.task_id,
        left=await _side(left_run),
        right=await _side(right_run),
    )


async def _load_command_index_response(db: AsyncSession) -> CommandIndexResponse:
    items: list[CommandPaletteItem] = [
        CommandPaletteItem(id="route-agent", kind="route", label="Agent", description="Open the live agent thread", route="/"),
        CommandPaletteItem(id="route-board", kind="route", label="Board", description="Open the task pipeline", route="/board"),
        CommandPaletteItem(id="route-metrics", kind="route", label="Metrics", description="Open cost and run metrics", route="/metrics"),
        CommandPaletteItem(id="route-knowledge", kind="route", label="Knowledge", description="Open system docs and retrieval", route="/knowledge"),
        CommandPaletteItem(id="route-memory", kind="route", label="Memory", description="Open durable decisions and corrections", route="/memory"),
        CommandPaletteItem(id="route-backlog", kind="route", label="Backlog", description="Open the feature ledger", route="/backlog"),
        CommandPaletteItem(id="route-inbox", kind="route", label="Inbox", description="Open pending approvals", route="/inbox"),
        CommandPaletteItem(id="route-compare", kind="route", label="Compare", description="Compare two agent runs", route="/compare"),
    ]

    sessions_result = await db.execute(
        select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(8)
    )
    for session in sessions_result.scalars().all():
        items.append(
            CommandPaletteItem(
                id=f"session-{session.id}",
                kind="session",
                label=f"Resume session {session.id[:8]}",
                description=session.workspace_cwd or session.repo_identity or "Recent session",
                route=f"/?session={session.id}",
                session_id=session.id,
            )
        )

    approvals = await _load_inbox_response(db)
    for approval in approvals[:8]:
        items.append(
            CommandPaletteItem(
                id=f"approval-{approval.id}",
                kind="approval",
                label=f"{approval.gate_type.title()} approval · {approval.task_title or approval.id[:8]}",
                description=f"{approval.project_name or 'Project'} · {approval.status}",
                route=approval.approval_url,
                gate_id=approval.id,
            )
        )

    task_result = await db.execute(
        select(Task)
        .options(selectinload(Task.feature))
        .order_by(Task.updated_at.desc())
        .limit(12)
    )
    for task in task_result.scalars().all():
        items.append(
            CommandPaletteItem(
                id=f"task-{task.id}",
                kind="task",
                label=task.title,
                description=f"{task.feature.title if task.feature else 'Task'} · {_status_str(task)}",
                route="/board",
                action="dispatch",
                task_id=task.id,
            )
        )

    return CommandIndexResponse(items=items)


@router.get("/dashboard/shell-summary", response_model=ShellSummaryResponse)
async def shell_summary_json(request: Request, db: AsyncSession = Depends(get_db)):
    return await _load_shell_summary_response(request, db)


@router.get("/dashboard/inbox", response_model=list[InboxItem])
async def inbox_json(db: AsyncSession = Depends(get_db)):
    return await _load_inbox_response(db)


@router.get("/dashboard/compare", response_model=CompareResponse)
async def compare_json(left_run_id: str, right_run_id: str, db: AsyncSession = Depends(get_db)):
    return await _load_compare_response(left_run_id, right_run_id, db)


@router.get("/dashboard/command-index", response_model=CommandIndexResponse)
async def command_index_json(db: AsyncSession = Depends(get_db)):
    return await _load_command_index_response(db)


@router.get("/dashboard/board/stream")
async def board_stream(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Stream board snapshot updates as SSE."""
    hub = get_dashboard_stream_hub()
    queue = await hub.register_board()
    initial_snapshot = (await load_board_response(db)).model_dump(mode="json")

    async def event_generator():
        try:
            yield {"event": "snapshot", "data": json.dumps(initial_snapshot)}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield {
                        "event": event["event"],
                        "data": json.dumps(event["data"]),
                    }
                except TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            await hub.unregister_board(queue)

    return EventSourceResponse(event_generator())


@router.get("/dashboard/approvals/{gate_id}/stream")
async def approval_stream(
    gate_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Stream approval snapshot updates as SSE."""
    hub = get_dashboard_stream_hub()
    queue = await hub.register_approval(gate_id)
    initial_snapshot = (await load_approval_details_response(gate_id, db)).model_dump(mode="json")

    async def event_generator():
        try:
            yield {"event": "snapshot", "data": json.dumps(initial_snapshot)}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield {
                        "event": event["event"],
                        "data": json.dumps(event["data"]),
                    }
                except TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            await hub.unregister_approval(gate_id, queue)

    return EventSourceResponse(event_generator())
