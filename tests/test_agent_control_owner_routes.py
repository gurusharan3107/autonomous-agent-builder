from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from autonomous_agent_builder.db.models import (
    ChatEvent,
    ChatSession,
    Feature,
    FeatureStatus,
    Project,
)
from autonomous_agent_builder.embedded.server import agent_chat_sessions, agent_sprint_planning
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes


async def _wait_for_history_item(
    client: AsyncClient,
    session_id: str,
    item_type: str,
    *,
    timeout: float = 3.0,
    predicate=None,
):
    deadline = asyncio.get_running_loop().time() + timeout
    found_payload = None
    found_item = None
    while asyncio.get_running_loop().time() < deadline:
        response = await client.get("/api/agent/chat/history", params={"session_id": session_id})
        assert response.status_code == 200
        payload = response.json()
        for item in payload["items"]:
            if item["type"] == item_type and (predicate is None or predicate(item)):
                if item_type not in {"assistant_message", "run_error"}:
                    return payload, item
                found_payload = payload
                found_item = item
                status = payload.get("status") or {}
                if status.get("running") is not True and status.get("stop_reason") not in {
                    "completed_after_running_status",
                }:
                    return payload, item
        await asyncio.sleep(0.05)
    if found_payload is not None and found_item is not None:
        return found_payload, found_item
    raise AssertionError(f"Timed out waiting for history item type '{item_type}'")


