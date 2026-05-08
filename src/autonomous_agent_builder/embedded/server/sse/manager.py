"""SSE event manager for real-time dashboard updates.

Manages event queues for connected clients and broadcasts events
to all active connections.
"""

from __future__ import annotations

import asyncio
from typing import Any


class SSEEventManager:
    """Manages Server-Sent Events for real-time updates.
    
    This manager maintains a list of active client queues and broadcasts
    events to all connected clients. Each client gets its own queue to
    handle backpressure independently.
    """
    
    def __init__(self):
        """Initialize the SSE event manager."""
        self._clients: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()
    
    async def register(self, queue: asyncio.Queue) -> None:
        """Register a new client queue.
        
        Args:
            queue: Client's event queue
        """
        async with self._lock:
            self._clients.append(queue)
    
    async def unregister(self, queue: asyncio.Queue) -> None:
        """Unregister a client queue.
        
        Args:
            queue: Client's event queue to remove
        """
        async with self._lock:
            if queue in self._clients:
                self._clients.remove(queue)
    
    async def broadcast(self, event_type: str, data: dict[str, Any]) -> None:
        """Broadcast an event to all connected clients.
        
        Args:
            event_type: Type of event (task_update, gate_result, etc.)
            data: Event data payload
        """
        event = {
            "type": event_type,
            "data": data,
        }
        
        async with self._lock:
            # Send to all clients, but don't block if a queue is full
            for queue in self._clients:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Client is not consuming fast enough, skip this event
                    pass
    
    def client_count(self) -> int:
        """Get the number of connected clients.
        
        Returns:
            Number of active client connections
        """
        return len(self._clients)


# Global SSE manager instance
_sse_manager: SSEEventManager | None = None


def get_sse_manager() -> SSEEventManager:
    """Get the global SSE manager instance.
    
    Returns:
        SSE event manager singleton
    """
    global _sse_manager
    if _sse_manager is None:
        _sse_manager = SSEEventManager()
    return _sse_manager


async def broadcast_event(event_type: str, data: dict[str, Any]) -> None:
    """Broadcast an event to all connected clients.
    
    Convenience function for broadcasting events without directly
    accessing the manager.
    
    Args:
        event_type: Type of event (task_update, gate_result, agent_progress, board_update)
        data: Event data payload
        
    Examples:
        >>> await broadcast_event("task_update", {
        ...     "task_id": "123",
        ...     "status": "in_progress",
        ...     "updated_at": "2024-01-15T10:30:00Z",
        ... })
    """
    manager = get_sse_manager()
    await manager.broadcast(event_type, data)
