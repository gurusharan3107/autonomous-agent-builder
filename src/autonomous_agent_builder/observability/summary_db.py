"""SQLite query helpers and row-aggregation utilities extracted from observability summary."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from autonomous_agent_builder.services.context_budget import summarize_context_budgets
from autonomous_agent_builder.services.token_costing import estimate_run_cost


def _column_or_default(columns: set[str], column: str, default: str, alias: str) -> str:
    return f"{column} as {alias}" if column in columns else f"{default} as {alias}"


def _window_token_totals(
    conn: sqlite3.Connection,
    *,
    start_iso: str | None,
    end_iso: str | None,
    exclude_agents: tuple[str, ...] = ("optimization-agent",),
) -> dict[str, int]:
    """Return delivery token sum and run count for agent_runs in [start_iso, end_iso).

    Token formula: sum(max(tokens_input - tokens_cached, 0) + tokens_output).
    Uses julianday() for safe ISO8601 timezone comparison (Z vs +00:00).
    start_iso=None means open-start; end_iso=None means open-end.
    Rows with null/empty started_at are excluded.
    """
    if not _table_exists(conn, "agent_runs"):
        return {"tokens": 0, "runs": 0}
    columns = _table_columns(conn, "agent_runs")
    if "started_at" not in columns:
        return {"tokens": 0, "runs": 0}

    tokens_input = "coalesce(tokens_input, 0)"
    tokens_cached = "coalesce(tokens_cached, 0)" if "tokens_cached" in columns else "0"
    tokens_output = "coalesce(tokens_output, 0)"
    token_expr = f"max({tokens_input} - {tokens_cached}, 0) + {tokens_output}"

    conditions: list[str] = [
        "started_at is not null",
        "started_at != ''",
    ]
    params: list[Any] = []

    if exclude_agents:
        placeholders = ", ".join("?" for _ in exclude_agents)
        conditions.append(f"agent_name not in ({placeholders})")
        params.extend(exclude_agents)

    if start_iso is not None:
        conditions.append("julianday(started_at) >= julianday(?)")
        params.append(start_iso)
    if end_iso is not None:
        conditions.append("julianday(started_at) < julianday(?)")
        params.append(end_iso)

    where = "where " + " and ".join(conditions)
    row = conn.execute(
        f"select coalesce(sum({token_expr}), 0) as tokens, count(*) as runs"
        f" from agent_runs {where}",
        params,
    ).fetchone()
    if row is None:
        return {"tokens": 0, "runs": 0}
    return {"tokens": int(row[0] or 0), "runs": int(row[1] or 0)}


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return (
        conn.execute(
            "select 1 from sqlite_master where type = 'table' and name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"pragma table_info({table_name})").fetchall()}


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _maybe_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _stop_reason_counts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "agent_runs"):
        return []
    return [
        _row_dict(row)
        for row in conn.execute(
            """
            select coalesce(stop_reason, 'unknown') as stop_reason, count(*) as count
            from agent_runs
            group by coalesce(stop_reason, 'unknown')
            order by count desc
            """
        ).fetchall()
    ]


def _tool_counts(conn: sqlite3.Connection) -> tuple[list[dict[str, Any]], int]:
    if not _table_exists(conn, "agent_run_events"):
        return [], 0
    count = int(conn.execute("select count(*) from agent_run_events").fetchone()[0] or 0)
    rows = [
        _row_dict(row)
        for row in conn.execute(
            """
            select coalesce(tool_name, event_type, 'unknown') as tool_name, count(*) as calls
            from agent_run_events
            group by coalesce(tool_name, event_type, 'unknown')
            order by count(*) desc
            """
        ).fetchall()
    ]
    return rows, count


def _event_types(conn: sqlite3.Connection) -> list[str]:
    if not _table_exists(conn, "chat_events"):
        return []
    return [
        str(row["event_type"])
        for row in conn.execute(
            "select distinct event_type from chat_events order by event_type"
        ).fetchall()
        if row["event_type"]
    ]


def _repeated_retrieval_signal(tool_counts: list[dict[str, Any]]) -> dict[str, Any]:
    retrieval_tools = {"Glob", "Grep", "Read", "rg", "grep"}
    summary_tools = {"mcp__builder__kb_search", "mcp__builder__memory_search"}
    retrieval_rows = [
        row for row in tool_counts if str(row.get("tool_name") or "") in retrieval_tools
    ]
    repeated = [row for row in retrieval_rows if int(row.get("calls") or 0) >= 5]
    strong_search = [
        row
        for row in retrieval_rows
        if str(row.get("tool_name") or "") != "Read" and int(row.get("calls") or 0) >= 5
    ]
    summary_rows = [row for row in tool_counts if str(row.get("tool_name") or "") in summary_tools]
    summary_calls = sum(int(row.get("calls") or 0) for row in summary_rows)
    detected = bool(repeated) and bool(strong_search) and summary_calls == 0
    return {
        "detected": detected,
        "tools": repeated,
        "summary_tools": summary_rows,
        "summary_calls": summary_calls,
    }


def _agent_run_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "agent_runs"):
        return []
    columns = _table_columns(conn, "agent_runs")
    select_parts = [
        "agent_name",
        _column_or_default(columns, "runtime_sdk", "''", "runtime_sdk"),
        _column_or_default(columns, "provider", "''", "provider"),
        _column_or_default(columns, "model", "''", "model"),
        _column_or_default(columns, "effort", "''", "effort"),
        "coalesce(num_turns, 0) as turns",
        "coalesce(tokens_input, 0) as input_tokens",
        "coalesce(tokens_output, 0) as output_tokens",
        "coalesce(tokens_cached, 0) as cached_tokens",
        "coalesce(cost_usd, 0.0) as cost_usd",
        "coalesce(duration_ms, 0) as duration_ms",
        _column_or_default(columns, "stop_reason", "'unknown'", "stop_reason"),
        _column_or_default(columns, "observability", "null", "observability"),
    ]
    rows = conn.execute(f"select {', '.join(select_parts)} from agent_runs").fetchall()
    normalized: list[dict[str, Any]] = []
    for row in rows:
        item = _row_dict(row)
        item["runs"] = 1
        item["observability"] = _maybe_json_dict(item.get("observability"))
        item["tokens_input"] = int(item.get("input_tokens") or 0)
        item["tokens_output"] = int(item.get("output_tokens") or 0)
        item["tokens_cached"] = int(item.get("cached_tokens") or 0)
        item.update(
            estimate_run_cost(
                model=str(item.get("model") or ""),
                input_tokens=int(item.get("input_tokens") or 0),
                cached_input_tokens=int(item.get("cached_tokens") or 0),
                output_tokens=int(item.get("output_tokens") or 0),
                actual_cost_usd=float(item.get("cost_usd") or 0.0),
                runtime_sdk=str(item.get("runtime_sdk") or ""),
                provider=str(item.get("provider") or ""),
            )
        )
        normalized.append(item)
    return normalized


def _chat_run_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not _table_exists(conn, "chat_events"):
        return []
    rows: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        select payload_json
        from chat_events
        where event_type = 'run_status' and status in ('completed', 'failed', 'error', 'blocked')
        """
    ).fetchall():
        payload = _maybe_json_dict(row["payload_json"])
        if payload.get("running") is True:
            continue
        item = {
            "agent_name": str(payload.get("agent_name") or "agent-chat"),
            "runtime_sdk": str(payload.get("runtime_sdk") or ""),
            "provider": str(payload.get("provider") or ""),
            "model": str(payload.get("model") or ""),
            "effort": str(payload.get("effort") or ""),
            "runs": 1,
            "turns": int(payload.get("current_turn") or 0),
            "input_tokens": int(payload.get("tokens_input") or 0),
            "output_tokens": int(
                payload.get("tokens_output")
                or payload.get("tokens_used")
                or payload.get("total_tokens")
                or 0
            ),
            "cached_tokens": int(payload.get("cached_tokens") or 0),
            "cost_usd": float(payload.get("cost_usd") or 0.0),
            "duration_ms": int(payload.get("duration_ms") or 0),
            "stop_reason": str(payload.get("stop_reason") or "unknown"),
            "observability": (
                payload.get("observability")
                if isinstance(payload.get("observability"), dict)
                else {}
            ),
        }
        item["tokens_input"] = item["input_tokens"]
        item["tokens_output"] = item["output_tokens"]
        item["tokens_cached"] = item["cached_tokens"]
        item.update(
            estimate_run_cost(
                model=item["model"],
                input_tokens=item["input_tokens"],
                cached_input_tokens=item["cached_tokens"],
                output_tokens=item["output_tokens"],
                actual_cost_usd=item["cost_usd"],
                runtime_sdk=item["runtime_sdk"],
                provider=item["provider"],
            )
        )
        rows.append(item)
    return rows


