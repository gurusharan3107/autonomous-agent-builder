"""Recommendation lifecycle tracking extracted from observability summary."""

from __future__ import annotations

import sqlite3
from typing import Any

from autonomous_agent_builder.observability.recommendation_outcome import (
    compute_outcome,
    metric_for_code,
)
from autonomous_agent_builder.observability.summary_db import (
    _column_or_default,
    _maybe_json_dict,
    _row_dict,
    _table_columns,
    _table_exists,
    _window_token_totals,
)
from autonomous_agent_builder.observability.summary_recommendations import (
    _deterministic_recommendation,
)


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

    # --- Loop-4 outcome attribution (Design A: read-time, applied records only) ---
    # Collect all era-boundary timestamps from every decision in by_code, sorted.
    all_decided_ats: list[str] = sorted(
        {
            str(rec.get("decided_at") or "")
            for rec in lifecycle["by_code"].values()
            if str(rec.get("decided_at") or "")
        }
    )
    for record in lifecycle["applied"]:
        decided_at = str(record.get("decided_at") or "")
        code = str(record.get("code") or "")
        metric = metric_for_code(code)

        if not decided_at:
            record["outcome"] = {
                "verdict": "insufficient_data",
                "metric": metric,
            }
            continue

        # Determine era boundaries around this decided_at.
        try:
            idx = all_decided_ats.index(decided_at)
        except ValueError:
            idx = 0

        before_boundary: str | None = all_decided_ats[idx - 1] if idx > 0 else None
        after_boundary: str | None = (
            all_decided_ats[idx + 1] if idx + 1 < len(all_decided_ats) else None
        )

        if metric is None:
            record["outcome"] = {"verdict": "not_measurable", "metric": None}
            continue

        # Query token windows using the already-open connection.
        before_window = _window_token_totals(
            conn,
            start_iso=before_boundary,
            end_iso=decided_at,
        )
        after_window = _window_token_totals(
            conn,
            start_iso=decided_at,
            end_iso=after_boundary,
        )
        record["outcome"] = compute_outcome(
            before_window["tokens"],
            after_window["tokens"],
            before_window["runs"],
            after_window["runs"],
        )
    # Sync by_code references (by_code and applied share the same dict objects).

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
        "outcome": None,
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
