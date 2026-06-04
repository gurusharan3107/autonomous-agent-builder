"""Agent background timeline and shipped-closeout route regressions."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import (
    AgentRun,
    BacklogItemType,
    ChatEvent,
    ChatSession,
    DesignDocument,
    Feature,
    FeatureStatus,
    Project,
    Sprint,
    SprintPhase,
    Task,
    TaskPhase,
    TaskStatus,
)
from autonomous_agent_builder.embedded.server import agent_chat_sessions
from autonomous_agent_builder.embedded.server.app import create_app
from tests.agent_route_test_support import (
    wait_for_history_item as _wait_for_history_item,
)
from tests.agent_route_test_support import (
    write_forward_engineering_ready_state as _write_forward_engineering_ready_state,
)


@pytest.mark.asyncio
async def test_chat_post_starts_background_run_and_persists_timeline(
    monkeypatch, test_db, tmp_path
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )

    async def fake_run_phase(self, **kwargs):
        assert kwargs["agent_name"] == "chat"
        return RunResult(
            session_id="sdk-session-1",
            cost_usd=0.02,
            tokens_input=10,
            tokens_output=5,
            num_turns=1,
            duration_ms=1234,
            stop_reason="end_turn",
            output_text="hello back",
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
            "/api/agent/chat", json={"message": "hello", "session_id": None}
        )

        assert response.status_code == 200
        payload = response.json()
        # Conftest sets RUNTIME_MODEL=sonnet (autouse).
        assert payload["model"] == "sonnet"
        assert payload["status"]["running"] is True
        session_id = payload["session_id"]

        history_payload, assistant_item = await _wait_for_history_item(
            client, session_id, "assistant_message"
        )

    assert assistant_item["payload"]["content"] == "hello back"
    assert history_payload["sdk_session_id"] == "sdk-session-1"
    assert history_payload["status"]["running"] is False
    assert history_payload["status"]["sdk_session_id"] == "sdk-session-1"
    assert history_payload["status"]["duration_ms"] == 1234
    assert history_payload["status"]["stop_reason"] == "end_turn"
    assert history_payload["messages"][-1]["content"] == "hello back"


@pytest.mark.asyncio
async def test_chat_history_appends_shipped_delivery_closeout_once(test_db, tmp_path):
    _, factory = test_db
    _write_forward_engineering_ready_state(tmp_path)
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )

    async with factory() as db:
        project = Project(name="demo", description="demo", language="javascript")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Collapsible completed todos section",
            description="Completed todos can be collapsed.",
            status=FeatureStatus.DONE,
            item_type=BacklogItemType.IMPROVEMENT,
        )
        db.add(feature)
        await db.flush()
        tasks = [
            Task(
                feature_id=feature.id,
                title="Implement core app behavior for Collapsible completed todos section",
                description="Implement the feature.",
                status=TaskStatus.DONE,
                phase=TaskPhase.COMPLETE,
            ),
            Task(
                feature_id=feature.id,
                title="Cover persistence and tests for Collapsible completed todos section",
                description="Cover persistence.",
                status=TaskStatus.DONE,
                phase=TaskPhase.COMPLETE,
            ),
            Task(
                feature_id=feature.id,
                title="Verify Collapsible completed todos section for shipping",
                description="Verify shipping.",
                status=TaskStatus.DONE,
                phase=TaskPhase.COMPLETE,
            ),
        ]
        db.add_all(tasks)
        await db.flush()
        plan_doc = DesignDocument(
            task_id=tasks[0].id,
            doc_type="sprint_plan",
            title="Sprint execution plan",
            content=json.dumps({"plan_id": "sprint-plan-closeout"}),
        )
        db.add(plan_doc)
        await db.flush()
        sprint = Sprint(
            project_id=project.id,
            label="Sprint 7",
            phase=SprintPhase.SHIPPED,
            plan_doc_id=plan_doc.id,
            approved_feature_ids=[feature.id],
            generated_task_ids=[task.id for task in tasks],
            verification_status="passed",
        )
        db.add(sprint)
        db.add_all(
            [
                AgentRun(
                    task_id=tasks[0].id,
                    agent_name="code-gen",
                    status="completed",
                    tokens_input=120,
                    tokens_output=10,
                    tokens_cached=100,
                ),
                AgentRun(
                    task_id=tasks[1].id,
                    agent_name="code-gen",
                    status="completed",
                    tokens_input=80,
                    tokens_output=5,
                    tokens_cached=70,
                ),
            ]
        )
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, tmp_path)
        db.add(session)
        await db.flush()
        db.add(
            ChatEvent(
                session_id=session.id,
                event_type="delivery_plan_created",
                payload_json={
                    "plan_id": "sprint-plan-closeout",
                    "feature_ids": [feature.id],
                    "feature_titles": [feature.title],
                },
                status="completed",
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
        first_history = (
            await client.get("/api/agent/chat/history", params={"session_id": session_id})
        ).json()
        second_history = (
            await client.get("/api/agent/chat/history", params={"session_id": session_id})
        ).json()

    closeouts = [
        item["payload"].get("content", "")
        for item in second_history["items"]
        if item["type"] == "assistant_message"
        and item["payload"].get("content", "").startswith("Builder shipped ")
    ]
    assert len(closeouts) == 1
    assert closeouts[0] in [item["payload"].get("content", "") for item in first_history["items"]]
    assert "Builder shipped `Collapsible completed todos section`." in closeouts[0]
    assert "implementation, tests, and browser-visible verification completed" in closeouts[0]
    assert "3 pieces of work completed" in closeouts[0]
    assert "215 raw, 170 cached, 45 non-cached plus output across 2 run(s)" in closeouts[0]
