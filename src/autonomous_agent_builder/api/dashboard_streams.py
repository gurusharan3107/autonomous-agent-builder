"""Server-sent event streams for board and approval dashboard surfaces."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import structlog

log = structlog.get_logger()


StreamQueue = asyncio.Queue[dict[str, Any]]


class DashboardStreamHub:
    """Track board and approval SSE subscribers and broadcast payload snapshots."""

    def __init__(self) -> None:
        self._board_clients: set[StreamQueue] = set()
        self._approval_clients: dict[str, set[StreamQueue]] = {}
        self._onboarding_clients: set[StreamQueue] = set()
        self._lock = asyncio.Lock()

    async def register_board(self) -> StreamQueue:
        queue: StreamQueue = asyncio.Queue(maxsize=20)
        async with self._lock:
            self._board_clients.add(queue)
        return queue

    async def unregister_board(self, queue: StreamQueue) -> None:
        async with self._lock:
            self._board_clients.discard(queue)

    async def register_approval(self, gate_id: str) -> StreamQueue:
        queue: StreamQueue = asyncio.Queue(maxsize=20)
        async with self._lock:
            self._approval_clients.setdefault(gate_id, set()).add(queue)
        return queue

    async def register_onboarding(self) -> StreamQueue:
        queue: StreamQueue = asyncio.Queue(maxsize=20)
        async with self._lock:
            self._onboarding_clients.add(queue)
        return queue

    async def unregister_approval(self, gate_id: str, queue: StreamQueue) -> None:
        async with self._lock:
            clients = self._approval_clients.get(gate_id)
            if not clients:
                return
            clients.discard(queue)
            if not clients:
                self._approval_clients.pop(gate_id, None)

    async def unregister_onboarding(self, queue: StreamQueue) -> None:
        async with self._lock:
            self._onboarding_clients.discard(queue)

    async def publish_board(self, payload: Mapping[str, Any]) -> None:
        await self._publish(self._board_clients, payload, event_name="board.snapshot")

    async def publish_approval(self, gate_id: str, payload: Mapping[str, Any]) -> None:
        async with self._lock:
            clients = set(self._approval_clients.get(gate_id, set()))
        await self._publish(clients, payload, event_name="approval.snapshot", gate_id=gate_id)

    async def publish_onboarding(self, payload: Mapping[str, Any]) -> None:
        async with self._lock:
            clients = set(self._onboarding_clients)
        await self._publish(clients, payload, event_name="onboarding.snapshot")

    async def _publish(
        self,
        clients: set[StreamQueue],
        payload: Mapping[str, Any],
        *,
        event_name: str,
        gate_id: str | None = None,
    ) -> None:
        event = {
            "event": "snapshot",
            "data": dict(payload),
        }
        dropped = 0
        for queue in clients:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dropped += 1

        log.info(
            "dashboard_stream_broadcast",
            event_name=event_name,
            gate_id=gate_id,
            clients=len(clients),
            dropped=dropped,
        )


_dashboard_stream_hub: DashboardStreamHub | None = None


def get_dashboard_stream_hub() -> DashboardStreamHub:
    global _dashboard_stream_hub
    if _dashboard_stream_hub is None:
        _dashboard_stream_hub = DashboardStreamHub()
    return _dashboard_stream_hub
