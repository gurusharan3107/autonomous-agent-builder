"""Metrics command — bounded verification and cost state."""

from __future__ import annotations

import sys
from typing import Any

import typer

from autonomous_agent_builder.cli.client import (
    EXIT_SUCCESS,
    AabApiError,
    BuilderConnectivityError,
    get_client,
    handle_api_error,
    request_json,
)
from autonomous_agent_builder.cli.local_fallback import load_local_metrics
from autonomous_agent_builder.cli.output import render, table
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.observability.runtime_optimization import (
    optimization_decision_summary,
)
from autonomous_agent_builder.runtime.factory import resolve_runtime_config

app = typer.Typer(
    help=(
        "Cost and performance metrics.\n\n"
        "Start here:\n"
        "  builder metrics show --json\n"
        "  builder backlog run summary <query> --json\n"
        "  builder backlog task status <task-id> --json\n"
    )
)


def _run_analysis_id(run: dict) -> str:
    if str(run.get("agent_name") or "") == "agent-chat" and run.get("task_id"):
        return str(run.get("task_id") or "")
    return str(run.get("session_id") or run.get("id") or run.get("run_id") or "")


def _compact_run(run: dict) -> dict:
    analysis_id = _run_analysis_id(run)
    return {
        "analysis_id": analysis_id,
        "analysis_command": (
            f"builder logs analyze --session {analysis_id} --json"
            if analysis_id
            else "builder metrics show --json --full --limit 10"
        ),
        "agent_name": run.get("agent_name", ""),
        "status": run.get("status", ""),
        "cost_usd": run.get("cost_usd", 0),
        "tokens": run.get("tokens_input", 0) + run.get("tokens_output", 0),
        "duration_ms": run.get("duration_ms", 0),
        "model": run.get("model") or run.get("model_name") or "",
    }


def _metrics_analysis_command(runs: list[Any]) -> str:
    for run in runs:
        if not isinstance(run, dict):
            continue
        analysis_id = _run_analysis_id(run)
        if analysis_id:
            return f"builder logs analyze --session {analysis_id} --json"
    return "builder metrics show --json --full --limit 10"


_GENERATED_PATH_PARTS = ("/node_modules/", "/dist/", "/build/")
_EXCLUDED_METRICS_KEYS = {
    "preview",
    "raw",
    "raw_response",
    "full_output",
    "stdout",
    "stderr",
}


def _is_generated_path(path: str) -> bool:
    normalized_path = path.replace("\\", "/").lstrip("./")
    normalized = f"/{normalized_path}"
    return any(part in normalized for part in _GENERATED_PATH_PARTS)


def _bounded_value(value: Any, *, list_limit: int = 50, depth: int = 0) -> Any:
    if depth > 8:
        return "<nested-payload-omitted>"
    if isinstance(value, str):
        return "<generated-artifact-path-omitted>" if _is_generated_path(value) else value
    if isinstance(value, dict):
        bounded: dict[str, Any] = {}
        for key, item in value.items():
            if key in _EXCLUDED_METRICS_KEYS:
                continue
            if isinstance(item, str) and _is_generated_path(item):
                continue
            bounded[key] = _bounded_value(item, list_limit=list_limit, depth=depth + 1)
        return bounded
    if isinstance(value, list):
        source_items = [
            item for item in value if not (isinstance(item, str) and _is_generated_path(item))
        ]
        items = [
            _bounded_value(item, list_limit=list_limit, depth=depth + 1)
            for item in source_items[:list_limit]
        ]
        if len(source_items) > list_limit:
            items.append({"omitted_items": len(source_items) - list_limit})
        return items
    return value


def _bounded_diff_summary(diff_summary: Any, *, limit: int = 50) -> Any:
    if not isinstance(diff_summary, dict):
        return diff_summary
    sanitized = dict(diff_summary)
    omitted_generated = 0
    truncated = False
    for key in ("files", "hunks"):
        items = diff_summary.get(key)
        if not isinstance(items, list):
            continue
        kept: list[Any] = []
        for item in items:
            path = ""
            if isinstance(item, dict):
                path = str(item.get("path") or item.get("old_path") or item.get("file") or "")
            if path and _is_generated_path(path):
                omitted_generated += 1
                continue
            kept.append(_bounded_value(item, depth=1))
        if len(kept) > limit:
            kept = kept[:limit]
            truncated = True
        sanitized[key] = kept
    if omitted_generated or truncated:
        sanitized["bounded"] = True
        sanitized["omitted_generated_paths"] = omitted_generated
        sanitized["truncated"] = truncated
        sanitized["note"] = (
            "Generated dependency/build artifact paths are omitted from metrics output."
        )
    return sanitized


