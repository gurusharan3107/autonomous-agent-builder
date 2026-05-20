"""Agent feature-spec tooling and read-only inspection route regressions."""

from __future__ import annotations

import asyncio

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


@pytest.mark.asyncio
async def test_feature_spec_lane_allows_read_only_workspace_inspection_before_user_question(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        db.add(Project(name="demo", description="demo", language="python"))
        await db.commit()

    async def fake_run_phase(self, **kwargs):
        permission = await kwargs["can_use_tool"]("mcp__workspace__get_project_info", {}, {})
        assert getattr(permission, "behavior", "") == "allow"
        assert getattr(permission, "updated_input", {}) == {}
        return RunResult(
            session_id="sdk-session-feature-tool-allow",
            cost_usd=0.01,
            tokens_input=4,
            tokens_output=4,
            num_turns=1,
            output_text="I inspected the current repo shape before deciding what to ask next.",
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
        response = await client.post(
            "/api/agent/chat",
            json={
                "message": (
                    "I want users to be able to bookmark posts and see their bookmarks "
                    "from their profile. Can you take this through the next steps?"
                )
            },
        )
        session_id = response.json()["session_id"]
        history_payload = (await client.get("/api/agent/chat/history", params={"session_id": session_id})).json()

    assert not any(
        item["type"] == "tool_error"
        and item["payload"].get("tool_name") == "mcp__workspace__get_project_info"
        for item in history_payload["items"]
    )

@pytest.mark.asyncio
async def test_chat_auto_approves_read_only_internal_inspection_tools(
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
        for tool_name in ("mcp__builder__board", "mcp__workspace__get_project_info"):
            permission = await kwargs["can_use_tool"](tool_name, {}, {})
            assert getattr(permission, "behavior", "") == "allow"
            assert getattr(permission, "updated_input", {}) == {}
        return RunResult(
            session_id="sdk-session-read-only-auto",
            cost_usd=0.01,
            tokens_input=4,
            tokens_output=4,
            num_turns=1,
            output_text="I checked the current project state and can continue.",
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
        history_payload, _ = await _wait_for_history_item(client, session_id, "assistant_message")
        for _ in range(20):
            if history_payload["status"]["running"] is False:
                break
            await asyncio.sleep(0.05)
            history_payload = (
                await client.get("/api/agent/chat/history", params={"session_id": session_id})
            ).json()

    assert not any(item["type"] == "tool_approval_request" for item in history_payload["items"])

@pytest.mark.asyncio
async def test_chat_feature_spec_follow_up_stays_in_feature_backlog_lane(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        db.add(Project(name="demo", description="demo", language="python"))
        await db.commit()

    responses = [
        RunResult(
            session_id="sdk-session-followup-1",
            cost_usd=0.01,
            tokens_input=6,
            tokens_output=20,
            num_turns=1,
            output_text=(
                "I have one clarifying question before I finalize the scope:\n\n"
                "Should bookmarks be private to each user, or visible on other users' profiles?"
            ),
        ),
        RunResult(
            session_id="sdk-session-followup-1",
            cost_usd=0.01,
            tokens_input=4,
            tokens_output=12,
            num_turns=1,
            output_text=(
                "AGREEMENT: Add private post bookmarking as one bounded feature.\n\n"
                'FEATURE_SPEC_JSON: {"title":"Private Post Bookmarking","description":"Allow '
                'signed-in users to save posts privately and review them from their own profile.",'
                '"priority":77,"acceptance_criteria":["Users can bookmark and unbookmark a post",'
                '"Users can open a bookmarks list from their own profile"],"dependencies":[]}'
            ),
        ),
    ]
    captured_prompts: list[str] = []

    async def fake_run_phase(self, **kwargs):
        captured_prompts.append(str(kwargs["prompt"]))
        return responses.pop(0)

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
        response = await client.post(
            "/api/agent/chat",
            json={
                "message": (
                    "I want users to be able to bookmark posts and see their bookmarks "
                    "from their profile. Can you take this through the next steps?"
                )
            },
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        await _wait_for_history_item(client, session_id, "assistant_message")

        follow_up = await client.post(
            "/api/agent/chat",
            json={"session_id": session_id, "message": "Keep bookmarks private to each user."},
        )
        assert follow_up.status_code == 200
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "I captured that improvement" in item["payload"].get("content", ""),
        )
        features_response = await client.get("/api/dashboard/features")
        feature_payload = features_response.json()
        created_feature = next(
            feature for feature in feature_payload["features"] if feature["title"] == "Private Post Bookmarking"
        )
        tasks_response = await client.get(f"/api/features/{created_feature['id']}/tasks")

    payload = feature_payload
    assert any(feature["title"] == "Private Post Bookmarking" for feature in payload["features"])
    tasks = tasks_response.json()
    assert tasks == []
    assert dispatched == []
    assert len(captured_prompts) == 2
    assert "When there are a few clear choices, use AskUserQuestion" in captured_prompts[1]
    assert "continue the interview until the first implementation scope has no obvious gaps" in captured_prompts[1]
    assert "I captured that improvement as `Private Post Bookmarking`." in assistant_item["payload"]["content"]
    assert "Ready for Builder to start now" in assistant_item["payload"]["content"]
    assert "AGREEMENT:" not in assistant_item["payload"]["content"]
