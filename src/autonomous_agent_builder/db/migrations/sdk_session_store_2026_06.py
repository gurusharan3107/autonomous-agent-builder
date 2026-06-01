"""Claude Agent SDK SessionStore backing tables (2026-06).

Creates the two tables the DB-backed ``PostgresSessionStore``
(:mod:`autonomous_agent_builder.db.session_store`) persists to:

* ``sdk_session_turns`` — one row per appended transcript entry.
* ``sdk_session_summaries`` — incrementally-folded per-session summary sidecar.

``Base.metadata.create_all`` already creates these on fresh databases; this
migration backfills pre-existing databases that were created before the models
landed. Idempotent: every statement uses ``CREATE TABLE/INDEX IF NOT EXISTS``,
so it is a safe no-op on every server boot. Mirrors
:mod:`add_indices_2026_05` / :mod:`sprint_pr_2026_05` in shape and is applied
from ``init_db`` after ``Base.metadata.create_all``.

Cross-dialect: ``entry``/``data`` use ``JSON`` (renders to TEXT on SQLite,
JSON on Postgres) — never JSONB — and ``mtime`` is ``BIGINT`` because epoch-ms
overflows 32-bit INTEGER. Both DDL forms are valid on SQLite and PostgreSQL.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

_CREATE_TURNS = """
CREATE TABLE IF NOT EXISTS sdk_session_turns (
    id VARCHAR(36) PRIMARY KEY,
    instance_id VARCHAR(36) NOT NULL,
    project_key VARCHAR(1024) NOT NULL,
    session_id VARCHAR(1024) NOT NULL,
    subpath VARCHAR(1024),
    seq INTEGER NOT NULL,
    entry JSON,
    mtime BIGINT NOT NULL,
    created_at TIMESTAMP
)
"""

_CREATE_SUMMARIES = """
CREATE TABLE IF NOT EXISTS sdk_session_summaries (
    id VARCHAR(36) PRIMARY KEY,
    instance_id VARCHAR(36) NOT NULL,
    project_key VARCHAR(1024) NOT NULL,
    session_id VARCHAR(1024) NOT NULL,
    data JSON,
    mtime BIGINT NOT NULL,
    created_at TIMESTAMP
)
"""

_INDICES: tuple[tuple[str, str], ...] = (
    (
        "ix_sdk_session_turns_key_seq",
        "sdk_session_turns (instance_id, project_key, session_id, subpath, seq)",
    ),
    (
        "ix_sdk_session_turns_project",
        "sdk_session_turns (instance_id, project_key)",
    ),
)


async def apply(conn: AsyncConnection) -> None:
    """Create the SDK SessionStore tables and indices if missing."""
    await conn.execute(text(_CREATE_TURNS))
    await conn.execute(text(_CREATE_SUMMARIES))
    for name, target in _INDICES:
        await conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {target}"))
    # Unique index on the summary logical key (one summary per main transcript).
    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_sdk_session_summaries_key "
            "ON sdk_session_summaries (instance_id, project_key, session_id)"
        )
    )
