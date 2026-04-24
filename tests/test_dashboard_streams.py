"""Focused SSE verification for board and approval mission-control surfaces."""

from __future__ import annotations

import asyncio

import pytest

from autonomous_agent_builder.api.dashboard_streams import get_dashboard_stream_hub
from autonomous_agent_builder.api.routes.dashboard_api import (
    load_approval_details_response,
    load_board_response,
)
from autonomous_agent_builder.db.models import ApprovalGate, Task, TaskStatus


async def _create_review_gate(client, test_db) -> tuple[str, str]:
    _, session_factory = test_db

    project = await client.post(
        "/api/projects/",
        json={"name": "stream-proj", "language": "python"},
    )
    feature = await client.post(
        f"/api/projects/{project.json()['id']}/features",
        json={"title": "Stream feature"},
    )
    task = await client.post(
        f"/api/features/{feature.json()['id']}/tasks",
        json={"title": "Stream task"},
    )
    task_id = task.json()["id"]

    async with session_factory() as session:
        db_task = await session.get(Task, task_id)
        assert db_task is not None
        db_task.status = TaskStatus.DESIGN_REVIEW
        gate = ApprovalGate(task_id=task_id, gate_type="planning")
        session.add(gate)
        await session.commit()
        await session.refresh(gate)
        return task_id, gate.id


@pytest.mark.asyncio
class TestDashboardStreams:
    async def test_board_stream_pushes_updated_snapshot(self, client, test_db):
        _, gate_id = await _create_review_gate(client, test_db)
        _, session_factory = test_db
        hub = get_dashboard_stream_hub()
        queue = await hub.register_board()

        try:
            async with session_factory() as session:
                initial_board = await load_board_response(session)
                assert len(initial_board.review) == 1
                assert initial_board.active == []

            decision = await client.post(
                f"/api/approval-gates/{gate_id}/approve",
                json={
                    "approver_email": "reviewer@example.com",
                    "decision": "approve",
                    "comment": "Looks good",
                    "reason": "Ready for design",
                },
            )
            assert decision.status_code == 200

            updated = await asyncio.wait_for(queue.get(), timeout=3.0)
            assert updated["event"] == "snapshot"
            updated_board = updated["data"]
            assert updated_board["review"] == []
            assert len(updated_board["active"]) == 1
            assert updated_board["active"][0]["status"] == "design"
        finally:
            await hub.unregister_board(queue)

    async def test_approval_stream_reconnects_with_current_snapshot(self, client, test_db):
        _, gate_id = await _create_review_gate(client, test_db)
        _, session_factory = test_db
        hub = get_dashboard_stream_hub()
        queue = await hub.register_approval(gate_id)

        try:
            async with session_factory() as session:
                initial_payload = await load_approval_details_response(gate_id, session)
                assert initial_payload.gate_status == "pending"
                assert initial_payload.thread == []

            decision = await client.post(
                f"/api/approval-gates/{gate_id}/approve",
                json={
                    "approver_email": "reviewer@example.com",
                    "decision": "approve",
                    "comment": "Approved for implementation",
                    "reason": "Evidence reviewed",
                },
            )
            assert decision.status_code == 200

            updated = await asyncio.wait_for(queue.get(), timeout=3.0)
            assert updated["event"] == "snapshot"
            updated_payload = updated["data"]
            assert updated_payload["gate_status"] == "approve"
            assert len(updated_payload["thread"]) == 1

            async with session_factory() as session:
                reconnect_payload = await load_approval_details_response(gate_id, session)
                assert reconnect_payload.gate_status == "approve"
                assert len(reconnect_payload.thread) == 1
                assert reconnect_payload.thread[0].author == "reviewer@example.com"
        finally:
            await hub.unregister_approval(gate_id, queue)
