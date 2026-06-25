"""Tests for _window_token_totals / window_token_totals in logs_runtime_aggregates."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from autonomous_agent_builder.cli.commands.logs_runtime_aggregates import (
    _window_token_totals,
    window_token_totals,
)


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table agent_runs (
            id text primary key,
            task_id text,
            agent_name text,
            tokens_input integer,
            tokens_output integer,
            tokens_cached integer,
            started_at text
        );
        """
    )
    conn.commit()
    conn.close()
    return db_path


def _insert_run(
    conn: sqlite3.Connection,
    run_id: str,
    agent_name: str,
    tokens_input: int,
    tokens_output: int,
    tokens_cached: int,
    started_at: str,
) -> None:
    conn.execute(
        "insert into agent_runs (id, task_id, agent_name, tokens_input, tokens_output, tokens_cached, started_at)"
        " values (?, ?, ?, ?, ?, ?, ?)",
        (run_id, "task-1", agent_name, tokens_input, tokens_output, tokens_cached, started_at),
    )


# noncached_plus_output = max(input - cached, 0) + output
# e.g. input=1000, cached=200, output=100  → max(800, 0) + 100 = 900


class TestWindowTokenTotals:
    def test_splits_at_boundary(self, tmp_path):
        """Runs before boundary count in before window; after boundary in after window."""
        db_path = _make_db(tmp_path)
        boundary = "2026-05-06T00:00:00+00:00"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Before: 2 runs at 800 noncached+output each
        _insert_run(conn, "before-1", "code-gen", 1000, 100, 200, "2026-05-05T12:00:00+00:00")
        _insert_run(conn, "before-2", "code-gen", 1000, 100, 200, "2026-05-05T23:59:59+00:00")
        # After: 3 runs at 900 noncached+output each
        _insert_run(conn, "after-1", "code-gen", 1000, 100, 100, "2026-05-06T01:00:00+00:00")
        _insert_run(conn, "after-2", "code-gen", 1000, 100, 100, "2026-05-06T02:00:00+00:00")
        _insert_run(conn, "after-3", "code-gen", 1000, 100, 100, "2026-05-06T03:00:00+00:00")
        conn.commit()

        before = _window_token_totals(conn, start_iso=None, end_iso=boundary)
        after = _window_token_totals(conn, start_iso=boundary, end_iso=None)

        conn.close()

        # before: 2 runs × 900 tokens (max(1000-200,0)+100) = 1800
        assert before["runs"] == 2
        assert before["tokens"] == 2 * (max(1000 - 200, 0) + 100)
        # after: 3 runs × 1000 tokens (max(1000-100,0)+100) = 3000
        assert after["runs"] == 3
        assert after["tokens"] == 3 * (max(1000 - 100, 0) + 100)

    def test_excludes_optimization_agent(self, tmp_path):
        """optimization-agent rows must be excluded by default."""
        db_path = _make_db(tmp_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        _insert_run(conn, "opt-1", "optimization-agent", 5000, 500, 0, "2026-05-06T01:00:00+00:00")
        _insert_run(conn, "gen-1", "code-gen", 1000, 100, 100, "2026-05-06T01:00:00+00:00")
        conn.commit()

        result = _window_token_totals(conn, start_iso=None, end_iso=None)
        conn.close()

        # Only code-gen row: max(1000-100,0)+100 = 1000
        assert result["runs"] == 1
        assert result["tokens"] == 1000

    def test_z_suffix_timezone_sorts_correctly(self, tmp_path):
        """Z-suffixed started_at sorts the same as +00:00 for julianday comparison."""
        db_path = _make_db(tmp_path)
        boundary = "2026-05-06T00:00:00+00:00"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Insert a run with a Z-suffix timestamp that is before the boundary.
        _insert_run(conn, "z-run", "code-gen", 1000, 200, 0, "2026-05-05T23:00:00Z")
        conn.commit()

        before = _window_token_totals(conn, start_iso=None, end_iso=boundary)
        after = _window_token_totals(conn, start_iso=boundary, end_iso=None)
        conn.close()

        assert before["runs"] == 1  # Z run is before boundary
        assert after["runs"] == 0

    def test_empty_table_returns_zero(self, tmp_path):
        db_path = _make_db(tmp_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        result = _window_token_totals(conn, start_iso=None, end_iso=None)
        conn.close()

        assert result == {"tokens": 0, "runs": 0}

    def test_null_started_at_excluded(self, tmp_path):
        """Rows with null started_at must be excluded."""
        db_path = _make_db(tmp_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "insert into agent_runs (id, task_id, agent_name, tokens_input, tokens_output, tokens_cached, started_at)"
            " values (?, ?, ?, ?, ?, ?, ?)",
            ("null-run", "task-1", "code-gen", 1000, 100, 100, None),
        )
        conn.commit()

        result = _window_token_totals(conn, start_iso=None, end_iso=None)
        conn.close()

        assert result["runs"] == 0

    def test_public_window_token_totals_wrapper(self, tmp_path):
        """window_token_totals public wrapper delegates correctly."""
        db_path = _make_db(tmp_path)
        conn = sqlite3.connect(db_path)
        _insert_run(conn, "run-1", "code-gen", 2000, 200, 500, "2026-05-07T10:00:00+00:00")
        conn.commit()
        conn.close()

        result = window_token_totals(db_path, start_iso=None, end_iso=None)
        # max(2000-500,0)+200 = 1700
        assert result["runs"] == 1
        assert result["tokens"] == max(2000 - 500, 0) + 200
