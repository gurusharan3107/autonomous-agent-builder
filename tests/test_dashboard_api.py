"""Tests for dashboard API — board/metrics/approval JSON shapes."""

from __future__ import annotations

from datetime import UTC, datetime

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
            "approval_gate_type", "pending_approval_count",
            "blocked_reason", "latest_run_status", "updated_at",
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

    async def test_metrics_include_agent_chat_runs(self, client, test_db):
        _, factory = test_db
        from autonomous_agent_builder.db.models import ChatEvent, ChatSession

        async with factory() as session:
            chat = ChatSession()
            session.add(chat)
            await session.flush()
            session.add_all(
                [
                    ChatEvent(
                        session_id=chat.id,
                        event_type="run_status",
                        payload_json={
                            "running": True,
                            "current_turn": 0,
                            "tokens_used": 0,
                            "cost_usd": 0.0,
                        },
                        status="running",
                    ),
                    ChatEvent(
                        session_id=chat.id,
                        event_type="run_status",
                        payload_json={
                            "running": False,
                            "current_turn": 3,
                            "tokens_used": 321,
                            "cost_usd": 0.42,
                        },
                        status="completed",
                    ),
                ]
            )
            await session.commit()

        resp = await client.get("/api/dashboard/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cost"] == pytest.approx(0.42)
        assert data["total_tokens"] == 321
        assert data["total_runs"] == 1
        assert len(data["runs"]) == 1
        assert data["runs"][0]["agent_name"] == "agent-chat"
        assert data["runs"][0]["task_id"]
        assert data["runs"][0]["num_turns"] == 3
        assert data["runs"][0]["status"] == "completed"


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

    async def test_approval_details_tolerates_mixed_datetime_awareness(self, client, test_db):
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

        _, factory = test_db
        from autonomous_agent_builder.db.models import AgentRun, Approval, ApprovalDecision, ApprovalGate

        async with factory() as session:
            gate = ApprovalGate(task_id=task_id, gate_type="planning")
            session.add(gate)
            await session.flush()
            session.add(
                AgentRun(
                    task_id=task_id,
                    agent_name="planner",
                    started_at=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
                    completed_at=datetime(2026, 4, 23, 12, 1, tzinfo=UTC),
                    cost_usd=0.01,
                    num_turns=1,
                    duration_ms=1000,
                    status="completed",
                )
            )
            session.add(
                Approval(
                    approval_gate_id=gate.id,
                    approver_email="operator@example.com",
                    decision=ApprovalDecision.APPROVE,
                    comment="Looks good",
                    created_at=datetime(2026, 4, 23, 12, 2),
                )
            )
            gate_id = gate.id
            await session.commit()

        resp = await client.get(f"/api/dashboard/approvals/{gate_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert [entry["role"] for entry in data["thread"]] == ["agent", "human"]


@pytest.mark.asyncio
class TestDashboardUtilityEndpoints:
    async def test_shell_summary_includes_pending_gate_and_questions(self, client, test_db):
        proj = await client.post("/api/projects/", json={"name": "shell-proj", "language": "python"})
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Shell feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Shell task"},
        )
        task_id = task.json()["id"]

        _, factory = test_db
        from autonomous_agent_builder.db.models import ApprovalGate, ChatEvent, ChatSession

        async with factory() as session:
            chat_session = ChatSession(repo_identity="repo", workspace_cwd="cwd")
            session.add(chat_session)
            await session.flush()
            session.add(ApprovalGate(task_id=task_id, gate_type="planning", status="pending"))
            session.add(
                ChatEvent(
                    session_id=chat_session.id,
                    event_type="ask_user_question",
                    status="pending",
                    payload_json={"question": "Need approval?"},
                )
            )
            await session.commit()

        resp = await client.get("/api/dashboard/shell-summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pending_approvals"] == 1
        assert data["pending_questions"] == 1
        assert "running_label" in data
        assert isinstance(data["todo_snapshots"], list)

    async def test_inbox_returns_latest_run_context(self, client, test_db):
        proj = await client.post("/api/projects/", json={"name": "inbox-proj", "language": "python"})
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Inbox feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Inbox task"},
        )
        task_id = task.json()["id"]

        _, factory = test_db
        from autonomous_agent_builder.db.models import AgentRun, ApprovalGate

        async with factory() as session:
            gate = ApprovalGate(task_id=task_id, gate_type="design", status="pending")
            session.add(gate)
            session.add(
                AgentRun(
                    task_id=task_id,
                    agent_name="designer",
                    status="completed",
                    num_turns=3,
                    duration_ms=2400,
                    cost_usd=0.02,
                )
            )
            await session.commit()

        resp = await client.get("/api/dashboard/inbox")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["gate_type"] == "design"
        assert data[0]["latest_run_agent"] == "designer"
        assert data[0]["approval_url"].startswith("/approvals/")

    async def test_compare_returns_both_runs(self, client, test_db):
        proj = await client.post("/api/projects/", json={"name": "compare-proj", "language": "python"})
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Compare feature"},
        )
        task = await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Compare task"},
        )
        task_id = task.json()["id"]

        _, factory = test_db
        from autonomous_agent_builder.db.models import AgentRun

        async with factory() as session:
            left = AgentRun(task_id=task_id, agent_name="baseline", status="completed", cost_usd=0.01, num_turns=2)
            right = AgentRun(task_id=task_id, agent_name="variant", status="completed", cost_usd=0.03, num_turns=4)
            session.add_all([left, right])
            await session.flush()
            left_id = left.id
            right_id = right.id
            await session.commit()

        resp = await client.get(
            f"/api/dashboard/compare?left_run_id={left_id}&right_run_id={right_id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["same_task"] is True
        assert data["left"]["agent_name"] == "baseline"
        assert data["right"]["agent_name"] == "variant"

    async def test_command_index_returns_routes_and_task_actions(self, client, test_db):
        proj = await client.post("/api/projects/", json={"name": "command-proj", "language": "python"})
        feat = await client.post(
            f"/api/projects/{proj.json()['id']}/features",
            json={"title": "Command feature"},
        )
        await client.post(
            f"/api/features/{feat.json()['id']}/tasks",
            json={"title": "Dispatch me"},
        )

        resp = await client.get("/api/dashboard/command-index")
        assert resp.status_code == 200
        data = resp.json()
        labels = {item["label"] for item in data["items"]}
        assert "Agent" in labels
        assert "Board" in labels
        assert "Compare" in labels
        assert "Dispatch me" in labels
