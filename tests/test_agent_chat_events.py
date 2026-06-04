"""Agent chat event persistence regressions."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from autonomous_agent_builder.db.models import ChatEvent, ChatMessage, ChatSession
from autonomous_agent_builder.embedded.server.agent_chat_events import (
    append_chat_event,
    update_request_event,
)


@pytest.mark.asyncio
async def test_append_chat_event_can_mirror_transcript_message(test_db):
    _, factory = test_db
    async with factory() as db:
        session = ChatSession(repo_identity="repo", workspace_cwd="repo")
        db.add(session)
        await db.commit()
        session_id = session.id

    event = await append_chat_event(
        session_id,
        event_type="assistant_message",
        payload={"content": "Done"},
        mirror_message=("assistant", "Done", 17, 0.02),
    )

    assert event.event_type == "assistant_message"
    async with factory() as db:
        message_result = await db.execute(
            select(ChatMessage).where(ChatMessage.session_id == session_id)
        )
        message = message_result.scalar_one()

    assert message.role == "assistant"
    assert message.content == "Done"
    assert message.tokens_used == 17
    assert message.cost_usd == 0.02


@pytest.mark.asyncio
async def test_update_request_event_uses_request_session(test_db):
    _, factory = test_db
    async with factory() as db:
        session = ChatSession(repo_identity="repo", workspace_cwd="repo")
        db.add(session)
        await db.flush()
        request_event = ChatEvent(
            session_id=session.id,
            event_type="ask_user_question",
            payload_json={"answered": False},
            status="pending",
        )
        db.add(request_event)
        await db.commit()
        event_id = request_event.id

    async with factory() as db:
        event = await db.get(ChatEvent, event_id)
        assert event is not None
        updated = await update_request_event(
            db,
            event,
            payload_patch={"answered": True, "answer_value": "Yes"},
            status="answered",
            answer_event_type="ask_user_question_answer",
            answer_payload={"answer_value": "Yes"},
        )

    assert updated.status == "answered"
    assert updated.payload_json["answered"] is True
    async with factory() as db:
        answer_result = await db.execute(
            select(ChatEvent)
            .where(ChatEvent.response_to_event_id == event_id)
            .where(ChatEvent.event_type == "ask_user_question_answer")
        )
        answer = answer_result.scalar_one()

    assert answer.payload_json == {"answer_value": "Yes"}
