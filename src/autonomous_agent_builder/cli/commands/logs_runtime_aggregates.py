"""Repo-local runtime aggregates queries for `builder logs analyze`.

Extracted from `logs.py` so the CLI command surface stays focused on
typer wiring and timeline rendering. Public entry points:

- `runtime_aggregates(db_path, session_id=None)` returns the compact
  aggregate payload consumed by the `analyze` command.
- `selected_runtime_sdk()` reports the configured runtime SDK lane.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autonomous_agent_builder.cli.commands.logs_db_utils import (
    maybe_json_dict,
    row_dict,
    table_columns,
    table_exists,
)
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.observability.runtime_optimization import (
    optimization_decision_summary,
    runtime_decision_summary,
)
from autonomous_agent_builder.observability.summary_db import (
    _window_token_totals,
)
from autonomous_agent_builder.runtime.factory import resolve_runtime_config
from autonomous_agent_builder.services.codex_optimization import (
    summarize_runs_for_optimization,
)


def window_token_totals(
    db_path: Path,
    *,
    start_iso: str | None,
    end_iso: str | None,
    exclude_agents: tuple[str, ...] = ("optimization-agent",),
) -> dict[str, int]:
    """Public wrapper: open db_path, delegate to _window_token_totals, close."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return _window_token_totals(
            conn,
            start_iso=start_iso,
            end_iso=end_iso,
            exclude_agents=exclude_agents,
        )
    finally:
        conn.close()


def _session_task_filter(
    conn: sqlite3.Connection, session_id: str | None
) -> tuple[str, tuple[Any, ...]]:
    """Return (where_fragment, params) scoping `task_id` to a chat session.

    Empty fragment when no session_id provided, or when the linkage column is
    absent on this DB (older repos without the `tasks.chat_session_id` add).
    """
    if not session_id or not table_exists(conn, "tasks"):
        return "", ()
    if "chat_session_id" not in table_columns(conn, "tasks"):
        return "", ()
    return "task_id IN (SELECT id FROM tasks WHERE chat_session_id = ?)", (session_id,)


