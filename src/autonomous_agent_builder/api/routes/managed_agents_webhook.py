"""Anthropic Managed Agents webhook receiver — Phase E.

Replaces orchestrator polling for session/vault state changes with an
Anthropic-pushed event stream. Per MA docs §Webhooks: payloads are thin
(event type + resource IDs), HMAC-signed with the per-endpoint
`whsec_` secret, and may arrive at-most-twice (retries carry the same
`event.id` — dedupe).

Handler pipeline:
  1. Read raw body + headers
  2. `client.beta.webhooks.unwrap(body, headers)` verifies HMAC + parses
     (rejects if more than ~5 minutes old; raises on bad signature)
  3. Skip if `event.id` already seen in `WebhookDelivery` table (Phase F
     will add the table; Phase E uses an in-process LRU set as a stub)
  4. Dispatch to a per-event-type handler that fetches the resource
     and resumes the orchestrator follow-up logic

Phase E ships the route + verification + dedupe scaffolding + a
dispatch table that logs each event type. Hooking the actual
orchestrator resume-on-idle logic to specific event types is a Phase E2
follow-up — touches existing orchestrator code paths and warrants its
own focused diff.

Console registration is documented but done at deploy time per MA docs;
no programmatic endpoint registration is offered by the API.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from typing import Any

import structlog
from fastapi import APIRouter, Header, Request

log = structlog.get_logger()

router = APIRouter(prefix="/managed-agents", tags=["managed-agents"])


# Phase E in-process LRU dedupe ring. Bounded so the process doesn't
# accumulate memory under sustained traffic. Phase F will replace this
# with a `WebhookDelivery` DB table for cross-process / cross-restart
# dedupe.
_SEEN_EVENT_IDS: OrderedDict[str, None] = OrderedDict()
_SEEN_LIMIT = 4096


def _record_event_id(event_id: str) -> bool:
    """Return True if already seen (skip), False if new (process)."""
    if event_id in _SEEN_EVENT_IDS:
        # Move-to-end so MRU stays alive
        _SEEN_EVENT_IDS.move_to_end(event_id)
        return True
    _SEEN_EVENT_IDS[event_id] = None
    while len(_SEEN_EVENT_IDS) > _SEEN_LIMIT:
        _SEEN_EVENT_IDS.popitem(last=False)
    return False


# Phase E delivery dispatch — one entry per subscribed event type. Each
# handler receives the unwrapped event object and is expected to be
# idempotent (Phase F will add the orchestrator resume hook here).
async def _on_session_idled(event: Any) -> dict[str, Any]:
    log.info(
        "managed_agents_webhook_session_idled",
        session_id=getattr(event.data, "id", None),
    )
    return {"action": "logged", "phase_E2": "orchestrator_resume_pending"}


async def _on_session_terminated(event: Any) -> dict[str, Any]:
    log.info(
        "managed_agents_webhook_session_terminated",
        session_id=getattr(event.data, "id", None),
    )
    return {"action": "logged", "phase_E2": "task_close_pending"}


async def _on_outcome_evaluation_ended(event: Any) -> dict[str, Any]:
    log.info(
        "managed_agents_webhook_outcome_evaluation_ended",
        session_id=getattr(event.data, "id", None),
    )
    return {"action": "logged", "phase_E2": "gate_result_pending"}


async def _on_vault_credential_refresh_failed(event: Any) -> dict[str, Any]:
    log.warning(
        "managed_agents_webhook_vault_credential_refresh_failed",
        credential_id=getattr(event.data, "id", None),
    )
    return {"action": "logged", "phase_E2": "inbox_alert_pending"}


_DISPATCH: dict[str, Any] = {
    "session.status_idled": _on_session_idled,
    "session.status_terminated": _on_session_terminated,
    "session.outcome_evaluation_ended": _on_outcome_evaluation_ended,
    "vault_credential.refresh_failed": _on_vault_credential_refresh_failed,
}


def _client_factory() -> Any:
    """Lazy import keeps the route loadable when anthropic isn't installed."""
    import anthropic

    return anthropic.Anthropic()


# Test seam — overridable so unit tests can inject a fake unwrap impl.
_unwrap_override: Any = None


def _set_unwrap_override(fn: Any) -> None:
    """Test-only seam to inject a custom unwrap callable."""
    global _unwrap_override
    _unwrap_override = fn


def _unwrap_event(body: bytes, headers: dict[str, str]) -> Any:
    if _unwrap_override is not None:
        return _unwrap_override(body, headers)
    client = _client_factory()
    # SDK reads `ANTHROPIC_WEBHOOK_SIGNING_KEY` from env automatically.
    return client.beta.webhooks.unwrap(body, headers=headers)


@router.post("/webhook")
async def managed_agents_webhook(
    request: Request,
    webhook_id: str | None = Header(default=None, alias="webhook-id"),
) -> dict[str, Any]:
    """Receive HMAC-signed MA webhook events.

    Returns 200 with `{status: ok, ...}` on every recognized payload —
    even `skipped` (already-seen) and `unhandled_type` — so Anthropic
    doesn't retry. Returns 400 on signature/schema failures so the
    delivery is retried per MA's policy.
    """
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    if not os.environ.get("ANTHROPIC_WEBHOOK_SIGNING_KEY"):
        log.error(
            "managed_agents_webhook_missing_signing_key",
            webhook_id=webhook_id,
        )
        # 503 so Anthropic retries after the secret is configured
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

    if _record_event_id(event_id):
        return {"status": "ok", "skipped": True, "event_id": event_id}

    event_type = getattr(getattr(event, "data", None), "type", None) or ""
    handler = _DISPATCH.get(event_type)
    if handler is None:
        log.info(
            "managed_agents_webhook_unhandled_type",
            type=event_type,
            event_id=event_id,
        )
        return {
            "status": "ok",
            "skipped": False,
            "event_id": event_id,
            "unhandled_type": event_type,
        }

    result = await handler(event)
    return {
        "status": "ok",
        "skipped": False,
        "event_id": event_id,
        "type": event_type,
        "result": result,
    }


def _error(status_code: int, code: str, *, detail: str | None = None) -> dict[str, Any]:
    """Return a deterministic JSON error envelope.

    FastAPI's HTTPException would do, but raising it gives a plain text
    body for some status codes. We want JSON for any agent-facing
    integration that inspects the body.
    """
    from fastapi.responses import JSONResponse

    payload: dict[str, Any] = {"status": "error", "code": code}
    if detail:
        payload["detail"] = detail
    # Note: returning a JSONResponse from a route function works in
    # FastAPI; the Response replaces the default serialization path.
    return JSONResponse(content=payload, status_code=status_code)


# ── Test-only utilities ──


def _reset_seen_ids() -> None:
    """Clear the in-process dedupe ring (test-only)."""
    _SEEN_EVENT_IDS.clear()
