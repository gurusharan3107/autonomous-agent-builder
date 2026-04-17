"""Quality gate API routes for embedded server."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.session import get_db

router = APIRouter()


@router.get("/gates")
async def list_gate_results(db: AsyncSession = Depends(get_db)):
    """List quality gate results."""
    from autonomous_agent_builder.db.models import GateResult
    from sqlalchemy import select
    
    result = await db.execute(select(GateResult).order_by(GateResult.created_at.desc()).limit(50))
    gates = result.scalars().all()
    
    return [
        {
            "id": g.id,
            "task_id": g.task_id,
            "gate_name": g.gate_name,
            "status": g.status.value,
            "findings_count": g.findings_count,
            "elapsed_ms": g.elapsed_ms,
            "created_at": g.created_at.isoformat(),
        }
        for g in gates
    ]
