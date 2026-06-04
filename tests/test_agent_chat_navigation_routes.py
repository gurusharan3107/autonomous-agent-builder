"""Agent chat navigation, observability, and recent-context route regressions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import (
    ChatEvent,
    ChatSession,
)
from autonomous_agent_builder.embedded.server import (
    agent_message_intent,
    agent_observability_context,
)
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from tests.agent_route_test_support import (
    wait_for_history_item as _wait_for_history_item,
)
from tests.agent_route_test_support import (
    wait_for_history_status as _wait_for_history_status,
)


def test_observability_context_pack_keeps_analysis_model_backed(monkeypatch, tmp_path):
    db_dir = tmp_path / ".agent-builder"
    db_dir.mkdir()
    (db_dir / "agent_builder.db").write_text("", encoding="utf-8")

    monkeypatch.setattr(
        agent_observability_context,
        "dashboard_observability_summary",
        lambda _db_path: {
            "runtime": {"selected_runtime_sdk": "codex_sdk"},
            "observability_coverage": {
                "source": "codex_app_server",
                "missing_signals": [],
                "next": "Inspect large command output before retrying.",
                "telemetry_health": {
                    "codex_native": {
                        "status": "ok",
                        "collector_status": "reachable",
                    }
                },
                "aggregates": {
                    "raw_token_total": 1000,
                    "cache_ratio": 0.5,
                    "avoidable_cost_flags": ["large_command_output"],
                    "top_cost_drivers": [
                        {
                            "agent_name": "agent-chat",
                            "runs": 3,
                            "raw_tokens": 900,
                            "avoidable_token_estimate": 100,
                        }
                    ],
                },
                "deterministic_recommendations": [
                    {
                        "code": "script_candidate_output_truncation_artifact",
                        "severity": "high",
                        "next_action": "promote_or_reuse_builder_script_candidate",
                        "lifecycle_status": "open",
                    }
                ],
            },
        },
    )

    context = agent_routes._observability_context_for_prompt(
        tmp_path,
        "what can you tell me from observability data, what should i fix next?",
    )

    assert "Builder observability context pack already retrieved" in context
    assert "analyze the operator's intent" in context
    assert "builder metrics show --json" in context
    assert "builder logs --error --json" in context
    assert "Avoid raw or --full" in context
    assert "large_command_output" in context
    assert "agent-chat" in context

@pytest.mark.asyncio
async def test_agent_chat_simple_dashboard_navigation_is_model_backed(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    captured_prompts: list[str] = []

    async def fake_run_phase(self, **kwargs):
        captured_prompts.append(str(kwargs.get("prompt") or ""))
        return RunResult(
            session_id="sdk-navigation",
            cost_usd=0.01,
            tokens_input=8,
            tokens_output=4,
            num_turns=1,
            output_text="I can help with the Backlog view from here.",
            stop_reason="end_turn",
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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/agent/chat", json={"message": "show me the backlog"})
        assert response.status_code == 200
        session_id = response.json()["session_id"]

        _history, assistant = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Backlog view" in item["payload"].get("content", ""),
        )
        history = await _wait_for_history_status(
            client,
            session_id,
            predicate=lambda status: status.get("running") is False
            and status.get("stop_reason") == "end_turn",
        )

    assert captured_prompts
    assert "show me the backlog" in captured_prompts[0]
    assert assistant["payload"]["content"] == "I can help with the Backlog view from here."
    assert history["status"]["running"] is False
    assert history["status"]["stop_reason"] == "end_turn"

def test_agent_chat_dashboard_navigation_does_not_capture_questions():
    assert agent_message_intent.dashboard_navigation_route_from_message("show me the backlog") == "/backlog"
    assert (
        agent_message_intent.dashboard_navigation_route_from_message(
            "why is observability still showing a missing signal?"
        )
        == ""
    )

@pytest.mark.asyncio
async def test_agent_chat_observability_question_is_model_backed(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    captured_prompts: list[str] = []

    async def fake_run_phase(self, **kwargs):
        captured_prompts.append(str(kwargs.get("prompt") or ""))
        return RunResult(
            session_id="sdk-observability",
            cost_usd=0.01,
            tokens_input=8,
            tokens_output=6,
            num_turns=1,
            output_text="Observability is showing a missing signal because telemetry is incomplete.",
            stop_reason="end_turn",
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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "why is observability still showing a missing signal?"},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]

        _history, assistant = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Observability is showing" in item["payload"].get("content", ""),
        )
        history = await _wait_for_history_status(
            client,
            session_id,
            predicate=lambda status: status.get("running") is False
            and status.get("stop_reason") == "end_turn",
        )

    assert captured_prompts
    assert "why is observability still showing a missing signal?" in captured_prompts[0]
    assert "Opening Observability" not in assistant["payload"]["content"]
    assert "Observability is showing" in assistant["payload"]["content"]
    assert history["status"]["running"] is False
    assert history["status"]["stop_reason"] == "end_turn"

def test_agent_chat_recovery_preflight_does_not_capture_evidence_requests():
    assert agent_message_intent.message_requests_recovery_preflight("Recover the last failed run.")
    assert not agent_message_intent.message_requests_recovery_preflight(
        "Give me a bounded recovery plan for the blocked task using Builder evidence only."
    )

@pytest.mark.asyncio
async def test_agent_chat_recovery_request_without_board_target_is_model_backed(
    monkeypatch: pytest.MonkeyPatch,
    test_db,
    tmp_path: Path,
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    captured_prompts: list[str] = []

    async def fake_run_phase(self, **kwargs):
        captured_prompts.append(str(kwargs.get("prompt") or ""))
        return RunResult(
            session_id="sdk-recovery-preflight",
            cost_usd=0.01,
            tokens_input=8,
            tokens_output=8,
            num_turns=1,
            output_text="No recoverable Board task is currently blocked, failed, or capability-limited.",
            stop_reason="end_turn",
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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "Recover the last failed run."},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]

        _history, assistant = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "No recoverable Board task"
            in item["payload"].get("content", ""),
        )
        history = await _wait_for_history_status(
            client,
            session_id,
            predicate=lambda status: status.get("running") is False
            and status.get("stop_reason") == "end_turn",
        )

    content = assistant["payload"]["content"]
    assert captured_prompts
    assert "Recover the last failed run." in captured_prompts[0]
    assert "No recoverable Board task is currently blocked, failed, or capability-limited." in content
    assert history["status"]["running"] is False
    assert history["status"]["stop_reason"] == "end_turn"

def test_recent_chat_context_pack_includes_prior_voice_and_builder_messages(tmp_path):
    session = ChatSession()
    session.events = [
        ChatEvent(
            event_type="voice_operator_message",
            status="completed",
            created_at=datetime.now(UTC),
            payload_json={"content": "We discussed push notification recommendations."},
        ),
        ChatEvent(
            event_type="user_message",
            status="completed",
            created_at=datetime.now(UTC),
            payload_json={
                "content": "Review the recent conversation about notifications.",
                "source": "realtime_voice",
            },
        ),
        ChatEvent(
            event_type="assistant_message",
            status="completed",
            created_at=datetime.now(UTC),
            payload_json={"content": "Push notifications should cover due soon and completed tasks."},
        ),
    ]

    context = agent_routes._recent_chat_context_for_prompt(
        session,
        "Please create the backlog from the recommendations discussed.",
    )
    prompt = agent_routes._general_chat_prompt(
        tmp_path,
        "Please create the backlog from the recommendations discussed.",
        recent_context=context,
    )

    assert "Operator by voice: We discussed push notification recommendations." in context
    assert "Samantha delegated: Review the recent conversation" in context
    assert "Builder Agent: Push notifications should cover due soon" in context
    assert "Bounded retrieval context already available" in prompt
    assert "Push notifications should cover due soon" in prompt

def test_recent_chat_context_pack_is_bounded_and_marks_clipped_events():
    session = ChatSession()
    session.events = [
        ChatEvent(
            event_type="assistant_message",
            status="completed",
            created_at=datetime(2026, 5, 15, index, tzinfo=UTC),
            payload_json={"content": f"Older context event {index} " + ("detail " * 80)},
        )
        for index in range(8)
    ]

    context = agent_routes._recent_chat_context_for_prompt(
        session,
        "Use the previous recommendation from this conversation.",
    )

    assert "Context pack clipped 2 older event(s)." in context
    assert "Older context event 0" not in context
    assert "Older context event 1" not in context
    assert "Older context event 2" in context
    assert "..." in context
    assert len(context) < 2_100
