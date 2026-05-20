"""Bounded dashboard payload serializers shared by API and embedded routes."""

from __future__ import annotations

from typing import Any

_GENERATED_DIFF_PATH_PARTS = ("/node_modules/", "/dist/", "/build/")
_EXCLUDED_METRICS_KEYS = {
    "preview",
    "raw",
    "raw_response",
    "full_output",
    "stdout",
    "stderr",
}


def _int_value(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _first_int(*values: Any) -> int:
    for value in values:
        number = _int_value(value)
        if number:
            return number
    return 0


def chat_status_token_usage(payload: dict[str, Any]) -> dict[str, int]:
    """Normalize Agent-page chat run usage from status payloads.

    New run_status events carry explicit token fields. Older events only have
    tokens_used, and Codex-backed events may also carry native usage under the
    observability optimization summary. This keeps metrics cache-aware without
    making old sessions disappear from totals.
    """

    observability = payload.get("observability") if isinstance(payload.get("observability"), dict) else {}
    optimization = (
        observability.get("optimization_summary")
        if isinstance(observability.get("optimization_summary"), dict)
        else {}
    )
    accounting = (
        optimization.get("token_accounting")
        if isinstance(optimization.get("token_accounting"), dict)
        else {}
    )
    input_tokens = _first_int(
        payload.get("tokens_input"),
        accounting.get("input_tokens"),
        observability.get("input_tokens"),
    )
    output_tokens = _first_int(
        payload.get("tokens_output"),
        accounting.get("output_tokens"),
        observability.get("output_tokens"),
    )
    cached_tokens = min(
        _first_int(
            payload.get("tokens_cached"),
            accounting.get("cached_input_tokens"),
            observability.get("cached_input_tokens"),
        ),
        input_tokens,
    )
    raw_tokens = _first_int(
        payload.get("raw_tokens"),
        accounting.get("raw_total_tokens"),
        observability.get("total_tokens"),
        payload.get("tokens_used"),
        input_tokens + output_tokens,
    )
    if input_tokens == 0 and output_tokens == 0 and raw_tokens:
        output_tokens = raw_tokens
    return {
        "tokens_input": input_tokens,
        "tokens_output": output_tokens,
        "tokens_cached": cached_tokens,
        "tokens_used": input_tokens + output_tokens,
        "raw_tokens": raw_tokens or input_tokens + output_tokens,
        "noncached_plus_output_tokens": _first_int(
            payload.get("noncached_plus_output_tokens"),
            accounting.get("noncached_plus_output_tokens"),
            max(input_tokens - cached_tokens, 0) + output_tokens,
        ),
    }


def is_generated_diff_path(path: str) -> bool:
    normalized_path = path.replace("\\", "/").lstrip("./")
    normalized = f"/{normalized_path}"
    return any(part in normalized for part in _GENERATED_DIFF_PATH_PARTS)


def bounded_metrics_value(value: Any, *, list_limit: int = 50, depth: int = 0) -> Any:
    if depth > 8:
        return "<nested-payload-omitted>"
    if isinstance(value, str):
        return "<generated-artifact-path-omitted>" if is_generated_diff_path(value) else value
    if isinstance(value, dict):
        bounded: dict[str, Any] = {}
        for key, item in value.items():
            if key in _EXCLUDED_METRICS_KEYS:
                continue
            if isinstance(item, str) and is_generated_diff_path(item):
                continue
            bounded[key] = bounded_metrics_value(item, list_limit=list_limit, depth=depth + 1)
        return bounded
    if isinstance(value, list):
        source_items = [
            item for item in value if not (isinstance(item, str) and is_generated_diff_path(item))
        ]
        items = [
            bounded_metrics_value(item, list_limit=list_limit, depth=depth + 1)
            for item in source_items[:list_limit]
        ]
        if len(source_items) > list_limit:
            items.append({"omitted_items": len(source_items) - list_limit})
        return items
    return value


def bounded_diff_summary(diff_summary: dict | None, *, limit: int = 50) -> dict | None:
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
            if path and is_generated_diff_path(path):
                omitted_generated += 1
                continue
            kept.append(bounded_metrics_value(item, depth=1))
        if len(kept) > limit:
            kept = kept[:limit]
            truncated = True
        sanitized[key] = kept
    if omitted_generated:
        sanitized["bounded"] = True
        sanitized["omitted_generated_paths"] = omitted_generated
    if truncated:
        sanitized["truncated"] = True
        sanitized["bounded"] = True
    if omitted_generated or truncated:
        sanitized["note"] = (
            "Generated dependency/build artifact paths are omitted from metrics output."
        )
    return sanitized
