"""Forward-engineering Agent route regression tests."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import ChatEvent, Feature, FeatureStatus, Project, Task
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from autonomous_agent_builder.onboarding import _INIT_PROJECT_BOOTSTRAP_MESSAGE
from tests.agent_route_test_support import (
    wait_for_history_item,
    write_forward_engineering_ready_state,
)


@pytest.mark.asyncio
async def test_forward_engineering_greeting_uses_general_model_backed_chat(
    monkeypatch, test_db, tmp_path
):
    dashboard_root = tmp_path.parent / f"{tmp_path.name}-dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )
    write_forward_engineering_ready_state(tmp_path)
    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured.update(kwargs)
        assert kwargs["agent_name"] == "chat"
        return RunResult(
            session_id="sdk-forward-greeting",
            cost_usd=0.01,
            tokens_input=6,
            tokens_output=4,
            num_turns=1,
            output_text="Hi. What would you like to build?",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        history = await client.get("/api/agent/chat/history")
        session_id = history.json()["session_id"]
        response = await client.post(
            "/api/agent/chat",
            json={"message": "hi", "session_id": session_id},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        assert response.json()["model"] == agent_routes._runtime_metadata_for_agent("chat")["model"]

        _history_payload, assistant_item = await wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            timeout=10.0,
            predicate=lambda item: (
                item["payload"].get("content") == "Hi. What would you like to build?"
            ),
        )

    prompt = str(captured["prompt"])
    assert "Forward-engineering project context is active" in prompt
    assert "the user's prompt still owns intent" in prompt
    assert "User: hi" in prompt
    assert assistant_item["payload"]["content"] == "Hi. What would you like to build?"
    assert not (tmp_path / ".claude" / "progress" / "feature-list.json").exists()


@pytest.mark.asyncio
async def test_forward_engineering_first_product_prompt_ignores_stale_delivery_feature(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path.parent / f"{tmp_path.name}-dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )
    write_forward_engineering_ready_state(tmp_path)
    async with factory() as db:
        project = Project(name="habit-lab", description="Habit Lab", language="javascript")
        db.add(project)
        await db.flush()
        db.add(
            Feature(
                project_id=project.id,
                title="Local-first daily habit tracker",
                description="Previously captured generic Habit Lab scope.",
                status=FeatureStatus.BACKLOG,
                priority=100,
                acceptance_criteria=[
                    "User can add a habit.",
                    "User can mark the habit complete today.",
                ],
            )
        )
        await db.commit()

    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured.update(kwargs)
        assert kwargs["agent_name"] == "chat"
        return RunResult(
            session_id="sdk-forward-first-product",
            cost_usd=0.01,
            tokens_input=10,
            tokens_output=8,
            num_turns=1,
            output_text="Who is this Habit Lab app for, and what outcome should it show first?",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
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
            json={"message": "I want to build a personal Habit Lab app for tracking daily habits."},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        history_payload, assistant_item = await wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            timeout=10.0,
            predicate=lambda item: (
                "Who is this Habit Lab app for" in item["payload"].get("content", "")
            ),
        )

    prompt = str(captured["prompt"])
    assert "improvement-scoping guide" in prompt
    assert "user-specific requirements" in prompt
    assert "avoid a generic MVP inferred from the product category" in prompt
    assert "Do not cap the interview at one question or one structured request" in prompt
    assert assistant_item["payload"]["content"].startswith("Who is this Habit Lab app for")
    assert all(item["type"] != "tool_approval_request" for item in history_payload["items"])


@pytest.mark.asyncio
async def test_forward_engineering_chat_marks_provider_limit_blocked(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path.parent / f"{tmp_path.name}-dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )
    write_forward_engineering_ready_state(tmp_path)

    async def fake_run_phase(self, **kwargs):
        assert kwargs["agent_name"] == "chat"
        return RunResult(
            session_id="sdk-provider-limit-1",
            num_turns=6,
            output_text="You're out of extra usage · resets 11:10pm (Asia/Calcutta)",
            stop_reason="provider_limit",
            provider_limit={
                "code": "provider_limit",
                "reason": "stop_sequence",
                "reset_at": "2026-05-07T17:40:00+00:00",
                "reset_hint": "resets 11:10pm",
                "source": "claude_agent_sdk",
            },
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        history = await client.get("/api/agent/chat/history")
        session_id = history.json()["session_id"]
        response = await client.post(
            "/api/agent/chat",
            json={"message": "Build me a local todo app.", "session_id": session_id},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _payload, assistant_item = await wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: item["status"] == "blocked",
        )

    assert "Provider limit blocked this run" in assistant_item["payload"]["content"]
    assert not (tmp_path / ".claude" / "progress" / "feature-list.json").exists()

    async with factory() as db:
        result = await db.execute(
            select(ChatEvent).where(
                ChatEvent.session_id == session_id,
                ChatEvent.event_type == "run_status",
            )
        )
        status_event = [
            event
            for event in result.scalars().all()
            if event.payload_json.get("stop_reason") == "provider_limit"
        ][0]

    assert status_event.status == "blocked"
    assert status_event.payload_json["stop_reason"] == "provider_limit"
    assert status_event.payload_json["provider_limit"]["source"] == "claude_agent_sdk"


@pytest.mark.asyncio
async def test_built_project_does_not_bootstrap_init_project_chat(monkeypatch, test_db, tmp_path):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )
    write_forward_engineering_ready_state(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.js").write_text("console.log('built');\n", encoding="utf-8")

    _, factory = test_db
    async with factory() as db:
        project = Project(
            name="built-project",
            description="Already generated app",
            repo_url=str(tmp_path),
            language="node",
        )
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Existing shipped outcome",
            description="Generated app already exists.",
            status=FeatureStatus.DONE,
        )
        db.add(feature)
        await db.flush()
        db.add(Task(feature_id=feature.id, title="Existing implementation", status="done"))
        await db.commit()

    async def fake_run_phase(self, **kwargs):
        assert kwargs["agent_name"] == "chat"
        return RunResult(
            session_id="sdk-chat-built-project",
            cost_usd=0.01,
            tokens_input=4,
            tokens_output=3,
            tokens_cached=2,
            num_turns=1,
            output_text="Normal chat route.",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        history = await client.get("/api/agent/chat/history")
        assert history.status_code == 200
        history_payload = history.json()
        assert _INIT_PROJECT_BOOTSTRAP_MESSAGE not in [
            item["payload"].get("content")
            for item in history_payload["items"]
            if item["type"] == "assistant_message"
        ]

        response = await client.post(
            "/api/agent/chat",
            json={"message": "What is the current state?"},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        history_payload, assistant_item = await wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            timeout=10.0,
            predicate=lambda item: item["payload"].get("content") == "Normal chat route.",
        )

    assert assistant_item["payload"]["content"] == "Normal chat route."
    assert history_payload["status"]["tokens_used"] == 7
    assert history_payload["status"]["tokens_input"] == 4
    assert history_payload["status"]["tokens_output"] == 3
    assert history_payload["status"]["tokens_cached"] == 2
    assert history_payload["status"]["noncached_plus_output_tokens"] == 5


@pytest.mark.asyncio
async def test_forward_engineering_new_thread_does_not_reuse_bootstrap_session(
    monkeypatch, test_db, tmp_path
):
    write_forward_engineering_ready_state(tmp_path)
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )

    async def fake_run_phase(self, **kwargs):
        return RunResult(
            session_id="sdk-session-new-thread",
            cost_usd=0.01,
            tokens_input=5,
            tokens_output=4,
            num_turns=1,
            output_text="New thread accepted.",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        history = await client.get("/api/agent/chat/history")
        bootstrap_session_id = history.json()["session_id"]

        response = await client.post(
            "/api/agent/chat",
            json={"message": "Build a tiny local app.", "session_id": None},
        )
        assert response.status_code == 200
        new_session_id = response.json()["session_id"]

        assert new_session_id != bootstrap_session_id
        _, assistant_item = await wait_for_history_item(
            client,
            new_session_id,
            "assistant_message",
            timeout=10.0,
            predicate=lambda item: item["payload"].get("content") == "New thread accepted.",
        )

    assert assistant_item["payload"]["content"] == "New thread accepted."
