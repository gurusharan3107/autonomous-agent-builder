"""Agent chat-turn publication helpers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from autonomous_agent_builder.db.models import ChatEvent, utcnow

AppendChatEvent = Callable[..., Awaitable[ChatEvent]]
SerializeChatEvent = Callable[[ChatEvent], Any]


def terminal_run_status_payload(
    *,
    runtime_metadata: dict[str, Any],
    max_turns: int,
    stop_reason: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        **runtime_metadata,
        "running": False,
        "current_turn": 0,
        "max_turns": max_turns,
        "tokens_used": 0,
        "cost_usd": 0.0,
    }
    if stop_reason:
        payload["stop_reason"] = stop_reason
    return payload


@dataclass(frozen=True)
class ChatTurnPublisher:
    session_id: str
    hub: Any
    runtime_metadata: dict[str, Any]
    max_turns: int
    append_chat_event: AppendChatEvent
    serialize_event: SerializeChatEvent

    async def publish_event(self, event: ChatEvent) -> None:
        await self.hub.publish(
            self.session_id,
            self.serialize_event(event).model_dump(mode="json"),
        )

    async def publish_stream_delta(self, text: str) -> None:
        content = str(text or "")
        if not content:
            return
        await self.hub.publish(
            self.session_id,
            {
                "id": f"stream:{self.session_id}",
                "type": "assistant_stream_delta",
                "status": "streaming",
                "timestamp": utcnow().isoformat(),
                "payload": {"content": content},
            },
        )

    async def publish_terminal_assistant_response(
        self,
        content: str,
        *,
        stop_reason: str | None = None,
    ) -> None:
        assistant_event = await self.append_chat_event(
            self.session_id,
            event_type="assistant_message",
            payload={"content": content, "final": True},
            status="completed",
            mirror_message=("assistant", content, 0, 0.0),
        )
        await self.publish_event(assistant_event)

        status_event = await self.append_chat_event(
            self.session_id,
            event_type="run_status",
            payload=terminal_run_status_payload(
                runtime_metadata=self.runtime_metadata,
                max_turns=self.max_turns,
                stop_reason=stop_reason,
            ),
            status="completed",
        )
        await self.publish_event(status_event)

    async def publish_terminal_error(self, error: Exception) -> None:
        content = f"Error: {error}"
        error_event = await self.append_chat_event(
            self.session_id,
            event_type="run_error",
            payload={"content": content},
            status="completed",
            mirror_message=("assistant", content, 0, 0.0),
        )
        await self.publish_event(error_event)

        status_event = await self.append_chat_event(
            self.session_id,
            event_type="run_status",
            payload={
                **self.runtime_metadata,
                "running": False,
                "error": str(error),
            },
            status="completed",
        )
        await self.publish_event(status_event)
