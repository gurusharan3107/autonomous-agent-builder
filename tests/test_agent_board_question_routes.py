"""Agent board and approval question route regressions."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import (
    BacklogItemType,
    ChatEvent,
    Feature,
    FeatureStatus,
    Project,
    Sprint,
)
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from tests.agent_route_test_support import (
    wait_for_history_item as _wait_for_history_item,
)
from tests.agent_route_test_support import (
    write_forward_engineering_ready_state as _write_forward_engineering_ready_state,
)


@pytest.mark.asyncio
async def test_agent_approval_status_question_uses_model_backed_read_only_context(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )
    _write_forward_engineering_ready_state(tmp_path)
    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        db.add(
            Feature(
                project_id=project.id,
                title="Existing backlog item",
                description="Keeps the chat lane out of init bootstrap.",
                status=FeatureStatus.DONE,
                item_type=BacklogItemType.FEATURE,
            )
        )
        await db.commit()

    runtime_prompts: list[str] = []

    class FakeRuntime:
        name = "codex_sdk"

        async def run(self, prompt, *args, **kwargs):
            runtime_prompts.append(prompt)
            return RunResult(
                session_id="sdk-session-approval-status",
                cost_usd=0.01,
                tokens_input=5,
                tokens_output=7,
                num_turns=1,
                output_text=(
                    "Board status from Builder source of truth: no active blocked work. "
                    "No approval or prepared action is pending right now. "
                    "I did not create sprint scope, dispatch a task, recover a task, "
                    "or mark work done."
                ),
                stop_reason="end_turn",
            )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeRuntime())

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "do I need to approve anything?"},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "No approval or prepared action is pending right now."
            in item["payload"].get("content", ""),
        )

    async with factory() as db:
        status_result = await db.execute(
            select(ChatEvent).where(
                ChatEvent.session_id == session_id,
                ChatEvent.event_type == "run_status",
            )
        )
        stop_reasons = [
            event.payload_json.get("stop_reason")
            for event in status_result.scalars().all()
        ]

    content = assistant_item["payload"]["content"]
    assert "Board status from Builder source of truth" in content
    assert "No approval or prepared action is pending right now." in content
    assert "I did not create sprint scope, dispatch a task, recover a task" in content
    assert runtime_prompts
    assert "do I need to approve anything?" in runtime_prompts[0]
    assert "end_turn" in stop_reasons
    assert "deterministic_status_check" not in stop_reasons

@pytest.mark.asyncio
async def test_bulk_backlog_mutation_request_stays_runtime_judgment_with_safety_contract(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )
    _write_forward_engineering_ready_state(tmp_path)
    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        db.add(
            Feature(
                project_id=project.id,
                title="Existing shipped feature",
                description="Keeps the chat lane out of init bootstrap.",
                status=FeatureStatus.DONE,
                item_type=BacklogItemType.FEATURE,
            )
        )
        await db.commit()

    runtime_prompts: list[str] = []

    class FakeRuntime:
        name = "claude"
        provider = "claude_agent_sdk"

        async def run(self, prompt, *args, **kwargs):
            runtime_prompts.append(prompt)
            return RunResult(
                session_id="bulk-mutation-safety",
                cost_usd=0.01,
                tokens_input=4,
                tokens_output=4,
                num_turns=1,
                output_text=(
                    "I can inspect the backlog state, but I cannot clear or mark everything shipped "
                    "without a visible prepared action and explicit approval for the exact targets."
                ),
                stop_reason="end_turn",
            )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeRuntime())

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "mark everything shipped and clear the backlog"},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "visible prepared action and explicit approval"
            in item["payload"].get("content", ""),
        )

    async with factory() as db:
        status_result = await db.execute(
            select(ChatEvent).where(
                ChatEvent.session_id == session_id,
                ChatEvent.event_type == "run_status",
            )
        )
        stop_reasons = [
            event.payload_json.get("stop_reason")
            for event in status_result.scalars().all()
        ]

    assert runtime_prompts
    assert "execute requested mutations through granted Builder tools" in runtime_prompts[0]
    assert "Not allowed: invent a `don't-ask mode`" in runtime_prompts[0]
    assert "bulk requests such as clearing backlog" in runtime_prompts[0]
    assert "visible approval/prepared-action path" in runtime_prompts[0]
    assert "without a visible prepared action" in assistant_item["payload"]["content"]
    assert "end_turn" in stop_reasons
    assert "deterministic_risky_mutation_guard" not in stop_reasons

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "what is left on the board?",
        "what's left in the backlog?",
        "is anything actually blocked?",
    ],
)
async def test_board_remaining_prompt_uses_model_backed_status_lane(
    monkeypatch, test_db, tmp_path, message
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )
    _write_forward_engineering_ready_state(tmp_path)

    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Done feature",
            description="Already shipped.",
            status=FeatureStatus.DONE,
            item_type=BacklogItemType.FEATURE,
        )
        db.add(feature)
        await db.flush()
        sprint = Sprint(
            project_id=project.id,
            label="Sprint 1",
            phase="shipped",
            verification_status="shipped",
            approved_feature_ids=[feature.id],
            generated_task_ids=[],
        )
        db.add(sprint)
        await db.commit()

    class FakeRuntime:
        name = "codex_sdk"

        async def run(self, prompt, *args, **kwargs):
            return RunResult(
                session_id="sdk-board-remaining",
                cost_usd=0.01,
                tokens_input=12,
                tokens_output=16,
                num_turns=1,
                output_text=(
                    "Board status from Builder source of truth: "
                    "Queued 0, in progress 0, needs review 0, shipped 0, blocked 0. "
                    "No Board tasks are currently tracked."
                ),
                stop_reason="end_turn",
            )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeRuntime())

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": message},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Board status from Builder source of truth"
            in item["payload"].get("content", ""),
        )

    content = assistant_item["payload"]["content"]
    assert "Board status from Builder source of truth" in content
    assert "Queued 0, in progress 0, needs review 0, shipped 0, blocked 0" in content
    assert "No Board tasks are currently tracked." in content

@pytest.mark.asyncio
async def test_continue_building_auto_answers_recommended_next_feature(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )

    async with factory() as db:
        db.add(Project(name="demo", description="demo", language="python"))
        await db.commit()

    async def fake_run_phase(self, **kwargs):
        permission = await kwargs["can_use_tool"](
            "AskUserQuestion",
            {
                "questions": [
                    {
                        "header": "Next Feature",
                        "question": "Which feature should we implement next?",
                        "options": [
                            {
                                "label": "Session List UI",
                                "description": "Build the main session list interface.",
                            },
                            {
                                "label": "Session Timer",
                                "description": "Implement timer controls.",
                            },
                        ],
                        "recommendedIndex": 0,
                    }
                ]
            },
            {},
        )
        updated_input = getattr(permission, "updated_input", None) or getattr(
            permission,
            "updatedInput",
            None,
        )
        assert updated_input["answers"]["Which feature should we implement next?"] == (
            "Session List UI"
        )
        return RunResult(
            session_id="sdk-session-auto-question",
            cost_usd=0.01,
            tokens_input=4,
            tokens_output=4,
            num_turns=1,
            output_text="Continuing with Session List UI.",
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
            json={"message": "Continue building my app."},
        )
        session_id = response.json()["session_id"]
        history_payload, _ = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
        )
        for _ in range(20):
            if history_payload["status"]["running"] is False:
                break
            await asyncio.sleep(0.05)
            history_payload = (
                await client.get("/api/agent/chat/history", params={"session_id": session_id})
            ).json()

    assert not any(item["type"] == "ask_user_question" for item in history_payload["items"])
