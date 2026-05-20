"""Agent documentation-specialist chat route regressions."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import (
    Feature,
    FeatureStatus,
    Project,
    Task,
)
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server import agent_sprint_planning
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from tests.agent_route_test_support import (
    approve_pending_sprint_scope as _approve_pending_sprint_scope,
)
from tests.agent_route_test_support import (
    create_project_feature_task as _create_project_feature_task,
)
from tests.agent_route_test_support import (
    wait_for_history_item as _wait_for_history_item,
)
from tests.agent_route_test_support import (
    write_forward_engineering_ready_state as _write_forward_engineering_ready_state,
)


@pytest.mark.asyncio
async def test_chat_routes_explicit_documentation_intent_to_subagent(monkeypatch, test_db, tmp_path):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")
    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured.update(kwargs)
        await kwargs["on_tool_event"](
            {
                "tool_name": "mcp__builder__kb_add",
                "tool_input": {"doc_type": "feature", "title": "Feature Doc"},
                "tool_response": {"status": "ok"},
                "tool_use_id": "toolu_publish",
            }
        )
        await kwargs["on_tool_event"](
            {
                "tool_name": "mcp__builder__kb_validate",
                "tool_input": {"kb_dir": "system-docs"},
                "tool_response": {"passed": True, "summary": "KB validation passed"},
                "tool_use_id": "toolu_validate",
            }
        )
        return RunResult(
            session_id="sdk-session-doc-route",
            cost_usd=0.02,
            tokens_input=10,
            tokens_output=12,
            num_turns=2,
            output_text="updated and verified",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)
    monkeypatch.setattr(agent_sprint_planning, "schedule_task_dispatch", fake_schedule_task_dispatch)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/agent/chat", json={"message": "is documentation updated?"})
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        history_payload, _ = await _wait_for_history_item(
            client,
            session_id,
            "specialist_status",
            predicate=lambda item: item["payload"].get("phase") == "completed",
        )

    assert captured["subagents"] == ("documentation-agent",)
    assert "Documentation routing is active for this turn." in captured["prompt"]
    assert "shared product knowledge for both users and future agents" in captured["prompt"]
    assert '"canonical_ref": "main"' in captured["prompt"]
    assert '"freshness_candidates"' in captured["prompt"]
    assert '"resolved_action": "advisory_only"' in captured["prompt"]
    assert '"target_doc_type": "system-docs"' in captured["prompt"]
    assert "Refresh `system-docs` through the canonical extraction lane" in captured["prompt"]
    phases = [
        item["payload"]["phase"]
        for item in history_payload["items"]
        if item["type"] == "specialist_status"
    ]
    assert "discovering" in phases
    assert "publishing" in phases
    assert "verifying" in phases
    assert "completed" in phases
    specialist_item = next(item for item in history_payload["items"] if item["type"] == "specialist_status")
    assert specialist_item["payload"]["diagnostic"]["kind"] == "specialist_status"

@pytest.mark.asyncio
async def test_chat_does_not_route_unrelated_message_to_documentation_subagent(
    monkeypatch, test_db, tmp_path
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")
    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured.update(kwargs)
        return RunResult(
            session_id="sdk-session-no-doc-route",
            cost_usd=0.0,
            tokens_input=1,
            tokens_output=1,
            num_turns=1,
            output_text="Here is the codebase summary.",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)
    monkeypatch.setattr(agent_sprint_planning, "schedule_task_dispatch", fake_schedule_task_dispatch)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/agent/chat", json={"message": "what files are in this repo?"})
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        history_payload, _ = await _wait_for_history_item(client, session_id, "assistant_message")

    assert captured["subagents"] is None
    assert "Documentation routing is active for this turn." not in captured["prompt"]
    assert all(item["type"] != "specialist_status" for item in history_payload["items"])

@pytest.mark.asyncio
async def test_chat_proactively_routes_when_latest_task_requires_docs(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")
    await _create_project_feature_task(
        factory,
        project_name="demo",
        feature_title="Task-scoped KB requirement docs",
        task_title="Refresh maintained docs",
        task_description="Keep maintained feature and testing knowledge current after implementation.",
        depends_on={"system_docs": {"required_docs": ["reverse-engineering/system-architecture.md"]}},
    )
    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured.update(kwargs)
        return RunResult(
            session_id="sdk-session-proactive-doc-route",
            cost_usd=0.01,
            tokens_input=3,
            tokens_output=4,
            num_turns=1,
            output_text="already current",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)
    monkeypatch.setattr(agent_sprint_planning, "schedule_task_dispatch", fake_schedule_task_dispatch)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "I just implemented the change and want you to check it."},
        )
        session_id = response.json()["session_id"]
        history_payload, _ = await _wait_for_history_item(client, session_id, "assistant_message")

    assert response.status_code == 200
    assert captured["subagents"] == ("documentation-agent",)
    assert "active_task_doc_expectation" in captured["prompt"]
    assert "required_docs" in captured["prompt"]

@pytest.mark.asyncio
async def test_chat_feature_spec_request_does_not_trigger_documentation_specialist(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")
    await _create_project_feature_task(
        factory,
        project_name="demo",
        feature_title="Task-scoped KB requirement docs",
        task_title="Refresh maintained docs",
        task_description="Keep maintained feature and testing knowledge current after implementation.",
        depends_on={"system_docs": {"required_docs": ["reverse-engineering/system-architecture.md"]}},
    )
    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured.update(kwargs)
        return RunResult(
            session_id="sdk-session-feature-spec-route",
            cost_usd=0.01,
            tokens_input=4,
            tokens_output=5,
            num_turns=1,
            output_text=(
                "AGREEMENT: Add bookmark support for saved posts.\n\n"
                'FEATURE_SPEC_JSON: {"title":"Post bookmarks","description":"Allow signed-in '
                'users to save and review bookmarked posts.","priority":72,'
                '"acceptance_criteria":["Users can bookmark and unbookmark posts"],'
                '"dependencies":[]}'
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
            json={
                "message": (
                    "Create a bounded feature spec to add post bookmarks so users can save posts "
                    "and view them from their profile."
                )
            },
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        history_payload, _assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
        )

    assert captured["subagents"] is None
    assert "Documentation routing is active for this turn." not in captured["prompt"]
    assert "FEATURE_SPEC_JSON:" in captured["prompt"]
    assert all(item["type"] != "specialist_status" for item in history_payload["items"])

@pytest.mark.asyncio
async def test_mission_aligned_delivery_prompt_does_not_route_to_documentation_agent(
    monkeypatch, test_db, tmp_path
):
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)
    monkeypatch.setattr(agent_sprint_planning, "schedule_task_dispatch", fake_schedule_task_dispatch)
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")
    _write_forward_engineering_ready_state(tmp_path)

    _, factory = test_db
    async with factory() as db:
        project = Project(name="todo-app", description="Todo app", language="javascript")
        db.add(project)
        await db.flush()
        shipped_feature = Feature(
            project_id=project.id,
            title="Existing shipped work",
            description="Already shipped.",
            status=FeatureStatus.DONE,
            priority=100,
        )
        next_feature = Feature(
            project_id=project.id,
            title="Today List View",
            description="Show tasks due today.",
            status=FeatureStatus.BACKLOG,
            priority=90,
            acceptance_criteria=["Today tasks are visible"],
        )
        db.add_all([shipped_feature, next_feature])
        await db.flush()
        db.add(
            Task(
                feature_id=shipped_feature.id,
                title="Refresh feature documentation",
                description="Documentation follow-up from the last sprint.",
                status="done",
                depends_on={"system_docs": {"required_docs": ["system-docs/system-architecture.md"]}},
            )
        )
        setup_project = Project(
            name="onboarding-project",
            description="Builder setup project created after the todo app.",
            language="python",
        )
        db.add(setup_project)
        await db.flush()
        db.add(
            Feature(
                project_id=setup_project.id,
                title="Seed operator workspace and backlog surfaces",
                description="Setup backlog for the builder operator workspace.",
                status=FeatureStatus.BACKLOG,
                priority=99,
            )
        )
        await db.commit()

    async def fake_run_phase(self, **kwargs):
        raise AssertionError("delivery continuation should use lifecycle planning, not chat subagents")

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)
    monkeypatch.setattr(agent_sprint_planning, "schedule_task_dispatch", fake_schedule_task_dispatch)

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
                    "Continue building this todo app. Ship the next useful improvement "
                    "and tell me when it is ready."
                )
            },
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        await _approve_pending_sprint_scope(client, session_id)
        history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Builder prepared the work" in item["payload"].get("content", ""),
        )

    assert "Today List View" in assistant_item["payload"]["content"]
    assert dispatched
    assert all(item["type"] != "specialist_status" for item in history_payload["items"])
    assert all(item["type"] != "ask_user_question" for item in history_payload["items"])
