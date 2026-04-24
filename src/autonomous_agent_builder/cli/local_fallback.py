"""Local fallback loaders for agent-friendly CLI behavior when the API is down."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

from autonomous_agent_builder.agents.definitions import get_agent_definition
from autonomous_agent_builder.api.routes.dashboard_api import load_board_response, metrics_json
from autonomous_agent_builder.cli.project_discovery import ProjectNotFoundError, find_agent_builder_dir
from autonomous_agent_builder.db.session import get_session_factory
from autonomous_agent_builder.embedded.server.routes.agent import _active_chat_agent_name


def _project_root() -> Path:
    try:
        return find_agent_builder_dir(Path.cwd()).resolve().parent
    except ProjectNotFoundError:
        return Path.cwd().resolve()


def _db_path() -> Path:
    return _project_root() / ".agent-builder" / "agent_builder.db"


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"pragma table_info({table})").fetchall()
    return any(str(row["name"]) == column for row in rows)


def _local_chat_model_name(project_root: Path) -> str:
    return get_agent_definition(_active_chat_agent_name(project_root)).model


def _extract_payload_text(payload: dict[str, Any]) -> str:
    candidates = [
        payload.get("content"),
        payload.get("summary"),
        payload.get("message"),
        payload.get("detail"),
        payload.get("error"),
    ]
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return " ".join(text.split())
    return ""


def _infer_role(event_type: str, payload: dict[str, Any]) -> str:
    explicit = str(payload.get("role", "")).strip().lower()
    if explicit in {"user", "assistant", "system"}:
        return explicit
    lowered = event_type.lower()
    if "user" in lowered:
        return "user"
    if "assistant" in lowered or "tool" in lowered or "run_" in lowered:
        return "assistant"
    return "system"


async def _load_local_board_async(limit: int) -> dict[str, Any]:
    factory = get_session_factory()
    async with factory() as session:
        payload = (await load_board_response(session)).model_dump(mode="json")
    for section in ("pending", "active", "review", "done", "blocked"):
        if section in payload and isinstance(payload[section], list):
            payload[section] = payload[section][:limit]
    payload["counts"] = {
        section: len(payload.get(section, []))
        for section in ("pending", "active", "review", "done", "blocked")
    }
    payload["degraded"] = True
    payload["source"] = "local_db_fallback"
    payload["next_step"] = "builder backlog task status <task-id> --json"
    return payload


def load_local_board(limit: int) -> dict[str, Any]:
    return asyncio.run(_load_local_board_async(limit))


async def _load_local_metrics_async() -> dict[str, Any]:
    factory = get_session_factory()
    async with factory() as session:
        data = await metrics_json(session)
    payload = data.model_dump(mode="json")
    payload["summary"] = {
        "total_cost": payload.get("total_cost", 0),
        "total_tokens": payload.get("total_tokens", 0),
        "total_runs": payload.get("total_runs", 0),
        "gate_pass_rate": payload.get("gate_pass_rate", 0),
    }
    payload["degraded"] = True
    payload["source"] = "local_db_fallback"
    payload["next_step"] = "builder backlog run summary <query> --json"
    return payload


def load_local_metrics() -> dict[str, Any]:
    return asyncio.run(_load_local_metrics_async())


def load_local_agent_sessions(limit: int) -> dict[str, Any]:
    db_path = _db_path()
    project_root = _project_root()
    if not db_path.exists():
        return {
            "status": "ok",
            "count": 0,
            "results": [],
            "schema_version": "1",
            "degraded": True,
            "source": "local_db_fallback",
            "next_step": "builder start",
        }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        has_sdk_session_id = _has_column(conn, "chat_sessions", "sdk_session_id")
        session_columns = "id, sdk_session_id, created_at, updated_at" if has_sdk_session_id else "id, created_at, updated_at"
        rows = conn.execute(
            f"""
            select {session_columns}
            from chat_sessions
            order by updated_at desc, created_at desc
            limit ?
            """,
            (max(limit, 1),),
        ).fetchall()
        results = []
        for row in rows:
            event_count = conn.execute(
                "select count(*) from chat_events where session_id = ?",
                (row["id"],),
            ).fetchone()[0]
            preview_row = conn.execute(
                """
                select payload_json
                from chat_events
                where session_id = ?
                order by created_at desc
                limit 1
                """,
                (row["id"],),
            ).fetchone()
            preview = ""
            if preview_row and preview_row[0]:
                try:
                    preview = _extract_payload_text(json.loads(preview_row[0] or "{}"))
                except json.JSONDecodeError:
                    preview = ""
            results.append(
                {
                    "id": row["id"],
                    "sdk_session_id": row["sdk_session_id"] if has_sdk_session_id else None,
                    "created_at": row["created_at"] or "",
                    "updated_at": row["updated_at"] or "",
                    "message_count": event_count,
                    "preview": preview,
                }
            )
    finally:
        conn.close()

    return {
        "status": "ok",
        "count": len(results),
        "results": results,
        "schema_version": "1",
        "degraded": True,
        "source": "local_db_fallback",
        "repo_identity": str(project_root),
        "workspace_cwd": str(project_root),
        "next_step": "builder agent history --session <id> --json",
    }


def load_local_agent_history(session_id: str | None, *, full: bool) -> dict[str, Any]:
    db_path = _db_path()
    project_root = _project_root()
    payload: dict[str, Any] = {
        "session_id": "",
        "sdk_session_id": None,
        "model": _local_chat_model_name(project_root),
        "repo_identity": str(project_root),
        "workspace_cwd": str(project_root),
        "messages": [],
        "status": None,
        "degraded": True,
        "source": "local_db_fallback",
        "next_step": "builder logs --session <id> --compact --json",
    }
    if not db_path.exists():
        if full:
            payload["items"] = []
        return payload

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        has_sdk_session_id = _has_column(conn, "chat_sessions", "sdk_session_id")
        resolved_session = session_id
        if not resolved_session:
            row = conn.execute(
                "select id from chat_sessions order by updated_at desc, created_at desc limit 1"
            ).fetchone()
            resolved_session = str(row["id"]) if row else ""
        payload["session_id"] = resolved_session or ""
        if not resolved_session:
            if full:
                payload["items"] = []
            return payload
        session_row = None
        if has_sdk_session_id:
            session_row = conn.execute(
                "select sdk_session_id from chat_sessions where id = ?",
                (resolved_session,),
            ).fetchone()
        if session_row:
            payload["sdk_session_id"] = session_row["sdk_session_id"]

        rows = conn.execute(
            """
            select id, event_type, status, payload_json, created_at
            from chat_events
            where session_id = ?
            order by created_at asc
            """,
            (resolved_session,),
        ).fetchall()
        messages: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        for row in rows:
            raw_payload = row["payload_json"] or "{}"
            try:
                parsed = json.loads(raw_payload)
            except json.JSONDecodeError:
                parsed = {"content": str(raw_payload)}
            text = _extract_payload_text(parsed)
            if text:
                messages.append({"role": _infer_role(str(row["event_type"]), parsed), "content": text})
            if full:
                items.append(
                    {
                        "id": row["id"],
                        "type": row["event_type"],
                        "status": row["status"],
                        "timestamp": row["created_at"],
                        "payload": parsed,
                    }
                )
        payload["messages"] = messages
        for item in reversed(items):
            if item["type"] == "run_status":
                payload["status"] = item["payload"]
                break
        if not full and rows:
            for row in reversed(rows):
                if row["event_type"] != "run_status":
                    continue
                try:
                    payload["status"] = json.loads(row["payload_json"] or "{}")
                except json.JSONDecodeError:
                    payload["status"] = None
                break
        if full:
            payload["items"] = items
    finally:
        conn.close()
    return payload


def load_local_agent_meta() -> dict[str, Any]:
    project_root = _project_root()
    return {
        "model": _local_chat_model_name(project_root),
        "repo_identity": str(project_root),
        "workspace_cwd": str(project_root),
        "degraded": True,
        "source": "local_fallback",
        "next_step": "builder agent sessions --json",
    }
