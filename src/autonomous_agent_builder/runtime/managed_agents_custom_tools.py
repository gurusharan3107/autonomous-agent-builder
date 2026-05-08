"""Host-side custom tool handlers for the Managed Agents lane.

When an MA agent emits ``agent.custom_tool_use``, the orchestrator runs the
matching handler host-side (NOT inside the cloud session container) and
replies with ``user.custom_tool_result``. This is MA Pattern 9 from
`shared/managed-agents-client-patterns.md` — keep non-MCP CLIs and
filesystem-bound state host-side rather than projecting it into the
session container.

Phase A ships exactly one custom tool: ``builder_memory_search``. It wraps
the existing ``builder memory`` CLI so MA-lane agents can read precedent
from the canonical ``.memory/`` filesystem without builder needing to
project it into a Memory Store. The filesystem-based memory contract is
preserved.
"""

from __future__ import annotations

import asyncio
import shlex
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

log = structlog.get_logger()

# Async handler signature: (input_json) -> result_text
CustomToolHandler = Callable[[dict[str, Any]], Awaitable[str]]


class CustomToolRegistry:
    """Lookup table for host-side custom tool handlers.

    The runtime adapter resolves a tool name from ``agent.custom_tool_use``
    events through this registry. Unregistered tool names produce an
    is_error=True result back to the agent.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, CustomToolHandler] = {}

    def register(self, name: str, handler: CustomToolHandler) -> None:
        self._handlers[name] = handler

    def get(self, name: str) -> CustomToolHandler | None:
        return self._handlers.get(name)

    def names(self) -> list[str]:
        return sorted(self._handlers.keys())


async def _builder_memory_search(input_json: dict[str, Any]) -> str:
    """Run ``builder memory search`` host-side and return JSON results.

    Inputs:
        query (str, required): the search query
        tags (str, optional): comma-separated tags
        limit (int, optional): max results (default 10)

    Returns the search output as a string. Empty results yield a polite
    "no matches" message rather than an empty string so the agent doesn't
    confuse silence with failure.
    """
    query = str(input_json.get("query") or "").strip()
    if not query:
        return "Error: builder_memory_search requires a non-empty `query` argument."

    tags = str(input_json.get("tags") or "").strip()
    limit = int(input_json.get("limit") or 10)
    limit = max(1, min(limit, 100))

    cmd: list[str] = ["builder", "memory", "search", query, "--limit", str(limit), "--json"]
    if tags:
        cmd.extend(["--tags", tags])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
    except FileNotFoundError:
        return "Error: `builder` CLI not found on PATH on the host. Memory search unavailable."
    except Exception as exc:  # pragma: no cover — defensive
        return f"Error running builder memory search: {exc}"

    stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        log.warning(
            "builder_memory_search_nonzero_exit",
            cmd=" ".join(shlex.quote(c) for c in cmd),
            returncode=proc.returncode,
            stderr=stderr[:500],
        )
        # Surface a useful summary to the agent rather than the full stderr
        return (
            f"builder memory search exited {proc.returncode}. "
            f"stderr: {stderr[:500] or '(empty)'}"
        )

    if not stdout:
        return f"No memory entries match query: {query!r}."
    return stdout


def default_custom_tool_registry() -> CustomToolRegistry:
    """Phase A registry with `builder_memory_search` registered.

    Future phases will register additional host-side tools as needed
    (e.g. `builder_knowledge_search`, `builder_metrics_show`, etc.).
    """
    registry = CustomToolRegistry()
    registry.register("builder_memory_search", _builder_memory_search)
    return registry
