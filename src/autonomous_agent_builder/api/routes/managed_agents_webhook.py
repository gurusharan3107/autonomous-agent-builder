"""Anthropic Managed Agents webhook receiver — Phases E + E2.

Replaces orchestrator polling for session/vault state changes with an
Anthropic-pushed event stream. Per MA docs §Webhooks: payloads are thin
(event type + resource IDs), HMAC-signed with the per-endpoint
``whsec_`` secret, and may arrive at-most-twice (retries carry the same
``event.id`` — dedupe).

Phase E2 changes (relative to E):
- Dedupe is DB-backed via the ``webhook_deliveries`` table (cross-process
  / cross-restart safe) instead of an in-process LRU.
- ``session.status_idled`` / ``session.status_terminated`` /
  ``session.outcome_evaluation_ended`` look up the matching ``AgentRun``
  by ``session_id`` and call ``Orchestrator.dispatch(task)`` to advance
  the lifecycle. Lookup failures are logged and the delivery is marked
  ``failed`` so operators can investigate.
- ``vault_credential.refresh_failed`` continues to surface as a log alert;
  Inbox surfacing is a Phase F concern.

Console registration is documented but done at deploy time per MA docs;
no programmatic endpoint registration is offered by the API.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import AgentRun, Task, WebhookDelivery
from autonomous_agent_builder.db.session import get_db

log = structlog.get_logger()

router = APIRouter(prefix="/managed-agents", tags=["managed-agents"])


# Test seam — overridable so unit tests can inject a fake unwrap impl.
_unwrap_override: Any = None


def _set_unwrap_override(fn: Any) -> None:
    """Test-only seam to inject a custom unwrap callable."""
    global _unwrap_override
    _unwrap_override = fn


def _client_factory() -> Any:
    """Lazy import keeps the route loadable when anthropic isn't installed."""
    import anthropic

    return anthropic.Anthropic()


def _unwrap_event(body: bytes, headers: dict[str, str]) -> Any:
    if _unwrap_override is not None:
        return _unwrap_override(body, headers)
    client = _client_factory()
    # SDK reads ``ANTHROPIC_WEBHOOK_SIGNING_KEY`` from env automatically.
    return client.beta.webhooks.unwrap(body, headers=headers)


# ── DB-backed dedupe ──────────────────────────────────────────────────────


async def _record_delivery(
    db: AsyncSession,
    *,
    event_id: str,
    event_type: str,
    session_id: str | None,
) -> bool:
    """Insert a delivery row. Return True when this is a duplicate.

    The primary key on ``event_id`` makes the duplicate case observable
    from the DB layer without a SELECT round-trip first.
    """
    delivery = WebhookDelivery(
        event_id=event_id,
        event_type=event_type,
        session_id=session_id,
        dispatch_status="received",
    )
    db.add(delivery)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return True
    await db.commit()
    return False


async def _mark_delivery_status(
    db: AsyncSession,
    *,
    event_id: str,
    status: str,
    error: str | None = None,
) -> None:
    delivery = await db.get(WebhookDelivery, event_id)
    if delivery is None:  # pragma: no cover — should not happen post-record
        return
    delivery.dispatch_status = status
    delivery.processed_at = datetime.now(UTC)
    if error is not None:
        delivery.error = error[:1024]
    await db.commit()


# ── Orchestrator resume helpers ───────────────────────────────────────────


async def _task_for_session(
    db: AsyncSession, session_id: str | None
) -> Task | None:
    if not session_id:
        return None
    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.session_id == session_id)
        .order_by(AgentRun.started_at.desc())
        .limit(1)
    )
    run = result.scalars().first()
    if run is None:
        return None
    return await db.get(Task, run.task_id)


async def _resume_orchestrator(db: AsyncSession, task: Task) -> None:
    """Call ``Orchestrator.dispatch`` for the task that owns this session.

    Imported lazily to avoid a circular import at route load time.
    """
    from autonomous_agent_builder.orchestrator.orchestrator import Orchestrator

    orchestrator = Orchestrator(get_settings(), db)
    await orchestrator.dispatch(task)


# ── Per-event-type handlers ───────────────────────────────────────────────


async def _on_session_idled(event: Any, db: AsyncSession) -> dict[str, Any]:
    session_id = getattr(event.data, "id", None)
    log.info("managed_agents_webhook_session_idled", session_id=session_id)
    task = await _task_for_session(db, session_id)
    if task is None:
        return {"action": "skipped", "reason": "no_matching_agent_run"}
    await _resume_orchestrator(db, task)
    return {"action": "resumed", "task_id": task.id}


