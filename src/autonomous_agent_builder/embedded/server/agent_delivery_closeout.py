"""Agent chat delivery closeout helpers."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.db.models import (
    AgentRun,
    ChatEvent,
    ChatMessage,
    ChatSession,
    DesignDocument,
    Feature,
    Sprint,
    SprintPhase,
    Task,
    TaskStatus,
    utcnow,
)
from autonomous_agent_builder.db.session import get_session_factory
from autonomous_agent_builder.embedded.server import agent_chat_sessions, agent_chat_transcript
from autonomous_agent_builder.embedded.server.chat_state import ChatSessionHub
from autonomous_agent_builder.services.sprint_execution import SPRINT_PLAN_DOC_TYPE

DELIVERY_PLAN_ID_PATTERN = re.compile(r"created plan `([^`]+)`")
DELIVERY_SHIPPED_CLOSEOUT_PREFIX = "Builder shipped "
DELIVERY_CLOSEOUT_MAX_POLLS = 600
DELIVERY_CLOSEOUT_POLL_SECONDS = 2.0


def enum_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip()


def delivery_plan_id_from_session(session: ChatSession) -> str:
    for event in reversed(session.events or []):
        if event.event_type != "delivery_plan_created":
            continue
        plan_id = str((event.payload_json or {}).get("plan_id") or "").strip()
        if plan_id:
            return plan_id
    for item in reversed(agent_chat_transcript.history_items(session)):
        if item.type != "assistant_message":
            continue
        content = str(item.payload.get("content", ""))
        match = DELIVERY_PLAN_ID_PATTERN.search(content)
        if match:
            return match.group(1).strip()
    return ""


def session_has_delivery_closeout(session: ChatSession) -> bool:
    return any(
        item.type == "assistant_message"
        and str(item.payload.get("content", "")).startswith(DELIVERY_SHIPPED_CLOSEOUT_PREFIX)
        for item in agent_chat_transcript.history_items(session)
    )


async def sprint_for_delivery_plan_id(db: AsyncSession, plan_id: str) -> Sprint | None:
    sprint_result = await db.execute(select(Sprint).where(Sprint.plan_doc_id == plan_id))
    sprint = sprint_result.scalar_one_or_none()
    if sprint is not None:
        return sprint

    plan_doc_result = await db.execute(
        select(DesignDocument)
        .where(DesignDocument.doc_type == SPRINT_PLAN_DOC_TYPE)
        .where(DesignDocument.content.contains(plan_id))
        .order_by(DesignDocument.created_at.desc())
    )
    for plan_doc in plan_doc_result.scalars().all():
        try:
            plan_payload = json.loads(plan_doc.content or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(plan_payload, dict) or plan_payload.get("plan_id") != plan_id:
            continue
        sprint_result = await db.execute(select(Sprint).where(Sprint.plan_doc_id == plan_doc.id))
        sprint = sprint_result.scalar_one_or_none()
        if sprint is not None:
            return sprint
    return None


def run_token_totals(runs: list[AgentRun]) -> tuple[int, int, int]:
    raw_tokens = sum(
        max(0, int(run.tokens_input or 0)) + max(0, int(run.tokens_output or 0)) for run in runs
    )
    cached_tokens = sum(max(0, int(run.tokens_cached or 0)) for run in runs)
    noncached_plus_output = sum(
        max(0, int(run.tokens_input or 0) - int(run.tokens_cached or 0))
        + max(0, int(run.tokens_output or 0))
        for run in runs
    )
    return raw_tokens, cached_tokens, noncached_plus_output


async def delivery_closeout_for_shipped_plan(
    db: AsyncSession,
    session: ChatSession,
) -> str:
    if session_has_delivery_closeout(session):
        return ""
    plan_id = delivery_plan_id_from_session(session)
    if not plan_id:
        return ""
    sprint = await sprint_for_delivery_plan_id(db, plan_id)
    if sprint is None:
        return ""
    sprint_phase = enum_text(sprint.phase)
    verification_status = enum_text(sprint.verification_status).lower()
    if sprint_phase != SprintPhase.SHIPPED.value and verification_status not in {
        "pass",
        "passed",
        "shipped",
    }:
        return ""

    task_ids = [
        str(task_id) for task_id in (sprint.generated_task_ids or []) if str(task_id).strip()
    ]
    feature_ids = [
        str(feature_id)
        for feature_id in (sprint.approved_feature_ids or [])
        if str(feature_id).strip()
    ]
    feature_titles: list[str] = []
    if feature_ids:
        feature_result = await db.execute(
            select(Feature).where(Feature.id.in_(feature_ids)).order_by(Feature.created_at.asc())
        )
        feature_titles = [
            feature.title for feature in feature_result.scalars().all() if feature.title
        ]
    if not feature_titles and task_ids:
        task_result = await db.execute(
            select(Task).where(Task.id.in_(task_ids)).options(selectinload(Task.feature))
        )
        seen_feature_ids: set[str] = set()
        for task in task_result.scalars().all():
            if task.feature_id in seen_feature_ids or task.feature is None:
                continue
            seen_feature_ids.add(task.feature_id)
            if task.feature.title:
                feature_titles.append(task.feature.title)
    if not feature_titles:
        feature_titles = ["the approved improvement"]

    completed_steps = 0
    if task_ids:
        task_result = await db.execute(select(Task.status).where(Task.id.in_(task_ids)))
        completed_steps = sum(
            1
            for status in task_result.scalars().all()
            if enum_text(status) == TaskStatus.DONE.value
        )
    run_result = await db.execute(
        select(AgentRun)
        .where(AgentRun.task_id.in_(task_ids or [""]))
        .where(AgentRun.status == "completed")
        .order_by(AgentRun.started_at.asc())
    )
    runs = list(run_result.scalars().all())
    raw_tokens, cached_tokens, noncached_plus_output = run_token_totals(runs)
    feature_label = ", ".join(f"`{title}`" for title in feature_titles[:3])
    evidence_parts = [
        "implementation, tests, and browser-visible verification completed",
        "final checks passed",
        "delivery was integrated",
    ]
    if completed_steps:
        evidence_parts.append(f"{completed_steps} pieces of work completed")
    token_text = ""
    if runs:
        token_text = (
            f" Token evidence: {raw_tokens:,} raw, {cached_tokens:,} cached, "
            f"{noncached_plus_output:,} non-cached plus output across {len(runs)} run(s)."
        )
    return (
        f"{DELIVERY_SHIPPED_CLOSEOUT_PREFIX}{feature_label}. "
        f"Evidence: {'; '.join(evidence_parts)}."
        f"{token_text}"
    )


async def append_delivery_closeout_if_ready(
    session_id: str,
    project_root: Path,
    db: AsyncSession,
    *,
    hub: ChatSessionHub | None = None,
) -> bool:
    session = await agent_chat_sessions.load_session(
        db,
        session_id,
        project_root=project_root,
        reject_scope_mismatch=True,
    )
    if session is None:
        return False
    closeout = await delivery_closeout_for_shipped_plan(db, session)
    if not closeout:
        return False
    session.updated_at = utcnow()
    assistant_event = ChatEvent(
        session_id=session_id,
        event_type="assistant_message",
        payload_json={"content": closeout, "final": True},
        status="completed",
    )
    db.add(assistant_event)
    db.add(
        ChatMessage(
            session_id=session_id,
            role="assistant",
            content=closeout,
            tokens_used=0,
            cost_usd=0.0,
        )
    )
    await db.flush()
    await db.refresh(assistant_event)
    if hub is not None:
        await hub.publish(
            session_id,
            agent_chat_transcript.serialize_event(assistant_event).model_dump(mode="json"),
        )
    return True


def schedule_delivery_closeout_watch(
    session_id: str,
    project_root: Path,
    hub: ChatSessionHub,
) -> None:
    async def _watch() -> None:
        session_factory = get_session_factory()
        for _ in range(DELIVERY_CLOSEOUT_MAX_POLLS):
            async with session_factory() as db:
                session = await agent_chat_sessions.load_session(
                    db,
                    session_id,
                    project_root=project_root,
                    reject_scope_mismatch=True,
                )
                if session is None or not delivery_plan_id_from_session(session):
                    return
                appended = await append_delivery_closeout_if_ready(
                    session_id,
                    project_root,
                    db,
                    hub=hub,
                )
                if appended:
                    await db.commit()
                    return
            await asyncio.sleep(DELIVERY_CLOSEOUT_POLL_SECONDS)

    asyncio.create_task(_watch())