def runtime_aggregates(db_path: Path, session_id: str | None = None) -> dict[str, Any]:
    """Return compact repo-local runtime aggregates for optimization review.

    When ``session_id`` is provided, all aggregate queries are scoped to the
    chat session's tasks via ``tasks.chat_session_id``. Without it, aggregates
    are global (preserves pre-existing behavior for non-session callers).
    """
    if not db_path.exists():
        return {"available": False, "reason": "agent_builder_db_missing"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if not table_exists(conn, "agent_runs"):
            return {"available": False, "reason": "agent_runs_table_missing"}
        run_columns = table_columns(conn, "agent_runs")
        task_filter, filter_params = _session_task_filter(conn, session_id)
        where_clause = f"where {task_filter}" if task_filter else ""

        by_agent = [
            row_dict(row)
            for row in conn.execute(
                f"""
                select agent_name,
                       count(*) as runs,
                       coalesce(sum(num_turns), 0) as turns,
                       coalesce(sum(tokens_input), 0) as input_tokens,
                       coalesce(sum(tokens_output), 0) as output_tokens,
                       coalesce(sum(tokens_cached), 0) as cached_tokens,
                       coalesce(sum(cost_usd), 0.0) as cost_usd,
                       coalesce(sum(duration_ms), 0) as duration_ms
                from agent_runs
                {where_clause}
                group by agent_name
                order by coalesce(sum(cost_usd), 0.0) desc
                """,
                filter_params,
            ).fetchall()
        ]
        by_runtime: list[dict[str, Any]] = []
        if {"runtime_sdk", "provider"}.issubset(run_columns):
            by_runtime = [
                row_dict(row)
                for row in conn.execute(
                    f"""
                    select coalesce(runtime_sdk, '') as runtime_sdk,
                           coalesce(provider, '') as provider,
                           count(*) as runs,
                           coalesce(sum(num_turns), 0) as turns,
                           coalesce(sum(tokens_input), 0) as input_tokens,
                           coalesce(sum(tokens_output), 0) as output_tokens,
                           coalesce(sum(tokens_cached), 0) as cached_tokens,
                           coalesce(sum(cost_usd), 0.0) as cost_usd,
                           coalesce(sum(duration_ms), 0) as duration_ms
                    from agent_runs
                    {where_clause}
                    group by coalesce(runtime_sdk, ''), coalesce(provider, '')
                    order by count(*) desc
                    """,
                    filter_params,
                ).fetchall()
            ]
        approval_wait = _approval_wait_summary(conn, session_id=session_id)
        tool_counts, tool_event_count = _tool_counts(conn, session_id=session_id)
        optimization_summary = _optimization_summary(conn, session_id=session_id)
        totals = _sum_agent_rows(by_agent)
        has_runtime_runs = int(totals.get("runs") or 0) > 0
        payload = {
            "available": True,
            "session_scoped": bool(task_filter),
            "by_agent": by_agent,
            "by_runtime": by_runtime,
            "totals": totals,
            "stop_reasons": _stop_reason_counts(conn, session_id=session_id),
            "phase_ceremony": _phase_ceremony_summary(by_agent, approval_wait),
            "approval_wait": approval_wait,
            "provider_limits": _provider_limit_summary(conn, session_id=session_id),
            "optimization_summary": optimization_summary,
            "tool_observability": {
                "agent_run_events_available": table_exists(conn, "agent_run_events"),
                "agent_run_event_count": tool_event_count,
                "missing_tool_events": table_exists(conn, "agent_run_events")
                and has_runtime_runs
                and tool_event_count == 0,
                "tool_counts": tool_counts,
                "repeated_retrieval_signal": _repeated_retrieval_signal(tool_counts),
            },
        }
        payload["deterministic_script_candidates"] = runtime_decision_summary(
            selected_runtime_sdk(),
            aggregates=payload,
            optimization=optimization_summary,
        ).get("deterministic_script_candidates", [])
        payload["optimization_decision"] = optimization_decision_summary(
            selected_runtime_sdk(),
            aggregates=payload,
            optimization=optimization_summary,
        )
        return payload
    finally:
        conn.close()


def selected_runtime_sdk() -> str:
    try:
        config = resolve_runtime_config(get_settings())
    except Exception:
        return "claude_agent_sdk"
    sdk = str(config.get("sdk") or "claude")
    return "codex_sdk" if sdk.startswith("codex") else "claude_agent_sdk"


def _optimization_summary(
    conn: sqlite3.Connection, *, session_id: str | None = None
) -> dict[str, Any]:
    if not table_exists(conn, "agent_runs"):
        return {"available": False, "reason": "agent_runs_missing"}
    columns = table_columns(conn, "agent_runs")
    observability_select = (
        "observability" if "observability" in columns else "null as observability"
    )
    runtime_select = "runtime_sdk" if "runtime_sdk" in columns else "'' as runtime_sdk"
    task_filter, filter_params = _session_task_filter(conn, session_id)
    where_clause = f"where {task_filter}" if task_filter else ""
    rows = conn.execute(
        f"""
        select agent_name,
               {runtime_select},
               tokens_input,
               tokens_output,
               tokens_cached,
               {observability_select}
        from agent_runs
        {where_clause}
        """,
        filter_params,
    ).fetchall()
    runs: list[dict[str, Any]] = []
    for row in rows:
        item = row_dict(row)
        item["observability"] = maybe_json_dict(item.get("observability"))
        runs.append(item)
    summary = summarize_runs_for_optimization(runs)
    summary["available"] = True
    return summary


def _sum_agent_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "runs": sum(int(row.get("runs") or 0) for row in rows),
        "turns": sum(int(row.get("turns") or 0) for row in rows),
        "input_tokens": sum(int(row.get("input_tokens") or 0) for row in rows),
        "output_tokens": sum(int(row.get("output_tokens") or 0) for row in rows),
        "cached_tokens": sum(int(row.get("cached_tokens") or 0) for row in rows),
        "cost_usd": sum(float(row.get("cost_usd") or 0.0) for row in rows),
        "duration_ms": sum(int(row.get("duration_ms") or 0) for row in rows),
    }


def _stop_reason_counts(
    conn: sqlite3.Connection, *, session_id: str | None = None
) -> list[dict[str, Any]]:
    task_filter, filter_params = _session_task_filter(conn, session_id)
    where_clause = f"where {task_filter}" if task_filter else ""
    return [
        row_dict(row)
        for row in conn.execute(
            f"""
            select coalesce(stop_reason, 'unknown') as stop_reason, count(*) as count
            from agent_runs
            {where_clause}
            group by coalesce(stop_reason, 'unknown')
            order by count desc
            """,
            filter_params,
        ).fetchall()
    ]


def _tool_counts(
    conn: sqlite3.Connection, *, session_id: str | None = None
) -> tuple[list[dict[str, Any]], int]:
    if not table_exists(conn, "agent_run_events"):
        return [], 0
    task_filter, filter_params = _session_task_filter(conn, session_id)
    if task_filter:
        run_filter = (
            f"where run_id IN (SELECT id FROM agent_runs WHERE {task_filter})"
        )
    else:
        run_filter = ""
    event_count = int(
        conn.execute(
            f"select count(*) from agent_run_events {run_filter}", filter_params
        ).fetchone()[0]
        or 0
    )
    rows = conn.execute(
        f"""
        select coalesce(tool_name, event_type, 'unknown') as tool_name, count(*) as calls
        from agent_run_events
        {run_filter}
        group by coalesce(tool_name, event_type, 'unknown')
        order by calls desc
        limit 20
        """,
        filter_params,
    ).fetchall()
    return [row_dict(row) for row in rows], event_count