async def _on_session_terminated(event: Any, db: AsyncSession) -> dict[str, Any]:
    session_id = getattr(event.data, "id", None)
    log.info("managed_agents_webhook_session_terminated", session_id=session_id)
    task = await _task_for_session(db, session_id)
    if task is None:
        return {"action": "skipped", "reason": "no_matching_agent_run"}
    await _resume_orchestrator(db, task)
    return {"action": "resumed", "task_id": task.id}


async def _on_outcome_evaluation_ended(
    event: Any, db: AsyncSession
) -> dict[str, Any]:
    session_id = getattr(event.data, "id", None)
    log.info(
        "managed_agents_webhook_outcome_evaluation_ended", session_id=session_id
    )
    task = await _task_for_session(db, session_id)
    if task is None:
        return {"action": "skipped", "reason": "no_matching_agent_run"}
    await _resume_orchestrator(db, task)
    return {"action": "resumed", "task_id": task.id}


async def _on_vault_credential_refresh_failed(
    event: Any, db: AsyncSession
) -> dict[str, Any]:
    log.warning(
        "managed_agents_webhook_vault_credential_refresh_failed",
        credential_id=getattr(event.data, "id", None),
    )
    return {"action": "logged", "phase": "inbox_alert_pending"}


_DISPATCH: dict[str, Any] = {
    "session.status_idled": _on_session_idled,
    "session.status_terminated": _on_session_terminated,
    "session.outcome_evaluation_ended": _on_outcome_evaluation_ended,
    "vault_credential.refresh_failed": _on_vault_credential_refresh_failed,
}


# ── Route ─────────────────────────────────────────────────────────────────


@router.post("/webhook")
async def managed_agents_webhook(
    request: Request,
    webhook_id: str | None = Header(default=None, alias="webhook-id"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Receive HMAC-signed MA webhook events.

    Returns 200 with ``{status: ok, ...}`` on every recognized payload —
    even ``skipped`` (already-seen) and ``unhandled_type`` — so Anthropic
    doesn't retry. Returns 400 on signature/schema failures so the
    delivery is retried per MA's policy.
    """
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    if not os.environ.get("ANTHROPIC_WEBHOOK_SIGNING_KEY"):
        log.error(
            "managed_agents_webhook_missing_signing_key", webhook_id=webhook_id
        )
        return _error(503, "missing_signing_key")

    try:
        event = _unwrap_event(body, headers)
    except Exception as exc:
        log.warning(
            "managed_agents_webhook_verify_failed",
            error=str(exc),
            webhook_id=webhook_id,
        )
        return _error(400, "invalid_signature_or_payload", detail=str(exc))

    event_id = getattr(event, "id", None)
    if not event_id:
        return _error(400, "missing_event_id")

    event_type = getattr(getattr(event, "data", None), "type", None) or ""
    session_id = getattr(getattr(event, "data", None), "id", None)

    duplicate = await _record_delivery(
        db,
        event_id=event_id,
        event_type=event_type,
        session_id=session_id,
    )
    if duplicate:
        return {"status": "ok", "skipped": True, "event_id": event_id}

    handler = _DISPATCH.get(event_type)
    if handler is None:
        log.info(
            "managed_agents_webhook_unhandled_type",
            type=event_type,
            event_id=event_id,
        )
        await _mark_delivery_status(db, event_id=event_id, status="skipped")
        return {
            "status": "ok",
            "skipped": False,
            "event_id": event_id,
            "unhandled_type": event_type,
        }

    try:
        result = await handler(event, db)
    except Exception as exc:
        log.error(
            "managed_agents_webhook_handler_failed",
            type=event_type,
            event_id=event_id,
            error=str(exc),
        )
        await _mark_delivery_status(
            db, event_id=event_id, status="failed", error=str(exc)
        )
        return _error(500, "handler_failed", detail=str(exc))

    await _mark_delivery_status(db, event_id=event_id, status="processed")
    return {
        "status": "ok",
        "skipped": False,
        "event_id": event_id,
        "type": event_type,
        "result": result,
    }


def _error(status_code: int, code: str, *, detail: str | None = None) -> Any:
    """Return a deterministic JSON error envelope."""
    from fastapi.responses import JSONResponse

    payload: dict[str, Any] = {"status": "error", "code": code}
    if detail:
        payload["detail"] = detail
    return JSONResponse(content=payload, status_code=status_code)
