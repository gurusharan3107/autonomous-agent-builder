"""Memory commands — list, search, show, add, and lifecycle management.

Memory is file-based (.memory/ directory), not DB-backed.
CLI reads/writes directly to the filesystem and keeps routing.json in sync.
"""

from __future__ import annotations

import json as json_lib
import os
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from autonomous_agent_builder.cli.client import EXIT_SUCCESS
from autonomous_agent_builder.cli.output import emit_error, error, render, table, truncate
from autonomous_agent_builder.cli.retrieval import (
    compact_results_payload,
    join_query_parts,
    not_found_hint,
    query_terms,
    resolve_collection_item,
)

app = typer.Typer(
    help=(
        "Project memory — decisions, patterns, and corrections.\n\n"
        "Start here:\n"
        "  builder memory list --json\n"
        "  builder memory search <query> --json\n"
        "  builder memory summary <query> --json\n"
    )
)

TYPE_DIRS = {
    "decision": "decisions",
    "pattern": "patterns",
    "correction": "corrections",
}
VALID_STATUSES = ("active", "superseded", "graduated", "invalidated", "pruned", "flagged")
LEGACY_PREFIXES = {
    "decision_": "decision",
    "pattern_": "pattern",
    "correction_": "correction",
}
MEMORY_CONTRACT_REQUIRED_KEYS = ("title", "type", "date", "phase", "entity", "status")


def _memory_root() -> Path:
    """Resolve memory directory path."""
    return Path(os.environ.get("AAB_MEMORY_ROOT", ".memory"))


def _routing_path() -> Path:
    return _memory_root() / "routing.json"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse a minimal YAML-like frontmatter block."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, content

    end = -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end < 0:
        return {}, content

    metadata: dict[str, Any] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, _, raw_value = line.partition(":")
        key = key.strip()
        value = raw_value.strip()
        if value.startswith("[") and value.endswith("]"):
            items = [item.strip().strip("'\"") for item in value[1:-1].split(",")]
            metadata[key] = [item for item in items if item]
        elif value.lower() in {"true", "false"}:
            metadata[key] = value.lower() == "true"
        else:
            metadata[key] = value.strip("'\"")

    return metadata, "\n".join(lines[end + 1 :]).strip()


def _format_frontmatter_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        items = ", ".join(str(item) for item in value if str(item).strip())
        return f"[{items}]"
    return str(value)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "memory-entry"


def _default_title(slug: str) -> str:
    return slug.replace("-", " ").strip().title()


def _entry_path(entry: dict[str, Any]) -> Path:
    return _memory_root() / str(entry.get("file", "")).strip()


def _infer_entry_from_file(path: Path, memory_root: Path) -> dict[str, Any]:
    """Build a routing entry from a memory markdown file."""
    relative = path.relative_to(memory_root)
    content = _read_text(path)
    metadata, _ = _parse_frontmatter(content)

    mem_type = metadata.get("type")
    if not mem_type:
        if len(relative.parts) > 1:
            mem_type = relative.parts[0].rstrip("s")
        else:
            stem = path.stem
            mem_type = "pattern"
            for prefix, candidate in LEGACY_PREFIXES.items():
                if stem.startswith(prefix):
                    mem_type = candidate
                    break

    stem = path.stem
    for prefix in LEGACY_PREFIXES:
        if stem.startswith(prefix):
            stem = stem[len(prefix) :]
            break

    tags = metadata.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    related = metadata.get("related", [])
    if not isinstance(related, list):
        related = []

    return {
        "slug": metadata.get("slug", stem),
        "file": str(relative),
        "title": metadata.get("title", _default_title(stem)),
        "type": mem_type,
        "phase": metadata.get("phase", ""),
        "entity": metadata.get("entity", ""),
        "tags": tags,
        "status": metadata.get("status", "active"),
        "related": related,
        "date": metadata.get("date", ""),
        "preserve_as_precedent": bool(metadata.get("preserve_as_precedent", False)),
        "flag_reason": str(metadata.get("flag_reason", "")),
        "graduated_into": str(metadata.get("graduated_into", "")),
    }


