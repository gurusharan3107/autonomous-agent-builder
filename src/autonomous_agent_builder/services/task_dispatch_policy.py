"""Shared dispatchability policy for Builder task continuation and dispatch."""

from __future__ import annotations

from autonomous_agent_builder.backlog_items import backlog_item_reaches_board
from autonomous_agent_builder.db.models import Feature, Task, TaskStatus
from autonomous_agent_builder.services.provider_limits import provider_limit_payload

NON_DISPATCHABLE_TASK_STATUSES = {
    TaskStatus.DESIGN_REVIEW.value,
    TaskStatus.REVIEW_PENDING.value,
    TaskStatus.BLOCKED.value,
    TaskStatus.CAPABILITY_LIMIT.value,
    TaskStatus.DONE.value,
    TaskStatus.FAILED.value,
}

_DISPATCH_STATUS_PRIORITY = {
    TaskStatus.IMPLEMENTATION.value: 0,
    TaskStatus.BUILD_VERIFY.value: 1,
    TaskStatus.QUALITY_GATES.value: 2,
    TaskStatus.PLANNING.value: 3,
    TaskStatus.PENDING.value: 4,
    TaskStatus.QUEUED.value: 5,
    TaskStatus.DESIGN.value: 6,
    TaskStatus.PR_CREATION.value: 7,
}


def task_status_value(task: Task) -> str:
    return str(task.status.value if hasattr(task.status, "value") else task.status)


def feature_status_value(feature: Feature | None) -> str:
    return str(
        feature.status.value
        if feature is not None and hasattr(feature.status, "value")
        else (feature.status if feature is not None else "")
    )


def task_status_blocks_dispatch(task: Task) -> bool:
    return task_status_value(task) in NON_DISPATCHABLE_TASK_STATUSES


def task_feature_reaches_board(task: Task) -> bool:
    return backlog_item_reaches_board(feature_status_value(getattr(task, "feature", None)))


def task_is_dispatchable(task: Task) -> bool:
    return not task_status_blocks_dispatch(task) and task_feature_reaches_board(task)


def task_not_dispatchable_detail(task: Task) -> dict[str, object]:
    return {
        "code": "task_not_dispatchable",
        "task_id": task.id,
        "status": task_status_value(task),
        "blocked_reason": task.blocked_reason,
        "provider_limit": provider_limit_payload(task) or None,
        "message": "Task is in a terminal or approval-blocked state and cannot be dispatched.",
    }


def backlog_item_not_queued_detail(task: Task) -> dict[str, object]:
    return {
        "code": "backlog_item_not_queued",
        "task_id": task.id,
        "feature_id": task.feature_id,
        "feature_status": feature_status_value(getattr(task, "feature", None)),
        "message": "Task cannot be dispatched until its backlog item has been approved and queued.",
    }


def dispatch_already_running_payload(task: Task) -> dict[str, object]:
    return {
        "task_id": task.id,
        "status": "already_running",
        "current_status": task_status_value(task),
    }


def dispatch_started_payload(task: Task) -> dict[str, object]:
    return {
        "task_id": task.id,
        "status": "dispatched",
        "current_status": task_status_value(task),
    }


def task_dispatch_sort_key(task: Task) -> tuple[int, float]:
    updated = task.updated_at or task.created_at
    timestamp = updated.timestamp() if updated is not None else 0.0
    return (_DISPATCH_STATUS_PRIORITY.get(task_status_value(task), 99), -timestamp)
