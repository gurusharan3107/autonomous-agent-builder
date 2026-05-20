"""Tests for embedded Agent runtime attribution and resume safety."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from autonomous_agent_builder.db.models import ChatEvent, ChatSession
from autonomous_agent_builder.embedded.server import agent_chat_sessions
from autonomous_agent_builder.embedded.server.app import create_app


def test_compatible_resume_session_rejects_session_from_previous_runtime():
    session = ChatSession(id="session-1", sdk_session_id="claude-sdk-session")
    session.events = [
        ChatEvent(
            session_id="session-1",
            event_type="run_status",
            payload_json={
                "sdk_session_id": "claude-sdk-session",
                "runtime_sdk": "claude",
                "provider": "claude_code",
            },
            created_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )
    ]

    class CodexRuntime:
        name = "codex_sdk"
        provider = "codex_subscription"

    assert agent_chat_sessions.compatible_resume_session(session, CodexRuntime()) is None


def test_compatible_resume_session_reuses_session_for_same_runtime():
    session = ChatSession(id="session-1", sdk_session_id="codex-sdk-session")
    session.events = [
        ChatEvent(
            session_id="session-1",
            event_type="run_status",
            payload_json={
                "sdk_session_id": "codex-sdk-session",
                "runtime_sdk": "codex_sdk",
                "provider": "codex_subscription",
            },
            created_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )
    ]

    class CodexRuntime:
        name = "codex_sdk"
        provider = "codex_subscription"

    assert agent_chat_sessions.compatible_resume_session(session, CodexRuntime()) == "codex-sdk-session"


@pytest.mark.asyncio
async def test_chat_history_preserves_thread_runtime_after_runtime_switch(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")
    env_path = Path(os.environ["AAB_BUILDER_SOURCE_ENV"])
    env_path.write_text(
        'RUNTIME_SDK="codex_sdk"\n'
        'RUNTIME_PROVIDER="codex_subscription"\n'
        'RUNTIME_MODEL="gpt-5.5"\n',
        encoding="utf-8",
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        db.add(
            ChatEvent(
                session_id=session.id,
                event_type="run_status",
                payload_json={
                    "running": False,
                    "runtime_sdk": "claude",
                    "provider": "claude_agent_sdk",
                    "model": "sonnet",
                    "effort": "medium",
                    "tokens_used": 1283,
                },
                status="completed",
                created_at=datetime(2026, 5, 15, 5, 13, tzinfo=UTC),
            )
        )
        await db.commit()
        session_id = session.id

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        meta_payload = (await client.get("/api/agent/chat/meta")).json()
        history_payload = (
            await client.get("/api/agent/chat/history", params={"session_id": session_id})
        ).json()

    assert meta_payload["runtime_sdk"] == "codex_sdk"
    assert meta_payload["provider"] == "codex_subscription"
    assert history_payload["runtime_sdk"] == "claude"
    assert history_payload["provider"] == "claude_agent_sdk"
    assert history_payload["model"] == "sonnet"
    assert history_payload["status"]["runtime_sdk"] == "claude"


def test_compatible_resume_session_rejects_codex_large_output_context():
    session = ChatSession(id="session-1", sdk_session_id="codex-sdk-session")
    session.events = [
        ChatEvent(
            session_id="session-1",
            event_type="run_status",
            payload_json={
                "sdk_session_id": "codex-sdk-session",
                "runtime_sdk": "codex_sdk",
                "provider": "codex_subscription",
                "observability": {
                    "context_retention": {
                        "resume_recommended": False,
                        "reason": "large_command_output_artifact",
                    }
                },
            },
            created_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )
    ]

    class CodexRuntime:
        name = "codex_sdk"
        provider = "codex_subscription"

    assert agent_chat_sessions.compatible_resume_session(session, CodexRuntime()) is None


def test_compatible_resume_session_rejects_unattributed_session_when_status_exists():
    session = ChatSession(id="session-1", sdk_session_id="stale-sdk-session")
    session.events = [
        ChatEvent(
            session_id="session-1",
            event_type="run_status",
            payload_json={
                "runtime_sdk": "codex_sdk",
                "provider": "codex_subscription",
            },
            created_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )
    ]

    class CodexRuntime:
        name = "codex_sdk"
        provider = "codex_subscription"

    assert agent_chat_sessions.compatible_resume_session(session, CodexRuntime()) is None
