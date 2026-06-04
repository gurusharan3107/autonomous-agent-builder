"""Agent sprint-start and queue route regressions."""

from __future__ import annotations

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import (
    ChatEvent,
    Feature,
    FeatureStatus,
    Project,
    Sprint,
    Task,
    TaskStatus,
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
@pytest.mark.parametrize("prompt", ["Go ahead.", "start"])
async def test_go_ahead_dispatches_first_pending_sprint_task_without_manual_board(
    prompt, monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )

    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Todo filters and counts",
            description="Filter todos by completion state.",
            status=FeatureStatus.SPRINT_PLANNED,
            priority=80,
            acceptance_criteria=["Users can filter all, active, and completed todos."],
        )
        db.add(feature)
        await db.flush()
        task = Task(
            feature_id=feature.id,
            title="Implement core app behavior for Todo filters and counts",
            description="Add filter state and counters.",
            status=TaskStatus.PENDING,
        )
        older_feature = Feature(
            project_id=project.id,
            title="Older setup work",
            description="Seeded setup task.",
            status=FeatureStatus.PLANNING,
            priority=10,
        )
        db.add(older_feature)
        await db.flush()
        db.add(
            Task(
                feature_id=older_feature.id,
                title="Older pending setup task",
                description="Should not be dispatched before the active sprint task.",
                status=TaskStatus.PENDING,
            )
        )
        db.add(task)
        await db.flush()
        db.add(
            Sprint(
                project_id=project.id,
                label="Sprint 1",
                approved_feature_ids=[feature.id],
                generated_task_ids=[task.id],
            )
        )
        await db.commit()
        task_id = task.id

    captured_prompts: list[str] = []

    async def fake_run_phase(self, **kwargs):
        captured_prompts.append(str(kwargs["prompt"]))
        dispatch_permission = await kwargs["can_use_tool"](
            "mcp__builder__task_dispatch",
            {"task_id": task_id},
            {},
        )
        assert getattr(dispatch_permission, "behavior", "") == "allow"
        assert getattr(dispatch_permission, "updated_input", {}) == {"task_id": task_id}
        await kwargs["on_tool_event"](
            {
                "tool_name": "mcp__builder__task_dispatch",
                "tool_input": {"task_id": task_id},
                "tool_response": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "status": "dispatched",
                                    "task_id": task_id,
                                    "current_status": "implementation",
                                }
                            ),
                        }
                    ],
                    "metadata": {"exit_code": 0},
                },
                "tool_use_id": "tool-dispatch-go-ahead",
            }
        )
        return RunResult(
            session_id="sdk-session-go-ahead",
            cost_usd=0.01,
            tokens_input=9,
            tokens_output=7,
            num_turns=1,
            output_text="Started work on browser-visible proof.",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)
    monkeypatch.setattr(
        agent_sprint_planning, "schedule_task_dispatch", fake_schedule_task_dispatch
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/agent/chat", json={"message": prompt})
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Started work on" in item["payload"].get("content", ""),
        )
        status_events = []
        for _ in range(20):
            async with factory() as db:
                status_result = await db.execute(
                    select(ChatEvent).where(
                        ChatEvent.session_id == session_id,
                        ChatEvent.event_type == "run_status",
                    )
                )
                status_events = [
                    event
                    for event in status_result.scalars().all()
                    if event.payload_json.get("stop_reason") == "task_dispatched"
                ]
            if status_events:
                break
            await asyncio.sleep(0.05)

    assert captured_prompts
    assert "helpful AI assistant" in captured_prompts[0]
    assert "current sprint task" not in assistant_item["payload"]["content"]
    assert "browser-visible proof" in assistant_item["payload"]["content"]
    assert status_events
    assert status_events[0].payload_json["tokens_used"] == 0
    assert status_events[0].payload_json["cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_chat_start_next_sprint_infers_first_ready_backlog_item_without_scope_prompt(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )

    async with factory() as db:
        project = Project(name="todo app", description="personal todo app", language="typescript")
        db.add(project)
        await db.flush()
        db.add(
            Feature(
                id="feature-01",
                project_id=project.id,
                title="Todo Creation And Editing",
                description="done",
                priority=100,
                status=FeatureStatus.DONE,
            )
        )
        db.add(
            Feature(
                id="feature-02",
                project_id=project.id,
                title="Local Browser Persistence",
                description="done",
                priority=90,
                status=FeatureStatus.DONE,
                dependencies=["feature-01"],
            )
        )
        db.add(
            Feature(
                id="feature-03",
                project_id=project.id,
                title="Today List View",
                description="next ready feature",
                priority=80,
                dependencies=["feature-01", "feature-02"],
            )
        )
        db.add(
            Feature(
                id="feature-04",
                project_id=project.id,
                title="Completion Workflow",
                description="later feature",
                priority=70,
                dependencies=["feature-03"],
            )
        )
        await db.commit()

    async def fail_run_phase(self, **kwargs):
        raise AssertionError("Next sprint inference should stay in the deterministic chat lane.")

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fail_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)
    monkeypatch.setattr(
        agent_sprint_planning, "schedule_task_dispatch", fake_schedule_task_dispatch
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/agent/chat", json={"message": "I want to start next sprint"}
        )
        assert first.status_code == 200
        session_id = first.json()["session_id"]
        await _approve_pending_sprint_scope(client, session_id)
        history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: (
                "Builder prepared the work" in item["payload"].get("content", "")
            ),
        )
        features_response = await client.get("/api/dashboard/features")

    assert "Today List View" in assistant_item["payload"]["content"]
    assert dispatched
    history_items = history_payload["items"]
    assert not any(item["type"] == "ask_user_question" for item in history_items)
    statuses = {
        feature["id"]: feature["status"] for feature in features_response.json()["features"]
    }
    assert statuses["feature-03"] == FeatureStatus.SPRINT_PLANNED.value
    assert statuses["feature-04"] == FeatureStatus.BACKLOG.value


