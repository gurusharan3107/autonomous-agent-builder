"""Script for manually triggering dashboard state updates.

This script allows agents to manually trigger SSE events to update
the dashboard without making database changes.
"""

import asyncio
from typing import Any

from .base import Script, ScriptResult


class UpdateDashboardScript(Script):
    """Manually trigger dashboard state updates via SSE."""

    @property
    def name(self) -> str:
        return "update_dashboard"

    @property
    def description(self) -> str:
        return "Manually trigger dashboard state updates via SSE events"

    def validate_args(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate script arguments.
        
        Required args:
            - event_type: str - Type of event (task_update, gate_result, agent_progress, board_update)
            - data: dict - Event data payload
        """
        if "event_type" not in kwargs:
            return False, "Missing required argument: event_type"
        
        if "data" not in kwargs:
            return False, "Missing required argument: data"
        
        if not isinstance(kwargs["event_type"], str):
            return False, "Argument 'event_type' must be a string"
        
        if not isinstance(kwargs["data"], dict):
            return False, "Argument 'data' must be a dictionary"
        
        # Validate event type
        valid_event_types = ["task_update", "gate_result", "agent_progress", "board_update"]
        if kwargs["event_type"] not in valid_event_types:
            return False, (
                f"Invalid event_type. Must be one of: {', '.join(valid_event_types)}"
            )
        
        return True, None

    def run(self, **kwargs: Any) -> ScriptResult:
        """Execute the script to trigger a dashboard update.
        
        Args:
            event_type: Type of event to broadcast
            data: Event data payload
            
        Returns:
            ScriptResult with broadcast confirmation
        """
        try:
            # Run async operation in sync context
            return asyncio.run(self._async_run(**kwargs))
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": f"Failed to update dashboard: {str(e)}",
            }

    async def _async_run(self, **kwargs: Any) -> ScriptResult:
        """Async implementation of dashboard update."""
        from autonomous_agent_builder.embedded.server.sse.manager import broadcast_event
        
        event_type = kwargs["event_type"]
        data = kwargs["data"]
        
        try:
            # Broadcast SSE event
            await broadcast_event(event_type, data)
            
            return {
                "success": True,
                "data": {
                    "event_type": event_type,
                    "data": data,
                    "message": f"Successfully broadcast {event_type} event to dashboard",
                },
                "error": None,
            }
            
        except Exception as e:
            raise e
