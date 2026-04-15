"""E2E test fixtures — async DB, HTTP client, mock SDK, synthetic workspace."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autonomous_agent_builder.agents.runner import AgentRunner, RunResult
from autonomous_agent_builder.db.models import Base

# Prevent pytest from collecting tests inside the synthetic project
collect_ignore_glob = ["synthetic_project/*"]

SYNTHETIC_PROJECT = Path(__file__).parent / "synthetic_project"


# ── Database ──


@pytest_asyncio.fixture
async def test_db(tmp_path):
    """Create an isolated SQLite test database and inject it into the session module."""
    import autonomous_agent_builder.db.session as session_mod

    db_path = tmp_path / "e2e_test.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Override the module-level globals so all code paths use our test DB
    old_engine = session_mod._engine
    old_factory = session_mod._session_factory
    session_mod._engine = engine
    session_mod._session_factory = factory

    yield engine, factory

    # Restore originals and dispose
    session_mod._engine = old_engine
    session_mod._session_factory = old_factory
    await engine.dispose()


# ── HTTP Client ──


@pytest_asyncio.fixture
async def client(test_db):
    """Async HTTP client backed by the test database."""
    from autonomous_agent_builder.api.app import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── Workspace ──


@pytest.fixture
def workspace_path(tmp_path):
    """Copy synthetic project to a temp dir and git-init it."""
    workspace = tmp_path / "workspace"
    shutil.copytree(SYNTHETIC_PROJECT, workspace)

    # Initialize as a git repository (quality gates need this)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "e2e-test",
        "GIT_COMMITTER_NAME": "e2e-test",
        "GIT_AUTHOR_EMAIL": "e2e@test.com",
        "GIT_COMMITTER_EMAIL": "e2e@test.com",
    }
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True, env=env)
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "Initial synthetic project"],
        cwd=workspace,
        check=True,
        capture_output=True,
        env=env,
    )

    return workspace


# ── Mock Agent Runner ──


def _mock_run_result(agent_name: str) -> RunResult:
    """Realistic RunResult with cost/token data for each agent type."""
    data = {
        "planner": (0.0850, 15000, 3000, 5000, 8, 45000, "session-planner-e2e"),
        "designer": (0.0620, 12000, 2500, 4000, 6, 35000, "session-designer-e2e"),
        "code-gen": (0.1200, 20000, 5000, 8000, 15, 90000, "session-codegen-e2e"),
        "pr-creator": (0.0350, 8000, 1500, 3000, 4, 20000, "session-pr-e2e"),
        "build-verifier": (0.0200, 5000, 1000, 2000, 3, 15000, "session-build-e2e"),
    }
    cost, tok_in, tok_out, tok_cached, turns, duration, sid = data.get(
        agent_name, (0.05, 10000, 2000, 3000, 5, 30000, "session-unknown-e2e")
    )
    return RunResult(
        session_id=sid,
        cost_usd=cost,
        tokens_input=tok_in,
        tokens_output=tok_out,
        tokens_cached=tok_cached,
        num_turns=turns,
        duration_ms=duration,
        stop_reason="end_turn",
        output_text=f"Completed {agent_name} phase successfully.",
    )


@pytest.fixture
def mock_sdk():
    """Patch AgentRunner._execute_query to return mock results (no real SDK calls)."""

    async def _fake_execute(
        self, agent_def, prompt, workspace_path, registry, resume_session, on_stream
    ):
        return _mock_run_result(agent_def.name)

    with patch.object(AgentRunner, "_execute_query", _fake_execute):
        yield
