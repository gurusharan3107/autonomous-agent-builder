"""Tests for /api/managed-agents/webhook (Phases E + E2).

E2 changes the dedupe surface from an in-process LRU to the
``webhook_deliveries`` DB table. These tests use the `client` fixture
(httpx AsyncClient against the full app with ``test_db``) so the DB
round-trip is exercised end-to-end.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from autonomous_agent_builder.api.routes import managed_agents_webhook
from autonomous_agent_builder.db.models import WebhookDelivery


@pytest.fixture(autouse=True)
def _reset_unwrap_override():
    """Always restore the unwrap seam after each test."""
    yield
    managed_agents_webhook._set_unwrap_override(None)


def _install_unwrap(events: list[Any]) -> None:
    iter_state = iter(events)

    def _fake_unwrap(_body: bytes, _headers: dict[str, str]) -> Any:
        return next(iter_state)

    managed_agents_webhook._set_unwrap_override(_fake_unwrap)


def _event_obj(event_id: str, event_type: str, data_id: str = "sesn_x") -> Any:
    """Mirror the SDK's unwrapped object shape (attrs, not dicts)."""
    data = SimpleNamespace(type=event_type, id=data_id)
    return SimpleNamespace(id=event_id, data=data)


@pytest.mark.asyncio
async def test_webhook_returns_503_when_signing_key_unset(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_WEBHOOK_SIGNING_KEY", raising=False)
    resp = await client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == "missing_signing_key"


@pytest.mark.asyncio
async def test_webhook_returns_400_on_unwrap_failure(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_WEBHOOK_SIGNING_KEY", "whsec_test")

    def _bad_unwrap(_body: bytes, _headers: dict[str, str]) -> Any:
        raise ValueError("bad signature")

    managed_agents_webhook._set_unwrap_override(_bad_unwrap)
    resp = await client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "invalid_signature_or_payload"
    assert "bad signature" in body["detail"]


@pytest.mark.asyncio
async def test_webhook_dispatches_session_idled_records_delivery(
    client, monkeypatch: pytest.MonkeyPatch, test_db
) -> None:
    """Unmatched session_id → handler logs `skipped`, delivery row is processed."""
    monkeypatch.setenv("ANTHROPIC_WEBHOOK_SIGNING_KEY", "whsec_test")
    _install_unwrap([_event_obj("event_1", "session.status_idled", "sesn_a")])

    resp = await client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["skipped"] is False
    assert body["event_id"] == "event_1"
    assert body["type"] == "session.status_idled"
    assert body["result"]["action"] == "skipped"

    _, factory = test_db
    async with factory() as db:
        rows = (
            await db.execute(
                select(WebhookDelivery).where(WebhookDelivery.event_id == "event_1")
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].dispatch_status == "processed"
    assert rows[0].event_type == "session.status_idled"
    assert rows[0].session_id == "sesn_a"


@pytest.mark.asyncio
async def test_webhook_dispatches_outcome_evaluation_ended(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_WEBHOOK_SIGNING_KEY", "whsec_test")
    _install_unwrap([_event_obj("event_3", "session.outcome_evaluation_ended")])
    resp = await client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 200
    assert resp.json()["type"] == "session.outcome_evaluation_ended"


@pytest.mark.asyncio
async def test_webhook_dispatches_vault_credential_refresh_failed(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_WEBHOOK_SIGNING_KEY", "whsec_test")
    _install_unwrap([_event_obj("event_4", "vault_credential.refresh_failed")])
    resp = await client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 200
    assert resp.json()["type"] == "vault_credential.refresh_failed"


@pytest.mark.asyncio
async def test_webhook_returns_unhandled_type_for_unknown(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_WEBHOOK_SIGNING_KEY", "whsec_test")
    _install_unwrap([_event_obj("event_5", "session.thread_idled")])
    resp = await client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["unhandled_type"] == "session.thread_idled"


@pytest.mark.asyncio
async def test_webhook_dedupes_repeat_event_id(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same event id appearing twice → first processes, second is `skipped`."""
    monkeypatch.setenv("ANTHROPIC_WEBHOOK_SIGNING_KEY", "whsec_test")
    _install_unwrap(
        [
            _event_obj("event_dup", "session.status_idled"),
            _event_obj("event_dup", "session.status_idled"),
        ]
    )
    first = await client.post("/api/managed-agents/webhook", json={})
    second = await client.post("/api/managed-agents/webhook", json={})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["skipped"] is False
    assert second.json()["skipped"] is True


@pytest.mark.asyncio
async def test_webhook_returns_400_when_event_id_missing(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_WEBHOOK_SIGNING_KEY", "whsec_test")
    bad_event = SimpleNamespace(id=None, data=SimpleNamespace(type="x", id="y"))
    _install_unwrap([bad_event])
    resp = await client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 400
    assert resp.json()["code"] == "missing_event_id"


@pytest.mark.asyncio
async def test_webhook_resumes_orchestrator_when_session_matches(
    client, monkeypatch: pytest.MonkeyPatch, test_db
) -> None:
    """When an AgentRun has the matching session_id, dispatch fires for its task."""
    from autonomous_agent_builder.db.models import (
        AgentRun,
        Feature,
        FeatureStatus,
        Project,
        Task,
        TaskPhase,
        TaskStatus,
    )
    from autonomous_agent_builder.orchestrator.orchestrator import Orchestrator

    monkeypatch.setenv("ANTHROPIC_WEBHOOK_SIGNING_KEY", "whsec_test")

    _, factory = test_db
    async with factory() as db:
        project = Project(
            id="p1", name="demo", language="python", repo_url="/tmp/demo"
        )
        feature = Feature(
            id="f1",
            project_id="p1",
            title="t",
            description="d",
            status=FeatureStatus.IN_PROGRESS,
        )
        task = Task(
            id="t1",
            feature_id="f1",
            title="t",
            description="d",
            status=TaskStatus.QUALITY_GATES,
            phase=TaskPhase.VERIFICATION,
        )
        run = AgentRun(
            id="r1",
            task_id="t1",
            agent_name="feature-verifier",
            session_id="sesn_match",
            status="completed",
        )
        db.add_all([project, feature, task, run])
        await db.commit()

    captured: dict[str, str] = {}

    async def _fake_dispatch(self, t: Task) -> None:
        captured["task_id"] = t.id

    monkeypatch.setattr(Orchestrator, "dispatch", _fake_dispatch)

    _install_unwrap(
        [_event_obj("event_resume", "session.status_idled", "sesn_match")]
    )
    resp = await client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["action"] == "resumed"
    assert body["result"]["task_id"] == "t1"
    assert captured == {"task_id": "t1"}
