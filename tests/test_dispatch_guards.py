"""Regression tests for IMP-007 (project-level dispatch guard) and
IMP-009 (scaffold-pending dispatch guard).
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from autonomous_agent_builder.db.models import (
    AgentRun,
    BacklogItemType,
    Feature,
    FeatureStatus,
    Project,
    Task,
)
from autonomous_agent_builder.services.dispatch_lock import (
    _PROJECT_ACTIVE_DISPATCHES,
    release_project_dispatch,
    reserve_project_dispatch,
)


# ---------------------------------------------------------------------------
# Unit tests for dispatch_lock project-level guard (IMP-007)
# ---------------------------------------------------------------------------


def test_reserve_project_dispatch_allows_first_reservation():
    project_id = "unit-proj-reserve"
    _PROJECT_ACTIVE_DISPATCHES.pop(project_id, None)

    result = reserve_project_dispatch(project_id)

    assert result is True
    assert _PROJECT_ACTIVE_DISPATCHES.get(project_id) == 1
    release_project_dispatch(project_id)


def test_reserve_project_dispatch_blocks_at_limit():
    project_id = "unit-proj-limit"
    _PROJECT_ACTIVE_DISPATCHES.pop(project_id, None)

    first = reserve_project_dispatch(project_id)
    second = reserve_project_dispatch(project_id)

    assert first is True
    assert second is False

    release_project_dispatch(project_id)


def test_release_project_dispatch_clears_slot():
    project_id = "unit-proj-release"
    _PROJECT_ACTIVE_DISPATCHES.pop(project_id, None)

    reserve_project_dispatch(project_id)
    release_project_dispatch(project_id)

    assert project_id not in _PROJECT_ACTIVE_DISPATCHES


def test_release_project_dispatch_is_safe_when_not_reserved():
    release_project_dispatch("unit-nonexistent-project-id")


# ---------------------------------------------------------------------------
# Integration tests against the embedded-server dispatch route
# ---------------------------------------------------------------------------


def _make_embedded_app(tmp_path):
    from autonomous_agent_builder.embedded.server.app import create_app

    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html></html>")
    (tmp_path / ".agent-builder").mkdir(parents=True, exist_ok=True)
    return create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )


@pytest.mark.asyncio
async def test_dispatch_returns_scaffold_pending_when_scaffold_agent_running(
    test_db, tmp_path
):
    """IMP-009: dispatch route must block while a scaffold AgentRun is running."""
    _, factory = test_db
    app = _make_embedded_app(tmp_path)

    async with factory() as db:
        project = Project(name="scaffold-guard", description="", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Scaffold guard feature",
            description="",
            status=FeatureStatus.QUEUED,
            item_type=BacklogItemType.FEATURE,
        )
        db.add(feature)
        await db.flush()
        task = Task(feature_id=feature.id, title="Task with scaffold", description="")
        db.add(task)
        await db.flush()
        # Simulate a scaffold agent run that is still in-flight
        run = AgentRun(task_id=task.id, agent_name="scaffold", status="running")
        db.add(run)
        await db.commit()
        task_id = task.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/tasks/{task_id}/dispatch")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "scaffold_pending", f"Unexpected response: {body}"
    assert body["task_id"] == task_id


@pytest.mark.asyncio
async def test_dispatch_returns_project_busy_when_project_already_dispatching(
    test_db, tmp_path
):
    """IMP-007: second task in same project returns project_busy while first is dispatching."""
    from autonomous_agent_builder.services import dispatch_lock

    dispatch_lock._PROJECT_ACTIVE_DISPATCHES.clear()

    _, factory = test_db
    app = _make_embedded_app(tmp_path)

    async with factory() as db:
        project = Project(name="busy-guard", description="", language="python")
        db.add(project)
        await db.flush()
        project_id = project.id

        feature = Feature(
            project_id=project_id,
            title="Busy feature",
            description="",
            status=FeatureStatus.QUEUED,
            item_type=BacklogItemType.FEATURE,
        )
        db.add(feature)
        await db.flush()
        task_b = Task(feature_id=feature.id, title="Task B", description="")
        db.add(task_b)
        await db.commit()
        task_b_id = task_b.id

    # Manually hold the project dispatch slot (simulates task A already running)
    dispatch_lock.reserve_project_dispatch(project_id)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/api/tasks/{task_b_id}/dispatch")
    finally:
        dispatch_lock.release_project_dispatch(project_id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "project_busy", f"Unexpected response: {body}"
    assert body["task_id"] == task_b_id
