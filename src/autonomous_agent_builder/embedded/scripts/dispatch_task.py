"""Script for dispatching tasks through the orchestrator.

This script dispatches a task for execution through the orchestrator
and triggers an SSE event to update the dashboard in real-time.
"""

import asyncio
from typing import Any

from .base import Script, ScriptResult


class DispatchTaskScript(Script):
    """Dispatch a task through the orchestrator."""

    @property
    def name(self) -> str:
        return "dispatch_task"

    @property
    def description(self) -> str:
        return "Dispatch a task for execution through the orchestrator"

    def validate_args(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate script arguments.
        
        Required args:
            - task_id: str - The task ID to dispatch
        """
        if "task_id" not in kwargs:
            return False, "Missing required argument: task_id"
        
        if not isinstance(kwargs["task_id"], str):
            return False, "Argument 'task_id' must be a string"
        
        if not kwargs["task_id"].strip():
            return False, "Argument 'task_id' cannot be empty"
        
        return True, None

    def run(self, **kwargs: Any) -> ScriptResult:
        """Execute the script to dispatch a task.
        
        Args:
            task_id: The task ID to dispatch
            
        Returns:
            ScriptResult with dispatch result
        """
        try:
            # Run async operation in sync context
            return asyncio.run(self._async_run(**kwargs))
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": f"Failed to dispatch task: {str(e)}",
            }

    async def _async_run(self, **kwargs: Any) -> ScriptResult:
        """Async implementation of task dispatch."""
        from sqlalchemy import select
        from autonomous_agent_builder.db.models import Task
        from autonomous_agent_builder.db.session import get_session_factory
        from autonomous_agent_builder.embedded.server.sse.manager import broadcast_event
        
        task_id = kwargs["task_id"]
        
        # Create database session
        factory = get_session_factory()
        async with factory() as session:
            try:
                # Load task
                result = await session.execute(
                    select(Task).where(Task.id == task_id)
                )
                task = result.scalar_one_or_none()
                
                if task is None:
                    return {
                        "success": False,
                        "data": None,
                        "error": f"Task '{task_id}' not found",
                    }
                
                # TODO: Dispatch through orchestrator
                # This would involve:
                # 1. Calling the orchestrator to execute the task
                # 2. Updating task status based on orchestrator response
                # 3. Creating a run record
                
                # For now, just broadcast the task update event
                await broadcast_event("task_update", {
                    "task_id": task.id,
                    "status": task.status.value,
                    "title": task.title,
                })
                
                return {
                    "success": True,
                    "data": {
                        "task_id": task.id,
                        "title": task.title,
                        "status": task.status.value,
                        "message": "Task dispatch mechanism not yet fully implemented. "
                                   "Orchestrator integration pending.",
                    },
                    "error": None,
                }
                
            except Exception as e:
                await session.rollback()
                raise e
