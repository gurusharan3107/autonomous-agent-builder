"""In-process guard against duplicate dispatch runs for a task.

Also enforces a per-project concurrent dispatch limit (max 1) so the agent
cannot saturate the SQLAlchemy connection pool by dispatching all tasks at
once (IMP-007).
"""

from __future__ import annotations

_RUNNING_DISPATCHES: set[str] = set()
_PROJECT_ACTIVE_DISPATCHES: dict[str, int] = {}
_MAX_CONCURRENT_DISPATCHES_PER_PROJECT = 1


def reserve_dispatch(task_id: str) -> bool:
    if task_id in _RUNNING_DISPATCHES:
        return False
    _RUNNING_DISPATCHES.add(task_id)
    return True


def is_dispatch_reserved(task_id: str) -> bool:
    return task_id in _RUNNING_DISPATCHES


def release_dispatch(task_id: str) -> None:
    _RUNNING_DISPATCHES.discard(task_id)


def reserve_project_dispatch(project_id: str) -> bool:
    """Reserve a concurrent dispatch slot for the project.

    Returns False when the project already has
    _MAX_CONCURRENT_DISPATCHES_PER_PROJECT tasks running so the caller can
    surface a clear "another task is already running" message instead of
    letting multiple agent loops hammer the connection pool (IMP-007).
    """
    count = _PROJECT_ACTIVE_DISPATCHES.get(project_id, 0)
    if count >= _MAX_CONCURRENT_DISPATCHES_PER_PROJECT:
        return False
    _PROJECT_ACTIVE_DISPATCHES[project_id] = count + 1
    return True


def release_project_dispatch(project_id: str) -> None:
    count = _PROJECT_ACTIVE_DISPATCHES.get(project_id, 0)
    if count <= 1:
        _PROJECT_ACTIVE_DISPATCHES.pop(project_id, None)
    else:
        _PROJECT_ACTIVE_DISPATCHES[project_id] = count - 1