@pytest.mark.asyncio
async def test_chat_history_supersedes_voice_summary_echo_for_pending_delivery_question(
    test_db,
    tmp_path,
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        assistant = ChatEvent(
            session_id=session.id,
            event_type="assistant_message",
            payload_json={
                "content": "Ready for Builder to start now, or should I hold?",
                "final": True,
            },
            status="completed",
        )
        db.add(assistant)
        await db.flush()
        question = ChatEvent(
            session_id=session.id,
            event_type="ask_user_question",
            payload_json={
                "question": "Ready for Builder to start this improvement?",
                "answered": False,
                "answer_value": "",
                "source": "assistant_delivery_permission_prompt",
                "assistant_event_id": assistant.id,
            },
            status="pending",
        )
        summary = ChatEvent(
            session_id=session.id,
            event_type="voice_final_summary",
            payload_json={
                "summary": "Ready for Builder to start now, or should I hold?",
                "assistant_event_id": assistant.id,
            },
            status="completed",
        )
        db.add_all([question, summary])
        await db.flush()
        notification = ChatEvent(
            session_id=session.id,
            event_type="voice_completion_notification",
            payload_json={"voice_final_summary_event_id": summary.id},
            status="completed",
        )
        db.add(notification)
        await db.flush()
        session_id = session.id
        question_id = question.id
        summary_id = summary.id
        notification_id = notification.id
        await db.commit()

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/agent/chat/history", params={"session_id": session_id})

    assert response.status_code == 200
    item_types = [item["type"] for item in response.json()["items"]]
    assert "ask_user_question" in item_types
    assert "voice_final_summary" not in item_types

    async with factory() as db:
        superseded = await db.get(ChatEvent, summary_id)
        notification = await db.get(ChatEvent, notification_id)
    assert superseded.status == "superseded"
    assert superseded.payload_json["superseded_by_event_id"] == question_id
    assert superseded.payload_json["superseded_reason"] == (
        "pending_decision_controls_operator_response"
    )
    assert notification.status == "superseded"
    assert notification.payload_json["superseded_by_event_id"] == question_id
    assert notification.payload_json["superseded_reason"] == (
        "pending_decision_controls_operator_response"
    )


@pytest.mark.asyncio
async def test_assistant_delivery_permission_answer_uses_captured_feature(
    monkeypatch,
    test_db,
    tmp_path,
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        project = Project(name="todo-app", description="Todo app", language="javascript")
        db.add(project)
        await db.flush()
        stale_feature = Feature(
            project_id=project.id,
            title="Highlight overdue active todos",
            description="Older ready work.",
            status=FeatureStatus.BACKLOG,
            priority=50,
            acceptance_criteria=["Older work remains available"],
        )
        captured_feature = Feature(
            project_id=project.id,
            title="Show current filter todo count",
            description="Display a compact count for the active todo filter.",
            status=FeatureStatus.BACKLOG,
            priority=50,
            acceptance_criteria=["The count updates when the active filter changes"],
        )
        session = ChatSession(
            repo_identity=str(tmp_path.resolve()),
            workspace_cwd=str(tmp_path.resolve()),
        )
        db.add_all([stale_feature, captured_feature, session])
        await db.flush()
        assistant = ChatEvent(
            session_id=session.id,
            event_type="assistant_message",
            payload_json={
                "content": (
                    "Add a compact count beside the existing filter tabs. "
                    "I captured that improvement as `Show current filter todo count`. "
                    "Ready for Builder to start now, or should I hold?"
                ),
                "final": True,
            },
            status="completed",
        )
        db.add(assistant)
        await db.flush()
        question = ChatEvent(
            session_id=session.id,
            event_type="ask_user_question",
            payload_json={
                "header": "Start Work?",
                "question": "Ready for Builder to start this improvement?",
                "options": [{"label": "Start now", "description": "Start the work."}],
                "answered": False,
                "answer_value": "",
                "source": "assistant_delivery_permission_prompt",
                "assistant_event_id": assistant.id,
            },
            status="pending",
        )
        db.add(question)
        await db.commit()
        session_id = session.id
        question_id = question.id
        captured_feature_id = captured_feature.id
        stale_feature_id = stale_feature.id

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
        answer = await client.post(
            "/api/agent/chat/respond",
            json={
                "session_id": session_id,
                "event_id": question_id,
                "selected_options": ["Start now"],
            },
        )
        assert answer.status_code == 200
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Delivery has started" in item["payload"].get("content", ""),
        )

    assert "Show current filter todo count" in assistant_item["payload"]["content"]
    async with factory() as db:
        approval_result = await db.execute(
            select(ChatEvent)
            .where(ChatEvent.session_id == session_id)
            .where(ChatEvent.event_type == "tool_approval_request")
        )
        plan_result = await db.execute(
            select(ChatEvent)
            .where(ChatEvent.session_id == session_id)
            .where(ChatEvent.event_type == "delivery_plan_created")
        )
        approvals = [
            event
            for event in approval_result.scalars().all()
            if event.payload_json.get("tool_name") == "Delivery scope approval"
        ]
        plan_event = plan_result.scalar_one()

    assert approvals == []
    assert plan_event.payload_json["feature_ids"] == [captured_feature_id]
    assert stale_feature_id not in plan_event.payload_json["feature_ids"]
    assert dispatched


@pytest.mark.asyncio
async def test_chat_history_supersedes_redundant_delivery_scope_approval(
    test_db,
    tmp_path,
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        project = Project(name="todo-app", description="Todo app", language="javascript")
        captured_feature = Feature(
            project=project,
            title="Show current filter todo count",
            description="Show active filter count",
            status=FeatureStatus.BACKLOG,
            priority=80,
        )
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add_all([project, captured_feature, session])
        await db.flush()
        assistant = ChatEvent(
            session_id=session.id,
            event_type="assistant_message",
            payload_json={
                "content": (
                    "I captured that improvement as `Show current filter todo count`. "
                    "Ready for Builder to start now, or should I hold?"
                ),
                "final": True,
            },
            status="completed",
        )
        db.add(assistant)
        await db.flush()
        question = ChatEvent(
            session_id=session.id,
            event_type="ask_user_question",
            payload_json={
                "question": "Ready for Builder to start this improvement?",
                "answered": True,
                "answer_value": "Start now",
                "source": "assistant_delivery_permission_prompt",
                "assistant_event_id": assistant.id,
            },
            status="answered",
        )
        approval = ChatEvent(
            session_id=session.id,
            event_type="tool_approval_request",
            payload_json={
                "tool_name": "Delivery scope approval",
                "summary": "Approve this improvement before work starts",
                "tool_input": {"feature_ids": [captured_feature.id]},
            },
            status="pending",
        )
        db.add_all([question, approval])
        await db.flush()
        session_id = session.id
        question_id = question.id
        approval_id = approval.id
        await db.commit()

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/agent/chat/history", params={"session_id": session_id})

    assert response.status_code == 200
    item_types = [item["type"] for item in response.json()["items"]]
    assert "tool_approval_request" not in item_types

    async with factory() as db:
        superseded = await db.get(ChatEvent, approval_id)
    assert superseded.status == "superseded"
    assert superseded.payload_json["superseded_by_event_id"] == question_id
    assert superseded.payload_json["superseded_reason"] == (
        "delivery_permission_answer_controls_delivery_start"
    )
