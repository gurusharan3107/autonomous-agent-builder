"""Server-Sent Events (SSE) stream endpoint for real-time updates."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from autonomous_agent_builder.embedded.server.sse.manager import get_sse_manager

router = APIRouter()


@router.get("/stream")
async def stream_events(request: Request):
    """SSE endpoint for real-time updates.
    
    Streams events to connected clients for real-time dashboard updates.
    Events include task updates, gate results, agent progress, and board changes.
    
    Event types:
    - task_update: Task status changed
    - gate_result: Quality gate completed
    - agent_progress: Agent execution progress
    - board_update: Board state changed
    """
    
    async def event_generator():
        """Generate SSE events for this client."""
        # Create queue for this client
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        manager = get_sse_manager()
        
        # Register client
        await manager.register(queue)
        
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                
                # Wait for event with timeout to check disconnection periodically
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    
                    # Yield event to client
                    yield {
                        "event": event["type"],
                        "data": json.dumps(event["data"]),
                    }
                    
                except asyncio.TimeoutError:
                    # Send keepalive comment to prevent connection timeout
                    yield {
                        "comment": "keepalive",
                    }
                    
        finally:
            # Unregister client on disconnect
            await manager.unregister(queue)
    
    return EventSourceResponse(event_generator())
