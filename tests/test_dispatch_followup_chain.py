"""Focused regressions for dispatch follow-up cycle handling."""

from __future__ import annotations

import pytest

from autonomous_agent_builder.db.models import (
    BacklogItemType,
    Feature,
    FeatureStatus,
    Project,
    Task,
    TaskStatus,
)


@pytest.mark.asyncio
async def test_api_dispatch_blocks_same_status_followup_cycle(test_db, monkeypatch):
    dispatched: list[str] = []

    async def fake_dispatch(self, task: Task) -> None:
        dispatched.append(task.id)

    monkeypatch.setattr(
        "autonomous_agent_builder.api.routes.dispatch.Orchestrator.dispatch",
        fake_dispatch,
    )

    _, factory = test_db
    async with factory() as db:
        project = Project(name="dispatch-cycle-proj", description="", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Dispatch cycle feature",
            description="",
            status=FeatureStatus.QUEUED,
            item_type=BacklogItemType.FEATURE,
        )
        db.add(feature)
        await db.flush()
        task = Task(feature_id=feature.id, title="Stuck dispatch task", description="")
        db.add(task)
        await db.commit()
        task_id = task.id

    from autonomous_agent_builder.api.routes.dispatch import _run_dispatch

    await _run_dispatch(task_id)

    async with factory() as db:
        refreshed = await db.get(Task, task_id)

    assert refreshed is not None
    assert dispatched == [task_id]
    assert refreshed.status == TaskStatus.BLOCKED
    assert "follow-up cycle detected" in str(refreshed.blocked_reason)
