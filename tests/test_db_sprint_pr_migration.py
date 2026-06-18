"""Verify sprint-PR Phase A schema migration lands on a SQLite DB."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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


@pytest.mark.asyncio
async def test_init_db_adds_ui_preview_enabled_column_to_legacy_features_table(tmp_path):
    """init_db must ALTER a legacy features table that lacks ui_preview_enabled.

    Failure mode without the fix: the column is absent and any ORM query on
    features raises sqlite3.OperationalError: no such column: features.ui_preview_enabled.
    """
    import autonomous_agent_builder.db.session as session_mod
    from autonomous_agent_builder.db.session import init_db

    db_path = tmp_path / "legacy_features.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    # Build a legacy DB: create all tables via create_all on a temporary engine,
    # then DROP the features table and re-create it without ui_preview_enabled.
    # This simulates a pre-IMP-034b database upgraded through all prior ALTER
    # guards but never receiving ui_preview_enabled.
    bootstrap_engine = create_async_engine(url, connect_args={"timeout": 15})
    async with bootstrap_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("DROP TABLE features"))
        await conn.execute(
            text(
                "CREATE TABLE features ("
                "  id VARCHAR(36) PRIMARY KEY,"
                "  project_id VARCHAR(36) NOT NULL REFERENCES projects(id),"
                "  title VARCHAR(255) NOT NULL,"
                "  description TEXT DEFAULT '',"
                "  status VARCHAR(32) DEFAULT 'pending',"
                "  priority INTEGER DEFAULT 0,"
                "  item_type VARCHAR(32) DEFAULT 'feature',"
                "  tags JSON DEFAULT '[]',"
                "  severity VARCHAR(32),"
                "  source VARCHAR(32) DEFAULT 'manual',"
                "  evidence TEXT DEFAULT '',"
                "  acceptance_criteria JSON DEFAULT '[]',"
                "  dependencies JSON DEFAULT '[]',"
                "  proposed_tasks JSON DEFAULT '[]',"
                "  created_at DATETIME,"
                "  updated_at DATETIME"
                ")"
            )
        )
    await bootstrap_engine.dispose()

    # Confirm ui_preview_enabled is absent before init_db runs.
    verify_engine = create_async_engine(url, connect_args={"timeout": 15})
    async with verify_engine.connect() as conn:
        result = await conn.execute(text("PRAGMA table_info(features)"))
        pre_columns = {row[1] for row in result.fetchall()}
    await verify_engine.dispose()
    assert "ui_preview_enabled" not in pre_columns, (
        "Test setup error: ui_preview_enabled should not be present before init_db"
    )

    # Redirect the global engine to the legacy DB and run init_db().
    legacy_engine = create_async_engine(url, connect_args={"timeout": 15})
    old_engine = session_mod._engine
    old_factory = session_mod._session_factory
    session_mod._engine = legacy_engine
    session_mod._session_factory = async_sessionmaker(
        legacy_engine, class_=AsyncSession, expire_on_commit=False
    )
    try:
        await init_db()
    finally:
        session_mod._engine = old_engine
        session_mod._session_factory = old_factory
        await legacy_engine.dispose()

    # Confirm the column is now present.
    post_engine = create_async_engine(url, connect_args={"timeout": 15})
    try:
        async with post_engine.connect() as conn:
            result = await conn.execute(text("PRAGMA table_info(features)"))
            post_columns = {row[1] for row in result.fetchall()}
        assert "ui_preview_enabled" in post_columns, (
            "init_db must ALTER the features table to add ui_preview_enabled"
        )
        # Verify a SELECT on the column does not raise OperationalError.
        async with post_engine.connect() as conn:
            await conn.execute(text("SELECT ui_preview_enabled FROM features LIMIT 1"))
    finally:
        await post_engine.dispose()
