"""Chat and tool log inspection for the repo-local builder runtime."""

from __future__ import annotations

import json
import json as json_lib
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

import typer

from autonomous_agent_builder.cli.client import EXIT_FAILURE, EXIT_INVALID_USAGE, EXIT_SUCCESS
from autonomous_agent_builder.cli.commands.logs_db_utils import (
    maybe_json_dict as _maybe_json_dict,
    row_dict as _row_dict,
    table_columns as _table_columns,
    table_exists as _table_exists,
)
from autonomous_agent_builder.cli.commands.logs_runtime_aggregates import (
    runtime_aggregates as _compute_runtime_aggregates,
    selected_runtime_sdk as _selected_runtime_sdk,
)
from autonomous_agent_builder.cli.output import emit_error, render, table, truncate
from autonomous_agent_builder.cli.project_discovery import (
    ProjectNotFoundError,
    find_agent_builder_dir,
)
from autonomous_agent_builder.cli.retrieval import compact_results_payload
from autonomous_agent_builder.logs.diagnostics import summarize_chat_event
from autonomous_agent_builder.observability.runtime_optimization import (
    optimization_decision_summary,
    runtime_decision_summary,
)
from autonomous_agent_builder.observability.summary import dashboard_observability_summary
from autonomous_agent_builder.observability.timeline_analysis import build_timeline_prompts

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

_VOICE_TYPES = (
    "voice_tool_call",
    "voice_tool_output",
    "voice_usage",
    "voice_digest",
    "voice_wait",
)
_INFO_TYPES = ("tool_result", "run_status", "specialist_status", "context_budget", *_VOICE_TYPES)
_DEFAULT_TYPES = (
    "tool_result",
    "tool_error",
    "run_error",
    "run_status",
    "specialist_status",
    "context_budget",
    *_VOICE_TYPES,
)
_PROMPT_EVENT_TYPES = ("user_message", "assistant_message", *_DEFAULT_TYPES)


def _db_path() -> Path:
    try:
        return find_agent_builder_dir(Path.cwd()).resolve() / "agent_builder.db"
    except ProjectNotFoundError as exc:
        raise RuntimeError(exc.hint or "Initialize this repo with 'builder init' first.") from exc


def _resolve_session_id(conn: sqlite3.Connection, session_id: str | None) -> str:
    if not _table_exists(conn, "chat_sessions"):
        return str(session_id or "")
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
        project_wide_errors = errors_only and not session_id
        resolved_session = "" if project_wide_errors else _resolve_session_id(conn, session_id)

        if not resolved_session and not project_wide_errors:
            return []

        clauses: list[str] = []
        params: list[Any] = []
        if resolved_session:
            clauses.append("session_id = ?")
            params.append(resolved_session)

        if errors_only:
            clauses.append(
                "("
                "event_type in ('tool_error', 'run_error')"
                " or (event_type = 'voice_tool_output' and "
                "(status = 'failed' or json_extract(payload_json, '$.ok') = 0))"
                ")"
            )
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
            f"where {' and '.join(clauses) if clauses else '1 = 1'} "
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
    if not _table_exists(conn, "chat_sessions"):
        run = _agent_run_metadata(conn, resolved_session)
        if run:
            return {
                "id": str(run.get("id") or resolved_session),
                "target_kind": "agent_run",
                "agent_run": run,
            }
        return {"id": resolved_session}
    row = conn.execute(
        "select * from chat_sessions where id = ?",
        (resolved_session,),
    ).fetchone()
    if row is None:
        run = _agent_run_metadata(conn, resolved_session)
        if run:
            return {
                "id": str(run.get("id") or resolved_session),
                "target_kind": "agent_run",
                "agent_run": run,
            }
        return {"id": resolved_session}
    metadata = {key: row[key] for key in row.keys()}
    run = _agent_run_metadata(conn, resolved_session)
    if run:
        metadata["agent_run"] = run
    return metadata


