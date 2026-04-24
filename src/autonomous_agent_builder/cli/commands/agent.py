"""Agent commands — chat sessions and runtime metadata."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import typer

from autonomous_agent_builder.agents.documentation_bridge import run_documentation_refresh_bridge
from autonomous_agent_builder.cli.client import (
    EXIT_SUCCESS,
    AabApiError,
    BuilderConnectivityError,
    get_client,
    handle_api_error,
    request_json,
)
from autonomous_agent_builder.cli.local_fallback import (
    load_local_agent_history,
    load_local_agent_meta,
    load_local_agent_sessions,
)
from autonomous_agent_builder.cli.output import emit_error, render, table, truncate

app = typer.Typer(
    help=(
        "Agent chat sessions and runtime metadata.\n\n"
        "Start here:\n"
        "  builder agent sessions --json\n"
        "  builder agent history --json\n"
        "  builder agent meta --json\n"
        "  builder agent documentation-refresh --validation kb-validate.json --json\n"
    )
)


def _documentation_refresh_format(payload: dict[str, Any]) -> str:
    lines = [
        f"status: {payload.get('status', '')}",
        f"mode: {payload.get('mode', '')}",
        f"summary: {payload.get('summary', '')}",
    ]
    actionable = payload.get("actionable_doc_ids", [])
    if actionable:
        lines.append(f"actionable_doc_ids: {', '.join(str(item) for item in actionable)}")
    if payload.get("manual_attention_reasons"):
        lines.append("manual_attention_reasons:")
        for reason in payload["manual_attention_reasons"]:
            lines.append(f"  - {reason}")
    run = payload.get("run") or {}
    if run:
        lines.append(
            "run: "
            + ", ".join(
                f"{key}={value}"
                for key, value in run.items()
                if key in {"session_id", "cost_usd", "num_turns", "stop_reason"}
                and value not in ("", None)
            )
        )
    remaining_gap = str(payload.get("remaining_gap", "") or "").strip()
    if remaining_gap:
        lines.append(f"remaining_gap: {remaining_gap}")
    lines.append(f"Next: {payload.get('next_step', '')}")
    return "\n".join(lines)


@app.command("sessions")
def list_sessions(
    limit: int = typer.Option(20, help="Max sessions."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List saved agent chat sessions."""
    client = get_client(use_json=json)
    try:
        try:
            data = request_json(client, "GET", "/agent/chat/sessions")
        except BuilderConnectivityError:
            data = load_local_agent_sessions(limit)
    except AabApiError as e:
        handle_api_error(e, use_json=json)
    else:
        raw_items = (
            data.get("results", [])
            if isinstance(data, dict) and "results" in data
            else data.get("sessions", []) if isinstance(data, dict) else []
        )
        items = list(raw_items)[:limit]
        payload = dict(data) if isinstance(data, dict) else {}
        payload.update(
            {
                "status": "ok",
                "count": len(items),
                "results": items,
                "schema_version": "1",
                "next_step": "builder agent history --session <id> --json",
            }
        )

        def fmt(data: dict[str, Any]) -> str:
            rows = list(data.get("results", []))
            headers = ["ID", "SDK SESSION", "UPDATED", "MESSAGES", "PREVIEW"]
            body = [
                [
                    str(item.get("id", ""))[:12],
                    str(item.get("sdk_session_id", "") or "")[:12],
                    str(item.get("updated_at", ""))[:19],
                    str(item.get("message_count", 0)),
                    truncate(str(item.get("preview", "") or ""), 60),
                ]
                for item in rows
            ]
            return table(headers, body) + f"\n\nNext: {data.get('next_step', '')}"

        render(payload, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def history(
    session_id: str | None = typer.Option(None, "--session", help="Chat session ID."),
    full: bool = typer.Option(False, "--full", help="Include timeline items."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show agent chat history for one session."""
    client = get_client(use_json=json)
    try:
        params = {"session_id": session_id} if session_id else {}
        try:
            data = request_json(client, "GET", "/agent/chat/history", params=params)
        except BuilderConnectivityError:
            data = load_local_agent_history(session_id, full=full)
    except AabApiError as e:
        handle_api_error(e, use_json=json)
    else:
        payload = dict(data) if isinstance(data, dict) else {}
        if not full:
            payload.pop("items", None)
        payload["next_step"] = "builder logs --session <id> --compact --json"

        def fmt(item: dict[str, Any]) -> str:
            lines = [
                f"session_id: {item.get('session_id', '') or '(none)'}",
                f"sdk_session_id: {item.get('sdk_session_id', '') or '(none)'}",
                f"model: {item.get('model', '')}",
                f"messages: {len(item.get('messages', []))}",
            ]
            status = item.get("status")
            if status:
                lines.append(
                    "status: "
                    + ", ".join(
                        f"{key}={value}"
                        for key, value in status.items()
                        if key
                        in {
                            "running",
                            "current_turn",
                            "max_turns",
                            "tokens_used",
                            "cost_usd",
                            "duration_ms",
                            "stop_reason",
                            "sdk_session_id",
                            "error",
                        }
                        and value not in ("", None)
                    )
                )
            messages = item.get("messages", [])
            if messages:
                lines.append("")
                lines.append("--- MESSAGES ---")
                for message in messages[-10:]:
                    role = str(message.get("role", ""))
                    content = truncate(str(message.get("content", "") or ""), 220)
                    lines.append(f"[{role}] {content}")
            if full and item.get("items"):
                lines.append("")
                lines.append(f"timeline_items: {len(item['items'])}")
            lines.append("")
            lines.append(f"Next: {item.get('next_step', '')}")
            return "\n".join(lines)

        render(payload, fmt, use_json=json)
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command()
def meta(
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show stable agent-lane metadata."""
    client = get_client(use_json=json)
    try:
        try:
            data = request_json(client, "GET", "/agent/chat/meta")
        except BuilderConnectivityError:
            data = load_local_agent_meta()
    except AabApiError as e:
        handle_api_error(e, use_json=json)
    else:
        payload = dict(data) if isinstance(data, dict) else {"raw": data}
        payload["next_step"] = "builder agent sessions --json"
        render(
            payload,
            lambda item: (
                f"model: {item.get('model', '')}\n"
                f"Next: {item.get('next_step', '')}"
            ),
            use_json=json,
        )
        sys.exit(EXIT_SUCCESS)
    finally:
        client.close()


@app.command("documentation-refresh")
def documentation_refresh(
    validation: Path = typer.Option(
        ...,
        "--validation",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to `builder knowledge validate --json` output.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Run the repo-owned documentation-agent bridge for bounded freshness updates."""
    try:
        validation_payload = json.loads(validation.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        emit_error(
            f"Invalid validation JSON: {exc}",
            code="invalid_input",
            hint="Run `builder knowledge validate --json > kb-validate.json` and retry.",
            use_json=json_output,
        )
        sys.exit(2)

    project_root = Path(os.environ.get("AAB_PROJECT_ROOT", Path.cwd())).resolve()
    payload = asyncio.run(
        run_documentation_refresh_bridge(validation_payload, project_root=project_root)
    )
    render(payload, _documentation_refresh_format, use_json=json_output)

    status = str(payload.get("status", "") or "").strip()
    validation_status = str(payload.get("validation_status", "") or "").strip()
    if status in {"already_current", "updated_and_verified"} and (
        not validation_status or validation_status == "pass"
    ):
        sys.exit(EXIT_SUCCESS)
    if status == "already_current":
        sys.exit(EXIT_SUCCESS)
    sys.exit(1)
