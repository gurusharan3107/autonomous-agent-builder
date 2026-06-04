"""Agent recovery-dispatch route regressions."""

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
    Sprint,
    Task,
    TaskPhase,
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
async def test_recover_and_keep_going_uses_model_to_recover_and_dispatch(
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
            title="Quick todo status filters",
            description="Current sprint filter work.",
            status=FeatureStatus.IN_PROGRESS,
            item_type=BacklogItemType.FEATURE,
        )
        db.add(feature)
        await db.flush()
        failed_task = Task(
            feature_id=feature.id,
            title="Implement core app behavior for Quick todo status filters",
            description="Failed integration task.",
            status=TaskStatus.FAILED,
            phase=TaskPhase.INTEGRATION,
            blocked_reason="Integration failed: could not fast-forward task branch.",
        )
        later_pending_task = Task(
            feature_id=feature.id,
            title="Cover persistence and tests for Quick todo status filters",
            description="Must wait for failed implementation recovery.",
            status=TaskStatus.PENDING,
        )
        db.add_all([failed_task, later_pending_task])
        await db.flush()
        db.add(
            Sprint(
                project_id=project.id,
                label="Sprint 3",
                phase="blocked",
                approved_feature_ids=[feature.id],
                generated_task_ids=[failed_task.id, later_pending_task.id],
            )
        )
        await db.commit()
        failed_task_id = failed_task.id
        pending_task_id = later_pending_task.id

    runtime_prompts: list[str] = []

    class FakeRuntime:
        name = "claude"

        async def run(self, prompt, **kwargs):
            runtime_prompts.append(prompt)
            recover_permission = await kwargs["can_use_tool"](
                "mcp__builder__task_recover",
                {"task_id": failed_task_id},
                {},
            )
            assert getattr(recover_permission, "behavior", "") == "allow"
            await kwargs["on_tool_event"](
                {
                    "tool_name": "mcp__builder__task_recover",
                    "tool_input": {"task_id": failed_task_id},
                    "tool_response": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "status": "ok",
                                        "task_id": failed_task_id,
                                        "previous_status": "failed",
                                        "current_status": "build_verify",
                                    }
                                ),
                            }
                        ],
                        "metadata": {"exit_code": 0},
                    },
                    "tool_use_id": "tool-recover-direct-start",
                }
            )
            dispatch_permission = await kwargs["can_use_tool"](
                "mcp__builder__task_dispatch",
                {"task_id": failed_task_id},
                {},
            )
            assert getattr(dispatch_permission, "behavior", "") == "allow"
            await kwargs["on_tool_event"](
                {
                    "tool_name": "mcp__builder__task_dispatch",
                    "tool_input": {"task_id": failed_task_id},
                    "tool_response": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "status": "dispatched",
                                        "task_id": failed_task_id,
                                        "current_status": "build_verify",
                                    }
                                ),
                            }
                        ],
                        "metadata": {"exit_code": 0},
                    },
                    "tool_use_id": "tool-dispatch-direct-start",
                }
            )
            return RunResult(
                session_id="sdk-session-recover-and-keep-going",
                cost_usd=0.01,
                tokens_input=12,
                tokens_output=8,
                num_turns=1,
                output_text="I recovered and dispatched the blocked Board task.",
            )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeRuntime())

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "Please recover this and keep going until it is shipped."},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
        )

    async with factory() as db:
        pending = await db.get(Task, pending_task_id)
        status_result = await db.execute(
            select(ChatEvent).where(
                ChatEvent.session_id == session_id,
                ChatEvent.event_type == "run_status",
            )
        )
        stop_reasons = [
            event.payload_json.get("stop_reason") for event in status_result.scalars().all()
        ]

    assert runtime_prompts
    assert "mcp__builder__task_recover" in runtime_prompts[0]
    assert "Model-backed delivery context is active for this turn." in runtime_prompts[0]
    assert any(
        item["type"] == "tool_result"
        and item["payload"].get("tool_name") == "mcp__builder__task_recover"
        for item in history_payload["items"]
    )
    assert pending is not None
    assert pending.status == TaskStatus.PENDING
    assert "recovered and dispatched" in assistant_item["payload"]["content"]
    assert "task_dispatched" in stop_reasons
    assert "task_recovered_and_dispatched" not in stop_reasons


@pytest.mark.asyncio
async def test_plain_keep_going_lets_model_recover_and_dispatch_blocked_task(
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
            title="Quick todo status filters",
            description="Current sprint filter work.",
            status=FeatureStatus.IN_PROGRESS,
            item_type=BacklogItemType.FEATURE,
        )
        db.add(feature)
        await db.flush()
        failed_task = Task(
            feature_id=feature.id,
            title="Verify Quick todo status filters for shipping",
            description="Interrupted integration verification task.",
            status=TaskStatus.FAILED,
            phase=TaskPhase.INTEGRATION,
            blocked_reason="Agent run was interrupted before reporting runtime evidence.",
        )
        db.add(failed_task)
        await db.flush()
        db.add(
            Sprint(
                project_id=project.id,
                label="Sprint 3",
                phase="blocked",
                approved_feature_ids=[feature.id],
                generated_task_ids=[failed_task.id],
            )
        )
        await db.commit()
        failed_task_id = failed_task.id

    runtime_prompts: list[str] = []

    class FakeRuntime:
        name = "claude"

        async def run(self, prompt, **kwargs):
            runtime_prompts.append(prompt)
            recover_permission = await kwargs["can_use_tool"](
                "mcp__builder__task_recover",
                {"task_id": failed_task_id},
                {},
            )
            assert getattr(recover_permission, "behavior", "") == "allow"
            await kwargs["on_tool_event"](
                {
                    "tool_name": "mcp__builder__task_recover",
                    "tool_input": {"task_id": failed_task_id},
                    "tool_response": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "status": "ok",
                                        "task_id": failed_task_id,
                                        "previous_status": "failed",
                                        "current_status": "build_verify",
                                    }
                                ),
                            }
                        ],
                        "metadata": {"exit_code": 0},
                    },
                    "tool_use_id": "tool-recover-1",
                }
            )
            dispatch_permission = await kwargs["can_use_tool"](
                "mcp__builder__task_dispatch",
                {"task_id": failed_task_id},
                {},
            )
            assert getattr(dispatch_permission, "behavior", "") == "allow"
            await kwargs["on_tool_event"](
                {
                    "tool_name": "mcp__builder__task_dispatch",
                    "tool_input": {"task_id": failed_task_id},
                    "tool_response": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "status": "dispatched",
                                        "task_id": failed_task_id,
                                        "current_status": "build_verify",
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
                session_id="sdk-session-plain-keep-going-recovery",
                cost_usd=0.01,
                tokens_input=12,
                tokens_output=8,
                num_turns=1,
                output_text="I recovered and dispatched the blocked Board task.",
            )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeRuntime())

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "Keep going until it is shipped."},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        history_payload, _assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
        )

    assert runtime_prompts
    assert "mcp__builder__task_recover" in runtime_prompts[0]
    assert "Model-backed delivery context is active for this turn." in runtime_prompts[0]
    assert not any(item["type"] == "tool_approval_request" for item in history_payload["items"])
    assert any(
        item["type"] == "tool_result"
        and item["payload"].get("tool_name") == "mcp__builder__task_recover"
        for item in history_payload["items"]
    )
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
