"""Verify sprint-PR Phase A schema migration lands on a SQLite DB."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from autonomous_agent_builder.db.migrations.add_indices_2026_05 import apply as apply_indices
from autonomous_agent_builder.db.migrations.sprint_pr_2026_05 import apply as apply_sprint_pr
from autonomous_agent_builder.db.models import Base


async def _bootstrap(db_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await apply_indices(conn)
        await apply_sprint_pr(conn)
    return engine


@pytest.mark.asyncio
async def test_sprints_branch_and_pr_url_columns_present(tmp_path):
    db_path = tmp_path / "sprint_a.db"
    engine = await _bootstrap(db_path)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("PRAGMA table_info(sprints)"))
            columns = {row[1] for row in result.fetchall()}
        assert "branch" in columns
        assert "pr_url" in columns
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_approval_gates_sprint_id_present_and_task_id_nullable(tmp_path):
    db_path = tmp_path / "sprint_b.db"
    engine = await _bootstrap(db_path)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("PRAGMA table_info(approval_gates)"))
            rows = list(result.fetchall())
        by_name = {row[1]: row for row in rows}
        assert "sprint_id" in by_name
        # PRAGMA table_info: notnull is row[3]; 0 means nullable.
        assert by_name["task_id"][3] == 0, "task_id must be nullable for sprint_pr gates"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sprint_status_index_present(tmp_path):
    db_path = tmp_path / "sprint_c.db"
    engine = await _bootstrap(db_path)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='index'")
            )
            indices = {row[0] for row in result.fetchall()}
        assert "ix_approval_gates_sprint_status" in indices
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sprint_pr_apply_is_idempotent(tmp_path):
    db_path = tmp_path / "sprint_d.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await apply_indices(conn)
            await apply_sprint_pr(conn)
            # Second invocation must not raise; columns and indices already exist.
            await apply_sprint_pr(conn)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sprint_pr_migration_preserves_existing_approval_gate_rows(tmp_path):
    """SQLite table-rebuild path must carry forward existing rows."""
    db_path = tmp_path / "sprint_e.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await apply_indices(conn)
            # Seed a row pretending we are a pre-migration database: insert a
            # row before the sprint_pr migration runs.
            await conn.execute(
                text(
                    "INSERT INTO approval_gates "
                    "(id, task_id, gate_type, status, created_at) "
                    "VALUES ('gate-1', 'task-1', 'planning', 'pending', "
                    "'2026-05-01T00:00:00+00:00')"
                )
            )
            await apply_sprint_pr(conn)

        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT id, task_id, sprint_id, gate_type, status FROM approval_gates")
            )
            rows = result.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "gate-1"
        assert rows[0][1] == "task-1"
        assert rows[0][2] is None  # sprint_id starts NULL for legacy rows
        assert rows[0][3] == "planning"
        assert rows[0][4] == "pending"
    finally:
        await engine.dispose()
