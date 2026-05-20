"""Persistence helpers for Agent-page chat events."""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.models import ChatEvent, ChatMessage, ChatSession, utcnow
from autonomous_agent_builder.db.session import get_session_factory
from autonomous_agent_builder.embedded.server import agent_chat_transcript
from autonomous_agent_builder.embedded.server.chat_state import ChatSessionHub
from autonomous_agent_builder.services.voice_completion_digest import AgentVoiceDigestService


async def append_chat_event(
    session_id: str,
    *,
    event_type: str,
    payload: dict[str, Any],
    status: str = "completed",
    tool_use_id: str | None = None,
    response_to_event_id: str | None = None,
    mirror_message: tuple[str, str, int, float] | None = None,
) -> ChatEvent:
    session_factory = get_session_factory()
    for attempt in range(5):
        try:
            async with session_factory() as db:
                session = await db.get(ChatSession, session_id)
                if session is None:
                    raise RuntimeError(f"Chat session '{session_id}' not found")

                session.updated_at = utcnow()
                event = ChatEvent(
                    session_id=session_id,
                    event_type=event_type,
                    payload_json=payload,
                    status=status,
                    tool_use_id=tool_use_id,
                    response_to_event_id=response_to_event_id,
                )
                db.add(event)
                if mirror_message is not None:
                    role, content, tokens_used, cost_usd = mirror_message
                    db.add(
                        ChatMessage(
                            session_id=session_id,
                            role=role,
                            content=content,
                            tokens_used=tokens_used,
                            cost_usd=cost_usd,
                        )
                    )
                await db.commit()
                await db.refresh(event)
                return event
        except OperationalError as exc:
            if "database is locked" not in str(exc).lower() or attempt == 4:
                raise
            await asyncio.sleep(0.1 * (attempt + 1))
    raise RuntimeError("Unable to append chat event after retry")


async def append_voice_final_summary_if_needed(
    session_id: str,
    *,
    assistant_event_id: str,
    content: str,
    hub: ChatSessionHub,
) -> ChatEvent | None:
    """Persist the SDK-backed Agent completion summary for Realtime voice."""
    session_factory = get_session_factory()
    async with session_factory() as db:
        voice_request_result = await db.execute(
            select(ChatEvent)
            .where(ChatEvent.session_id == session_id)
            .where(ChatEvent.event_type == "user_message")
            .order_by(ChatEvent.created_at.desc())
            .limit(20)
        )
        voice_request = next(
            (
                event
                for event in voice_request_result.scalars().all()
                if (event.payload_json or {}).get("speaker") == "realtime_voice_ai"
                and (event.payload_json or {}).get("target") == "sdk_backed_agent"
            ),
            None,
        )
        pending_control_result = await db.execute(
            select(ChatEvent)
            .where(ChatEvent.session_id == session_id)
            .where(ChatEvent.event_type.in_(("ask_user_question", "tool_approval_request")))
            .where(ChatEvent.status == "pending")
        )
        pending_control = pending_control_result.scalars().first()
    if voice_request is None:
        return None
    if pending_control is not None:
        return None
    digest_service = AgentVoiceDigestService()
    payload = digest_service.build_digest_payload(
        session_id=session_id,
        assistant_event_id=assistant_event_id,
        content=content,
        voice_request_event_id=voice_request.id,
    )
    event = await append_chat_event(
        session_id,
        event_type="voice_final_summary",
        payload=payload,
        status=digest_service.event_status(payload["outcome"]),
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(event).model_dump(mode="json"))
    return event


async def update_request_event(
    db: AsyncSession,
    event: ChatEvent,
    *,
    payload_patch: dict[str, Any],
    status: str,
    answer_event_type: str,
    answer_payload: dict[str, Any],
) -> ChatEvent:
    event_payload = dict(event.payload_json or {})
    event_payload.update(payload_patch)
    event.payload_json = event_payload
    event.status = status

    session = await db.get(ChatSession, event.session_id)
    if session is not None:
        session.updated_at = utcnow()

    db.add(
        ChatEvent(
            session_id=event.session_id,
            event_type=answer_event_type,
            payload_json=answer_payload,
            status="completed",
            response_to_event_id=event.id,
        )
    )
    await db.commit()
    await db.refresh(event)
    return event
