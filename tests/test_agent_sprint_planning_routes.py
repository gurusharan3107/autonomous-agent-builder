"""Agent sprint-planning route regressions."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from autonomous_agent_builder.db.models import (
    Feature,
    FeatureStatus,
    Project,
)
from autonomous_agent_builder.embedded.server import agent_sprint_planning
from autonomous_agent_builder.embedded.server.app import create_app
from tests.agent_route_test_support import (
    approve_pending_sprint_scope as _approve_pending_sprint_scope,
)
from tests.agent_route_test_support import (
    wait_for_history_item as _wait_for_history_item,
)


@pytest.mark.asyncio
async def test_chat_sprint_planning_recommends_one_feature_and_creates_task_breakdown(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        db.add(
            Feature(
                id="feature-blocked",
                project_id=project.id,
                title="Dependent future item",
                description="future",
                priority=120,
                dependencies=["feature-missing"],
            )
        )
        db.add(
            Feature(
                project_id=project.id,
                title="Already selected sprint item",
                description="existing sprint work",
                priority=110,
                status=FeatureStatus.SPRINT_BACKLOG,
            )
        )
        db.add(Feature(project_id=project.id, title="Backlog item one", description="one", priority=100))
        db.add(Feature(project_id=project.id, title="Backlog item two", description="two", priority=90))
        await db.commit()

    async def fail_run_phase(self, **kwargs):
        raise AssertionError("Sprint planning should run through the deterministic agent chat lane.")

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fail_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_sprint_planning, "schedule_task_dispatch", fake_schedule_task_dispatch)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/agent/chat", json={"message": "I want to do sprint planning."})
        assert first.status_code == 200
        session_id = first.json()["session_id"]
        _history_payload, prompt_item = await _wait_for_history_item(
            client,
            session_id,
            "ask_user_question",
            predicate=lambda item: item["payload"].get("header") == "Delivery Scope",
        )
        recommended_label = prompt_item["payload"]["options"][0]["label"]
        assert recommended_label.startswith("Ship this improvement:")
        assert "Dependent future item" not in recommended_label
        assert "Keeps delivery focused on one shippable outcome" in prompt_item["payload"]["options"][0]["description"]
        assert prompt_item["payload"]["options"][1]["label"] == "Ship all ready improvements"

        selection = await client.post(
            "/api/agent/chat/respond",
            json={
                "session_id": session_id,
                "event_id": prompt_item["id"],
                "selected_options": [recommended_label],
            },
        )
        assert selection.status_code == 200
        board_before_approval = await client.get("/api/dashboard/board")
        assert board_before_approval.json()["pending"] == []
        await _approve_pending_sprint_scope(client, session_id)
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Builder prepared the work" in item["payload"].get("content", ""),
        )
        features_response = await client.get("/api/dashboard/features")
        board_response = await client.get("/api/dashboard/board")

    feature_payload = features_response.json()
    queued_features = {feature["title"]: feature["status"] for feature in feature_payload["features"]}
    assert queued_features["Backlog item one"] == FeatureStatus.SPRINT_PLANNED.value
    assert queued_features["Backlog item two"] == FeatureStatus.BACKLOG.value
    assert queued_features["Dependent future item"] == FeatureStatus.BACKLOG.value
    assert queued_features["Already selected sprint item"] == FeatureStatus.SPRINT_BACKLOG.value
    board_payload = board_response.json()
    assert len(board_payload["pending"]) == 3
    assert {item["feature_title"] for item in board_payload["pending"]} == {"Backlog item one"}
    assert dispatched == [board_payload["pending"][0]["id"]]
    assert board_payload["current_sprint"]["active_phase"] == "implementation"
    assert board_payload["current_sprint"]["phase_statuses"]["implementation"] == "active"
    assert "work step" not in assistant_item["payload"]["content"]

@pytest.mark.asyncio
async def test_chat_sprint_planning_named_feature_requires_scope_approval_before_tasks(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        project = Project(name="demo", description="demo", language="javascript")
        db.add(project)
        await db.flush()
        db.add(Feature(project_id=project.id, title="Backlog item one", description="one", priority=100))
        db.add(Feature(project_id=project.id, title="Backlog item two", description="two", priority=90))
        await db.commit()

    async def fail_run_phase(self, **kwargs):
        raise AssertionError("Sprint planning should use deterministic dashboard lifecycle.")

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fail_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_sprint_planning, "schedule_task_dispatch", fake_schedule_task_dispatch)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": 'Plan Sprint 1 for the backlog item "Backlog item one" only.'},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _history_payload, approval_item = await _wait_for_history_item(
            client,
            session_id,
            "tool_approval_request",
            predicate=lambda item: item["payload"].get("tool_name") == "Delivery scope approval",
        )
        board_before_approval = await client.get("/api/dashboard/board")
        assert board_before_approval.json()["pending"] == []

        denial = await client.post(
            "/api/agent/chat/respond",
            json={
                "session_id": session_id,
                "event_id": approval_item["id"],
                "decision": "deny",
                "reason": "Review the scope first.",
            },
        )
        assert denial.status_code == 200
        await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Delivery scope was not approved" in item["payload"].get("content", ""),
        )
        board_after_denial = await client.get("/api/dashboard/board")

    assert board_after_denial.json()["pending"] == []
