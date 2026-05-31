"""Shared prompt timeline analysis for Builder chat evidence."""

from __future__ import annotations

import json
from typing import Any

from autonomous_agent_builder.logs.diagnostics import summarize_chat_event

# A single chat prompt can emit several run_status events: an initial
# running marker (zeros), the real model-run total, then deterministic
# continuation / dispatch / terminal markers that also carry zeros
# (delivery-permission handling, sprint planning, task_dispatched). Streaming
# partial usage is never persisted as a run_status event, so every persisted
# run_status holds a complete per-invocation total. Overwriting telemetry with
# the last run_status therefore lets a trailing zero marker clobber the real
# cost/token totals and blank the analyze headline (IMP-023). Sum the additive
# fields across a prompt's run_status events; keep last-non-empty for status
# scalars.
_ADDITIVE_TELEMETRY_FIELDS = (
    "tokens_used",
    "tokens_input",
    "tokens_output",
    "tokens_cached",
    "raw_tokens",
    "noncached_plus_output_tokens",
    "cost_usd",
    "duration_ms",
)
_STATUS_TELEMETRY_FIELDS = (
    "running",
    "current_turn",
    "max_turns",
    "stop_reason",
    "sdk_session_id",
    "error",
    "dispatch",
)


def _merge_run_status_telemetry(
    existing: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(existing)
    for key in _ADDITIVE_TELEMETRY_FIELDS:
        value = payload.get(key)
        if value in ("", None):
            continue
        merged[key] = (merged.get(key) or 0) + value
    for key in _STATUS_TELEMETRY_FIELDS:
        value = payload.get(key)
        if value in ("", None):
            continue
        merged[key] = value
    return merged


def build_timeline_prompts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build per-prompt analysis records from persisted chat timeline events."""
    prompts: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for item in items:
        payload = item.get("payload", {})
        if not isinstance(payload, dict):
            payload = {"content": str(payload)}
        event_type = str(item.get("event_type", ""))
        if event_type == "user_message":
            if current is not None:
                current["context_efficiency"] = context_signal(current)
                prompts.append(current)
            current = {
                "index": len(prompts) + 1,
                "user_prompt": text_preview(payload.get("content"), limit=260),
                "started_at": item.get("created_at"),
                "tools": [],
                "assistant_response": "",
                "telemetry": {},
            }
            continue
        if current is None:
            continue
        if event_type == "assistant_message":
            current["assistant_response"] = text_preview(payload.get("content"), limit=360)
            continue
        if event_type == "run_status":
            diagnostic = summarize_chat_event(event_type, payload)
            current["telemetry"] = _merge_run_status_telemetry(
                current.get("telemetry") or {}, payload
            )
            snapshot = payload.get("observability")
            if isinstance(snapshot, dict) and snapshot:
                current["observability"] = snapshot
            if diagnostic.get("outcome") == "error":
                current.setdefault("risks", []).append("run_error")
            continue
        if event_type == "context_budget":
            current["context_budget"] = {
                key: payload.get(key)
                for key in (
                    "lane",
                    "stage",
                    "runtime_sdk",
                    "provider",
                    "model",
                    "effort",
                    "total_estimated_tokens",
                    "signal_category",
                    "signal_value",
                    "privacy_policy",
                )
                if payload.get(key) not in ("", None)
            }
            components = payload.get("components")
            if isinstance(components, list):
                current["context_budget"]["components"] = [
                    {
                        key: item.get(key)
                        for key in (
                            "name",
                            "estimated_tokens",
                            "signal_category",
                            "source",
                            "present",
                        )
                        if isinstance(item, dict) and item.get(key) not in ("", None)
                    }
                    for item in components[:8]
                    if isinstance(item, dict)
                ]
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
            dispatch_payload = extract_text_json(str(payload.get("content", "")))
            dispatch = {
                key: dispatch_payload.get(key)
                for key in ("task_id", "status", "current_status")
                if dispatch_payload.get(key) not in ("", None)
            }
            if dispatch:
                tool["dispatch"] = dispatch
        current["tools"].append(tool)

    if current is not None:
        current["context_efficiency"] = context_signal(current)
        prompts.append(current)
    return prompts


def text_preview(value: Any, *, limit: int = 220) -> str:
    text = str(value or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def extract_text_json(value: Any) -> dict[str, Any]:
    text = str(value or "").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def context_signal(segment: dict[str, Any]) -> dict[str, Any]:
    user_prompt = str(segment.get("user_prompt", "")).lower()
    tool_names = [str(tool.get("tool_name", "")) for tool in segment.get("tools", [])]
    signals: list[str] = []

    if any(tool == "Glob" for tool in tool_names):
        signals.append("broad_file_discovery")
    if any(tool == "Read" for tool in tool_names) and any(
        "which project" in user_prompt for _ in [0]
    ):
        signals.append("file_read_for_identity_question")
    if any(tool == "Agent" for tool in tool_names):
        signals.append("delegated_subagent")
    if any(tool.startswith("mcp__builder__kb_") for tool in tool_names):
        signals.append("used_builder_knowledge")
    if "backlog" in user_prompt and not any(
        tool.startswith("mcp__builder__backlog") or tool.startswith("builder backlog")
        for tool in tool_names
    ):
        signals.append("backlog_not_checked_through_backlog_surface")

    if not tool_names:
        grade = "minimal"
    elif signals:
        grade = "review"
    else:
        grade = "targeted"
    return {"grade": grade, "signals": signals}
