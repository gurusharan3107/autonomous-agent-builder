"""Focused regressions for dispatch follow-up cycle handling."""

from __future__ import annotations

import pytest

from autonomous_agent_builder.db.models import Feature, FeatureStatus, Task, TaskStatus


@pytest.mark.asyncio
async def test_api_dispatch_blocks_same_status_followup_cycle(client, test_db, monkeypatch):
    dispatched: list[str] = []

    async def fake_dispatch(self, task: Task) -> None:
        dispatched.append(task.id)

    monkeypatch.setattr(
        "autonomous_agent_builder.api.routes.dispatch.Orchestrator.dispatch",
        fake_dispatch,
    )

    proj = await client.post(
        "/api/projects/", json={"name": "dispatch-cycle-proj", "language": "python"}
    )
    feat = await client.post(
        f"/api/projects/{proj.json()['id']}/features",
        json={"title": "Dispatch cycle feature"},
    )
    await _queue_feature(test_db, feat.json()["id"])
    task = await client.post(
        f"/api/features/{feat.json()['id']}/tasks",
        json={"title": "Stuck dispatch task"},
    )
    task_id = task.json()["id"]

    from autonomous_agent_builder.api.routes.dispatch import _run_dispatch

    await _run_dispatch(task_id)

    _, factory = test_db
    async with factory() as db:
        refreshed = await db.get(Task, task_id)

    assert refreshed is not None
    assert dispatched == [task_id]
    assert refreshed.status == TaskStatus.BLOCKED
    assert "follow-up cycle detected" in str(refreshed.blocked_reason)


async def _queue_feature(test_db, feature_id: str) -> None:
    _, factory = test_db
    async with factory() as db:
        feature = await db.get(Feature, feature_id)
        feature.status = FeatureStatus.QUEUED
        await db.commit()