def _scan_filesystem(memory_root: Path | None = None) -> list[dict[str, Any]]:
    """Scan the filesystem and rebuild memory entries from markdown files."""
    root = memory_root or _memory_root()
    if not root.exists():
        return []

    paths: list[Path] = []
    for dirname in TYPE_DIRS.values():
        path = root / dirname
        if path.exists():
            paths.extend(sorted(path.glob("*.md")))
    for path in sorted(root.glob("*.md")):
        if path.name == "INDEX.md":
            continue
        paths.append(path)

    entries = [_infer_entry_from_file(path, root) for path in paths]
    entries.sort(key=lambda entry: (entry.get("date", ""), entry.get("slug", "")), reverse=True)
    return entries


def _load_routing() -> list[dict[str, Any]]:
    """Load routing.json index. Falls back to the filesystem when needed."""
    routing_path = _routing_path()
    if routing_path.exists():
        try:
            data = json_lib.loads(routing_path.read_text(encoding="utf-8"))
        except (json_lib.JSONDecodeError, OSError):
            data = {}
        if isinstance(data, dict):
            entries = data.get("entries")
            if isinstance(entries, list):
                return entries
            memories = data.get("memories")
            if isinstance(memories, list):
                return memories
        elif isinstance(data, list):
            return data

    entries = _scan_filesystem()
    if entries:
        _save_routing(entries)
    return entries


def _save_routing(entries: list[dict[str, Any]]) -> None:
    """Save routing.json index with summary routing maps."""
    routing_path = _routing_path()
    routing_path.parent.mkdir(parents=True, exist_ok=True)

    routing: dict[str, list[str]] = {}
    for entry in entries:
        slug = str(entry.get("slug", "")).strip()
        if not slug:
            continue
        for key, value in (
            ("type", entry.get("type", "")),
            ("phase", entry.get("phase", "")),
            ("entity", entry.get("entity", "")),
            ("status", entry.get("status", "active")),
        ):
            if value:
                routing.setdefault(f"{key}:{value}", []).append(slug)
        for tag in entry.get("tags", []):
            routing.setdefault(f"tag:{tag}", []).append(slug)

    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "entries": entries,
        "memories": entries,
        "routing": routing,
    }
    routing_path.write_text(json_lib.dumps(payload, indent=2, default=str), encoding="utf-8")


def _build_memory_markdown(entry: dict[str, Any], body: str) -> str:
    """Render a memory markdown file with frontmatter."""
    frontmatter = {
        "title": entry["title"],
        "type": entry["type"],
        "date": entry["date"],
        "phase": entry["phase"],
        "entity": entry["entity"],
        "tags": entry.get("tags", []),
        "status": entry.get("status", "active"),
        "related": entry.get("related", []),
    }
    if entry.get("preserve_as_precedent"):
        frontmatter["preserve_as_precedent"] = True
    if entry.get("flag_reason"):
        frontmatter["flag_reason"] = entry["flag_reason"]
    if entry.get("graduated_into"):
        frontmatter["graduated_into"] = entry["graduated_into"]

    lines = ["---"]
    for key, value in frontmatter.items():
        if value in ("", [], None, False):
            continue
        lines.append(f"{key}: {_format_frontmatter_value(value)}")
    lines.append("---")
    lines.append("")
    lines.append(body.strip() or "## Summary\n\nAdd memory details here.")
    return "\n".join(lines).rstrip() + "\n"


def _body_for_entry(entry: dict[str, Any]) -> str:
    """Return the markdown body for an entry, excluding frontmatter."""
    content = _read_text(_entry_path(entry))
    _, body = _parse_frontmatter(content)
    return body


def _write_entry_file(entry: dict[str, Any], body: str) -> None:
    path = _entry_path(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_build_memory_markdown(entry, body), encoding="utf-8")


def _memory_markdown_files(root: Path | None = None) -> list[Path]:
    memory_root = root or _memory_root()
    files: list[Path] = []
    for dirname in TYPE_DIRS.values():
        directory = memory_root / dirname
        if directory.exists():
            files.extend(sorted(directory.glob("*.md")))
    for path in sorted(memory_root.glob("*.md")):
        if path.name != "INDEX.md":
            files.append(path)
    return files


