"""Knowledge Base API routes for embedded server."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.session import get_db

router = APIRouter()


@router.get("/kb/")
async def list_kb_docs(
    task_id: str | None = None,
    doc_type: str | None = None,
    limit: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List knowledge base documents."""
    # For now, return empty list since KB is not yet implemented
    # This will be implemented in later tasks
    return []


@router.get("/kb/{doc_id}")
async def get_kb_doc(doc_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific knowledge base document."""
    # For now, return empty response
    # This will be implemented in later tasks
    return {"id": doc_id, "content": "", "doc_type": ""}


@router.get("/kb/search")
async def search_kb_docs(q: str, db: AsyncSession = Depends(get_db)):
    """Search knowledge base documents."""
    # For now, return empty list
    # This will be implemented in later tasks
    return []
