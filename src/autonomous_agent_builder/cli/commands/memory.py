"""Memory commands — list, search, show, add.

Memory is file-based (.memory/ directory), not DB-backed.
CLI reads/writes directly to the filesystem.
"""

from __future__ import annotations

import json as json_lib
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer

from autonomous_agent_builder.cli.client import EXIT_INVALID_USAGE, EXIT_NOT_FOUND, EXIT_SUCCESS
from autonomous_agent_builder.cli.output import render, table, truncate

app = typer.Typer(help="Project memory — decisions, patterns, and corrections.")


def _memory_root() -> Path:
    """Resolve memory directory path."""
    return Path(os.environ.get("AAB_MEMORY_ROOT", ".memory"))


def _load_routing() -> list[dict]:
    """Load routing.json index. Returns empty list if missing."""
    routing_path = _memory_root() / "routing.json"
    if not routing_path.exists():
        return []
    try:
        data = json_lib.loads(routing_path.read_text(encoding="utf-8"))
        return data.get("entries", []) if isinstance(data, dict) else data
    except (json_lib.JSONDecodeError, OSError):
        return []


def _save_routing(entries: list[dict]) -> None:
    """Save routing.json index."""
    routing_path = _memory_root() / "routing.json"
    routing_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"entries": entries, "updated": datetime.now(UTC).isoformat()}
    routing_path.write_text(
        json_lib.dumps(data, indent=2, default=str), encoding="utf-8"
    )


def _read_memory_file(entry: dict) -> str:
    """Read content from a memory file referenced in routing."""
    file_path = _memory_root() / entry.get("file", "")
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return ""


@app.command("list")
def list_memories(
    mem_type: str | None = typer.Option(
        None, "--type", help="Filter: decision, pattern, correction."
    ),
    phase: str | None = typer.Option(None, help="Filter by phase."),
    entity: str | None = typer.Option(None, help="Filter by entity."),
    limit: int = typer.Option(20, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List project memories from .memory/ directory."""
    entries = _load_routing()

    if mem_type:
        entries = [e for e in entries if e.get("type") == mem_type]
    if phase:
        entries = [e for e in entries if e.get("phase") == phase]
    if entity:
        entries = [e for e in entries if e.get("entity") == entity]
    if entries:
        # Sort by date descending
        entries.sort(key=lambda e: e.get("date", ""), reverse=True)
    entries = entries[:limit]

    def fmt(items: list) -> str:
        headers = ["SLUG", "TYPE", "TITLE", "PHASE", "ENTITY"]
        rows = [
            [
                e.get("slug", "")[:20],
                e.get("type", ""),
                e.get("title", "")[:35],
                e.get("phase", ""),
                e.get("entity", ""),
            ]
            for e in items
        ]
        return table(headers, rows)

    render(entries, fmt, use_json=json)
    sys.exit(EXIT_SUCCESS)


@app.command()
def show(
    slug: str = typer.Argument(help="Memory slug."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show a memory entry by slug."""
    entries = _load_routing()
    entry = next((e for e in entries if e.get("slug") == slug), None)

    if not entry:
        from autonomous_agent_builder.cli.output import error
        error(f"Error: memory '{slug}' not found")
        sys.exit(EXIT_NOT_FOUND)

    content = _read_memory_file(entry)
    data = {**entry, "content": content}

    def fmt(d: dict) -> str:
        lines = [
            f"slug: {d.get('slug', '')}",
            f"type: {d.get('type', '')}",
            f"title: {d.get('title', '')}",
            f"phase: {d.get('phase', '')}",
            f"entity: {d.get('entity', '')}",
            f"tags: {', '.join(d.get('tags', []))}",
            f"status: {d.get('status', 'active')}",
            f"date: {d.get('date', '')}",
            "",
            d.get("content", ""),
        ]
        return "\n".join(lines)

    render(data, fmt, use_json=json)
    sys.exit(EXIT_SUCCESS)


@app.command()
def search(
    query: str = typer.Argument(help="Search query."),
    entity: str | None = typer.Option(None, help="Filter by entity."),
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag."),
    limit: int = typer.Option(10, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Search memories by content, title, tags."""
    entries = _load_routing()
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    results = []

    for entry in entries:
        if entity and entry.get("entity") != entity:
            continue
        if tag and tag not in entry.get("tags", []):
            continue

        # Search title
        if pattern.search(entry.get("title", "")):
            results.append(entry)
            continue

        # Search tags
        if any(pattern.search(t) for t in entry.get("tags", [])):
            results.append(entry)
            continue

        # Search file content
        content = _read_memory_file(entry)
        if pattern.search(content):
            results.append(entry)

    results = results[:limit]

    def fmt(items: list) -> str:
        headers = ["SLUG", "TYPE", "TITLE", "ENTITY"]
        rows = [
            [
                e.get("slug", "")[:20],
                e.get("type", ""),
                e.get("title", "")[:40],
                e.get("entity", ""),
            ]
            for e in items
        ]
        return table(headers, rows)

    render(results, fmt, use_json=json)
    sys.exit(EXIT_SUCCESS)


@app.command()
def add(
    mem_type: str = typer.Option(..., "--type", help="Type: decision, pattern, correction."),
    phase: str = typer.Option(..., help="Phase (design, testing, implementation, ...)."),
    entity: str = typer.Option(..., help="Entity name."),
    tags: str = typer.Option(..., help="Comma-separated tags."),
    title: str = typer.Option(..., help="Memory title."),
    content: str | None = typer.Option(None, help="Content inline."),
    content_file: str | None = typer.Option(
        None, "--content-file", help="File to read content from (- for stdin)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be created."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Add a memory entry to the project .memory/ directory."""
    # Resolve content
    if content:
        body = content
    elif content_file:
        if content_file == "-":
            body = sys.stdin.read()
        else:
            p = Path(content_file)
            if not p.exists():
                from autonomous_agent_builder.cli.output import error
                error(f"Error: file not found — {content_file}")
                sys.exit(EXIT_INVALID_USAGE)
            body = p.read_text(encoding="utf-8")
    else:
        from autonomous_agent_builder.cli.output import error
        error("Error: provide --content or --content-file")
        sys.exit(EXIT_INVALID_USAGE)

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
    filename = f"{mem_type}_{slug}.md"

    entry = {
        "slug": slug,
        "file": filename,
        "title": title,
        "type": mem_type,
        "phase": phase,
        "entity": entity,
        "tags": tag_list,
        "status": "active",
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
    }

    if dry_run:
        render(
            {"dry_run": True, "would_create": entry, "content_preview": truncate(body, 200)},
            lambda d: f"Would create {mem_type} memory: {title}",
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    # Write memory file
    mem_root = _memory_root()
    mem_root.mkdir(parents=True, exist_ok=True)
    mem_file = mem_root / filename
    mem_file.write_text(body, encoding="utf-8")

    # Update routing index
    entries = _load_routing()
    # Replace if slug exists
    entries = [e for e in entries if e.get("slug") != slug]
    entries.append(entry)
    _save_routing(entries)

    def fmt(d: dict) -> str:
        return (
            f"created {mem_type} memory\n"
            f"slug: {d.get('slug', '')}\n"
            f"file: {d.get('file', '')}"
        )

    render(entry, fmt, use_json=json)
    sys.exit(EXIT_SUCCESS)