def _bounded_run_payload(run: Any) -> Any:
    if not isinstance(run, dict):
        return run
    bounded = dict(run)
    if "diff_summary" in bounded:
        bounded["diff_summary"] = _bounded_diff_summary(bounded.get("diff_summary"))
    if "observability" in bounded:
        bounded["observability"] = _bounded_value(bounded.get("observability"))
    return bounded


def _bound_metrics_payload(payload: dict, *, run_limit: int | None = None) -> dict:
    bounded = dict(payload)
    runs = bounded.get("runs")
    if isinstance(runs, list):
        selected_runs = runs[:run_limit] if run_limit is not None else runs
        bounded["runs"] = [_bounded_run_payload(run) for run in selected_runs]
        if run_limit is not None:
            bounded["run_count"] = len(runs)
            bounded["runs_returned"] = len(selected_runs)
            if len(runs) > len(selected_runs):
                bounded["truncated"] = True
                bounded["next_step"] = f"builder metrics show --json --full --limit {len(runs)}"
    return bounded


def _compact_voice_ledger(ledger: dict) -> dict:
    if not isinstance(ledger, dict):
        return {}
    totals = ledger.get("totals") if isinstance(ledger.get("totals"), dict) else {}
    tool_outputs = (
        ledger.get("tool_outputs") if isinstance(ledger.get("tool_outputs"), list) else []
    )
    failed_outputs = [item for item in tool_outputs if item.get("ok") is False]
    return {
        "totals": {
            "responses": totals.get("responses", 0),
            "total_tokens": totals.get("total_tokens", 0),
            "input_text_tokens": totals.get("input_text_tokens", 0),
            "input_audio_tokens": totals.get("input_audio_tokens", 0),
            "output_text_tokens": totals.get("output_text_tokens", 0),
            "output_audio_tokens": totals.get("output_audio_tokens", 0),
            "cached_tokens": totals.get("cached_tokens", 0),
            "estimated_cost_usd": totals.get("estimated_cost_usd"),
            "cost_source": totals.get("cost_source", ""),
            "delegated_messages": totals.get("delegated_messages", 0),
            "voice_digests": totals.get("voice_digests", 0),
            "tool_calls": totals.get("tool_calls", 0),
            "tool_outputs": totals.get("tool_outputs", 0),
            "failed_tool_outputs": totals.get("failed_tool_outputs", len(failed_outputs)),
            "wait_events": totals.get("wait_events", 0),
            "prepared_actions": totals.get("prepared_actions", 0),
            "confirmed_actions": totals.get("confirmed_actions", 0),
            "delegation_ratio": totals.get("delegation_ratio", 0.0),
        },
        "recent_failures": [
            {
                "tool_name": item.get("tool_name", ""),
                "tool_call_id": item.get("tool_call_id", ""),
                "error": item.get("error", ""),
                "event_id": item.get("event_id", ""),
            }
            for item in failed_outputs[:5]
        ],
        "raw_evidence": {
            "command": "builder metrics show --json --full",
            "contains": ["voice_usage", "voice_tool_call", "voice_tool_output", "voice_digest"],
        },
    }


def _selected_runtime_sdk() -> str:
    try:
        config = resolve_runtime_config(get_settings())
    except Exception:
        return "claude_agent_sdk"
    sdk = str(config.get("sdk") or "claude")
    return "codex_sdk" if sdk.startswith("codex") else "claude_agent_sdk"


def _ensure_optimization_decision(payload: dict) -> None:
    if isinstance(payload.get("optimization_decision"), dict) and payload["optimization_decision"]:
        return
    optimization = (
        payload.get("optimization_summary")
        if isinstance(payload.get("optimization_summary"), dict)
        else {}
    )
    top_drivers = optimization.get("top_cost_drivers") if isinstance(optimization, dict) else []
    aggregates = {
        "by_agent": top_drivers if isinstance(top_drivers, list) else [],
        "tool_observability": {"tool_counts": []},
    }
    payload["optimization_decision"] = optimization_decision_summary(
        _selected_runtime_sdk(),
        aggregates=aggregates,
        optimization=optimization,
    )


