"""Runtime-aware observability summaries for dashboard and CLI surfaces."""

from __future__ import annotations

import json
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
from autonomous_agent_builder.observability.summary_recommendations import (
    _deterministic_recommendation,
    _deterministic_recommendations,
    _rank_recommendations,
)
from autonomous_agent_builder.runtime.factory import resolve_runtime_config
from autonomous_agent_builder.services.codex_optimization import summarize_runs_for_optimization
from autonomous_agent_builder.services.context_budget import summarize_context_budgets
from autonomous_agent_builder.services.provider_limits import (
    is_provider_limit_text,
    parse_reset_hint,
)
from autonomous_agent_builder.services.token_costing import estimate_run_cost


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




def _empty_recommendation_lifecycle() -> dict[str, Any]:
    return {
        "available": True,
        "applied": [],
        "rejected": [],
        "not_applicable": [],
        "deferred": [],
        "observed": [],
        "by_code": {},
        "counts": {
            "applied": 0,
            "rejected": 0,
            "not_applicable": 0,
            "deferred": 0,
            "observed": 0,
        },
    }


def _recommendation_lifecycle(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return persisted optimizer decisions keyed by recommendation code."""

    lifecycle = _empty_recommendation_lifecycle()
    if not _table_exists(conn, "agent_runs"):
        return {**lifecycle, "available": False, "reason": "agent_runs_missing"}
    columns = _table_columns(conn, "agent_runs")
    if "output_text" not in columns:
        return {**lifecycle, "available": False, "reason": "agent_run_output_missing"}

    select_parts = [
        "agent_name",
        _column_or_default(columns, "status", "''", "status"),
        _column_or_default(columns, "stop_reason", "''", "stop_reason"),
        _column_or_default(columns, "output_text", "''", "output_text"),
        _column_or_default(columns, "completed_at", "null", "completed_at"),
        _column_or_default(columns, "started_at", "null", "started_at"),
    ]
    rows = conn.execute(
        f"""
        select {", ".join(select_parts)}
        from agent_runs
        where agent_name = 'optimization-agent'
        order by coalesce(completed_at, started_at, '') asc
        """
    ).fetchall()
    for row in rows:
        item = _row_dict(row)
        payload = _maybe_json_dict(item.get("output_text"))
        if not payload:
            continue
        decided_at = str(item.get("completed_at") or item.get("started_at") or "")
        status = str(payload.get("status") or item.get("status") or "")
        if status in {"implemented", "completed"}:
            for code in _recommendation_codes(payload.get("selected_recommendation")):
                _record_recommendation_decision(
                    lifecycle,
                    code,
                    "applied",
                    "optimization agent selected and implemented this recommendation",
                    decided_at,
                    payload,
                )
            for code in _recommendation_codes(payload.get("selected_recommendations")):
                _record_recommendation_decision(
                    lifecycle,
                    code,
                    "applied",
                    "optimization agent selected and implemented this recommendation",
                    decided_at,
                    payload,
                )

        decision = payload.get("post_preflight_decision")
        if isinstance(decision, dict):
            for code in _recommendation_codes(decision.get("deterministic_actions_applied")):
                _record_recommendation_decision(
                    lifecycle,
                    code,
                    "applied",
                    str(decision.get("reason") or "deterministic preflight applied this action"),
                    decided_at,
                    payload,
                )
            for entry in _decision_entries(decision.get("recommendation_decisions")):
                code = str(entry.get("code") or "").strip()
                lifecycle_status = str(entry.get("lifecycle_status") or entry.get("status") or "")
                if not code or lifecycle_status not in {
                    "applied",
                    "rejected",
                    "not_applicable",
                    "deferred",
                    "observed",
                }:
                    continue
                _record_recommendation_decision(
                    lifecycle,
                    code,
                    lifecycle_status,
                    str(entry.get("reason") or decision.get("reason") or ""),
                    decided_at,
                    payload,
                )

        for entry in _decision_entries(payload.get("recommendation_decisions")):
            code = str(entry.get("code") or "").strip()
            lifecycle_status = str(entry.get("lifecycle_status") or entry.get("status") or "")
            if not code or lifecycle_status not in {
                "applied",
                "rejected",
                "not_applicable",
                "deferred",
                "observed",
            }:
                continue
            _record_recommendation_decision(
                lifecycle,
                code,
                lifecycle_status,
                str(entry.get("reason") or ""),
                decided_at,
                payload,
            )

        for key, lifecycle_status in (
            ("rejected_recommendations", "rejected"),
            ("not_applicable_recommendations", "not_applicable"),
            ("deferred_recommendations", "deferred"),
            ("observed_recommendations", "observed"),
        ):
            for entry in _decision_entries(payload.get(key)):
                code = str(entry.get("code") or "").strip()
                if not code:
                    continue
                _record_recommendation_decision(
                    lifecycle,
                    code,
                    lifecycle_status,
                    str(entry.get("reason") or ""),
                    decided_at,
                    payload,
                )

    for status_key in ("applied", "rejected", "not_applicable", "deferred", "observed"):
        lifecycle["counts"][status_key] = len(lifecycle[status_key])
    return lifecycle


def _decision_entries(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        return [raw]
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _recommendation_codes(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, dict):
        code = str(raw.get("code") or "").strip()
        return [code] if code else []
    if not isinstance(raw, list):
        return []
    codes: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            codes.append(item.strip())
        elif isinstance(item, dict) and str(item.get("code") or "").strip():
            codes.append(str(item.get("code")).strip())
    return codes


def _record_recommendation_decision(
    lifecycle: dict[str, Any],
    code: str,
    lifecycle_status: str,
    reason: str,
    decided_at: str,
    payload: dict[str, Any],
) -> None:
    code = code.strip()
    if not code:
        return
    priority = {
        "observed": 1,
        "deferred": 2,
        "not_applicable": 3,
        "rejected": 4,
        "applied": 5,
    }
    existing = lifecycle["by_code"].get(code)
    if existing and priority.get(str(existing.get("lifecycle_status")), 0) > priority.get(
        lifecycle_status, 0
    ):
        return
    decision = {
        "code": code,
        "lifecycle_status": lifecycle_status,
        "reason": reason,
        "decided_at": decided_at,
        "agent_name": str(payload.get("agent_name") or "optimization-agent"),
        "selected_recommendation": str(payload.get("selected_recommendation") or ""),
    }
    lifecycle["by_code"][code] = decision
    for status_key in ("applied", "rejected", "not_applicable", "deferred", "observed"):
        lifecycle[status_key] = [item for item in lifecycle[status_key] if item.get("code") != code]
    lifecycle[lifecycle_status].append(decision)


def _apply_recommendation_lifecycle(
    recommendations: list[dict[str, Any]],
    lifecycle: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_code = lifecycle.get("by_code") if isinstance(lifecycle, dict) else {}
    by_code = by_code if isinstance(by_code, dict) else {}
    build_verify_applied = (
        isinstance(by_code.get("script_candidate_build_verify_script"), dict)
        and by_code["script_candidate_build_verify_script"].get("lifecycle_status") == "applied"
    )
    open_items: list[dict[str, Any]] = []
    resolved_items: list[dict[str, Any]] = []
    for item in recommendations:
        code = str(item.get("code") or "")
        decision = by_code.get(code) if code else None
        if code == "script_candidate_command_sequence_wrapper" and build_verify_applied:
            resolved_items.append(
                {
                    **item,
                    "lifecycle_status": "applied",
                    "decision_reason": (
                        "covered by builder script run build_verify for repeated setup, lint, "
                        "test, build, and app-smoke evidence"
                    ),
                }
            )
            continue
        if isinstance(decision, dict):
            enriched = {
                **item,
                "lifecycle_status": str(decision.get("lifecycle_status") or "resolved"),
                "decision_reason": str(decision.get("reason") or ""),
                "decided_at": str(decision.get("decided_at") or ""),
            }
            resolved_items.append(enriched)
            continue
        if _is_historical_info_recommendation(item):
            resolved_items.append(
                {
                    **item,
                    "lifecycle_status": "observed",
                    "decision_reason": "historical runtime signal; no current operator action required",
                }
            )
            continue
        lifecycle_status = str(item.get("lifecycle_status") or "open")
        if lifecycle_status in {"applied", "observed", "not_applicable", "rejected", "deferred"}:
            resolved_items.append(
                {
                    **item,
                    "lifecycle_status": lifecycle_status,
                    "decision_reason": item.get("decision_reason")
                    or "deterministic telemetry lifecycle verified this status",
                }
            )
            continue
        open_items.append({**item, "lifecycle_status": "open"})
    if not open_items:
        open_items.append(
            _deterministic_recommendation(
                code="deterministic_baseline_ready",
                severity="info",
                trigger="no open deterministic recommendation thresholds crossed",
                recommendation="Continue collecting structured run evidence.",
                next_action="continue_collecting_structured_builder_db_events",
                evidence={},
            )
        )
    return open_items, resolved_items


def _open_script_candidates(
    candidates: list[Any],
    recommendations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    open_codes = {
        str(item.get("code") or "")
        for item in recommendations
        if isinstance(item, dict) and str(item.get("code") or "").startswith("script_candidate_")
    }
    return [
        dict(candidate)
        for candidate in candidates
        if isinstance(candidate, dict)
        and f"script_candidate_{candidate.get('code') or ''}" in open_codes
    ]


def _is_historical_info_recommendation(item: dict[str, Any]) -> bool:
    code = str(item.get("code") or "")
    return code in {"runtime_switch_preserve_history", "runtime_resume_recovered"}


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
    where = """
            event_type in ('tool_error', 'run_error')
               or (event_type = 'voice_tool_output' and status = 'failed')
            """
    total_count = int(
        conn.execute(f"select count(*) from chat_events where {where}").fetchone()[0] or 0
    )
    rows = [
        _row_dict(row)
        for row in conn.execute(
            f"""
            select {", ".join(select)}
            from chat_events
            where {where}
            order by created_at desc
            limit 250
            """
        ).fetchall()
    ]
    recent: list[dict[str, Any]] = []
    active_recent: list[dict[str, Any]] = []
    resolved_count = 0
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
            item["resolved"] = True
        else:
            active_recent.append(item)
        recent.append(item)
    active_count = max(total_count - resolved_count, 0)
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


def _provider_payload(depends_on: Any) -> dict[str, Any]:
    parsed = _maybe_json_dict(depends_on)
    provider = parsed.get("provider_limit")
    return provider if isinstance(provider, dict) else {}


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


def _column_or_default(columns: set[str], column: str, default: str, alias: str) -> str:
    return f"{column} as {alias}" if column in columns else f"{default} as {alias}"


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
