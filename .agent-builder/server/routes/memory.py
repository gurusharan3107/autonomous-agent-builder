"""Memory API routes for embedded server."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.session import get_db

router = APIRouter()


@router.get("/memory/")
async def list_memories(db: AsyncSession = Depends(get_db)):
    """List all memory entries."""
    # For now, return empty list since memory is not yet implemented
    # This will be implemented in later tasks
    return []


@router.get("/memory/{slug}")
async def get_memory(slug: str, db: AsyncSession = Depends(get_db)):
    """Get a specific memory entry."""
    # For now, return empty response
    # This will be implemented in later tasks
    return {"slug": slug, "content": "", "type": ""}
