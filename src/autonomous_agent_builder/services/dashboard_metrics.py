"""Shared dashboard metrics response assembly."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Float, Integer, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.cli.project_discovery import find_agent_builder_dir
from autonomous_agent_builder.db.models import AgentRun, ChatEvent, GateResult
from autonomous_agent_builder.observability.summary import dashboard_observability_summary
from autonomous_agent_builder.services.codex_optimization import summarize_runs_for_optimization
from autonomous_agent_builder.services.context_budget import summarize_context_budgets
from autonomous_agent_builder.services.dashboard_payloads import (
    bounded_diff_summary,
    bounded_metrics_value,
    chat_status_token_usage,
)
from autonomous_agent_builder.services.realtime_voice_ledger import (
    VOICE_LEDGER_EVENT_TYPES,
    build_realtime_voice_ledger,
)
from autonomous_agent_builder.services.token_costing import estimate_run_cost

METRICS_RUN_LIMIT = 100
METRICS_CHAT_EVENT_SCAN_LIMIT = 500

ObservabilitySummary = Callable[[Path], Mapping[str, Any]]


class MetricsRunItem(BaseModel):
    id: str
    task_id: str
    agent_name: str
    runtime_sdk: str = ""
    provider: str = ""
    model: str = ""
    effort: str | None = None
    cost_usd: float
    estimated_cost_usd: float = 0.0
    estimated_codex_credits: float | None = None
    cost_source: str = ""
    pricing_model: str = ""
    pricing_note: str = ""
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
    observability: dict | None = None
    started_at: datetime
    completed_at: datetime | None


class MetricsResponse(BaseModel):
    total_cost: float
    total_estimated_cost_usd: float = 0.0
    total_estimated_codex_credits: float | None = None
    total_tokens: int
    total_runs: int
    gate_pass_rate: float
    optimization_summary: dict[str, Any] = Field(default_factory=dict)
    optimization_decision: dict[str, Any] = Field(default_factory=dict)
    runtime_decision_summary: dict[str, Any] = Field(default_factory=dict)
    deterministic_script_candidates: list[dict[str, Any]] = Field(default_factory=list)
    voice_ledger: dict[str, Any] = Field(default_factory=dict)
    context_budget: dict[str, Any] = Field(default_factory=dict)
    runs: list[MetricsRunItem]


def serialize_metric_run(run: AgentRun) -> MetricsRunItem:
    cost = estimate_run_cost(
        model=getattr(run, "model", "") or "",
        input_tokens=run.tokens_input,
        cached_input_tokens=run.tokens_cached,
        output_tokens=run.tokens_output,
        actual_cost_usd=run.cost_usd,
        runtime_sdk=getattr(run, "runtime_sdk", "") or "",
        provider=getattr(run, "provider", "") or "",
    )
    return MetricsRunItem(
        id=run.id,
        task_id=run.task_id,
        agent_name=run.agent_name,
        runtime_sdk=getattr(run, "runtime_sdk", "") or "",
        provider=getattr(run, "provider", "") or "",
        model=getattr(run, "model", "") or "",
        effort=getattr(run, "effort", None),
        cost_usd=run.cost_usd,
        estimated_cost_usd=float(cost["estimated_cost_usd"] or 0.0),
        estimated_codex_credits=cost["estimated_codex_credits"],
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
        diff_summary=bounded_diff_summary(getattr(run, "diff_summary", None)),
        observability=bounded_metrics_value(getattr(run, "observability", None)),
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


def _degraded_observability_payload(
    reason: str,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    payload = {
        "available": False,
        "status": "degraded",
        "reason": "observability_unavailable",
        "detail": reason,
    }
    context_budget = summarize_context_budgets([])
    context_budget.update(payload)
    return (
        dict(payload),
        dict(payload),
        [{"code": "observability_unavailable", "severity": "medium", **payload}],
        context_budget,
    )


def _chat_run_item(
    event: ChatEvent, payload: dict[str, Any], started_at: datetime
) -> MetricsRunItem:
    duration_ms = max(int((event.created_at - started_at).total_seconds() * 1000), 0)
    usage = chat_status_token_usage(payload)
    cost = estimate_run_cost(
        model=str(payload.get("model", "") or ""),
        input_tokens=usage["tokens_input"],
        cached_input_tokens=usage["tokens_cached"],
        output_tokens=usage["tokens_output"],
        actual_cost_usd=float(payload.get("cost_usd", 0.0) or 0.0),
        runtime_sdk=str(payload.get("runtime_sdk", "") or ""),
        provider=str(payload.get("provider", "") or ""),
    )
    return MetricsRunItem(
        id=event.id,
        task_id=event.session_id,
        agent_name="agent-chat",
        runtime_sdk=str(payload.get("runtime_sdk", "") or ""),
        provider=str(payload.get("provider", "") or ""),
        model=str(payload.get("model", "") or ""),
        effort=str(payload.get("effort", "") or "") or None,
        cost_usd=float(payload.get("cost_usd", 0.0) or 0.0),
        estimated_cost_usd=float(cost["estimated_cost_usd"] or 0.0),
        estimated_codex_credits=cost["estimated_codex_credits"],
        cost_source=str(cost["cost_source"] or ""),
        pricing_model=str(cost["pricing_model"] or ""),
        pricing_note=str(cost["pricing_note"] or ""),
        tokens_input=usage["tokens_input"],
        tokens_output=usage["tokens_output"],
        tokens_cached=usage["tokens_cached"],
        num_turns=int(payload.get("current_turn", 0) or 0),
        duration_ms=duration_ms,
        stop_reason=None,
        status="failed" if event.status in {"failed", "error"} else "completed",
        error=None,
        observability=(
            bounded_metrics_value(payload.get("observability"))
            if isinstance(payload.get("observability"), dict)
            else None
        ),
        started_at=started_at,
        completed_at=event.created_at,
    )


async def _load_recent_chat_runs(
    db: AsyncSession, *, event_scan_limit: int
) -> list[MetricsRunItem]:
    event_result = await db.execute(
        select(ChatEvent)
        .where(ChatEvent.event_type == "run_status")
        .order_by(ChatEvent.created_at.desc())
        .limit(event_scan_limit)
    )
    run_events = list(reversed(event_result.scalars().all()))
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
        chat_runs.append(_chat_run_item(event, payload, started_at))
    return chat_runs


async def _load_voice_ledger(db: AsyncSession) -> dict[str, Any]:
    voice_event_result = await db.execute(
        select(ChatEvent)
        .where(ChatEvent.event_type.in_(VOICE_LEDGER_EVENT_TYPES))
        .order_by(ChatEvent.created_at.desc())
        .limit(100)
    )
    return build_realtime_voice_ledger(list(voice_event_result.scalars().all()))


async def _load_active_run_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count(AgentRun.id)).where(AgentRun.status == "running"))
    return int(result.scalar() or 0)


async def _load_run_aggregates(db: AsyncSession) -> tuple[int, float, int]:
    run_count_result = await db.execute(
        select(
            func.count(AgentRun.id),
            func.coalesce(func.sum(AgentRun.cost_usd), 0.0),
            func.coalesce(func.sum(AgentRun.tokens_input + AgentRun.tokens_output), 0),
        )
    )
    orchestrator_count, orchestrator_cost, orchestrator_tokens = run_count_result.one()
    return (
        int(orchestrator_count or 0),
        float(orchestrator_cost or 0.0),
        int(orchestrator_tokens or 0),
    )


async def _load_chat_aggregates(db: AsyncSession) -> tuple[int, float, int]:
    completed_chat_filter = (ChatEvent.event_type == "run_status") & (
        (ChatEvent.status.in_(["completed", "failed", "error"]))
        | (func.json_extract(ChatEvent.payload_json, "$.running") == 0)
    )
    chat_input = func.coalesce(
        cast(func.json_extract(ChatEvent.payload_json, "$.tokens_input"), Integer), 0
    )
    chat_output = func.coalesce(
        cast(func.json_extract(ChatEvent.payload_json, "$.tokens_output"), Integer), 0
    )
    chat_tokens_used = func.coalesce(
        cast(func.json_extract(ChatEvent.payload_json, "$.tokens_used"), Integer), 0
    )
    chat_token_expr = case(
        (chat_input + chat_output > 0, chat_input + chat_output),
        else_=chat_tokens_used,
    )
    chat_aggregate_result = await db.execute(
        select(
            func.count(ChatEvent.id),
            func.coalesce(
                func.sum(cast(func.json_extract(ChatEvent.payload_json, "$.cost_usd"), Float)),
                0,
            ),
            func.coalesce(func.sum(chat_token_expr), 0),
        ).where(completed_chat_filter)
    )
    chat_count, chat_cost, chat_tokens = chat_aggregate_result.one()
    return int(chat_count or 0), float(chat_cost or 0.0), int(chat_tokens or 0)


async def _load_gate_pass_rate(db: AsyncSession) -> float:
    gate_aggregate_result = await db.execute(
        select(
            func.count(GateResult.id),
            func.coalesce(
                func.sum(case((GateResult.status == "pass", 1), else_=0)),
                0,
            ),
        )
    )
    gate_count, gate_pass_count = gate_aggregate_result.one()
    return (int(gate_pass_count) / int(gate_count) * 100) if gate_count else 0


def _load_observability_payloads(
    project_root: Path,
    observability_summary: ObservabilitySummary,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    context_budget_payload: dict[str, Any] = summarize_context_budgets([])
    try:
        db_path = find_agent_builder_dir(project_root).resolve() / "agent_builder.db"
        observability = observability_summary(db_path)
        runtime_decision_summary_payload = dict(observability.get("runtime_decision_summary", {}))
        optimization_decision_payload = dict(observability.get("optimization_decision", {}))
        deterministic_candidates = list(observability.get("deterministic_script_candidates", []))
        runtime_aggregates_payload = observability.get("runtime_aggregates", {})
        if isinstance(runtime_aggregates_payload, dict):
            context_budget_payload = runtime_aggregates_payload.get("context_budget", {})
        return (
            runtime_decision_summary_payload,
            optimization_decision_payload,
            deterministic_candidates,
            context_budget_payload,
        )
    except Exception as exc:
        return _degraded_observability_payload(str(exc))


async def load_dashboard_metrics_response(
    db: AsyncSession,
    project_root: Path,
    *,
    run_limit: int = METRICS_RUN_LIMIT,
    chat_event_scan_limit: int = METRICS_CHAT_EVENT_SCAN_LIMIT,
    observability_summary: ObservabilitySummary = dashboard_observability_summary,
) -> MetricsResponse:
    result = await db.execute(
        select(AgentRun).order_by(AgentRun.started_at.desc()).limit(run_limit)
    )
    orchestrator_runs = result.scalars().all()

    chat_runs = await _load_recent_chat_runs(db, event_scan_limit=chat_event_scan_limit)
    voice_ledger = await _load_voice_ledger(db)
    orchestrator_count, orchestrator_cost, orchestrator_tokens = await _load_run_aggregates(db)
    chat_count, chat_cost, chat_tokens = await _load_chat_aggregates(db)
    gate_pass_rate = await _load_gate_pass_rate(db)
    active_run_count = await _load_active_run_count(db)

    all_runs = [
        *[serialize_metric_run(run) for run in orchestrator_runs],
        *chat_runs,
    ]
    all_runs.sort(key=lambda run: run.completed_at or run.started_at, reverse=True)
    optimization_summary = summarize_runs_for_optimization(all_runs)
    if active_run_count > 0:
        optimization_summary = {
            **optimization_summary,
            "active_runs": active_run_count,
            "active_runs_note": (
                f"{active_run_count} run(s) in progress — token data not yet available. "
                "Check again after the run completes."
            ),
        }
    total_estimated_cost_usd = sum(run.estimated_cost_usd for run in all_runs)
    credit_values = [
        run.estimated_codex_credits for run in all_runs if run.estimated_codex_credits is not None
    ]
    (
        runtime_decision_summary_payload,
        optimization_decision_payload,
        deterministic_candidates,
        context_budget_payload,
    ) = _load_observability_payloads(project_root, observability_summary)
    return MetricsResponse(
        total_cost=orchestrator_cost + chat_cost,
        total_estimated_cost_usd=total_estimated_cost_usd,
        total_estimated_codex_credits=sum(credit_values) if credit_values else None,
        total_tokens=orchestrator_tokens + chat_tokens,
        total_runs=orchestrator_count + chat_count,
        gate_pass_rate=gate_pass_rate,
        optimization_summary=optimization_summary,
        optimization_decision=optimization_decision_payload,
        runtime_decision_summary=runtime_decision_summary_payload,
        deterministic_script_candidates=deterministic_candidates,
        voice_ledger=voice_ledger,
        context_budget=context_budget_payload,
        runs=all_runs,
    )
