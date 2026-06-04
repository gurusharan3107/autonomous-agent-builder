"""Agent chat tool-event and stream-delta route regressions."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import (
    ChatEvent,
)
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from tests.agent_route_test_support import (
    wait_for_history_item as _wait_for_history_item,
)


@pytest.mark.asyncio
async def test_chat_turn_persists_tool_error_events(monkeypatch, test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async def fake_run_phase(self, **kwargs):
        await kwargs["on_tool_event"](
            {
                "tool_name": "mcp__builder__kb_add",
                "tool_input": {"doc_type": "feature", "title": "Broken Feature Doc"},
                "tool_response": {
                    "status": "error",
                    "error": {
                        "message": "Missing required sections for feature: Current behavior, Boundaries, Verification, Change guidance"
                    },
                },
                "tool_use_id": "toolu_123",
            }
        )
        return RunResult(
            session_id="sdk-session-logs",
            cost_usd=0.0,
            tokens_input=0,
            tokens_output=0,
            num_turns=1,
            output_text="I hit a KB validation error.",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/agent/chat", json={"message": "create KB docs"})
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        history_payload, tool_item = await _wait_for_history_item(
            client,
            session_id,
            "tool_error",
            predicate=lambda item: item["payload"].get("tool_name") == "mcp__builder__kb_add",
        )

    assert history_payload["session_id"] == session_id
    assert "Missing required sections for feature" in tool_item["payload"]["content"]
    assert tool_item["payload"]["tool_name"] == "mcp__builder__kb_add"
    assert tool_item["payload"]["diagnostic"]["outcome"] == "error"
    assert tool_item["payload"]["diagnostic"]["tool_name"] == "mcp__builder__kb_add"
    assert "doc_type=feature" in tool_item["payload"]["diagnostic"]["input_focus"]
    assert "failed" in tool_item["payload"]["diagnostic"]["summary"]

@pytest.mark.asyncio
async def test_chat_turn_accepts_codex_keyword_tool_events(monkeypatch, test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async def fake_run_phase(self, **kwargs):
        await kwargs["on_tool_event"](
            event_type="tool_use",
            tool_name="shell_command",
            tool_input={"cmd": "npm test"},
            output_preview="item/started",
        )
        return RunResult(
            session_id="sdk-session-codex-keyword-event",
            cost_usd=0.0,
            tokens_input=0,
            tokens_output=0,
            num_turns=1,
            output_text="I started the command.",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/agent/chat", json={"message": "run tests"})
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        await _wait_for_history_item(client, session_id, "assistant_message")

    async with factory() as db:
        result = await db.execute(
            select(ChatEvent).where(
                ChatEvent.session_id == session_id,
                ChatEvent.event_type == "tool_use",
            )
        )
        event = result.scalar_one()

    assert event.payload_json["tool_name"] == "shell_command"
    assert event.payload_json["tool_input"] == {"cmd": "npm test"}
    assert event.payload_json["content"] == "item/started"
    assert event.payload_json["diagnostic"]["tool_name"] == "shell_command"

@pytest.mark.asyncio
async def test_codex_chat_suppresses_draft_stream_deltas_in_agent_transcript(
    monkeypatch, test_db, tmp_path
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    release_stream = asyncio.Event()

    class FakeRuntime:
        name = "codex_sdk"
        provider = "codex_subscription"

        async def run(self, prompt, **kwargs):
            await release_stream.wait()
            await kwargs["on_chunk"]("I'll do a bounded repo/history check first.")
            return RunResult(
                session_id="codex-sdk-stream-session",
                cost_usd=0.0,
                tokens_input=8,
                tokens_output=6,
                num_turns=1,
                output_text="Do shipping/state reconciliation next.",
                stop_reason="completed",
            )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeRuntime())

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/agent/chat", json={"message": "what should I do next?"})
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        queue = await app.state.chat_hub.register_session(session_id)
        try:
            release_stream.set()
            _history_payload, assistant_item = await _wait_for_history_item(
                client, session_id, "assistant_message"
            )
            queued_events: list[dict[str, object]] = []
            while not queue.empty():
                queued_events.append(await queue.get())
        finally:
            await app.state.chat_hub.unregister_session(session_id, queue)

    assert assistant_item["payload"]["content"] == "Do shipping/state reconciliation next."
    assert all(event["data"]["type"] != "assistant_stream_delta" for event in queued_events)

@pytest.mark.asyncio
async def test_claude_chat_keeps_user_visible_stream_deltas(monkeypatch, test_db, tmp_path):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    release_stream = asyncio.Event()

    class FakeRuntime:
        name = "claude"
        provider = "claude_agent_sdk"

        async def run(self, prompt, **kwargs):
            await release_stream.wait()
            await kwargs["on_chunk"]("Streaming visible progress.")
            return RunResult(
                session_id="claude-stream-session",
                cost_usd=0.01,
                tokens_input=8,
                tokens_output=6,
                num_turns=1,
                output_text="Final assistant answer.",
                stop_reason="completed",
            )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeRuntime())

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/agent/chat", json={"message": "what should I do next?"})
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        queue = await app.state.chat_hub.register_session(session_id)
        try:
            release_stream.set()
            stream_event = None
            for _ in range(5):
                candidate = await asyncio.wait_for(queue.get(), timeout=2.0)
                if candidate["data"]["type"] == "assistant_stream_delta":
                    stream_event = candidate
                    break
            _history_payload, assistant_item = await _wait_for_history_item(
                client, session_id, "assistant_message"
            )
        finally:
            await app.state.chat_hub.unregister_session(session_id, queue)

    assert stream_event is not None
    assert stream_event["data"]["type"] == "assistant_stream_delta"
    assert stream_event["data"]["payload"]["content"] == "Streaming visible progress."
    assert assistant_item["payload"]["content"] == "Final assistant answer."