def _compact_optimization_summary(summary: Any) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    drivers = (
        summary.get("top_cost_drivers") if isinstance(summary.get("top_cost_drivers"), list) else []
    )
    return {
        "primary_score": summary.get("primary_score", ""),
        "raw_token_total": summary.get("raw_token_total", 0),
        "noncached_plus_output_tokens": summary.get("noncached_plus_output_tokens", 0),
        "cached_tokens": summary.get("cached_tokens", 0),
        "active_raw_token_total": summary.get("active_raw_token_total", 0),
        "active_noncached_plus_output_tokens": summary.get(
            "active_noncached_plus_output_tokens", 0
        ),
        "active_cached_tokens": summary.get("active_cached_tokens", 0),
        "cache_ratio": summary.get("cache_ratio", 0),
        "avoidable_token_estimate": summary.get("avoidable_token_estimate", 0),
        "avoidable_cost_flags": summary.get("avoidable_cost_flags", []),
        "active_avoidable_cost_flags": summary.get("active_avoidable_cost_flags", []),
        "chunk_pressure": summary.get("chunk_pressure", {}),
        "top_cost_drivers": [
            {
                "agent_name": driver.get("agent_name", ""),
                "runs": driver.get("runs", 0),
                "raw_tokens": driver.get("raw_tokens", 0),
                "noncached_plus_output_tokens": driver.get(
                    "noncached_plus_output_tokens", 0
                ),
                "cached_tokens": driver.get("cached_tokens", 0),
                "avoidable_token_estimate": driver.get("avoidable_token_estimate", 0),
            }
            for driver in drivers[:3]
            if isinstance(driver, dict)
        ],
        "active_top_cost_drivers": [
            {
                "agent_name": driver.get("agent_name", ""),
                "runs": driver.get("runs", 0),
                "raw_tokens": driver.get("raw_tokens", 0),
                "noncached_plus_output_tokens": driver.get(
                    "noncached_plus_output_tokens", 0
                ),
                "cached_tokens": driver.get("cached_tokens", 0),
                "avoidable_token_estimate": driver.get("avoidable_token_estimate", 0),
            }
            for driver in (
                summary.get("active_top_cost_drivers")
                if isinstance(summary.get("active_top_cost_drivers"), list)
                else []
            )[:3]
            if isinstance(driver, dict)
        ],
        "benchmark": summary.get("benchmark", {}),
        "recommended_next_change": summary.get("recommended_next_change", ""),
    }


def _compact_context_budget(summary: Any) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    return {
        "available": bool(summary.get("available")),
        "event_count": int(summary.get("event_count") or 0),
        "total_estimated_tokens": int(summary.get("total_estimated_tokens") or 0),
        "by_lane": list(summary.get("by_lane") or [])[:4],
        "signal_counts": list(summary.get("signal_counts") or [])[:5],
        "top_components": list(summary.get("top_components") or [])[:5],
        "latest": summary.get("latest", {}) if isinstance(summary.get("latest"), dict) else {},
    }


def _compact_optimization_decision(decision: Any) -> dict[str, Any]:
    if not isinstance(decision, dict):
        return {}
    candidates = (
        decision.get("deterministic_script_candidates")
        if isinstance(decision.get("deterministic_script_candidates"), list)
        else []
    )
    return {
        "runtime": decision.get("runtime", ""),
        "next_action": decision.get("next_action", ""),
        "target_area": decision.get("target_area", ""),
        "reason": decision.get("reason", ""),
        "top_driver": {
            "agent_name": (decision.get("top_driver") or {}).get("agent_name", "")
            if isinstance(decision.get("top_driver"), dict)
            else "",
            "avoidable_token_estimate": (decision.get("top_driver") or {}).get(
                "avoidable_token_estimate", 0
            )
            if isinstance(decision.get("top_driver"), dict)
            else 0,
        },
        "deterministic_script_candidates": [
            {
                "code": candidate.get("code", ""),
                "severity": candidate.get("severity", ""),
                "status": candidate.get("status", ""),
                "command": candidate.get("command", ""),
                "owner_lane": candidate.get("owner_lane", ""),
                "next_actor": candidate.get("next_actor", ""),
            }
            for candidate in candidates[:3]
            if isinstance(candidate, dict)
        ],
        "model_effort_action": decision.get("model_effort_action", ""),
        "subagent_action": decision.get("subagent_action", ""),
    }


def _compact_script_candidates(candidates: Any) -> list[dict[str, Any]]:
    if not isinstance(candidates, list):
        return []
    return [
        {
            "code": candidate.get("code", ""),
            "severity": candidate.get("severity", ""),
            "status": candidate.get("status", ""),
            "command": candidate.get("command", ""),
            "owner_lane": candidate.get("owner_lane", ""),
            "next_actor": candidate.get("next_actor", ""),
            "estimated_savings_tokens": candidate.get("estimated_savings_tokens", 0),
        }
        for candidate in candidates[:3]
        if isinstance(candidate, dict)
    ]


def _compact_runtime_decision_summary(summary: Any) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    return {
        "runtime": summary.get("runtime", ""),
        "capability_gaps": summary.get("capability_gaps", []),
        "native_capability_count": summary.get("native_capability_count", 0),
        "fallback_capability_count": summary.get("fallback_capability_count", 0),
        "deterministic_script_candidates": _compact_script_candidates(
            summary.get("deterministic_script_candidates")
        ),
        "next": summary.get("next", ""),
    }


