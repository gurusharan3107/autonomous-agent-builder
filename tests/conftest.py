"""Shared test fixtures."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autonomous_agent_builder.agents.runner import AgentRunner, RunResult
from autonomous_agent_builder.db.models import Base


@pytest.fixture
def sample_workspace(tmp_path):
    """Create a sample workspace with basic Python project structure."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "main.py").write_text('def hello() -> str:\n    return "hello"\n')

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("")
    (tests / "test_main.py").write_text(
        "from src.main import hello\n\ndef test_hello():\n    assert hello() == 'hello'\n"
    )

    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 100\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
    )

    return tmp_path


# ── Async DB ──


@pytest_asyncio.fixture
async def test_db(tmp_path):
    """Isolated SQLite test database with all tables created."""
    import autonomous_agent_builder.db.session as session_mod

    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(url, echo=False)
    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    old_engine = session_mod._engine
    old_factory = session_mod._session_factory
    session_mod._engine = engine
    session_mod._session_factory = factory

    yield engine, factory

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


# ── Mock Agent Runner ──


def _mock_run_result(agent_name: str) -> RunResult:
    """Realistic RunResult for each agent type."""
    data = {
        "planner": (0.085, 15000, 3000, 5000, 8, 45000, "sess-planner"),
        "designer": (0.062, 12000, 2500, 4000, 6, 35000, "sess-designer"),
        "code-gen": (0.120, 20000, 5000, 8000, 15, 90000, "sess-codegen"),
        "pr-creator": (0.035, 8000, 1500, 3000, 4, 20000, "sess-pr"),
        "build-verifier": (0.020, 5000, 1000, 2000, 3, 15000, "sess-build"),
    }
    cost, ti, to, tc, turns, dur, sid = data.get(
        agent_name, (0.05, 10000, 2000, 3000, 5, 30000, "sess-unknown")
    )
    return RunResult(
        session_id=sid,
        cost_usd=cost,
        tokens_input=ti,
        tokens_output=to,
        tokens_cached=tc,
        num_turns=turns,
        duration_ms=dur,
        stop_reason="end_turn",
        output_text=f"Completed {agent_name} phase.",
    )


@pytest.fixture
def mock_sdk():
    """Patch AgentRunner to return mock results (no real SDK calls)."""

    async def _fake_execute(
        self, agent_def, prompt, workspace_path, registry, resume_session, on_stream
    ):
        return _mock_run_result(agent_def.name)

    with patch.object(AgentRunner, "_execute_query", _fake_execute):
        yield