def _memory_contract_payload() -> dict[str, Any]:
    sample_entry = {
        "title": "Capture repo-scoped CLI precedent",
        "type": "decision",
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "phase": "implementation",
        "entity": "builder-cli",
        "tags": ["cli", "precedent"],
        "status": "active",
        "related": ["existing-related-memory"],
    }
    return {
        "doc_type": "memory",
        "memory_root": str(_memory_root()),
        "required_frontmatter": {key: "string" for key in MEMORY_CONTRACT_REQUIRED_KEYS},
        "optional_frontmatter": {
            "tags": "array[string]",
            "related": "array[string]",
            "preserve_as_precedent": "boolean",
            "flag_reason": "string",
            "graduated_into": "string",
        },
        "allowed_types": sorted(TYPE_DIRS.keys()),
        "allowed_statuses": list(VALID_STATUSES),
        "rules": [
            "Memory entries live in .memory/ and are the owner surface for project-specific precedent.",
            "Frontmatter must identify the type, date, phase, entity, and lifecycle status.",
            "Invalidate a memory as soon as it becomes irrelevant so active memory stays reusable.",
            "The markdown body should capture the reusable decision, pattern, or correction without duplicating global doctrine.",
            "Use builder memory reindex after manual filesystem edits so routing.json stays in sync.",
        ],
        "sample_markdown": _build_memory_markdown(
            sample_entry,
            (
                "## Summary\n\n"
                "Use repo-scoped CLI commands first, then record the narrow correction that future runs should reuse.\n\n"
                "## Why it mattered\n\n"
                "This precedent keeps future agents on the owner surface without rediscovering the same drift."
            ),
        ),
    }


def _lint_memory_entries(root: Path | None = None) -> dict[str, Any]:
    memory_root = root or _memory_root()
    issues: list[dict[str, str]] = []
    related_targets: set[str] = set()
    seen_slugs: set[str] = set()

    for path in _memory_markdown_files(memory_root):
        relative = path.relative_to(memory_root).as_posix()
        content = _read_text(path)
        metadata, body = _parse_frontmatter(content)
        inferred_entry = _infer_entry_from_file(path, memory_root)
        slug = str(inferred_entry.get("slug", path.stem))
        seen_slugs.add(slug)

        legacy_without_frontmatter = not metadata
        if legacy_without_frontmatter:
            if not body.strip():
                issues.append({"path": relative, "severity": "error", "message": "missing frontmatter"})
                continue
            issues.append(
                {
                    "path": relative,
                    "severity": "warning",
                    "message": "legacy entry without frontmatter; inferred metadata from path and slug",
                }
            )

        required_keys = ("title", "type", "status") if legacy_without_frontmatter else MEMORY_CONTRACT_REQUIRED_KEYS
        for key in required_keys:
            value = inferred_entry.get(key, metadata.get(key, ""))
            if not str(value).strip():
                issues.append(
                    {"path": relative, "severity": "error", "message": f"missing required frontmatter '{key}'"}
                )

        entry_type = str(inferred_entry.get("type", metadata.get("type", ""))).strip()
        if entry_type and entry_type not in TYPE_DIRS:
            issues.append(
                {"path": relative, "severity": "error", "message": f"invalid memory type '{entry_type}'"}
            )

        status = str(inferred_entry.get("status", metadata.get("status", ""))).strip()
        if status and status not in VALID_STATUSES:
            issues.append(
                {"path": relative, "severity": "error", "message": f"invalid lifecycle status '{status}'"}
            )

        if not body.strip():
            issues.append({"path": relative, "severity": "error", "message": "missing markdown body"})

        related = inferred_entry.get("related", metadata.get("related", []))
        if isinstance(related, list):
            for item in related:
                if str(item).strip():
                    related_targets.add(str(item).strip())

    missing_related = sorted(target for target in related_targets if target not in seen_slugs)
    for slug in missing_related:
        issues.append(
            {
                "path": "routing.json",
                "severity": "error",
                "message": f"related memory '{slug}' does not exist",
            }
        )

    error_count = sum(1 for issue in issues if issue["severity"] == "error")
    warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
    return {
        "status": "ok" if error_count == 0 else "error",
        "passed": error_count == 0,
        "memory_root": str(memory_root),
        "files_checked": len(_memory_markdown_files(memory_root)),
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": issues,
    }


