"""In-process guard against duplicate dispatch runs for a task."""

from __future__ import annotations

_RUNNING_DISPATCHES: set[str] = set()


def reserve_dispatch(task_id: str) -> bool:
    if task_id in _RUNNING_DISPATCHES:
        return False
    _RUNNING_DISPATCHES.add(task_id)
    return True


def is_dispatch_reserved(task_id: str) -> bool:
    return task_id in _RUNNING_DISPATCHES


def release_dispatch(task_id: str) -> None:
    _RUNNING_DISPATCHES.discard(task_id)