def _approval_wait_summary(
    conn: sqlite3.Connection, *, session_id: str | None = None
) -> dict[str, Any]:
    if not table_exists(conn, "approval_gates"):
        return {"available": False, "reason": "approval_gates_table_missing"}
    task_filter, filter_params = _session_task_filter(conn, session_id)
    where_clause = f"where {task_filter}" if task_filter else ""
    by_gate = [
        row_dict(row)
        for row in conn.execute(
            f"""
            select gate_type,
                   count(*) as total,
                   sum(case when resolved_at is not null then 1 else 0 end) as resolved,
                   coalesce(avg((julianday(resolved_at) - julianday(created_at)) * 86400000), 0) as avg_wait_ms
            from approval_gates
            {where_clause}
            group by gate_type
            order by gate_type
            """,
            filter_params,
        ).fetchall()
    ]
    return {
        "available": True,
        "by_gate_type": by_gate,
        "total": sum(int(row.get("total") or 0) for row in by_gate),
        "resolved": sum(int(row.get("resolved") or 0) for row in by_gate),
        "avg_wait_ms": _weighted_average_wait(by_gate),
    }


def _weighted_average_wait(rows: list[dict[str, Any]]) -> float:
    resolved = sum(int(row.get("resolved") or 0) for row in rows)
    if resolved == 0:
        return 0.0
    weighted = sum(
        float(row.get("avg_wait_ms") or 0.0) * int(row.get("resolved") or 0) for row in rows
    )
    return weighted / resolved


def _provider_limit_summary(
    conn: sqlite3.Connection, *, session_id: str | None = None
) -> dict[str, Any]:
    if not table_exists(conn, "tasks"):
        return {"available": False, "reason": "tasks_table_missing"}
    extra_clause = ""
    params: tuple[Any, ...] = ()
    if session_id and "chat_session_id" in table_columns(conn, "tasks"):
        extra_clause = " and chat_session_id = ?"
        params = (session_id,)
    rows = conn.execute(
        "select id, status, depends_on from tasks where status = 'capability_limit'"
        + extra_clause,
        params,
    ).fetchall()
    now = datetime.now(UTC)
    ready = 0
    waiting = 0
    reset_times: list[str] = []
    for row in rows:
        payload = _provider_payload(row["depends_on"])
        reset_at = _parse_iso_datetime(payload.get("reset_at"))
        if reset_at is not None:
            reset_times.append(reset_at.isoformat())
        if reset_at is not None and reset_at <= now:
            ready += 1
        else:
            waiting += 1
    return {
        "available": True,
        "count": len(rows),
        "ready_to_resume": ready,
        "waiting_for_reset": waiting,
        "reset_at": reset_times,
    }


def _provider_payload(depends_on: Any) -> dict[str, Any]:
    parsed = maybe_json_dict(depends_on)
    provider = parsed.get("provider_limit")
    return provider if isinstance(provider, dict) else {}


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _phase_ceremony_summary(
    by_agent: list[dict[str, Any]],
    approval_wait: dict[str, Any],
) -> dict[str, Any]:
    by_name = {str(row.get("agent_name")): row for row in by_agent}
    planning_design_cost = _agent_cost(by_name, "planner") + _agent_cost(by_name, "designer")
    implementation_cost = _agent_cost(by_name, "code-gen")
    ratio = planning_design_cost / implementation_cost if implementation_cost else None
    return {
        "planning_design_cost_usd": planning_design_cost,
        "implementation_cost_usd": implementation_cost,
        "verification_cost_usd": _agent_cost(by_name, "build-verifier"),
        "integration_cost_usd": _agent_cost(by_name, "pr-creator"),
        "planning_design_to_implementation_ratio": ratio,
        "approval_wait_ms": approval_wait.get("avg_wait_ms", 0.0),
        "flag": (
            "planning_design_exceeds_implementation" if ratio is not None and ratio > 1.0 else ""
        ),
    }


def _agent_cost(by_name: dict[str, dict[str, Any]], agent_name: str) -> float:
    return float(by_name.get(agent_name, {}).get("cost_usd") or 0.0)


def _repeated_retrieval_signal(tool_counts: list[dict[str, Any]]) -> dict[str, Any]:
    retrieval_tools = {"Glob", "Grep", "Read", "rg", "grep"}
    summary_tools = {"mcp__builder__kb_search", "mcp__builder__memory_search"}
    retrieval_rows = [
        {"tool_name": row.get("tool_name"), "calls": row.get("calls")}
        for row in tool_counts
        if row.get("tool_name") in retrieval_tools
    ]
    repeated = [row for row in retrieval_rows if int(row.get("calls") or 0) >= 5]
    strong_search = [
        row
        for row in retrieval_rows
        if row.get("tool_name") != "Read" and int(row.get("calls") or 0) >= 5
    ]
    summary_rows = [
        {"tool_name": row.get("tool_name"), "calls": row.get("calls")}
        for row in tool_counts
        if row.get("tool_name") in summary_tools
    ]
    summary_calls = sum(int(row.get("calls") or 0) for row in summary_rows)
    return {
        "detected": bool(repeated) and bool(strong_search) and summary_calls == 0,
        "tools": repeated,
        "summary_tools": summary_rows,
        "summary_calls": summary_calls,
    }
