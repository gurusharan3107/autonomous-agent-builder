"""Agent feature-spec backlog and follow-up route regressions."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import (
    FeatureStatus,
    Project,
    Task,
)
from autonomous_agent_builder.embedded.server import agent_sprint_planning
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from tests.agent_route_test_support import (
    approve_pending_sprint_scope as _approve_pending_sprint_scope,
)
from tests.agent_route_test_support import (
    wait_for_history_item as _wait_for_history_item,
)


@pytest.mark.asyncio
async def test_chat_feature_spec_request_creates_backlog_feature(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        db.add(Project(name="demo", description="demo", language="python"))
        await db.commit()

    async def fake_run_phase(self, **kwargs):
        return RunResult(
            session_id="sdk-session-feature-spec-create",
            cost_usd=0.02,
            tokens_input=8,
            tokens_output=12,
            num_turns=1,
            output_text=(
                "AGREEMENT: Add bookmark support as one bounded feature.\n\n"
                'FEATURE_SPEC_JSON: {"title":"Post bookmarks","description":"Allow signed-in '
                'users to save posts and review them from profile pages.","priority":77,'
                '"acceptance_criteria":["Users can bookmark and unbookmark a post",'
                '"Users can open a bookmarks list from their profile"],'
                '"dependencies":["Existing Flask-Login session flow"]}'
            ),
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)
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
            json={"message": "Create a bounded feature spec for post bookmarks."},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "I captured that improvement" in item["payload"].get("content", ""),
        )
        features_response = await client.get("/api/dashboard/features")
        feature_payload = features_response.json()
        created_feature = next(feature for feature in feature_payload["features"] if feature["title"] == "Post bookmarks")
        tasks_response = await client.get(f"/api/features/{created_feature['id']}/tasks")

    assert "I captured that improvement as `Post bookmarks`." in assistant_item["payload"]["content"]
    payload = feature_payload
    assert any(feature["title"] == "Post bookmarks" for feature in payload["features"])
    assert created_feature["priority"] == "77"
    assert "bookmark and unbookmark a post" in created_feature["description"]
    assert tasks_response.json() == []
    assert dispatched == []
    assert any(item["type"] == "assistant_message" for item in history_payload["items"])

@pytest.mark.asyncio
async def test_chat_natural_feature_request_routes_into_feature_backlog_lane(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        db.add(Project(name="demo", description="demo", language="python"))
        await db.commit()

    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured.update(kwargs)
        return RunResult(
            session_id="sdk-session-natural-feature-route",
            cost_usd=0.02,
            tokens_input=8,
            tokens_output=12,
            num_turns=1,
            output_text=(
                "AGREEMENT: Add bookmark support as one bounded feature.\n\n"
                'FEATURE_SPEC_JSON: {"title":"Post bookmarks","description":"Allow signed-in '
                'users to save posts and review them from profile pages.","priority":77,'
                '"acceptance_criteria":["Users can bookmark and unbookmark a post",'
                '"Users can open a bookmarks list from their profile"],'
                '"dependencies":["Existing Flask-Login session flow"]}'
            ),
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)
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
            json={
                "message": (
                    "I want users to be able to bookmark posts and see their bookmarks "
                    "from their profile. Can you take this through the next steps?"
                )
            },
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "I captured that improvement" in item["payload"].get("content", ""),
        )
        features_response = await client.get("/api/dashboard/features")
        feature_payload = features_response.json()
        created_feature = next(feature for feature in feature_payload["features"] if feature["title"] == "Post bookmarks")
        tasks_response = await client.get(f"/api/features/{created_feature['id']}/tasks")

    assert captured["subagents"] is None
    assert "FEATURE_SPEC_JSON:" in str(captured["prompt"])
    assert "Documentation routing is active for this turn." not in str(captured["prompt"])
    payload = feature_payload
    assert any(feature["title"] == "Post bookmarks" for feature in payload["features"])
    tasks = tasks_response.json()
    assert tasks == []
    assert dispatched == []
    assert "I captured that improvement as `Post bookmarks`." in assistant_item["payload"]["content"]
    assert "Ready for Builder to start now" not in assistant_item["payload"]["content"]

@pytest.mark.asyncio
async def test_chat_saved_feature_delivery_followup_routes_through_sprint_backlog_and_queue_approval(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        db.add(Project(name="demo", description="demo", language="python"))
        await db.commit()

    async def fake_run_phase(self, **kwargs):
        return RunResult(
            session_id="sdk-session-feature-followup",
            cost_usd=0.02,
            tokens_input=8,
            tokens_output=12,
            num_turns=1,
            output_text=(
                "AGREEMENT: Add one focused regression test.\n\n"
                'FEATURE_SPEC_JSON: {"title":"__html__ escaping regression",'
                '"description":"Confirm trusted HTML representation is not double escaped.",'
                '"priority":82,'
                '"acceptance_criteria":["One focused regression test covers __html__ escaping"],'
                '"dependencies":[]}'
            ),
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)
    monkeypatch.setattr(agent_sprint_planning, "schedule_task_dispatch", fake_schedule_task_dispatch)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/agent/chat",
            json={"message": "Create a feature spec for __html__ escaping regression."},
        )
        assert first.status_code == 200
        session_id = first.json()["session_id"]
        await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "I captured that improvement" in item["payload"].get("content", ""),
        )

        async def fail_run_phase(self, **kwargs):
            raise AssertionError("Saved feature delivery follow-up should not invoke Claude.")

        monkeypatch.setattr(
            "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
            fail_run_phase,
        )
        second = await client.post(
            "/api/agent/chat",
            json={
                "message": "Ship this saved feature now. Create the delivery task and dispatch it.",
                "session_id": session_id,
            },
        )
        assert second.status_code == 200
        await _approve_pending_sprint_scope(client, session_id)
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Builder prepared the work" in item["payload"].get("content", ""),
        )
        features_response = await client.get("/api/dashboard/features")
        feature_payload = features_response.json()
        created_feature = next(
            feature
            for feature in feature_payload["features"]
            if feature["title"] == "__html__ escaping regression"
        )
        tasks_response = await client.get(f"/api/features/{created_feature['id']}/tasks")
        task_result = await db.execute(select(Task).where(Task.feature_id == created_feature["id"]))
        task_rows = list(task_result.scalars().all())

    tasks = tasks_response.json()
    assert len(tasks) == 3
    assert {task["title"] for task in tasks} == {
        "Implement core app behavior for __html__ escaping regression",
        "Cover persistence and tests for __html__ escaping regression",
        "Verify __html__ escaping regression for shipping",
    }
    assert all(task.depends_on["sprint_execution"]["skip_task_planning"] is True for task in task_rows)
    assert all(task.depends_on["sprint_execution"]["skip_task_design"] is True for task in task_rows)
    assert dispatched == [task_rows[0].id]
    assert created_feature["status"] == FeatureStatus.SPRINT_PLANNED.value
    assert "sprint-plan" not in assistant_item["payload"]["content"]
    assert "task" not in assistant_item["payload"]["content"].lower()
    assert "Delivery has started." in assistant_item["payload"]["content"]

@pytest.mark.asyncio
async def test_chat_feature_spec_can_use_ask_user_question_and_resume_to_feature_save(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        db.add(Project(name="demo", description="demo", language="python"))
        await db.commit()

    async def fake_run_phase(self, **kwargs):
        permission = await kwargs["can_use_tool"](
            "AskUserQuestion",
            {
                "questions": [
                    {
                        "header": "Bookmarks",
                        "question": "Where should bookmarks appear on the profile?",
                        "options": [
                            {
                                "label": "Dedicated tab",
                                "description": "Clearer first release and simpler routing. (Recommended)",
                            },
                            {
                                "label": "Activity feed",
                                "description": "Mix bookmarks into the existing profile activity stream.",
                            },
                        ],
                        "multiSelect": False,
                    }
                ]
            },
            {},
        )
        updated_input = getattr(permission, "updated_input", None) or getattr(
            permission, "updatedInput", None
        )
        assert updated_input["answers"]["Where should bookmarks appear on the profile?"] == "Dedicated tab"
        return RunResult(
            session_id="sdk-session-feature-question",
            cost_usd=0.03,
            tokens_input=10,
            tokens_output=16,
            num_turns=2,
            output_text=(
                "AGREEMENT: Add private post bookmarking with a dedicated profile tab.\n\n"
                'FEATURE_SPEC_JSON: {"title":"Private Post Bookmarks","description":"Allow '
                'signed-in users to bookmark posts privately and review them from a dedicated '
                'Bookmarks tab on their own profile.","priority":80,'
                '"acceptance_criteria":["Users can bookmark and unbookmark a post",'
                '"Users can open a dedicated Bookmarks tab from their own profile"],'
                '"dependencies":[]}'
            ),
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)
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
            json={
                "message": (
                    "I want users to be able to bookmark posts and see their bookmarks "
                    "from their profile. Can you take this through the next steps?"
                )
            },
        )
        session_id = response.json()["session_id"]

        _, question_item = await _wait_for_history_item(client, session_id, "ask_user_question")
        assert question_item["status"] == "pending"
        assert question_item["payload"]["recommended_index"] == 0

        answer = await client.post(
            "/api/agent/chat/respond",
            json={
                "session_id": session_id,
                "event_id": question_item["id"],
                "selected_options": ["Dedicated tab"],
            },
        )
        assert answer.status_code == 200

        history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "I captured that improvement" in item["payload"].get("content", ""),
        )
        features_response = await client.get("/api/dashboard/features")
        feature_payload = features_response.json()
        created_feature = next(
            feature for feature in feature_payload["features"] if feature["title"] == "Private Post Bookmarks"
        )
        tasks_response = await client.get(f"/api/features/{created_feature['id']}/tasks")

    updated_question = next(item for item in history_payload["items"] if item["id"] == question_item["id"])
    assert updated_question["payload"]["answered"] is True
    assert updated_question["payload"]["answer_value"] == "Dedicated tab"
    tasks = tasks_response.json()
    assert tasks == []
    assert dispatched == []
    assert "I captured that improvement as `Private Post Bookmarks`." in assistant_item["payload"]["content"]
    assert "Ready for Builder to start now" not in assistant_item["payload"]["content"]
