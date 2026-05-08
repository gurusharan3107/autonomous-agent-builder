"""Dual-audience output rendering — JSON for agents, text for humans.

TTY detection: JSON when stdout is piped or --json flag is set.
Readable text tables when running in a terminal.
Context window protection via truncation defaults.
"""

from __future__ import annotations

import json
import re
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
        print(json.dumps(normalize_json_payload(data), indent=2, default=str))
    else:
        print(format_fn(data))


def render_json(data: Any) -> None:
    """Always render as JSON regardless of TTY."""
    print(json.dumps(normalize_json_payload(data), indent=2, default=str))


def estimate_tokens(data: Any) -> int:
    """Return a rough token estimate for a JSON-compatible payload."""
    try:
        text = json.dumps(data, default=str, ensure_ascii=False)
    except TypeError:
        text = str(data)
    return max(1, (len(text) + 3) // 4)


def _status_is_ok(status: Any) -> bool:
    return str(status or "ok").lower() not in {"error", "failed", "fail", "miss"}


def normalize_json_payload(data: Any, *, exit_code: int | None = None) -> Any:
    """Enrich machine-readable output with the stable builder JSON envelope.

    Existing command payload fields stay at the top level for compatibility.
    """
    if not isinstance(data, dict):
        payload = {"ok": True, "status": "ok", "exit_code": 0, "data": data}
    else:
        payload = dict(data)
        ok = bool(payload["ok"]) if "ok" in payload else _status_is_ok(payload.get("status"))
        payload.setdefault("ok", ok)
        payload.setdefault("status", "ok" if ok else "error")
        payload.setdefault("exit_code", 0 if ok else 1)

    if exit_code is not None:
        payload["exit_code"] = exit_code
    if payload.get("ok") is False and "error" not in payload:
        code = str(payload.get("code") or "error")
        hint = str(payload.get("hint") or payload.get("next") or payload.get("next_step") or "")
        payload.setdefault("code", code)
        payload["error"] = {
            "code": code,
            "message": sanitize_error_detail(payload.get("message", code)),
            "hint": extract_next_command(hint) or hint,
            "detail": sanitize_error_detail(payload.get("detail")),
        }
    if payload.get("next") and not payload.get("next_step"):
        payload["next_step"] = payload["next"]
    if payload.get("next_step") and not payload.get("next"):
        payload["next"] = payload["next_step"]
    if payload.get("hint") and not payload.get("next"):
        next_command = extract_next_command(str(payload.get("hint")))
        if next_command:
            payload["next"] = next_command
            payload.setdefault("next_step", next_command)
    payload.setdefault("schema_version", "1")
    payload.setdefault("truncated", False)
    payload.setdefault("token_estimate", estimate_tokens(payload))
    return payload


def sanitize_error_detail(value: Any) -> Any:
    """Redact raw internals that should not leak through JSON error envelopes."""
    if isinstance(value, dict):
        return {str(k): sanitize_error_detail(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_error_detail(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value

    text = str(value)
    if "Traceback (most recent call last)" in text:
        return "internal traceback redacted"
    if "<html" in text.lower() or "<!doctype html" in text.lower():
        return "html response redacted"
    text = re.sub(r"(?i)(api[_-]?key|token|secret|password)=\S+", r"\1=<redacted>", text)
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1<redacted>", text)
    return text


def _infer_exit_code(code: str) -> int:
    if code in {"invalid_usage", "invalid_input"}:
        return 2
    if code.startswith("connectivity") or code.startswith("invalid_health"):
        return 3
    return 1


def extract_next_command(text: str | None) -> str:
    """Extract the first concrete builder/workflow command from guidance text."""
    if not text:
        return ""
    patterns = [
        r"'((?:builder|workflow) [^']+)'",
        r"\b((?:builder|workflow) [A-Za-z0-9_./<>=:\" -]+--json)\b",
        r"\b((?:builder|workflow) [A-Za-z0-9_./<>=:\" -]+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return " ".join(match.group(1).split()).strip(" .,")
    return ""


def emit_error(
    message: str,
    *,
    code: str = "error",
    hint: str | None = None,
    detail: Any = None,
    exit_code: int | None = None,
    use_json: bool = False,
) -> None:
    """Render a stable error envelope for agents or plain text for humans."""
    if use_json or not is_tty():
        next_command = extract_next_command(hint)
        payload = {
            "ok": False,
            "status": "error",
            "exit_code": exit_code if exit_code is not None else _infer_exit_code(code),
            "code": code,
            "next": next_command,
            "error": {
                "code": code,
                "message": sanitize_error_detail(message),
                "hint": next_command or hint or "",
                "detail": sanitize_error_detail(detail),
            },
            "schema_version": "1",
        }
        print(json.dumps(normalize_json_payload(payload), indent=2, default=str))
        return

    lines = [f"Error: {message}"]
    if hint:
        lines.append(f"Hint: {hint}")
    print("\n".join(lines), file=sys.stderr)


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
