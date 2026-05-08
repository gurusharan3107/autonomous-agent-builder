"""Sprint-PR refactor schema migration (Phase A).

Adds the columns and indices needed to attach approval gates to sprints and to
track per-sprint integration branches and PR URLs:

* ``approval_gates.task_id`` — drop NOT NULL so sprint-level gates can omit it.
* ``approval_gates.sprint_id`` — new nullable FK to ``sprints``.
* ``sprints.branch`` — per-sprint integration branch name.
* ``sprints.pr_url`` — URL of the sprint-level PR.
* ``ix_approval_gates_sprint_status`` — composite index for sprint-gate lookups.

Idempotent: every step uses ``IF NOT EXISTS`` / ``PRAGMA`` checks so reruns
are safe. Mirrors :mod:`add_indices_2026_05` in shape and is applied from
``init_db`` after ``Base.metadata.create_all``.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def _has_column(conn: AsyncConnection, table: str, column: str) -> bool:
    dialect = conn.engine.dialect.name
    if dialect == "sqlite":
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        return any(row[1] == column for row in result.fetchall())
    # postgres / other
    result = await conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    )
    return result.first() is not None


async def _column_is_nullable(conn: AsyncConnection, table: str, column: str) -> bool:
    dialect = conn.engine.dialect.name
    if dialect == "sqlite":
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        for row in result.fetchall():
            if row[1] == column:
                # PRAGMA table_info: notnull is row[3]; 0 means nullable.
                return row[3] == 0
        return False
    result = await conn.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    )
    row = result.first()
    return bool(row and str(row[0]).upper() == "YES")


async def _drop_not_null_task_id_sqlite(conn: AsyncConnection) -> None:
    """SQLite cannot ALTER a column's NOT NULL — rebuild the table preserving rows."""
    if await _column_is_nullable(conn, "approval_gates", "task_id"):
        return
    await conn.execute(
        text(
            """
            CREATE TABLE approval_gates_new (
                id VARCHAR(36) PRIMARY KEY,
                task_id VARCHAR(36) REFERENCES tasks(id),
                sprint_id VARCHAR(36) REFERENCES sprints(id),
                gate_type VARCHAR(50) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP,
                resolved_at TIMESTAMP
            )
            """
        )
    )
    # Carry forward existing columns. ``sprint_id`` defaults to NULL for
    # legacy per-task rows, which is correct.
    await conn.execute(
        text(
            "INSERT INTO approval_gates_new "
            "(id, task_id, sprint_id, gate_type, status, created_at, resolved_at) "
            "SELECT id, task_id, NULL, gate_type, status, created_at, resolved_at "
            "FROM approval_gates"
        )
    )
    await conn.execute(text("DROP TABLE approval_gates"))
    await conn.execute(text("ALTER TABLE approval_gates_new RENAME TO approval_gates"))


async def _drop_not_null_task_id_approval_log_sqlite(conn: AsyncConnection) -> None:
    """Make ``approval_log.task_id`` nullable + add ``sprint_id``.

    SQLite needs a table rebuild to drop NOT NULL. Existing rows survive with
    their original ``task_id`` populated; sprint-level audit entries land
    after the migration with ``task_id=NULL`` and a populated ``sprint_id``.
    """
    has_sprint_id = await _has_column(conn, "approval_log", "sprint_id")
    task_id_nullable = await _column_is_nullable(conn, "approval_log", "task_id")
    if has_sprint_id and task_id_nullable:
        return
    await conn.execute(
        text(
            """
            CREATE TABLE approval_log_new (
                id VARCHAR(36) PRIMARY KEY,
                task_id VARCHAR(36) REFERENCES tasks(id),
                sprint_id VARCHAR(36) REFERENCES sprints(id),
                approver_email VARCHAR(255) NOT NULL,
                decision VARCHAR(50) NOT NULL,
                reason TEXT DEFAULT '',
                timestamp TIMESTAMP
            )
            """
        )
    )
    # Carry forward existing columns. Pre-migration rows always have ``task_id``
    # set; ``sprint_id`` defaults to NULL.
    await conn.execute(
        text(
            "INSERT INTO approval_log_new "
            "(id, task_id, sprint_id, approver_email, decision, reason, timestamp) "
            "SELECT id, task_id, NULL, approver_email, decision, reason, timestamp "
            "FROM approval_log"
        )
    )
    await conn.execute(text("DROP TABLE approval_log"))
    await conn.execute(text("ALTER TABLE approval_log_new RENAME TO approval_log"))


async def apply(conn: AsyncConnection) -> None:
    """Apply the sprint-PR schema migration."""
    dialect = conn.engine.dialect.name

    # 1) sprints.branch / sprints.pr_url ---------------------------------------
    if not await _has_column(conn, "sprints", "branch"):
        await conn.execute(text("ALTER TABLE sprints ADD COLUMN branch VARCHAR(255)"))
    if not await _has_column(conn, "sprints", "pr_url"):
        await conn.execute(text("ALTER TABLE sprints ADD COLUMN pr_url VARCHAR(1024)"))

    # 2) approval_gates.sprint_id ---------------------------------------------
    if not await _has_column(conn, "approval_gates", "sprint_id"):
        if dialect == "sqlite":
            await conn.execute(
                text(
                    "ALTER TABLE approval_gates ADD COLUMN sprint_id VARCHAR(36) "
                    "REFERENCES sprints(id)"
                )
            )
        else:
            await conn.execute(
                text(
                    "ALTER TABLE approval_gates ADD COLUMN sprint_id VARCHAR(36) "
                    "REFERENCES sprints(id)"
                )
            )

    # 3) drop NOT NULL on approval_gates.task_id ------------------------------
    if dialect == "sqlite":
        await _drop_not_null_task_id_sqlite(conn)
    else:
        if not await _column_is_nullable(conn, "approval_gates", "task_id"):
            await conn.execute(
                text("ALTER TABLE approval_gates ALTER COLUMN task_id DROP NOT NULL")
            )

    # 4) sprint-status index --------------------------------------------------
    await conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_approval_gates_sprint_status "
            "ON approval_gates (sprint_id, status)"
        )
    )

    # 5) approval_log: nullable task_id + sprint_id FK -------------------------
    if dialect == "sqlite":
        await _drop_not_null_task_id_approval_log_sqlite(conn)
    else:
        if not await _has_column(conn, "approval_log", "sprint_id"):
            await conn.execute(
                text(
                    "ALTER TABLE approval_log ADD COLUMN sprint_id VARCHAR(36) "
                    "REFERENCES sprints(id)"
                )
            )
        if not await _column_is_nullable(conn, "approval_log", "task_id"):
            await conn.execute(
                text("ALTER TABLE approval_log ALTER COLUMN task_id DROP NOT NULL")
            )
