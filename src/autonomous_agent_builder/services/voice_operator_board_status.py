"""Board-status aggregation helpers for the Realtime voice operator board status query."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.db.models import (
    AgentRun,
    BacklogItemType,
    Feature,
    FeatureStatus,
    Task,
    TaskStatus,
)
from autonomous_agent_builder.embedded.server.board_scope import (
    board_response_task_ids,
    board_status_scope_from_message,
)
from autonomous_agent_builder.embedded.server.routes.dashboard import load_board_response
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
from autonomous_agent_builder.services.voice_operator_interaction import (
    task_is_review_board_lane as _task_is_review_board_lane,
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


async def load_voice_board_status(db: Any, *, status_prompt: str = "") -> dict[str, Any]:
    """Load and assemble the full board status dict for the voice digest."""
    board_response = await load_board_response(db)
    status_scope = board_status_scope_from_message(status_prompt, board_response.current_sprint)
    visible_task_ids = board_response_task_ids(board_response)
    scoped_task_ids = set(status_scope.generated_task_ids)
    result = await db.execute(select(Task).options(selectinload(Task.feature)))
    tasks = list(result.scalars().all())
    if visible_task_ids:
        tasks = [task for task in tasks if task.id in visible_task_ids]
    if status_scope.is_current_sprint:
        tasks = [task for task in tasks if task.id in scoped_task_ids]
    feature_result = await db.execute(select(Feature).order_by(Feature.priority.desc()))
    backlog_items = list(feature_result.scalars().all())
    sprint_summaries = [
        {
            "id": sprint.sprint_id,
            "label": sprint.label,
            "phase": sprint.active_phase,
            "approved_feature_count": len(sprint.included_items or []),
            "generated_task_count": len(sprint.generated_task_ids or []),
            "verification_status": sprint.verification_status,
        }
        for sprint in (board_response.sprints or [])
    ]
    tasks_by_id = {task.id: task for task in tasks}
    backlog_status_counts, backlog_type_counts, open_backlog_items = aggregate_backlog_items(
        backlog_items
    )
    status_counts = aggregate_task_status_counts(tasks)
    run_result = await db.execute(
        select(AgentRun).order_by(AgentRun.started_at.desc()).limit(50)
    )
    latest_runs_by_task: dict[str, AgentRun] = {}
    for run in run_result.scalars().all():
        if run.task_id not in latest_runs_by_task:
            latest_runs_by_task[run.task_id] = run

    blocked_tasks = build_blocked_tasks(tasks)
    queued_tasks, active_tasks, dispatchable_tasks = build_task_lane_lists(
        tasks, latest_runs_by_task
    )
    provider_limit_runs = build_provider_limit_runs(latest_runs_by_task, tasks_by_id)
    return {
        "task_count": len(tasks),
        "sprint_count": len(sprint_summaries),
        "sprints": sprint_summaries[:10],
        "scope": status_scope.scope,
        "current_sprint_label": status_scope.current_sprint_label,
        "current_sprint_phase": str(
            getattr(board_response.current_sprint, "active_phase", "") or ""
        ).strip(),
        "status_counts": status_counts,
        "review_count": sum(1 for task in tasks if _task_is_review_board_lane(task)),
        "done_count": sum(
            1 for task in tasks if _task_status_value(task) == TaskStatus.DONE.value
        ),
        "blocked_count": len(blocked_tasks),
        "queued_count": len(queued_tasks),
        "active_count": len(active_tasks),
        "blocked_tasks": blocked_tasks[:5],
        "queued_tasks": queued_tasks[:5],
        "active_tasks": active_tasks[:5],
        "dispatchable_count": len(dispatchable_tasks),
        "dispatchable_tasks": dispatchable_tasks,
        "provider_limit_count": len(provider_limit_runs),
        "provider_limit_runs": provider_limit_runs[:5],
        "backlog_status": {
            "item_count": len(backlog_items),
            "feature_count": backlog_type_counts.get(BacklogItemType.FEATURE.value, 0),
            "done_count": backlog_status_counts.get(FeatureStatus.DONE.value, 0),
            "open_count": len(open_backlog_items),
            "status_counts": backlog_status_counts,
            "type_counts": backlog_type_counts,
            "open_items": open_backlog_items[:5],
        },
    }
