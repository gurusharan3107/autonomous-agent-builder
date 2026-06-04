"""DB-backed Claude Agent SDK :class:`SessionStore` adapter.

Implements the ``claude_agent_sdk`` (0.2.85) ``SessionStore`` protocol over the
repo's SQLAlchemy 2 async layer. Ported 1:1 from the SDK's reference
``InMemorySessionStore`` (``claude_agent_sdk._internal.session_store``), swapping
its three in-memory dicts (``_store`` / ``_mtimes`` / ``_summaries``) for the two
backing tables :class:`~autonomous_agent_builder.db.models.SdkSessionTurn` and
:class:`~autonomous_agent_builder.db.models.SdkSessionSummary`.

Works on both aiosqlite (dev/test) and asyncpg (prod) — see the cross-dialect
note in ``models.py``. Each instance carries a unique ``instance_id`` that
namespaces all of its rows, so many instances (and the SDK conformance harness,
which reuses fixed project/session keys across a fresh store per contract) can
share one physical database without colliding.

Sessions are short-lived per call (``async with factory() as s: ... commit``),
never a long-lived/dispatch session (see repo memory: long-lived session
pattern / SSE pool exhaustion).

NOT wired into the runtime yet — this module only defines the adapter; selecting
it as the SDK's session store is a separate task.
"""

from __future__ import annotations

import time
from typing import cast
from uuid import uuid4

from claude_agent_sdk import (
    SessionKey,
    SessionListSubkeysKey,
    SessionStore,
    SessionStoreEntry,
    SessionStoreListEntry,
    SessionSummaryEntry,
    fold_session_summary,
)
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from autonomous_agent_builder.db.models import SdkSessionSummary, SdkSessionTurn
from autonomous_agent_builder.db.session import get_session_factory


