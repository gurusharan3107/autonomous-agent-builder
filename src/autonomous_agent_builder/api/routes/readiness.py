"""Readiness API routes for Agent-page gating."""

from __future__ import annotations

from fastapi import APIRouter, Request

from autonomous_agent_builder.services.project_context import request_project_root
from autonomous_agent_builder.services.readiness import assess_readiness, load_readiness_status

router = APIRouter(tags=["readiness"])


def _project_root(request: Request):
    return request_project_root(request)


@router.get("/readiness/status")
async def readiness_status(request: Request):
    return load_readiness_status(_project_root(request))


@router.post("/readiness/assess")
async def readiness_assess(request: Request):
    return assess_readiness(_project_root(request), write=True)
