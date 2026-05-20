"""JSON and SSE API endpoints for the React dashboard."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from autonomous_agent_builder.agents.definitions import AGENT_DEFINITIONS
from autonomous_agent_builder.api.dashboard_streams import get_dashboard_stream_hub
from autonomous_agent_builder.backlog_items import read_all_item_artifacts
from autonomous_agent_builder.cli.project_discovery import (
    ProjectNotFoundError,
    find_agent_builder_dir,
)
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import (
    AgentRun,
    Approval,
    ApprovalGate,
    ChatEvent,
    ChatSession,
    DesignDocument,
    Feature,
    GateResult,
    Project,
    Sprint,
    Task,
)
from autonomous_agent_builder.db.session import get_db
from autonomous_agent_builder.observability.summary import dashboard_observability_summary
from autonomous_agent_builder.onboarding import (
    load_feature_list_from_db,
    select_delivery_project,
    sync_forward_engineering_feature_backlog,
)
from autonomous_agent_builder.runtime.factory import resolve_runtime_config
from autonomous_agent_builder.services.dashboard_inbox import load_dashboard_inbox_items
from autonomous_agent_builder.services.dashboard_metrics import (
    MetricsResponse,
    MetricsRunItem,
    load_dashboard_metrics_response,
    serialize_metric_run,
)
from autonomous_agent_builder.services.dashboard_payloads import (
    bounded_diff_summary,
    bounded_metrics_value,
)
from autonomous_agent_builder.services.sprint_execution import (
    SPRINT_DESIGN_DOC_TYPE,
    SPRINT_EXECUTION_KEY,
    SPRINT_PLAN_DOC_TYPE,
    compact_board_runtime_tool_strategy,
    compact_board_sprint_design_details,
    compact_board_sprint_execution,
    compact_board_sprint_plan_details,
)
from autonomous_agent_builder.services.task_activity import build_task_activity_timeline
from autonomous_agent_builder.services.token_costing import estimate_run_cost

router = APIRouter(tags=["dashboard"])

# Status groupings
_PENDING = {"pending", "queued"}
_ACTIVE = {
    "planning",
    "design",
    "implementation",
    "quality_gates",
    "pr_creation",
    "build_verify",
}
_REVIEW = {"design_review", "review_pending"}
_DONE = {"done"}
_BLOCKED = {"blocked", "capability_limit", "failed"}
_MAX_APPROVAL_OUTPUT_CHARS = 12000
_BOARD_TASK_RUN_LIMIT = 10
_BOARD_RUN_DIFF_LIMIT = 10


def _latest_run_status(task: Task) -> str:
    latest = _latest_task_run(task)
    if not latest:
        return ""
    return str(getattr(latest, "status", "") or "")


def _is_active_lane_task(task: Task) -> bool:
    status = _status_str(task)
    latest_status = _latest_run_status(task)
    return (
        status in _ACTIVE
        and not str(getattr(task, "blocked_reason", "") or "").strip()
        and (
            latest_status == "running" or (status in {"planning", "design"} and latest_status == "")
        )
    )


def _needs_review_lane_task(task: Task) -> bool:
    return _status_str(task) in _REVIEW or (
        _status_str(task) in _ACTIVE
        and bool(str(getattr(task, "blocked_reason", "") or "").strip())
    )


def _is_pending_lane_task(task: Task) -> bool:
    status = _status_str(task)
    return status in _PENDING or (
        status in _ACTIVE and not _is_active_lane_task(task) and not _needs_review_lane_task(task)
    )


def _sortable_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _latest_task_run(task: Task) -> AgentRun | None:
    runs = list(getattr(task, "agent_runs", []) or [])
    if not runs:
        return None
    return max(
        runs,
        key=lambda run: getattr(run, "started_at", None) or datetime.min.replace(tzinfo=UTC),
    )


def _display_task_run(task: Task) -> AgentRun | None:
    runs = sorted(
        list(getattr(task, "agent_runs", []) or []),
        key=lambda run: _sortable_timestamp(getattr(run, "started_at", None) or datetime.min),
        reverse=True,
    )
    for run in runs:
        if str(getattr(run, "runtime_sdk", "") or "") != "deterministic":
            return run
    return runs[0] if runs else None


def _board_task_runs(task: Task) -> list[AgentRun]:
    return sorted(
        list(getattr(task, "agent_runs", []) or []),
        key=lambda run: _sortable_timestamp(getattr(run, "started_at", None) or datetime.min),
        reverse=True,
    )[:_BOARD_TASK_RUN_LIMIT]


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        payload = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _status_str(t: Task) -> str:
    return t.status.value if hasattr(t.status, "value") else str(t.status)


def _run_thread_content(run: AgentRun) -> str:
    output_text = str(getattr(run, "output_text", "") or "").strip()
    if output_text:
        if len(output_text) > _MAX_APPROVAL_OUTPUT_CHARS:
            output_text = output_text[:_MAX_APPROVAL_OUTPUT_CHARS].rstrip() + "\n\n[truncated]"
        return (
            f"Completed {run.agent_name} phase "
            f"({run.num_turns} turns, ${run.cost_usd:.4f}).\n\n"
            f"{output_text}"
        )
    return f"Completed {run.agent_name} phase ({run.num_turns} turns, ${run.cost_usd:.4f})"


def _read_feature_list(project_root: Path) -> dict:
    """Read features from .claude/progress/feature-list.json."""
    features = read_all_item_artifacts(project_root)
    if not features:
        return {"features": [], "metadata": {}}
    done = sum(1 for item in features if item.get("status") == "done")
    return {
        "features": features,
        "metadata": {
            "project": project_root.name,
            "done": done,
            "pending": max(len(features) - done, 0),
        },
    }


def _feature_list_item_from_dict(f: dict) -> FeatureListItem:
    return FeatureListItem(
        id=f.get("id", ""),
        title=f.get("title", ""),
        description=f.get("description", ""),
        status=f.get("status", "pending"),
        priority=str(f.get("priority", "P1")),
        item_type=f.get("item_type", f.get("type", "feature")),
        type=f.get("type", f.get("item_type", "feature")),
        tags=f.get("tags", []),
        severity=f.get("severity", ""),
        source=f.get("source", "manual"),
        evidence=f.get("evidence", ""),
        acceptance_criteria=f.get("acceptance_criteria", []),
        dependencies=f.get("dependencies", []),
    )


# ── Response Schemas ──


class TaskAgentRunSummary(BaseModel):
    id: str
    session_id: str | None = None
    agent_name: str
    runtime_sdk: str = ""
    provider: str = ""
    model: str = ""
    effort: str | None = None
    cost_usd: float = 0.0
    estimated_cost_usd: float = 0.0
    estimated_codex_credits: float | None = None
    max_budget_usd: float | None = None
    cost_source: str = ""
    pricing_model: str = ""
    pricing_note: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_cached: int = 0
    num_turns: int = 0
    duration_ms: int = 0
    stop_reason: str | None = None
    status: str = ""
    error: str | None = None
    confidence: float | None = None
    diff_summary: dict | None = None
    observability: dict | None = None
    started_at: datetime
    completed_at: datetime | None = None


class TaskBoardItem(BaseModel):
    id: str
    title: str
    description: str = ""
    status: str
    phase: str
    feature_id: str
    feature_title: str
    feature_description: str = ""
    feature_priority: int
    feature_item_type: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    sprint_execution: dict[str, Any] | None = None
    agent_name: str
    runtime_sdk: str = ""
    provider: str = ""
    model: str = ""
    effort: str | None = None
    cost_usd: float
    total_cost: float
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_cached: int = 0
    num_turns: int
    duration_ms: int
    approval_gate_id: str
    approval_gate_type: str
    pending_approval_count: int
    blocked_reason: str
    latest_run_status: str
    observability: dict | None = None
    gate_results: list[dict[str, object]] = Field(default_factory=list)
    agent_runs: list[TaskAgentRunSummary] = Field(default_factory=list)
    activity_timeline: list[TaskActivityEvent] = Field(default_factory=list)
    updated_at: datetime | None


class TaskActivityEvent(BaseModel):
    id: str
    run_id: str
    agent_name: str
    runtime_sdk: str = ""
    provider: str = ""
    status: str
    event_type: str
    action: str
    file_path: str = ""
    timestamp: datetime


class SprintBatchSummary(BaseModel):
    id: str
    title: str
    execution_mode: str
    model: str
    effort: str
    depends_on_batches: list[str] = Field(default_factory=list)


class SprintPlanSummary(BaseModel):
    plan_id: str
    design_id: str
    sprint_number: int = 1
    mode: str
    model: str
    effort: str
    single_plan: bool
    single_design: bool
    strategy: str
    batch_count: int
    sequential_count: int
    parallel_count: int
    context_strategy: str
    runtime_tool_strategy: dict[str, Any] = Field(default_factory=dict)
    batches: list[SprintBatchSummary] = Field(default_factory=list)
    plan_details: dict[str, Any] = Field(default_factory=dict)
    design_details: dict[str, Any] = Field(default_factory=dict)


class CurrentSprintItemSummary(BaseModel):
    id: str
    title: str
    status: str
    description: str = ""
    dependencies: list[str] = Field(default_factory=list)
    sprint_execution: dict[str, Any] = Field(default_factory=dict)


class CurrentSprintSummary(BaseModel):
    sprint_id: str
    label: str
    active_phase: str
    phase_statuses: dict[str, str] = Field(default_factory=dict)
    included_items: list[CurrentSprintItemSummary] = Field(default_factory=list)
    task_counts: dict[str, int] = Field(default_factory=dict)
    plan_doc_id: str | None = None
    design_doc_id: str | None = None
    generated_task_ids: list[str] = Field(default_factory=list)
    generated_tasks: list[CurrentSprintItemSummary] = Field(default_factory=list)
    verification_status: str = "pending"
    verification_evidence: dict[str, Any] | None = None
    runtime_sdk: str = ""
    model: str = ""
    effort: str = ""


class BoardResponse(BaseModel):
    pending: list[TaskBoardItem]
    active: list[TaskBoardItem]
    review: list[TaskBoardItem]
    done: list[TaskBoardItem]
    blocked: list[TaskBoardItem]
    sprint_plan: SprintPlanSummary | None = None
    current_sprint: CurrentSprintSummary | None = None
    sprints: list[CurrentSprintSummary] = Field(default_factory=list)


def _serialize_task_run(run: AgentRun, *, diff_limit: int = 50) -> TaskAgentRunSummary:
    cost = estimate_run_cost(
        model=getattr(run, "model", "") or "",
        input_tokens=run.tokens_input,
        cached_input_tokens=run.tokens_cached,
        output_tokens=run.tokens_output,
        actual_cost_usd=run.cost_usd,
        runtime_sdk=getattr(run, "runtime_sdk", "") or "",
        provider=getattr(run, "provider", "") or "",
    )
    return TaskAgentRunSummary(
        id=run.id,
        session_id=getattr(run, "session_id", None),
        agent_name=run.agent_name,
        runtime_sdk=getattr(run, "runtime_sdk", "") or "",
        provider=getattr(run, "provider", "") or "",
        model=getattr(run, "model", "") or "",
        effort=getattr(run, "effort", None),
        cost_usd=run.cost_usd,
        estimated_cost_usd=float(cost["estimated_cost_usd"] or 0.0),
        estimated_codex_credits=cost["estimated_codex_credits"],
        max_budget_usd=(
            AGENT_DEFINITIONS[run.agent_name].max_budget_usd
            if run.agent_name in AGENT_DEFINITIONS
            else None
        ),
        cost_source=str(cost["cost_source"] or ""),
        pricing_model=str(cost["pricing_model"] or ""),
        pricing_note=str(cost["pricing_note"] or ""),
        tokens_input=run.tokens_input,
        tokens_output=run.tokens_output,
        tokens_cached=run.tokens_cached,
        num_turns=run.num_turns,
        duration_ms=run.duration_ms,
        stop_reason=getattr(run, "stop_reason", None),
        status=run.status,
        error=run.error,
        confidence=getattr(run, "confidence", None),
        diff_summary=bounded_diff_summary(getattr(run, "diff_summary", None), limit=diff_limit),
        observability=bounded_metrics_value(getattr(run, "observability", None)),
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


async def _load_metrics_response(
    db: AsyncSession,
    project_root: Path,
) -> MetricsResponse:
    return await load_dashboard_metrics_response(
        db,
        project_root,
        observability_summary=dashboard_observability_summary,
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
    # Sprint-PR refactor: populated only for ``gate_type == "sprint_pr"``.
    sprint_id: str = ""
    sprint_label: str = ""
    sprint_pr_url: str = ""
    sprint_changes_summary: str = ""


class FeatureListItem(BaseModel):
    id: str
    title: str
    description: str
    status: str
    priority: str
    item_type: str = "feature"
    type: str = "feature"
    tags: list[str] = []
    severity: str = ""
    source: str = "manual"
    evidence: str = ""
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


def _latest_gate_results_by_name(gate_results: list[GateResult]) -> list[GateResult]:
    latest: dict[str, GateResult] = {}
    for gate_result in sorted(
        gate_results,
        key=lambda item: _sortable_timestamp(item.created_at),
        reverse=True,
    ):
        latest.setdefault(gate_result.gate_name, gate_result)
    return sorted(latest.values(), key=lambda item: _sortable_timestamp(item.created_at))


async def _load_latest_todo_snapshots(
    db: AsyncSession, *, limit: int = 3
) -> list[TodoSnapshotResponse]:
    ranked_events = (
        select(
            ChatEvent.id.label("event_id"),
            func.row_number()
            .over(partition_by=ChatEvent.session_id, order_by=ChatEvent.created_at.desc())
            .label("session_rank"),
        )
        .where(ChatEvent.event_type == "todo_snapshot")
        .subquery()
    )
    result = await db.execute(
        select(ChatEvent)
        .join(ranked_events, ChatEvent.id == ranked_events.c.event_id)
        .where(ranked_events.c.session_rank == 1)
        .order_by(ChatEvent.created_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    snapshots: list[TodoSnapshotResponse] = []
    for event in events:
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
    return snapshots


# ── Endpoints ──


@router.get("/dashboard/features", response_model=FeatureListResponse)
async def features_json(request: Request, db: AsyncSession = Depends(get_db)):
    """Feature list from the repo artifact when present, else builder-managed state."""
    project_root = request.app.state.project_root
    if await sync_forward_engineering_feature_backlog(db, project_root):
        await db.commit()
    data = _read_feature_list(project_root)
    features_data = data.get("features", [])
    metadata = data.get("metadata", {})
    payload = await load_feature_list_from_db(db, project_root)
    db_features = payload.get("features", []) if payload["total"] > 0 else []
    merged = {str(item.get("id", "")): item for item in features_data}
    for item in db_features:
        merged[str(item.get("id", ""))] = item
    merged_features = list(merged.values())
    if merged_features:
        done = sum(1 for item in merged_features if item.get("status") == "done")
        return FeatureListResponse(
            project_name=payload.get("project_name") or metadata.get("project", project_root.name),
            total=len(merged_features),
            done=done,
            pending=max(len(merged_features) - done, 0),
            features=[_feature_list_item_from_dict(f) for f in merged_features],
        )
    return FeatureListResponse(
        project_name=metadata.get("project", "unknown"),
        total=len(features_data),
        done=metadata.get("done", 0),
        pending=metadata.get("pending", 0),
        features=[_feature_list_item_from_dict(f) for f in features_data],
    )


def _build_task_item(t: Task) -> TaskBoardItem:
    latest_run = _latest_task_run(t)
    display_run = _display_task_run(t)
    board_runs = _board_task_runs(t)
    total_cost = sum(r.cost_usd for r in t.agent_runs)
    pending_gates = [g for g in t.approval_gates if g.status == "pending"]
    pending_gate = pending_gates[0] if pending_gates else None
    return TaskBoardItem(
        id=t.id,
        title=t.title,
        description=t.description or "",
        status=_status_str(t),
        phase=t.phase.value if hasattr(t.phase, "value") else str(t.phase),
        feature_id=t.feature.id if t.feature else "",
        feature_title=t.feature.title if t.feature else "",
        feature_description=t.feature.description if t.feature else "",
        feature_priority=t.feature.priority if t.feature else 0,
        feature_item_type=(
            t.feature.item_type.value
            if t.feature and hasattr(t.feature.item_type, "value")
            else str(t.feature.item_type if t.feature and t.feature.item_type else "feature")
        ),
        acceptance_criteria=[
            str(item)
            for item in (t.feature.acceptance_criteria if t.feature else [])
            if str(item).strip()
        ],
        dependencies=[
            str(item) for item in (t.feature.dependencies if t.feature else []) if str(item).strip()
        ],
        sprint_execution=_task_sprint_execution(t),
        agent_name=display_run.agent_name if display_run else "",
        runtime_sdk=getattr(display_run, "runtime_sdk", "") if display_run else "",
        provider=getattr(display_run, "provider", "") if display_run else "",
        model=getattr(display_run, "model", "") if display_run else "",
        effort=getattr(display_run, "effort", None) if display_run else None,
        cost_usd=display_run.cost_usd if display_run else 0,
        total_cost=total_cost,
        tokens_input=display_run.tokens_input if display_run else 0,
        tokens_output=display_run.tokens_output if display_run else 0,
        tokens_cached=display_run.tokens_cached if display_run else 0,
        num_turns=display_run.num_turns if display_run else 0,
        duration_ms=display_run.duration_ms if display_run else 0,
        approval_gate_id=pending_gate.id if pending_gate else "",
        approval_gate_type=pending_gate.gate_type if pending_gate else "",
        pending_approval_count=len(pending_gates),
        blocked_reason=t.blocked_reason or "",
        latest_run_status=latest_run.status if latest_run else "",
        observability=bounded_metrics_value(getattr(display_run, "observability", None))
        if display_run
        else None,
        gate_results=[
            _serialize_gate_result(result)
            for result in _latest_gate_results_by_name(list(getattr(t, "gate_results", []) or []))
        ],
        agent_runs=[
            _serialize_task_run(run, diff_limit=_BOARD_RUN_DIFF_LIMIT)
            for run in sorted(board_runs, key=lambda item: _sortable_timestamp(item.started_at))
        ],
        activity_timeline=[
            TaskActivityEvent(**item)
            for item in build_task_activity_timeline(
                board_runs,
                blocked_reason=t.blocked_reason or "",
            )
        ],
        updated_at=t.updated_at,
    )


def _json_doc_content(doc: DesignDocument | None) -> dict[str, Any]:
    if doc is None:
        return {}
    try:
        payload = json.loads(doc.content)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


_LEGACY_MODEL_LABELS = {"opus", "sonnet", "haiku"}


def _selected_runtime_model() -> str:
    try:
        config = resolve_runtime_config(get_settings())
    except Exception:
        return ""
    return str(config.get("model") or "").strip()


def _display_runtime_model(value: Any, fallback_model: str) -> str:
    model = str(value or "").strip()
    if model.lower() in _LEGACY_MODEL_LABELS and fallback_model:
        return fallback_model
    return model or fallback_model


def _normalize_runtime_model_details(value: Any, fallback_model: str) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_runtime_model_details(item, fallback_model)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalize_runtime_model_details(item, fallback_model) for item in value]
    if isinstance(value, str) and value.strip().lower() in _LEGACY_MODEL_LABELS and fallback_model:
        return fallback_model
    return value


def _task_sprint_execution(task: Task) -> dict[str, Any] | None:
    depends_on = task.depends_on if isinstance(task.depends_on, dict) else {}
    payload = depends_on.get(SPRINT_EXECUTION_KEY)
    if not isinstance(payload, dict):
        return None
    normalized = dict(payload)
    normalized["recommended_model"] = _display_runtime_model(
        normalized.get("recommended_model"),
        _selected_runtime_model(),
    )
    return compact_board_sprint_execution(normalized)


def _sprint_batch_summary(
    batch: dict[str, Any],
    plan: dict[str, Any],
    fallback_model: str,
) -> SprintBatchSummary:
    title = ", ".join(str(value).strip() for value in batch.get("titles", []) if str(value).strip())
    return SprintBatchSummary(
        id=str(batch.get("id") or ""),
        title=title or str(batch.get("id") or "Sprint batch"),
        execution_mode=str(batch.get("execution_mode") or "sequential"),
        model=_display_runtime_model(
            batch.get("recommended_model") or plan.get("planning_model"),
            fallback_model,
        ),
        effort=str(batch.get("recommended_effort") or plan.get("planning_effort") or ""),
        depends_on_batches=[
            str(value) for value in batch.get("depends_on_batches", []) if str(value).strip()
        ],
    )


def _compact_sprint_plan_summary(
    plan_doc: DesignDocument | None,
    design_doc: DesignDocument | None,
    *,
    sprint_number: int = 1,
) -> SprintPlanSummary | None:
    plan = _json_doc_content(plan_doc)
    if not plan:
        return None
    fallback_model = _selected_runtime_model()
    design = _json_doc_content(design_doc)
    batches_payload = plan.get("batches", [])
    batches = [item for item in batches_payload if isinstance(item, dict)]
    parallelism = plan.get("parallelism") if isinstance(plan.get("parallelism"), dict) else {}
    sequential_batches = parallelism.get("sequential_batches")
    parallel_batches = parallelism.get("parallel_batches")
    sequential_count = (
        len(sequential_batches)
        if isinstance(sequential_batches, list)
        else len([batch for batch in batches if batch.get("execution_mode") != "parallel"])
    )
    parallel_count = (
        len(parallel_batches)
        if isinstance(parallel_batches, list)
        else len([batch for batch in batches if batch.get("execution_mode") == "parallel"])
    )
    runtime_strategy = plan.get("runtime_tool_strategy")
    if not isinstance(runtime_strategy, dict):
        runtime_strategy = {}
    plan_details = _normalize_runtime_model_details(plan, fallback_model)
    design_details = _normalize_runtime_model_details(design, fallback_model)
    return SprintPlanSummary(
        plan_id=str(plan.get("plan_id") or ""),
        design_id=str(design.get("design_id") or plan.get("design_id") or ""),
        sprint_number=max(int(sprint_number or 1), 1),
        mode=str(plan.get("mode") or ""),
        model=_display_runtime_model(plan.get("planning_model"), fallback_model),
        effort=str(plan.get("planning_effort") or ""),
        single_plan=bool(plan.get("single_sprint_plan", True)),
        single_design=bool(plan.get("single_sprint_design", True)),
        strategy=str(parallelism.get("strategy") or plan.get("mode") or ""),
        batch_count=len(batches),
        sequential_count=sequential_count,
        parallel_count=parallel_count,
        context_strategy=str(plan.get("context_strategy") or ""),
        runtime_tool_strategy=compact_board_runtime_tool_strategy(runtime_strategy),
        batches=[_sprint_batch_summary(batch, plan, fallback_model) for batch in batches],
        plan_details=compact_board_sprint_plan_details(
            plan_details if isinstance(plan_details, dict) else {}
        ),
        design_details=compact_board_sprint_design_details(
            design_details if isinstance(design_details, dict) else {}
        ),
    )


async def _load_sprint_plan_summary(db: AsyncSession) -> SprintPlanSummary | None:
    result = await db.execute(
        select(DesignDocument)
        .where(DesignDocument.doc_type.in_([SPRINT_PLAN_DOC_TYPE, SPRINT_DESIGN_DOC_TYPE]))
        .order_by(DesignDocument.created_at.desc())
    )
    docs = list(result.scalars().all())
    plan_doc = next((doc for doc in docs if doc.doc_type == SPRINT_PLAN_DOC_TYPE), None)
    design_doc = next((doc for doc in docs if doc.doc_type == SPRINT_DESIGN_DOC_TYPE), None)
    sprint_number = len([doc for doc in docs if doc.doc_type == SPRINT_PLAN_DOC_TYPE]) or 1
    return _compact_sprint_plan_summary(plan_doc, design_doc, sprint_number=sprint_number)


def _generated_sprint_tasks_from_plan(
    generated_ids: list[str],
    plan: dict[str, Any],
    *,
    all_generated_ids: list[str] | None = None,
) -> list[CurrentSprintItemSummary]:
    batches = [item for item in plan.get("batches", []) if isinstance(item, dict)]
    task_specs = [item for item in plan.get("task_specs", []) if isinstance(item, dict)]
    source_ids = all_generated_ids or generated_ids
    source_index = {task_id: index for index, task_id in enumerate(source_ids)}
    items: list[CurrentSprintItemSummary] = []
    for index, task_id in enumerate(generated_ids):
        plan_index = source_index.get(task_id, index)
        batch = batches[plan_index] if plan_index < len(batches) else {}
        spec = task_specs[plan_index] if plan_index < len(task_specs) else {}
        title = str(
            batch.get("task_title")
            or batch.get("title")
            or spec.get("title")
            or batch.get("task_key")
            or spec.get("task_key")
            or f"Generated sprint task {index + 1}"
        ).strip()
        batch_id = str(batch.get("id") or "").strip()
        dependencies = [
            str(value).strip()
            for value in (batch.get("depends_on_batches") or spec.get("depends_on_batches") or [])
            if str(value).strip()
        ]
        runtime_strategy = (
            batch.get("runtime_tool_strategy") or plan.get("runtime_tool_strategy") or {}
        )
        sprint_execution = {
            "sprint_id": str(plan.get("sprint_id") or "").strip(),
            "plan_id": str(plan.get("plan_id") or "").strip(),
            "mode": str(plan.get("mode") or "").strip(),
            "batch_id": batch_id,
            "batch_index": int(batch.get("index") or index + 1),
            "task_key": str(batch.get("task_key") or spec.get("task_key") or "").strip(),
            "execution_mode": str(batch.get("execution_mode") or "sequential"),
            "depends_on_batches": dependencies,
            "recommended_model": _display_runtime_model(
                batch.get("recommended_model")
                or spec.get("recommended_model")
                or plan.get("planning_model"),
                _selected_runtime_model(),
            ),
            "recommended_effort": str(
                batch.get("recommended_effort")
                or spec.get("recommended_effort")
                or plan.get("planning_effort")
                or ""
            ),
            "context_strategy": str(
                batch.get("context_strategy") or plan.get("context_strategy") or ""
            ),
            "runtime_tool_strategy": runtime_strategy if isinstance(runtime_strategy, dict) else {},
            "implementation_brief": str(
                spec.get("implementation_brief") or batch.get("implementation_brief") or ""
            ),
            "file_ownership_hint": str(
                spec.get("file_ownership_hint") or batch.get("file_ownership_hint") or ""
            ),
        }
        items.append(
            CurrentSprintItemSummary(
                id=task_id,
                title=title,
                status="done",
                description=str(spec.get("purpose") or ""),
                dependencies=dependencies,
                sprint_execution=compact_board_sprint_execution(sprint_execution),
            )
        )
    return items


def _sprint_feature_tasks(
    sprint: Sprint,
    all_tasks: list[Task],
    feature_id: str,
) -> list[Task]:
    generated_ids = {str(task_id) for task_id in (sprint.generated_task_ids or [])}
    return [
        task for task in all_tasks if task.id in generated_ids and task.feature_id == feature_id
    ]


def _verification_status_for_sprint_tasks(sprint: Sprint, sprint_tasks: list[Task]) -> str:
    active_phase = _display_sprint_phase(sprint, sprint_tasks)
    if active_phase == "shipped":
        return "shipped"
    if active_phase == "blocked":
        return "blocked"
    if sprint_tasks and all(_status_str(task) in _DONE for task in sprint_tasks):
        return "shipped"
    return sprint.verification_status or "pending"


def _display_sprint_phase(sprint: Sprint, tasks: list[Task]) -> str:
    status_values = {_status_str(task) for task in tasks}
    generated_count = len(tasks)
    done_count = sum(1 for task in tasks if _status_str(task) in _DONE)
    verification_status = str(sprint.verification_status or "pending")
    sprint_phase = sprint.phase.value if hasattr(sprint.phase, "value") else str(sprint.phase or "")
    if generated_count:
        if status_values & _BLOCKED:
            return "blocked"
        if done_count == generated_count:
            if verification_status == "blocked":
                return "blocked"
            if verification_status in {"pass", "passed", "shipped"}:
                return "shipped"
            return "build"
        if "build_verify" in status_values:
            return "build"
        if status_values & {"pr_creation", "review_pending"}:
            return "pr_review"
        if "quality_gates" in status_values:
            return "verify"
        if sprint_phase == "implementation":
            return "implementation"
        if status_values and status_values <= {"pending", "planning"}:
            return "planning"
        if status_values and status_values <= {"design", "design_review", "pending", "planning"}:
            return "design"
        return "implementation"
    if verification_status in {"pass", "passed", "shipped"}:
        return "shipped"
    if sprint_phase in {"scope", "planning"}:
        return "planning"
    if sprint_phase == "queued":
        return "implementation"
    if sprint_phase in {"design", "implementation", "verify", "pr_review", "shipped", "blocked"}:
        return sprint_phase
    return "planning"


def _phase_statuses(active_phase: str) -> dict[str, str]:
    display_order = ["plan", "design", "implementation", "verify", "pr_review", "build", "shipped"]
    phase_to_stage = {
        "scope": "plan",
        "queued": "implementation",
        "planning": "plan",
        "design": "design",
        "implementation": "implementation",
        "verify": "verify",
        "quality_gates": "verify",
        "pr_creation": "pr_review",
        "review_pending": "pr_review",
        "pr_review": "pr_review",
        "build": "build",
        "build_verify": "build",
        "shipped": "shipped",
        "blocked": "blocked",
    }
    if active_phase == "blocked":
        return {
            "plan": "complete",
            "design": "complete",
            "implementation": "blocked",
            "blocked": "active",
            "verify": "pending",
            "pr_review": "pending",
            "build": "pending",
            "shipped": "pending",
        }
    active_stage = phase_to_stage.get(active_phase, "plan")
    active_index = display_order.index(active_stage)
    statuses: dict[str, str] = {}
    for index, stage in enumerate(display_order):
        if index < active_index:
            statuses[stage] = "complete"
        elif index == active_index:
            statuses[stage] = "active"
        else:
            statuses[stage] = "pending"
    return statuses


async def _build_sprint_summary(
    db: AsyncSession,
    sprint: Sprint,
    all_tasks: list[Task],
    *,
    visible_sprint_id: str | None = None,
    visible_label: str | None = None,
    visible_feature: Feature | None = None,
    visible_tasks: list[Task] | None = None,
) -> CurrentSprintSummary | None:
    generated_ids = [str(task_id) for task_id in (sprint.generated_task_ids or [])]
    generated_id_set = set(generated_ids)
    sprint_tasks = visible_tasks or [task for task in all_tasks if task.id in generated_id_set]
    active_phase = _display_sprint_phase(sprint, sprint_tasks)
    parent_sprint_tasks = [task for task in all_tasks if task.id in generated_id_set]
    parent_all_tasks_done = bool(parent_sprint_tasks) and all(
        _status_str(task) in _DONE for task in parent_sprint_tasks
    )
    if (
        visible_feature is not None
        and sprint_tasks
        and all(_status_str(task) in _DONE for task in sprint_tasks)
        and not (active_phase == "blocked" and parent_all_tasks_done)
    ):
        active_phase = "shipped"
    if visible_feature is not None:
        features = [visible_feature]
    else:
        feature_ids = [str(feature_id) for feature_id in (sprint.approved_feature_ids or [])]
        feature_result = await db.execute(
            select(Feature)
            .where(Feature.id.in_(feature_ids))
            .order_by(Feature.priority.desc(), Feature.created_at.asc())
        )
        features = list(feature_result.scalars().all())
    task_counts: dict[str, int] = {}
    for task in sprint_tasks:
        status = _status_str(task)
        task_counts[status] = task_counts.get(status, 0) + 1
    plan_doc = await db.get(DesignDocument, sprint.plan_doc_id) if sprint.plan_doc_id else None
    plan = _json_doc_content(plan_doc)
    runtime_strategy = plan.get("runtime_tool_strategy")
    if not isinstance(runtime_strategy, dict):
        runtime_strategy = {}
    visible_generated_ids = [task.id for task in sprint_tasks]
    return CurrentSprintSummary(
        sprint_id=visible_sprint_id or sprint.id,
        label=visible_label or sprint.label or "Sprint 1",
        active_phase=active_phase,
        phase_statuses=_phase_statuses(active_phase),
        included_items=[
            CurrentSprintItemSummary(
                id=feature.id,
                title=feature.title,
                status=feature.status.value
                if hasattr(feature.status, "value")
                else str(feature.status),
            )
            for feature in features
        ],
        task_counts=task_counts,
        plan_doc_id=sprint.plan_doc_id,
        design_doc_id=sprint.design_doc_id,
        generated_task_ids=visible_generated_ids,
        generated_tasks=_generated_sprint_tasks_from_plan(
            visible_generated_ids,
            plan,
            all_generated_ids=generated_ids,
        ),
        verification_status=_verification_status_for_sprint_tasks(sprint, sprint_tasks),
        verification_evidence=sprint.verification_evidence,
        runtime_sdk=str(runtime_strategy.get("runtime_sdk") or ""),
        model=_display_runtime_model(plan.get("planning_model"), _selected_runtime_model()),
        effort=str(plan.get("planning_effort") or ""),
    )


async def _build_visible_sprint_summaries(
    db: AsyncSession,
    sprint: Sprint,
    all_tasks: list[Task],
) -> list[CurrentSprintSummary]:
    feature_ids = [str(feature_id) for feature_id in (sprint.approved_feature_ids or [])]
    if len(feature_ids) <= 1:
        summary = await _build_sprint_summary(db, sprint, all_tasks)
        return [summary] if summary is not None else []

    feature_result = await db.execute(
        select(Feature)
        .where(Feature.id.in_(feature_ids))
        .order_by(Feature.priority.desc(), Feature.created_at.asc())
    )
    features = list(feature_result.scalars().all())
    summaries: list[CurrentSprintSummary] = []
    for index, feature in enumerate(features, start=1):
        tasks = _sprint_feature_tasks(sprint, all_tasks, feature.id)
        if not tasks:
            continue
        summary = await _build_sprint_summary(
            db,
            sprint,
            all_tasks,
            visible_sprint_id=f"{sprint.id}:{feature.id}",
            visible_label=_visible_sprint_feature_label(sprint, index),
            visible_feature=feature,
            visible_tasks=tasks,
        )
        if summary is not None:
            summaries.append(summary)

    return sorted(
        summaries,
        key=lambda item: (
            0 if item.active_phase in {"blocked", "implementation", "verify"} else 1,
            item.label,
        ),
    )


def _visible_sprint_feature_label(sprint: Sprint, index: int) -> str:
    base = sprint.label or "Sprint"
    return f"{base} / Feature {index}"


async def _load_sprint_summaries(
    db: AsyncSession,
    all_tasks: list[Task],
    *,
    project_id: str | None = None,
) -> list[CurrentSprintSummary]:
    query = select(Sprint).order_by(Sprint.created_at.desc())
    if project_id:
        query = query.where(Sprint.project_id == project_id)
    query = query.execution_options(populate_existing=True)
    sprint_result = await db.execute(query)
    summaries: list[CurrentSprintSummary] = []
    for sprint in sprint_result.scalars().all():
        summaries.extend(await _build_visible_sprint_summaries(db, sprint, all_tasks))
    return summaries


async def load_board_response(db: AsyncSession, project_root: Path | None = None) -> BoardResponse:
    """Build the current board snapshot."""
    if project_root is not None and await sync_forward_engineering_feature_backlog(
        db, project_root
    ):
        await db.commit()
    project = await select_delivery_project(db, "")
    project_id = project.id if project is not None else ""
    result = await db.execute(
        select(Task).options(
            selectinload(Task.feature).selectinload(Feature.project),
            selectinload(Task.gate_results),
            selectinload(Task.agent_runs).selectinload(AgentRun.events),
            selectinload(Task.approval_gates),
            selectinload(Task.workspace),
        ).execution_options(populate_existing=True)
    )
    all_tasks = [
        task
        for task in result.scalars().all()
        if task.feature and (not project_id or task.feature.project_id == project_id)
    ]
    sprint_summaries = await _load_sprint_summaries(db, all_tasks, project_id=project_id)
    return BoardResponse(
        pending=[_build_task_item(t) for t in all_tasks if _is_pending_lane_task(t)],
        active=[_build_task_item(t) for t in all_tasks if _is_active_lane_task(t)],
        review=[_build_task_item(t) for t in all_tasks if _needs_review_lane_task(t)],
        done=[_build_task_item(t) for t in all_tasks if _status_str(t) in _DONE],
        blocked=[_build_task_item(t) for t in all_tasks if _status_str(t) in _BLOCKED],
        sprint_plan=await _load_sprint_plan_summary(db),
        current_sprint=sprint_summaries[0] if sprint_summaries else None,
        sprints=sprint_summaries,
    )


@router.get("/dashboard/board", response_model=BoardResponse)
async def board_json(request: Request, db: AsyncSession = Depends(get_db)):
    """Board data as JSON — consumed by React frontend."""
    return await load_board_response(db, request.app.state.project_root)


@router.get("/dashboard/metrics", response_model=MetricsResponse)
async def metrics_json(request: Request, db: AsyncSession = Depends(get_db)):
    """Metrics data as JSON — consumed by React frontend."""
    return await _load_metrics_response(db, request.app.state.project_root)


@router.get("/dashboard/observability")
async def observability_json(request: Request):
    """Runtime observability evidence as JSON — consumed by React frontend."""
    try:
        db_path = (
            find_agent_builder_dir(request.app.state.project_root).resolve() / "agent_builder.db"
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=exc.hint or "Builder project not found"
        ) from exc
    return dashboard_observability_summary(db_path)


async def load_approval_details_response(
    gate_id: str,
    db: AsyncSession,
) -> ApprovalDetailsResponse:
    """Build the current approval details snapshot."""
    gate = await db.get(ApprovalGate, gate_id)
    if not gate:
        raise HTTPException(status_code=404, detail="Approval gate not found")

    task = await db.get(Task, gate.task_id) if gate.task_id else None
    feature = await db.get(Feature, task.feature_id) if task else None
    project = await db.get(Project, feature.project_id) if feature else None

    sprint = await db.get(Sprint, gate.sprint_id) if gate.sprint_id else None
    if sprint and not project:
        project = await db.get(Project, sprint.project_id)

    # Sprint-PR refactor: when the gate is sprint-level, surface evidence from
    # every task that landed in the sprint instead of a single task's runs.
    sprint_task_ids: list[str] = (
        [str(tid) for tid in (sprint.generated_task_ids or []) if str(tid).strip()]
        if sprint
        else []
    )
    target_task_ids = sprint_task_ids if sprint_task_ids else [gate.task_id] if gate.task_id else []

    if target_task_ids:
        result = await db.execute(select(GateResult).where(GateResult.task_id.in_(target_task_ids)))
        gate_results = _latest_gate_results_by_name(result.scalars().all())

        result = await db.execute(
            select(AgentRun)
            .where(AgentRun.task_id.in_(target_task_ids))
            .order_by(AgentRun.started_at)
        )
        runs = list(result.scalars().all())
    else:
        gate_results = []
        runs = []

    result = await db.execute(
        select(Approval).where(Approval.approval_gate_id == gate_id).order_by(Approval.created_at)
    )
    approvals = result.scalars().all()

    thread: list[ThreadEntry] = []
    for run in runs:
        thread.append(
            ThreadEntry(
                role="agent",
                agent_name=run.agent_name,
                author=run.agent_name,
                content=_run_thread_content(run),
                timestamp=run.completed_at or run.started_at,
            )
        )
    for approval in approvals:
        comment = (
            f"[{approval.decision.upper()}] {approval.comment}"
            if approval.comment
            else f"[{approval.decision.upper()}]"
        )
        thread.append(
            ThreadEntry(
                role="human",
                agent_name="",
                author=approval.approver_email,
                content=comment,
                timestamp=approval.created_at,
            )
        )
    thread.sort(key=lambda entry: _sortable_timestamp(entry.timestamp))

    task_status = _status_str(task) if task else ""

    sprint_pr_url = ""
    sprint_summary = ""
    if sprint:
        sprint_pr_url = sprint.pr_url or ""
        evidence = sprint.verification_evidence or {}
        if isinstance(evidence, dict):
            sprint_pr_meta = evidence.get("sprint_pr") or {}
            if isinstance(sprint_pr_meta, dict):
                sprint_summary = str(sprint_pr_meta.get("summary") or "")

    return ApprovalDetailsResponse(
        gate_id=gate.id,
        gate_type=gate.gate_type,
        gate_status=gate.status,
        task_id=task.id if task else "",
        task_title=task.title if task else (sprint.label if sprint else ""),
        task_status=task_status,
        task_description=task.description if task else sprint_summary,
        feature_title=feature.title if feature else "",
        project_name=project.name if project else "",
        thread=thread,
        runs=[serialize_metric_run(run) for run in runs],
        gate_results=[_serialize_gate_result(gate_result) for gate_result in gate_results],
        sprint_id=sprint.id if sprint else "",
        sprint_label=sprint.label if sprint else "",
        sprint_pr_url=sprint_pr_url,
        sprint_changes_summary=sprint_summary,
    )


@router.get(
    "/dashboard/approvals/{gate_id}",
    response_model=ApprovalDetailsResponse,
)
async def approval_details_json(gate_id: str, db: AsyncSession = Depends(get_db)):
    """Approval gate details as JSON — consumed by React frontend."""
    return await load_approval_details_response(gate_id, db)


async def _load_shell_summary_response(request: Request, db: AsyncSession) -> ShellSummaryResponse:
    metrics = await _load_metrics_response(db, request.app.state.project_root)
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


async def _load_inbox_response(db: AsyncSession, *, limit: int | None = None) -> list[InboxItem]:
    return [InboxItem(**item) for item in await load_dashboard_inbox_items(db, limit=limit)]


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
        gate_result = await db.execute(select(GateResult).where(GateResult.task_id == run.task_id))
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
            stop_reason=getattr(run, "stop_reason", None),
            error=run.error,
            confidence=getattr(run, "confidence", None),
            diff_summary=getattr(run, "diff_summary", None),
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
        CommandPaletteItem(
            id="route-agent",
            kind="route",
            label="Agent",
            description="Open the live agent thread",
            route="/",
        ),
        CommandPaletteItem(
            id="route-board",
            kind="route",
            label="Board",
            description="Open the task pipeline",
            route="/board",
        ),
        CommandPaletteItem(
            id="route-metrics",
            kind="route",
            label="Metrics",
            description="Open cost and run metrics",
            route="/metrics",
        ),
        CommandPaletteItem(
            id="route-observability",
            kind="route",
            label="Observability",
            description="Open SDK diagnostic evidence",
            route="/observability",
        ),
        CommandPaletteItem(
            id="route-knowledge",
            kind="route",
            label="Knowledge",
            description="Open system docs and retrieval",
            route="/knowledge",
        ),
        CommandPaletteItem(
            id="route-memory",
            kind="route",
            label="Memory",
            description="Open durable decisions and corrections",
            route="/memory",
        ),
        CommandPaletteItem(
            id="route-backlog",
            kind="route",
            label="Backlog",
            description="Open the feature ledger",
            route="/backlog",
        ),
        CommandPaletteItem(
            id="route-inbox",
            kind="route",
            label="Inbox",
            description="Open pending approvals",
            route="/inbox",
        ),
        CommandPaletteItem(
            id="route-compare",
            kind="route",
            label="Compare",
            description="Compare two agent runs",
            route="/compare",
        ),
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

    approvals = await _load_inbox_response(db, limit=8)
    for approval in approvals:
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
        select(Task).options(selectinload(Task.feature)).order_by(Task.updated_at.desc()).limit(12)
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
    initial_snapshot = (await load_board_response(db, request.app.state.project_root)).model_dump(
        mode="json"
    )

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


async def publish_board_snapshot(db: AsyncSession) -> None:
    await db.flush()
    payload = (await load_board_response(db)).model_dump(mode="json")
    await get_dashboard_stream_hub().publish_board(payload)


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


async def publish_approval_snapshot(db: AsyncSession, gate_id: str) -> None:
    payload = (await load_approval_details_response(gate_id, db)).model_dump(mode="json")
    await get_dashboard_stream_hub().publish_approval(gate_id, payload)
