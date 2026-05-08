"""Chat and tool log inspection for the repo-local builder runtime."""

from __future__ import annotations

import json
import json as json_lib
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from autonomous_agent_builder.cli.client import EXIT_FAILURE, EXIT_INVALID_USAGE, EXIT_SUCCESS
from autonomous_agent_builder.cli.output import emit_error, render, table, truncate
from autonomous_agent_builder.cli.project_discovery import (
    ProjectNotFoundError,
    find_agent_builder_dir,
)
from autonomous_agent_builder.cli.retrieval import compact_results_payload
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.logs.diagnostics import summarize_chat_event
from autonomous_agent_builder.observability.runtime_optimization import (
    optimization_decision_summary,
    runtime_decision_summary,
)
from autonomous_agent_builder.observability.summary import dashboard_observability_summary
from autonomous_agent_builder.runtime.factory import resolve_runtime_config
from autonomous_agent_builder.services.codex_optimization import summarize_runs_for_optimization

app = typer.Typer(
    help=(
        "Inspect repo-local embedded chat logs and tool outcomes.\n\n"
        "Start here:\n"
        "  builder logs --error\n"
        "  builder logs --info --compact\n"
        "  builder logs --session <id>\n"
        "  builder logs --session <id> --raw --json\n"
        "  builder logs --error --follow --ndjson\n"
        "  builder logs --tool mcp__builder__kb_add --json\n"
    )
)

_INFO_TYPES = ("tool_result", "run_status", "specialist_status")
_DEFAULT_TYPES = ("tool_result", "tool_error", "run_error", "run_status", "specialist_status")
_PROMPT_EVENT_TYPES = ("user_message", "assistant_message", *_DEFAULT_TYPES)


def _db_path() -> Path:
    try:
        return find_agent_builder_dir(Path.cwd()).resolve() / "agent_builder.db"
    except ProjectNotFoundError as exc:
        raise RuntimeError(exc.hint or "Initialize this repo with 'builder init' first.") from exc


def _resolve_session_id(conn: sqlite3.Connection, session_id: str | None) -> str:
    if not session_id:
        row = conn.execute(
            "select id from chat_sessions order by updated_at desc, created_at desc limit 1"
        ).fetchone()
        return str(row["id"]) if row else ""

    exact = conn.execute("select id from chat_sessions where id = ?", (session_id,)).fetchone()
    if exact:
        return str(exact["id"])

    matches = conn.execute(
        "select id from chat_sessions where id like ? order by updated_at desc, created_at desc limit 2",
        (f"{session_id}%",),
    ).fetchall()
    if len(matches) == 1:
        return str(matches[0]["id"])
    if len(matches) > 1:
        raise ValueError(f"Session prefix '{session_id}' is ambiguous.")
    return session_id


