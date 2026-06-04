from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from autonomous_agent_builder.db.models import (
    AgentRun,
    ChatEvent,
    ChatSession,
    Feature,
    FeatureStatus,
    Project,
    Sprint,
    Task,
    TaskPhase,
    TaskStatus,
)
from autonomous_agent_builder.db.session import close_db
from autonomous_agent_builder.embedded.server import agent_chat_sessions
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from autonomous_agent_builder.embedded.server.routes import realtime
from autonomous_agent_builder.embedded.server.routes import tasks as task_routes
from autonomous_agent_builder.services.voice_operator import (
    AgentOperatorService,
    VoiceCompletionNotifier,
    VoiceOperatorService,
)
from tests.realtime_voice_operator_test_support import FakeAsyncClient as _FakeAsyncClient


@pytest.mark.asyncio
async def test_realtime_session_requires_openai_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    app = FastAPI()
    app.include_router(realtime.router, prefix="/api")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/realtime/session",
            content="v=0\r\no=- test 1 1 IN IP4 127.0.0.1\r\n",
            headers={"Content-Type": "application/sdp"},
        )

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.text
    assert "Builder source environment" in response.text
    assert "not the generated app .env" in response.text
    assert "restart builder start" in response.text


@pytest.mark.asyncio
async def test_realtime_session_does_not_use_selected_runtime_api_key(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("RUNTIME_PROVIDER", "codex_subscription")
    monkeypatch.setenv("RUNTIME_API_KEY_ENV", "OTHER_OPENAI_KEY")
    monkeypatch.setenv("OTHER_OPENAI_KEY", "wrong-lane-key")
    monkeypatch.setattr(realtime.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.calls = []

    app = FastAPI()
    app.include_router(realtime.router, prefix="/api")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/realtime/session",
            content="v=0\r\no=- test 1 1 IN IP4 127.0.0.1\r\n",
            headers={"Content-Type": "application/sdp"},
        )

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.text
    assert _FakeAsyncClient.calls == []


@pytest.mark.asyncio
async def test_realtime_session_posts_sdp_and_session_as_multipart_fields(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("RUNTIME_PROVIDER", "codex_subscription")
    monkeypatch.setenv("RUNTIME_API_KEY_ENV", "OTHER_OPENAI_KEY")
    monkeypatch.setenv("OTHER_OPENAI_KEY", "wrong-lane-key")
    monkeypatch.setattr(realtime.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(realtime, "_start_sideband_task", lambda app, call_id: None)
    _FakeAsyncClient.calls = []

    app = FastAPI()
    app.include_router(realtime.router, prefix="/api")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/realtime/session",
            content="v=0\r\no=- test 1 1 IN IP4 127.0.0.1\r\n",
            headers={"Content-Type": "application/sdp"},
        )

    assert response.status_code == 201
    assert response.text == "answer-sdp"
    assert response.headers["location"] == "/v1/realtime/calls/rtc_test_call"
    assert response.headers["x-realtime-call-id"] == "rtc_test_call"

    call = _FakeAsyncClient.calls[0]
    assert call["url"] == "https://api.openai.com/v1/realtime/calls"
    assert call["headers"] == {"Authorization": "Bearer test-key"}
    assert "wrong-lane-key" not in json.dumps(call)
    assert call["files"]["sdp"] == (None, "v=0\r\no=- test 1 1 IN IP4 127.0.0.1\r\n")
    assert call["files"]["session"][0] is None
    assert '"model": "gpt-realtime-mini"' in call["files"]["session"][1]
    assert '"retention_ratio": 0.8' in call["files"]["session"][1]
    assert '"noise_reduction": {"type": "far_field"}' in call["files"]["session"][1]
    assert '"turn_detection": {"type": "server_vad"' in call["files"]["session"][1]
    assert '"threshold": 0.5' in call["files"]["session"][1]
    assert '"prefix_padding_ms": 300' in call["files"]["session"][1]
    assert '"silence_duration_ms": 500' in call["files"]["session"][1]
    assert '"create_response": true' in call["files"]["session"][1]
    assert "idle_timeout_ms" not in call["files"]["session"][1]


@pytest.mark.asyncio
async def test_realtime_text_control_handles_simple_board_status_prompt(test_db, tmp_path: Path):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        project = Project(name="Todo App")
        feature = Feature(
            project=project,
            title="Deterministic tests and build script",
            status=FeatureStatus.DONE,
        )
        task = Task(
            feature=feature,
            title="Verify Deterministic tests and build script for shipping",
            status=TaskStatus.IMPLEMENTATION,
        )
        db.add_all([session, project, feature, task])
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/realtime/text-control",
            json={
                "message": "what is the status of the board?",
                "call_id": "rtc_text_test",
                "session_id": session.id,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["tool_name"] == "get_builder_agent_update"
    assert "Board status from Builder source of truth" in payload["assistant_message"]
    assert (
        "Queued 1, in progress 0, needs review 0, shipped 0, blocked 0."
        in payload["assistant_message"]
    )
    assert "Backlog features 1/1 done, 0 open." in payload["assistant_message"]
    assert "queued board task" in payload["assistant_message"]
    assert "No operator decision is pending." in payload["assistant_message"]

    async with factory() as db:
        result = await db.execute(
            select(ChatEvent.event_type).where(
                ChatEvent.event_type.in_(("voice_tool_call", "voice_tool_output", "voice_digest"))
            )
        )
        event_types = set(result.scalars().all())

    assert {"voice_tool_call", "voice_tool_output", "voice_digest"} <= event_types


@pytest.mark.asyncio
async def test_realtime_text_control_defaults_to_current_sprint_scope(test_db, tmp_path: Path):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        project = Project(name="Todo App")
        older_feature = Feature(
            project=project,
            title="Deterministic tests and build script",
            status=FeatureStatus.DONE,
        )
        current_feature = Feature(
            project=project,
            title="In-app task completion notifications",
            status=FeatureStatus.DONE,
        )
        older_task = Task(
            feature=older_feature,
            title="Verify Deterministic tests and build script for shipping",
            status=TaskStatus.IMPLEMENTATION,
            phase=TaskPhase.IMPLEMENTATION,
        )
        current_task = Task(
            feature=current_feature,
            title="Verify In-app task completion notifications for shipping",
            status=TaskStatus.DONE,
            phase=TaskPhase.COMPLETE,
        )
        db.add_all([session, project, older_feature, current_feature, older_task, current_task])
        await db.flush()
        db.add(
            AgentRun(
                task_id=older_task.id,
                agent_name="feature-verifier",
                runtime_sdk="claude",
                status="completed",
                stop_reason="provider_limit",
                completed_at=datetime(2026, 5, 12, 12, 0, tzinfo=UTC),
                started_at=datetime(2026, 5, 12, 11, 59, tzinfo=UTC),
            )
        )
        older_sprint = Sprint(
            project=project,
            label="Sprint 1",
            phase="implementation",
            approved_feature_ids=[older_feature.id],
            generated_task_ids=[older_task.id],
            created_at=datetime(2026, 5, 12, tzinfo=UTC),
        )
        current_sprint = Sprint(
            project=project,
            label="Sprint 2",
            phase="shipped",
            verification_status="shipped",
            approved_feature_ids=[current_feature.id],
            generated_task_ids=[current_task.id],
            created_at=datetime(2026, 5, 13, tzinfo=UTC),
        )
        db.add_all([older_sprint, current_sprint])
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/realtime/text-control",
            json={
                "message": "what is the status of the board?",
                "call_id": "rtc_current_sprint",
                "session_id": session.id,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert (
        "Current sprint Board status from Builder source of truth (`Sprint 2`):"
        in payload["assistant_message"]
    )
    assert (
        "Queued 0, in progress 0, needs review 0, shipped 1, blocked 0."
        in payload["assistant_message"]
    )
    assert "Backlog features 2/2 done, 0 open." in payload["assistant_message"]
    assert "Current sprint `Sprint 2` is shipped." in payload["assistant_message"]
    assert payload["assistant_message"].endswith("No operator decision is pending.")
    assert (
        "Verify Deterministic tests and build script for shipping"
        not in payload["assistant_message"]
    )
    assert "queued board task" not in payload["assistant_message"]


@pytest.mark.asyncio
async def test_realtime_text_control_leaves_non_status_text_to_realtime_model(tmp_path: Path):
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/realtime/text-control",
            json={"message": "This should feel natural, not prompt driven."},
        )

    assert response.status_code == 200
    assert response.json() == {
        "handled": False,
        "operator_message": "",
        "assistant_message": "",
        "tool_name": "",
        "route": "",
    }


@pytest.mark.asyncio
async def test_realtime_text_control_fallback_delegates_exact_message(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )
    captured: dict[str, str] = {}

    async def fake_run_chat_turn(app_arg: Any, session_id: str, message: str) -> None:
        assert app_arg is app
        captured["session_id"] = session_id
        captured["message"] = message

    monkeypatch.setattr(agent_routes, "_run_chat_turn", fake_run_chat_turn)
    monkeypatch.setattr(VoiceCompletionNotifier, "schedule", lambda *args: None)

    exact_message = "I want to improve the todo app so I can search tasks by text."
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/realtime/text-control",
            json={"message": exact_message, "fallback_to_agent": True},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["handled"] is True
    assert payload["operator_message"] == exact_message
    assert payload["assistant_message"] == "Builder is working in Conversation."
    assert payload["tool_name"] == "delegate_to_builder_agent"
    assert payload["route"].startswith("/?session=")
    assert payload["route"].endswith("&mode=chat")
    await asyncio.sleep(0)
    assert captured["message"] == exact_message
    assert captured["session_id"] in payload["route"]

    async with factory() as db:
        event_result = await db.execute(
            select(ChatEvent).where(ChatEvent.event_type == "user_message")
        )
        user_event = event_result.scalar_one()
    assert user_event.payload_json["content"] == exact_message
    assert user_event.payload_json["source"] == "realtime_voice"


@pytest.mark.asyncio
async def test_realtime_text_control_does_not_treat_page_questions_as_navigation(tmp_path: Path):
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/realtime/text-control",
            json={"message": "why is observability still showing a missing signal?"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "handled": False,
        "operator_message": "",
        "assistant_message": "",
        "tool_name": "",
        "route": "",
    }


@pytest.mark.asyncio
async def test_realtime_session_fresh_mode_binds_new_agent_session(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(realtime.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(realtime, "_start_sideband_task", lambda *args: None)
    _FakeAsyncClient.calls = []
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/realtime/session",
            content="v=0\r\no=- test 1 1 IN IP4 127.0.0.1\r\n",
            headers={
                "Content-Type": "application/sdp",
                "X-Agent-Session-Mode": "fresh",
            },
        )

    assert response.status_code == 201
    assert response.headers["X-Realtime-Call-Id"] == "rtc_test_call"
    bound_session_id = response.headers["X-Agent-Session-Id"]
    assert bound_session_id
    assert realtime._voice_call_session_id(app, "rtc_test_call") == bound_session_id


@pytest.mark.asyncio
async def test_realtime_tool_status_uses_bound_fresh_session_not_latest(
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        old_session = ChatSession()
        fresh_session = ChatSession()
        agent_chat_sessions.stamp_session_scope(old_session, tmp_path)
        agent_chat_sessions.stamp_session_scope(fresh_session, tmp_path)
        db.add_all([old_session, fresh_session])
        await db.flush()
        db.add(
            ChatEvent(
                session_id=old_session.id,
                event_type="voice_final_summary",
                status="completed",
                payload_json={"summary": "Old session summary should not be reused."},
            )
        )
        await db.commit()
        old_session_id = old_session.id
        fresh_session_id = fresh_session.id

    realtime._bind_voice_call_session(app, "rtc_fresh", fresh_session_id)
    result = await realtime._handle_tool_call(
        app,
        {"name": "get_builder_agent_update", "arguments": "{}"},
        call_id="rtc_fresh",
    )

    assert result["ok"] is True
    assert result["status"]["latest_session_id"] == fresh_session_id
    assert result["status"]["latest_session_id"] != old_session_id
    assert "Old session summary" not in result["status"]["voice_digest"]


@pytest.mark.asyncio
async def test_embedded_server_registers_realtime_session_route(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/realtime/session",
            content="v=0\r\no=- test 1 1 IN IP4 127.0.0.1\r\n",
            headers={"Content-Type": "application/sdp"},
        )

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.text


@pytest.mark.asyncio
async def test_voice_tool_switches_builder_runtime_for_future_runs(test_db, tmp_path: Path):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    codex_result = await realtime._handle_tool_call(
        app,
        {"name": "switch_builder_runtime", "arguments": '{"sdk": "codex sdk"}'},
        call_id="rtc_runtime",
    )

    assert codex_result["ok"] is True
    assert codex_result["result"]["status"] == "runtime_switched"
    assert codex_result["result"]["selected_runtime_sdk"] == "codex_sdk"
    assert codex_result["result"]["provider"] == "codex_subscription"
    assert codex_result["result"]["scope"] == "future_runs_only"
    assert "preserved" in codex_result["result"]["voice_digest"]
    env_text = Path(os.environ["AAB_BUILDER_SOURCE_ENV"]).read_text(encoding="utf-8")
    assert 'RUNTIME_SDK="codex_sdk"' in env_text
    assert 'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="1"' in env_text
    assert 'AAB_CLAUDE_OTEL_ENABLED="0"' in env_text

    claude_result = await realtime._switch_builder_runtime(
        app,
        {"sdk": "Claude Agent SDK", "voice_call_id": "rtc_runtime"},
    )

    assert claude_result["selected_runtime_sdk"] == "claude"
    assert claude_result["provider"] == "claude_agent_sdk"
    env_text = Path(os.environ["AAB_BUILDER_SOURCE_ENV"]).read_text(encoding="utf-8")
    assert 'RUNTIME_SDK="claude"' in env_text
    assert 'AAB_CLAUDE_OTEL_ENABLED="1"' in env_text
    assert 'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="0"' in env_text

    async with factory() as db:
        event_result = await db.execute(
            select(ChatEvent)
            .where(ChatEvent.event_type == "runtime_settings_updated")
            .order_by(ChatEvent.created_at.asc())
        )
        events = list(event_result.scalars().all())
    assert [event.payload_json["selected_runtime_sdk"] for event in events] == [
        "codex_sdk",
        "claude",
    ]
    assert all(event.payload_json["scope"] == "future_runs_only" for event in events)
    assert all(event.payload_json["source"] == "realtime_voice" for event in events)


@pytest.mark.asyncio
async def test_get_builder_status_summarizes_latest_pending_cards(test_db, tmp_path: Path):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        db.add(
            ChatEvent(
                session_id=session.id,
                event_type="ask_user_question",
                status="pending",
                payload_json={"question": "Which scope?", "summary": "Scope decision"},
            )
        )
        await db.commit()

    payload = await realtime._get_builder_status(app)

    assert payload["latest_session_id"] == session.id
    assert payload["voice_digest"] == "Builder needs 1 operator decision or answer."
    assert payload["pending_operator_items"][0]["type"] == "ask_user_question"
    assert payload["pending_operator_items"][0]["question"] == "Which scope?"
    async with factory() as db:
        event_result = await db.execute(
            select(ChatEvent).where(ChatEvent.event_type == "voice_digest")
        )
        digest_events = list(event_result.scalars().all())
    assert digest_events
    assert digest_events[0].payload_json["pending_operator_count"] == 1


@pytest.mark.asyncio
async def test_get_builder_status_includes_blocked_board_tasks(test_db, tmp_path: Path):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        project = Project(name="Todo App")
        feature = Feature(project=project, title="Board status")
        task = Task(
            feature=feature,
            title="Fix provider status reporting",
            status=TaskStatus.CAPABILITY_LIMIT,
            capability_limit_reason="provider quota blocked implementation",
        )
        db.add_all([session, project, feature, task])
        await db.commit()
        session_id = session.id

    payload = await realtime._get_builder_status(app)

    assert payload["latest_session_id"] == session_id
    assert payload["board_status"]["blocked_count"] == 1
    assert payload["board_status"]["status_counts"]["capability_limit"] == 1
    assert payload["board_status"]["blocked_tasks"][0]["title"] == ("Fix provider status reporting")
    assert "blocked board task" in payload["voice_digest"]
    assert "Fix provider status reporting" in payload["voice_digest"]
    assert "provider quota blocked implementation" in payload["voice_digest"]
    assert "Builder is idle" not in payload["voice_digest"]
    async with factory() as db:
        event_result = await db.execute(
            select(ChatEvent).where(ChatEvent.event_type == "voice_digest")
        )
        digest_event = event_result.scalar_one()
    assert digest_event.payload_json["board_status"]["blocked_count"] == 1


@pytest.mark.asyncio
async def test_get_builder_status_uses_board_lane_counts_for_waiting_task(test_db, tmp_path: Path):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        project = Project(name="Todo App")
        feature = Feature(project=project, title="Board status")
        task = Task(
            feature=feature,
            title="Verify Deterministic tests and build script for shipping",
            status=TaskStatus.IMPLEMENTATION,
        )
        db.add_all([session, project, feature, task])
        await db.commit()

    payload = await realtime._get_builder_status(app)

    assert payload["board_status"]["queued_count"] == 1
    assert payload["board_status"]["active_count"] == 0
    assert payload["board_status"]["queued_tasks"][0]["title"] == (
        "Verify Deterministic tests and build script for shipping"
    )
    assert "queued board task" in payload["voice_digest"]
    assert "active board task" not in payload["voice_digest"]


@pytest.mark.asyncio
async def test_get_builder_status_separates_done_backlog_from_queued_board_task(
    test_db, tmp_path: Path
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        project = Project(name="Todo App")
        feature = Feature(
            project=project,
            title="Deterministic tests and build script",
            status=FeatureStatus.DONE,
        )
        task = Task(
            feature=feature,
            title="Verify Deterministic tests and build script for shipping",
            status=TaskStatus.IMPLEMENTATION,
        )
        db.add_all([session, project, feature, task])
        await db.commit()

    payload = await realtime._get_builder_status(app)

    assert payload["board_status"]["backlog_status"]["feature_count"] == 1
    assert payload["board_status"]["backlog_status"]["open_count"] == 0
    assert payload["board_status"]["queued_count"] == 1
    assert "Backlog features are complete" in payload["voice_digest"]
    assert "queued board task" in payload["voice_digest"]


@pytest.mark.asyncio
async def test_get_builder_status_reports_recent_provider_limit_run(test_db, tmp_path: Path):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        project = Project(name="sample-app")
        feature = Feature(project=project, title="Build verification")
        task = Task(
            feature=feature,
            title="Verify deterministic build",
            status=TaskStatus.IMPLEMENTATION,
        )
        db.add_all([session, project, feature, task])
        await db.flush()
        db.add(
            AgentRun(
                task_id=task.id,
                agent_name="code-gen",
                runtime_sdk="claude",
                provider="claude_agent_sdk",
                model="sonnet",
                stop_reason="provider_limit",
                status="completed",
            )
        )
        await db.commit()

    payload = await realtime._get_builder_status(app)

    assert payload["board_status"]["blocked_count"] == 0
    assert payload["board_status"]["provider_limit_count"] == 1
    assert payload["current_runtime"]["sdk"] == "claude"
    assert payload["board_status"]["provider_limit_runs"][0]["task_title"] == (
        "Verify deterministic build"
    )
    assert "Builder hit a provider limit recently" in payload["voice_digest"]
    assert "provider_limit" in payload["voice_digest"]
    assert "Board task is currently implementation" in payload["voice_digest"]


@pytest.mark.asyncio
async def test_get_builder_status_does_not_report_stale_provider_limit_as_current(
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        project = Project(name="sample-app")
        feature = Feature(project=project, title="Build verification")
        task = Task(
            feature=feature,
            title="Verify deterministic build",
            status=TaskStatus.CAPABILITY_LIMIT,
            capability_limit_reason="SDK limit: provider_limit",
            blocked_reason=(
                "provider limit blocked: reset_at=2026-05-09T01:00:00+00:00; "
                "builder will resume at implementation."
            ),
        )
        db.add_all([session, project, feature, task])
        await db.flush()
        db.add(
            AgentRun(
                task_id=task.id,
                agent_name="code-gen",
                runtime_sdk="claude",
                provider="claude_agent_sdk",
                model="sonnet",
                stop_reason="provider_limit",
                status="completed",
                completed_at=datetime.now(UTC) - timedelta(days=2),
            )
        )
        await db.commit()

    payload = await realtime._get_builder_status(app)

    assert payload["board_status"]["blocked_count"] == 1
    assert payload["board_status"]["provider_limit_runs"][0]["provider_limit_current"] is False
    assert "stale provider-limit Board block" in payload["voice_digest"]
    assert "not evidence of a current Claude rate limit" in payload["voice_digest"]


@pytest.mark.asyncio
async def test_get_builder_status_includes_pending_approval_context(test_db, tmp_path: Path):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        db.add(
            ChatEvent(
                session_id=session.id,
                event_type="tool_approval_request",
                status="pending",
                payload_json={
                    "summary": "Approve task dispatch",
                    "description": "Dispatch implementation task",
                    "tool_name": "mcp__builder__task_dispatch",
                    "tool_input": {"task_id": "task-123"},
                },
            )
        )
        await db.commit()

    payload = await realtime._get_builder_status(app)

    item = payload["pending_operator_items"][0]
    assert item["type"] == "tool_approval_request"
    assert item["summary"] == "Approve task dispatch"
    assert item["description"] == "Dispatch implementation task"
    assert item["tool_name"] == "mcp__builder__task_dispatch"
    assert item["decision_prompt"] == (
        "Ask the operator whether to approve or deny this pending tool request."
    )
    assert item["tool_input_summary"] == '{"task_id": "task-123"}'


@pytest.mark.asyncio
async def test_get_builder_status_includes_prepared_voice_action_context(test_db, tmp_path: Path):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        db.add(
            ChatEvent(
                session_id=session.id,
                event_type="voice_action_prepared",
                status="pending",
                payload_json={
                    "action_kind": "recovery",
                    "consequence_summary": "Recover blocked Board task.",
                    "confirmation_phrase": "Confirm recovery for task task-123.",
                },
            )
        )
        await db.commit()

    payload = await realtime._get_builder_status(app)

    item = payload["pending_operator_items"][0]
    assert item["type"] == "voice_action_prepared"
    assert item["summary"] == "Recover blocked Board task."
    assert item["action_kind"] == "recovery"
    assert item["decision_prompt"] == (
        "Ask the operator whether to confirm or cancel this prepared voice action."
    )


@pytest.mark.asyncio
async def test_get_builder_status_includes_pending_question_options(test_db, tmp_path: Path):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        db.add(
            ChatEvent(
                session_id=session.id,
                event_type="ask_user_question",
                status="pending",
                payload_json={
                    "question": "Which stack should Builder use?",
                    "options": [
                        {
                            "label": "React (Recommended)",
                            "description": "Best fit for this generated app.",
                        },
                        {
                            "label": "Vue",
                            "description": "Use only if the operator prefers Vue.",
                        },
                    ],
                    "recommended_index": 0,
                },
            )
        )
        await db.commit()

    payload = await realtime._get_builder_status(app)

    item = payload["pending_operator_items"][0]
    assert item["type"] == "ask_user_question"
    assert item["question"] == "Which stack should Builder use?"
    assert item["options"] == [
        {
            "label": "React (Recommended)",
            "description": "Best fit for this generated app.",
        },
        {"label": "Vue", "description": "Use only if the operator prefers Vue."},
    ]
    assert item["recommended_index"] == 0
    assert item["recommended_option"]["label"] == "React (Recommended)"


@pytest.mark.asyncio
async def test_pending_approval_prompt_records_voice_reminder(test_db, tmp_path: Path):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        db.add(
            ChatEvent(
                session_id=session.id,
                event_type="tool_approval_request",
                status="pending",
                payload_json={
                    "summary": "Approve task dispatch",
                    "description": "Dispatch implementation task",
                    "tool_name": "mcp__builder__task_dispatch",
                },
            )
        )
        await db.commit()

    reminder = await AgentOperatorService(app).pending_approval_prompt(
        active_session_id=session.id,
        call_id="rtc_prompt",
    )

    assert reminder is not None
    assert reminder["pending_approval_count"] == 1
    assert "Say approve or deny" in reminder["prompt"]
    async with factory() as db:
        event_result = await db.execute(
            select(ChatEvent)
            .where(ChatEvent.event_type == "voice_approval_prompt")
            .order_by(ChatEvent.created_at.asc())
        )
        prompt_event = event_result.scalar_one()
    assert prompt_event.payload_json["voice_call_id"] == "rtc_prompt"
    assert prompt_event.payload_json["pending_item"]["type"] == "tool_approval_request"


@pytest.mark.asyncio
async def test_delegate_status_request_is_guarded_as_direct_realtime_status(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async def fail_run_chat_turn(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("read-only voice status must not delegate to SDK-backed Agent")

    monkeypatch.setattr(agent_routes, "_run_chat_turn", fail_run_chat_turn)

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        project = Project(name="Todo App")
        feature = Feature(project=project, title="Deterministic shipping")
        task = Task(
            feature=feature,
            title="Verify Deterministic tests and build script for shipping",
            status=TaskStatus.CAPABILITY_LIMIT,
            phase=TaskPhase.IMPLEMENTATION,
            capability_limit_reason="SDK limit: provider_limit",
        )
        sprint_1 = Sprint(project=project, label="Sprint 1", generated_task_ids=[task.id])
        sprint_2 = Sprint(project=project, label="Sprint 2", generated_task_ids=[])
        db.add_all([session, project, feature, task, sprint_1, sprint_2])
        await db.commit()

    result = await realtime._handle_tool_call(
        app,
        {
            "name": "delegate_to_builder_agent",
            "arguments": json.dumps(
                {
                    "message": "Check how many sprints there are.",
                    "thread_mode": "current",
                    "routing_reason": "mistaken model delegation for sprint count",
                }
            ),
        },
    )

    assert result["ok"] is True
    assert result["result"]["status"] == "read_only_status"
    assert result["result"]["completion_status"] == "direct_status"
    assert result["result"]["voice_route"]["route"] == "status"
    board_status = result["result"]["builder_status"]["board_status"]
    assert board_status["sprint_count"] == 2
    assert board_status["blocked_count"] == 1
    assert board_status["blocked_tasks"][0]["title"] == (
        "Verify Deterministic tests and build script for shipping"
    )
    async with factory() as db:
        event_result = await db.execute(
            select(ChatEvent).where(
                ChatEvent.event_type.in_(("voice_operator_message", "user_message"))
            )
        )
        events = list(event_result.scalars().all())
    assert events == []


@pytest.mark.asyncio
async def test_delegate_request_reports_provider_limit_blocker_without_agent_run(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async def fail_run_chat_turn(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("provider-limited voice work must not delegate")

    monkeypatch.setattr(agent_routes, "_run_chat_turn", fail_run_chat_turn)

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        project = Project(name="Todo App")
        feature = Feature(project=project, title="Build verification")
        task = Task(
            feature=feature,
            title="Verify deterministic build",
            status=TaskStatus.IMPLEMENTATION,
        )
        db.add_all([session, project, feature, task])
        await db.flush()
        db.add(
            AgentRun(
                task_id=task.id,
                agent_name="code-gen",
                runtime_sdk="claude",
                provider="claude_agent_sdk",
                model="sonnet",
                stop_reason="provider_limit",
                status="completed",
            )
        )
        await db.commit()

    result = await realtime._handle_tool_call(
        app,
        {
            "name": "delegate_to_builder_agent",
            "arguments": json.dumps(
                {
                    "message": "Please fix the generated app build failure.",
                    "thread_mode": "new",
                    "routing_reason": "voice requested generated-app work",
                }
            ),
        },
    )

    assert result["ok"] is True
    payload = result["result"]
    assert payload["status"] == "capability_blocked"
    assert payload["completion_status"] == "capability_blocked"
    assert payload["capability_decision"]["decision"] == "blocked"
    assert payload["capability_decision"]["voice_action"] == "report_blocker"
    assert payload["capability_decision"]["can_execute_now"] is False
    assert payload["capability_decision"]["builder_route"] == "agent_chat"
    assert "provider_limit" in payload["capability_decision"]["blocker"]
    assert "cannot delegate" in payload["operator_message"]
    async with factory() as db:
        event_result = await db.execute(
            select(ChatEvent).where(
                ChatEvent.event_type.in_(("voice_operator_message", "user_message"))
            )
        )
        events = list(event_result.scalars().all())
    assert events == []


@pytest.mark.asyncio
async def test_delegate_request_reports_unsupported_without_agent_run(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async def fail_run_chat_turn(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("unsupported voice request must not delegate")

    monkeypatch.setattr(agent_routes, "_run_chat_turn", fail_run_chat_turn)

    result = await realtime._handle_tool_call(
        app,
        {
            "name": "delegate_to_builder_agent",
            "arguments": json.dumps(
                {
                    "message": "Book a flight to Paris tomorrow.",
                    "thread_mode": "new",
                    "routing_reason": "unsupported operator request",
                }
            ),
        },
    )

    assert result["ok"] is True
    payload = result["result"]
    assert payload["status"] == "unsupported_request"
    assert payload["completion_status"] == "unsupported_request"
    assert payload["capability_decision"] == {
        "decision": "unsupported",
        "voice_action": "report_unsupported",
        "builder_route": "none",
        "can_execute_now": False,
        "blocker": "unsupported_operator_request",
        "operator_message": (
            "Neither Realtime voice nor Builder can do that right now. I can "
            "help with Builder status, approvals, recovery, and software "
            "delivery work."
        ),
        "evidence_refs": ["voice_capability.unsupported_phrase"],
    }
    async with factory() as db:
        event_result = await db.execute(select(ChatEvent))
        events = list(event_result.scalars().all())
    assert events == []


@pytest.mark.asyncio
async def test_send_agent_message_uses_existing_agent_chat_path(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )

    async def fake_run_chat_turn(app_arg: Any, session_id: str, message: str) -> None:
        assert app_arg is app
        assert message == "Plan the next sprint"
        async with factory() as db:
            db.add(
                ChatEvent(
                    session_id=session_id,
                    event_type="voice_final_summary",
                    status="completed",
                    payload_json={"summary": "Sprint plan is ready."},
                )
            )
            await db.commit()

    monkeypatch.setattr(agent_routes, "_run_chat_turn", fake_run_chat_turn)

    result = await realtime._handle_tool_call(
        app,
        {
            "name": "send_agent_message",
            "arguments": '{"message": "Plan the next sprint"}',
        },
    )

    assert result["ok"] is True
    session_id = result["result"]["session_id"]
    async with factory() as db:
        event_result = await db.execute(select(ChatEvent).where(ChatEvent.session_id == session_id))
        events = list(event_result.scalars().all())

    user_events = [event for event in events if event.event_type == "user_message"]
    voice_events = [event for event in events if event.event_type == "voice_operator_message"]
    assert voice_events
    assert voice_events[0].payload_json["speaker"] == "operator"
    assert voice_events[0].payload_json["target"] == "realtime_voice_ai"
    assert user_events
    assert user_events[0].payload_json["content"] == "Plan the next sprint"
    assert user_events[0].payload_json["source"] == "realtime_voice"
    assert user_events[0].payload_json["speaker"] == "realtime_voice_ai"
    assert user_events[0].payload_json["target"] == "sdk_backed_agent"
    assert user_events[0].payload_json["thread_mode"] == "new"
    assert result["result"]["completion_status"] == "completed"
    assert (
        result["result"]["completion_digest"]["voice_digest"]
        == "Builder finished: Sprint plan is ready."
    )


@pytest.mark.asyncio
async def test_voice_delegation_can_continue_current_or_start_new_agent_threads(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )
    captured: list[tuple[str, str]] = []

    async def fake_run_chat_turn(app_arg: Any, session_id: str, message: str) -> None:
        assert app_arg is app
        captured.append((session_id, message))

    monkeypatch.setattr(agent_routes, "_run_chat_turn", fake_run_chat_turn)
    monkeypatch.setattr(VoiceCompletionNotifier, "schedule", lambda *args: None)

    async with factory() as db:
        existing = ChatSession()
        agent_chat_sessions.stamp_session_scope(existing, tmp_path)
        db.add(existing)
        await db.flush()
        db.add(
            ChatEvent(
                session_id=existing.id,
                event_type="user_message",
                status="completed",
                payload_json={"content": "Existing topic", "source": "operator"},
            )
        )
        await db.commit()
        existing_id = existing.id

    current_result = await realtime._handle_tool_call(
        app,
        {
            "name": "delegate_to_builder_agent",
            "arguments": json.dumps(
                {
                    "message": "Continue checking the current task",
                    "thread_mode": "current",
                    "routing_reason": "operator follow-up",
                }
            ),
        },
    )
    new_result = await realtime._handle_tool_call(
        app,
        {
            "name": "delegate_to_builder_agent",
            "arguments": json.dumps(
                {
                    "message": "Investigate a separate runtime policy issue",
                    "thread_mode": "new",
                    "routing_reason": "distinct topic",
                }
            ),
        },
    )
    await asyncio.sleep(0)

    assert current_result["result"]["session_id"] == existing_id
    assert current_result["result"]["thread_mode"] == "current"
    assert new_result["result"]["session_id"] != existing_id
    assert new_result["result"]["thread_mode"] == "new"
    assert captured == [
        (existing_id, "Continue checking the current task"),
        (new_result["result"]["session_id"], "Investigate a separate runtime policy issue"),
    ]

    async with factory() as db:
        result = await db.execute(select(ChatEvent).order_by(ChatEvent.created_at.asc()))
        events = list(result.scalars().all())

    voice_delegations = [
        event
        for event in events
        if event.event_type == "user_message"
        and event.payload_json.get("speaker") == "realtime_voice_ai"
    ]
    assert [event.payload_json["thread_mode"] for event in voice_delegations] == [
        "current",
        "new",
    ]
    assert {event.payload_json["target"] for event in voice_delegations} == {"sdk_backed_agent"}


@pytest.mark.asyncio
async def test_voice_delegation_rebinds_visible_session_without_waiting(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )
    release = asyncio.Event()

    async def fake_run_chat_turn(app_arg: Any, session_id: str, message: str) -> None:
        assert app_arg is app
        assert message == "Add text search to the todo app."
        await release.wait()

    monkeypatch.setattr(agent_routes, "_run_chat_turn", fake_run_chat_turn)

    async with factory() as db:
        voice_session = ChatSession()
        agent_chat_sessions.stamp_session_scope(voice_session, tmp_path)
        db.add(voice_session)
        await db.commit()
        voice_session_id = voice_session.id

    realtime._bind_voice_call_session(app, "rtc_delegate", voice_session_id)
    result = await asyncio.wait_for(
        realtime._handle_tool_call(
            app,
            {
                "name": "delegate_to_builder_agent",
                "arguments": json.dumps(
                    {
                        "message": "Add text search to the todo app.",
                        "thread_mode": "new",
                        "routing_reason": "operator requested a new feature",
                    }
                ),
            },
            call_id="rtc_delegate",
        ),
        timeout=1,
    )

    payload = result["result"]
    delegated_session_id = payload["session_id"]
    assert result["ok"] is True
    assert payload["completion_status"] == "running"
    assert delegated_session_id != voice_session_id
    assert realtime._voice_call_session_id(app, "rtc_delegate") == delegated_session_id

    async with factory() as db:
        old_result = await db.execute(
            select(ChatEvent)
            .where(ChatEvent.session_id == voice_session_id)
            .order_by(ChatEvent.created_at.asc())
        )
        old_events = list(old_result.scalars().all())
        new_result = await db.execute(
            select(ChatEvent)
            .where(ChatEvent.session_id == delegated_session_id)
            .order_by(ChatEvent.created_at.asc())
        )
        new_events = list(new_result.scalars().all())

    redirect = next(event for event in old_events if event.event_type == "voice_control_action")
    assert redirect.payload_json["action"] == "bind_agent_session"
    assert redirect.payload_json["session_id"] == delegated_session_id
    assert redirect.payload_json["route"] == f"/?session={delegated_session_id}&mode=chat"
    assert any(event.event_type == "voice_operator_message" for event in new_events)
    user_event = next(event for event in new_events if event.event_type == "user_message")
    assert user_event.payload_json["participant_label"] == "Samantha"

    release.set()
    await asyncio.sleep(0.2)


@pytest.mark.asyncio
async def test_sdk_agent_completion_persists_voice_final_summary_for_realtime(
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )
    long_tool_heavy_response = (
        "I inspected the board, checked the runtime settings, reviewed logs, and verified the "
        "handoff. Final result: runtime switching is future-run-only and historical task "
        "attribution remains visible. Raw tool call detail should not be spoken."
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        db.add(
            ChatEvent(
                session_id=session.id,
                event_type="user_message",
                status="completed",
                payload_json={
                    "content": "Check runtime switching",
                    "source": "realtime_voice",
                    "speaker": "realtime_voice_ai",
                    "target": "sdk_backed_agent",
                },
            )
        )
        assistant = ChatEvent(
            session_id=session.id,
            event_type="assistant_message",
            status="completed",
            payload_json={"content": long_tool_heavy_response, "final": True},
        )
        db.add(assistant)
        await db.commit()
        session_id = session.id
        assistant_id = assistant.id

    event = await agent_routes._append_voice_final_summary_if_needed(
        session_id,
        assistant_event_id=assistant_id,
        content=long_tool_heavy_response,
        hub=app.state.chat_hub,
    )

    assert event is not None
    assert event.event_type == "voice_final_summary"
    assert event.payload_json["source"] == "sdk_backed_agent"
    assert event.payload_json["target"] == "realtime_voice_ai"
    assert event.payload_json["assistant_event_id"] == assistant_id
    assert event.payload_json["spoken_summary"] == event.payload_json["summary"]
    assert event.payload_json["outcome"] == "completed"
    assert event.payload_json["evidence_refs"] == [
        {
            "kind": "agent_event",
            "id": assistant_id,
            "summary": "SDK-backed Agent final response",
        }
    ]
    assert event.payload_json["read_policy"] == "realtime_voice_reads_summary_only_not_tool_calls"
    assert "runtime switching is future-run-only" in event.payload_json["summary"]

    status = await realtime._get_builder_status(app)
    assert status["latest_voice_summary"]["event_id"] == event.id
    assert status["latest_voice_summary"]["assistant_event_id"] == assistant_id
    assert "Builder is idle. Last Agent result:" in status["voice_digest"]
    assert "runtime switching is future-run-only" in status["voice_digest"]

    completion_status = await realtime._get_builder_status(app, prefer_latest_summary=True)
    assert "Builder finished:" in completion_status["voice_digest"]
    assert "runtime switching is future-run-only" in completion_status["voice_digest"]


@pytest.mark.asyncio
async def test_voice_completion_notifier_persists_digest_after_nonblocking_delegation(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async def fake_run_chat_turn(app_arg: Any, session_id: str, message: str) -> None:
        assert app_arg is app
        assert message == "Verify the current build"
        await asyncio.sleep(0.01)
        async with factory() as db:
            db.add(
                ChatEvent(
                    session_id=session_id,
                    event_type="assistant_message",
                    status="completed",
                    payload_json={"content": "Verification passed with deterministic evidence."},
                )
            )
            await db.commit()

    monkeypatch.setattr(agent_routes, "_run_chat_turn", fake_run_chat_turn)

    result = await realtime._handle_tool_call(
        app,
        {
            "name": "delegate_to_builder_agent",
            "arguments": json.dumps(
                {
                    "message": "Verify the current build",
                    "wait_for_completion": False,
                }
            ),
        },
    )

    assert result["ok"] is True
    assert result["result"]["completion_status"] == "running"
    assert result["result"]["completion_notification"]["mode"] == "event_driven"
    await asyncio.sleep(0.1)

    session_id = result["result"]["session_id"]
    async with factory() as db:
        event_result = await db.execute(
            select(ChatEvent)
            .where(ChatEvent.session_id == session_id)
            .order_by(ChatEvent.created_at.asc())
        )
        events = list(event_result.scalars().all())

    digest = next(event for event in events if event.event_type == "voice_final_summary")
    notification = next(
        event for event in events if event.event_type == "voice_completion_notification"
    )
    assert (
        digest.payload_json["spoken_summary"] == "Verification passed with deterministic evidence."
    )
    assert digest.payload_json["completion_trigger"] == "agent_task_done_callback"
    assert digest.payload_json["evidence_refs"][0]["kind"] == "agent_event"
    assert notification.payload_json["voice_final_summary_event_id"] == digest.id
    assert notification.payload_json["trigger"] == "agent_task_done_callback"


@pytest.mark.asyncio
async def test_recover_blocked_run_without_board_target_reports_not_recoverable(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async def fake_run_chat_turn(app_arg: Any, session_id: str, message: str) -> None:
        raise AssertionError("Board recovery must not fabricate an Agent-page recovery run")

    monkeypatch.setattr(agent_routes, "_run_chat_turn", fake_run_chat_turn)

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        db.add(
            ChatEvent(
                session_id=session.id,
                event_type="run_error",
                status="completed",
                payload_json={"content": "Provider limit blocked this run"},
            )
        )
        await db.commit()

    result = await realtime._handle_tool_call(
        app,
        {
            "name": "recover_blocked_run",
            "arguments": (
                '{"session_id": "'
                + session.id
                + '", "recovery_request": "retry after quota reset"}'
            ),
        },
    )

    assert result["ok"] is True
    await asyncio.sleep(0)
    assert result["result"]["session_id"] == session.id
    assert result["result"]["status"] == "not_recoverable"
    assert result["result"]["requires_confirmation"] is False
    assert "No blocked, failed, or capability-limited Board task" in result["result"]["message"]
    assert result["result"]["recommended_tool"] == "open_run_trace"


@pytest.mark.asyncio
async def test_delegate_recovery_without_board_target_does_not_prepare_approval(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async def fake_run_chat_turn(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Realtime recovery without Board target must not delegate")

    monkeypatch.setattr(agent_routes, "_run_chat_turn", fake_run_chat_turn)

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        db.add(
            ChatEvent(
                session_id=session.id,
                event_type="run_status",
                status="completed",
                payload_json={"stop_reason": "deterministic_recovery_preflight"},
            )
        )
        await db.commit()

    result = await realtime._handle_tool_call(
        app,
        {
            "name": "delegate_to_builder_agent",
            "arguments": json.dumps(
                {
                    "message": "Identify and recover the last failed run.",
                    "thread_mode": "new",
                    "routing_reason": "recover the last failed run",
                }
            ),
        },
    )

    assert result["ok"] is True
    payload = result["result"]
    assert payload["status"] == "not_recoverable"
    assert payload["completion_status"] == "not_recoverable"
    assert payload["capability_decision"]["decision"] == "not_recoverable"
    assert payload["capability_decision"]["can_execute_now"] is False
    assert "recoverable Board task" in payload["operator_message"]


@pytest.mark.asyncio
async def test_voice_tool_output_persists_terminal_recovery_evidence(test_db, tmp_path: Path):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    await VoiceOperatorService(app).record_tool_event(
        "voice_tool_output",
        "rtc_recovery_evidence",
        {
            "name": "delegate_to_builder_agent",
            "call_id": "call_recovery",
        },
        output={
            "ok": True,
            "result": {
                "status": "not_recoverable",
                "completion_status": "not_recoverable",
                "operator_message": (
                    "No recoverable Board task is currently blocked, failed, or capability-limited."
                ),
                "recommended_tool": "open_run_trace",
                "capability_decision": {"decision": "not_recoverable"},
            },
        },
    )

    async with factory() as db:
        result = await db.execute(select(ChatEvent).order_by(ChatEvent.created_at.desc()))
        event = result.scalars().first()

    assert event is not None
    assert event.event_type == "voice_tool_output"
    payload = event.payload_json
    assert payload["tool_name"] == "delegate_to_builder_agent"
    assert payload["ok"] is True
    assert payload["result_status"] == "not_recoverable"
    assert payload["completion_status"] == "not_recoverable"
    assert payload["capability_decision"] == "not_recoverable"
    assert payload["recommended_tool"] == "open_run_trace"
    assert "No recoverable Board task" in payload["result_message"]


@pytest.mark.asyncio
async def test_recover_blocked_run_prepares_then_confirms_board_task_recovery(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async def fail_run_chat_turn(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("blocked Board recovery must not delegate to free-form chat")

    monkeypatch.setattr(agent_routes, "_run_chat_turn", fail_run_chat_turn)

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        project = Project(name="Todo App")
        feature = Feature(project=project, title="Deterministic shipping")
        task = Task(
            feature=feature,
            title="Verify Deterministic tests and build script for shipping",
            status=TaskStatus.CAPABILITY_LIMIT,
            phase=TaskPhase.IMPLEMENTATION,
            capability_limit_reason="SDK provider limit",
            blocked_reason=(
                "provider limit blocked: reset_at=2026-05-09T01:00:00+00:00; "
                "builder will resume at implementation."
            ),
        )
        db.add_all([session, project, feature, task])
        await db.commit()
        session_id = session.id
        task_id = task.id

    result = await realtime._handle_tool_call(
        app,
        {
            "name": "recover_blocked_run",
            "arguments": json.dumps(
                {
                    "session_id": session_id,
                    "recovery_request": (
                        "Recover the blocked task: Verify Deterministic tests and "
                        "build script for shipping. The reason is SDK provider limit."
                    ),
                }
            ),
        },
    )

    assert result["ok"] is True
    assert result["result"]["status"] == "confirmation_required"
    assert result["result"]["requires_confirmation"] is True
    assert result["result"]["task"]["id"] == task_id
    assert result["result"]["matched_on"] == "title"

    async with factory() as db:
        still_blocked = await db.get(Task, task_id)
        prepared = await db.get(ChatEvent, result["result"]["action_id"])
    assert still_blocked is not None
    assert still_blocked.status == TaskStatus.CAPABILITY_LIMIT
    assert prepared is not None
    assert prepared.event_type == "voice_action_prepared"
    assert prepared.status == "pending"
    assert prepared.payload_json["action_kind"] == "recovery"
    assert prepared.payload_json["target_entity_id"] == task_id

    confirmed = await realtime._confirm_high_risk_action(
        app,
        {
            "action_id": result["result"]["action_id"],
            "transcript_excerpt": "Confirm recovery for this blocked task.",
        },
    )

    assert confirmed["status"] == "recovered_blocked_task"
    assert confirmed["recovery"]["current_status"] == "implementation"

    async with factory() as db:
        recovered = await db.get(Task, task_id)
        prepared_after = await db.get(ChatEvent, result["result"]["action_id"])
        event_result = await db.execute(select(ChatEvent).order_by(ChatEvent.created_at.asc()))
        events = list(event_result.scalars().all())
    assert recovered is not None
    assert recovered.status == TaskStatus.IMPLEMENTATION
    assert recovered.blocked_reason is None
    assert recovered.capability_limit_reason is None
    assert prepared_after is not None
    assert prepared_after.status == "answered"
    assert prepared_after.payload_json["prepared_status"] == "executed"
    assert not any(event.event_type == "tool_approval_request" for event in events)
    tool_event = next(event for event in events if event.event_type == "tool_result")
    assert tool_event.payload_json["tool_name"] == "recover_blocked_run"
    assert "Verify Deterministic tests" in tool_event.payload_json["diagnostic"]


@pytest.mark.asyncio
async def test_recover_board_task_recovers_without_confirmation_for_one_step_voice_control(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async def fail_run_chat_turn(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("direct Board recovery must not delegate to SDK chat")

    monkeypatch.setattr(agent_routes, "_run_chat_turn", fail_run_chat_turn)

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        project = Project(name="Todo App")
        feature = Feature(
            project=project,
            title="Deterministic shipping",
            status=FeatureStatus.QUEUED,
        )
        task = Task(
            feature=feature,
            title="Verify Deterministic tests and build script for shipping",
            status=TaskStatus.CAPABILITY_LIMIT,
            phase=TaskPhase.IMPLEMENTATION,
            capability_limit_reason="SDK provider limit",
        )
        db.add_all([session, project, feature, task])
        await db.commit()
        session_id = session.id
        task_id = task.id

    result = await realtime._handle_tool_call(
        app,
        {
            "name": "recover_board_task",
            "arguments": json.dumps(
                {
                    "session_id": session_id,
                    "task_id": task_id,
                    "recovery_request": "recover the blocked task",
                }
            ),
        },
        call_id="rtc_recover",
    )

    assert result["ok"] is True
    payload = result["result"]
    assert payload["status"] == "recovered_board_task"
    assert payload["task_id"] == task_id
    assert payload["current_status"] == "implementation"
    assert payload["next_step"] == "dispatch_board_task"

    async with factory() as db:
        recovered = await db.get(Task, task_id)
        event_result = await db.execute(select(ChatEvent).order_by(ChatEvent.created_at.asc()))
        events = list(event_result.scalars().all())
    assert recovered is not None
    assert recovered.status == TaskStatus.IMPLEMENTATION
    assert recovered.capability_limit_reason is None
    control = next(event for event in events if event.event_type == "voice_control_action")
    assert control.payload_json["action"] == "recover_task"
    assert control.payload_json["route"] == "/board"


@pytest.mark.asyncio
async def test_dispatch_board_task_uses_board_dispatch_path_for_recovered_task(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )
    dispatched: list[str] = []

    async def fake_run_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(task_routes, "_run_dispatch", fake_run_dispatch)

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        project = Project(name="Todo App")
        feature = Feature(
            project=project,
            title="Deterministic shipping",
            status=FeatureStatus.QUEUED,
        )
        task = Task(
            feature=feature,
            title="Verify Deterministic tests and build script for shipping",
            status=TaskStatus.IMPLEMENTATION,
            phase=TaskPhase.IMPLEMENTATION,
        )
        db.add_all([session, project, feature, task])
        await db.commit()
        task_id = task.id

    result = await realtime._handle_tool_call(
        app,
        {
            "name": "dispatch_board_task",
            "arguments": json.dumps({"selection": "the recovered task"}),
        },
        call_id="rtc_dispatch",
    )
    await asyncio.sleep(0)

    assert result["ok"] is True
    payload = result["result"]
    assert payload["status"] == "dispatched"
    assert payload["task_id"] == task_id
    assert payload["route"] == "/board"
    assert dispatched == [task_id]

    async with factory() as db:
        event_result = await db.execute(
            select(ChatEvent).where(ChatEvent.event_type == "voice_control_action")
        )
        control = event_result.scalar_one()
    assert control.payload_json["action"] == "dispatch_task"
    assert control.payload_json["status"] == "dispatched"


@pytest.mark.asyncio
async def test_sideband_registers_tools_and_returns_function_output(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    class FakeRealtimeWebSocket:
        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []
            self._messages = [
                {
                    "type": "response.output_item.added",
                    "item": {
                        "type": "function_call",
                        "call_id": "call_status",
                        "name": "get_builder_status",
                        "arguments": "{}",
                    },
                },
                {
                    "type": "response.done",
                    "response": {
                        "output": [
                            {
                                "type": "function_call",
                                "call_id": "call_status",
                                "name": "get_builder_status",
                                "arguments": "{}",
                            }
                        ]
                    },
                },
                {
                    "type": "response.done",
                    "response": {
                        "output": [
                            {
                                "type": "function_call",
                                "call_id": "call_status",
                                "name": "get_builder_status",
                                "arguments": "{}",
                            }
                        ]
                    },
                },
            ]

        async def __aenter__(self) -> FakeRealtimeWebSocket:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def send(self, message: str) -> None:
            self.sent.append(json.loads(message))

        def __aiter__(self) -> FakeRealtimeWebSocket:
            return self

        async def __anext__(self) -> str:
            if not self._messages:
                raise StopAsyncIteration
            return json.dumps(self._messages.pop(0))

    class FakeWebsocketsModule:
        def __init__(self) -> None:
            self.ws = FakeRealtimeWebSocket()
            self.url = ""
            self.additional_headers: dict[str, str] = {}

        def connect(self, url: str, *, additional_headers: dict[str, str]):
            self.url = url
            self.additional_headers = additional_headers
            return self.ws

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    fake_websockets = FakeWebsocketsModule()
    monkeypatch.setitem(sys.modules, "websockets", fake_websockets)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    await realtime._run_sideband(app, "rtc_test_call")

    assert fake_websockets.url.endswith("call_id=rtc_test_call")
    assert fake_websockets.additional_headers == {"Authorization": "Bearer test-key"}
    assert fake_websockets.ws.sent[0]["type"] == "session.update"
    assert fake_websockets.ws.sent[0]["session"]["tools"] == realtime.TOOL_DEFINITIONS
    assert fake_websockets.ws.sent[1]["type"] == "conversation.item.create"
    assert fake_websockets.ws.sent[1]["item"]["call_id"] == "call_status"
    assert json.loads(fake_websockets.ws.sent[1]["item"]["output"])["ok"] is True
    assert fake_websockets.ws.sent[2] == {"type": "response.create"}

    _, factory = test_db
    async with factory() as db:
        event_result = await db.execute(select(ChatEvent).order_by(ChatEvent.created_at.asc()))
        events = list(event_result.scalars().all())
    event_types = [event.event_type for event in events]
    assert "voice_tool_call" in event_types
    assert "voice_digest" in event_types
    assert "voice_tool_output" in event_types
    tool_call = next(event for event in events if event.event_type == "voice_tool_call")
    tool_output = next(event for event in events if event.event_type == "voice_tool_output")
    assert tool_call.payload_json["voice_call_id"] == "rtc_test_call"
    assert tool_call.payload_json["tool_name"] == "get_builder_status"
    assert tool_output.payload_json["tool_name"] == "get_builder_status"
    assert tool_output.payload_json["ok"] is True
    assert event_types.count("voice_tool_call") == 1
    assert event_types.count("voice_tool_output") == 1


@pytest.mark.asyncio
async def test_sideband_wait_for_user_stays_silent_after_tool_output(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    class FakeConnectionClosedError(Exception):
        pass

    class FakeRealtimeWebSocket:
        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []
            self._messages = [
                {
                    "type": "response.done",
                    "response": {
                        "output": [
                            {
                                "type": "function_call",
                                "call_id": "call_wait",
                                "name": "wait_for_user",
                                "arguments": '{"reason":"background audio"}',
                            }
                        ]
                    },
                }
            ]

        async def __aenter__(self) -> FakeRealtimeWebSocket:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def send(self, message: str) -> None:
            self.sent.append(json.loads(message))

        async def __anext__(self) -> str:
            if not self._messages:
                raise StopAsyncIteration
            return json.dumps(self._messages.pop(0))

    class FakeWebsocketsModule:
        exceptions = type(
            "FakeWebsocketsExceptions",
            (),
            {"ConnectionClosed": FakeConnectionClosedError},
        )

        def __init__(self) -> None:
            self.ws = FakeRealtimeWebSocket()

        def connect(self, _url: str, *, additional_headers: dict[str, str]):
            return self.ws

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    fake_websockets = FakeWebsocketsModule()
    monkeypatch.setitem(sys.modules, "websockets", fake_websockets)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    await realtime._run_sideband(app, "rtc_wait_call")

    assert fake_websockets.ws.sent[0]["type"] == "session.update"
    assert fake_websockets.ws.sent[1]["type"] == "conversation.item.create"
    assert fake_websockets.ws.sent[1]["item"]["call_id"] == "call_wait"
    assert not any(item.get("type") == "response.create" for item in fake_websockets.ws.sent)


@pytest.mark.asyncio
async def test_sideband_stays_silent_for_pending_approval_without_operator_input(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    class FakeRealtimeWebSocket:
        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []

        async def __aenter__(self) -> FakeRealtimeWebSocket:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def send(self, message: str) -> None:
            payload = json.loads(message)
            self.sent.append(payload)

        def __aiter__(self) -> FakeRealtimeWebSocket:
            return self

        async def __anext__(self) -> str:
            raise StopAsyncIteration

    class FakeWebsocketsModule:
        exceptions = type(
            "FakeWebsocketsExceptions",
            (),
            {"ConnectionClosed": RuntimeError},
        )

        def __init__(self) -> None:
            self.ws = FakeRealtimeWebSocket()

        def connect(self, _url: str, *, additional_headers: dict[str, str]):
            return self.ws

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    fake_websockets = FakeWebsocketsModule()
    monkeypatch.setitem(sys.modules, "websockets", fake_websockets)

    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )
    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        db.add(
            ChatEvent(
                session_id=session.id,
                event_type="tool_approval_request",
                status="pending",
                payload_json={"summary": "Approve sprint dispatch"},
            )
        )
        await db.commit()
    realtime._bind_voice_call_session(app, "rtc_prompt_call", session.id)

    await realtime._run_sideband(app, "rtc_prompt_call")

    assert fake_websockets.ws.sent == [
        {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "instructions": realtime.VOICE_OPERATOR_INSTRUCTIONS,
                "tools": realtime.TOOL_DEFINITIONS,
                "tool_choice": "auto",
            },
        }
    ]
    async with factory() as db:
        event_result = await db.execute(
            select(ChatEvent).where(ChatEvent.event_type == "voice_approval_prompt")
        )
        assert event_result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_sideband_connection_close_is_clean_shutdown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    class FakeConnectionClosedError(Exception):
        pass

    class FakeRealtimeWebSocket:
        async def __aenter__(self) -> FakeRealtimeWebSocket:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def send(self, _message: str) -> None:
            return None

        def __aiter__(self) -> FakeRealtimeWebSocket:
            return self

        async def __anext__(self) -> str:
            raise FakeConnectionClosedError("no close frame received or sent")

    class FakeWebsocketsModule:
        exceptions = type(
            "FakeWebsocketsExceptions",
            (),
            {"ConnectionClosed": FakeConnectionClosedError},
        )

        def connect(self, _url: str, *, additional_headers: dict[str, str]):
            return FakeRealtimeWebSocket()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "websockets", FakeWebsocketsModule())
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    try:
        await realtime._run_sideband(app, "rtc_closed_call")
    finally:
        await close_db()


def test_realtime_tool_calls_only_extract_completed_argument_events():
    in_progress = {
        "type": "response.output_item.added",
        "item": {
            "type": "function_call",
            "name": "delegate_to_builder_agent",
            "call_id": "call_1",
            "arguments": "{}",
        },
    }
    done = {
        "type": "response.done",
        "response": {
            "output": [
                {
                    "type": "function_call",
                    "name": "delegate_to_builder_agent",
                    "call_id": "call_1",
                    "arguments": '{"message":"status"}',
                }
            ]
        },
    }

    assert realtime._extract_tool_calls(in_progress) == []
    assert realtime._extract_tool_calls(done)[0]["arguments"] == '{"message":"status"}'


@pytest.mark.asyncio
async def test_pending_question_tool_updates_existing_event_shape(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async def fake_continue(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(agent_routes, "_continue_after_persisted_response", fake_continue)

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        event = ChatEvent(
            session_id=session.id,
            event_type="ask_user_question",
            status="pending",
            payload_json={"question": "Which option?"},
        )
        db.add(event)
        await db.commit()

    result = await realtime._answer_pending_question(
        app,
        {"session_id": session.id, "event_id": event.id, "answer": "Use the recommended scope"},
    )

    assert result["answered"] is True
    async with factory() as db:
        updated = await db.get(ChatEvent, event.id)
    assert updated is not None
    assert updated.status == "answered"
    assert updated.payload_json["answered"] is True
    assert updated.payload_json["answer"] == "Use the recommended scope"
    assert updated.payload_json["answer_value"] == "Use the recommended scope"


@pytest.mark.asyncio
async def test_voice_delegation_routes_natural_answer_to_single_pending_question(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async def fake_continue(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(agent_routes, "_continue_after_persisted_response", fake_continue)

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        event = ChatEvent(
            session_id=session.id,
            event_type="ask_user_question",
            status="pending",
            payload_json={
                "question": "Which stack?",
                "summary": "Stack decision",
                "options": [
                    {
                        "label": "React (Recommended)",
                        "description": "Best fit for this generated app.",
                    },
                    {"label": "Vue", "description": "Use only if requested."},
                ],
                "recommended_index": 0,
            },
        )
        db.add(event)
        await db.commit()

    result = await realtime._send_agent_message(app, {"message": "Use the recommended one."})

    assert result["status"] == "answered_pending_question"
    assert result["voice_route"]["route"] == "answer_pending"
    assert result["result"]["event_id"] == event.id
    async with factory() as db:
        updated = await db.get(ChatEvent, event.id)
    assert updated is not None
    assert updated.status == "answered"
    assert updated.payload_json["answer"] == "Use the recommended one."
    assert updated.payload_json["answer_value"] == "React (Recommended)"


@pytest.mark.asyncio
async def test_voice_delegation_clarifies_multiple_pending_questions(
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        db.add_all(
            [
                ChatEvent(
                    session_id=session.id,
                    event_type="ask_user_question",
                    status="pending",
                    payload_json={"question": "Which stack?"},
                ),
                ChatEvent(
                    session_id=session.id,
                    event_type="ask_user_question",
                    status="pending",
                    payload_json={"question": "Which storage?"},
                ),
            ]
        )
        await db.commit()

    result = await realtime._send_agent_message(app, {"message": "Use the recommended one."})

    assert result["status"] == "clarification_required"
    assert result["voice_route"]["route"] == "clarify"
    assert result["clarifying_question"] == "Which pending question should I answer?"


@pytest.mark.asyncio
async def test_voice_delegation_clarifies_multiple_pending_approvals(
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        db.add_all(
            [
                ChatEvent(
                    session_id=session.id,
                    event_type="tool_approval_request",
                    status="pending",
                    payload_json={"tool_name": "DispatchTask"},
                ),
                ChatEvent(
                    session_id=session.id,
                    event_type="tool_approval_request",
                    status="pending",
                    payload_json={"tool_name": "RunVerifier"},
                ),
            ]
        )
        await db.commit()

    result = await realtime._send_agent_message(app, {"message": "Approve it."})

    assert result["status"] == "clarification_required"
    assert result["voice_route"]["route"] == "clarify"
    assert result["clarifying_question"] == "Which pending approval should I use?"


@pytest.mark.asyncio
async def test_voice_delegation_prepares_single_pending_approval_from_operator_answer(
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        approval = ChatEvent(
            session_id=session.id,
            event_type="tool_approval_request",
            status="pending",
            payload_json={
                "tool_name": "mcp__builder__task_dispatch",
                "summary": "Dispatch blocked task",
                "description": "Dispatch task after recovery",
                "tool_input": {"task_id": "task-123"},
            },
        )
        db.add(approval)
        await db.commit()

    result = await realtime._send_agent_message(app, {"message": "Yes, approve it."})

    assert result["status"] == "confirmation_required"
    assert result["voice_route"]["route"] == "approval_pending"
    assert result["result"]["requires_confirmation"] is True

    async with factory() as db:
        still_pending = await db.get(ChatEvent, approval.id)
        prepared = await db.get(ChatEvent, result["result"]["action_id"])
    assert still_pending is not None
    assert still_pending.status == "pending"
    assert prepared is not None
    assert prepared.event_type == "voice_action_prepared"
    assert prepared.status == "pending"
    assert prepared.payload_json["target_event_id"] == approval.id
    assert prepared.payload_json["proposed_decision"] == "allow"


@pytest.mark.asyncio
async def test_approval_confirmation_requires_prepared_action(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    async def fake_continue(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(agent_routes, "_continue_after_persisted_response", fake_continue)

    missing = await realtime._handle_tool_call(
        app,
        {"name": "confirm_high_risk_action", "arguments": '{"action_id": "missing"}'},
    )
    assert missing["ok"] is False

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        event = ChatEvent(
            session_id=session.id,
            event_type="tool_approval_request",
            status="pending",
            payload_json={"tool_name": "DispatchTask", "summary": "Dispatch task"},
        )
        db.add(event)
        await db.commit()

    prepared = await realtime._prepare_approval_decision(
        app,
        {
            "session_id": session.id,
            "event_id": event.id,
            "decision": "deny",
            "reason": "Need design review first",
        },
    )
    assert prepared["requires_confirmation"] is True
    assert prepared["consequence_summary"] == 'Voice will deny pending approval "DispatchTask".'

    async with factory() as db:
        still_pending = await db.get(ChatEvent, event.id)
        prepared_event = await db.get(ChatEvent, prepared["action_id"])
    assert still_pending is not None
    assert still_pending.status == "pending"
    assert still_pending.payload_json.get("decision") is None
    assert prepared_event is not None
    assert prepared_event.event_type == "voice_action_prepared"
    assert prepared_event.status == "pending"
    assert prepared_event.payload_json["target_event_id"] == event.id
    assert prepared_event.payload_json["proposed_decision"] == "deny"

    confirmed = await realtime._confirm_high_risk_action(
        app,
        {"action_id": prepared["action_id"]},
    )
    assert confirmed["decision"] == "deny"

    async with factory() as db:
        updated = await db.get(ChatEvent, event.id)
        prepared_updated = await db.get(ChatEvent, prepared["action_id"])
    assert updated is not None
    assert updated.status == "answered"
    assert updated.payload_json["decision"] == "deny"
    assert prepared_updated is not None
    assert prepared_updated.status == "answered"
    assert prepared_updated.payload_json["prepared_status"] == "executed"


@pytest.mark.asyncio
async def test_prepare_high_risk_decision_delegates_non_approval_event_as_normal_work(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )
    captured: dict[str, Any] = {}

    async def fake_send_agent_message(
        self: AgentOperatorService,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        assert self.app is app
        captured.update(arguments)
        return {"session_id": arguments["session_id"], "completion_status": "completed"}

    monkeypatch.setattr(AgentOperatorService, "send_message", fake_send_agent_message)

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        assistant_event = ChatEvent(
            session_id=session.id,
            event_type="assistant_message",
            status="completed",
            payload_json={"content": "Builder can create a push notification backlog."},
        )
        db.add(assistant_event)
        await db.commit()
        session_id = session.id
        event_id = assistant_event.id

    result = await realtime._prepare_approval_decision(
        app,
        {
            "session_id": session_id,
            "event_id": event_id,
            "decision": "allow",
            "reason": "Create a backlog for push notifications with due-soon triggers.",
        },
    )

    assert result["status"] == "delegated_non_approval_request"
    assert result["delegation"]["completion_status"] == "completed"
    assert captured["session_id"] == session_id
    assert captured["thread_mode"] == "current"
    assert captured["message"] == "Create a backlog for push notifications with due-soon triggers."


@pytest.mark.asyncio
async def test_wait_for_user_persists_noop_voice_event(test_db, tmp_path: Path):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    result = await realtime._handle_tool_call(
        app,
        {"name": "wait_for_user", "arguments": '{"reason": "background audio"}'},
    )

    assert result["ok"] is True
    assert result["result"]["status"] == "waiting"
    async with factory() as db:
        event_result = await db.execute(select(ChatEvent))
        events = list(event_result.scalars().all())
    assert [event.event_type for event in events] == ["voice_wait"]
    assert events[0].payload_json["reason"] == "background audio"


@pytest.mark.asyncio
async def test_realtime_usage_events_are_persisted_and_listed(test_db, tmp_path: Path):
    _, factory = test_db
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    await realtime._record_realtime_usage(
        app,
        "rtc_test_call",
        {
            "type": "response.done",
            "response": {
                "id": "resp_123",
                "model": "gpt-realtime-mini",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 25,
                    "total_tokens": 125,
                    "input_token_details": {"audio_tokens": 80, "cached_tokens": 10},
                    "output_token_details": {"audio_tokens": 20, "text_tokens": 5},
                },
            },
        },
    )

    async with factory() as db:
        event_result = await db.execute(select(ChatEvent))
        events = list(event_result.scalars().all())
    assert [event.event_type for event in events] == ["voice_usage"]
    assert events[0].payload_json["voice_call_id"] == "rtc_test_call"
    assert events[0].payload_json["input_tokens"] == 100
    assert events[0].payload_json["audio_output_tokens"] == 20
    assert events[0].payload_json["usefulness_category"] == "useful_voice_response"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/realtime/ledger")
    assert response.status_code == 200
    payload = response.json()
    assert payload["totals"]["responses"] == 1
    assert payload["totals"]["total_tokens"] == 125
    assert payload["totals"]["useful_turns"] == 1
    assert payload["totals"]["wasted_turns"] == 0
    assert payload["totals"]["usefulness_counts"]["useful_voice_response"] == 1
    assert payload["usage"][0]["response_id"] == "resp_123"


@pytest.mark.asyncio
async def test_realtime_ledger_classifies_wasted_empty_responses(test_db, tmp_path: Path):
    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )

    await realtime._record_realtime_usage(
        app,
        "rtc_test_call",
        {
            "type": "response.done",
            "response": {
                "id": "resp_empty",
                "usage": {
                    "input_tokens": 42,
                    "output_tokens": 0,
                    "total_tokens": 42,
                },
            },
        },
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/realtime/ledger")

    assert response.status_code == 200
    payload = response.json()
    assert payload["usage"][0]["usefulness_category"] == "wasted_empty_response"
    assert payload["totals"]["useful_turns"] == 0
    assert payload["totals"]["wasted_turns"] == 1
    assert payload["totals"]["usefulness_counts"]["wasted_empty_response"] == 1


@pytest.mark.asyncio
async def test_realtime_ledger_estimates_cost_when_rate_card_is_configured(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    for name, value in {
        "BUILDER_REALTIME_INPUT_TEXT_USD_PER_MILLION": "1",
        "BUILDER_REALTIME_INPUT_AUDIO_USD_PER_MILLION": "2",
        "BUILDER_REALTIME_OUTPUT_TEXT_USD_PER_MILLION": "3",
        "BUILDER_REALTIME_OUTPUT_AUDIO_USD_PER_MILLION": "4",
        "BUILDER_REALTIME_CACHED_INPUT_USD_PER_MILLION": "5",
    }.items():
        monkeypatch.setenv(name, value)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=tmp_path,
        project_root=tmp_path,
    )
    await realtime._record_realtime_usage(
        app,
        "rtc_test_call",
        {
            "type": "response.done",
            "response": {
                "id": "resp_123",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 25,
                    "total_tokens": 125,
                    "input_token_details": {
                        "audio_tokens": 80,
                        "cached_tokens": 10,
                        "text_tokens": 5,
                    },
                    "output_token_details": {"audio_tokens": 20, "text_tokens": 5},
                },
            },
        },
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/realtime/ledger")

    assert response.status_code == 200
    totals = response.json()["totals"]
    assert totals["input_text_tokens"] == 5
    assert totals["input_audio_tokens"] == 80
    assert totals["output_text_tokens"] == 5
    assert totals["output_audio_tokens"] == 20
    assert totals["cached_tokens"] == 10
    assert totals["estimated_cost_usd"] == 0.00031
    assert totals["cost_source"] == "configured_realtime_rate_card"