def _metrics_progressive_disclosure(runs: list[Any]) -> list[dict[str, str]]:
    analysis_command = _metrics_analysis_command(runs)
    return [
        {
            "when": "inspect prompt-level evidence for the latest run/session",
            "command": analysis_command,
        },
        {
            "when": "inspect bounded raw run payloads and observability fields",
            "command": "builder metrics show --json --full --limit 10",
        },
    ]


@app.command("show")
def show(
    full: bool = typer.Option(False, "--full", help="Include bounded run payloads in JSON output."),
    limit: int = typer.Option(
        10,
        "--limit",
        help="Limit runs included with --full; increase deliberately for historical sweeps.",
    ),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show project metrics — cost, tokens, runs, gate pass rate."""
    client = get_client(use_json=json)
    try:
        try:
            data = request_json(client, "GET", "/dashboard/metrics")
        except BuilderConnectivityError as exc:
            data = load_local_metrics()
            if isinstance(data, dict):
                data.setdefault("fallback_reason", exc.reason)
                data.setdefault("fallback_base_url", exc.base_url)
    except AabApiError as e:
        handle_api_error(e, use_json=json)
    else:
        run_limit = max(limit, 1) if full else None
        payload = (
            _bound_metrics_payload(dict(data), run_limit=run_limit)
            if isinstance(data, dict)
            else {"raw": data}
        )
        _ensure_optimization_decision(payload)
        payload.setdefault(
            "summary",
            {
                "total_cost": payload.get("total_cost", 0),
                "total_tokens": payload.get("total_tokens", 0),
                "total_runs": payload.get("total_runs", 0),
                "gate_pass_rate": payload.get("gate_pass_rate", 0),
            },
        )
        payload.setdefault("next_step", "builder backlog run summary <query> --json")
        if json and "voice_ledger" in payload:
            payload["voice_ledger"] = _compact_voice_ledger(payload["voice_ledger"])
        if json and "context_budget" in payload:
            payload["context_budget"] = _compact_context_budget(payload["context_budget"])
        if json and not full:
            runs = payload.get("runs", [])
            compact_payload = {
                key: value
                for key, value in payload.items()
                if key
                not in {
                    "runs",
                    "raw",
                    "total_cost",
                    "total_estimated_cost_usd",
                    "total_estimated_codex_credits",
                    "total_tokens",
                    "total_runs",
                    "gate_pass_rate",
                }
            }
            compact_payload["run_count"] = len(runs) if isinstance(runs, list) else 0
            compact_payload["recent_runs"] = (
                [_compact_run(run) for run in runs[:3]] if isinstance(runs, list) else []
            )
            compact_payload["optimization_summary"] = _compact_optimization_summary(
                compact_payload.get("optimization_summary")
            )
            compact_payload["optimization_decision"] = _compact_optimization_decision(
                compact_payload.get("optimization_decision")
            )
            compact_payload["runtime_decision_summary"] = _compact_runtime_decision_summary(
                compact_payload.get("runtime_decision_summary")
            )
            compact_payload["deterministic_script_candidates"] = _compact_script_candidates(
                compact_payload.get("deterministic_script_candidates")
            )
            compact_payload["next_step"] = _metrics_analysis_command(
                runs if isinstance(runs, list) else []
            )
            compact_payload["actionable_next"] = compact_payload["next_step"]
            compact_payload["progressive_disclosure"] = _metrics_progressive_disclosure(
                runs if isinstance(runs, list) else []
            )
            compact_payload["raw_evidence"] = {
                "available": isinstance(runs, list) and len(runs) > 0,
                "command": "builder metrics show --json --full --limit 10",
                "contains": ["runs", "observability", "token fields", "model", "effort"],
            }
            payload = compact_payload

        def fmt(d: dict) -> str:
            lines = [
                "--- METRICS ---",
                f"total_cost:      ${d.get('total_cost', 0):.2f}",
                f"total_tokens:    {d.get('total_tokens', 0):,}",
                f"total_runs:      {d.get('total_runs', 0)}",
                f"gate_pass_rate:  {d.get('gate_pass_rate', 0):.1%}",
            ]
            runs = d.get("runs", [])
            if runs:
                lines.append(f"\n--- RECENT RUNS ({min(len(runs), 5)}) ---")
                headers = ["AGENT", "COST", "TOKENS", "DURATION", "STATUS"]
                rows = [
                    [
                        r.get("agent_name", "")[:15],
                        f"${r.get('cost_usd', 0):.2f}",
                        str(r.get("tokens_input", 0) + r.get("tokens_output", 0)),
                        f"{r.get('duration_ms', 0)}ms",
                        r.get("status", ""),
                    ]
                    for r in runs[:5]
                ]
                lines.append(table(headers, rows))
            lines.append(f"\nNext: {d.get('next_step', '')}")
            return "\n".join(lines)

        render(payload, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
