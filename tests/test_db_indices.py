"""Verify secondary indices land on the database (Council 2026-05-08 Item 4)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from autonomous_agent_builder.db.migrations.add_indices_2026_05 import INDICES, apply
from autonomous_agent_builder.db.models import Base

EXPECTED_INDEX_NAMES = {name for name, _table, _cols in INDICES}


@pytest.mark.asyncio
async def test_init_creates_all_expected_indices(tmp_path):
    db_path = tmp_path / "indices.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await apply(conn)

        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))
            existing = {row[0] for row in result.fetchall()}

        missing = EXPECTED_INDEX_NAMES - existing
        assert not missing, f"missing indices: {missing}"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_apply_is_idempotent(tmp_path):
    db_path = tmp_path / "idempotent.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await apply(conn)
            # Second invocation must not raise on existing indices.
            await apply(conn)

        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'ix_%'")
            )
            named = {row[0] for row in result.fetchall()}

        assert EXPECTED_INDEX_NAMES.issubset(named)
    finally:
        await engine.dispose()
