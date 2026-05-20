"""Repo-scoped Agent chat session lookup and preview helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.db.models import ChatSession
from autonomous_agent_builder.embedded.server.agent_chat_transcript import history_items
from autonomous_agent_builder.onboarding import _INIT_PROJECT_BOOTSTRAP_MESSAGE


def repo_identity(project_root: Path) -> str:
    return str(project_root.resolve())


def workspace_cwd(project_root: Path) -> str:
    return str(project_root.resolve())


def compatible_resume_session(session: ChatSession, runtime: Any) -> str | None:
    """Return a runtime-owned SDK session id only when it matches the active runtime."""
    sdk_session_id = str(session.sdk_session_id or "").strip()
    if not sdk_session_id:
        return None
    runtime_name = str(getattr(runtime, "name", "") or "")
    runtime_provider = str(getattr(runtime, "provider", "") or "")
    matching_statuses = [
        event
        for event in session.events
        if event.event_type == "run_status"
        and isinstance(event.payload_json, dict)
        and str(event.payload_json.get("sdk_session_id") or "") == sdk_session_id
    ]
    if not matching_statuses:
        status_events = [event for event in session.events if event.event_type == "run_status"]
        return None if status_events else sdk_session_id
    latest = max(matching_statuses, key=lambda event: event.created_at)
    payload = latest.payload_json or {}
    event_runtime = str(payload.get("runtime_sdk") or "")
    event_provider = str(payload.get("provider") or "")
    if event_runtime and runtime_name and event_runtime != runtime_name:
        return None
    if event_provider and runtime_provider and event_provider != runtime_provider:
        return None
    observability = (
        payload.get("observability") if isinstance(payload.get("observability"), dict) else {}
    )
    retention = (
        payload.get("context_retention")
        if isinstance(payload.get("context_retention"), dict)
        else observability.get("context_retention")
        if isinstance(observability.get("context_retention"), dict)
        else {}
    )
    if runtime_name == "codex_sdk" and retention.get("resume_recommended") is False:
        return None
    return sdk_session_id


def stamp_session_scope(session: ChatSession, project_root: Path) -> None:
    session.repo_identity = repo_identity(project_root)
    session.workspace_cwd = workspace_cwd(project_root)


def session_matches_scope(session: ChatSession, project_root: Path) -> bool:
    expected_repo_identity = repo_identity(project_root)
    expected_workspace_cwd = workspace_cwd(project_root)
    return not (
        (session.repo_identity and session.repo_identity != expected_repo_identity)
        or (session.workspace_cwd and session.workspace_cwd != expected_workspace_cwd)
    )


def session_has_meaningful_transcript(session: ChatSession) -> bool:
    items = history_items(session)
    for item in items:
        if item.type == "user_message":
            return True
        if item.type == "assistant_message":
            content = str(item.payload.get("content", "")).strip()
            if content and content != _INIT_PROJECT_BOOTSTRAP_MESSAGE:
                return True
            continue
        if item.type in {"ask_user_question", "tool_approval_request", "run_error"}:
            return True
    return False


def session_preview(session: ChatSession) -> str:
    items = history_items(session)
    for item in items:
        if item.type == "user_message":
            content = str(item.payload.get("content", "")).strip()
            normalized = " ".join(content.split())
            if normalized:
                return normalized[:117] + "..." if len(normalized) > 120 else normalized
    for item in items:
        content = str(item.payload.get("content", "")).strip()
        normalized = " ".join(content.split())
        if normalized:
            return normalized[:117] + "..." if len(normalized) > 120 else normalized
    return "Empty session"


async def load_session(
    db: AsyncSession,
    session_id: str | None,
    *,
    project_root: Path | None = None,
    reject_scope_mismatch: bool = False,
) -> ChatSession | None:
    if not session_id:
        return None
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(selectinload(ChatSession.events), selectinload(ChatSession.messages))
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None
    if project_root is not None:
        if not session_matches_scope(session, project_root):
            if reject_scope_mismatch:
                raise HTTPException(
                    status_code=409,
                    detail="Chat session belongs to a different repo or workspace.",
                )
            return None
        if not session.repo_identity or not session.workspace_cwd:
            stamp_session_scope(session, project_root)
            await db.flush()
    return session


async def list_scoped_sessions(db: AsyncSession, project_root: Path) -> list[ChatSession]:
    result = await db.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.events), selectinload(ChatSession.messages))
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = result.scalars().all()
    scoped_sessions: list[ChatSession] = []
    for session in sessions:
        if not session_matches_scope(session, project_root):
            continue
        if not session.repo_identity or not session.workspace_cwd:
            stamp_session_scope(session, project_root)
            await db.flush()
        scoped_sessions.append(session)
    return scoped_sessions


def latest_resume_candidate(sessions: list[ChatSession]) -> ChatSession | None:
    for session in sessions:
        if session_has_meaningful_transcript(session):
            return session
    return None
