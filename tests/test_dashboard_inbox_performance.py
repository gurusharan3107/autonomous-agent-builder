"""Focused dashboard inbox query regressions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event

from autonomous_agent_builder.db.models import (
    AgentRun,
    ApprovalGate,
    Feature,
    FeatureStatus,
    Project,
    Task,
    TaskStatus,
)


@pytest.mark.asyncio
async def test_command_index_bounds_approval_loading_for_large_history(client, test_db):
    engine, factory = test_db
    base_time = datetime(2026, 5, 20, 6, 0, tzinfo=UTC)
    async with factory() as session:
        project = Project(
            name="large-inbox-proj",
            description="Large approval history",
            language="python",
        )
        session.add(project)
        await session.flush()
        feature = Feature(
            project_id=project.id,
            title="Large inbox feature",
            description="Command index should stay bounded",
            status=FeatureStatus.QUEUED,
        )
        session.add(feature)
        await session.flush()
        tasks = [
            Task(
                feature_id=feature.id,
                title=f"Approval task {index}",
                description="Historical approval",
                status=TaskStatus.PENDING,
            )
            for index in range(500)
        ]
        session.add_all(tasks)
        await session.flush()
        session.add_all(
            [
                ApprovalGate(
                    task_id=task.id,
                    gate_type="design",
                    status="pending",
                    created_at=base_time + timedelta(seconds=index),
                )
                for index, task in enumerate(tasks)
            ]
        )
        session.add(
            AgentRun(
                task_id=tasks[-1].id,
                agent_name="designer",
                status="completed",
                started_at=base_time + timedelta(days=1),
            )
        )
        await session.commit()

    resp, select_count = await _count_selects_for(
        engine,
        client.get("/api/dashboard/command-index"),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    approval_items = [item for item in items if item["kind"] == "approval"]
    assert len(approval_items) == 8
    assert any("Approval task 499" in item["label"] for item in approval_items)
    assert all("Approval task 0" not in item["label"] for item in approval_items)
    assert select_count <= 12

    from autonomous_agent_builder.embedded.server.routes.dashboard import (
        _load_inbox_response as load_embedded_inbox_response,
    )

    async def load_embedded_items():
        async with factory() as session:
            return await load_embedded_inbox_response(session, limit=8)

    embedded_items, embedded_select_count = await _count_selects_for(
        engine,
        load_embedded_items(),
    )
    assert len(embedded_items) == 8
    assert any(item.task_title == "Approval task 499" for item in embedded_items)
    assert all(item.task_title != "Approval task 0" for item in embedded_items)
    assert embedded_select_count <= 8


async def _count_selects_for(engine, awaitable):
    select_count = 0

    def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        nonlocal select_count
        if statement.lstrip().lower().startswith("select"):
            select_count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_selects)
    try:
        result = await awaitable
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_selects)
    return result, select_count
