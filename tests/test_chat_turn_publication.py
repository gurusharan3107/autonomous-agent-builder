"""Tests for Agent chat-turn publication helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from autonomous_agent_builder.db.models import ChatEvent, utcnow
from autonomous_agent_builder.embedded.server.chat_turn_publication import (
    ChatTurnPublisher,
    terminal_run_status_payload,
)


@dataclass(frozen=True)
class _SerializedEvent:
    payload: dict[str, Any]

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


class _Hub:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, session_id: str, payload: dict[str, Any]) -> None:
        self.published.append((session_id, payload))


def _serialize_event(event: ChatEvent) -> _SerializedEvent:
    return _SerializedEvent(
        {
            "id": event.id,
            "type": event.event_type,
            "status": event.status,
            "payload": event.payload_json,
        }
    )


def test_terminal_run_status_payload_preserves_optional_stop_reason() -> None:
    payload = terminal_run_status_payload(
        runtime_metadata={"model": "gpt-5", "runtime_sdk": "codex_sdk"},
        max_turns=4,
        stop_reason="review_approved_and_dispatched",
    )

    assert payload == {
        "model": "gpt-5",
        "runtime_sdk": "codex_sdk",
        "running": False,
        "current_turn": 0,
        "max_turns": 4,
        "tokens_used": 0,
        "cost_usd": 0.0,
        "stop_reason": "review_approved_and_dispatched",
    }


def test_terminal_run_status_payload_omits_empty_stop_reason() -> None:
    payload = terminal_run_status_payload(
        runtime_metadata={"model": "gpt-5"},
        max_turns=2,
    )

    assert "stop_reason" not in payload
    assert payload["running"] is False
    assert payload["tokens_used"] == 0


@pytest.mark.asyncio
async def test_publisher_records_terminal_assistant_response_and_status() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def append_chat_event(session_id: str, **kwargs: Any) -> ChatEvent:
        calls.append((session_id, kwargs))
        return ChatEvent(
            id=f"event-{len(calls)}",
            session_id=session_id,
            event_type=kwargs["event_type"],
            payload_json=kwargs["payload"],
            status=kwargs["status"],
            created_at=utcnow(),
        )

    hub = _Hub()
    publisher = ChatTurnPublisher(
        session_id="session-1",
        hub=hub,
        runtime_metadata={"model": "gpt-5", "effort": "medium"},
        max_turns=3,
        append_chat_event=append_chat_event,
        serialize_event=_serialize_event,
    )

    await publisher.publish_terminal_assistant_response(
        "Approved review and started build verification.",
        stop_reason="review_approved_and_dispatched",
    )

    assert [call[1]["event_type"] for call in calls] == [
        "assistant_message",
        "run_status",
    ]
    assert calls[0][1]["payload"] == {
        "content": "Approved review and started build verification.",
        "final": True,
    }
    assert calls[0][1]["mirror_message"] == (
        "assistant",
        "Approved review and started build verification.",
        0,
        0.0,
    )
    assert calls[1][1]["payload"]["stop_reason"] == "review_approved_and_dispatched"
    assert [payload["type"] for _, payload in hub.published] == [
        "assistant_message",
        "run_status",
    ]


@pytest.mark.asyncio
async def test_publisher_records_terminal_error_and_status() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def append_chat_event(session_id: str, **kwargs: Any) -> ChatEvent:
        calls.append((session_id, kwargs))
        return ChatEvent(
            id=f"event-{len(calls)}",
            session_id=session_id,
            event_type=kwargs["event_type"],
            payload_json=kwargs["payload"],
            status=kwargs["status"],
            created_at=utcnow(),
        )

    hub = _Hub()
    publisher = ChatTurnPublisher(
        session_id="session-1",
        hub=hub,
        runtime_metadata={"model": "gpt-5", "runtime_sdk": "codex_sdk"},
        max_turns=3,
        append_chat_event=append_chat_event,
        serialize_event=_serialize_event,
    )

    await publisher.publish_terminal_error(RuntimeError("provider unavailable"))

    assert [call[1]["event_type"] for call in calls] == ["run_error", "run_status"]
    assert calls[0][1]["payload"] == {"content": "Error: provider unavailable"}
    assert calls[0][1]["mirror_message"] == (
        "assistant",
        "Error: provider unavailable",
        0,
        0.0,
    )
    assert calls[1][1]["payload"] == {
        "model": "gpt-5",
        "runtime_sdk": "codex_sdk",
        "running": False,
        "error": "provider unavailable",
    }
    assert [payload["type"] for _, payload in hub.published] == [
        "run_error",
        "run_status",
    ]


@pytest.mark.asyncio
async def test_publisher_suppresses_empty_stream_delta() -> None:
    async def append_chat_event(session_id: str, **kwargs: Any) -> ChatEvent:
        raise AssertionError("stream deltas do not persist chat events")

    hub = _Hub()
    publisher = ChatTurnPublisher(
        session_id="session-1",
        hub=hub,
        runtime_metadata={},
        max_turns=1,
        append_chat_event=append_chat_event,
        serialize_event=_serialize_event,
    )

    await publisher.publish_stream_delta("")

    assert hub.published == []
