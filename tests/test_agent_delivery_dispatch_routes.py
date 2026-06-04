"""Agent delivery-dispatch route regressions."""

from __future__ import annotations

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import (
    BacklogItemType,
    ChatEvent,
    Feature,
    FeatureStatus,
    Project,
    Task,
)
from autonomous_agent_builder.embedded.server import agent_message_intent
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from tests.agent_route_test_support import (
    wait_for_history_item as _wait_for_history_item,
)
from tests.agent_route_test_support import (
    write_forward_engineering_ready_state as _write_forward_engineering_ready_state,
)


@pytest.mark.asyncio
async def test_continue_building_auto_approves_builder_task_dispatch(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )
    _write_forward_engineering_ready_state(tmp_path)

    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Existing work",
            description="Marks the workspace as past bootstrap for chat continuation.",
            status=FeatureStatus.SPRINT_PLANNED,
            item_type=BacklogItemType.FEATURE,
        )
        db.add(feature)
        await db.flush()
        db.add(
            Task(
                feature_id=feature.id,
                title="Existing dispatchable task",
                description="A pending task should make continuation dispatch task work before sprint planning.",
            )
        )
        await db.commit()

    async def fake_run_phase(self, **kwargs):
        permission = await kwargs["can_use_tool"](
            "mcp__builder__task_dispatch",
            {"task_id": "task-1"},
            {},
        )
        assert getattr(permission, "behavior", "") == "allow"
        assert getattr(permission, "updated_input", {}) == {"task_id": "task-1"}
        await kwargs["on_tool_event"](
            {
                "tool_name": "mcp__builder__task_dispatch",
                "tool_input": {"task_id": "task-1"},
                "tool_response": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "status": "dispatched",
                                    "task_id": "task-1",
                                    "current_status": "implementation",
                                }
                            ),
                        }
                    ],
                    "metadata": {"exit_code": 0},
                },
                "tool_use_id": "tool-dispatch-continue-building",
            }
        )
        return RunResult(
            session_id="sdk-session-task-dispatch-auto",
            cost_usd=0.01,
            tokens_input=4,
            tokens_output=4,
            num_turns=1,
            output_text="Continuing the selected board task.",
        )

    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )
    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "Continue building my app."},
        )
        session_id = response.json()["session_id"]
        history_payload, _ = await _wait_for_history_item(client, session_id, "assistant_message")
        dispatch_statuses = []
        for _ in range(20):
            async with factory() as db:
                result = await db.execute(
                    select(ChatEvent).where(
                        ChatEvent.session_id == session_id,
                        ChatEvent.event_type == "run_status",
                    )
                )
                dispatch_statuses = [
                    event
                    for event in result.scalars().all()
                    if event.payload_json.get("stop_reason") == "task_dispatched"
                ]
            if dispatch_statuses:
                break
            await asyncio.sleep(0.05)

    assert not any(item["type"] == "tool_approval_request" for item in history_payload["items"])
    assert dispatch_statuses


@pytest.mark.asyncio
async def test_ready_delivery_followup_stays_model_backed_and_allows_model_dispatch(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )
    _write_forward_engineering_ready_state(tmp_path)

    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Due dates",
            description="Approved improvement with queued delivery work.",
            status=FeatureStatus.SPRINT_PLANNED,
            item_type=BacklogItemType.FEATURE,
        )
        db.add(feature)
        await db.flush()
        task = Task(
            feature_id=feature.id,
            title="Set up due date model",
            description="A pending task should start from natural operator wording.",
        )
        db.add(task)
        await db.flush()
        task_id = task.id
        await db.commit()

    captured_prompts: list[str] = []

    async def fake_run_phase(self, **kwargs):
        captured_prompts.append(str(kwargs["prompt"]))
        assert (
            agent_message_intent.message_requests_autonomous_continuation(
                "I'm ready for the next safe step."
            )
            is False
        )

        board_permission = await kwargs["can_use_tool"](
            "mcp__builder__board",
            {},
            {},
        )
        assert getattr(board_permission, "behavior", "") == "allow"

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
                "tool_use_id": "tool-dispatch-start-shipping",
            }
        )
        return RunResult(
            session_id="sdk-session-start-shipping",
            cost_usd=0.01,
            tokens_input=4,
            tokens_output=8,
            num_turns=1,
            output_text="Started the first due-date delivery step.",
            stop_reason="completed",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
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
            json={"message": "I'm ready for the next safe step."},
        )
        session_id = response.json()["session_id"]
        history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
        )

    assert captured_prompts
    assert "Model-backed delivery context is active" in captured_prompts[0]
    assert "do not treat it as a fixed command or deterministic shortcut" in captured_prompts[0]
    assert "you choose which tools to call and in what order" in captured_prompts[0]
    assert "Started the first due-date delivery step." in assistant_item["payload"]["content"]
    assert history_payload["status"]["running"] is False

    dispatch_statuses = []
    for _ in range(20):
        async with factory() as db:
            result = await db.execute(
                select(ChatEvent).where(
                    ChatEvent.session_id == session_id,
                    ChatEvent.event_type == "run_status",
                )
            )
            dispatch_statuses = [
                event
                for event in result.scalars().all()
                if event.payload_json.get("stop_reason") == "task_dispatched"
            ]
        if dispatch_statuses:
            break
        await asyncio.sleep(0.05)

    assert dispatch_statuses
