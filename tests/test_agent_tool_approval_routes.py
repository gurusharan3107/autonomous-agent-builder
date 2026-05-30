"""Agent operator tool-approval route regressions."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import (
    Project,
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
async def test_assistant_delivery_permission_prompt_becomes_pending_question(
    monkeypatch, test_db, tmp_path
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async def fake_run_phase(self, **kwargs):
        return RunResult(
            session_id="sdk-session-delivery-permission",
            cost_usd=0.02,
            tokens_input=10,
            tokens_output=12,
            num_turns=1,
            output_text=(
                "I found the implementation path.\n\n"
                "Ready for Builder to start now, or should I hold?"
            ),
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
            json={"message": "Confirm the implementation plan."},
        )
        session_id = response.json()["session_id"]

        history_payload, question_item = await _wait_for_history_item(
            client, session_id, "ask_user_question"
        )

    assert question_item["status"] == "pending"
    assert question_item["payload"]["source"] == "assistant_delivery_permission_prompt"
    assert question_item["payload"]["question"] == (
        "Ready for Builder to start this work?"
    )
    assert question_item["payload"]["options"][0]["label"] == "Start now"
    assert history_payload["status"]["running"] is False

@pytest.mark.asyncio
async def test_codex_init_project_prompt_uses_native_question_tool_and_card(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")
    _write_forward_engineering_ready_state(tmp_path)
    async with factory() as db:
        db.add(Project(name="ChoreFlow", description="demo", language="python"))
        await db.commit()
    captured_prompts: list[str] = []

    class FakeCodexRuntime:
        name = "codex_sdk"

        async def run(self, input: str, **kwargs):
            captured_prompts.append(input)
            permission = await kwargs["can_use_tool"](
                "request_user_input",
                {
                    "questions": [
                        {
                            "header": "Fairness",
                            "question": "Which chore rotation rule should ChoreFlow use?",
                            "options": [
                                {
                                    "label": "Effort balance (Recommended)",
                                    "description": "Assign the next chore to the lowest current effort total.",
                                },
                                {
                                    "label": "Round robin",
                                    "description": "Rotate each chore independently.",
                                },
                                {
                                    "label": "Manual pick",
                                    "description": "Let the operator assign each chore manually.",
                                },
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
            assert (
                updated_input["answers"]["Which chore rotation rule should ChoreFlow use?"]
                == "Effort balance (Recommended)"
            )
            return RunResult(
                session_id="codex-sdk-question",
                cost_usd=0.0,
                tokens_input=11,
                tokens_output=6,
                num_turns=1,
                output_text=(
                    "AGREEMENT:\n"
                    "ChoreFlow will use effort-balanced chore rotation.\n\n"
                    "FEATURE_LIST_JSON:\n"
                    "{"
                    '"metadata":{"project":"ChoreFlow","done":0,"pending":1},'
                    '"features":[{"id":"feature-01","title":"Effort-balanced chores",'
                    '"description":"Assign chores using effort balance.",'
                    '"status":"pending","priority":"100",'
                    '"acceptance_criteria":["Owners can see balanced chore assignments"],'
                    '"dependencies":[]}]'
                    "}"
                ),
            )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **_kwargs: FakeCodexRuntime())

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
            json={"session_id": session_id, "message": "Build ChoreFlow."},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]

        _, question_item = await _wait_for_history_item(
            client,
            session_id,
            "ask_user_question",
        )
        assert question_item["status"] == "pending"
        assert question_item["payload"]["header"] == "Fairness"
        assert question_item["payload"]["options"][0]["label"] == "Effort balance (Recommended)"

        answer = await client.post(
            "/api/agent/chat/respond",
            json={
                "session_id": session_id,
                "event_id": question_item["id"],
                "selected_options": ["Effort balance (Recommended)"],
            },
        )
        assert answer.status_code == 200

        history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
        )

    assert captured_prompts
    assert "request_user_input" in captured_prompts[0]
    assert "AskUserQuestion" not in captured_prompts[0]
    updated_question = next(item for item in history_payload["items"] if item["id"] == question_item["id"])
    assert updated_question["payload"]["answered"] is True
    assert updated_question["payload"]["answer_value"] == "Effort balance (Recommended)"
    assert "Great, I will use effort balance" not in assistant_item["payload"]["content"]
    assert "ChoreFlow will use effort-balanced chore rotation" in assistant_item["payload"]["content"]
    assert "backlog" not in assistant_item["payload"]["content"].lower()
    assert "sprint" not in assistant_item["payload"]["content"].lower()
    assert "task" not in assistant_item["payload"]["content"].lower()

@pytest.mark.asyncio
async def test_tool_approval_card_can_be_denied_and_run_continues(monkeypatch, test_db, tmp_path):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async def fake_run_phase(self, **kwargs):
        permission = await kwargs["can_use_tool"](
            "Bash",
            {"command": "npm publish", "description": "Publish the package"},
            {},
        )
        assert "wait" in getattr(permission, "message", "")
        return RunResult(
            session_id="sdk-session-approval",
            cost_usd=0.03,
            tokens_input=9,
            tokens_output=7,
            num_turns=2,
            output_text="Understood. I will not publish anything yet.",
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
        response = await client.post("/api/agent/chat", json={"message": "Release this package"})
        session_id = response.json()["session_id"]

        _, approval_item = await _wait_for_history_item(client, session_id, "tool_approval_request")
        assert approval_item["payload"]["tool_name"] == "Bash"

        answer = await client.post(
            "/api/agent/chat/respond",
            json={
                "session_id": session_id,
                "event_id": approval_item["id"],
                "decision": "deny",
                "reason": "User prefers to wait for manual release approval.",
            },
        )
        assert answer.status_code == 200

        history_payload, assistant_item = await _wait_for_history_item(
            client, session_id, "assistant_message"
        )

    updated_approval = next(item for item in history_payload["items"] if item["id"] == approval_item["id"])
    assert updated_approval["payload"]["answered"] is True
    assert updated_approval["payload"]["decision"] == "deny"
    assert assistant_item["payload"]["content"] == "Understood. I will not publish anything yet."
