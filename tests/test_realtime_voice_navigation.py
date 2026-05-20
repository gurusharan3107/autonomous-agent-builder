"""Tests for Realtime Voice navigation and run-trace tool calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from autonomous_agent_builder.db.models import (
    AgentRun,
    ChatEvent,
    ChatSession,
    Feature,
    FeatureStatus,
    Project,
    Task,
    TaskPhase,
    TaskStatus,
)
from autonomous_agent_builder.embedded.server import agent_chat_sessions
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import realtime
from autonomous_agent_builder.services.voice_operator import AgentOperatorService


@pytest.mark.asyncio
async def test_navigate_dashboard_publishes_voice_navigation_event(test_db, tmp_path: Path):
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
        await db.commit()
        session_id = session.id

    result = await realtime._handle_tool_call(
        app,
        {
            "name": "navigate_dashboard",
            "arguments": json.dumps({"target": "I want to see the board"}),
        },
        call_id="rtc_nav",
    )

    assert result["ok"] is True
    payload = result["result"]
    assert payload["status"] == "navigation_requested"
    assert payload["route"] == "/board"

    async with factory() as db:
        event_result = await db.execute(
            select(ChatEvent).where(ChatEvent.event_type == "voice_navigation_request")
        )
        event = event_result.scalar_one()
    assert event.session_id == session_id
    assert event.payload_json["route"] == "/board"


@pytest.mark.asyncio
async def test_open_run_trace_publishes_navigation_for_latest_optimization_run(
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
        project = Project(name="Todo App")
        feature = Feature(project=project, title="Optimize task loop", status=FeatureStatus.QUEUED)
        task = Task(
            feature=feature,
            title="Reduce repeated agent runs",
            status=TaskStatus.DONE,
            phase=TaskPhase.IMPLEMENTATION,
        )
        run = AgentRun(
            task=task,
            agent_name="optimization-agent",
            status="completed",
            num_turns=4,
        )
        db.add_all([session, project, feature, task, run])
        await db.commit()
        session_id = session.id
        task_id = task.id
        run_id = run.id

    result = await realtime._handle_tool_call(
        app,
        {
            "name": "open_run_trace",
            "arguments": json.dumps({"selection": "show me the last optimization run"}),
        },
        call_id="rtc_trace",
    )

    assert result["ok"] is True
    payload = result["result"]
    assert payload["status"] == "navigation_requested"
    assert payload["run_id"] == run_id
    assert payload["task_id"] == task_id
    assert payload["matched_on"] == "agent_name"
    assert payload["route"] == f"/?mode=trace&task={task_id}&run={run_id}"

    async with factory() as db:
        event_result = await db.execute(
            select(ChatEvent).where(ChatEvent.event_type == "voice_navigation_request")
        )
        event = event_result.scalar_one()
    assert event.session_id == session_id
    assert event.payload_json["action"] == "open_run_trace"
    assert event.payload_json["route"] == f"/?mode=trace&task={task_id}&run={run_id}"
    assert event.payload_json["run"]["agent_name"] == "optimization-agent"


@pytest.mark.asyncio
async def test_open_run_trace_then_delegates_analysis_to_builder_agent(
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

    async def fake_send_message(
        self: AgentOperatorService,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        assert self.app is app
        captured.update(arguments)
        return {"session_id": arguments["session_id"], "completion_status": "completed"}

    monkeypatch.setattr(AgentOperatorService, "send_message", fake_send_message)

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        project = Project(name="Todo App")
        feature = Feature(project=project, title="Blocked recovery", status=FeatureStatus.QUEUED)
        task = Task(
            feature=feature,
            title="Fix blocked persistence run",
            status=TaskStatus.BLOCKED,
            phase=TaskPhase.IMPLEMENTATION,
            blocked_reason="Tests failed after dispatch.",
        )
        run = AgentRun(
            task=task,
            agent_name="code-gen",
            status="failed",
            error="pytest failed",
            num_turns=9,
        )
        db.add_all([session, project, feature, task, run])
        await db.commit()
        session_id = session.id
        task_id = task.id
        run_id = run.id

    result = await realtime._handle_tool_call(
        app,
        {
            "name": "open_run_trace",
            "arguments": json.dumps(
                {
                    "selection": "current agent run that led to blocked state",
                    "intent": "open_then_analyze",
                    "analysis_request": "Was this run efficient and what issues do you see?",
                    "completion_timeout_seconds": 5,
                }
            ),
        },
        call_id="rtc_trace_analysis",
    )

    assert result["ok"] is True
    payload = result["result"]
    assert payload["route"] == f"/?mode=trace&task={task_id}&run={run_id}"
    assert payload["analysis_request"] == "Was this run efficient and what issues do you see?"
    assert payload["delegation"]["completion_status"] == "completed"
    assert captured["session_id"] == session_id
    assert captured["bypass_voice_routing"] is True
    assert "Run id: " + run_id in captured["message"]
    assert "Task id: " + task_id in captured["message"]
    assert "Was this run efficient" in captured["message"]
    assert "Use Builder-owned run trace, logs, metrics, and task evidence" in captured["message"]

    async with factory() as db:
        event_result = await db.execute(
            select(ChatEvent).where(ChatEvent.event_type == "voice_navigation_request")
        )
        event = event_result.scalar_one()
    assert event.payload_json["intent"] == "open_then_analyze"
    assert event.payload_json["analysis_request"] == (
        "Was this run efficient and what issues do you see?"
    )


@pytest.mark.asyncio
async def test_open_run_trace_intent_open_then_analyze_defaults_analysis_request(
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

    async def fake_send_message(
        self: AgentOperatorService,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        captured.update(arguments)
        return {"session_id": arguments["session_id"], "completion_status": "completed"}

    monkeypatch.setattr(AgentOperatorService, "send_message", fake_send_message)

    async with factory() as db:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        project = Project(name="Todo App")
        feature = Feature(project=project, title="Trace review", status=FeatureStatus.QUEUED)
        task = Task(
            feature=feature,
            title="Review current agent run",
            status=TaskStatus.DONE,
            phase=TaskPhase.IMPLEMENTATION,
        )
        run = AgentRun(task=task, agent_name="code-gen", status="completed")
        db.add_all([session, project, feature, task, run])
        await db.commit()
        run_id = run.id

    result = await realtime._handle_tool_call(
        app,
        {
            "name": "open_run_trace",
            "arguments": json.dumps(
                {
                    "selection": "analyze the current agent run",
                    "intent": "open_then_analyze",
                }
            ),
        },
        call_id="rtc_trace_default_analysis",
    )

    assert result["ok"] is True
    assert result["result"]["run_id"] == run_id
    assert result["result"]["analysis_request"] == "analyze the current agent run"
    assert result["result"]["delegation"]["completion_status"] == "completed"
    assert "analyze the current agent run" in captured["message"].lower()
    assert captured["bypass_voice_routing"] is True
