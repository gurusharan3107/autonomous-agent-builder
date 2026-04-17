"""Feature API routes for embedded server."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.session import get_db

router = APIRouter()


@router.get("/features")
async def list_features(db: AsyncSession = Depends(get_db)):
    """List all features for the current project."""
    from autonomous_agent_builder.db.models import Feature
    from sqlalchemy import select
    
    result = await db.execute(select(Feature))
    features = result.scalars().all()
    
    return [
        {
            "id": f.id,
            "project_id": f.project_id,
            "title": f.title,
            "description": f.description,
            "status": f.status.value,
            "priority": f.priority,
            "created_at": f.created_at.isoformat(),
        }
        for f in features
    ]


@router.post("/features")
async def create_feature(
    title: str,
    description: str = "",
    priority: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Create a new feature."""
    from autonomous_agent_builder.db.models import Feature, FeatureStatus
    
    # TODO: Get project_id from context or create default project
    # For now, we'll need to handle this in the full implementation
    
    feature = Feature(
        project_id="default",  # Placeholder
        title=title,
        description=description,
        status=FeatureStatus.BACKLOG,
        priority=priority,
    )
    
    db.add(feature)
    await db.flush()
    
    return {
        "id": feature.id,
        "title": feature.title,
        "status": feature.status.value,
    }
