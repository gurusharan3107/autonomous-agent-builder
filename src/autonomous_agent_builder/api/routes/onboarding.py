"""Onboarding API routes for dashboard-first enterprise repo bootstrap."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from autonomous_agent_builder.api.dashboard_streams import get_dashboard_stream_hub
from autonomous_agent_builder.db.session import get_session_factory
from autonomous_agent_builder.onboarding import (
    load_onboarding_state,
    publish_onboarding_snapshot,
    retry_onboarding,
    start_onboarding,
)

router = APIRouter(tags=["onboarding"])


class OnboardingPhase(BaseModel):
    id: str
    title: str
    status: str
    message: str
    started_at: str | None = None
    finished_at: str | None = None
    result: dict | None = None
    error: str | None = None


class OnboardingStatusResponse(BaseModel):
    repo: dict
    onboarding_mode: str
    current_phase: str
    ready: bool
    started_at: str | None = None
    updated_at: str
    phases: list[OnboardingPhase]
    entity_counts: dict
    kb_status: dict
    scan_summary: dict
    archives: list[dict]
    errors: list[dict]


def _project_root(request: Request) -> Path:
    return Path(getattr(request.app.state, "project_root", Path.cwd()))


@router.get("/onboarding/status", response_model=OnboardingStatusResponse)
async def onboarding_status(request: Request):
    return load_onboarding_state(_project_root(request))


@router.post("/onboarding/start", response_model=OnboardingStatusResponse)
async def onboarding_start(request: Request):
    state = await start_onboarding(_project_root(request), get_session_factory())
    return state


@router.post("/onboarding/retry", response_model=OnboardingStatusResponse)
async def onboarding_retry(request: Request):
    state = await retry_onboarding(_project_root(request), get_session_factory())
    return state


@router.get("/onboarding/stream")
async def onboarding_stream(request: Request):
    project_root = _project_root(request)

    async def event_generator():
        queue = await get_dashboard_stream_hub().register_onboarding()
        try:
            initial_state = load_onboarding_state(project_root)
            yield {"event": "snapshot", "data": json.dumps(initial_state)}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield {
                        "event": event["event"],
                        "data": json.dumps(event["data"]),
                    }
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            await get_dashboard_stream_hub().unregister_onboarding(queue)

    return EventSourceResponse(event_generator())