def _agent_run_metadata(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    if not run_id or not _table_exists(conn, "agent_runs"):
        return {}
    columns = _table_columns(conn, "agent_runs")
    select_columns = [
        name
        for name in (
            "id",
            "task_id",
            "agent_name",
            "runtime_sdk",
            "provider",
            "model",
            "effort",
            "cost_usd",
            "estimated_cost_usd",
            "estimated_codex_credits",
            "tokens_input",
            "tokens_output",
            "tokens_cached",
            "num_turns",
            "duration_ms",
            "stop_reason",
            "status",
            "error",
            "observability",
            "started_at",
            "completed_at",
        )
        if name in columns
    ]
    if not select_columns:
        return {}
    query = f"select {', '.join(select_columns)} from agent_runs where id = ?"
    row = conn.execute(query, (run_id,)).fetchone()
    if row is None:
        order_column = "started_at" if "started_at" in columns else "id"
        matches = conn.execute(
            f"select {', '.join(select_columns)} from agent_runs where id like ? order by {order_column} desc limit 2",
            (f"{run_id}%",),
        ).fetchall()
        if len(matches) == 1:
            row = matches[0]
        elif len(matches) > 1:
            raise ValueError(f"Run prefix '{run_id}' is ambiguous.")
    if row is None:
        return {}
    item = _row_dict(row)
    item["observability"] = _maybe_json_dict(item.get("observability"))
    return item


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
        if not _table_exists(conn, "chat_events"):
            return session, []

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
    summary = truncate(
        str(diagnostic.get("summary", "") or payload.get("content", "") or ""), 160
    ).replace("\n", " ")
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
        is_error = event_type in {"tool_error", "run_error"} or (
            event_type == "voice_tool_output" and diagnostic.get("outcome") == "error"
        )
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


def _effective_observability(prompts: list[dict[str, Any]]) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for prompt in prompts:
        snapshot = prompt.get("observability")
        if isinstance(snapshot, dict) and snapshot:
            latest = snapshot
    if not latest:
        _resolve_claude_obs = None
        try:
            from autonomous_agent_builder.config import get_settings
            from autonomous_agent_builder.observability.runtime import resolve_claude_observability as _resolve_claude_obs
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
        elif sdk == "claude" and _resolve_claude_obs is not None:
            latest = _resolve_claude_obs().summary
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
    collector = (
        effective.get("collector", {}) if isinstance(effective.get("collector"), dict) else {}
    )
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
        if (
            telemetry_enabled
            and uses_otlp
            and collector_checked
            and collector_reachable is not True
        ):
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
        next_step = (
            "Configure a real OTLP collector endpoint before treating exported telemetry as usable."
        )
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


def _selected_runtime_from_coverage(coverage: dict[str, Any]) -> str:
    runtime_sdk = str(coverage.get("runtime_sdk") or "").strip()
    if runtime_sdk.startswith("codex"):
        return "codex_sdk"
    if runtime_sdk in {"claude", "claude_agent_sdk"}:
        return "claude_agent_sdk"
    return _selected_runtime_sdk()


def _prompt_summaries(prompts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for prompt in prompts:
        tools = prompt.get("tools", [])
        if not isinstance(tools, list):
            tools = []
        tool_names = [
            str(tool.get("tool_name") or tool.get("event_type") or "")
            for tool in tools
            if isinstance(tool, dict)
        ]
        failed_tools = [
            name
            for name, tool in zip(tool_names, tools, strict=False)
            if isinstance(tool, dict) and tool.get("outcome") == "error"
        ]
        telemetry = prompt.get("telemetry", {})
        if not isinstance(telemetry, dict):
            telemetry = {}
        token_accounting = _prompt_token_accounting(prompt)
        context = prompt.get("context_efficiency", {})
        if not isinstance(context, dict):
            context = {}
        summary: dict[str, Any] = {
            "index": prompt.get("index"),
            "started_at": prompt.get("started_at"),
            "user_prompt": _text_preview(prompt.get("user_prompt", ""), limit=140),
            "tool_count": len(tool_names),
            "failed_tool_count": len(failed_tools),
            "tool_names": sorted({name for name in tool_names if name})[:8],
            "telemetry": {
                key: telemetry.get(key)
                for key in (
                    "tokens_used",
                    "tokens_input",
                    "tokens_output",
                    "tokens_cached",
                    "raw_tokens",
                    "noncached_plus_output_tokens",
                    "cost_usd",
                    "duration_ms",
                    "stop_reason",
                )
                if telemetry.get(key) not in ("", None)
            },
            "context_efficiency": {
                "grade": context.get("grade", ""),
                "signals": context.get("signals", []),
            },
        }
        if token_accounting["raw_tokens"]:
            summary["token_accounting"] = token_accounting
        if failed_tools:
            summary["failed_tools"] = failed_tools[:5]
        if prompt.get("risks"):
            summary["risks"] = prompt.get("risks")
        if isinstance(prompt.get("context_budget"), dict):
            context_budget = prompt["context_budget"]
            summary["context_budget"] = {
                key: context_budget.get(key)
                for key in ("lane", "stage", "total_estimated_tokens", "signal_category")
                if context_budget.get(key) not in ("", None)
            }
        summaries.append(summary)
    return summaries


def _prompt_token_accounting(prompt: dict[str, Any]) -> dict[str, Any]:
    telemetry = prompt.get("telemetry", {})
    if not isinstance(telemetry, dict):
        telemetry = {}
    observability = prompt.get("observability", {})
    if not isinstance(observability, dict):
        observability = {}
    observability_accounting = observability.get("optimization_summary", {}).get("token_accounting", {})
    if not isinstance(observability_accounting, dict):
        observability_accounting = {}

    input_tokens = _int_value(
        telemetry.get("tokens_input"),
        observability.get("input_tokens"),
        observability_accounting.get("input_tokens"),
    )
    output_tokens = _int_value(
        telemetry.get("tokens_output"),
        observability.get("output_tokens"),
        observability_accounting.get("output_tokens"),
    )
    cached_tokens = _int_value(
        telemetry.get("tokens_cached"),
        observability.get("cached_input_tokens"),
        observability_accounting.get("cached_input_tokens"),
    )
    raw_tokens = _int_value(
        telemetry.get("raw_tokens"),
        observability.get("total_tokens"),
        observability_accounting.get("raw_total_tokens"),
        telemetry.get("tokens_used"),
    )
    if raw_tokens == 0 and (input_tokens or output_tokens):
        raw_tokens = input_tokens + output_tokens
    noncached_plus_output_tokens = _int_value(
        telemetry.get("noncached_plus_output_tokens"),
        observability_accounting.get("noncached_plus_output_tokens"),
    )
    if noncached_plus_output_tokens == 0 and (input_tokens or output_tokens or cached_tokens):
        noncached_plus_output_tokens = max(input_tokens - cached_tokens, 0) + output_tokens
    cache_ratio = _float_value(
        observability_accounting.get("cache_ratio"),
        telemetry.get("cache_ratio"),
    )
    if cache_ratio == 0.0 and (cached_tokens + input_tokens) > 0:
        _cr_denom = cached_tokens + input_tokens
        cache_ratio = round(min(1.0, max(0.0, cached_tokens / _cr_denom)), 4)
    return {
        "raw_tokens": raw_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "noncached_plus_output_tokens": noncached_plus_output_tokens,
        "cache_ratio": cache_ratio,
    }


def _aggregate_prompt_token_accounting(prompts: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [_prompt_token_accounting(prompt) for prompt in prompts]
    raw_tokens = sum(row["raw_tokens"] for row in rows)
    input_tokens = sum(row["input_tokens"] for row in rows)
    output_tokens = sum(row["output_tokens"] for row in rows)
    cached_tokens = sum(row["cached_tokens"] for row in rows)
    noncached_plus_output_tokens = sum(row["noncached_plus_output_tokens"] for row in rows)
    _cr_denom = cached_tokens + input_tokens
    cache_ratio = round(min(1.0, max(0.0, cached_tokens / _cr_denom)), 4) if _cr_denom > 0 else 0.0
    return {
        "raw_tokens": raw_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "noncached_plus_output_tokens": noncached_plus_output_tokens,
        "cache_ratio": cache_ratio,
    }


def _int_value(*values: Any) -> int:
    for value in values:
        if value in ("", None):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _float_value(*values: Any) -> float:
    for value in values:
        if value in ("", None):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _compact_observability_coverage(coverage: dict[str, Any]) -> dict[str, Any]:
    otel = coverage.get("otel", {}) if isinstance(coverage.get("otel"), dict) else {}
    collector = otel.get("collector", {}) if isinstance(otel.get("collector"), dict) else {}
    return {
        "source": coverage.get("source", ""),
        "runtime_sdk": coverage.get("runtime_sdk", ""),
        "provider": coverage.get("provider", ""),
        "telemetry_source": coverage.get("telemetry_source", ""),
        "counts": coverage.get("counts", {}),
        "missing_signals": coverage.get("missing_signals", []),
        "otel": {
            "enabled": otel.get("enabled"),
            "signals": {
                "metrics": bool(otel.get("metrics_exporter")),
                "logs": bool(otel.get("logs_exporter")),
                "traces": bool(otel.get("traces_exporter")),
            },
            "collector": {
                "configured": collector.get("configured"),
                "reachable": collector.get("reachable"),
                "status": collector.get("status", ""),
            },
        },
        "next": coverage.get("next", ""),
    }


def _compact_telemetry_health(telemetry_health: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in ("claude_native", "codex_native", "builder_product"):
        value = telemetry_health.get(key)
        if not isinstance(value, dict):
            continue
        collector = value.get("collector", {}) if isinstance(value.get("collector"), dict) else {}
        compact[key] = {
            "status": value.get("status", ""),
            "enabled": value.get("enabled"),
            "collector_status": value.get("collector_status") or collector.get("status", ""),
            "collector_reachable": value.get("collector_reachable") or collector.get("reachable"),
            "missing_signals": value.get("missing_signals", []),
        }
    return compact


def _compact_optimization_decision(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        key: decision.get(key)
        for key in (
            "runtime",
            "primary_score_surface",
            "diagnostic_surface",
            "next_action",
            "target_area",
            "reason",
            "estimated_script_savings_tokens",
            "model_effort_action",
            "subagent_action",
        )
        if decision.get(key) not in ("", None)
    }


def _compact_runtime_decision_summary(decisions: dict[str, Any]) -> dict[str, Any]:
    candidates = decisions.get("deterministic_script_candidates", [])
    if not isinstance(candidates, list):
        candidates = []
    phases = decisions.get("phase_decisions", [])
    if not isinstance(phases, list):
        phases = []
    return {
        "runtime": decisions.get("runtime", ""),
        "capability_gaps": decisions.get("capability_gaps", []),
        "native_capability_count": decisions.get("native_capability_count", 0),
        "fallback_capability_count": decisions.get("fallback_capability_count", 0),
        "phase_count": len(phases),
        "deterministic_script_candidate_codes": [
            str(item.get("code") or "")
            for item in candidates
            if isinstance(item, dict) and item.get("code")
        ],
    }


def _compact_script_candidates(candidates: Any) -> list[dict[str, Any]]:
    if not isinstance(candidates, list):
        return []
    return [
        {
            key: item.get(key)
            for key in (
                "code",
                "severity",
                "status",
                "trigger",
                "command",
                "owner_lane",
                "next_actor",
            )
            if isinstance(item, dict) and item.get(key) not in ("", None)
        }
        for item in candidates[:5]
        if isinstance(item, dict)
    ]


def _compact_recommendations(recommendations: Any) -> list[dict[str, Any]]:
    if not isinstance(recommendations, list):
        return []
    return [
        {
            key: item.get(key)
            for key in ("code", "severity", "next_action", "lifecycle_status")
            if isinstance(item, dict) and item.get(key) not in ("", None)
        }
        for item in recommendations[:5]
        if isinstance(item, dict)
    ]


def _compact_cost_drivers(drivers: Any) -> list[dict[str, Any]]:
    if not isinstance(drivers, list):
        return []
    return [
        {
            key: item.get(key)
            for key in ("agent_name", "runs", "raw_tokens")
            if isinstance(item, dict) and item.get(key) not in ("", None)
        }
        for item in drivers[:5]
        if isinstance(item, dict)
    ]


def _analyze_timeline(
    session: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    full: bool = False,
) -> dict[str, Any]:
    _agent_run_raw = session.get("agent_run")
    agent_run: dict = _agent_run_raw if isinstance(_agent_run_raw, dict) else {}
    prompts = build_timeline_prompts(items)

    prompt_tokens = sum(
        int(prompt.get("telemetry", {}).get("tokens_used") or 0) for prompt in prompts
    )
    prompt_token_accounting = _aggregate_prompt_token_accounting(prompts)
    run_tokens = int(agent_run.get("tokens_input") or 0) + int(agent_run.get("tokens_output") or 0)
    total_tokens = prompt_tokens or run_tokens
    prompt_cost = sum(
        float(prompt.get("telemetry", {}).get("cost_usd") or 0.0) for prompt in prompts
    )
    total_cost = prompt_cost or float(
        agent_run.get("estimated_cost_usd") or agent_run.get("cost_usd") or 0.0
    )
    review_count = sum(
        1 for prompt in prompts if prompt.get("context_efficiency", {}).get("grade") == "review"
    )
    coverage = _observability_coverage(prompts)
    runtime_aggregates = _compute_runtime_aggregates(
        _db_path(), session_id=str(session.get("id") or "") or None
    )
    dashboard_observability = dashboard_observability_summary(_db_path())
    telemetry_health = dashboard_observability.get("observability_coverage", {}).get(
        "telemetry_health",
        {},
    )
    deterministic_recommendations = dashboard_observability.get("deterministic_recommendations", [])
    optimization = runtime_aggregates.get("optimization_summary", {})
    # IMP-023: per-prompt telemetry.tokens_used and agent_run usage columns are
    # not always persisted (notably chat-session prompts), leaving the headline
    # at 0 while the session-scoped raw event-payload aggregate IS populated.
    # Fall back to the same optimization_summary source raw_token_total uses so
    # the self-optimizer headline is never blind. (Cost has no in-scope raw
    # fallback — deferred to Fix B / chat-turn telemetry persistence.)
    if not total_tokens:
        total_tokens = int(
            optimization.get("noncached_plus_output_tokens")
            or optimization.get("raw_token_total")
            or 0
        )
    context_budget = runtime_aggregates.get("context_budget", {})
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
    payload = {
        "ok": True,
        "status": "ok",
        "exit_code": EXIT_SUCCESS,
        "session_id": session.get("id", ""),
        "sdk_session_id": session.get("sdk_session_id"),
        "prompt_count": len(prompts),
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "analysis_target": (
            "agent_run"
            if agent_run and not items
            else str(session.get("target_kind") or "chat_session")
        ),
        "review_prompt_count": review_count,
        "observability_coverage": (coverage if full else _compact_observability_coverage(coverage)),
        "selected_runtime": selected_runtime,
        "runtime_native_telemetry_health": {
            key: telemetry_health.get(key)
            for key in ("claude_native", "codex_native")
            if key in telemetry_health
        }
        if full
        else {
            key: value
            for key, value in _compact_telemetry_health(telemetry_health).items()
            if key in ("claude_native", "codex_native")
        },
        "builder_product_telemetry_health": (
            telemetry_health.get("builder_product", {})
            if full
            else _compact_telemetry_health(telemetry_health).get("builder_product", {})
        ),
        "raw_token_total": int(
            optimization.get("raw_token_total")
            or prompt_token_accounting["raw_tokens"]
            or total_tokens
        ),
        "input_tokens": int(prompt_token_accounting["input_tokens"]),
        "output_tokens": int(prompt_token_accounting["output_tokens"]),
        "cached_tokens": int(
            optimization.get("cached_tokens") or prompt_token_accounting["cached_tokens"]
        ),
        "noncached_plus_output_tokens": int(
            optimization.get("noncached_plus_output_tokens")
            or prompt_token_accounting["noncached_plus_output_tokens"]
        ),
        "cache_ratio": float(
            optimization.get("cache_ratio") or prompt_token_accounting["cache_ratio"]
        ),
        "phase_ceremony_tokens": int(optimization.get("phase_ceremony_tokens") or 0),
        "avoidable_token_estimate": int(optimization.get("avoidable_token_estimate") or 0),
        "top_cost_drivers": (
            (optimization.get("top_cost_drivers", []) or [])[:5]
            if full
            else _compact_cost_drivers(optimization.get("top_cost_drivers", []))
        ),
        "recommended_next_change": str(optimization.get("recommended_next_change") or ""),
        "optimization_decision": (
            optimization_decision if full else _compact_optimization_decision(optimization_decision)
        ),
        "runtime_decision_summary": (
            decisions if full else _compact_runtime_decision_summary(decisions)
        ),
        "phase_runtime_decisions": decisions.get("phase_decisions", []) if full else [],
        "deterministic_script_candidates": (
            decisions.get("deterministic_script_candidates", [])
            if full
            else _compact_script_candidates(decisions.get("deterministic_script_candidates", []))
        ),
        "deterministic_recommendations": (
            deterministic_recommendations
            if full
            else _compact_recommendations(deterministic_recommendations)
        ),
        "context_budget": context_budget,
        "agent_run_evidence": _compact_agent_run_evidence(agent_run) if agent_run else {},
        "raw_evidence": {
            "available": bool(items) or bool(agent_run),
            "event_count": len(items),
            "command": "builder logs --session <id> --raw --json",
            "full_analysis_command": "builder logs analyze --session <id> --full --json",
            "contains": [
                "chat events",
                "tool results",
                "run status",
                "context budget",
                "raw payloads",
                "persisted AgentRun observability",
            ],
            "note": (
                "chat timeline events are available for this builder chat session"
                if items
                else (
                    "no chat timeline events resolved; using persisted AgentRun observability for this run"
                    if agent_run
                    else "no chat timeline events resolved for this session; use builder metrics show --json --full for persisted AgentRun observability"
                )
            ),
        },
        "schema_version": "1",
        "next": "builder logs analyze --session <id> --full --json",
    }
    if full:
        payload["telemetry_health"] = telemetry_health
        payload["runtime_aggregates"] = runtime_aggregates
        payload["prompts"] = prompts
    else:
        payload["prompt_summaries"] = _prompt_summaries(prompts)
        payload["analysis_mode"] = "summary"
    return payload


def _compact_agent_run_evidence(agent_run: dict[str, Any]) -> dict[str, Any]:
    if not agent_run:
        return {}
    tokens_input = int(agent_run.get("tokens_input") or 0)
    tokens_output = int(agent_run.get("tokens_output") or 0)
    observability = agent_run.get("observability")
    return {
        "id": agent_run.get("id", ""),
        "task_id": agent_run.get("task_id", ""),
        "agent_name": agent_run.get("agent_name", ""),
        "runtime_sdk": agent_run.get("runtime_sdk", ""),
        "provider": agent_run.get("provider", ""),
        "model": agent_run.get("model", ""),
        "effort": agent_run.get("effort", ""),
        "status": agent_run.get("status", ""),
        "stop_reason": agent_run.get("stop_reason", ""),
        "tokens": tokens_input + tokens_output,
        "tokens_cached": int(agent_run.get("tokens_cached") or 0),
        "duration_ms": int(agent_run.get("duration_ms") or 0),
        "cost_usd": float(agent_run.get("cost_usd") or 0.0),
        "estimated_cost_usd": float(agent_run.get("estimated_cost_usd") or 0.0),
        "observability_available": bool(observability),
    }


def _emit_ndjson(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        sys.stdout.write(json.dumps(row, ensure_ascii=True) + "\n")
    sys.stdout.flush()


@app.command("analyze")
def analyze(
    session_id: str | None = typer.Option(
        None, "--session", help="Chat session ID or unique prefix."
    ),
    full: bool = typer.Option(
        False,
        "--full",
        help="Include full prompt details, runtime aggregates, and telemetry health payloads.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Analyze one chat session with compact telemetry by default."""
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

    payload = _analyze_timeline(session, items, full=full)
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
        prompt_rows = item.get("prompts") or item.get("prompt_summaries") or []
        for prompt in prompt_rows:
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
                + (f" ({', '.join(context.get('signals', []))})" if context.get("signals") else "")
            )
            if "tools" in prompt:
                tool_names = [
                    tool.get("tool_name", "") or tool.get("event_type", "")
                    for tool in prompt.get("tools", [])
                ]
            else:
                tool_names = prompt.get("tool_names", [])
            lines.append(f"tools: {', '.join(tool_names) if tool_names else '(none)'}")
            if prompt.get("failed_tool_count"):
                lines.append(f"failed_tools: {prompt.get('failed_tool_count')}")
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
    raw: bool = typer.Option(
        False, "--raw", help="Emit exact stored event rows without diagnostic compaction."
    ),
    compact: bool = typer.Option(
        False, "--compact", help="Trim payloads to the minimum useful fields."
    ),
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
    should_follow = (
        bool(follow)
        if follow is not None
        else bool(error and not (json or ndjson) and sys.stdout.isatty())
    )

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
                    truncate(
                        str(diagnostic.get("summary", "") or payload.get("content", "") or ""), 120
                    ).replace("\n", " "),
                    truncate(str(diagnostic.get("input_focus", "") or "-"), 80).replace("\n", " "),
                ]
            )
        return table(headers, body, max_col_width=60)

    payload = (
        compact_results_payload(
            "logs",
            rendered_items,
            next_step="builder logs --session <id> --raw --json"
            if raw
            else "builder logs --session <id> --compact --json",
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
                new_items = [
                    item for item in reversed(fresh) if str(item.get("id", "")) not in seen_ids
                ]
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
