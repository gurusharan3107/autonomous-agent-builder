"""Typed backlog item commands."""

from __future__ import annotations

import sys

import typer

from autonomous_agent_builder.backlog_items import (
    FEATURE_STATUSES,
    ITEM_TYPES,
    SEVERITIES,
    SOURCES,
    parse_tags,
    require_primary_tag,
)
from autonomous_agent_builder.cli.client import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
    AabApiError,
    get_client,
    handle_api_error,
)
from autonomous_agent_builder.cli.output import emit_error, format_status, render, table

app = typer.Typer(
    help=(
        "Typed backlog items: feature, improvement, optimization, incident.\n\n"
        "Start here:\n"
        "  builder backlog item create --project <id> --type incident --title ... --severity high --evidence ... --json\n"
        "  builder backlog item list --project <id> --type improvement --json\n"
    )
)


def _payload_type(item: dict) -> str:
    return str(item.get("item_type") or item.get("type") or "feature")


def _parse_primary_tag(tags: str, *, use_json: bool) -> list[str]:
    try:
        return require_primary_tag(parse_tags(tags))
    except ValueError as exc:
        emit_error(
            str(exc),
            code="invalid_backlog_item_tags",
            hint="Use at most one primary tag, for example --tags dispatch.",
            exit_code=EXIT_FAILURE,
            use_json=use_json,
        )
        sys.exit(EXIT_FAILURE)


