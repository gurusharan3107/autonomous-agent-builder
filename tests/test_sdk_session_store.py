"""Conformance + unit tests for the DB-backed Claude Agent SDK SessionStore.

The acceptance gate is the SDK's own ``run_session_store_conformance`` harness
(claude_agent_sdk.testing), which asserts the 14 behavioral contracts every
``SessionStore`` adapter must satisfy. We run it against
:class:`PostgresSessionStore` over the isolated SQLite ``test_db`` fixture.

The harness invokes ``make_store`` once per contract for isolation. Each
``PostgresSessionStore()`` gets a fresh ``instance_id`` that namespaces all its
rows, so the harness's reused fixed project/session keys never collide across
contracts even though they share one physical DB.
"""

from __future__ import annotations

import pytest
from claude_agent_sdk.testing import run_session_store_conformance

from autonomous_agent_builder.db.session_store import PostgresSessionStore

_KEY = {"project_key": "proj", "session_id": "sess"}


@pytest.mark.asyncio
async def test_sdk_session_store_conformance(test_db):
    """PostgresSessionStore passes the full SDK conformance suite (14 contracts)."""
    # make_store: fresh, isolated logical store per contract via unique instance_id.
    await run_session_store_conformance(lambda: PostgresSessionStore())


@pytest.mark.asyncio
async def test_append_load_roundtrip(test_db):
    store = PostgresSessionStore()
    entries = [
        {"type": "user", "uuid": "u1", "n": 1},
        {"type": "assistant", "uuid": "a1", "n": 2},
    ]
    await store.append(_KEY, entries)
    loaded = await store.load(_KEY)
    assert loaded == entries
    # Unknown key returns None.
    assert await store.load({"project_key": "proj", "session_id": "missing"}) is None


@pytest.mark.asyncio
async def test_monotonic_mtime_across_appends(test_db):
    """mtime is strictly increasing across appends, even back-to-back ones."""
    store = PostgresSessionStore()
    mtimes: list[int] = []
    for i in range(5):
        await store.append(
            {"project_key": "proj", "session_id": f"s{i}"},
            [{"type": "x", "n": i}],
        )
    sessions = await store.list_sessions("proj")
    mtimes = sorted(s["mtime"] for s in sessions)
    # All distinct and strictly increasing.
    assert len(set(mtimes)) == len(mtimes)
    assert mtimes == sorted(mtimes)
    # Epoch-ms, not epoch-seconds.
    assert all(m > 1e12 for m in mtimes)


@pytest.mark.asyncio
async def test_subpath_excluded_from_summary(test_db):
    """Subagent (subpath) appends never contribute to the main session summary."""
    store = PostgresSessionStore()
    key = {"project_key": "proj", "session_id": "main"}
    await store.append(
        key,
        [{"type": "x", "timestamp": "2024-01-01T00:00:00.000Z", "customTitle": "main"}],
    )
    before = await store.list_session_summaries("proj")
    assert len(before) == 1
    data_before = before[0]["data"]

    # Subagent append under the same session.
    await store.append(
        {**key, "subpath": "subagents/agent-1"},
        [{"type": "x", "timestamp": "2024-01-01T00:00:09.000Z", "customTitle": "sub"}],
    )
    after = {s["session_id"]: s for s in await store.list_session_summaries("proj")}
    # Still exactly one summary (the main one), and its data is unchanged.
    assert set(after) == {"main"}
    assert after["main"]["data"] == data_before
    # But the subagent transcript IS stored and loadable + listed as a subkey.
    assert await store.load({**key, "subpath": "subagents/agent-1"}) is not None
    assert await store.list_subkeys(key) == ["subagents/agent-1"]


@pytest.mark.asyncio
async def test_instance_isolation(test_db):
    """Two stores sharing the DB do not see each other's data."""
    a = PostgresSessionStore()
    b = PostgresSessionStore()
    assert a.instance_id != b.instance_id
    await a.append(_KEY, [{"type": "x", "from": "a"}])
    assert await b.load(_KEY) is None
    assert await a.load(_KEY) == [{"type": "x", "from": "a"}]


@pytest.mark.asyncio
async def test_delete_cascades_to_subkeys(test_db):
    store = PostgresSessionStore()
    sub = {**_KEY, "subpath": "subagents/agent-1"}
    await store.append(_KEY, [{"type": "x", "n": 1}])
    await store.append(sub, [{"type": "x", "n": 1}])
    await store.delete(_KEY)
    assert await store.load(_KEY) is None
    assert await store.load(sub) is None
    assert await store.list_session_summaries("proj") == []
