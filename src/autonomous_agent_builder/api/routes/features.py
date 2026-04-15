"""Feature and Task CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.api.schemas import (
    FeatureCreate,
    FeatureResponse,
    TaskCreate,
    TaskResponse,
)
from autonomous_agent_builder.db.models import Feature, Project, Task
from autonomous_agent_builder.db.session import get_db

router = APIRouter(tags=["features"])


# ── Features ──


@router.post("/projects/{project_id}/features", response_model=FeatureResponse, status_code=201)
async def create_feature(project_id: str, data: FeatureCreate, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    feature = Feature(
        project_id=project_id,
        title=data.title,
        description=data.description,
        priority=data.priority,
    )
    db.add(feature)
    await db.flush()
    await db.refresh(feature)
    return feature


@router.get("/projects/{project_id}/features", response_model=list[FeatureResponse])
async def list_features(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Feature)
        .where(Feature.project_id == project_id)
        .order_by(Feature.priority.desc(), Feature.created_at.desc())
    )
    return result.scalars().all()


@router.get("/features/{feature_id}", response_model=FeatureResponse)
async def get_feature(feature_id: str, db: AsyncSession = Depends(get_db)):
    feature = await db.get(Feature, feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")
    return feature


# ── Tasks ──


@router.post("/features/{feature_id}/tasks", response_model=TaskResponse, status_code=201)
async def create_task(feature_id: str, data: TaskCreate, db: AsyncSession = Depends(get_db)):
    feature = await db.get(Feature, feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")

    task = Task(
        feature_id=feature_id,
        title=data.title,
        description=data.description,
        complexity=data.complexity,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


@router.get("/features/{feature_id}/tasks", response_model=list[TaskResponse])
async def list_tasks(feature_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Task).where(Task.feature_id == feature_id).order_by(Task.created_at)
    )
    return result.scalars().all()


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