def _resolve_entry(slug: str, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    exact = next((entry for entry in entries if entry.get("slug") == slug), None)
    if exact:
        return exact
    matches = [entry for entry in entries if str(entry.get("slug", "")).startswith(slug)]
    return matches[0] if len(matches) == 1 else None


def _resolve_memory_query(query: str, entries: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str, list[str]]:
    exact = _resolve_entry(query, entries)
    if exact:
        return exact, "slug", []
    searchable_entries = []
    for entry in entries:
        searchable_entries.append(
            {
                **entry,
                "tags_text": " ".join(str(tag) for tag in entry.get("tags", [])),
                "body": _body_for_entry(entry),
            }
        )
    resolution = resolve_collection_item(
        query,
        searchable_entries,
        id_keys=("slug",),
        text_keys=("title", "entity", "phase", "status", "tags_text", "body"),
        suggestion_id_key="slug",
        suggestion_label_key="title",
    )
    if resolution and resolution.item:
        return resolution.item, resolution.matched_on, resolution.suggestions
    terms = query_terms(query)
    if terms:
        lowered_query = query.lower().strip()
        ranked: list[tuple[tuple[int, int, int, int], dict[str, Any]]] = []
        for entry in searchable_entries:
            title = str(entry.get("title", "") or "").lower()
            combined = " ".join(
                str(entry.get(key, "") or "")
                for key in ("title", "entity", "phase", "status", "tags_text", "body")
            ).lower()
            matched_terms = sum(1 for term in terms if term in combined)
            if not matched_terms:
                continue
            phrase_in_title = int(bool(lowered_query and lowered_query in title))
            phrase_in_combined = int(bool(lowered_query and lowered_query in combined))
            frequency = sum(combined.count(term) for term in terms)
            ranked.append(((phrase_in_title, phrase_in_combined, matched_terms, frequency), entry))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if ranked:
            return ranked[0][1], "search", resolution.suggestions if resolution else []
    return None, "", resolution.suggestions if resolution else []


def _memory_compact(entry: dict[str, Any], *, preview: str = "") -> dict[str, Any]:
    return {
        "id": str(entry.get("slug", "")),
        "title": str(entry.get("title", "")),
        "doc_type": "memory",
        "status": str(entry.get("status", "active")),
        "preview": preview,
    }


def _memory_lookup_error(query: str, suggestions: list[str], *, use_json: bool) -> None:
    emit_error(
        f"Memory not found: {query}",
        code="not_found",
        hint=not_found_hint(
            query,
            search_command=f'builder memory search "{query}" --json',
            suggestions=suggestions,
        ),
        detail={"query": query, "suggestions": suggestions},
        use_json=use_json,
    )
    sys.exit(1)


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
        entries = [entry for entry in entries if entry.get("type") == mem_type]
    if phase:
        entries = [entry for entry in entries if entry.get("phase") == phase]
    if entity:
        entries = [entry for entry in entries if entry.get("entity") == entity]
    entries.sort(key=lambda entry: (entry.get("date", ""), entry.get("slug", "")), reverse=True)
    entries = entries[:limit]

    def fmt(items: list[dict[str, Any]]) -> str:
        headers = ["SLUG", "TYPE", "TITLE", "PHASE", "ENTITY", "STATUS"]
        rows = [
            [
                str(entry.get("slug", ""))[:24],
                str(entry.get("type", "")),
                str(entry.get("title", ""))[:40],
                str(entry.get("phase", "")),
                str(entry.get("entity", ""))[:18],
                str(entry.get("status", "active")),
            ]
            for entry in items
        ]
        return table(headers, rows)

    compact = [
        _memory_compact(entry, preview=truncate(_body_for_entry(entry).replace("\n", " "), 120))
        for entry in entries
    ]
    render(
        compact_results_payload("list", compact, next_step="builder memory summary <query> --json")
        if json
        else entries,
        fmt,
        use_json=json,
    )
    sys.exit(EXIT_SUCCESS)


@app.command()
def summary(
    query_parts: list[str] = typer.Argument(help="Memory slug or natural-language query."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show a bounded memory overview before loading full content."""
    query = join_query_parts(query_parts)
    entries = _load_routing()
    entry, matched_on, suggestions = _resolve_memory_query(query, entries)
    if not entry:
        _memory_lookup_error(query, suggestions, use_json=json)

    payload = {
        "id": entry.get("slug", ""),
        "title": entry.get("title", ""),
        "doc_type": "memory",
        "matched_on": matched_on,
        "status": entry.get("status", "active"),
        "summary": "\n".join(
            [
                f"type: {entry.get('type', '')}",
                f"phase: {entry.get('phase', '')}",
                f"entity: {entry.get('entity', '')}",
                f"tags: {', '.join(entry.get('tags', []))}",
            ]
        ),
        "next_step": f"builder memory show {entry.get('slug', '')} --json",
    }

    def fmt(data: dict[str, Any]) -> str:
        return (
            f"{data['title']}\n"
            f"id: {data['id']}\n"
            f"matched_on: {data['matched_on']}\n"
            f"status: {data['status']}\n\n"
            f"{data['summary']}\n\n"
            f"Next: {data['next_step']}"
        )

    render(payload, fmt, use_json=json)
    sys.exit(EXIT_SUCCESS)


@app.command()
def contract(
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show the canonical memory markdown contract and sample entry."""
    payload = _memory_contract_payload()

    def fmt(data: dict[str, Any]) -> str:
        lines = [
            "Memory contract",
            f"memory_root: {data['memory_root']}",
            f"allowed_types: {', '.join(data['allowed_types'])}",
            f"allowed_statuses: {', '.join(data['allowed_statuses'])}",
            "",
            "Rules:",
            *[f"- {rule}" for rule in data["rules"]],
        ]
        return "\n".join(lines)

    render(payload, fmt, use_json=json)
    sys.exit(EXIT_SUCCESS)


@app.command()
def show(
    slug_parts: list[str] = typer.Argument(help="Memory slug or natural-language query."),
    full: bool = typer.Option(False, "--full", help="Show full content."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show a memory entry by slug."""
    slug = join_query_parts(slug_parts)
    entries = _load_routing()
    entry, matched_on, suggestions = _resolve_memory_query(slug, entries)
    if not entry:
        _memory_lookup_error(slug, suggestions, use_json=json)

    content = _read_text(_entry_path(entry))
    if not full:
        content = truncate(content)

    payload = {
        **entry,
        "content": content,
        "matched_on": matched_on,
        "next_step": f"builder memory summary {entry.get('slug', '')} --json",
    }

    def fmt(data: dict[str, Any]) -> str:
        lines = [
            f"slug: {data.get('slug', '')}",
            f"type: {data.get('type', '')}",
            f"title: {data.get('title', '')}",
            f"phase: {data.get('phase', '')}",
            f"entity: {data.get('entity', '')}",
            f"status: {data.get('status', 'active')}",
            f"tags: {', '.join(data.get('tags', []))}",
            f"matched_on: {data.get('matched_on', '')}",
        ]
        if data.get("related"):
            lines.append(f"related: {', '.join(data['related'])}")
        if data.get("flag_reason"):
            lines.append(f"flag_reason: {data['flag_reason']}")
        lines.extend(["", data.get("content", ""), "", f"Next: {data.get('next_step', '')}"])
        return "\n".join(lines)

    render(payload, fmt, use_json=json)
    sys.exit(EXIT_SUCCESS)


@app.command()
def search(
    query_parts: list[str] = typer.Argument(help="Search query."),
    entity: str | None = typer.Option(None, help="Filter by entity."),
    tag: str | None = typer.Option(None, help="Filter by tag."),
    limit: int = typer.Option(10, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Search memories by content, title, tags."""
    query = join_query_parts(query_parts)
    entries = _load_routing()
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    results: list[dict[str, Any]] = []

    for entry in entries:
        if entity and entry.get("entity") != entity:
            continue
        if tag and tag not in entry.get("tags", []):
            continue
        body = _body_for_entry(entry)
        haystacks = [entry.get("title", ""), " ".join(entry.get("tags", [])), body]
        if any(pattern.search(haystack) for haystack in haystacks):
            results.append({**entry, "match_preview": truncate(body.replace("\n", " "), 160)})

    results = results[:limit]

    def fmt(items: list[dict[str, Any]]) -> str:
        headers = ["SLUG", "TYPE", "TITLE", "ENTITY"]
        rows = [
            [
                str(entry.get("slug", ""))[:24],
                str(entry.get("type", "")),
                str(entry.get("title", ""))[:40],
                str(entry.get("entity", ""))[:20],
            ]
            for entry in items
        ]
        return table(headers, rows)

    compact = [_memory_compact(entry, preview=str(entry.get("match_preview", ""))) for entry in results]
    render(
        compact_results_payload(query, compact, next_step="builder memory summary <query> --json")
        if json
        else results,
        fmt,
        use_json=json,
    )
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
    if mem_type not in TYPE_DIRS:
        error("Error: --type must be one of decision, pattern, correction")
        sys.exit(2)

    if content:
        body = content
    elif content_file:
        if content_file == "-":
            body = sys.stdin.read()
        else:
            path = Path(content_file)
            if not path.exists():
                error(f"Error: file not found — {content_file}")
                sys.exit(2)
            body = path.read_text(encoding="utf-8")
    else:
        error("Error: provide --content or --content-file")
        sys.exit(2)

    tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
    slug = _slugify(title)
    entry = {
        "slug": slug,
        "file": f"{TYPE_DIRS[mem_type]}/{slug}.md",
        "title": title,
        "type": mem_type,
        "phase": phase,
        "entity": entity,
        "tags": tag_list,
        "status": "active",
        "related": [],
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "preserve_as_precedent": False,
        "flag_reason": "",
        "graduated_into": "",
    }

    if dry_run:
        render(
            {"dry_run": True, "would_create": entry, "content_preview": truncate(body, 200)},
            lambda _: f"Would create {mem_type} memory: {title}",
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    entries = [item for item in _load_routing() if item.get("slug") != slug]
    entries.append(entry)
    _write_entry_file(entry, body)
    _save_routing(entries)

    def fmt(data: dict[str, Any]) -> str:
        return (
            f"created {mem_type} memory\n"
            f"slug: {data.get('slug', '')}\n"
            f"title: {data.get('title', '')}\n"
            f"path: {data.get('file', '')}"
        )

    render(entry, fmt, use_json=json)
    sys.exit(EXIT_SUCCESS)


@app.command()
def init(
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Initialize the .memory/ directory and typed subdirectories."""
    root = _memory_root()
    root.mkdir(parents=True, exist_ok=True)
    for dirname in TYPE_DIRS.values():
        (root / dirname).mkdir(parents=True, exist_ok=True)
    _save_routing(_scan_filesystem(root))

    payload = {
        "status": "ok",
        "memory_root": str(root),
        "directories": [str(root / dirname) for dirname in TYPE_DIRS.values()],
    }
    render(payload, lambda _: f"initialized memory at {root}", use_json=json)
    sys.exit(EXIT_SUCCESS)


@app.command()
def reindex(
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Rebuild routing.json from the current .memory/ filesystem."""
    entries = _scan_filesystem()
    _save_routing(entries)
    payload = {"status": "ok", "total": len(entries), "memory_root": str(_memory_root())}
    render(payload, lambda _: f"reindexed {len(entries)} memories", use_json=json)
    sys.exit(EXIT_SUCCESS)


@app.command()
def lint(
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Lint memory markdown files and routing integrity."""
    payload = _lint_memory_entries()

    def fmt(data: dict[str, Any]) -> str:
        if data["passed"]:
            return f"memory lint passed ({data['files_checked']} files checked)"
        lines = [f"memory lint failed ({data['error_count']} errors)"]
        for issue in data["issues"][:10]:
            lines.append(f"- {issue['path']}: {issue['message']}")
        return "\n".join(lines)

    render(payload, fmt, use_json=json)
    sys.exit(EXIT_SUCCESS if payload["passed"] else 1)


@app.command()
def stats(
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show memory counts by type and status."""
    entries = _load_routing()
    type_counts = Counter(str(entry.get("type", "")) for entry in entries)
    status_counts = Counter(str(entry.get("status", "active")) for entry in entries)
    payload = {
        "status": "ok",
        "total": len(entries),
        "active": status_counts.get("active", 0),
        "types": dict(type_counts),
        "statuses": dict(status_counts),
    }

    def fmt(data: dict[str, Any]) -> str:
        lines = [
            f"total: {data['total']}",
            f"active: {data['active']}",
        ]
        if data["types"]:
            lines.append("types: " + ", ".join(f"{k}={v}" for k, v in sorted(data["types"].items())))
        if data["statuses"]:
            lines.append("statuses: " + ", ".join(f"{k}={v}" for k, v in sorted(data["statuses"].items())))
        return "\n".join(lines)

    render(payload, fmt, use_json=json)
    sys.exit(EXIT_SUCCESS)


def _mutate_entry(slug: str, mutator, *, json: bool) -> None:
    entries = _load_routing()
    entry = _resolve_entry(slug, entries)
    if not entry:
        error(f"Error: memory '{slug}' not found")
        sys.exit(1)

    body = _body_for_entry(entry)
    changed = mutator(entry)
    if changed:
        _write_entry_file(entry, body)
        _save_routing(entries)

    render(
        {"status": "ok" if changed else "unchanged", "memory": entry, "changed": changed},
        lambda data: f"{data['status']}: {entry['slug']}",
        use_json=json,
    )
    sys.exit(EXIT_SUCCESS)


@app.command()
def relate(
    slug: str = typer.Argument(help="Source memory slug."),
    to: str = typer.Option(..., "--to", help="Target memory slug."),
    one_way: bool = typer.Option(False, "--one-way", help="Do not create the reverse link."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Add a related-memory link between two memories."""
    entries = _load_routing()
    source = _resolve_entry(slug, entries)
    target = _resolve_entry(to, entries)
    if not source or not target:
        error("Error: source or target memory not found")
        sys.exit(1)
    if source["slug"] == target["slug"]:
        error("Error: a memory cannot relate to itself")
        sys.exit(2)

    changed = False
    source.setdefault("related", [])
    target.setdefault("related", [])
    if target["slug"] not in source["related"]:
        source["related"].append(target["slug"])
        changed = True
    if not one_way and source["slug"] not in target["related"]:
        target["related"].append(source["slug"])
        changed = True

    if changed:
        _write_entry_file(source, _body_for_entry(source))
        _write_entry_file(target, _body_for_entry(target))
        _save_routing(entries)

    payload = {
        "status": "ok" if changed else "unchanged",
        "from": source["slug"],
        "to": target["slug"],
        "one_way": one_way,
    }
    render(payload, lambda _: f"{payload['status']}: {source['slug']} -> {target['slug']}", use_json=json)
    sys.exit(EXIT_SUCCESS)


@app.command()
def unrelate(
    slug: str = typer.Argument(help="Source memory slug."),
    to: str = typer.Option(..., "--to", help="Target memory slug."),
    one_way: bool = typer.Option(False, "--one-way", help="Only remove the forward link."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Remove a related-memory link between two memories."""
    entries = _load_routing()
    source = _resolve_entry(slug, entries)
    target = _resolve_entry(to, entries)
    if not source or not target:
        error("Error: source or target memory not found")
        sys.exit(1)

    changed = False
    source_related = source.setdefault("related", [])
    target_related = target.setdefault("related", [])
    if target["slug"] in source_related:
        source["related"] = [item for item in source_related if item != target["slug"]]
        changed = True
    if not one_way and source["slug"] in target_related:
        target["related"] = [item for item in target_related if item != source["slug"]]
        changed = True

    if changed:
        _write_entry_file(source, _body_for_entry(source))
        _write_entry_file(target, _body_for_entry(target))
        _save_routing(entries)

    payload = {
        "status": "ok" if changed else "unchanged",
        "from": source["slug"],
        "to": target["slug"],
        "one_way": one_way,
    }
    render(payload, lambda _: f"{payload['status']}: {source['slug']} -/-> {target['slug']}", use_json=json)
    sys.exit(EXIT_SUCCESS)


@app.command()
def flag(
    slug: str = typer.Argument(help="Memory slug."),
    reason: str = typer.Option(..., "--reason", help="Why this memory needs review."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Flag a memory for review."""

    def mutate(entry: dict[str, Any]) -> bool:
        changed = entry.get("status") != "flagged" or entry.get("flag_reason") != reason
        entry["status"] = "flagged"
        entry["flag_reason"] = reason
        return changed

    _mutate_entry(slug, mutate, json=json)


@app.command()
def graduate(
    slug: str = typer.Argument(help="Memory slug."),
    into: str = typer.Option("", "--into", help="Destination surface the memory graduated into."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Mark a memory as graduated into a more durable surface."""

    def mutate(entry: dict[str, Any]) -> bool:
        changed = (
            entry.get("status") != "graduated"
            or not entry.get("preserve_as_precedent")
            or entry.get("graduated_into", "") != into
        )
        entry["status"] = "graduated"
        entry["preserve_as_precedent"] = True
        entry["graduated_into"] = into
        entry["flag_reason"] = ""
        return changed

    _mutate_entry(slug, mutate, json=json)


@app.command()
def invalidate(
    slug: str = typer.Argument(help="Memory slug."),
    reason: str = typer.Option(..., "--reason", help="Why this memory is no longer relevant."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Mark a memory invalid the moment it is no longer reusable."""

    def mutate(entry: dict[str, Any]) -> bool:
        changed = entry.get("status") != "invalidated" or entry.get("flag_reason") != reason
        entry["status"] = "invalidated"
        entry["flag_reason"] = reason
        entry["preserve_as_precedent"] = False
        return changed

    _mutate_entry(slug, mutate, json=json)
