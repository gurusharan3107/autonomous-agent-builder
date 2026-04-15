"""Tests for dashboard API — board/metrics/approval JSON shapes."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
class TestBoardEndpoint:
    """Test /api/dashboard/board response shape."""

    async def test_board_empty(self, client, test_db):
        resp = await client.get("/api/dashboard/board")
        assert resp.status_code == 200
        data = resp.json()
        assert "pending" in data
        assert "active" in data
        assert "review" in data
        assert "done" in data
        assert "blocked" in data
        assert all(isinstance(data[k], list) for k in data)

    async def test_board_pending_task(self, client, test_db):
        proj = await client.post(
            "/api/projects/", json={"name": "board-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Board feature"},
        )
        await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Board task"},
        )
        resp = await client.get("/api/dashboard/board")
        data = resp.json()
        assert len(data["pending"]) == 1
        task_item = data["pending"][0]
        assert task_item["title"] == "Board task"
        assert task_item["status"] == "pending"
        assert "feature_title" in task_item
        assert "cost_usd" in task_item
        assert "total_cost" in task_item

    async def test_board_task_item_shape(self, client, test_db):
        proj = await client.post(
            "/api/projects/", json={"name": "shape-proj", "language": "python"}
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Shape feature"},
        )
        await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Shape task"},
        )
        resp = await client.get("/api/dashboard/board")
        task_item = resp.json()["pending"][0]
        expected_fields = {
            "id", "title", "status", "feature_title",
            "agent_name", "cost_usd", "total_cost",
            "num_turns", "duration_ms", "approval_gate_id",
            "blocked_reason",
        }
        assert set(task_item.keys()) == expected_fields


@pytest.mark.asyncio
class TestMetricsEndpoint:
    """Test /api/dashboard/metrics response shape."""

    async def test_metrics_empty(self, client, test_db):
        resp = await client.get("/api/dashboard/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost"] == 0
        assert data["total_tokens"] == 0
        assert data["total_runs"] == 0
        assert data["gate_pass_rate"] == 0
        assert data["runs"] == []

    async def test_metrics_response_shape(self, client, test_db):
        resp = await client.get("/api/dashboard/metrics")
        data = resp.json()
        expected_fields = {
            "total_cost", "total_tokens", "total_runs",
            "gate_pass_rate", "runs",
        }
        assert set(data.keys()) == expected_fields


@pytest.mark.asyncio
class TestApprovalDetailsEndpoint:
    """Test /api/dashboard/approvals/{gate_id} response shape."""

    async def test_approval_not_found(self, client, test_db):
        resp = await client.get("/api/dashboard/approvals/bad-id")
        assert resp.status_code == 404

    async def test_approval_details_shape(self, client, test_db):
        """Create entities to test approval details endpoint."""
        # Create project → feature → task
        proj = await client.post(
            "/api/projects/",
            json={"name": "approval-proj", "language": "python"},
        )
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Approval feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Approval task"},
        )
        task_id = task.json()["id"]

        # Create an approval gate directly via DB
        _, factory = test_db
        from autonomous_agent_builder.db.models import ApprovalGate

        async with factory() as session:
            gate = ApprovalGate(task_id=task_id, gate_type="planning")
            session.add(gate)
            await session.flush()
            gate_id = gate.id
            await session.commit()

        resp = await client.get(f"/api/dashboard/approvals/{gate_id}")
        assert resp.status_code == 200
        data = resp.json()

        expected_fields = {
            "gate_id", "gate_type", "gate_status",
            "task_id", "task_title", "task_status", "task_description",
            "feature_title", "project_name",
            "thread", "runs", "gate_results",
        }
        assert set(data.keys()) == expected_fields
        assert data["gate_type"] == "planning"
        assert data["task_title"] == "Approval task"
        assert isinstance(data["thread"], list)
        assert isinstance(data["runs"], list)
        assert isinstance(data["gate_results"], list)
