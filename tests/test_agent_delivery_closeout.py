"""Tests for Agent delivery closeout helpers."""

from __future__ import annotations

from autonomous_agent_builder.db.models import AgentRun, ChatEvent, ChatSession, utcnow
from autonomous_agent_builder.embedded.server.agent_delivery_closeout import (
    DELIVERY_SHIPPED_CLOSEOUT_PREFIX,
    delivery_plan_id_from_session,
    run_token_totals,
    session_has_delivery_closeout,
)


def test_delivery_plan_id_from_session_prefers_structured_event() -> None:
    session = ChatSession(
        events=[
            ChatEvent(
                id="event-plan",
                session_id="session-1",
                event_type="delivery_plan_created",
                payload_json={"plan_id": "sprint-plan-1"},
                status="completed",
                created_at=utcnow(),
            )
        ]
    )

    assert delivery_plan_id_from_session(session) == "sprint-plan-1"


def test_session_has_delivery_closeout_detects_assistant_message() -> None:
    session = ChatSession(
        events=[
            ChatEvent(
                id="event-closeout",
                session_id="session-1",
                event_type="assistant_message",
                payload_json={"content": f"{DELIVERY_SHIPPED_CLOSEOUT_PREFIX}`Feature`."},
                status="completed",
                created_at=utcnow(),
            )
        ]
    )

    assert session_has_delivery_closeout(session) is True


def test_run_token_totals_counts_raw_cached_and_noncached_plus_output() -> None:
    raw_tokens, cached_tokens, noncached_plus_output = run_token_totals(
        [
            AgentRun(tokens_input=120, tokens_output=10, tokens_cached=100),
            AgentRun(tokens_input=80, tokens_output=5, tokens_cached=70),
        ]
    )

    assert raw_tokens == 215
    assert cached_tokens == 170
    assert noncached_plus_output == 45
