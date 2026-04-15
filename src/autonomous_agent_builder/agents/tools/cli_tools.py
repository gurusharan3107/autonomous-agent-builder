"""CLI tool bridge — agent-callable wrappers around `builder` CLI commands.

These async functions shell out to `builder --json` and return structured results.
Agents invoke them as MCP tools (mcp__builder__<name>).
Same pattern as workspace_tools.py — subprocess with argv, never shell=True.
"""

from __future__ import annotations

import asyncio
import json


async def _run_builder(*args: str) -> dict:
    """Execute a builder CLI command and return parsed JSON result."""
    cmd = ["builder", *args, "--json"]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    output = stdout.decode()

    # Try to parse JSON, fall back to raw text
    try:
        parsed = json.loads(output)
        return {
            "content": [{"type": "text", "text": json.dumps(parsed, indent=2)}],
            "metadata": {"exit_code": proc.returncode},
        }
    except json.JSONDecodeError:
        return {
            "content": [{"type": "text", "text": output + stderr.decode()}],
            "metadata": {"exit_code": proc.returncode},
        }


# ── SDLC Operations ──


async def builder_board() -> dict:
    """Get the current task pipeline board status."""
    return await _run_builder("board", "show")


async def builder_task_show(task_id: str) -> dict:
    """Show task details including status, retry count, and blocked reason.

    Args:
        task_id: The task ID to look up.
    """
    return await _run_builder("task", "show", task_id, "--full")


async def builder_task_status(task_id: str) -> dict:
    """Quick status check for a task.

    Args:
        task_id: The task ID to check.
    """
    return await _run_builder("task", "status", task_id)


async def builder_task_dispatch(task_id: str) -> dict:
    """Dispatch a task through the SDLC pipeline.

    Args:
        task_id: The task ID to dispatch.
    """
    return await _run_builder("task", "dispatch", task_id, "--yes")


async def builder_metrics() -> dict:
    """Get project metrics — cost, tokens, runs, gate pass rate."""
    return await _run_builder("metrics", "show")


# ── Knowledge Base ──


async def builder_kb_add(
    task_id: str, doc_type: str, title: str, content: str
) -> dict:
    """Add a document to the knowledge base.

    Args:
        task_id: Task this document belongs to.
        doc_type: Document type (adr, api_contract, schema, runbook, context).
        title: Document title.
        content: Document content.
    """
    return await _run_builder(
        "kb", "add",
        "--task", task_id,
        "--type", doc_type,
        "--title", title,
        "--content", content,
    )


async def builder_kb_search(query: str, doc_type: str = "") -> dict:
    """Search knowledge base documents.

    Args:
        query: Search query string.
        doc_type: Optional filter by type (adr, api_contract, schema, runbook, context).
    """
    args = ["kb", "search", query]
    if doc_type:
        args.extend(["--type", doc_type])
    return await _run_builder(*args)


async def builder_kb_show(doc_id: str) -> dict:
    """Get a knowledge base document by ID.

    Args:
        doc_id: Document ID.
    """
    return await _run_builder("kb", "show", doc_id, "--full")


# ── Memory ──


async def builder_memory_search(query: str, entity: str = "") -> dict:
    """Search project memory for decisions, patterns, and corrections.

    Args:
        query: Search query string.
        entity: Optional filter by entity name.
    """
    args = ["memory", "search", query]
    if entity:
        args.extend(["--entity", entity])
    return await _run_builder(*args)


async def builder_memory_show(slug: str) -> dict:
    """Get a memory entry by slug.

    Args:
        slug: Memory entry slug.
    """
    return await _run_builder("memory", "show", slug)


# Registry of all CLI tools — used by ToolRegistry
CLI_TOOLS = {
    "builder_board": builder_board,
    "builder_task_show": builder_task_show,
    "builder_task_status": builder_task_status,
    "builder_task_dispatch": builder_task_dispatch,
    "builder_metrics": builder_metrics,
    "builder_kb_add": builder_kb_add,
    "builder_kb_search": builder_kb_search,
    "builder_kb_show": builder_kb_show,
    "builder_memory_search": builder_memory_search,
    "builder_memory_show": builder_memory_show,
}
