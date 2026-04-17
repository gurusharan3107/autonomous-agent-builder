"""Project API routes for embedded server."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.models import Project
from autonomous_agent_builder.db.session import get_db

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    repo_url: str = ""
    language: str = ""


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    repo_url: str
    language: str


@router.post("/projects/", response_model=ProjectResponse, status_code=201)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    """Create a new project."""
    project = Project(
        name=data.name,
        description=data.description,
        repo_url=data.repo_url,
        language=data.language,
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description or "",
        repo_url=project.repo_url or "",
        language=project.language or "",
    )


@router.get("/projects/", response_model=list[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    """List all projects."""
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()
    return [
        ProjectResponse(
            id=p.id,
            name=p.name,
            description=p.description or "",
            repo_url=p.repo_url or "",
            language=p.language or "",
        )
        for p in projects
    ]


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description or "",
        repo_url=project.repo_url or "",
        language=project.language or "",
    )
