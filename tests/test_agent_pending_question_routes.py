"""Agent pending-question recovery route regressions."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import (
    ChatEvent,
    ChatSession,
    Feature,
    FeatureStatus,
    Project,
    Task,
)
from autonomous_agent_builder.embedded.server import agent_sprint_planning
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from tests.agent_route_test_support import (
    wait_for_history_item as _wait_for_history_item,
)


@pytest.mark.asyncio
async def test_chat_respond_recovers_persisted_pending_question_without_live_waiter(
    monkeypatch,
    test_db,
    tmp_path,
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        session = ChatSession(
            repo_identity=str(tmp_path.resolve()),
            workspace_cwd=str(tmp_path.resolve()),
        )
        db.add(session)
        await db.flush()
        question = ChatEvent(
            session_id=session.id,
            event_type="ask_user_question",
            payload_json={
                "header": "First Scope",
                "question": "Which first feature?",
                "options": [{"label": "Personal todos (Recommended)", "description": "Build todos."}],
                "answered": False,
                "answer_value": "",
            },
            status="pending",
        )
        db.add(question)
        await db.commit()
        session_id = session.id
        question_id = question.id

    captured_prompts: list[str] = []

    class FakeRuntime:
        name = "codex_sdk"
        provider = "codex_subscription"

        async def run(self, prompt, **kwargs):
            captured_prompts.append(prompt)
            return RunResult(
                session_id="codex-sdk-recovered-question",
                cost_usd=0.0,
                tokens_input=1,
                tokens_output=1,
                num_turns=1,
                output_text="I captured that improvement as `Personal todos`.",
            )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeRuntime())

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        answer = await client.post(
            "/api/agent/chat/respond",
            json={
                "session_id": session_id,
                "event_id": question_id,
                "selected_options": ["Personal todos (Recommended)"],
            },
        )
        assert answer.status_code == 200
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "I captured that improvement" in item["payload"].get("content", ""),
        )

    assert assistant_item["status"] == "completed"
    assert captured_prompts
    assert 'Operator answered pending question "Which first feature?": Personal todos (Recommended)' in captured_prompts[0]
    async with factory() as db:
        updated_question = await db.get(ChatEvent, question_id)
    assert updated_question is not None
    assert updated_question.status == "answered"
    assert updated_question.payload_json["answer_value"] == "Personal todos (Recommended)"

@pytest.mark.asyncio
async def test_chat_respond_recovers_persisted_delivery_scope_approval_without_live_waiter(
    monkeypatch,
    test_db,
    tmp_path,
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        project = Project(name="todo-app", description="Todo app", language="javascript")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Text search for todos",
            description="Narrow todos by title.",
            status=FeatureStatus.BACKLOG,
            priority=50,
            acceptance_criteria=["Search filters visible todos"],
        )
        session = ChatSession(
            repo_identity=str(tmp_path.resolve()),
            workspace_cwd=str(tmp_path.resolve()),
        )
        db.add_all([feature, session])
        await db.flush()
        approval = ChatEvent(
            session_id=session.id,
            event_type="tool_approval_request",
            payload_json={
                "tool_name": "Delivery scope approval",
                "tool_input": {
                    "feature_ids": [feature.id],
                    "features": [{"id": feature.id, "title": feature.title, "priority": 50}],
                },
                "summary": "Approve this improvement before work starts",
                "answered": False,
                "decision": "",
                "reason": "",
            },
            status="pending",
        )
        db.add(approval)
        await db.commit()
        session_id = session.id
        approval_id = approval.id
        feature_id = feature.id
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_sprint_planning, "schedule_task_dispatch", fake_schedule_task_dispatch)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        answer = await client.post(
            "/api/agent/chat/respond",
            json={
                "session_id": session_id,
                "event_id": approval_id,
                "decision": "allow",
                "reason": "approve",
            },
        )
        assert answer.status_code == 200
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Builder prepared the work" in item["payload"].get("content", ""),
        )

    assert "sprint-plan" not in assistant_item["payload"]["content"]
    assert "task" not in assistant_item["payload"]["content"].lower()
    assert "Delivery has started." in assistant_item["payload"]["content"]
    async with factory() as db:
        updated_feature = await db.get(Feature, feature_id)
        task_result = await db.execute(select(Task).where(Task.feature_id == feature_id))
        tasks = list(task_result.scalars().all())
    assert updated_feature is not None
    assert updated_feature.status == FeatureStatus.SPRINT_PLANNED
    assert tasks
    assert dispatched == [tasks[0].id]

@pytest.mark.asyncio
async def test_chat_response_updates_pending_event_without_opening_second_db_session(
    monkeypatch, test_db
):
    _, factory = test_db
    async with factory() as db:
        session = ChatSession(repo_identity="repo", workspace_cwd="repo")
        db.add(session)
        await db.flush()
        question = ChatEvent(
            session_id=session.id,
            event_type="ask_user_question",
            payload_json={"question": "Start?", "answered": False},
            status="pending",
        )
        db.add(question)
        await db.commit()
        question_id = question.id

    def fail_if_nested_session_factory_is_used():
        raise AssertionError("pending question responses must update through the request DB session")

    monkeypatch.setattr(agent_routes, "get_session_factory", fail_if_nested_session_factory_is_used)

    async with factory() as db:
        event = await db.get(ChatEvent, question_id)
        assert event is not None
        updated = await agent_routes._update_request_event(
            db,
            event,
            payload_patch={"answered": True, "answer_value": "Start now"},
            status="answered",
            answer_event_type="ask_user_question_answer",
            answer_payload={"question": "Start?", "answer_value": "Start now"},
        )

    assert updated.status == "answered"
    assert updated.payload_json["answer_value"] == "Start now"

@pytest.mark.asyncio
async def test_chat_question_card_can_be_answered_and_run_resumes(monkeypatch, test_db, tmp_path):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async def fake_run_phase(self, **kwargs):
        permission = await kwargs["can_use_tool"](
            "AskUserQuestion",
            {
                "questions": [
                    {
                        "header": "Stack",
                        "question": "Which stack should I use?",
                        "options": [
                            {"label": "FastAPI", "description": "Python API stack"},
                            {"label": "Django", "description": "Batteries included"},
                        ],
                        "multiSelect": False,
                    }
                ]
            },
            {},
        )
        updated_input = getattr(permission, "updated_input", None) or getattr(
            permission, "updatedInput", None
        )
        assert updated_input["answers"]["Which stack should I use?"] == "FastAPI"
        return RunResult(
            session_id="sdk-session-question",
            cost_usd=0.04,
            tokens_input=14,
            tokens_output=8,
            num_turns=2,
            output_text="Great, I will use FastAPI.",
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
        response = await client.post("/api/agent/chat", json={"message": "Help me choose a stack"})
        session_id = response.json()["session_id"]

        _, question_item = await _wait_for_history_item(client, session_id, "ask_user_question")
        assert question_item["status"] == "pending"
        assert question_item["payload"]["recommended_index"] == 0

        answer = await client.post(
            "/api/agent/chat/respond",
            json={
                "session_id": session_id,
                "event_id": question_item["id"],
                "selected_options": ["FastAPI"],
            },
        )
        assert answer.status_code == 200

        history_payload, assistant_item = await _wait_for_history_item(
            client, session_id, "assistant_message"
        )

    updated_question = next(item for item in history_payload["items"] if item["id"] == question_item["id"])
    assert updated_question["payload"]["answered"] is True
    assert updated_question["payload"]["answer_value"] == "FastAPI"
    assert assistant_item["payload"]["content"] == "Great, I will use FastAPI."
