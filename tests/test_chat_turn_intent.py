"""Tests for Agent chat-turn intent policy."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from autonomous_agent_builder.db.models import ChatEvent, ChatSession
from autonomous_agent_builder.embedded.server.chat_turn_intent import (
    resolve_chat_turn_intent,
)
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes


def _intent(**overrides):
    values = {
        "agent_name": "chat",
        "active_specialist_present": False,
        "autonomous_continuation_requested": False,
        "ambiguous_continuation_requested": False,
        "dispatchable_task_exists": False,
        "ready_delivery_feature_exists": False,
        "explicit_sprint_planning_intent": False,
        "feature_delivery_message_requested": False,
        "feature_delivery_confirmed": False,
        "session_has_saved_feature_for_delivery": False,
        "session_has_pending_feature_spec": False,
        "session_has_pending_sprint_planning": False,
        "review_approval_continuation_requested": False,
    }
    values.update(overrides)
    return resolve_chat_turn_intent(**values)


def test_model_backed_delivery_context_always_true_for_chat() -> None:
    intent = _intent()

    assert intent.model_backed_delivery_context_requested is True
    assert intent.sprint_planning_requested is False
    assert intent.feature_spec_requested is False


def test_dispatchable_work_uses_model_backed_delivery_context() -> None:
    intent = _intent(dispatchable_task_exists=True)

    assert intent.model_backed_delivery_context_requested is True
    assert intent.sprint_planning_requested is False
    assert intent.feature_spec_requested is False


def test_feature_delivery_followup_wins_without_dispatchable_work() -> None:
    intent = _intent(
        feature_delivery_message_requested=True,
        session_has_saved_feature_for_delivery=True,
        session_has_pending_feature_spec=True,
    )

    assert intent.feature_delivery_followup_requested is True
    assert intent.feature_spec_requested is False
    assert intent.sprint_planning_requested is False


def test_ready_delivery_autonomous_continuation_routes_to_sprint_planning() -> None:
    intent = _intent(
        autonomous_continuation_requested=True,
        ready_delivery_feature_exists=True,
        session_has_pending_feature_spec=True,
    )

    assert intent.sprint_planning_requested is True
    assert intent.feature_spec_requested is False
    assert intent.feature_delivery_followup_requested is False


@pytest.mark.asyncio
async def test_route_wrapper_prefers_delivery_context_for_ready_board_work(
    monkeypatch,
    test_db,
) -> None:
    async def has_dispatchable_task_state(db):
        return True

    async def has_ready_delivery_feature_state(db):
        return False

    async def no_review_approval(db):
        return None

    monkeypatch.setattr(agent_routes, "_has_dispatchable_task_state", has_dispatchable_task_state)
    monkeypatch.setattr(
        agent_routes,
        "_has_ready_delivery_feature_state",
        has_ready_delivery_feature_state,
    )
    monkeypatch.setattr(agent_routes, "_first_pending_review_approval", no_review_approval)

    session = ChatSession(id="session-intent-ready-work")
    session.events = []
    session.messages = []

    intent = await agent_routes._resolve_chat_turn_intent(
        session=session,
        user_message="start shipping",
        agent_name="chat",
        active_specialist=None,
    )

    assert intent.dispatchable_task_exists is True
    assert intent.model_backed_delivery_context_requested is True
    assert intent.feature_spec_requested is False
    assert intent.sprint_planning_requested is False


@pytest.mark.asyncio
async def test_route_wrapper_routes_saved_feature_delivery_followup(
    monkeypatch,
    test_db,
) -> None:
    async def no_dispatchable_task_state(db):
        return False

    async def no_ready_delivery_feature_state(db):
        return False

    async def no_review_approval(db):
        return None

    monkeypatch.setattr(agent_routes, "_has_dispatchable_task_state", no_dispatchable_task_state)
    monkeypatch.setattr(
        agent_routes,
        "_has_ready_delivery_feature_state",
        no_ready_delivery_feature_state,
    )
    monkeypatch.setattr(agent_routes, "_first_pending_review_approval", no_review_approval)

    session = ChatSession(id="session-intent-saved-feature")
    session.events = [
        ChatEvent(
            id="event-saved-feature",
            session_id=session.id,
            event_type="assistant_message",
            payload_json={
                "content": "Feature saved to backlog as `Keyboard shortcuts` in the backlog."
            },
            status="completed",
            created_at=datetime.now(UTC),
        )
    ]
    session.messages = []

    intent = await agent_routes._resolve_chat_turn_intent(
        session=session,
        user_message="start delivery",
        agent_name="chat",
        active_specialist=None,
    )

    assert intent.feature_delivery_followup_requested is True
    assert intent.sprint_planning_requested is False
    assert intent.model_backed_delivery_context_requested is True
