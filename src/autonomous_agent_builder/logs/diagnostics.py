"""Compact diagnostic summaries for chat events and builder tool logs."""

from __future__ import annotations

import json
from typing import Any


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    except TypeError:
        return str(value).strip()


def _maybe_parse_json_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    trimmed = value.strip()
    if not trimmed or trimmed[0] not in "{[":
        return value
    try:
        return json.loads(trimmed)
    except json.JSONDecodeError:
        return value


def _shorten(text: str, limit: int = 180) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _truncate_multiline(text: str, limit: int = 1200) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _extract_error_message(value: Any) -> str:
    if isinstance(value, dict):
        nested_error = value.get("error")
        if isinstance(nested_error, dict):
            nested_message = _extract_error_message(nested_error)
            if nested_message:
                return nested_message
        for key in ("message", "detail", "summary", "error"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    text = _stringify(value)
    lowered = text.lower()
    if lowered.startswith("error:"):
        return text[6:].strip()
    return text


def _input_focus(tool_input: dict[str, Any]) -> str:
    preferred_keys = (
        "doc_id",
        "query",
        "doc_type",
        "title",
        "task_id",
        "feature_id",
        "kb_dir",
        "path",
        "command",
        "description",
    )
    parts: list[str] = []
    for key in preferred_keys:
        value = tool_input.get(key)
        text = _stringify(value)
        if text:
            parts.append(f"{key}={text}")
    if parts:
        return _shorten("; ".join(parts), 180)
    return ""


def summarize_tool_event(
    *,
    event_type: str,
    tool_name: str,
    tool_input: dict[str, Any] | None,
    tool_response: Any,
) -> dict[str, Any]:
    tool_input = tool_input or {}
    parsed_response = _maybe_parse_json_string(tool_response)
    response_text = _truncate_multiline(_stringify(parsed_response), 4000)
    focus = _input_focus(tool_input)
    outcome = "error" if event_type == "tool_error" else "ok"
    summary = ""
    detail = ""
    error_message = ""
    next_action = ""

    if event_type == "tool_error":
        error_code = ""
        if isinstance(parsed_response, dict):
            nested_error = parsed_response.get("error")
            if isinstance(nested_error, dict):
                error_code = _stringify(nested_error.get("code")).lower()
                hint = _stringify(nested_error.get("hint"))
                if hint:
                    next_action = _shorten(hint, 220)
        error_message = _shorten(_extract_error_message(tool_response), 220)
        summary_label = "denied" if error_code in {"permission_denied", "approval_denied"} else "failed"
        summary = _shorten(f"{tool_name} {summary_label}", 140)
        detail = error_message or _shorten(response_text, 220)
        if not next_action:
            next_action = "Inspect the failing tool input and the referenced KB/task artifact."
    else:
        if isinstance(parsed_response, dict):
            status_text = _stringify(parsed_response.get("status"))
            summary_source = (
                _stringify(parsed_response.get("summary"))
                or _stringify(parsed_response.get("id"))
                or _stringify(parsed_response.get("detail"))
                or status_text
            )
            if status_text and status_text.lower() not in {"ok", "success"}:
                outcome = status_text.lower()
            if "results" in parsed_response and isinstance(parsed_response["results"], list):
                summary_source = f"{len(parsed_response['results'])} result(s)"
            summary = _shorten(f"{tool_name}: {summary_source or 'completed'}", 160)
            detail = _shorten(
                _stringify(parsed_response.get("summary"))
                or _stringify(parsed_response.get("detail"))
                or response_text,
                220,
            )
        else:
            summary = _shorten(f"{tool_name}: completed", 160)
            detail = _shorten(response_text, 220)
        next_action = "Expand raw output only if the compact digest is insufficient."

    return {
        "kind": "builder_tool",
        "outcome": outcome,
        "tool_name": tool_name,
        "input_focus": focus,
        "summary": summary,
        "detail": detail,
        "error_message": error_message,
        "next_action": next_action,
        "raw_response": response_text,
    }


def summarize_chat_event(event_type: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    if event_type in {"tool_result", "tool_error"}:
        return summarize_tool_event(
            event_type=event_type,
            tool_name=str(payload.get("tool_name", "") or ""),
            tool_input=payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {},
            tool_response=payload.get("content"),
        )
    if event_type == "specialist_status":
        phase = _stringify(payload.get("phase")) or "running"
        content = _stringify(payload.get("content"))
        return {
            "kind": "specialist_status",
            "outcome": phase,
            "tool_name": _stringify(payload.get("specialist")) or "specialist",
            "input_focus": "",
            "summary": _shorten(f"Documentation agent: {phase}", 160),
            "detail": _shorten(content, 220),
            "error_message": "",
            "next_action": "",
            "raw_response": _truncate_multiline(content, 2000),
        }
    if event_type == "run_error":
        content = _stringify(payload.get("content"))
        return {
            "kind": "run_error",
            "outcome": "error",
            "tool_name": "",
            "input_focus": "",
            "summary": "Agent run failed",
            "detail": _shorten(content, 220),
            "error_message": _shorten(content, 220),
            "next_action": "Inspect the latest builder tool errors before retrying.",
            "raw_response": _truncate_multiline(content, 2000),
        }
    if event_type == "run_status":
        running = bool(payload.get("running", False))
        outcome = "running" if running else "completed"
        if payload.get("error"):
            outcome = "error"
        parts = []
        for key in ("current_turn", "max_turns", "tokens_used", "cost_usd", "duration_ms", "stop_reason", "sdk_session_id"):
            text = _stringify(payload.get(key))
            if text:
                parts.append(f"{key}={text}")
        detail = _shorten("; ".join(parts), 220)
        return {
            "kind": "run_status",
            "outcome": outcome,
            "tool_name": "Agent",
            "input_focus": detail,
            "summary": f"Agent run {outcome}",
            "detail": detail,
            "error_message": _shorten(_stringify(payload.get("error")), 220),
            "next_action": "Use builder agent history --session <id> --full --json for the transcript.",
            "raw_response": _truncate_multiline(_stringify(payload), 2000),
        }
    return {
        "kind": event_type,
        "outcome": _stringify(payload.get("status")) or "",
        "tool_name": _stringify(payload.get("tool_name")),
        "input_focus": "",
        "summary": _shorten(_stringify(payload.get("summary")) or event_type, 160),
        "detail": _shorten(_stringify(payload.get("content")), 220),
        "error_message": "",
        "next_action": "",
        "raw_response": _truncate_multiline(_stringify(payload.get("content")), 2000),
    }
