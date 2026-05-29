"""Regression: chat_sessions.sdk_session_id write must survive `database is
locked` (P18 class) and never fail a completed run over bookkeeping.
Caught 2026-05-29 by the autoresearch fuzzer (fixture-D hang)."""
import asyncio

from sqlalchemy.exc import OperationalError

from autonomous_agent_builder.embedded.server import agent_chat_result_publisher as pub


class _FakeChatSession:
    def __init__(self):
        self.sdk_session_id = None
        self.updated_at = None


class _FakeDB:
    def __init__(self, behavior, session):
        self._behavior, self._session = behavior, session

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, _model, _sid):
        return self._session

    async def commit(self):
        if self._behavior() == "lock":
            raise OperationalError("UPDATE chat_sessions", {}, Exception("database is locked"))


def _factory(behavior, session):
    def get_factory():
        def factory():
            return _FakeDB(behavior, session)
        return factory
    return get_factory


async def _noop_sleep(_s):
    return None


def _run(coro):
    return asyncio.run(coro)


def test_non_fatal_on_persistent_lock(monkeypatch):
    sess = _FakeChatSession()
    monkeypatch.setattr(pub, "get_session_factory", _factory(lambda: "lock", sess))
    monkeypatch.setattr(pub.asyncio, "sleep", _noop_sleep)
    # Must NOT raise; returns False (gave up after retries) — run survives.
    assert _run(pub._persist_sdk_session_id("s1", "sdk-1")) is False


def test_retries_then_succeeds(monkeypatch):
    sess = _FakeChatSession()
    calls = {"n": 0}

    def behavior():
        calls["n"] += 1
        return "lock" if calls["n"] == 1 else "ok"

    monkeypatch.setattr(pub, "get_session_factory", _factory(behavior, sess))
    monkeypatch.setattr(pub.asyncio, "sleep", _noop_sleep)
    assert _run(pub._persist_sdk_session_id("s1", "sdk-1")) is True
    assert calls["n"] == 2  # exactly one retry
    assert sess.sdk_session_id == "sdk-1"


def test_skips_when_no_sdk_id(monkeypatch):
    # No subprocess/db touch needed; empty id short-circuits.
    assert _run(pub._persist_sdk_session_id("s1", None)) is False
