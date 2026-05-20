"""Transcript projection helpers for the embedded Agent surface."""

from __future__ import annotations

import re
from typing import Any

from autonomous_agent_builder.db.models import ChatEvent, ChatMessage, ChatSession
from autonomous_agent_builder.embedded.server.agent_api_models import MessageItem, TimelineItem

VISIBLE_EVENT_TYPES = {
    "user_message",
    "voice_operator_message",
    "voice_final_summary",
    "voice_navigation_request",
    "voice_control_action",
    "assistant_message",
    "ask_user_question",
    "tool_approval_request",
    "tool_result",
    "tool_error",
    "todo_snapshot",
    "specialist_status",
    "run_error",
}

OPERATOR_QUESTION_TEXT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("Approval and Status Recovery Panel", "Approval and Recovery Panel"),
    ("bounded approval/status recovery feature", "clear approval flow for blocked work"),
    ("approval/status recovery feature", "clear approval flow for blocked work"),
    ("approval/status recovery improvement", "approval flow improvement"),
    ("status recovery panel", "recovery panel"),
    ("approval/blocker status", "pending approvals and blocked work"),
    ("Different backlog item", "Different improvement"),
    ("backlog item", "improvement"),
    ("product-backlog", "saved improvement"),
    ("backlog", "saved improvements"),
    ("current sprint", "current delivery"),
    ("sprint", "delivery"),
    ("lifecycle terminology", "internal wording"),
    ("lifecycle", "delivery flow"),
    ("large logs", "extra technical details"),
    ("raw logs", "technical logs"),
    ("full logs", "technical logs"),
    ("status recovery", "getting unstuck"),
    ("scope it", "define it"),
    (" to scope", " to define"),
    ("bounded ", ""),
)

DELIVERY_PERMISSION_PROMPT_PATTERNS = (
    "would you like me to proceed",
    "would you like me to continue",
    "ready for builder to start",
    "ready to start now",
    "ready to start shipping",
    "should i hold",
    "shall i proceed",
    "should i proceed",
    "need write permission",
    "need permission to create",
    "need permission to modify",
    "proceed with the implementation",
)


def assistant_requests_delivery_permission(response_text: str) -> bool:
    normalized = " ".join(response_text.lower().split())
    if not normalized:
        return False
    return any(pattern in normalized for pattern in DELIVERY_PERMISSION_PROMPT_PATTERNS)


def operator_safe_question_text(value: Any) -> str:
    text = str(value or "")
    for needle, replacement in OPERATOR_QUESTION_TEXT_REPLACEMENTS:
        text = re.sub(re.escape(needle), replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"\ba\s+an\s+", "an ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def operator_safe_question_payload(question: dict[str, Any]) -> dict[str, Any]:
    options: list[dict[str, str]] = []
    for option in question.get("options", []) or []:
        if not isinstance(option, dict):
            continue
        options.append(
            {
                "label": operator_safe_question_text(option.get("label", "")),
                "description": operator_safe_question_text(option.get("description", "")),
            }
        )
    return {
        **question,
        "header": operator_safe_question_text(question.get("header", "")),
        "question": operator_safe_question_text(question.get("question", "")),
        "options": options,
    }


def operator_safe_assistant_content(value: Any) -> str:
    text = str(value or "")
    if not (
        assistant_requests_delivery_permission(text)
        or "approval/status" in text.lower()
        or "backlog item" in text.lower()
        or "large logs" in text.lower()
        or "raw logs" in text.lower()
        or "full logs" in text.lower()
    ):
        return text
    return operator_safe_question_text(text)


def serialize_event(event: ChatEvent) -> TimelineItem:
    payload = event.payload_json or {}
    if event.event_type == "ask_user_question" and isinstance(payload, dict):
        payload = operator_safe_question_payload(payload)
    elif event.event_type == "assistant_message" and isinstance(payload, dict):
        payload = {
            **payload,
            "content": operator_safe_assistant_content(payload.get("content", "")),
        }
    return TimelineItem(
        id=event.id,
        type=event.event_type,
        status=event.status,
        timestamp=event.created_at.isoformat(),
        payload=payload,
    )


def legacy_message_item(message: ChatMessage) -> TimelineItem:
    event_type = "user_message" if message.role == "user" else "assistant_message"
    return TimelineItem(
        id=message.id,
        type=event_type,
        status="completed",
        timestamp=message.created_at.isoformat(),
        payload={"content": message.content, "final": True},
    )


def history_items(session: ChatSession) -> list[TimelineItem]:
    if session.events:
        return [
            serialize_event(event)
            for event in session.events
            if event.event_type in VISIBLE_EVENT_TYPES and event.status != "superseded"
        ]
    return [legacy_message_item(message) for message in session.messages]


def legacy_messages(items: list[TimelineItem]) -> list[MessageItem]:
    messages: list[MessageItem] = []
    for item in items:
        if item.type not in {"user_message", "assistant_message", "tool_error", "run_error"}:
            continue
        role = "user" if item.type == "user_message" else "assistant"
        content = str(item.payload.get("content", ""))
        if not content:
            continue
        messages.append(
            MessageItem(
                id=item.id,
                role=role,
                content=content,
                timestamp=item.timestamp,
            )
        )
    return messages


def latest_status(session: ChatSession, *, active_run: bool | None = None) -> dict[str, Any] | None:
    status_events = [event for event in session.events if event.event_type == "run_status"]
    if not status_events:
        return None
    latest = max(status_events, key=lambda event: event.created_at)
    payload = dict(latest.payload_json or {})
    if payload.get("running"):
        has_later_terminal_message = any(
            event.created_at > latest.created_at
            and event.event_type in {"assistant_message", "run_error"}
            and event.status == "completed"
            for event in session.events
        )
        if has_later_terminal_message:
            payload["running"] = False
            payload.setdefault("stop_reason", "completed_after_running_status")
        elif active_run is False:
            payload["running"] = False
            payload.setdefault("stop_reason", "stale_running_status_no_active_task")
    return payload


def token_usage_status_payload(
    *,
    tokens_input: int,
    tokens_output: int,
    tokens_cached: int,
) -> dict[str, int]:
    tokens_cached = min(max(int(tokens_cached or 0), 0), max(int(tokens_input or 0), 0))
    tokens_input = max(int(tokens_input or 0), 0)
    tokens_output = max(int(tokens_output or 0), 0)
    return {
        "tokens_used": tokens_input + tokens_output,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "tokens_cached": tokens_cached,
        "raw_tokens": tokens_input + tokens_output,
        "noncached_plus_output_tokens": max(tokens_input - tokens_cached, 0) + tokens_output,
    }


def thread_runtime_metadata(
    current_runtime_metadata: dict[str, Any],
    status: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return runtime metadata for the loaded thread, not the selected future runtime."""

    metadata = dict(current_runtime_metadata)
    if not status:
        return metadata
    for key in ("model", "effort", "runtime_sdk", "provider"):
        value = status.get(key)
        if value not in (None, ""):
            metadata[key] = value
    return metadata
