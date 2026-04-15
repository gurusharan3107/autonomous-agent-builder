"""Dual-audience output rendering — JSON for agents, text for humans.

TTY detection: JSON when stdout is piped or --json flag is set.
Readable text tables when running in a terminal.
Context window protection via truncation defaults.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any


def is_tty() -> bool:
    """Check if stdout is a terminal (not piped)."""
    return sys.stdout.isatty()


def render(
    data: Any,
    format_fn: Callable[[Any], str],
    *,
    use_json: bool = False,
) -> None:
    """Render data as JSON or formatted text.

    Uses JSON when:
    - --json flag is set (use_json=True)
    - stdout is piped (not a TTY)

    Uses format_fn for human-readable terminal output.
    """
    if use_json or not is_tty():
        print(json.dumps(data, indent=2, default=str))
    else:
        print(format_fn(data))


def render_json(data: Any) -> None:
    """Always render as JSON regardless of TTY."""
    print(json.dumps(data, indent=2, default=str))


def truncate(text: str, max_chars: int = 2000) -> str:
    """Truncate text for context window protection.

    Appends a marker when truncated so agents know to use --full.
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... (truncated, use --full for complete output)"


def table(headers: list[str], rows: list[list[str]], *, max_col_width: int = 40) -> str:
    """Render an aligned text table for TTY output.

    Columns auto-size to content with a configurable max width.
    """
    if not rows:
        return "(no results)"

    # Truncate cells
    truncated_rows = []
    for row in rows:
        truncated_rows.append([
            cell[:max_col_width] + "..." if len(cell) > max_col_width else cell
            for cell in row
        ])

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in truncated_rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    # Build header
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    separator = "  ".join("-" * w for w in widths)

    # Build rows
    row_lines = []
    for row in truncated_rows:
        cells = []
        for i, cell in enumerate(row):
            if i < len(widths):
                cells.append(cell.ljust(widths[i]))
        row_lines.append("  ".join(cells))

    return "\n".join([header_line, separator, *row_lines])


def format_status(status: str) -> str:
    """Format a status string for terminal display."""
    status_upper = status.upper().replace("_", " ")
    return status_upper


def success(message: str) -> None:
    """Print a success message to stdout."""
    print(message)


def error(message: str) -> None:
    """Print an error message to stderr."""
    print(message, file=sys.stderr)
