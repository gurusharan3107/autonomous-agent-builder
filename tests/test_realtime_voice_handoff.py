from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import ChatEvent, ChatSession
from autonomous_agent_builder.embedded.server import agent_chat_sessions
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes


@pytest.mark.asyncio
async def test_realtime_text_control_dedupes_running_agent_handoff(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.commit()
        session_id = session.id

    assert await app.state.chat_hub.reserve_run(session_id)

    async def fail_if_run_chat_turn(*_: Any) -> None:
        raise AssertionError("duplicate voice handoff should not start a second run")

    monkeypatch.setattr(agent_routes, "_run_chat_turn", fail_if_run_chat_turn)

    message = "I want to improve the todo app footer."
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/realtime/text-control",
            json={
                "message": message,
                "session_id": session_id,
                "call_id": "rtc_running",
                "fallback_to_agent": True,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    async with factory() as db:
        output_payload = (
            (await db.execute(select(ChatEvent).where(ChatEvent.event_type == "voice_tool_output")))
            .scalar_one()
            .payload_json
        )
    assert payload["handled"] is True
    assert payload["operator_message"] == message
    assert payload["assistant_message"] == "Builder is already working in Conversation.", (
        payload,
        output_payload,
    )
    assert payload["tool_name"] == "delegate_to_builder_agent"
    assert payload["route"] == f"/?session={session_id}&mode=chat"

    async with factory() as db:
        user_events = (
            (await db.execute(select(ChatEvent).where(ChatEvent.event_type == "user_message")))
            .scalars()
            .all()
        )
        output = (
            await db.execute(select(ChatEvent).where(ChatEvent.event_type == "voice_tool_output"))
        ).scalar_one()

    assert user_events == []
    assert output.payload_json["ok"] is True
    assert output.payload_json["completion_status"] == "running"
    assert output.payload_json["result_message"] == "Builder is already working in Conversation."

    await app.state.chat_hub.release_run(session_id)


@pytest.mark.asyncio
async def test_realtime_handoff_permission_prompt_has_single_decision_owner(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async def fake_run_phase(self, **kwargs):
        return RunResult(
            session_id="sdk-permission-from-voice",
            cost_usd=0.01,
            tokens_input=12,
            tokens_output=8,
            num_turns=1,
            output_text=(
                "I captured that improvement as `Show completed todo count in footer`. "
                "Ready for Builder to start now, or should I hold?"
            ),
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/realtime/text-control",
            json={
                "message": "Add a compact completed todo count to the footer.",
                "call_id": "rtc_permission_owner",
                "fallback_to_agent": True,
            },
        )

    assert response.status_code == 200
    session_id = response.json()["route"].split("session=", 1)[1].split("&", 1)[0]

    events: list[ChatEvent] = []
    for _ in range(40):
        async with factory() as db:
            result = await db.execute(
                select(ChatEvent)
                .where(ChatEvent.session_id == session_id)
                .order_by(ChatEvent.created_at.asc())
            )
            events = list(result.scalars().all())
        if any(event.event_type == "ask_user_question" for event in events):
            break
        await asyncio.sleep(0.05)

    event_types = [event.event_type for event in events]
    assert "ask_user_question" in event_types
    assert "voice_final_summary" not in event_types
    assert "voice_completion_notification" not in event_types

    question = next(event for event in events if event.event_type == "ask_user_question")
    assert question.status == "pending"
    assert question.payload_json["source"] == "assistant_delivery_permission_prompt"
    assert question.payload_json["question"] == "Ready for Builder to start this work?"


@pytest.mark.asyncio
async def test_realtime_text_control_prioritizes_navigation_over_status_words(
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.commit()
        session_id = session.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/realtime/text-control",
            json={
                "message": "take me to backlog",
                "call_id": "rtc_nav_backlog",
                "session_id": session_id,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["tool_name"] == "navigate_dashboard"
    assert payload["assistant_message"] == "Opening Backlog."
    assert payload["route"] == "/backlog"

    async with factory() as db:
        event_result = await db.execute(
            select(ChatEvent).where(ChatEvent.event_type == "voice_navigation_request")
        )
        event = event_result.scalar_one()
    assert event.session_id == session_id
    assert event.payload_json["route"] == "/backlog"
    assert event.payload_json["source"] == "realtime_voice"
