"""Feature API routes for the embedded server."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.session import get_db

router = APIRouter()


class FeatureCreate(BaseModel):
    title: str
    description: str = ""
    priority: int = 0


def _feature_payload(feature) -> dict[str, object]:
    return {
        "id": feature.id,
        "project_id": feature.project_id,
        "title": feature.title,
        "description": feature.description,
        "status": feature.status.value if hasattr(feature.status, "value") else str(feature.status),
        "priority": feature.priority,
        "created_at": feature.created_at.isoformat() if feature.created_at else None,
    }


@router.get("/features")
async def list_features(db: AsyncSession = Depends(get_db)):
    """List all features for the current project."""
    from autonomous_agent_builder.db.models import Feature

    result = await db.execute(select(Feature))
    features = result.scalars().all()

    return [_feature_payload(feature) for feature in features]


@router.get("/projects/{project_id}/features")
async def list_project_features(project_id: str, db: AsyncSession = Depends(get_db)):
    """List features for one project using the canonical project-scoped route."""
    from autonomous_agent_builder.db.models import Feature, Project

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(Feature)
        .where(Feature.project_id == project_id)
        .order_by(Feature.priority.desc(), Feature.created_at.desc())
    )
    return [_feature_payload(feature) for feature in result.scalars().all()]


@router.get("/features/{feature_id}")
async def get_feature(feature_id: str, db: AsyncSession = Depends(get_db)):
    """Return one feature by ID."""
    from autonomous_agent_builder.db.models import Feature

    feature = await db.get(Feature, feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")
    return _feature_payload(feature)


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


@router.post("/projects/{project_id}/features", status_code=201)
async def create_project_feature(
    project_id: str,
    data: FeatureCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a feature for one project using the canonical project-scoped route."""
    from autonomous_agent_builder.db.models import Feature, FeatureStatus, Project

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    feature = Feature(
        project_id=project_id,
        title=data.title,
        description=data.description,
        status=FeatureStatus.BACKLOG,
        priority=data.priority,
    )
    db.add(feature)
    await db.flush()
    await db.refresh(feature)
    return _feature_payload(feature)


@router.get("/features/{feature_id}/tasks")
async def list_feature_tasks(feature_id: str, db: AsyncSession = Depends(get_db)):
    """List tasks belonging to one feature."""
    from autonomous_agent_builder.db.models import Task
    from sqlalchemy import select

    result = await db.execute(
        select(Task).where(Task.feature_id == feature_id).order_by(Task.created_at.desc())
    )
    tasks = result.scalars().all()
    return [
        {
            "id": t.id,
            "feature_id": t.feature_id,
            "title": t.title,
            "description": t.description,
            "status": t.status.value if hasattr(t.status, "value") else str(t.status),
            "complexity": t.complexity,
            "retry_count": t.retry_count,
            "blocked_reason": t.blocked_reason,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tasks
    ]
