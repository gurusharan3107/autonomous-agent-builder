"""Script for creating features with validation and database insertion.

This script creates a new feature in the database and triggers
an SSE event to update the dashboard in real-time.
"""

import asyncio
from typing import Any

from .base import Script, ScriptResult


class CreateFeatureScript(Script):
    """Create a new feature in the database."""

    @property
    def name(self) -> str:
        return "create_feature"

    @property
    def description(self) -> str:
        return "Create a new feature with validation and database insertion"

    def validate_args(self, **kwargs: Any) -> tuple[bool, str | None]:
        """Validate script arguments.
        
        Required args:
            - project_id: str - The project ID
            - title: str - Feature title
            
        Optional args:
            - description: str - Feature description (default: "")
            - priority: int - Feature priority (default: 0)
        """
        if "project_id" not in kwargs:
            return False, "Missing required argument: project_id"
        
        if "title" not in kwargs:
            return False, "Missing required argument: title"
        
        if not isinstance(kwargs["project_id"], str):
            return False, "Argument 'project_id' must be a string"
        
        if not isinstance(kwargs["title"], str):
            return False, "Argument 'title' must be a string"
        
        if not kwargs["title"].strip():
            return False, "Argument 'title' cannot be empty"
        
        if "description" in kwargs and not isinstance(kwargs["description"], str):
            return False, "Argument 'description' must be a string"
        
        if "priority" in kwargs:
            if not isinstance(kwargs["priority"], int):
                return False, "Argument 'priority' must be an integer"
        
        return True, None

    def run(self, **kwargs: Any) -> ScriptResult:
        """Execute the script to create a feature.
        
        Args:
            project_id: The project ID
            title: Feature title
            description: Optional feature description
            priority: Optional feature priority
            
        Returns:
            ScriptResult with created feature data
        """
        try:
            # Run async operation in sync context
            return asyncio.run(self._async_run(**kwargs))
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": f"Failed to create feature: {str(e)}",
            }

    async def _async_run(self, **kwargs: Any) -> ScriptResult:
        """Async implementation of feature creation."""
        from autonomous_agent_builder.db.models import Feature, FeatureStatus
        from autonomous_agent_builder.db.session import get_session_factory
        from autonomous_agent_builder.embedded.server.sse.manager import broadcast_event
        
        project_id = kwargs["project_id"]
        title = kwargs["title"]
        description = kwargs.get("description", "")
        priority = kwargs.get("priority", 0)
        
        # Create database session
        factory = get_session_factory()
        async with factory() as session:
            try:
                # Create feature
                feature = Feature(
                    project_id=project_id,
                    title=title,
                    description=description,
                    status=FeatureStatus.BACKLOG,
                    priority=priority,
                )
                
                session.add(feature)
                await session.commit()
                await session.refresh(feature)
                
                # Broadcast SSE event for dashboard update
                await broadcast_event("board_update", {
                    "type": "feature_created",
                    "feature_id": feature.id,
                    "title": feature.title,
                    "status": feature.status.value,
                })
                
                return {
                    "success": True,
                    "data": {
                        "id": feature.id,
                        "project_id": feature.project_id,
                        "title": feature.title,
                        "description": feature.description,
                        "status": feature.status.value,
                        "priority": feature.priority,
                        "created_at": feature.created_at.isoformat(),
                    },
                    "error": None,
                }
                
            except Exception as e:
                await session.rollback()
                raise e
