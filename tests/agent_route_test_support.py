"""Focused support helpers for embedded Agent route tests."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from httpx import AsyncClient

from autonomous_agent_builder.db.models import ChatEvent, ChatSession, Feature, Project, Task
from autonomous_agent_builder.services.readiness import assess_readiness


def write_forward_engineering_ready_state(project_root: Path) -> None:
    (project_root / "CLAUDE.md").write_text("# Test\n", encoding="utf-8")
    Path(os.environ["AAB_BUILDER_SOURCE_ENV"]).write_text(
        "AAB_CLAUDE_OTEL_ENABLED=1\n"
        "AAB_CLAUDE_OTEL_ENDPOINT=http://localhost:4318\n"
        "AAB_CLAUDE_OTEL_SERVICE_NAME=test\n"
        "AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID=true\n",
        encoding="utf-8",
    )
    agent_builder_dir = project_root / ".agent-builder"
    agent_builder_dir.mkdir(parents=True, exist_ok=True)
    (agent_builder_dir / "config.yaml").write_text("project:\n  name: test\n", encoding="utf-8")
    (agent_builder_dir / "agent_builder.db").write_text("", encoding="utf-8")
    phases = [
        {
            "id": phase_id,
            "title": phase_id.replace("_", " ").title(),
            "status": "passed",
            "message": "",
            "started_at": None,
            "finished_at": None,
            "result": result,
            "error": None,
        }
        for phase_id, result in (
            ("repo_detect", {}),
            ("project_seed", {}),
            ("repo_scan", {}),
            ("work_item_seed", {}),
            ("kb_extract", {"skipped": True, "reason": "forward_engineering_onboarding"}),
            ("kb_validate", {"skipped": True, "reason": "forward_engineering_onboarding"}),
        )
    ]
    phases.append(
        {
            "id": "ready",
            "title": "Ready",
            "status": "passed",
            "message": "",
            "started_at": None,
            "finished_at": None,
            "result": {"ready": True},
            "error": None,
        }
    )
    (agent_builder_dir / "onboarding-state.json").write_text(
        json.dumps(
            {
                "repo": {"root": str(project_root), "name": project_root.name},
                "onboarding_mode": "forward_engineering",
                "current_phase": "ready",
                "ready": True,
                "updated_at": "2026-04-20T00:00:00+00:00",
                "phases": phases,
                "entity_counts": {"projects": 1, "features": 0, "tasks": 0},
                "kb_status": {"quality_gate": "deferred"},
                "scan_summary": {"important_files": []},
                "archives": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    assess_readiness(project_root, write=True)


async def wait_for_history_item(
    client: AsyncClient,
    session_id: str,
    item_type: str,
    *,
    timeout: float = 3.0,
    predicate: Any = None,
):
    deadline = asyncio.get_running_loop().time() + timeout
    found_payload = None
    found_item = None
    while asyncio.get_running_loop().time() < deadline:
        response = await client.get("/api/agent/chat/history", params={"session_id": session_id})
        assert response.status_code == 200
        payload = response.json()
        for item in payload["items"]:
            if item["type"] == item_type and (predicate is None or predicate(item)):
                if item_type not in {"assistant_message", "run_error"}:
                    return payload, item
                found_payload = payload
                found_item = item
                status = payload.get("status") or {}
                if status.get("running") is not True and status.get("stop_reason") not in {
                    "completed_after_running_status",
                }:
                    return payload, item
        await asyncio.sleep(0.05)
    if found_payload is not None and found_item is not None:
        return found_payload, found_item
    raise AssertionError(f"Timed out waiting for history item type '{item_type}'")


async def wait_for_history_status(
    client: AsyncClient,
    session_id: str,
    *,
    timeout: float = 3.0,
    predicate: Any = None,
):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        response = await client.get("/api/agent/chat/history", params={"session_id": session_id})
        assert response.status_code == 200
        payload = response.json()
        status = payload.get("status")
        if status is not None and (predicate is None or predicate(status)):
            return payload
        await asyncio.sleep(0.05)
    raise AssertionError("Timed out waiting for history status")


async def approve_pending_sprint_scope(client: AsyncClient, session_id: str):
    _history_payload, approval_item = await wait_for_history_item(
        client,
        session_id,
        "tool_approval_request",
        predicate=lambda item: item["payload"].get("tool_name") == "Delivery scope approval"
        and item["status"] == "pending",
    )
    assert approval_item["payload"]["summary"] == "Approve this improvement before work starts"
    approval = await client.post(
        "/api/agent/chat/respond",
        json={
            "session_id": session_id,
            "event_id": approval_item["id"],
            "decision": "allow",
        },
    )
    assert approval.status_code == 200
    return approval_item


async def create_chat_session(
    factory,
    *,
    repo_identity: str | None,
    workspace_cwd: str | None,
    updated_at: datetime,
    events: list[tuple[str, dict]] | None = None,
) -> str:
    async with factory() as db:
        session = ChatSession(
            repo_identity=repo_identity,
            workspace_cwd=workspace_cwd,
            updated_at=updated_at,
        )
        db.add(session)
        await db.flush()
        for event_type, payload in events or []:
            db.add(
                ChatEvent(
                    session_id=session.id,
                    event_type=event_type,
                    payload_json=payload,
                    status="completed",
                )
            )
        await db.commit()
        return session.id


async def append_chat_event(
    factory,
    *,
    session_id: str,
    event_type: str,
    payload: dict,
    created_at: datetime,
) -> None:
    async with factory() as db:
        db.add(
            ChatEvent(
                session_id=session_id,
                event_type=event_type,
                payload_json=payload,
                status="completed",
                created_at=created_at,
            )
        )
        await db.commit()


async def create_project_feature_task(
    factory,
    *,
    project_name: str,
    feature_title: str,
    task_title: str,
    task_description: str,
    depends_on: dict | None = None,
) -> tuple[str, str, str]:
    async with factory() as db:
        project = Project(name=project_name, description="demo", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(project_id=project.id, title=feature_title, description="feature")
        db.add(feature)
        await db.flush()
        task = Task(
            feature_id=feature.id,
            title=task_title,
            description=task_description,
            depends_on=depends_on,
        )
        db.add(task)
        await db.commit()
        return project.id, feature.id, task.id
