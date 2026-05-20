"""Compact task activity timeline helpers for dashboard task details."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from autonomous_agent_builder.db.models import AgentRun

_MAX_ACTION_CHARS = 180


def _timestamp(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _compact(value: Any, *, limit: int = _MAX_ACTION_CHARS) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _file_event_type(status: str) -> str:
    match status.upper():
        case "A" | "ADDED" | "CREATED":
            return "file_created"
        case "D" | "DELETED":
            return "file_deleted"
        case "R" | "RENAMED":
            return "file_renamed"
        case _:
            return "file_updated"


def _run_metadata(run: AgentRun) -> dict[str, str]:
    return {
        "runtime_sdk": run.runtime_sdk or "",
        "provider": run.provider or "",
    }


def _file_action(event_type: str, path: str, added: int, removed: int, old_path: str = "") -> str:
    stats = f" (+{added}/-{removed})" if added or removed else ""
    if event_type == "file_created":
        return f"Created {path}{stats}"
    if event_type == "file_deleted":
        return f"Deleted {path}{stats}"
    if event_type == "file_renamed":
        source = f"{old_path} -> " if old_path else ""
        return f"Renamed {source}{path}{stats}"
    return f"Updated {path}{stats}"


def _diff_file_events(run: AgentRun) -> list[dict[str, Any]]:
    diff = run.diff_summary if isinstance(run.diff_summary, dict) else {}
    raw_files = diff.get("files")
    events: list[dict[str, Any]] = []
    timestamp = _timestamp(run.completed_at or run.started_at)
    if isinstance(raw_files, list):
        for index, item in enumerate(raw_files):
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or item.get("file") or "").strip()
            if not path:
                continue
            old_path = str(item.get("old_path") or "").strip()
            added = int(item.get("added_lines", 0) or 0)
            removed = int(item.get("removed_lines", 0) or 0)
            event_type = _file_event_type(str(item.get("status") or "M"))
            events.append(
                {
                    "id": f"{run.id}:diff:{index}",
                    "run_id": run.id,
                    "agent_name": run.agent_name,
                    **_run_metadata(run),
                    "status": run.status,
                    "event_type": event_type,
                    "action": _file_action(event_type, path, added, removed, old_path),
                    "file_path": path,
                    "timestamp": timestamp,
                }
            )
        return events

    raw_hunks = diff.get("hunks")
    if isinstance(raw_hunks, list):
        for index, item in enumerate(raw_hunks):
            if not isinstance(item, dict):
                continue
            path = str(item.get("file") or "").strip()
            if not path:
                continue
            added = int(item.get("added_lines", 0) or 0)
            removed = int(item.get("removed_lines", 0) or 0)
            events.append(
                {
                    "id": f"{run.id}:diff:{index}",
                    "run_id": run.id,
                    "agent_name": run.agent_name,
                    **_run_metadata(run),
                    "status": run.status,
                    "event_type": "file_updated",
                    "action": _file_action("file_updated", path, added, removed),
                    "file_path": path,
                    "timestamp": timestamp,
                }
            )
    return events


def _run_event_items(run: AgentRun) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for event in sorted(run.events or [], key=lambda item: _timestamp(item.timestamp)):
        if event.event_type == "agent_output":
            preview = _compact(event.output_preview)
            if not preview:
                continue
            action = preview
            event_type = "agent_output"
        elif event.event_type == "tool_use":
            tool_name = str(event.tool_name or "tool").strip()
            path = _tool_path(event.tool_input)
            action = f"Used {tool_name}{f' on {path}' if path else ''}"
            event_type = "tool_use"
        elif event.event_type == "thinking":
            action = f"Thinking: {_compact(event.output_preview)}"
            event_type = "thinking"
        elif event.event_type in {"runtime_item_started", "runtime_item_completed"}:
            tool_name = str(event.tool_name or "runtime item").strip()
            action = (
                f"{'Started' if event.event_type.endswith('started') else 'Completed'} {tool_name}"
            )
            event_type = event.event_type
        else:
            action = _compact(event.output_preview or event.event_type)
            event_type = event.event_type or "event"
        events.append(
            {
                "id": event.id,
                "run_id": run.id,
                "agent_name": run.agent_name,
                **_run_metadata(run),
                "status": run.status,
                "event_type": event_type,
                "action": action,
                "file_path": _tool_path(event.tool_input),
                "timestamp": _timestamp(event.timestamp),
            }
        )
    return events


def _tool_path(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("file_path", "path", "filename", "cwd"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def build_task_activity_timeline(
    runs: list[AgentRun],
    *,
    blocked_reason: str = "",
    limit: int = 40,
) -> list[dict[str, Any]]:
    """Return bounded, transcript-free task activity events from persisted runs."""
    timeline: list[dict[str, Any]] = []
    for run in sorted(runs, key=lambda item: _timestamp(item.started_at)):
        timeline.append(
            {
                "id": f"{run.id}:started",
                "run_id": run.id,
                "agent_name": run.agent_name,
                **_run_metadata(run),
                "status": run.status,
                "event_type": "run_started",
                "action": f"Started {run.agent_name}",
                "file_path": "",
                "timestamp": _timestamp(run.started_at),
            }
        )
        timeline.extend(_run_event_items(run))
        diff_events = _diff_file_events(run)
        timeline.extend(diff_events)
        if run.error:
            failure_detail = (
                blocked_reason if blocked_reason and run.status == "failed" else run.error
            )
            timeline.append(
                {
                    "id": f"{run.id}:failed",
                    "run_id": run.id,
                    "agent_name": run.agent_name,
                    **_run_metadata(run),
                    "status": run.status,
                    "event_type": "run_failed",
                    "action": f"Failed: {_compact(failure_detail)}",
                    "file_path": "",
                    "timestamp": _timestamp(run.completed_at or run.started_at),
                }
            )
        elif run.completed_at and not diff_events:
            timeline.append(
                {
                    "id": f"{run.id}:completed",
                    "run_id": run.id,
                    "agent_name": run.agent_name,
                    **_run_metadata(run),
                    "status": run.status,
                    "event_type": "run_completed",
                    "action": f"Completed {run.agent_name}",
                    "file_path": "",
                    "timestamp": _timestamp(run.completed_at),
                }
            )

    return timeline[-limit:]
