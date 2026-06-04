"""Agent delivery terminal-status route regressions."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

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
    Sprint,
    Task,
    TaskStatus,
)
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from tests.agent_route_test_support import (
    wait_for_history_item as _wait_for_history_item,
)
from tests.agent_route_test_support import (
    write_forward_engineering_ready_state as _write_forward_engineering_ready_state,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("operator_message", ["Start", "Continue building my app."])
async def test_continue_building_records_terminal_dispatch_status(
    operator_message, monkeypatch, test_db, tmp_path
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
        task = Task(
            feature_id=feature.id,
            title="Existing dispatchable task",
            description="A pending task should make continuation dispatch task work before sprint planning.",
            status=TaskStatus.PENDING,
        )
        db.add(task)
        await db.flush()
        task_id = task.id
        await db.commit()

    captured_prompts: list[str] = []
    captured_sessions: list[str | None] = []

    class FakeRuntime:
        name = "claude"

        async def run(self, *args, **kwargs):
            captured_prompts.append(str(args[0]))
            captured_sessions.append(kwargs.get("session"))
            dispatch_permission = await kwargs["can_use_tool"](
                "mcp__builder__task_dispatch",
                {"task_id": task_id},
                {},
            )
            assert getattr(dispatch_permission, "behavior", "") == "allow"
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
                    "tool_use_id": "tool-dispatch-1",
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

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeRuntime())
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

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
            json={"message": operator_message},
        )
        session_id = response.json()["session_id"]
        await _wait_for_history_item(client, session_id, "assistant_message")

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
    assert captured_prompts
    assert captured_sessions == [None]
    assert (
        "Model-backed delivery context is active" in captured_prompts[0]
        or "Autonomous continuation mode is active" in captured_prompts[0]
    )
    assert (
        "do not treat it as a fixed command or deterministic shortcut" in captured_prompts[0]
        or "Derive the next tool call from your responsibility" in captured_prompts[0]
    )
    if "Model-backed delivery context is active" in captured_prompts[0]:
        assert "dispatch that Board task with `mcp__builder__task_dispatch`" in captured_prompts[0]
        assert "Do not use generic code-editing or shell tools" in captured_prompts[0]
    assert all(event.payload_json["running"] is False for event in dispatch_statuses)
    with_payload = [event for event in dispatch_statuses if "dispatch" in event.payload_json]
    assert with_payload
    assert with_payload[0].payload_json["dispatch"] == {
        "task_id": task_id,
        "status": "dispatched",
        "current_status": "implementation",
    }


@pytest.mark.asyncio
async def test_continue_remaining_verification_task_dispatches_current_sprint_task(
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
        older_feature = Feature(
            project_id=project.id,
            title="Older sprint work",
            description="Should not win when current sprint has active work.",
            status=FeatureStatus.SPRINT_PLANNED,
            item_type=BacklogItemType.FEATURE,
        )
        current_feature = Feature(
            project_id=project.id,
            title="Deterministic tests and build script",
            description="Current sprint verification work.",
            status=FeatureStatus.SPRINT_PLANNED,
            item_type=BacklogItemType.FEATURE,
        )
        db.add_all([older_feature, current_feature])
        await db.flush()
        older_task = Task(
            feature_id=older_feature.id,
            title="Older pending task",
            description="Older sprint task should not preempt current sprint continuation.",
            status=TaskStatus.PENDING,
        )
        current_task = Task(
            feature_id=current_feature.id,
            title="Verify Deterministic tests and build script for shipping",
            description="Current sprint task the operator asked to continue.",
            status=TaskStatus.IMPLEMENTATION,
        )
        db.add_all([older_task, current_task])
        await db.flush()
        db.add_all(
            [
                Sprint(
                    project_id=project.id,
                    label="Sprint 1",
                    phase="implementation",
                    approved_feature_ids=[older_feature.id],
                    generated_task_ids=[older_task.id],
                    created_at=datetime(2026, 5, 12, tzinfo=UTC),
                ),
                Sprint(
                    project_id=project.id,
                    label="Sprint 2",
                    phase="implementation",
                    approved_feature_ids=[current_feature.id],
                    generated_task_ids=[current_task.id],
                    created_at=datetime(2026, 5, 13, tzinfo=UTC),
                ),
            ]
        )
        await db.commit()

    captured_prompts: list[str] = []
    dispatched: list[str] = []

    class FakeRuntime:
        name = "claude"

        async def run(self, *args, **kwargs):
            captured_prompts.append(str(args[0]))
            dispatch_permission = await kwargs["can_use_tool"](
                "mcp__builder__task_dispatch",
                {"task_id": current_task.id},
                {},
            )
            assert getattr(dispatch_permission, "behavior", "") == "allow"
            await kwargs["on_tool_event"](
                {
                    "tool_name": "mcp__builder__task_dispatch",
                    "tool_input": {"task_id": current_task.id},
                    "tool_response": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "status": "dispatched",
                                        "task_id": current_task.id,
                                        "current_status": "implementation",
                                    }
                                ),
                            }
                        ],
                        "metadata": {"exit_code": 0},
                    },
                    "tool_use_id": "tool-dispatch-current-sprint",
                }
            )
            return RunResult(
                session_id="sdk-session-current-sprint-task",
                cost_usd=0.01,
                tokens_input=5,
                tokens_output=7,
                num_turns=1,
                output_text=(
                    "Started work on `Deterministic tests and build script`. "
                    "Builder will continue through implementation, checks, and browser-visible proof."
                ),
            )

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeRuntime())
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
            json={"message": "Continue the remaining verification task."},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Started work on" in item["payload"].get("content", ""),
        )

    async with factory() as db:
        status_result = await db.execute(
            select(ChatEvent).where(
                ChatEvent.session_id == session_id,
                ChatEvent.event_type == "run_status",
            )
        )
        stop_reasons = [
            event.payload_json.get("stop_reason") for event in status_result.scalars().all()
        ]

    assert captured_prompts
    assert "Model-backed delivery context is active for this turn." in captured_prompts[0]
    assert "do not treat it as a fixed command or deterministic shortcut" in captured_prompts[0]
    assert dispatched == []
    assert (
        "Started work on `Deterministic tests and build script`."
        in assistant_item["payload"]["content"]
    )
    assert "current sprint task" not in assistant_item["payload"]["content"]
    assert (
        "There are no product backlog items available for sprint planning."
        not in assistant_item["payload"]["content"]
    )
    assert "task_dispatched" in stop_reasons
