"""Runtime-aware observability summaries for dashboard and CLI surfaces."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.observability.codex_otel import codex_otel_status
from autonomous_agent_builder.observability.runtime import resolve_claude_observability
from autonomous_agent_builder.observability.runtime_optimization import (
    deterministic_script_candidates,
    optimization_decision_summary,
    runtime_capability_matrix,
    runtime_decision_summary,
)
from autonomous_agent_builder.observability.summary_db import (
    _agent_run_rows,
    _chat_run_rows,
    _context_budget_summary,
    _event_types,
    _merge_rows,
    _repeated_retrieval_signal,
    _runtime_recovery_summary,
    _stop_reason_counts,
    _sum_rows,
    _table_exists,
    _tool_counts,
)
from autonomous_agent_builder.observability.summary_recommendation_lifecycle import (
    _apply_recommendation_lifecycle,
    _open_script_candidates,
    _recommendation_lifecycle,
)
from autonomous_agent_builder.observability.summary_recommendations import (
    _deterministic_recommendations,
    _rank_recommendations,
)
from autonomous_agent_builder.observability.summary_runtime_aggregates import (
    _approval_wait_summary,
    _empty_runtime_aggregates,
    _error_summary,
    _phase_ceremony_summary,
    _provider_limit_summary,
    _recommendations,
)
from autonomous_agent_builder.runtime.factory import resolve_runtime_config
from autonomous_agent_builder.services.codex_optimization import summarize_runs_for_optimization


def _available_packaged_scripts() -> list[str]:
    scripts_dir = Path(__file__).resolve().parents[1] / "embedded" / "scripts"
    if not scripts_dir.exists():
        return []
    return sorted(
        path.stem
        for path in scripts_dir.glob("*.py")
        if path.stem not in {"__init__", "base", "executor"}
    )


def dashboard_observability_summary(db_path: Path) -> dict[str, Any]:
    """Return runtime-specific diagnostic coverage for the dashboard."""

    runtime = _selected_runtime()
    aggregates = runtime_aggregates(db_path)
    optimization = aggregates.get("optimization_summary", {})
    project_root = _project_root_for_db(db_path)
    coverage = _observability_coverage(runtime, aggregates, optimization, project_root)
    telemetry_health = _telemetry_health(db_path, runtime, coverage, aggregates, optimization)
    raw_deterministic_recommendations = _deterministic_recommendations(
        telemetry_health,
        coverage,
        aggregates,
        optimization,
    )
    deterministic_recommendations, resolved_recommendations = _apply_recommendation_lifecycle(
        raw_deterministic_recommendations,
        aggregates.get("recommendation_lifecycle", {}),
    )
    deterministic_recommendations = _rank_recommendations(deterministic_recommendations)
    coverage["telemetry_health"] = telemetry_health
    coverage["deterministic_recommendations"] = deterministic_recommendations
    coverage["resolved_recommendations"] = resolved_recommendations
    coverage["recommendation_lifecycle"] = aggregates.get("recommendation_lifecycle", {})
    open_script_candidates = _open_script_candidates(
        aggregates.get("deterministic_script_candidates", []),
        deterministic_recommendations,
    )
    decision_aggregates = {
        **aggregates,
        "deterministic_script_candidates_override": open_script_candidates,
    }
    recommendations = _recommendations(runtime, coverage, aggregates, optimization)
    capability_matrix = runtime_capability_matrix(runtime["selected_runtime_sdk"])
    decision_summary = runtime_decision_summary(
        runtime["selected_runtime_sdk"],
        aggregates=decision_aggregates,
        optimization=optimization,
    )
    optimization_decision = optimization_decision_summary(
        runtime["selected_runtime_sdk"],
        aggregates=decision_aggregates,
        optimization=optimization,
    )
    return {
        "ok": True,
        "status": "ok",
        "schema_version": "1",
        "generated_at": datetime.now(UTC).isoformat(),
        "runtime": runtime,
        "observability_coverage": coverage,
        "runtime_aggregates": aggregates,
        "optimization_summary": optimization,
        "runtime_capability_matrix": capability_matrix,
        "phase_runtime_decisions": decision_summary["phase_decisions"],
        "deterministic_script_candidates": decision_summary["deterministic_script_candidates"],
        "deterministic_recommendations": deterministic_recommendations,
        "runtime_decision_summary": decision_summary,
        "optimization_decision": optimization_decision,
        "recommendations": recommendations,
    }


def runtime_aggregates(db_path: Path) -> dict[str, Any]:
    """Return compact repo-local run aggregates for observability review."""

    if not db_path.exists():
        return _empty_runtime_aggregates("agent_builder_db_missing")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "agent_runs") and not _table_exists(conn, "chat_events"):
            return _empty_runtime_aggregates("agent_runs_table_missing")
        run_rows = _agent_run_rows(conn)
        chat_rows = _chat_run_rows(conn)
        rows = [*run_rows, *chat_rows]
        by_agent = _merge_rows(rows, "agent_name")
        by_runtime = _merge_rows(rows, "runtime_sdk", "provider")
        by_model_effort = _merge_rows(rows, "model", "effort")
        approval_wait = _approval_wait_summary(conn)
        tool_counts, tool_event_count = _tool_counts(conn)
        context_budget = _context_budget_summary(conn)
        optimization_summary = summarize_runs_for_optimization(rows)
        totals = _sum_rows(rows)
        has_runtime_runs = int(totals.get("runs") or 0) > 0
        has_tokenized_runtime_runs = any(
            int(row.get("tokens_input") or 0) > 0
            or int(row.get("tokens_output") or 0) > 0
            or int(row.get("tokens_cached") or 0) > 0
            or float(row.get("cost_usd") or 0.0) > 0.0
            for row in rows
        )
        payload = {
            "available": True,
            "available_scripts": _available_packaged_scripts(),
            "by_agent": by_agent,
            "by_runtime": by_runtime,
            "by_model_effort": by_model_effort,
            "totals": totals,
            "stop_reasons": _stop_reason_counts(conn),
            "phase_ceremony": _phase_ceremony_summary(by_agent, approval_wait),
            "approval_wait": approval_wait,
            "provider_limits": _provider_limit_summary(conn),
            "error_summary": _error_summary(conn),
            "event_types": _event_types(conn),
            "runtime_recovery": _runtime_recovery_summary(rows),
            "context_budget": context_budget,
            "optimization_summary": {**optimization_summary, "available": True},
            "tool_observability": {
                "agent_run_events_available": _table_exists(conn, "agent_run_events"),
                "agent_run_event_count": tool_event_count,
                "missing_tool_events": _table_exists(conn, "agent_run_events")
                and has_runtime_runs
                and has_tokenized_runtime_runs
                and tool_event_count == 0,
                "tool_counts": tool_counts,
                "repeated_retrieval_signal": _repeated_retrieval_signal(tool_counts),
            },
        }
        payload["deterministic_script_candidates"] = deterministic_script_candidates(
            payload,
            payload["optimization_summary"],
        )
        payload["recommendation_lifecycle"] = _recommendation_lifecycle(conn)
        return payload
    finally:
        conn.close()


def _selected_runtime() -> dict[str, Any]:
    config = resolve_runtime_config(get_settings())
    sdk = str(config.get("sdk") or "claude")
    runtime_type = "codex_sdk" if sdk.startswith("codex") else "claude_agent_sdk"
    return {
        "selected_runtime_sdk": runtime_type,
        "runtime_sdk": sdk,
        "provider": str(config.get("provider") or ""),
        "model": str(config.get("model") or ""),
        "effort": str(config.get("effort") or config.get("preference") or "balanced"),
        "coverage_mode": "codex_app_server" if runtime_type == "codex_sdk" else "claude_otel",
    }


def _observability_coverage(
    runtime: dict[str, Any],
    aggregates: dict[str, Any],
    optimization: dict[str, Any],
    project_root: Path | None = None,
) -> dict[str, Any]:
    if runtime.get("selected_runtime_sdk") == "codex_sdk":
        return _codex_coverage(runtime, aggregates, optimization)
    return _claude_coverage(runtime, aggregates, project_root)


def _claude_coverage(
    runtime: dict[str, Any],
    aggregates: dict[str, Any],
    project_root: Path | None = None,
) -> dict[str, Any]:
    summary = resolve_claude_observability(_project_claude_otel_env(project_root)).summary
    signal_state = summary.get("signal_state", {})
    metrics_enabled = bool(signal_state.get("metrics") or summary.get("metrics_exporter"))
    logs_enabled = bool(signal_state.get("logs") or summary.get("logs_exporter"))
    traces_enabled = bool(signal_state.get("traces") or summary.get("traces_exporter"))
    collector = summary.get("collector") if isinstance(summary.get("collector"), dict) else {}
    collector_status = str(collector.get("status") or "unknown")
    collector_reachable = collector.get("reachable")
    missing: list[str] = []
    if not metrics_enabled:
        missing.append("otel_metrics_exporter")
    if not logs_enabled:
        missing.append("otel_logs_exporter")
    if not traces_enabled:
        missing.append("otel_traces_exporter")
    if bool(summary.get("endpoint_placeholder")):
        missing.append("otel_otlp_endpoint")
    if collector_status in {"configured_unreachable", "invalid_endpoint"}:
        missing.append("otel_collector_unreachable")
    if aggregates.get("tool_observability", {}).get("missing_tool_events"):
        missing.append("tool_events")
    next_action = (
        "Claude Agent SDK OTEL and local run evidence are usable."
        if not missing
        else "Fix missing Claude OTEL/tool signals before treating observability as complete."
    )
    return {
        "mode": "claude_otel",
        "source": summary.get("source", "runtime_env"),
        "runtime_sdk": runtime.get("runtime_sdk"),
        "available_signals": [
            signal
            for signal, enabled in (
                ("otel_metrics", metrics_enabled),
                ("otel_logs", logs_enabled),
                ("otel_traces", traces_enabled),
                (
                    "tool_events",
                    not aggregates.get("tool_observability", {}).get("missing_tool_events"),
                ),
            )
            if enabled
        ],
        "counts": {
            "tools": int(
                aggregates.get("tool_observability", {}).get("agent_run_event_count") or 0
            ),
            "errors": 0,
            "delegations": 0,
        },
        "otel": {
            **summary,
            "collector_reachable": collector_reachable,
            "collector_status": collector_status,
        },
        "codex": {},
        "missing_signals": missing,
        "next": next_action,
    }


def _codex_coverage(
    runtime: dict[str, Any],
    aggregates: dict[str, Any],
    optimization: dict[str, Any],
) -> dict[str, Any]:
    totals = aggregates.get("totals", {})
    tool_state = aggregates.get("tool_observability", {})
    context_budget = aggregates.get("context_budget", {})
    raw_tokens = int(optimization.get("raw_token_total") or 0)
    flags = optimization.get("avoidable_cost_flags") if isinstance(optimization, dict) else []
    flags = flags if isinstance(flags, list) else []
    flag_names = {str(item.get("flag")) for item in flags if isinstance(item, dict)}
    chunk_pressure = (
        optimization.get("chunk_pressure")
        if isinstance(optimization.get("chunk_pressure"), dict)
        else {}
    )
    chunk_pressure_available = bool(chunk_pressure.get("available"))
    missing: list[str] = []
    if raw_tokens <= 0:
        missing.append("codex_token_usage")
    if not aggregates.get("by_model_effort"):
        missing.append("model_effort_fields")
    if tool_state.get("missing_tool_events"):
        missing.append("tool_events")
    if not context_budget.get("available"):
        missing.append("context_budget")
    if (
        "chunk_pressure_large_event" in flag_names or "large_command_output" in flag_names
    ) and not chunk_pressure_available:
        missing.append("chunk_pressure")
    next_action = (
        "Codex app-server run evidence is usable for cost and quality diagnosis."
        if not missing
        else "Fix missing Codex app-server/token/tool signals before optimizing routing."
    )
    return {
        "mode": "codex_app_server",
        "source": "codex_app_server",
        "runtime_sdk": runtime.get("runtime_sdk"),
        "available_signals": [
            signal
            for signal, enabled in (
                ("app_server_events", raw_tokens > 0),
                ("token_usage", raw_tokens > 0),
                ("model_effort", bool(aggregates.get("by_model_effort"))),
                ("native_user_input", True),
                ("tool_events", not tool_state.get("missing_tool_events")),
                ("context_budget", bool(context_budget.get("available"))),
                ("chunk_pressure", chunk_pressure_available),
                ("estimated_cost", float(totals.get("estimated_cost_usd") or 0.0) > 0),
            )
            if enabled
        ],
        "counts": {
            "tools": int(tool_state.get("agent_run_event_count") or 0),
            "errors": 0,
            "delegations": 0,
        },
        "otel": {},
        "codex": {
            "app_server_events": raw_tokens > 0,
            "token_usage": raw_tokens > 0,
            "native_user_input": True,
            "estimated_cost_usd": float(totals.get("estimated_cost_usd") or 0.0),
            "estimated_codex_credits": totals.get("estimated_codex_credits"),
            "raw_token_total": raw_tokens,
            "cache_ratio": optimization.get("cache_ratio", 0),
            "chunk_pressure": chunk_pressure,
            "top_cost_drivers": optimization.get("top_cost_drivers", []),
            "avoidable_cost_flags": flags,
            "context_budget": context_budget,
        },
        "missing_signals": missing,
        "next": next_action,
    }


def _telemetry_health(
    db_path: Path,
    runtime: dict[str, Any],
    coverage: dict[str, Any],
    aggregates: dict[str, Any],
    optimization: dict[str, Any],
) -> dict[str, Any]:
    project_root = _project_root_for_db(db_path)
    claude_summary = resolve_claude_observability(_project_claude_otel_env(project_root)).summary
    claude_collector = (
        claude_summary.get("collector") if isinstance(claude_summary.get("collector"), dict) else {}
    )
    codex_status = codex_otel_status(project_root)
    selected = runtime.get("selected_runtime_sdk")
    claude_status = _native_status(
        enabled=bool(claude_summary.get("enabled")),
        collector_status=str(claude_collector.get("status") or "missing"),
        missing=[
            key
            for key in ("metrics_exporter", "logs_exporter", "traces_exporter")
            if not claude_summary.get(key)
        ],
    )
    if selected != "claude_agent_sdk" and not claude_summary.get("enabled"):
        claude_status = "inactive"
    codex_native_status = _native_status(
        enabled=bool(codex_status.get("enabled")),
        collector_status=str(codex_status.get("collector_status") or "missing"),
        missing=[]
        if codex_status.get("enabled")
        else [str(codex_status.get("reason") or "codex_otel_missing")],
    )
    if selected != "codex_sdk" and not codex_status.get("enabled"):
        codex_native_status = "inactive"
    return {
        "selected_runtime": selected,
        "claude_native": {
            "status": claude_status,
            "enabled": bool(claude_summary.get("enabled")),
            "signals": claude_summary.get("signal_state", {}),
            "collector": claude_collector,
            "collector_status": claude_collector.get("status", "missing"),
            "sensitive_data_flags": claude_summary.get("sensitive_data_flags", []),
        },
        "codex_native": {
            "status": codex_native_status,
            **codex_status,
        },
        "builder_product": _builder_product_health(db_path, aggregates, optimization),
        "contract": "runtime_native_to_otel_builder_db_is_product_truth",
    }


def _native_status(*, enabled: bool, collector_status: str, missing: list[str]) -> str:
    if not enabled:
        return "missing"
    if collector_status in {"configured_unreachable", "invalid_endpoint"}:
        return "blocked"
    if missing:
        return "degraded"
    if collector_status in {"reachable", "configured_not_checked"}:
        return "ok"
    return "unknown"


def _builder_product_health(
    db_path: Path,
    aggregates: dict[str, Any],
    optimization: dict[str, Any],
) -> dict[str, Any]:
    required_tables = {
        "projects": "project",
        "features": "feature",
        "tasks": "task",
        "agent_runs": "run",
        "agent_run_events": "tool",
        "gate_results": "gate",
        "approval_gates": "approval",
        "chat_events": "runtime",
    }
    if not db_path.exists():
        return {
            "status": "missing",
            "source": "active_db",
            "complete": False,
            "missing_facts": list(required_tables.values()),
            "counts": {},
        }
    conn = sqlite3.connect(db_path)
    try:
        counts: dict[str, int] = {}
        missing: list[str] = []
        for table, fact in required_tables.items():
            if not _table_exists(conn, table):
                counts[table] = 0
                missing.append(fact)
                continue
            count = int(conn.execute(f"select count(*) from {table}").fetchone()[0] or 0)
            counts[table] = count
            if count <= 0 and fact in {"task", "run", "runtime"}:
                missing.append(fact)
        if not aggregates.get("by_runtime"):
            missing.append("runtime_attribution")
        if float(aggregates.get("totals", {}).get("estimated_cost_usd") or 0.0) <= 0:
            missing.append("cost")
        if int(optimization.get("raw_token_total") or 0) <= 0:
            missing.append("token")
        context_budget = aggregates.get("context_budget", {})
        counts["context_budget_events"] = int(context_budget.get("event_count") or 0)
        if not context_budget.get("available"):
            missing.append("context")
        return {
            "status": "ok" if not missing else "degraded",
            "source": "active_db",
            "complete": not missing,
            "missing_facts": sorted(set(missing)),
            "counts": counts,
            "canonical_facts": [
                "project",
                "feature",
                "task",
                "run",
                "phase",
                "gate",
                "approval",
                "runtime",
                "model",
                "tool",
                "context",
                "cost",
                "failure",
                "retry",
                "artifact",
                "PR",
            ],
        }
    finally:
        conn.close()


def _project_root_for_db(db_path: Path) -> Path:
    return db_path.parent.parent if db_path.parent.name == ".agent-builder" else db_path.parent


def _project_claude_otel_env(project_root: Path | None) -> dict[str, str] | None:
    if project_root is None:
        return None
    env_path = project_root / ".env"
    if not env_path.exists():
        return None
    env: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw_value = stripped.partition("=")
        env[key.strip()] = raw_value.strip().strip('"').strip("'")
    if str(env.get("AAB_CLAUDE_OTEL_ENABLED") or "").lower() not in {"1", "true", "yes", "on"}:
        return None
    endpoint = str(env.get("AAB_CLAUDE_OTEL_ENDPOINT") or "").strip()
    if not endpoint:
        return None
    return {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
        "OTEL_TRACES_EXPORTER": env.get("AAB_CLAUDE_OTEL_TRACES_EXPORTER", "otlp"),
        "OTEL_METRICS_EXPORTER": env.get("AAB_CLAUDE_OTEL_METRICS_EXPORTER", "otlp"),
        "OTEL_LOGS_EXPORTER": env.get("AAB_CLAUDE_OTEL_LOGS_EXPORTER", "otlp"),
        "OTEL_EXPORTER_OTLP_PROTOCOL": env.get("AAB_CLAUDE_OTEL_PROTOCOL", "http/protobuf"),
        "OTEL_EXPORTER_OTLP_ENDPOINT": endpoint,
        "OTEL_SERVICE_NAME": env.get("AAB_CLAUDE_OTEL_SERVICE_NAME", "autonomous-agent-builder"),
        "OTEL_METRICS_INCLUDE_SESSION_ID": env.get("AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID", "true"),
        "OTEL_METRIC_EXPORT_INTERVAL": env.get("AAB_CLAUDE_OTEL_METRIC_INTERVAL_MS", "2000"),
        "OTEL_LOGS_EXPORT_INTERVAL": env.get("AAB_CLAUDE_OTEL_LOGS_INTERVAL_MS", "1000"),
        "OTEL_TRACES_EXPORT_INTERVAL": env.get("AAB_CLAUDE_OTEL_TRACES_INTERVAL_MS", "1000"),
    }