@app.command("create")
def create_item(
    project: str = typer.Option(..., "--project", help="Project ID."),
    item_type: str = typer.Option(
        "feature", "--type", help="feature, improvement, optimization, incident."
    ),
    title: str = typer.Option(..., help="Backlog item title."),
    description: str = typer.Option("", help="Backlog item description."),
    tags: str = typer.Option("", help="Single primary tag."),
    priority: int = typer.Option(0, help="Priority (0=highest)."),
    severity: str | None = typer.Option(
        None, help="Incident severity: low, medium, high, critical."
    ),
    source: str = typer.Option("manual", help="manual, validation, agent, system."),
    evidence: str = typer.Option(
        "", help="Required for incidents; reproduction or observed evidence."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be created."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Create a typed backlog item."""
    normalized_type = item_type.strip().lower()
    normalized_source = source.strip().lower()
    normalized_severity = severity.strip().lower() if severity else None
    if normalized_type not in ITEM_TYPES:
        emit_error(
            f"Unsupported backlog item type: {item_type}",
            code="invalid_backlog_item_type",
            hint="Use --type feature|improvement|optimization|incident.",
            exit_code=EXIT_FAILURE,
            use_json=json,
        )
        sys.exit(EXIT_FAILURE)
    if normalized_source not in SOURCES:
        emit_error(
            f"Unsupported backlog item source: {source}",
            code="invalid_backlog_item_source",
            hint="Use --source manual|validation|agent|system.",
            exit_code=EXIT_FAILURE,
            use_json=json,
        )
        sys.exit(EXIT_FAILURE)
    if normalized_type == "incident" and (not normalized_severity or not evidence.strip()):
        emit_error(
            "Incidents require --severity and --evidence.",
            code="incident_evidence_required",
            hint="Run builder backlog item create --type incident --severity high --evidence '<repro/evidence>'.",
            exit_code=EXIT_FAILURE,
            use_json=json,
        )
        sys.exit(EXIT_FAILURE)
    if normalized_severity and normalized_severity not in SEVERITIES:
        emit_error(
            f"Unsupported incident severity: {severity}",
            code="invalid_incident_severity",
            hint="Use --severity low|medium|high|critical.",
            exit_code=EXIT_FAILURE,
            use_json=json,
        )
        sys.exit(EXIT_FAILURE)

    payload = {
        "type": normalized_type,
        "title": title,
        "description": description,
        "priority": priority,
        "tags": _parse_primary_tag(tags, use_json=json),
        "severity": normalized_severity,
        "source": normalized_source,
        "evidence": evidence,
    }
    if dry_run:
        render(
            {"dry_run": True, "project_id": project, "would_create": payload},
            lambda data: str(data),
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    client = get_client(use_json=json)
    try:
        data = client.post(f"/projects/{project}/backlog/items", payload)
    except AabApiError as exc:
        handle_api_error(exc, use_json=json)
    else:

        def fmt(item: dict) -> str:
            return (
                f"created backlog item {str(item.get('id', ''))[:12]}\n"
                f"type: {_payload_type(item)}\n"
                f"title: {item.get('title', '')}\n"
                f"status: {format_status(item.get('status', ''))}"
            )

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command("update")
def update_item(
    item_id: str = typer.Argument(help="Backlog item ID."),
    title: str | None = typer.Option(None, help="New title."),
    description: str | None = typer.Option(None, help="New description."),
    status: str | None = typer.Option(
        None, help="Backlog item status, for example backlog, queued, or done."
    ),
    item_type: str | None = typer.Option(
        None, "--type", help="feature, improvement, optimization, incident."
    ),
    tags: str | None = typer.Option(None, help="Single primary tag. Use an empty string to clear."),
    priority: int | None = typer.Option(None, help="Priority (0=highest)."),
    severity: str | None = typer.Option(
        None, help="Incident severity: low, medium, high, critical. Use an empty string to clear."
    ),
    source: str | None = typer.Option(None, help="manual, validation, agent, system."),
    evidence: str | None = typer.Option(
        None, help="Observed evidence. Use an empty string to clear."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Update a typed backlog item."""
    payload: dict[str, object] = {}
    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description
    if status is not None:
        normalized_status = status.strip().lower()
        if normalized_status not in FEATURE_STATUSES:
            emit_error(
                f"Unsupported backlog item status: {status}",
                code="invalid_backlog_item_status",
                hint="Use --status backlog|sprint_backlog|queued|planning|in_progress|review|done|blocked.",
                exit_code=EXIT_FAILURE,
                use_json=json,
            )
            sys.exit(EXIT_FAILURE)
        payload["status"] = normalized_status
    if item_type is not None:
        normalized_type = item_type.strip().lower()
        if normalized_type not in ITEM_TYPES:
            emit_error(
                f"Unsupported backlog item type: {item_type}",
                code="invalid_backlog_item_type",
                hint="Use --type feature|improvement|optimization|incident.",
                exit_code=EXIT_FAILURE,
                use_json=json,
            )
            sys.exit(EXIT_FAILURE)
        payload["type"] = normalized_type
    if tags is not None:
        payload["tags"] = _parse_primary_tag(tags, use_json=json)
    if priority is not None:
        payload["priority"] = priority
    if severity is not None:
        normalized_severity = severity.strip().lower()
        if normalized_severity:
            if normalized_severity not in SEVERITIES:
                emit_error(
                    f"Unsupported incident severity: {severity}",
                    code="invalid_incident_severity",
                    hint="Use --severity low|medium|high|critical.",
                    exit_code=EXIT_FAILURE,
                    use_json=json,
                )
                sys.exit(EXIT_FAILURE)
            payload["severity"] = normalized_severity
        else:
            payload["severity"] = None
    if source is not None:
        normalized_source = source.strip().lower()
        if normalized_source not in SOURCES:
            emit_error(
                f"Unsupported backlog item source: {source}",
                code="invalid_backlog_item_source",
                hint="Use --source manual|validation|agent|system.",
                exit_code=EXIT_FAILURE,
                use_json=json,
            )
            sys.exit(EXIT_FAILURE)
        payload["source"] = normalized_source
    if evidence is not None:
        payload["evidence"] = evidence

    if not payload:
        emit_error(
            "No update fields provided.",
            code="no_backlog_item_updates",
            hint="Set at least one field such as --title, --tags, --type, or --evidence.",
            exit_code=EXIT_FAILURE,
            use_json=json,
        )
        sys.exit(EXIT_FAILURE)

    if not yes:
        render(
            {"item_id": item_id, "action": "update", "confirmed": False, "would_update": payload},
            lambda _d: f"Would update backlog item {item_id}. Use --yes to confirm.",
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)

    client = get_client(use_json=json)
    try:
        data = client.put(f"/backlog/items/{item_id}", payload)
    except AabApiError as exc:
        handle_api_error(exc, use_json=json)
    else:

        def fmt(item: dict) -> str:
            return (
                f"updated backlog item {str(item.get('id', ''))[:12]}\n"
                f"type: {_payload_type(item)}\n"
                f"title: {item.get('title', '')}\n"
                f"tags: {', '.join(item.get('tags', []))}\n"
                f"status: {format_status(item.get('status', ''))}"
            )

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command("list")
def list_items(
    project: str = typer.Option(..., "--project", help="Project ID."),
    item_type: str | None = typer.Option(None, "--type", help="Filter by item type."),
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag."),
    status: str | None = typer.Option(None, help="Filter by status."),
    limit: int = typer.Option(20, help="Max results."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List typed backlog items for a project."""
    client = get_client(use_json=json)
    params = {}
    if item_type:
        params["type"] = item_type
    if tag:
        params["tag"] = tag
    try:
        data = client.get(f"/projects/{project}/backlog/items", **params)
    except AabApiError as exc:
        handle_api_error(exc, use_json=json)
    else:
        items = data if isinstance(data, list) else []
        if status:
            items = [item for item in items if item.get("status") == status]
        items = items[:limit]

        def fmt(rows: list[dict]) -> str:
            return table(
                ["ID", "TYPE", "TITLE", "STATUS", "SEVERITY", "TAGS"],
                [
                    [
                        str(item.get("id", ""))[:12],
                        _payload_type(item),
                        str(item.get("title", ""))[:36],
                        format_status(item.get("status", "")),
                        str(item.get("severity", "")),
                        ",".join(item.get("tags", [])),
                    ]
                    for item in rows
                ],
            )

        render(items, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command("show")
def show_item(
    item_id: str = typer.Argument(help="Backlog item ID."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show one typed backlog item."""
    client = get_client(use_json=json)
    try:
        data = client.get(f"/backlog/items/{item_id}")
    except AabApiError as exc:
        handle_api_error(exc, use_json=json)
    else:

        def fmt(item: dict) -> str:
            return "\n".join(
                [
                    f"id: {item.get('id', '')}",
                    f"type: {_payload_type(item)}",
                    f"title: {item.get('title', '')}",
                    f"description: {item.get('description', '')}",
                    f"status: {format_status(item.get('status', ''))}",
                    f"priority: {item.get('priority', '')}",
                    f"severity: {item.get('severity', '')}",
                    f"source: {item.get('source', '')}",
                    f"tags: {', '.join(item.get('tags', []))}",
                    f"evidence: {item.get('evidence', '')}",
                ]
            )

        render(data, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()
