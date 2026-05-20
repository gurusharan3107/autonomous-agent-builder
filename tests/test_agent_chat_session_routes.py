"""Agent chat session and history route regressions."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import ChatEvent, ChatSession
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from tests.agent_route_test_support import create_chat_session as _create_chat_session


@pytest.mark.asyncio
async def test_agent_chat_concurrent_request_does_not_persist_rejected_user_message(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _engine, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        session = ChatSession(
            repo_identity=str(tmp_path.resolve()),
            workspace_cwd=str(tmp_path.resolve()),
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        session_id = session.id

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_run_chat_turn(app, chat_session_id: str, message: str) -> None:
        started.set()
        await release.wait()

    monkeypatch.setattr(agent_routes, "_run_chat_turn", fake_run_chat_turn)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            responses = await asyncio.gather(
                client.post(
                    "/api/agent/chat",
                    json={"session_id": session_id, "message": "first prompt"},
                ),
                client.post(
                    "/api/agent/chat",
                    json={"session_id": session_id, "message": "second prompt"},
                ),
            )
            await started.wait()

        statuses = sorted(response.status_code for response in responses)
        assert statuses == [200, 409]

        async with factory() as db:
            result = await db.execute(
                select(ChatEvent).where(
                    ChatEvent.session_id == session_id,
                    ChatEvent.event_type == "user_message",
                )
            )
            user_events = result.scalars().all()

        assert len(user_events) == 1
        assert user_events[0].payload_json["content"] in {"first prompt", "second prompt"}
    finally:
        release.set()
        await asyncio.sleep(0)
        await app.state.chat_hub.shutdown()

@pytest.mark.asyncio
async def test_chat_history_reports_model_without_session(test_db, tmp_path):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agent/chat/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == ""
    # Conftest sets RUNTIME_MODEL=sonnet (autouse).
    # API resolves that via resolve_project_runtime_config(project_root) on
    # the project root in scope and returns it as the chat metadata model.
    assert payload["model"] == "sonnet"
    assert payload["items"] == []
    assert payload["messages"] == []
    assert payload["repo_identity"] == str(tmp_path.resolve())
    assert payload["workspace_cwd"] == str(tmp_path.resolve())

@pytest.mark.asyncio
async def test_chat_history_defaults_to_latest_meaningful_scoped_session(test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    repo_identity = str(tmp_path.resolve())
    now = datetime.now(UTC)
    expected_session_id = await _create_chat_session(
        factory,
        repo_identity=repo_identity,
        workspace_cwd=repo_identity,
        updated_at=now - timedelta(minutes=5),
        events=[
            ("user_message", {"content": "Continue the repo-scoped thread"}),
            ("assistant_message", {"content": "Resuming the latest meaningful session", "final": True}),
        ],
    )
    await _create_chat_session(
        factory,
        repo_identity="/tmp/other-project",
        workspace_cwd="/tmp/other-project",
        updated_at=now,
        events=[
            ("user_message", {"content": "Wrong repo"}),
            ("assistant_message", {"content": "Should never be selected", "final": True}),
        ],
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agent/chat/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == expected_session_id
    assert payload["items"][0]["payload"]["content"] == "Continue the repo-scoped thread"

@pytest.mark.asyncio
async def test_chat_history_fresh_mode_skips_latest_session_resume(test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    repo_identity = str(tmp_path.resolve())
    now = datetime.now(UTC)
    await _create_chat_session(
        factory,
        repo_identity=repo_identity,
        workspace_cwd=repo_identity,
        updated_at=now - timedelta(minutes=1),
        events=[
            ("user_message", {"content": "Resume me"}),
            ("assistant_message", {"content": "Meaningful transcript", "final": True}),
        ],
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agent/chat/history", params={"fresh": "1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == ""
    assert payload["items"] == []
    assert payload["messages"] == []

@pytest.mark.asyncio
async def test_chat_session_list_filters_wrong_repo_and_marks_latest_resume_candidate(test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    repo_identity = str(tmp_path.resolve())
    now = datetime.now(UTC)
    older_session_id = await _create_chat_session(
        factory,
        repo_identity=repo_identity,
        workspace_cwd=repo_identity,
        updated_at=now - timedelta(minutes=10),
        events=[("assistant_message", {"content": "Bootstrap only", "final": True})],
    )
    latest_resume_id = await _create_chat_session(
        factory,
        repo_identity=repo_identity,
        workspace_cwd=repo_identity,
        updated_at=now - timedelta(minutes=2),
        events=[
            ("user_message", {"content": "Resume me"}),
            ("assistant_message", {"content": "Meaningful transcript", "final": True}),
        ],
    )
    await _create_chat_session(
        factory,
        repo_identity="/tmp/wrong-project",
        workspace_cwd="/tmp/wrong-project",
        updated_at=now,
        events=[("user_message", {"content": "Foreign session"})],
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agent/chat/sessions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_resume_session_id"] == latest_resume_id
    assert [session["id"] for session in payload["sessions"]] == [latest_resume_id, older_session_id]
    assert payload["sessions"][0]["is_resume_candidate"] is True
    assert payload["sessions"][1]["is_resume_candidate"] is False

@pytest.mark.asyncio
async def test_chat_history_rejects_wrong_project_session_id(test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    foreign_session_id = await _create_chat_session(
        factory,
        repo_identity="/tmp/other-project",
        workspace_cwd="/tmp/other-project",
        updated_at=datetime.now(UTC),
        events=[("user_message", {"content": "Do not load me"})],
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agent/chat/history", params={"session_id": foreign_session_id})

    assert response.status_code == 409
    assert "different repo or workspace" in response.json()["detail"]

@pytest.mark.asyncio
async def test_chat_post_rejects_wrong_project_session_id(monkeypatch, test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async def fake_run_phase(self, **kwargs):
        return RunResult(
            session_id="sdk-session-ignored",
            cost_usd=0.0,
            tokens_input=0,
            tokens_output=0,
            num_turns=1,
            output_text="Should not run",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )

    foreign_session_id = await _create_chat_session(
        factory,
        repo_identity="/tmp/other-project",
        workspace_cwd="/tmp/other-project",
        updated_at=datetime.now(UTC),
        events=[("user_message", {"content": "Do not post into me"})],
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "hello", "session_id": foreign_session_id},
        )

    assert response.status_code == 409
    assert "different repo or workspace" in response.json()["detail"]
