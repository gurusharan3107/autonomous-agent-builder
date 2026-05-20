"""Add secondary indices on hot-filter columns.

Council 2026-05-08 — Item 4: ``db/models.py`` had no secondary indices, so every
filtered query (project_id, task_id, status, created_at, run_id, ...) performed
a full table scan. The 12 indices below match the columns the dashboard, board,
inbox, metrics, and approval surfaces filter on most.

Idempotent: ``CREATE INDEX IF NOT EXISTS`` is a no-op when the index already
exists, so this can run on every server boot. SQLite and PostgreSQL both
support the syntax.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

# (index_name, table, column_list_for_CREATE_INDEX)
INDICES: tuple[tuple[str, str, str], ...] = (
    ("ix_features_project_status_created", "features", "project_id, status, created_at"),
    ("ix_sprints_project_phase", "sprints", "project_id, phase"),
    ("ix_tasks_feature_status", "tasks", "feature_id, status"),
    ("ix_tasks_status_phase", "tasks", "status, phase"),
    ("ix_gate_results_task_status", "gate_results", "task_id, status"),
    ("ix_approval_gates_task_status", "approval_gates", "task_id, status"),
    ("ix_agent_runs_task_started", "agent_runs", "task_id, started_at"),
    ("ix_agent_runs_status", "agent_runs", "status"),
    ("ix_agent_run_events_run_ts", "agent_run_events", "run_id, timestamp"),
    (
        "ix_chat_events_session_type_created",
        "chat_events",
        "session_id, event_type, created_at",
    ),
    ("ix_builder_recs_status", "builder_recommendations", "status"),
    ("ix_builder_recs_source_run", "builder_recommendations", "source_run_id"),
)


async def apply(conn: AsyncConnection) -> None:
    """Create every index in :data:`INDICES` if missing."""
    for name, table, cols in INDICES:
        await conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})"))
