"""Runtime aggregate helpers extracted from observability summary."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from autonomous_agent_builder.observability.summary_db import (
    _column_or_default,
    _maybe_json_dict,
    _parse_datetime,
    _provider_payload,
    _row_dict,
    _table_columns,
    _table_exists,
)
from autonomous_agent_builder.observability.summary_recommendation_lifecycle import (
    _empty_recommendation_lifecycle,
)
from autonomous_agent_builder.services.provider_limits import (
    is_provider_limit_text,
    parse_reset_hint,
)


def _empty_runtime_aggregates(reason: str) -> dict[str, Any]:
    totals = {
        "runs": 0,
        "turns": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "cost_usd": 0.0,
        "estimated_cost_usd": 0.0,
        "estimated_codex_credits": None,
        "duration_ms": 0,
    }
    return {
        "available": False,
        "reason": reason,
        "by_agent": [],
        "by_runtime": [],
        "by_model_effort": [],
        "totals": totals,
        "stop_reasons": [],
        "phase_ceremony": {
            "planning_design_cost_usd": 0.0,
            "implementation_cost_usd": 0.0,
            "verification_cost_usd": 0.0,
            "integration_cost_usd": 0.0,
            "planning_design_to_implementation_ratio": None,
            "approval_wait_ms": 0.0,
            "flag": "",
        },
        "approval_wait": {
            "available": False,
            "reason": reason,
            "by_gate_type": [],
            "active_unresolved": 0,
        },
        "provider_limits": {"available": False, "reason": reason, "count": 0},
        "error_summary": {"available": False, "reason": reason, "count": 0, "recent": []},
        "runtime_recovery": {"resume_retry_count": 0, "latest": {}},
        "context_budget": {
            "available": False,
            "event_count": 0,
            "total_estimated_tokens": 0,
            "by_lane": [],
            "by_stage": [],
            "signal_counts": [],
            "top_components": [],
            "latest": {},
        },
        "optimization_summary": {"available": False, "reason": reason},
        "tool_observability": {
            "agent_run_events_available": False,
            "agent_run_event_count": 0,
            "missing_tool_events": True,
            "tool_counts": [],
            "repeated_retrieval_signal": {"detected": False, "tools": []},
        },
        "deterministic_script_candidates": [],
        "optimization_decision": {},
        "recommendation_lifecycle": _empty_recommendation_lifecycle(),
    }


def _recommendations(
    runtime: dict[str, Any],
    coverage: dict[str, Any],
    aggregates: dict[str, Any],
    optimization: dict[str, Any],
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    missing = set(coverage.get("missing_signals") or [])
    if runtime.get("selected_runtime_sdk") == "codex_sdk":
        if "codex_token_usage" in missing:
            recommendations.append(
                _recommendation(
                    "codex_token_usage_missing",
                    "high",
                    "Codex token usage missing",
                    "Check app-server tokenUsage events before cost optimization.",
                )
            )
        if "model_effort_fields" in missing:
            recommendations.append(
                _recommendation(
                    "model_effort_missing",
                    "medium",
                    "Model or effort missing",
                    "Persist model and effort on every Codex run.",
                )
            )
        if "tool_events" in missing:
            recommendations.append(
                _recommendation(
                    "tool_events_missing",
                    "medium",
                    "Tool events are missing",
                    "Persist command/tool events before tuning routing.",
                )
            )
        if "chunk_pressure" in missing:
            recommendations.append(
                _recommendation(
                    "chunk_pressure",
                    "medium",
                    "Chunk pressure detected",
                    "Trim large command output before reinjecting context.",
                )
            )
        top_driver = (optimization.get("top_cost_drivers") or [{}])[0]
        if top_driver and top_driver.get("agent_name") == "code-gen":
            recommendations.append(
                _recommendation(
                    "code_gen_raw_tokens",
                    "medium",
                    "Code-gen dominates raw tokens",
                    "Tighten implementation briefs and file hints before lowering model effort.",
                )
            )
        for flag in optimization.get("avoidable_cost_flags") or []:
            name = str(flag.get("flag") if isinstance(flag, dict) else flag)
            if name in {"pr_lane_without_explicit_pr_target", "prompt_over_phase_budget"}:
                recommendations.append(
                    _recommendation(
                        name,
                        "medium",
                        name.replace("_", " "),
                        "Remove avoidable model ceremony from low-risk local sprints.",
                    )
                )
    else:
        if (
            "otel_metrics_exporter" in missing
            or "otel_logs_exporter" in missing
            or "otel_traces_exporter" in missing
        ):
            recommendations.append(
                _recommendation(
                    "claude_otel_missing",
                    "high",
                    "Claude OTEL exporters missing",
                    "Configure Claude Agent SDK OTEL before relying on external telemetry.",
                )
            )
        if "otel_otlp_endpoint" in missing:
            recommendations.append(
                _recommendation(
                    "claude_otlp_placeholder",
                    "medium",
                    "Collector endpoint missing",
                    "Use a real OTLP collector endpoint.",
                )
            )
        if coverage.get("otel", {}).get("sensitive_data_flags"):
            recommendations.append(
                _recommendation(
                    "sensitive_telemetry_flags",
                    "medium",
                    "Sensitive telemetry flags enabled",
                    "Review content logging before exporting telemetry.",
                )
            )
        if "tool_events" in missing:
            recommendations.append(
                _recommendation(
                    "tool_events_missing",
                    "medium",
                    "Tool events are missing",
                    "Persist tool events before tuning model routing.",
                )
            )
    approval_wait = aggregates.get("approval_wait", {})
    unresolved = int(approval_wait.get("active_unresolved") or 0)
    if unresolved > 0:
        recommendations.append(
            _recommendation(
                "approval_stalled",
                "medium",
                "Approval stalled",
                "Surface blocked approval action before dispatching more work.",
            )
        )
    if int(aggregates.get("provider_limits", {}).get("count") or 0) > 0:
        recommendations.append(
            _recommendation(
                "provider_limits_present",
                "medium",
                "Provider limits present",
                "Resume ready blocked tasks before queueing new work.",
            )
        )
    open_rule_codes = {
        str(item.get("code") or "")
        for item in coverage.get("deterministic_recommendations", [])
        if isinstance(item, dict)
    }
    open_rule_codes.discard("deterministic_baseline_ready")
    if not recommendations and not open_rule_codes:
        recommendations.append(
            _recommendation(
                "baseline_ready",
                "info",
                "Observability baseline is usable",
                "Continue collecting run evidence before changing routing policy.",
            )
        )
    return recommendations


def _recommendation(code: str, severity: str, title: str, detail: str) -> dict[str, Any]:
    return {"code": code, "severity": severity, "title": title, "detail": detail}


def _phase_ceremony_summary(
    by_agent: list[dict[str, Any]], approval_wait: dict[str, Any]
) -> dict[str, Any]:
    by_name = {str(row.get("agent_name")): row for row in by_agent}
    planning_design = _agent_cost(by_name, "planner") + _agent_cost(by_name, "designer")
    implementation = _agent_cost(by_name, "code-gen")
    ratio = planning_design / implementation if implementation else None
    return {
        "planning_design_cost_usd": planning_design,
        "implementation_cost_usd": implementation,
        "verification_cost_usd": _agent_cost(by_name, "build-verifier"),
        "integration_cost_usd": _agent_cost(by_name, "pr-creator"),
        "planning_design_to_implementation_ratio": ratio,
        "approval_wait_ms": approval_wait.get("avg_wait_ms", 0.0),
        "flag": "planning_design_exceeds_implementation" if ratio and ratio > 1.0 else "",
    }


def _agent_cost(by_name: dict[str, dict[str, Any]], agent_name: str) -> float:
    return float(by_name.get(agent_name, {}).get("estimated_cost_usd") or 0.0)


def _approval_wait_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "approval_gates"):
        return {"available": False, "reason": "approval_gates_missing", "by_gate_type": []}
    task_join = ""
    task_status_select = "null as task_status"
    if _table_exists(conn, "tasks"):
        task_join = "left join tasks t on t.id = ag.task_id"
        task_status_select = "t.status as task_status"
    rows = [
        _row_dict(row)
        for row in conn.execute(
            f"""
            select ag.gate_type, ag.status as gate_status, ag.created_at, ag.resolved_at,
                   {task_status_select}
            from approval_gates ag
            {task_join}
            """
        ).fetchall()
    ]
    buckets: dict[str, dict[str, Any]] = {}
    waits: list[float] = []
    active_unresolved = 0
    terminal_statuses = {"done", "failed"}
    for row in rows:
        gate_type = str(row.get("gate_type") or "unknown")
        bucket = buckets.setdefault(
            gate_type,
            {
                "gate_type": gate_type,
                "total": 0,
                "resolved": 0,
                "active_unresolved": 0,
                "avg_wait_ms": 0.0,
                "_waits": [],
            },
        )
        bucket["total"] += 1
        created = _parse_datetime(row.get("created_at"))
        resolved = _parse_datetime(row.get("resolved_at"))
        gate_status = str(row.get("gate_status") or "pending")
        task_status = str(row.get("task_status") or "")
        is_resolved = bool(resolved) or gate_status in {"approve", "approved", "rejected"}
        if not is_resolved and task_status not in terminal_statuses:
            bucket["active_unresolved"] += 1
            active_unresolved += 1
        if is_resolved:
            bucket["resolved"] += 1
        if created and resolved:
            wait = max((resolved - created).total_seconds() * 1000, 0)
            bucket["_waits"].append(wait)
            waits.append(wait)
    output = []
    for bucket in buckets.values():
        values = bucket.pop("_waits")
        bucket["avg_wait_ms"] = sum(values) / len(values) if values else 0.0
        output.append(bucket)
    return {
        "available": True,
        "by_gate_type": output,
        "total": len(rows),
        "resolved": sum(int(row.get("resolved") or 0) for row in output),
        "active_unresolved": active_unresolved,
        "avg_wait_ms": sum(waits) / len(waits) if waits else 0.0,
    }


def _provider_limit_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = []
    if _table_exists(conn, "tasks"):
        for row in conn.execute("select status, depends_on from tasks").fetchall():
            payload = _provider_payload(row["depends_on"])
            if payload or str(row["status"]) == "capability_limit":
                rows.append(payload)
    if _table_exists(conn, "chat_events"):
        columns = _table_columns(conn, "chat_events")
        if "payload_json" in columns:
            for row in conn.execute(
                "select payload_json from chat_events where event_type = 'run_status'"
            ).fetchall():
                payload = (
                    json.loads(row["payload_json"])
                    if isinstance(row["payload_json"], str)
                    else row["payload_json"]
                )
                payload = payload or {}
                if not isinstance(payload, dict):
                    continue
                provider_limit = payload.get("provider_limit")
                if isinstance(provider_limit, dict) and provider_limit:
                    rows.append(provider_limit)
        if "content" in columns:
            for row in conn.execute(
                "select content from chat_events where status in ('failed', 'error', 'blocked')"
            ).fetchall():
                content = str(row["content"] or "")
                if is_provider_limit_text(content):
                    reset_at, reset_hint = parse_reset_hint(content)
                    rows.append(
                        {
                            "reset_at": reset_at.isoformat() if reset_at else None,
                            "reset_hint": reset_hint,
                        }
                    )
    now = datetime.now(UTC)
    ready = 0
    waiting = 0
    reset_times: list[str] = []
    for payload in rows:
        reset_at = _parse_datetime(payload.get("reset_at")) if isinstance(payload, dict) else None
        if reset_at:
            reset_times.append(reset_at.isoformat())
            if reset_at <= now:
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


_ERROR_RETENTION_DAYS = 7


def _error_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "chat_events"):
        return {
            "available": False,
            "reason": "chat_events_missing",
            "count": 0,
            "total_count": 0,
            "active_count": 0,
            "resolved_count": 0,
            "recent_count": 0,
            "active_recent_count": 0,
            "recent": [],
            "active_recent": [],
        }
    columns = _table_columns(conn, "chat_events")
    select = [
        _column_or_default(columns, "id", "''", "id"),
        _column_or_default(columns, "session_id", "''", "session_id"),
        _column_or_default(columns, "event_type", "''", "event_type"),
        _column_or_default(columns, "status", "''", "status"),
        _column_or_default(columns, "content", "''", "content"),
        _column_or_default(columns, "payload_json", "''", "payload_json"),
        _column_or_default(columns, "created_at", "''", "created_at"),
    ]
    error_types_where = """
            event_type in ('tool_error', 'run_error')
               or (event_type = 'voice_tool_output' and status = 'failed')
            """
    total_count = int(
        conn.execute(f"select count(*) from chat_events where {error_types_where}").fetchone()[0]
        or 0
    )
    # Retention window: only rows within the last N days contribute to active_count
    # and are surfaced in recommendations. Rows outside this window are aged out.
    has_created_at = "created_at" in columns
    if has_created_at:
        retention_cutoff = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        # SQLite datetime arithmetic: subtract retention days
        window_where = (
            f"({error_types_where})"
            f" and (created_at is null or created_at = ''"
            f" or created_at >= datetime('{retention_cutoff}', '-{_ERROR_RETENTION_DAYS} days'))"
        )
    else:
        window_where = error_types_where
    rows = [
        _row_dict(row)
        for row in conn.execute(
            f"""
            select {", ".join(select)}
            from chat_events
            where {window_where}
            order by created_at desc
            limit 250
            """
        ).fetchall()
    ]
    recent: list[dict[str, Any]] = []
    active_recent: list[dict[str, Any]] = []
    resolved_count = 0
    within_window_count = len(rows)
    for row in rows:
        payload = _maybe_json_dict(row.get("payload_json"))
        message = (
            str(
                payload.get("error_message") or payload.get("error") or payload.get("summary") or ""
            )
            or str(payload.get("content") or "")
            or str(row.get("content") or "")
        )
        item = {
            "id": str(row.get("id") or ""),
            "event_type": str(row.get("event_type") or ""),
            "status": str(row.get("status") or ""),
            "summary": message[:240],
            "created_at": str(row.get("created_at") or ""),
        }
        if _error_row_has_later_success(conn, row):
            resolved_count += 1
            item["resolved"] = "true"
        else:
            active_recent.append(item)
        recent.append(item)
    # active_count is bounded to within-window errors only so stale errors age out
    active_count = max(within_window_count - resolved_count, 0)
    return {
        "available": True,
        "count": total_count,
        "total_count": total_count,
        "active_count": active_count,
        "resolved_count": resolved_count,
        "recent_count": min(len(recent), 10),
        "active_recent_count": min(len(active_recent), 10),
        "recent": recent[:5],
        "active_recent": active_recent[:5],
    }


def _error_row_has_later_success(conn: sqlite3.Connection, row: dict[str, Any]) -> bool:
    columns = _table_columns(conn, "chat_events")
    if "created_at" not in columns or "session_id" not in columns:
        return False
    created_at = str(row.get("created_at") or "")
    if not created_at:
        return False

    event_type = str(row.get("event_type") or "")
    payload = _maybe_json_dict(row.get("payload_json"))
    if event_type == "voice_tool_output":
        tool_name = str(payload.get("tool_name") or "").strip()
        return bool(tool_name and _has_later_successful_voice_tool(conn, tool_name, created_at))

    session_id = str(row.get("session_id") or "").strip()
    prompt = _session_user_prompt(conn, session_id)
    failed_runtime = _session_terminal_runtime(conn, session_id, created_at)
    return bool(
        prompt
        and _has_later_successful_prompt_session(
            conn,
            prompt,
            created_at,
            session_id,
            failed_runtime,
        )
    )


def _session_user_prompt(conn: sqlite3.Connection, session_id: str) -> str:
    if not session_id:
        return ""
    row = conn.execute(
        """
        select payload_json
        from chat_events
        where session_id = ? and event_type = 'user_message'
        order by created_at asc
        limit 1
        """,
        (session_id,),
    ).fetchone()
    payload = _maybe_json_dict(row[0] if row else "")
    return str(payload.get("content") or "").strip()


def _has_later_successful_prompt_session(
    conn: sqlite3.Connection,
    prompt: str,
    created_at: str,
    failed_session_id: str,
    failed_runtime: str,
) -> bool:
    rows = conn.execute(
        """
        select session_id, payload_json
        from chat_events
        where event_type = 'user_message' and created_at > ?
        order by created_at asc
        """,
        (created_at,),
    ).fetchall()
    for raw in rows:
        row = _row_dict(raw)
        session_id = str(row.get("session_id") or "")
        if not session_id or session_id == failed_session_id:
            continue
        payload = _maybe_json_dict(row.get("payload_json"))
        if str(payload.get("content") or "").strip() != prompt:
            continue
        if _session_has_later_successful_terminal_status(
            conn, session_id, created_at, failed_runtime
        ):
            return True
    return False


def _session_terminal_runtime(conn: sqlite3.Connection, session_id: str, created_at: str) -> str:
    rows = conn.execute(
        """
        select payload_json
        from chat_events
        where session_id = ?
          and event_type = 'run_status'
          and status = 'completed'
          and created_at >= ?
        order by created_at desc
        limit 1
        """,
        (session_id, created_at),
    ).fetchall()
    for raw in rows:
        payload = _maybe_json_dict(
            raw[0] if not isinstance(raw, sqlite3.Row) else raw["payload_json"]
        )
        runtime = str(payload.get("runtime_sdk") or "").strip()
        if runtime:
            return runtime
    return ""


def _session_has_later_successful_terminal_status(
    conn: sqlite3.Connection,
    session_id: str,
    created_at: str,
    required_runtime: str = "",
) -> bool:
    rows = conn.execute(
        """
        select payload_json
        from chat_events
        where session_id = ?
          and event_type = 'run_status'
          and status = 'completed'
          and created_at > ?
        order by created_at desc
        """,
        (session_id, created_at),
    ).fetchall()
    for raw in rows:
        payload = _maybe_json_dict(
            raw[0] if not isinstance(raw, sqlite3.Row) else raw["payload_json"]
        )
        runtime = str(payload.get("runtime_sdk") or "").strip()
        if required_runtime and runtime != required_runtime:
            continue
        if not payload.get("error") and str(payload.get("stop_reason") or "") != "runtime_error":
            return True
    return False


def _has_later_successful_voice_tool(
    conn: sqlite3.Connection, tool_name: str, created_at: str
) -> bool:
    rows = conn.execute(
        """
        select payload_json
        from chat_events
        where event_type = 'voice_tool_output'
          and status = 'completed'
          and created_at > ?
        order by created_at desc
        """,
        (created_at,),
    ).fetchall()
    for raw in rows:
        payload = _maybe_json_dict(
            raw[0] if not isinstance(raw, sqlite3.Row) else raw["payload_json"]
        )
        if (
            str(payload.get("tool_name") or "").strip() == tool_name
            and payload.get("ok") is not False
        ):
            return True
    return False
