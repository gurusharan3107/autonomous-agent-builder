"""Tests for /api/managed-agents/webhook (Phase E)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autonomous_agent_builder.api.routes import managed_agents_webhook


def _make_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Mount just the webhook router for isolated testing."""
    app = FastAPI()
    app.include_router(managed_agents_webhook.router, prefix="/api")
    monkeypatch.setenv("ANTHROPIC_WEBHOOK_SIGNING_KEY", "whsec_test")
    managed_agents_webhook._reset_seen_ids()
    yield_state: dict[str, Any] = {"last_event": None}
    return app, yield_state  # type: ignore[return-value]


@pytest.fixture
def webhook_app(monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, dict[str, Any]]:
    app, state = _make_app(monkeypatch)
    yield app, state
    managed_agents_webhook._set_unwrap_override(None)


def _install_unwrap(events: list[Any]) -> Any:
    """Install a fake unwrap that returns events from the supplied list in order."""
    iter_state = iter(events)

    def _fake_unwrap(_body: bytes, headers: dict[str, str]) -> Any:
        return next(iter_state)

    managed_agents_webhook._set_unwrap_override(_fake_unwrap)
    return _fake_unwrap


def _event_obj(event_id: str, event_type: str, data_id: str = "sesn_x") -> Any:
    """Mirror the SDK's unwrapped object shape (attrs, not dicts)."""
    data = SimpleNamespace(type=event_type, id=data_id)
    return SimpleNamespace(id=event_id, data=data)


def test_webhook_returns_503_when_signing_key_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_WEBHOOK_SIGNING_KEY", raising=False)
    managed_agents_webhook._reset_seen_ids()
    app = FastAPI()
    app.include_router(managed_agents_webhook.router, prefix="/api")
    client = TestClient(app)
    resp = client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == "missing_signing_key"


def test_webhook_returns_400_on_unwrap_failure(
    webhook_app: tuple[FastAPI, dict[str, Any]],
) -> None:
    app, _ = webhook_app

    def _bad_unwrap(_body: bytes, _headers: dict[str, str]) -> Any:
        raise ValueError("bad signature")

    managed_agents_webhook._set_unwrap_override(_bad_unwrap)
    client = TestClient(app)
    resp = client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "invalid_signature_or_payload"
    assert "bad signature" in body["detail"]


def test_webhook_dispatches_session_idled(
    webhook_app: tuple[FastAPI, dict[str, Any]],
) -> None:
    app, _ = webhook_app
    _install_unwrap([_event_obj("event_1", "session.status_idled", "sesn_a")])
    client = TestClient(app)
    resp = client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["skipped"] is False
    assert body["event_id"] == "event_1"
    assert body["type"] == "session.status_idled"
    assert "result" in body


def test_webhook_dispatches_session_terminated(
    webhook_app: tuple[FastAPI, dict[str, Any]],
) -> None:
    app, _ = webhook_app
    _install_unwrap([_event_obj("event_2", "session.status_terminated")])
    client = TestClient(app)
    resp = client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 200
    assert resp.json()["type"] == "session.status_terminated"


def test_webhook_dispatches_outcome_evaluation_ended(
    webhook_app: tuple[FastAPI, dict[str, Any]],
) -> None:
    app, _ = webhook_app
    _install_unwrap([_event_obj("event_3", "session.outcome_evaluation_ended")])
    client = TestClient(app)
    resp = client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 200
    assert resp.json()["type"] == "session.outcome_evaluation_ended"


def test_webhook_dispatches_vault_credential_refresh_failed(
    webhook_app: tuple[FastAPI, dict[str, Any]],
) -> None:
    app, _ = webhook_app
    _install_unwrap([_event_obj("event_4", "vault_credential.refresh_failed")])
    client = TestClient(app)
    resp = client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 200
    assert resp.json()["type"] == "vault_credential.refresh_failed"


def test_webhook_returns_unhandled_type_for_unknown(
    webhook_app: tuple[FastAPI, dict[str, Any]],
) -> None:
    app, _ = webhook_app
    _install_unwrap([_event_obj("event_5", "session.thread_idled")])
    client = TestClient(app)
    resp = client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["unhandled_type"] == "session.thread_idled"


def test_webhook_dedupes_repeat_event_id(
    webhook_app: tuple[FastAPI, dict[str, Any]],
) -> None:
    """Same event id appearing twice → first processes, second is `skipped`."""
    app, _ = webhook_app
    # Both calls return the SAME event id (Anthropic retry pattern)
    _install_unwrap(
        [
            _event_obj("event_dup", "session.status_idled"),
            _event_obj("event_dup", "session.status_idled"),
        ]
    )
    client = TestClient(app)
    first = client.post("/api/managed-agents/webhook", json={})
    second = client.post("/api/managed-agents/webhook", json={})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["skipped"] is False
    assert second.json()["skipped"] is True


def test_webhook_returns_400_when_event_id_missing(
    webhook_app: tuple[FastAPI, dict[str, Any]],
) -> None:
    app, _ = webhook_app
    bad_event = SimpleNamespace(id=None, data=SimpleNamespace(type="x", id="y"))
    _install_unwrap([bad_event])
    client = TestClient(app)
    resp = client.post("/api/managed-agents/webhook", json={})
    assert resp.status_code == 400
    assert resp.json()["code"] == "missing_event_id"


def test_dedupe_ring_evicts_oldest_when_full(
    webhook_app: tuple[FastAPI, dict[str, Any]],
) -> None:
    """Sustained traffic above _SEEN_LIMIT must not OOM — oldest evicts."""
    original_limit = managed_agents_webhook._SEEN_LIMIT
    try:
        # Shrink the ring for the test
        managed_agents_webhook._SEEN_LIMIT = 4  # type: ignore[attr-defined]
        for i in range(6):
            assert managed_agents_webhook._record_event_id(f"e{i}") is False
        # The first inserted (e0) should have evicted by now
        assert managed_agents_webhook._record_event_id("e0") is False
    finally:
        managed_agents_webhook._SEEN_LIMIT = original_limit  # type: ignore[attr-defined]
