"""Tests for database session management."""

from __future__ import annotations

import pytest

from autonomous_agent_builder.db.session import close_db, get_engine, get_session_factory


@pytest.mark.asyncio
class TestSessionManagement:
    """Test session factory and lifecycle."""

    async def test_init_db_creates_tables(self, test_db):
        """init_db is implicitly tested by the test_db fixture creating all tables."""
        engine, factory = test_db
        async with factory() as session:
            result = await session.execute(
                __import__("sqlalchemy").text("SELECT name FROM sqlite_master WHERE type='table'")
            )
            tables = [r[0] for r in result.fetchall()]
            assert "projects" in tables
            assert "features" in tables
            assert "tasks" in tables

    async def test_session_factory_returns_sessions(self, test_db):
        _, factory = test_db
        async with factory() as session:
            assert session is not None

    async def test_close_db(self, test_db):
        """close_db disposes engine without error."""
        await close_db()

    async def test_get_engine_returns_engine(self, test_db):
        engine = get_engine()
        assert engine is not None

    async def test_get_session_factory_returns_factory(self, test_db):
        factory = get_session_factory()
        assert factory is not None
