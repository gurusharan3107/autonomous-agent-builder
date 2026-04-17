"""Task API routes for embedded server."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.session import get_db

router = APIRouter()


@router.get("/tasks")
async def list_tasks(db: AsyncSession = Depends(get_db)):
    """List all tasks for the current project."""
    from autonomous_agent_builder.db.models import Task
    from sqlalchemy import select
    
    result = await db.execute(select(Task))
    tasks = result.scalars().all()
    
    return [
        {
            "id": t.id,
            "feature_id": t.feature_id,
            "title": t.title,
            "description": t.description,
            "status": t.status.value,
            "complexity": t.complexity,
            "created_at": t.created_at.isoformat(),
        }
        for t in tasks
    ]


@router.post("/tasks/{task_id}/dispatch")
async def dispatch_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Dispatch a task through the orchestrator."""
    from autonomous_agent_builder.db.models import Task
    from sqlalchemy import select
    
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    
    if not task:
        return {"error": "Task not found"}
    
    # TODO: Integrate with orchestrator
    # For now, return placeholder
    
    return {
        "task_id": task.id,
        "status": task.status.value,
        "message": "Task dispatch not yet implemented",
    }
