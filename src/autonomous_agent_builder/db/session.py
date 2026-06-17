"""Async database session — supports PostgreSQL (prod) and SQLite (local dev)."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autonomous_agent_builder.config import get_settings

_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        kwargs: dict = {"echo": settings.debug}
        if settings.db.driver == "postgresql":
            kwargs.update(pool_size=10, max_overflow=20, pool_pre_ping=True)
        elif settings.db.driver == "sqlite":
            kwargs.update(connect_args={"timeout": 15})
        _engine = create_async_engine(settings.db.url, **kwargs)
        if settings.db.driver == "sqlite":
            sync_engine = _engine.sync_engine

            @event.listens_for(sync_engine, "connect")
            def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA busy_timeout=15000")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for DB sessions."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables — for development/testing only. Use Alembic in prod."""
    from autonomous_agent_builder.db.migrations import (
        add_indices_2026_05,
        sdk_session_store_2026_06,
        sprint_pr_2026_05,
    )
    from autonomous_agent_builder.db.models import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Council 2026-05-08 — Item 4: ensure secondary indices exist on
        # databases created before __table_args__ landed in models.py.
        await add_indices_2026_05.apply(conn)
        # Sprint-PR refactor (2026-05) — Phase A schema additions.
        await sprint_pr_2026_05.apply(conn)
        # Claude Agent SDK SessionStore backing tables (2026-06) — backfill on
        # databases created before the models landed.
        await sdk_session_store_2026_06.apply(conn)
        if engine.dialect.name == "sqlite":
            result = await conn.execute(text("PRAGMA table_info(chat_sessions)"))
            columns = {row[1] for row in result.fetchall()}
            if "repo_identity" not in columns:
                await conn.execute(
                    text("ALTER TABLE chat_sessions ADD COLUMN repo_identity VARCHAR(1024)")
                )
            if "workspace_cwd" not in columns:
                await conn.execute(
                    text("ALTER TABLE chat_sessions ADD COLUMN workspace_cwd VARCHAR(1024)")
                )
            result = await conn.execute(text("PRAGMA table_info(features)"))
            feature_columns = {row[1] for row in result.fetchall()}
            if "item_type" not in feature_columns:
                await conn.execute(
                    text("ALTER TABLE features ADD COLUMN item_type VARCHAR(32) DEFAULT 'feature'")
                )
            if "tags" not in feature_columns:
                await conn.execute(text("ALTER TABLE features ADD COLUMN tags JSON DEFAULT '[]'"))
            if "severity" not in feature_columns:
                await conn.execute(text("ALTER TABLE features ADD COLUMN severity VARCHAR(32)"))
            if "source" not in feature_columns:
                await conn.execute(
                    text("ALTER TABLE features ADD COLUMN source VARCHAR(32) DEFAULT 'manual'")
                )
            if "evidence" not in feature_columns:
                await conn.execute(text("ALTER TABLE features ADD COLUMN evidence TEXT DEFAULT ''"))
            if "acceptance_criteria" not in feature_columns:
                await conn.execute(
                    text("ALTER TABLE features ADD COLUMN acceptance_criteria JSON DEFAULT '[]'")
                )
            if "dependencies" not in feature_columns:
                await conn.execute(
                    text("ALTER TABLE features ADD COLUMN dependencies JSON DEFAULT '[]'")
                )
            if "proposed_tasks" not in feature_columns:
                await conn.execute(
                    text("ALTER TABLE features ADD COLUMN proposed_tasks JSON DEFAULT '[]'")
                )
            if "ui_preview_enabled" not in feature_columns:
                await conn.execute(
                    text("ALTER TABLE features ADD COLUMN ui_preview_enabled BOOLEAN DEFAULT 0")
                )
            result = await conn.execute(text("PRAGMA table_info(agent_runs)"))
            run_columns = {row[1] for row in result.fetchall()}
            if "output_text" not in run_columns:
                await conn.execute(
                    text("ALTER TABLE agent_runs ADD COLUMN output_text TEXT DEFAULT ''")
                )
            if "runtime_sdk" not in run_columns:
                await conn.execute(
                    text("ALTER TABLE agent_runs ADD COLUMN runtime_sdk VARCHAR(50) DEFAULT ''")
                )
            if "provider" not in run_columns:
                await conn.execute(
                    text("ALTER TABLE agent_runs ADD COLUMN provider VARCHAR(100) DEFAULT ''")
                )
            if "model" not in run_columns:
                await conn.execute(
                    text("ALTER TABLE agent_runs ADD COLUMN model VARCHAR(100) DEFAULT ''")
                )
            if "effort" not in run_columns:
                await conn.execute(text("ALTER TABLE agent_runs ADD COLUMN effort VARCHAR(32)"))
            if "observability" not in run_columns:
                await conn.execute(text("ALTER TABLE agent_runs ADD COLUMN observability JSON"))
            result = await conn.execute(text("PRAGMA table_info(tasks)"))
            task_columns = {row[1] for row in result.fetchall()}
            if "chat_session_id" not in task_columns:
                await conn.execute(
                    text("ALTER TABLE tasks ADD COLUMN chat_session_id VARCHAR(36)")
                )
                await conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_tasks_chat_session_id "
                        "ON tasks (chat_session_id)"
                    )
                )


async def close_db() -> None:
    """Close engine connections."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
