"""Read-only observability context for Agent chat turns."""

from __future__ import annotations

import json
import re
from pathlib import Path

from autonomous_agent_builder.observability.summary import dashboard_observability_summary

OBSERVABILITY_BOUNDED_RETRIEVAL_SHORTCUT = (
    "Bounded retrieval shortcut: prefer compact Builder JSON commands. Start with "
    "`builder metrics show --json` and "
    "`builder logs --error --json`; use `builder logs --info --compact --json` for "
    "status context, and analyze only one selected run with "
    "`builder logs analyze --session <id-or-prefix> --json`. Avoid raw or --full "
    "outputs unless this compact evidence is insufficient."
)
OBSERVABILITY_ANALYSIS_SCOPE_TOKENS = {
    "metric",
    "metrics",
    "observability",
    "signal",
    "signals",
    "telemetry",
}
OBSERVABILITY_ANALYSIS_ACTION_TOKENS = {
    "analyze",
    "data",
    "fix",
    "next",
    "recommend",
    "recommendation",
    "recommendations",
    "should",
    "tell",
}


def normalize_observability_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def message_requests_observability_analysis(user_message: str) -> bool:
    normalized = " ".join(user_message.lower().replace("?", " ").split())
    if not normalized:
        return False
    tokens = set(normalize_observability_token(normalized).split())
    return bool(tokens & OBSERVABILITY_ANALYSIS_SCOPE_TOKENS) and bool(
        tokens & OBSERVABILITY_ANALYSIS_ACTION_TOKENS
    )


def observability_context_for_prompt(project_root: Path, user_message: str) -> str:
    if not message_requests_observability_analysis(user_message):
        return ""
    try:
        db_path = project_root / ".agent-builder" / "agent_builder.db"
        summary = dashboard_observability_summary(db_path)
        coverage = summary.get("observability_coverage", {})
        runtime = summary.get("runtime", {})
        aggregates = coverage.get("aggregates", {})
        telemetry_health = coverage.get("telemetry_health", {})

        compact = {
            "selected_runtime": runtime.get("selected_runtime_sdk"),
            "coverage_source": coverage.get("source"),
            "missing_signals": list(coverage.get("missing_signals") or [])[:5],
            "next": coverage.get("next"),
            "telemetry_health": {
                key: {
                    "status": value.get("status"),
                    "collector_status": value.get("collector_status"),
                }
                for key, value in telemetry_health.items()
                if isinstance(value, dict)
                and key in {"claude_native", "codex_native", "builder_product"}
            },
            "optimization": {
                "raw_token_total": aggregates.get("raw_token_total"),
                "cache_ratio": aggregates.get("cache_ratio"),
                "chunk_pressure": aggregates.get("chunk_pressure"),
                "avoidable_cost_flags": list(aggregates.get("avoidable_cost_flags") or [])[:5],
                "top_cost_drivers": [
                    {
                        "agent_name": item.get("agent_name"),
                        "runs": item.get("runs"),
                        "raw_tokens": item.get("raw_tokens"),
                        "avoidable_token_estimate": item.get("avoidable_token_estimate"),
                    }
                    for item in list(aggregates.get("top_cost_drivers") or [])[:5]
                    if isinstance(item, dict)
                ],
            },
            "deterministic_recommendations": [
                {
                    "code": item.get("code"),
                    "severity": item.get("severity"),
                    "next_action": item.get("next_action"),
                    "lifecycle_status": item.get("lifecycle_status"),
                }
                for item in list(coverage.get("deterministic_recommendations") or [])[:5]
                if isinstance(item, dict)
            ],
        }
        rendered = json.dumps(compact, ensure_ascii=True, sort_keys=True)
        if len(rendered) > 5000:
            rendered = rendered[:5000] + "...[truncated]"
        return (
            "Builder observability context pack already retrieved for this turn. "
            "Use this bounded evidence first, then analyze the operator's intent. "
            f"{OBSERVABILITY_BOUNDED_RETRIEVAL_SHORTCUT}\n"
            f"{rendered}"
        )
    except Exception as exc:
        return (
            "Builder observability context pack could not be retrieved before the model turn. "
            f"Error: {type(exc).__name__}: {exc}"
        )
