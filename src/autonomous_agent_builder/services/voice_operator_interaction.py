"""Deterministic interaction helpers for the Realtime voice operator."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from autonomous_agent_builder.db.models import AgentRun, Feature, Task, TaskStatus, utcnow
from autonomous_agent_builder.services.task_dispatch_policy import (
    task_is_dispatchable as _task_is_dispatchable,
)
from autonomous_agent_builder.services.task_dispatch_policy import (
    task_status_value as _task_status_value,
)

NAVIGATION_TARGETS = {
    "agent": "/",
    "conversation": "/?mode=chat",
    "chat": "/?mode=chat",
    "voice": "/?mode=voice",
    "realtime": "/?mode=voice",
    "realtime voice": "/?mode=voice",
    "run trace": "/?mode=trace",
    "trace": "/?mode=trace",
    "board": "/board",
    "metrics": "/metrics",
    "observability": "/observability",
    "logs": "/observability",
    "knowledge": "/knowledge",
    "memory": "/memory",
    "backlog": "/backlog",
    "inbox": "/inbox",
    "compare": "/compare",
    "settings": "/settings",
}

BOARD_QUEUED_STATUSES = {TaskStatus.PENDING.value, TaskStatus.QUEUED.value}
BOARD_PROGRESS_STATUSES = {
    TaskStatus.PLANNING.value,
    TaskStatus.DESIGN.value,
    TaskStatus.IMPLEMENTATION.value,
    TaskStatus.QUALITY_GATES.value,
    TaskStatus.PR_CREATION.value,
    TaskStatus.BUILD_VERIFY.value,
}
BOARD_REVIEW_STATUSES = {TaskStatus.DESIGN_REVIEW.value, TaskStatus.REVIEW_PENDING.value}


def compact_json_text(value: Any, *, max_chars: int = 700) -> str:
    if value in (None, "", [], {}):
        return ""
    try:
        text = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    except (TypeError, ValueError):
        text = str(value)
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 13].rstrip() + " ...[truncated]"


def approval_decision_from_utterance(message: str) -> str:
    normalized = " ".join(str(message or "").lower().split())
    if not normalized:
        return ""
    deny_phrases = (
        "do not approve",
        "don't approve",
        "dont approve",
        "deny",
        "reject",
        "decline",
        "not approved",
        "no",
        "nope",
    )
    allow_phrases = (
        "approve",
        "allow",
        "go ahead",
        "confirm",
        "confirmed",
        "yes",
        "yep",
        "yeah",
        "okay",
        "ok",
        "proceed",
    )
    if any(phrase in normalized for phrase in deny_phrases):
        return "deny"
    if any(phrase in normalized for phrase in allow_phrases):
        return "allow"
    return ""


def question_options(payload: dict[str, Any]) -> list[dict[str, str]]:
    raw_options = payload.get("options")
    if not isinstance(raw_options, list):
        return []
    options: list[dict[str, str]] = []
    for raw_option in raw_options:
        if not isinstance(raw_option, dict):
            continue
        label = str(raw_option.get("label") or "").strip()
        if not label:
            continue
        options.append(
            {
                "label": label,
                "description": str(raw_option.get("description") or "").strip(),
            }
        )
    return options


def recommended_option_index(payload: dict[str, Any], option_count: int) -> int:
    try:
        recommended_index = int(payload.get("recommended_index", -1))
    except (TypeError, ValueError):
        recommended_index = -1
    if 0 <= recommended_index < option_count:
        return recommended_index
    return 0 if option_count else -1


def resolve_question_answer_value(answer: str, payload: dict[str, Any]) -> str:
    normalized = " ".join(str(answer or "").lower().split())
    options = question_options(payload)
    if not normalized or not options:
        return answer
    labels = [option["label"] for option in options]
    recommended_index = recommended_option_index(payload, len(options))
    if "recommended" in normalized and 0 <= recommended_index < len(labels):
        return labels[recommended_index]
    ordinal_indexes = {
        "first": 0,
        "1st": 0,
        "one": 0,
        "second": 1,
        "2nd": 1,
        "two": 1,
        "third": 2,
        "3rd": 2,
        "three": 2,
    }
    for marker, index in ordinal_indexes.items():
        if marker in normalized and index < len(labels):
            return labels[index]
    if normalized in {"all", "all of them", "both"}:
        if bool(payload.get("multi_select")):
            return ", ".join(labels)
        if 0 <= recommended_index < len(labels):
            return labels[recommended_index]
    for label in labels:
        label_normalized = " ".join(label.lower().replace("(recommended)", "").split())
        if label.lower() in normalized or (label_normalized and label_normalized in normalized):
            return label
    return answer


def approval_reminder_prompt_text(item: dict[str, Any], pending_count: int) -> str:
    prefix = "Builder is waiting for your approval"
    if pending_count > 1:
        prefix = f"Builder is waiting for {pending_count} approvals"

    if item.get("type") == "voice_action_prepared":
        consequence = str(item.get("consequence_summary") or item.get("summary") or "").strip()
        confirmation = str(item.get("confirmation_phrase") or "").strip()
        if confirmation:
            return (
                f"{prefix}. {consequence} Say yes to confirm, no to cancel, "
                f"or ask Builder for details. Confirmation phrase: {confirmation}"
            )
        return (
            f"{prefix}. {consequence} Say yes to confirm, no to cancel, or ask Builder for details."
        )

    summary = str(item.get("summary") or item.get("tool_name") or "a pending tool request").strip()
    description = str(item.get("description") or "").strip()
    detail = f" {description}" if description else ""
    return f"{prefix}. {summary}.{detail} Say approve or deny, or ask Builder for details."


def voice_runtime_sdk(value: Any) -> str:
    normalized = " ".join(str(value or "").lower().replace("-", " ").replace("_", " ").split())
    if normalized in {"codex", "codex sdk", "codex app server", "codex subscription"}:
        return "codex_sdk"
    if normalized in {"claude", "claude sdk", "claude agent sdk", "claude code"}:
        return "claude"
    raise ValueError("sdk must be Codex SDK or Claude Agent SDK")


def runtime_display_name(sdk: str) -> str:
    if sdk == "codex_sdk":
        return "Codex SDK"
    if sdk == "claude":
        return "Claude Agent SDK"
    return sdk or "unknown"


def backlog_item_type_value(feature: Feature) -> str:
    return str(
        feature.item_type.value if hasattr(feature.item_type, "value") else feature.item_type
    )


def task_latest_run_status(task: Task, latest_runs_by_task: dict[str, AgentRun]) -> str:
    run = latest_runs_by_task.get(task.id)
    return str(getattr(run, "status", "") or "") if run is not None else ""


def task_has_blocked_reason(task: Task) -> bool:
    return bool(str(task.capability_limit_reason or task.blocked_reason or "").strip())


def task_is_in_progress_board_lane(
    task: Task,
    latest_runs_by_task: dict[str, AgentRun],
) -> bool:
    return (
        _task_status_value(task) in BOARD_PROGRESS_STATUSES
        and task_latest_run_status(task, latest_runs_by_task) == "running"
        and not task_has_blocked_reason(task)
    )


def task_is_review_board_lane(task: Task) -> bool:
    status = _task_status_value(task)
    return status in BOARD_REVIEW_STATUSES or (
        status in BOARD_PROGRESS_STATUSES and task_has_blocked_reason(task)
    )


def task_is_queued_board_lane(
    task: Task,
    latest_runs_by_task: dict[str, AgentRun],
) -> bool:
    status = _task_status_value(task)
    return status in BOARD_QUEUED_STATUSES or (
        status in BOARD_PROGRESS_STATUSES
        and not task_is_in_progress_board_lane(task, latest_runs_by_task)
        and not task_is_review_board_lane(task)
    )


def provider_limit_reason_is_current(
    reason: str,
    *,
    completed_at: datetime | None = None,
) -> bool:
    reset_at = provider_limit_reset_at(reason)
    if reset_at is not None:
        return reset_at > utcnow()
    if completed_at is None:
        return True
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=UTC)
    return completed_at > utcnow() - timedelta(hours=1)


def provider_limit_reset_at(reason: str) -> datetime | None:
    match = re.search(r"reset_at=([^;\s]+)", str(reason or ""))
    if not match:
        return None
    value = match.group(1).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def select_recovery_task(tasks: list[Task], recovery_request: str) -> tuple[Task | None, str]:
    if not tasks:
        return None, ""
    normalized_request = normalize_match_text(recovery_request)
    if normalized_request:
        for task in tasks:
            if task.id and task.id.lower() in normalized_request:
                return task, "task_id"
        for task in tasks:
            normalized_title = normalize_match_text(task.title)
            if normalized_title and normalized_title in normalized_request:
                return task, "title"
        request_terms = set(normalized_request.split())
        for task in tasks:
            haystack = normalize_match_text(
                " ".join(
                    [
                        task.title,
                        _task_status_value(task),
                        task.capability_limit_reason or "",
                        task.blocked_reason or "",
                    ]
                )
            )
            if request_terms and request_terms.issubset(set(haystack.split())):
                return task, "request_terms"
    if len(tasks) == 1:
        return tasks[0], "only_blocked_task"
    return None, ""


def normalize_match_text(value: str) -> str:
    return " ".join(str(value or "").lower().replace("`", " ").split())


def task_recovery_snapshot(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "feature_id": task.feature_id,
        "status": _task_status_value(task),
        "reason": task.capability_limit_reason or task.blocked_reason or "",
        "blocked_reason": task.blocked_reason or "",
        "capability_limit_reason": task.capability_limit_reason or "",
    }


def task_dispatch_snapshot(task: Task) -> dict[str, Any]:
    feature = getattr(task, "feature", None)
    feature_status = (
        feature.status.value
        if feature is not None and hasattr(feature.status, "value")
        else str(feature.status if feature is not None else "")
    )
    return {
        "id": task.id,
        "title": task.title,
        "feature_id": task.feature_id,
        "feature_status": feature_status,
        "status": _task_status_value(task),
        "phase": str(task.phase.value if hasattr(task.phase, "value") else task.phase),
        "retry_count": task.retry_count,
        "dispatchable": _task_is_dispatchable(task),
    }


def agent_run_trace_snapshot(run: AgentRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "task_id": run.task_id,
        "agent_name": run.agent_name,
        "status": str(run.status or ""),
        "runtime_sdk": run.runtime_sdk,
        "provider": run.provider,
        "model": run.model,
        "effort": run.effort,
        "cost_usd": run.cost_usd,
        "tokens_input": run.tokens_input,
        "tokens_output": run.tokens_output,
        "tokens_cached": run.tokens_cached,
        "num_turns": run.num_turns,
        "duration_ms": run.duration_ms,
        "stop_reason": run.stop_reason or "",
        "error": run.error or "",
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def dashboard_route_for_target(target: str) -> str:
    normalized = normalize_match_text(target)
    if normalized in NAVIGATION_TARGETS:
        return NAVIGATION_TARGETS[normalized]
    for key, route in NAVIGATION_TARGETS.items():
        if key in normalized:
            return route
    return ""


def voice_call_sessions(app: Any) -> dict[str, str]:
    sessions = getattr(app.state, "realtime_voice_call_sessions", None)
    if not isinstance(sessions, dict):
        sessions = {}
        app.state.realtime_voice_call_sessions = sessions
    return sessions


def bind_voice_call_session(app: Any, call_id: str, session_id: str) -> None:
    if call_id and session_id:
        voice_call_sessions(app)[call_id] = session_id


def voice_call_session_id(app: Any, call_id: str) -> str:
    if not call_id:
        return ""
    session_id = voice_call_sessions(app).get(call_id)
    return str(session_id or "")