class PostgresSessionStore(SessionStore):
    """SQLAlchemy-backed :class:`SessionStore` (Postgres prod, SQLite dev/test).

    Faithful port of the SDK reference ``InMemorySessionStore``: same composite
    keying, same strictly-monotonic ``mtime`` clock, same incremental summary
    fold, same subpath/cascade-delete semantics — just persisted to the DB.
    """

    def __init__(self, instance_id: str | None = None) -> None:
        # Namespace every row for this instance so concurrent/sequential stores
        # over one physical DB never collide on shared project/session keys.
        self._instance_id = instance_id or str(uuid4())
        # Process-local monotonic guard mirroring InMemory._last_mtime. Seeded
        # from the DB on each append so the clock stays monotonic across process
        # restarts that reattach to the same persisted instance.
        self._last_mtime = 0

    @property
    def instance_id(self) -> str:
        return self._instance_id

    def _now_ms(self) -> int:
        """Wall-clock epoch ms with a process-local monotonic guard.

        Distinct from InMemory only in that the floor is re-seeded from
        persisted rows in :meth:`_next_mtime` so monotonicity survives restart.
        """
        return int(time.time() * 1000)

    async def _next_mtime(self, session) -> int:
        """Strictly-increasing storage write time in epoch ms for this instance.

        Ports ``InMemorySessionStore._next_mtime`` but seeds the monotonic floor
        from the max persisted ``mtime`` across this instance's turns and
        summaries, so back-to-back appends always produce distinct, increasing
        mtimes even after a fresh process reattaches to the same instance_id.
        """
        max_turn = await session.scalar(
            select(func.max(SdkSessionTurn.mtime)).where(
                SdkSessionTurn.instance_id == self._instance_id
            )
        )
        max_summ = await session.scalar(
            select(func.max(SdkSessionSummary.mtime)).where(
                SdkSessionSummary.instance_id == self._instance_id
            )
        )
        floor = max(self._last_mtime, max_turn or 0, max_summ or 0)
        now_ms = self._now_ms()
        if now_ms <= floor:
            now_ms = floor + 1
        self._last_mtime = now_ms
        return now_ms

    # ------------------------------------------------------------------
    # Required: append + load
    # ------------------------------------------------------------------

    async def append(self, key: SessionKey, entries: list[SessionStoreEntry]) -> None:
        if not entries:
            # append([]) is a no-op (contract 4) — and must not advance mtime
            # or touch the summary, matching InMemory (which extends [] then
            # still stamps; we skip entirely since list_sessions reads the row
            # mtime and an empty append writes no row).
            return

        subpath = key.get("subpath")
        factory = get_session_factory()
        async with factory() as session:
            now_ms = await self._next_mtime(session)

            # Append order: continue from the current max seq for this logical key.
            max_seq = await session.scalar(
                select(func.max(SdkSessionTurn.seq)).where(
                    SdkSessionTurn.instance_id == self._instance_id,
                    SdkSessionTurn.project_key == key["project_key"],
                    SdkSessionTurn.session_id == key["session_id"],
                    SdkSessionTurn.subpath.is_(None)
                    if subpath is None
                    else SdkSessionTurn.subpath == subpath,
                )
            )
            seq = (max_seq or 0) + 1
            for entry in entries:
                session.add(
                    SdkSessionTurn(
                        instance_id=self._instance_id,
                        project_key=key["project_key"],
                        session_id=key["session_id"],
                        subpath=subpath,
                        seq=seq,
                        entry=dict(entry),
                        mtime=now_ms,
                    )
                )
                seq += 1

            # Maintain the per-session summary sidecar incrementally. Subagent
            # subpaths do NOT contribute to the main session's summary.
            if subpath is None:
                existing = await session.scalar(
                    select(SdkSessionSummary).where(
                        SdkSessionSummary.instance_id == self._instance_id,
                        SdkSessionSummary.project_key == key["project_key"],
                        SdkSessionSummary.session_id == key["session_id"],
                    )
                )
                prev: SessionSummaryEntry | None = None
                if existing is not None:
                    prev = {
                        "session_id": existing.session_id,
                        "mtime": existing.mtime,
                        "data": dict(existing.data),
                    }
                folded = fold_session_summary(prev, key, entries)
                # Stamp with this adapter's storage write time — the SAME clock
                # list_sessions exposes — so the fast-path staleness check holds.
                folded["mtime"] = now_ms
                if existing is None:
                    session.add(
                        SdkSessionSummary(
                            instance_id=self._instance_id,
                            project_key=key["project_key"],
                            session_id=key["session_id"],
                            data=dict(folded["data"]),
                            mtime=now_ms,
                        )
                    )
                else:
                    existing.data = dict(folded["data"])
                    existing.mtime = now_ms

            await session.commit()

    async def load(self, key: SessionKey) -> list[SessionStoreEntry] | None:
        subpath = key.get("subpath")
        factory = get_session_factory()
        async with factory() as session:
            rows = (
                await session.scalars(
                    select(SdkSessionTurn)
                    .where(
                        SdkSessionTurn.instance_id == self._instance_id,
                        SdkSessionTurn.project_key == key["project_key"],
                        SdkSessionTurn.session_id == key["session_id"],
                        SdkSessionTurn.subpath.is_(None)
                        if subpath is None
                        else SdkSessionTurn.subpath == subpath,
                    )
                    .order_by(SdkSessionTurn.seq, SdkSessionTurn.created_at)
                )
            ).all()
        if not rows:
            return None
        return cast("list[SessionStoreEntry]", [dict(r.entry) for r in rows])

    # ------------------------------------------------------------------
    # Optional: list_sessions
    # ------------------------------------------------------------------

    async def list_sessions(self, project_key: str) -> list[SessionStoreListEntry]:
        factory = get_session_factory()
        async with factory() as session:
            # Main transcripts only (subpath IS NULL). mtime = latest write for
            # the session, matching InMemory's per-key _mtimes value.
            rows = (
                await session.execute(
                    select(
                        SdkSessionTurn.session_id,
                        func.max(SdkSessionTurn.mtime),
                    )
                    .where(
                        SdkSessionTurn.instance_id == self._instance_id,
                        SdkSessionTurn.project_key == project_key,
                        SdkSessionTurn.subpath.is_(None),
                    )
                    .group_by(SdkSessionTurn.session_id)
                )
            ).all()
        return [{"session_id": sid, "mtime": mtime} for sid, mtime in rows]

    # ------------------------------------------------------------------
    # Optional: list_session_summaries
    # ------------------------------------------------------------------

    async def list_session_summaries(
        self, project_key: str
    ) -> list[SessionSummaryEntry]:
        factory = get_session_factory()
        async with factory() as session:
            rows = (
                await session.scalars(
                    select(SdkSessionSummary).where(
                        SdkSessionSummary.instance_id == self._instance_id,
                        SdkSessionSummary.project_key == project_key,
                    )
                )
            ).all()
        return [
            {
                "session_id": r.session_id,
                "mtime": r.mtime,
                "data": dict(r.data),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Optional: delete
    # ------------------------------------------------------------------

    async def delete(self, key: SessionKey) -> None:
        subpath = key.get("subpath")
        factory = get_session_factory()
        async with factory() as session:
            if subpath is None:
                # Deleting the main transcript cascades to its subkeys (subagent
                # transcripts) plus the summary sidecar so nothing is orphaned.
                await session.execute(
                    sa_delete(SdkSessionTurn).where(
                        SdkSessionTurn.instance_id == self._instance_id,
                        SdkSessionTurn.project_key == key["project_key"],
                        SdkSessionTurn.session_id == key["session_id"],
                    )
                )
                await session.execute(
                    sa_delete(SdkSessionSummary).where(
                        SdkSessionSummary.instance_id == self._instance_id,
                        SdkSessionSummary.project_key == key["project_key"],
                        SdkSessionSummary.session_id == key["session_id"],
                    )
                )
            else:
                # Targeted delete removes only that one subagent transcript.
                await session.execute(
                    sa_delete(SdkSessionTurn).where(
                        SdkSessionTurn.instance_id == self._instance_id,
                        SdkSessionTurn.project_key == key["project_key"],
                        SdkSessionTurn.session_id == key["session_id"],
                        SdkSessionTurn.subpath == subpath,
                    )
                )
            await session.commit()

    # ------------------------------------------------------------------
    # Optional: list_subkeys
    # ------------------------------------------------------------------

    async def list_subkeys(self, key: SessionListSubkeysKey) -> list[str]:
        factory = get_session_factory()
        async with factory() as session:
            rows = (
                await session.scalars(
                    select(SdkSessionTurn.subpath)
                    .where(
                        SdkSessionTurn.instance_id == self._instance_id,
                        SdkSessionTurn.project_key == key["project_key"],
                        SdkSessionTurn.session_id == key["session_id"],
                        SdkSessionTurn.subpath.is_not(None),
                    )
                    .distinct()
                )
            ).all()
        return [r for r in rows if r is not None]