@pytest.mark.asyncio
async def test_chat_ambiguous_go_ahead_asks_for_sprint_scope_before_mutating(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )

    async with factory() as db:
        project = Project(name="todo app", description="personal todo app", language="typescript")
        db.add(project)
        await db.flush()
        db.add(
            Feature(
                id="feature-03",
                project_id=project.id,
                title="Today List View",
                description="next ready feature",
                priority=80,
            )
        )
        await db.commit()

    async def fail_run_phase(self, **kwargs):
        raise AssertionError("Ambiguous continuation should use the deterministic question lane.")

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fail_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)
    monkeypatch.setattr(
        agent_sprint_planning, "schedule_task_dispatch", fake_schedule_task_dispatch
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/agent/chat", json={"message": "Can you go ahead?"})
        assert first.status_code == 200
        session_id = first.json()["session_id"]
        _history_payload, prompt_item = await _wait_for_history_item(
            client,
            session_id,
            "ask_user_question",
            predicate=lambda item: item["payload"].get("header") == "Delivery Scope",
        )
        features_response = await client.get("/api/dashboard/features")

    assert prompt_item["payload"]["options"][0]["label"].startswith(
        "Ship this improvement: feature-03"
    )
    statuses = {
        feature["id"]: feature["status"] for feature in features_response.json()["features"]
    }
    assert statuses["feature-03"] == FeatureStatus.BACKLOG.value


@pytest.mark.asyncio
async def test_chat_sprint_planning_direct_queue_all_product_backlog_items_creates_sprint_tasks(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )

    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        db.add(
            Feature(
                project_id=project.id, title="Backlog item one", description="one", priority=100
            )
        )
        db.add(
            Feature(project_id=project.id, title="Backlog item two", description="two", priority=90)
        )
        await db.commit()

    async def fail_run_phase(self, **kwargs):
        raise AssertionError("Direct sprint queueing should use the deterministic chat lane.")

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fail_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)
    monkeypatch.setattr(
        agent_sprint_planning, "schedule_task_dispatch", fake_schedule_task_dispatch
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "Queue all current product backlog items for the sprint."},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        await _approve_pending_sprint_scope(client, session_id)
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            timeout=10.0,
            predicate=lambda item: (
                "Builder prepared the work" in item["payload"].get("content", "")
            ),
        )
        board_response = await client.get("/api/dashboard/board")

    board_payload = board_response.json()
    assert len(board_payload["pending"]) == 6
    assert dispatched == [board_payload["pending"][0]["id"]]
    assert board_payload["current_sprint"]["active_phase"] == "implementation"
    assert "work step" not in assistant_item["payload"]["content"]