def _runtime_recovery_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    resume_retries: list[dict[str, Any]] = []
    for row in rows:
        observability = row.get("observability")
        if not isinstance(observability, dict):
            continue
        retry = observability.get("resume_retry")
        if not isinstance(retry, dict):
            continue
        resume_retries.append(
            {
                "agent_name": str(row.get("agent_name") or ""),
                "runtime_sdk": str(row.get("runtime_sdk") or ""),
                "model": str(row.get("model") or ""),
                "fallback": str(retry.get("fallback") or ""),
                "reason": str(retry.get("reason") or "")[:500],
            }
        )
    return {
        "resume_retry_count": len(resume_retries),
        "latest": resume_retries[-1] if resume_retries else {},
    }


def _context_budget_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "chat_events"):
        return summarize_context_budgets([])
    order_clause = (
        "order by created_at asc" if "created_at" in _table_columns(conn, "chat_events") else ""
    )
    rows = conn.execute(
        f"""
        select payload_json
        from chat_events
        where event_type = 'context_budget'
        {order_clause}
        """
    ).fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        payload = row["payload_json"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        if isinstance(payload, dict):
            events.append(payload)
    return summarize_context_budgets(events)


def _merge_rows(rows: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(str(row.get(name) or "unknown") for name in keys)
        current = merged.setdefault(
            key,
            {
                **{name: key[index] for index, name in enumerate(keys)},
                "runs": 0,
                "turns": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_tokens": 0,
                "cost_usd": 0.0,
                "estimated_cost_usd": 0.0,
                "estimated_codex_credits": 0.0,
                "duration_ms": 0,
            },
        )
        _add_row(current, row)
    return sorted(
        merged.values(),
        key=lambda item: (
            float(item.get("estimated_cost_usd") or 0.0),
            int(item.get("duration_ms") or 0),
        ),
        reverse=True,
    )


def _sum_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    current = {
        "runs": 0,
        "turns": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "cost_usd": 0.0,
        "estimated_cost_usd": 0.0,
        "estimated_codex_credits": 0.0,
        "duration_ms": 0,
    }
    for row in rows:
        _add_row(current, row)
    if current["estimated_codex_credits"] == 0.0:
        current["estimated_codex_credits"] = None
    return current


def _add_row(current: dict[str, Any], row: dict[str, Any]) -> None:
    current["runs"] += int(row.get("runs") or 0)
    current["turns"] += int(row.get("turns") or 0)
    current["input_tokens"] += int(row.get("input_tokens") or 0)
    current["output_tokens"] += int(row.get("output_tokens") or 0)
    current["cached_tokens"] += int(row.get("cached_tokens") or 0)
    current["cost_usd"] += float(row.get("cost_usd") or 0.0)
    current["estimated_cost_usd"] += float(row.get("estimated_cost_usd") or 0.0)
    current["estimated_codex_credits"] += float(row.get("estimated_codex_credits") or 0.0)
    current["duration_ms"] += int(row.get("duration_ms") or 0)


def _provider_payload(depends_on: Any) -> dict[str, Any]:
    parsed = _maybe_json_dict(depends_on)
    provider = parsed.get("provider_limit")
    return provider if isinstance(provider, dict) else {}