def _load_rows(
    *,
    session_id: str | None,
    tool_name: str | None,
    event_type: str | None,
    errors_only: bool,
    info_only: bool,
    limit: int,
) -> list[dict[str, Any]]:
    db_path = _db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Log database not found at {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        resolved_session = _resolve_session_id(conn, session_id)

        if not resolved_session:
            return []

        clauses = ["session_id = ?"]
        params: list[Any] = [resolved_session]

        if errors_only:
            clauses.append("event_type in ('tool_error', 'run_error')")
        elif info_only:
            placeholders = ", ".join("?" for _ in _INFO_TYPES)
            clauses.append(f"event_type in ({placeholders})")
            params.extend(_INFO_TYPES)
        elif event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        else:
            placeholders = ", ".join("?" for _ in _DEFAULT_TYPES)
            clauses.append(f"event_type in ({placeholders})")
            params.extend(_DEFAULT_TYPES)

        if tool_name:
            clauses.append("json_extract(payload_json, '$.tool_name') = ?")
            params.append(tool_name)

        params.append(max(limit, 1))
        query = (
            "select id, session_id, event_type, status, payload_json, tool_use_id, response_to_event_id, created_at "
            "from chat_events "
            f"where {' and '.join(clauses)} "
            "order by created_at desc "
            "limit ?"
        )
        rows = conn.execute(query, params).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = row["payload_json"]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {"content": payload}
            items.append(
                {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "event_type": row["event_type"],
                    "status": row["status"],
                    "tool_use_id": row["tool_use_id"],
                    "response_to_event_id": row["response_to_event_id"],
                    "created_at": row["created_at"],
                    "payload": payload or {},
                }
            )
        return items
    finally:
        conn.close()


def _session_metadata(conn: sqlite3.Connection, session_id: str | None) -> dict[str, Any]:
    resolved_session = _resolve_session_id(conn, session_id)
    if not resolved_session:
        return {}
    row = conn.execute(
        "select * from chat_sessions where id = ?",
        (resolved_session,),
    ).fetchone()
    if row is None:
        return {"id": resolved_session}
    return {key: row[key] for key in row.keys()}


def _load_session_timeline(session_id: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    db_path = _db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Log database not found at {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        session = _session_metadata(conn, session_id)
        resolved_session = str(session.get("id", ""))
        if not resolved_session:
            return {}, []

        placeholders = ", ".join("?" for _ in _PROMPT_EVENT_TYPES)
        rows = conn.execute(
            f"""
            select id, session_id, event_type, status, payload_json, tool_use_id, response_to_event_id, created_at
            from chat_events
            where session_id = ? and event_type in ({placeholders})
            order by created_at asc
            """,
            (resolved_session, *_PROMPT_EVENT_TYPES),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = row["payload_json"]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {"content": payload}
            items.append(
                {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "event_type": row["event_type"],
                    "status": row["status"],
                    "tool_use_id": row["tool_use_id"],
                    "response_to_event_id": row["response_to_event_id"],
                    "created_at": row["created_at"],
                    "payload": payload or {},
                }
            )
        return session, items
    finally:
        conn.close()


def _render_line(item: dict[str, Any]) -> str:
    payload = item.get("payload", {})
    if not isinstance(payload, dict):
        payload = {"content": str(payload)}
    diagnostic = payload.get("diagnostic")
    if not isinstance(diagnostic, dict):
        diagnostic = summarize_chat_event(str(item.get("event_type", "")), payload)
    tool_name = str(diagnostic.get("tool_name", "") or payload.get("tool_name", "") or "-")
    summary = truncate(str(diagnostic.get("summary", "") or payload.get("content", "") or ""), 160).replace("\n", " ")
    return f"{str(item.get('created_at', ''))[:19]}  {item.get('event_type', ''):<16}  {tool_name:<28}  {summary}"


def _compact_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for item in items:
        payload = item.get("payload", {})
        if not isinstance(payload, dict):
            payload = {"content": str(payload)}
        diagnostic = payload.get("diagnostic")
        if not isinstance(diagnostic, dict):
            diagnostic = summarize_chat_event(str(item.get("event_type", "")), payload)
        event_type = str(item.get("event_type", ""))
        is_error = event_type in {"tool_error", "run_error"}
        row = {
            "id": item.get("id"),
            "event_type": event_type,
            "created_at": item.get("created_at"),
            "tool_name": diagnostic.get("tool_name", "") or payload.get("tool_name", ""),
            "outcome": diagnostic.get("outcome", ""),
            "summary": diagnostic.get("summary", ""),
        }
        input_focus = diagnostic.get("input_focus", "")
        if input_focus:
            row["input_focus"] = input_focus
        if is_error:
            error_message = diagnostic.get("error_message", "") or diagnostic.get("detail", "")
            if error_message:
                row["error_message"] = error_message
        next_action = diagnostic.get("next_action", "")
        if next_action:
            row["next_action"] = next_action
        compacted.append(row)
    return compacted


def _raw_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_rows: list[dict[str, Any]] = []
    for item in items:
        payload = item.get("payload", {})
        if not isinstance(payload, dict):
            payload = {"content": str(payload)}
        raw_rows.append(
            {
                "id": item.get("id"),
                "session_id": item.get("session_id"),
                "event_type": item.get("event_type"),
                "status": item.get("status"),
                "payload": payload,
                "tool_use_id": item.get("tool_use_id"),
                "response_to_event_id": item.get("response_to_event_id"),
                "created_at": item.get("created_at"),
            }
        )
    return raw_rows


def _text_preview(value: Any, *, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    return truncate(text, limit)


def _extract_text_json(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _context_signal(segment: dict[str, Any]) -> dict[str, Any]:
    user_prompt = str(segment.get("user_prompt", "")).lower()
    tool_names = [str(tool.get("tool_name", "")) for tool in segment.get("tools", [])]
    signals: list[str] = []

    if any(tool == "Glob" for tool in tool_names):
        signals.append("broad_file_discovery")
    if any(tool == "Read" for tool in tool_names) and any("which project" in user_prompt for _ in [0]):
        signals.append("file_read_for_identity_question")
    if any(tool == "Agent" for tool in tool_names):
        signals.append("delegated_subagent")
    if any(tool.startswith("mcp__builder__kb_") for tool in tool_names):
        signals.append("used_builder_knowledge")
    if "backlog" in user_prompt and not any(
        tool.startswith("mcp__builder__backlog") or tool.startswith("builder backlog") for tool in tool_names
    ):
        signals.append("backlog_not_checked_through_backlog_surface")

    if not tool_names:
        grade = "minimal"
    elif signals:
        grade = "review"
    else:
        grade = "targeted"
    return {"grade": grade, "signals": signals}


def _effective_observability(prompts: list[dict[str, Any]]) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for prompt in prompts:
        snapshot = prompt.get("observability")
        if isinstance(snapshot, dict) and snapshot:
            latest = snapshot
    if not latest:
        try:
            from autonomous_agent_builder.config import get_settings
            from autonomous_agent_builder.observability.runtime import resolve_claude_observability
            from autonomous_agent_builder.runtime.factory import resolve_runtime_config

            runtime_config = resolve_runtime_config(get_settings())
        except Exception:
            runtime_config = {}
        sdk = str(runtime_config.get("sdk") or "")
        if sdk.startswith("codex"):
            source = "codex_app_server" if sdk == "codex_sdk" else "codex_jsonl"
            latest = {
                "source": source,
                "runtime_sdk": sdk,
                "provider": str(runtime_config.get("provider") or ""),
            }
        elif sdk == "claude":
            latest = resolve_claude_observability().summary
            latest["runtime_sdk"] = sdk
            latest["provider"] = str(runtime_config.get("provider") or "")
    return latest


def _observability_coverage(prompts: list[dict[str, Any]]) -> dict[str, Any]:
    tool_count = sum(len(prompt.get("tools", [])) for prompt in prompts)
    error_count = sum(
        1
        for prompt in prompts
        for tool in prompt.get("tools", [])
        if tool.get("event_type") in {"tool_error", "run_error"} or tool.get("outcome") == "error"
    )
    delegation_count = sum(
        1
        for prompt in prompts
        for tool in prompt.get("tools", [])
        if tool.get("tool_name") == "Agent"
    )
    effective = _effective_observability(prompts)
    runtime_sdk = str(effective.get("runtime_sdk", ""))
    codex_runtime = runtime_sdk.startswith("codex")
    signal_state = effective.get("signal_state", {})
    telemetry_enabled = bool(effective.get("enabled"))
    traces_enabled = bool(signal_state.get("traces") or effective.get("traces_exporter"))
    metrics_enabled = bool(signal_state.get("metrics") or effective.get("metrics_exporter"))
    logs_enabled = bool(signal_state.get("logs") or effective.get("logs_exporter"))
    detailed_tracing = bool(effective.get("detailed_beta_tracing"))
    sensitive_flags = list(effective.get("sensitive_data_flags", []))
    endpoint_configured = bool(effective.get("endpoint_configured"))
    endpoint_placeholder = bool(effective.get("endpoint_placeholder"))
    collector = effective.get("collector", {}) if isinstance(effective.get("collector"), dict) else {}
    collector_checked = bool(collector.get("checked"))
    collector_reachable = collector.get("reachable")
    uses_otlp = any(
        "otlp" in {part.strip() for part in str(effective.get(key, "")).split(",")}
        for key in ("metrics_exporter", "logs_exporter", "traces_exporter")
    )
    missing = []
    if codex_runtime:
        if not effective.get("telemetry_source"):
            missing.append("codex_runtime_usage")
    else:
        if not metrics_enabled:
            missing.append("otel_metrics_exporter")
        if not logs_enabled:
            missing.append("otel_logs_exporter")
        if not traces_enabled:
            missing.append("otel_traces_exporter")
        if telemetry_enabled and uses_otlp and (not endpoint_configured or endpoint_placeholder):
            missing.append("otel_otlp_endpoint")
        if telemetry_enabled and uses_otlp and collector_checked and collector_reachable is not True:
            missing.append("otel_collector_unreachable")
        if not (telemetry_enabled and traces_enabled):
            missing.extend(
                [
                    "llm_request_span_latency",
                    "tool_execution_span_latency",
                    "traceparent_correlation",
                ]
            )
        if not detailed_tracing:
            missing.append("hook_span_timeline")
    missing_set = set(missing)
    if codex_runtime and "codex_runtime_usage" in missing_set:
        next_step = (
            "Run a Codex-backed chat or task dispatch; builder will normalize "
            "Codex runtime usage events into tokens, turns, and duration."
        )
    elif codex_runtime:
        next_step = "Codex runtime usage telemetry is available for analysis."
    elif not telemetry_enabled:
        next_step = (
            "Enable CLAUDE_CODE_ENABLE_TELEMETRY=1 with OTEL_METRICS_EXPORTER, "
            "OTEL_LOGS_EXPORTER, and OTEL_TRACES_EXPORTER for span-level analysis."
        )
    elif "otel_otlp_endpoint" in missing_set:
        next_step = "Configure a real OTLP collector endpoint before treating exported telemetry as usable."
    elif "otel_collector_unreachable" in missing_set:
        next_step = (
            "Start the local OTEL collector or change AAB_CLAUDE_OTEL_ENDPOINT; "
            "telemetry is configured but exports are not reachable."
        )
    elif missing_set == {"hook_span_timeline"}:
        next_step = (
            "OTEL is configured for metrics, logs, and traces; hook span timeline is not "
            "captured in builder-local events yet."
        )
    elif missing:
        next_step = "OTEL is partially configured; inspect missing_signals before relying on span-level analysis."
    else:
        next_step = "OTEL coverage is sufficient for span-level LLM and tool analysis."
    return {
        "source": effective.get("source", "builder_chat_events"),
        "runtime_sdk": runtime_sdk,
        "provider": effective.get("provider", ""),
        "telemetry_source": effective.get("telemetry_source", ""),
        "available_signals": [
            "session_id",
            "sdk_session_id",
            "prompt_events",
            "assistant_events",
            "tool_results",
            "run_status",
            "tokens_used",
            "cost_usd",
            "duration_ms",
            "stop_reason",
            "runtime_sdk",
            "provider",
            "observability",
        ],
        "counts": {
            "tools": tool_count,
            "errors": error_count,
            "delegations": delegation_count,
        },
        "otel": {
            "enabled": telemetry_enabled,
            "metrics_exporter": effective.get("metrics_exporter", ""),
            "logs_exporter": effective.get("logs_exporter", ""),
            "traces_exporter": effective.get("traces_exporter", ""),
            "enhanced_tracing": bool(effective.get("enhanced_tracing")),
            "detailed_beta_tracing": detailed_tracing,
            "service_name": effective.get("service_name", ""),
            "resource_attributes": effective.get("resource_attributes", ""),
            "headers_configured": bool(effective.get("headers_configured")),
            "endpoint_configured": endpoint_configured,
            "endpoint_placeholder": endpoint_placeholder,
            "collector": collector,
            "collector_reachable": collector_reachable,
            "export_intervals_ms": effective.get("export_intervals_ms", {}),
            "sensitive_data_flags": sensitive_flags,
        },
        "missing_signals": missing,
        "next": next_step,
    }


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "select 1 from sqlite_master where type = 'table' and name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {str(row["name"]) for row in conn.execute(f"pragma table_info({table_name})")}


def _runtime_aggregates() -> dict[str, Any]:
    """Return compact repo-local runtime aggregates for optimization review."""
    db_path = _db_path()
    if not db_path.exists():
        return {"available": False, "reason": "agent_builder_db_missing"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "agent_runs"):
            return {"available": False, "reason": "agent_runs_table_missing"}
        run_columns = _table_columns(conn, "agent_runs")

        by_agent = [
            _row_dict(row)
            for row in conn.execute(
                """
                select agent_name,
                       count(*) as runs,
                       coalesce(sum(num_turns), 0) as turns,
                       coalesce(sum(tokens_input), 0) as input_tokens,
                       coalesce(sum(tokens_output), 0) as output_tokens,
                       coalesce(sum(tokens_cached), 0) as cached_tokens,
                       coalesce(sum(cost_usd), 0.0) as cost_usd,
                       coalesce(sum(duration_ms), 0) as duration_ms
                from agent_runs
                group by agent_name
                order by coalesce(sum(cost_usd), 0.0) desc
                """
            ).fetchall()
        ]
        by_runtime: list[dict[str, Any]] = []
        if {"runtime_sdk", "provider"}.issubset(run_columns):
            by_runtime = [
                _row_dict(row)
                for row in conn.execute(
                    """
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
                    group by coalesce(runtime_sdk, ''), coalesce(provider, '')
                    order by count(*) desc
                    """
                ).fetchall()
            ]
        approval_wait = _approval_wait_summary(conn)
        tool_counts, tool_event_count = _tool_counts(conn)
        optimization_summary = _optimization_summary(conn)
        totals = _sum_agent_rows(by_agent)
        has_runtime_runs = int(totals.get("runs") or 0) > 0
        payload = {
            "available": True,
            "by_agent": by_agent,
            "by_runtime": by_runtime,
            "totals": totals,
            "stop_reasons": _stop_reason_counts(conn),
            "phase_ceremony": _phase_ceremony_summary(by_agent, approval_wait),
            "approval_wait": approval_wait,
            "provider_limits": _provider_limit_summary(conn),
            "optimization_summary": optimization_summary,
            "tool_observability": {
                "agent_run_events_available": _table_exists(conn, "agent_run_events"),
                "agent_run_event_count": tool_event_count,
                "missing_tool_events": _table_exists(conn, "agent_run_events")
                and has_runtime_runs
                and tool_event_count == 0,
                "tool_counts": tool_counts,
                "repeated_retrieval_signal": _repeated_retrieval_signal(tool_counts),
            },
        }
        payload["deterministic_script_candidates"] = runtime_decision_summary(
            _selected_runtime_sdk(),
            aggregates=payload,
            optimization=optimization_summary,
        ).get("deterministic_script_candidates", [])
        payload["optimization_decision"] = optimization_decision_summary(
            _selected_runtime_sdk(),
            aggregates=payload,
            optimization=optimization_summary,
        )
        return payload
    finally:
        conn.close()


def _selected_runtime_sdk() -> str:
    try:
        config = resolve_runtime_config(get_settings())
    except Exception:
        return "claude_agent_sdk"
    sdk = str(config.get("sdk") or "claude")
    return "codex_sdk" if sdk.startswith("codex") else "claude_agent_sdk"


def _selected_runtime_from_coverage(coverage: dict[str, Any]) -> str:
    runtime_sdk = str(coverage.get("runtime_sdk") or "").strip()
    if runtime_sdk.startswith("codex"):
        return "codex_sdk"
    if runtime_sdk in {"claude", "claude_agent_sdk"}:
        return "claude_agent_sdk"
    return _selected_runtime_sdk()


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _optimization_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "agent_runs"):
        return {"available": False, "reason": "agent_runs_missing"}
    columns = _table_columns(conn, "agent_runs")
    observability_select = "observability" if "observability" in columns else "null as observability"
    runtime_select = "runtime_sdk" if "runtime_sdk" in columns else "'' as runtime_sdk"
    rows = conn.execute(
        f"""
        select agent_name,
               {runtime_select},
               tokens_input,
               tokens_output,
               tokens_cached,
               {observability_select}
        from agent_runs
        """
    ).fetchall()
    runs: list[dict[str, Any]] = []
    for row in rows:
        item = _row_dict(row)
        item["observability"] = _maybe_json_dict(item.get("observability"))
        runs.append(item)
    summary = summarize_runs_for_optimization(runs)
    summary["available"] = True
    return summary


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"pragma table_info({table_name})").fetchall()}


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


def _stop_reason_counts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
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
    event_count = int(conn.execute("select count(*) from agent_run_events").fetchone()[0] or 0)
    rows = conn.execute(
        """
        select coalesce(tool_name, event_type, 'unknown') as tool_name, count(*) as calls
        from agent_run_events
        group by coalesce(tool_name, event_type, 'unknown')
        order by calls desc
        limit 20
        """
    ).fetchall()
    return [_row_dict(row) for row in rows], event_count


def _approval_wait_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "approval_gates"):
        return {"available": False, "reason": "approval_gates_table_missing"}
    by_gate = [
        _row_dict(row)
        for row in conn.execute(
            """
            select gate_type,
                   count(*) as total,
                   sum(case when resolved_at is not null then 1 else 0 end) as resolved,
                   coalesce(avg((julianday(resolved_at) - julianday(created_at)) * 86400000), 0) as avg_wait_ms
            from approval_gates
            group by gate_type
            order by gate_type
            """
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
        float(row.get("avg_wait_ms") or 0.0) * int(row.get("resolved") or 0)
        for row in rows
    )
    return weighted / resolved


def _provider_limit_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "tasks"):
        return {"available": False, "reason": "tasks_table_missing"}
    rows = conn.execute(
        "select id, status, depends_on from tasks where status = 'capability_limit'"
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
    parsed = _maybe_json_dict(depends_on)
    provider = parsed.get("provider_limit")
    return provider if isinstance(provider, dict) else {}


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
            "planning_design_exceeds_implementation"
            if ratio is not None and ratio > 1.0
            else ""
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


def _analyze_timeline(session: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    prompts: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for item in items:
        payload = item.get("payload", {})
        if not isinstance(payload, dict):
            payload = {"content": str(payload)}
        event_type = str(item.get("event_type", ""))
        if event_type == "user_message":
            if current is not None:
                current["context_efficiency"] = _context_signal(current)
                prompts.append(current)
            current = {
                "index": len(prompts) + 1,
                "user_prompt": _text_preview(payload.get("content"), limit=260),
                "started_at": item.get("created_at"),
                "tools": [],
                "assistant_response": "",
                "telemetry": {},
            }
            continue
        if current is None:
            continue
        if event_type == "assistant_message":
            current["assistant_response"] = _text_preview(payload.get("content"), limit=360)
            continue
        if event_type == "run_status":
            diagnostic = summarize_chat_event(event_type, payload)
            current["telemetry"] = {
                key: payload.get(key)
                for key in (
                    "running",
                    "current_turn",
                    "max_turns",
                    "tokens_used",
                    "cost_usd",
                    "duration_ms",
                    "stop_reason",
                    "sdk_session_id",
                    "error",
                    "observability",
                    "dispatch",
                )
                if payload.get(key) not in ("", None)
            }
            if "observability" in current["telemetry"]:
                snapshot = current["telemetry"].pop("observability")
                if isinstance(snapshot, dict):
                    current["observability"] = snapshot
            if diagnostic.get("outcome") == "error":
                current.setdefault("risks", []).append("run_error")
            continue
        diagnostic = summarize_chat_event(event_type, payload)
        tool = {
            "event_type": event_type,
            "tool_name": diagnostic.get("tool_name", "") or payload.get("tool_name", ""),
            "outcome": diagnostic.get("outcome", ""),
            "summary": diagnostic.get("summary", ""),
        }
        input_focus = diagnostic.get("input_focus", "")
        if input_focus:
            tool["input_focus"] = input_focus
        if diagnostic.get("error_message"):
            tool["error_message"] = diagnostic.get("error_message")
        if tool["tool_name"] == "mcp__builder__task_dispatch":
            dispatch_payload = _extract_text_json(str(payload.get("content", "")))
            dispatch = {
                key: dispatch_payload.get(key)
                for key in ("task_id", "status", "current_status")
                if dispatch_payload.get(key) not in ("", None)
            }
            if dispatch:
                tool["dispatch"] = dispatch
        current["tools"].append(tool)

    if current is not None:
        current["context_efficiency"] = _context_signal(current)
        prompts.append(current)

    total_tokens = sum(
        int(prompt.get("telemetry", {}).get("tokens_used") or 0)
        for prompt in prompts
    )
    total_cost = sum(
        float(prompt.get("telemetry", {}).get("cost_usd") or 0.0)
        for prompt in prompts
    )
    review_count = sum(
        1 for prompt in prompts if prompt.get("context_efficiency", {}).get("grade") == "review"
    )
    coverage = _observability_coverage(prompts)
    runtime_aggregates = _runtime_aggregates()
    dashboard_observability = dashboard_observability_summary(_db_path())
    telemetry_health = dashboard_observability.get("observability_coverage", {}).get(
        "telemetry_health",
        {},
    )
    deterministic_recommendations = dashboard_observability.get("deterministic_recommendations", [])
    optimization = runtime_aggregates.get("optimization_summary", {})
    selected_runtime = _selected_runtime_from_coverage(coverage)
    decisions = runtime_decision_summary(
        selected_runtime,
        aggregates=runtime_aggregates,
        optimization=optimization,
    )
    optimization_decision = optimization_decision_summary(
        selected_runtime,
        aggregates=runtime_aggregates,
        optimization=optimization,
    )
    return {
        "ok": True,
        "status": "ok",
        "exit_code": EXIT_SUCCESS,
        "session_id": session.get("id", ""),
        "sdk_session_id": session.get("sdk_session_id"),
        "prompt_count": len(prompts),
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "review_prompt_count": review_count,
        "observability_coverage": coverage,
        "selected_runtime": selected_runtime,
        "runtime_native_telemetry_health": {
            key: telemetry_health.get(key)
            for key in ("claude_native", "codex_native")
            if key in telemetry_health
        },
        "builder_product_telemetry_health": telemetry_health.get("builder_product", {}),
        "telemetry_health": telemetry_health,
        "raw_token_total": int(optimization.get("raw_token_total") or total_tokens),
        "noncached_plus_output_tokens": int(
            optimization.get("noncached_plus_output_tokens") or 0
        ),
        "cache_ratio": float(optimization.get("cache_ratio") or 0.0),
        "phase_ceremony_tokens": int(optimization.get("phase_ceremony_tokens") or 0),
        "avoidable_token_estimate": int(optimization.get("avoidable_token_estimate") or 0),
        "top_cost_drivers": optimization.get("top_cost_drivers", []),
        "recommended_next_change": str(optimization.get("recommended_next_change") or ""),
        "optimization_decision": optimization_decision,
        "runtime_decision_summary": decisions,
        "phase_runtime_decisions": decisions.get("phase_decisions", []),
        "deterministic_script_candidates": decisions.get("deterministic_script_candidates", []),
        "deterministic_recommendations": deterministic_recommendations,
        "runtime_aggregates": runtime_aggregates,
        "raw_evidence": {
            "available": bool(items),
            "event_count": len(items),
            "command": "builder logs --session <id> --raw --json",
            "contains": ["chat events", "tool results", "run status", "raw payloads"],
            "note": (
                "chat timeline events are available for this builder chat session"
                if items
                else "no chat timeline events resolved for this session; use builder metrics show --json --full for persisted AgentRun observability"
            ),
        },
        "prompts": prompts,
        "schema_version": "1",
        "next": "builder logs --session <id> --compact --json",
    }


def _emit_ndjson(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        sys.stdout.write(json.dumps(row, ensure_ascii=True) + "\n")
    sys.stdout.flush()


@app.command("analyze")
def analyze(
    session_id: str | None = typer.Option(None, "--session", help="Chat session ID or unique prefix."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Analyze one chat session prompt-by-prompt with compact telemetry."""
    try:
        session, items = _load_session_timeline(session_id)
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        emit_error(
            str(exc),
            code="logs_unavailable",
            hint="Run `builder agent sessions --json` to resolve a valid session id.",
            use_json=json_output,
        )
        raise typer.Exit(EXIT_FAILURE) from exc

    payload = _analyze_timeline(session, items)
    if not payload.get("session_id"):
        payload["next"] = "builder agent sessions --json"

    def fmt(item: dict[str, Any]) -> str:
        lines = [
            f"session_id: {item.get('session_id', '') or '(none)'}",
            f"sdk_session_id: {item.get('sdk_session_id', '') or '(none)'}",
            f"prompts: {item.get('prompt_count', 0)}",
            f"tokens: {item.get('total_tokens', 0)}",
            f"cost_usd: {item.get('total_cost_usd', 0)}",
        ]
        aggregates = item.get("runtime_aggregates", {})
        if isinstance(aggregates, dict) and aggregates.get("available"):
            totals = aggregates.get("totals", {})
            ceremony = aggregates.get("phase_ceremony", {})
            lines.extend(
                [
                    f"runtime_runs: {totals.get('runs', 0)}",
                    f"runtime_turns: {totals.get('turns', 0)}",
                    f"runtime_cost_usd: {totals.get('cost_usd', 0)}",
                    f"ceremony_flag: {ceremony.get('flag', '') or '(none)'}",
                ]
            )
        coverage = item.get("observability_coverage", {})
        if isinstance(coverage, dict):
            otel = coverage.get("otel", {}) if isinstance(coverage.get("otel"), dict) else {}
            collector = otel.get("collector", {}) if isinstance(otel.get("collector"), dict) else {}
            if collector:
                lines.append(
                    "otel_collector: "
                    f"status={collector.get('status', '')}; "
                    f"reachable={collector.get('reachable')}"
                )
            if coverage.get("missing_signals"):
                lines.append(f"missing_signals: {', '.join(coverage.get('missing_signals', []))}")
            if coverage.get("next"):
                lines.append(f"observability_next: {coverage.get('next')}")
        for prompt in item.get("prompts", []):
            telemetry = prompt.get("telemetry", {})
            context = prompt.get("context_efficiency", {})
            lines.append("")
            lines.append(f"[{prompt.get('index')}] {prompt.get('user_prompt', '')}")
            lines.append(
                "telemetry: "
                + ", ".join(
                    f"{key}={telemetry.get(key)}"
                    for key in ("tokens_used", "cost_usd", "duration_ms", "stop_reason")
                    if telemetry.get(key) not in ("", None)
                )
            )
            lines.append(
                f"context: {context.get('grade', '')}"
                + (
                    f" ({', '.join(context.get('signals', []))})"
                    if context.get("signals")
                    else ""
                )
            )
            tool_names = [tool.get("tool_name", "") or tool.get("event_type", "") for tool in prompt.get("tools", [])]
            lines.append(f"tools: {', '.join(tool_names) if tool_names else '(none)'}")
            if prompt.get("assistant_response"):
                lines.append(f"response: {prompt.get('assistant_response')}")
        lines.append("")
        lines.append(f"Next: {item.get('next', '')}")
        return "\n".join(lines)

    render(payload, fmt, use_json=json_output)
    raise typer.Exit(EXIT_SUCCESS)


@app.callback(invoke_without_command=True)
def logs(
    ctx: typer.Context,
    session_id: str | None = typer.Option(None, "--session", help="Chat session ID."),
    tool: str | None = typer.Option(None, "--tool", help="Only show one tool name."),
    event_type: str | None = typer.Option(
        None,
        "--type",
        help="One event type such as tool_result, tool_error, or run_error.",
    ),
    error: bool = typer.Option(False, "--error", help="Only show error events."),
    info: bool = typer.Option(
        False,
        "--info",
        help="Only show non-error diagnostics such as tool results and run status.",
    ),
    follow: bool | None = typer.Option(
        None,
        "--follow/--no-follow",
        help="Stream new matching log events. Defaults to on for '--error' in TTY mode.",
    ),
    raw: bool = typer.Option(False, "--raw", help="Emit exact stored event rows without diagnostic compaction."),
    compact: bool = typer.Option(False, "--compact", help="Trim payloads to the minimum useful fields."),
    ndjson: bool = typer.Option(
        False,
        "--ndjson",
        help="Emit one JSON object per line. Use this for follow/watch style machine streams.",
    ),
    limit: int = typer.Option(5, min=1, max=200, help="Max log entries."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Inspect embedded chat logs for the latest or selected session."""
    if ctx.invoked_subcommand is not None:
        return
    if ndjson and json:
        emit_error(
            "Choose either --json or --ndjson, not both.",
            code="invalid_usage",
            hint="Use --ndjson for line-delimited streams, or --json for one bounded envelope.",
            use_json=True,
        )
        raise typer.Exit(EXIT_INVALID_USAGE)
    if raw and compact:
        emit_error(
            "Choose either --raw or --compact, not both.",
            code="invalid_usage",
            hint="Use --raw for exact stored event rows, or --compact for the summarized diagnostic lane.",
            use_json=True,
        )
        raise typer.Exit(EXIT_INVALID_USAGE)
    if sum(1 for flag in (error, info, bool(event_type)) if flag) > 1:
        emit_error(
            "choose only one log selector",
            code="invalid_input",
            hint="Use one of '--error', '--info', or '--type <event_type>' to narrow the log stream.",
            use_json=json or ndjson,
        )
        raise typer.Exit(EXIT_INVALID_USAGE)
    selected_type = event_type
    should_follow = bool(follow) if follow is not None else bool(error and not (json or ndjson) and sys.stdout.isatty())

    try:
        items = _load_rows(
            session_id=session_id,
            tool_name=tool,
            event_type=selected_type,
            errors_only=error,
            info_only=info,
            limit=limit,
        )
    except FileNotFoundError as exc:
        emit_error(
            str(exc),
            code="not_found",
            hint="Run 'builder start' or initialize the repo so .agent-builder/agent_builder.db exists.",
            use_json=json or ndjson,
        )
        raise typer.Exit(EXIT_FAILURE) from exc
    except RuntimeError as exc:
        emit_error(
            str(exc),
            code="project_not_initialized",
            hint="Run 'builder init' in the repo root first.",
            use_json=json or ndjson,
        )
        raise typer.Exit(EXIT_FAILURE) from exc

    compact_mode = compact or ((json or ndjson) and (error or info))
    if raw:
        rendered_items = _raw_items(items)
    elif compact_mode:
        rendered_items = _compact_items(items)
    else:
        rendered_items = items

    def fmt(rows: list[dict[str, Any]]) -> str:
        headers = ["TIME", "TYPE", "TOOL", "SUMMARY", "FOCUS"]
        body: list[list[str]] = []
        for item in rows:
            payload = item.get("payload", {})
            if not isinstance(payload, dict):
                payload = {"content": str(payload)}
            diagnostic = payload.get("diagnostic")
            if not isinstance(diagnostic, dict):
                diagnostic = summarize_chat_event(str(item.get("event_type", "")), payload)
            body.append(
                [
                    str(item.get("created_at", ""))[:19],
                    str(item.get("event_type", "")),
                    str(diagnostic.get("tool_name", "") or payload.get("tool_name", "") or "-"),
                    truncate(str(diagnostic.get("summary", "") or payload.get("content", "") or ""), 120).replace("\n", " "),
                    truncate(str(diagnostic.get("input_focus", "") or "-"), 80).replace("\n", " "),
                ]
            )
        return table(headers, body, max_col_width=60)

    payload = (
        compact_results_payload(
            "logs",
            rendered_items,
            next_step="builder logs --session <id> --raw --json" if raw else "builder logs --session <id> --compact --json",
        )
        if json
        else rendered_items
    )
    if ndjson:
        _emit_ndjson(rendered_items)
    else:
        if raw and not json:
            render(rendered_items, lambda rows: json_lib.dumps(rows, indent=2), use_json=True)
        else:
            render(payload, fmt, use_json=json)
    if should_follow:
        seen_ids = {str(item.get("id", "")) for item in items}
        try:
            while True:
                time.sleep(1.0)
                fresh = _load_rows(
                    session_id=session_id,
                    tool_name=tool,
                    event_type=selected_type,
                    errors_only=error,
                    info_only=info,
                    limit=limit,
                )
                new_items = [item for item in reversed(fresh) if str(item.get("id", "")) not in seen_ids]
                for item in new_items:
                    if raw:
                        display_item = _raw_items([item])[0]
                    elif compact_mode:
                        display_item = _compact_items([item])[0]
                    else:
                        display_item = item
                    if ndjson:
                        _emit_ndjson([display_item])
                    else:
                        if raw:
                            print(json_lib.dumps(display_item))
                        else:
                            print(_render_line(display_item))
                    seen_ids.add(str(item.get("id", "")))
        except KeyboardInterrupt:
            pass
    raise typer.Exit(EXIT_SUCCESS)
