"""Board-status aggregation helpers for the Realtime voice operator board status query."""

from __future__ import annotations

from typing import Any

from autonomous_agent_builder.db.models import (
    FeatureStatus,
    TaskStatus,
)
from autonomous_agent_builder.services.task_dispatch_policy import (
    feature_status_value as _feature_status_value,
)
from autonomous_agent_builder.services.task_dispatch_policy import (
    task_dispatch_sort_key as _task_dispatch_sort_key,
)
from autonomous_agent_builder.services.task_dispatch_policy import (
    task_is_dispatchable as _task_is_dispatchable,
)
from autonomous_agent_builder.services.task_dispatch_policy import (
    task_status_value as _task_status_value,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    backlog_item_type_value as _backlog_item_type_value,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    provider_limit_reason_is_current as _provider_limit_reason_is_current,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    task_dispatch_snapshot as _task_dispatch_snapshot,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    task_is_in_progress_board_lane as _task_is_in_progress_board_lane,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    task_is_queued_board_lane as _task_is_queued_board_lane,
)


def aggregate_backlog_items(
    backlog_items: list[Any],
) -> tuple[dict[str, int], dict[str, int], list[dict[str, Any]]]:
    """Aggregate backlog items by status and type. Returns (status_counts, type_counts, open_items)."""
    backlog_status_counts: dict[str, int] = {}
    backlog_type_counts: dict[str, int] = {}
    open_backlog_items: list[dict[str, Any]] = []
    for item in backlog_items:
        status = _feature_status_value(item)
        item_type = _backlog_item_type_value(item)
        backlog_status_counts[status] = backlog_status_counts.get(status, 0) + 1
        backlog_type_counts[item_type] = backlog_type_counts.get(item_type, 0) + 1
        if status != FeatureStatus.DONE.value:
            open_backlog_items.append(
                {
                    "id": item.id,
                    "title": item.title,
                    "status": status,
                    "type": item_type,
                }
            )
    return backlog_status_counts, backlog_type_counts, open_backlog_items


def aggregate_task_status_counts(tasks: list[Any]) -> dict[str, int]:
    """Count tasks by status."""
    status_counts: dict[str, int] = {}
    for task in tasks:
        status = _task_status_value(task)
        status_counts[status] = status_counts.get(status, 0) + 1
    return status_counts


def build_blocked_tasks(tasks: list[Any]) -> list[dict[str, Any]]:
    """Build list of blocked tasks with reasons."""
    blocked_statuses = {
        TaskStatus.BLOCKED.value,
        TaskStatus.CAPABILITY_LIMIT.value,
        TaskStatus.FAILED.value,
    }
    return [
        {
            "id": task.id,
            "title": task.title,
            "status": _task_status_value(task),
            "reason": task.capability_limit_reason or task.blocked_reason or "",
            "blocked_reason": task.blocked_reason or "",
            "capability_limit_reason": task.capability_limit_reason or "",
        }
        for task in tasks
        if _task_status_value(task) in blocked_statuses
    ]


def build_task_lane_lists(
    tasks: list[Any],
    latest_runs_by_task: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build queued, active, and dispatchable task lists. Returns (queued, active, dispatchable)."""
    queued_tasks = [
        {
            "id": task.id,
            "title": task.title,
            "status": _task_status_value(task),
        }
        for task in tasks
        if _task_is_queued_board_lane(task, latest_runs_by_task)
    ]
    active_tasks = [
        {
            "id": task.id,
            "title": task.title,
            "status": _task_status_value(task),
        }
        for task in tasks
        if _task_is_in_progress_board_lane(task, latest_runs_by_task)
    ]
    dispatchable_tasks = [
        _task_dispatch_snapshot(task)
        for task in sorted(
            [item for item in tasks if _task_is_dispatchable(item)],
            key=_task_dispatch_sort_key,
        )
    ][:5]
    return queued_tasks, active_tasks, dispatchable_tasks


def build_provider_limit_runs(
    latest_runs_by_task: dict[str, Any],
    tasks_by_id: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build list of provider-limit runs with task context."""
    provider_limit_runs = []
    for run in latest_runs_by_task.values():
        if str(run.stop_reason or "") != "provider_limit":
            continue
        task = tasks_by_id.get(run.task_id)
        if task is None:
            continue
        reason = (
            " ".join(
                item
                for item in [
                    str(task.capability_limit_reason or "").strip(),
                    str(task.blocked_reason or "").strip(),
                ]
                if item
            )
            if task is not None
            else ""
        )
        provider_limit_runs.append(
            {
                "run_id": run.id,
                "task_id": run.task_id,
                "task_title": task.title if task is not None else "",
                "task_status": _task_status_value(task) if task is not None else "",
                "task_reason": reason,
                "agent_name": run.agent_name,
                "runtime_sdk": run.runtime_sdk,
                "provider": run.provider,
                "model": run.model,
                "stop_reason": run.stop_reason or "",
                "provider_limit_current": _provider_limit_reason_is_current(
                    reason,
                    completed_at=run.completed_at,
                ),
                "started_at": run.started_at.isoformat(),
                "completed_at": run.completed_at.isoformat() if run.completed_at else "",
            }
        )
    return provider_limit_runs
