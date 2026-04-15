"""Knowledge base API — CRUD for agent-written documents (ADRs, contracts, runbooks)."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.api.schemas import (
    KBDocCreate,
    KBDocResponse,
    KBDocUpdate,
)
from autonomous_agent_builder.db.models import DesignDocument
from autonomous_agent_builder.db.session import get_db

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.post("/", response_model=KBDocResponse, status_code=201)
async def create_document(
    body: KBDocCreate,
    db: AsyncSession = Depends(get_db),
) -> DesignDocument:
    """Create a knowledge base document."""
    doc = DesignDocument(
        id=str(uuid4()),
        task_id=body.task_id,
        doc_type=body.doc_type,
        title=body.title,
        content=body.content,
        version=1,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


@router.get("/", response_model=list[KBDocResponse])
async def list_documents(
    task_id: str | None = Query(None),
    doc_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[DesignDocument]:
    """List knowledge base documents with optional filters."""
    stmt = select(DesignDocument).order_by(DesignDocument.created_at.desc())
    if task_id:
        stmt = stmt.where(DesignDocument.task_id == task_id)
    if doc_type:
        stmt = stmt.where(DesignDocument.doc_type == doc_type)
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/search", response_model=list[KBDocResponse])
async def search_documents(
    q: str = Query(..., min_length=1),
    doc_type: str | None = Query(None),
    task_id: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[DesignDocument]:
    """Search KB documents by title and content (SQL LIKE)."""
    pattern = f"%{q}%"
    stmt = (
        select(DesignDocument)
        .where(
            DesignDocument.title.ilike(pattern) | DesignDocument.content.ilike(pattern)
        )
        .order_by(DesignDocument.created_at.desc())
    )
    if doc_type:
        stmt = stmt.where(DesignDocument.doc_type == doc_type)
    if task_id:
        stmt = stmt.where(DesignDocument.task_id == task_id)
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{doc_id}", response_model=KBDocResponse)
async def get_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
) -> DesignDocument:
    """Get a single KB document by ID."""
    result = await db.execute(
        select(DesignDocument).where(DesignDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    return doc


@router.put("/{doc_id}", response_model=KBDocResponse)
async def update_document(
    doc_id: str,
    body: KBDocUpdate,
    db: AsyncSession = Depends(get_db),
) -> DesignDocument:
    """Update a KB document. Bumps version on content change."""
    result = await db.execute(
        select(DesignDocument).where(DesignDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    if body.title is not None:
        doc.title = body.title
    if body.content is not None:
        doc.content = body.content
        doc.version += 1

    await db.flush()
    await db.refresh(doc)
    return doc
