from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import ChatEvent, ChatSession, Feature, Project, Task
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from autonomous_agent_builder.embedded.server.app import create_app


def _write_forward_engineering_ready_state(tmp_path) -> None:
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True, exist_ok=True)
    (agent_builder_dir / "onboarding-state.json").write_text(
        json.dumps(
            {
                "repo": {"root": str(tmp_path), "name": tmp_path.name},
                "onboarding_mode": "forward_engineering",
                "current_phase": "ready",
                "ready": True,
                "updated_at": "2026-04-20T00:00:00+00:00",
                "phases": [],
                "entity_counts": {"projects": 1, "features": 0, "tasks": 0},
                "kb_status": {},
                "scan_summary": {},
                "archives": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )


async def _create_chat_session(
    factory,
    *,
    repo_identity: str | None,
    workspace_cwd: str | None,
    updated_at: datetime,
    events: list[tuple[str, dict]] | None = None,
) -> str:
    async with factory() as db:
        session = ChatSession(
            repo_identity=repo_identity,
            workspace_cwd=workspace_cwd,
            updated_at=updated_at,
        )
        db.add(session)
        await db.flush()
        for event_type, payload in events or []:
            db.add(
                ChatEvent(
                    session_id=session.id,
                    event_type=event_type,
                    payload_json=payload,
                    status="completed",
                )
            )
        await db.commit()
        return session.id


async def _append_chat_event(
    factory,
    *,
    session_id: str,
    event_type: str,
    payload: dict,
    created_at: datetime,
) -> None:
    async with factory() as db:
        db.add(
            ChatEvent(
                session_id=session_id,
                event_type=event_type,
                payload_json=payload,
                status="completed",
                created_at=created_at,
            )
        )
        await db.commit()


async def _create_project_feature_task(
    factory,
    *,
    project_name: str,
    feature_title: str,
    task_title: str,
    task_description: str,
    depends_on: dict | None = None,
) -> tuple[str, str, str]:
    async with factory() as db:
        project = Project(name=project_name, description="demo", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(project_id=project.id, title=feature_title, description="feature")
        db.add(feature)
        await db.flush()
        task = Task(
            feature_id=feature.id,
            title=task_title,
            description=task_description,
            depends_on=depends_on,
        )
        db.add(task)
        await db.commit()
        return project.id, feature.id, task.id


async def _wait_for_history_item(
    client: AsyncClient,
    session_id: str,
    item_type: str,
    *,
    timeout: float = 3.0,
    predicate=None,
):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        response = await client.get("/api/agent/chat/history", params={"session_id": session_id})
        assert response.status_code == 200
        payload = response.json()
        for item in payload["items"]:
            if item["type"] == item_type and (predicate is None or predicate(item)):
                return payload, item
        await asyncio.sleep(0.05)
    raise AssertionError(f"Timed out waiting for history item type '{item_type}'")


@pytest.mark.parametrize(
    ("message", "expected_scope"),
    [
        ("can documentation also be generated on testing required", "testing_required"),
        ("can documentation also be generated on testing by feature", "testing_by_feature"),
        (
            "can documentation also be generated on full reverse engineering testing starting from onboarding",
            "reverse_engineering",
        ),
        (
            "can documentation also be generated on forward engineering testing again from onboarding",
            "forward_engineering",
        ),
        ("can documentation also be generated on full end-to-end autonomous builder testing", "end_to_end"),
    ],
)
def test_resolve_documentation_action_adds_missing_testing_docs(message, expected_scope):
    resolution = agent_routes._resolve_documentation_action(
        user_message=message,
        targeted_docs=[],
        current_branch="feature/docs",
    )

    assert resolution == {
        "action": "add",
        "target_doc_type": "testing",
        "mode": "create",
        "testing_scope": expected_scope,
        "freshness_mode": "advisory",
        "doc_id": "",
        "requires_validate": True,
        "doc_exists": False,
        "targeted_doc_count": 0,
        "retry_budget": 1,
    }


def test_resolve_documentation_action_updates_existing_single_doc():
    resolution = agent_routes._resolve_documentation_action(
        user_message="Update the onboarding testing doc",
        targeted_docs=[{"id": "testing/onboarding.md", "doc_type": "testing"}],
        current_branch="main",
    )

    assert resolution["action"] == "update"
    assert resolution["target_doc_type"] == "testing"
    assert resolution["doc_id"] == "testing/onboarding.md"
    assert resolution["requires_validate"] is True


def test_resolve_documentation_action_extracts_system_docs_on_main():
    resolution = agent_routes._resolve_documentation_action(
        user_message="Check whether the knowledge base is current for this repo.",
        targeted_docs=[],
        current_branch="main",
    )

    assert resolution["action"] == "extract"
    assert resolution["target_doc_type"] == "system-docs"
    assert resolution["mode"] == "refresh"
    assert resolution["freshness_mode"] == "canonical"


def test_resolve_documentation_action_keeps_non_main_freshness_advisory():
    resolution = agent_routes._resolve_documentation_action(
        user_message="Check whether the knowledge base is current for this repo.",
        targeted_docs=[],
        current_branch="feature/docs",
    )

    assert resolution["action"] == "advisory_only"
    assert resolution["target_doc_type"] == "system-docs"
    assert resolution["requires_validate"] is False


def test_documentation_continuation_matcher_accepts_short_follow_ups():
    assert agent_routes._message_matches_documentation_continuation("please update")
    assert agent_routes._message_matches_documentation_continuation("go ahead.")
    assert not agent_routes._message_matches_documentation_continuation(
        "please update the billing implementation docs and tests"
    )


@pytest.mark.asyncio
async def test_select_specialist_route_reactivates_previous_documentation_specialist(test_db, tmp_path):
    _, factory = test_db
    now = datetime.now(UTC)
    session_id = await _create_chat_session(
        factory,
        repo_identity=str(tmp_path.resolve()),
        workspace_cwd=str(tmp_path.resolve()),
        updated_at=now,
    )
    await _append_chat_event(
        factory,
        session_id=session_id,
        event_type="user_message",
        payload={"content": "check docs"},
        created_at=now - timedelta(minutes=3),
    )
    await _append_chat_event(
        factory,
        session_id=session_id,
        event_type="specialist_status",
        payload={"specialist": "documentation-agent", "phase": "completed", "content": "done"},
        created_at=now - timedelta(minutes=2),
    )
    await _append_chat_event(
        factory,
        session_id=session_id,
        event_type="assistant_message",
        payload={"content": "stale docs found"},
        created_at=now - timedelta(minutes=1),
    )
    await _append_chat_event(
        factory,
        session_id=session_id,
        event_type="user_message",
        payload={"content": "please update"},
        created_at=now,
    )

    async with factory() as db:
        route = await agent_routes._select_specialist_route(
            db,
            tmp_path,
            session_id,
            "please update",
        )

    assert route is not None
    assert route.name == "documentation-agent"
    assert route.route_reason == "specialist_continuation:documentation-agent"
    assert route.context["route_reason"] == "specialist_continuation:documentation-agent"


@pytest.mark.asyncio
async def test_select_specialist_route_does_not_continue_without_previous_specialist(test_db, tmp_path):
    _, factory = test_db
    now = datetime.now(UTC)
    session_id = await _create_chat_session(
        factory,
        repo_identity=str(tmp_path.resolve()),
        workspace_cwd=str(tmp_path.resolve()),
        updated_at=now,
    )
    await _append_chat_event(
        factory,
        session_id=session_id,
        event_type="user_message",
        payload={"content": "hello"},
        created_at=now - timedelta(minutes=1),
    )
    await _append_chat_event(
        factory,
        session_id=session_id,
        event_type="assistant_message",
        payload={"content": "hi"},
        created_at=now - timedelta(seconds=30),
    )
    await _append_chat_event(
        factory,
        session_id=session_id,
        event_type="user_message",
        payload={"content": "please update"},
        created_at=now,
    )

    async with factory() as db:
        route = await agent_routes._select_specialist_route(
            db,
            tmp_path,
            session_id,
            "please update",
        )

    assert route is None


@pytest.mark.asyncio
async def test_select_specialist_route_does_not_continue_unrelated_message(test_db, tmp_path):
    _, factory = test_db
    now = datetime.now(UTC)
    session_id = await _create_chat_session(
        factory,
        repo_identity=str(tmp_path.resolve()),
        workspace_cwd=str(tmp_path.resolve()),
        updated_at=now,
    )
    await _append_chat_event(
        factory,
        session_id=session_id,
        event_type="user_message",
        payload={"content": "check docs"},
        created_at=now - timedelta(minutes=3),
    )
    await _append_chat_event(
        factory,
        session_id=session_id,
        event_type="specialist_status",
        payload={"specialist": "documentation-agent", "phase": "completed", "content": "done"},
        created_at=now - timedelta(minutes=2),
    )
    await _append_chat_event(
        factory,
        session_id=session_id,
        event_type="user_message",
        payload={"content": "build the API instead"},
        created_at=now,
    )

    async with factory() as db:
        route = await agent_routes._select_specialist_route(
            db,
            tmp_path,
            session_id,
            "build the API instead",
        )

    assert route is None


@pytest.mark.asyncio
async def test_select_specialist_route_prefers_explicit_specialist_over_continuation(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    now = datetime.now(UTC)
    session_id = await _create_chat_session(
        factory,
        repo_identity=str(tmp_path.resolve()),
        workspace_cwd=str(tmp_path.resolve()),
        updated_at=now,
    )
    await _append_chat_event(
        factory,
        session_id=session_id,
        event_type="user_message",
        payload={"content": "check docs"},
        created_at=now - timedelta(minutes=2),
    )
    await _append_chat_event(
        factory,
        session_id=session_id,
        event_type="specialist_status",
        payload={"specialist": "documentation-agent", "phase": "completed", "content": "done"},
        created_at=now - timedelta(minutes=1),
    )
    await _append_chat_event(
        factory,
        session_id=session_id,
        event_type="user_message",
        payload={"content": "go ahead"},
        created_at=now,
    )

    async def fake_context_builder(db, project_root, user_message, **kwargs):
        return {"route_reason": kwargs.get("route_reason_override", "explicit_intent")}

    fake_policy = agent_routes.SpecialistRoutePolicy(
        name="architecture-reviewer",
        explicit_intent_matcher=lambda message: agent_routes._normalized_follow_up_message(message) == "go ahead",
        continuation_matcher=lambda message: False,
        context_builder=fake_context_builder,
        auto_approve_tools=frozenset(),
        active_summary="Architecture reviewer active.",
        blocked_summary="Architecture reviewer blocked.",
        completed_summary="Architecture review complete.",
    )
    monkeypatch.setattr(
        agent_routes,
        "_SPECIALIST_ROUTE_POLICIES",
        {
            "architecture-reviewer": fake_policy,
            **agent_routes._SPECIALIST_ROUTE_POLICIES,
        },
    )

    async with factory() as db:
        route = await agent_routes._select_specialist_route(
            db,
            tmp_path,
            session_id,
            "go ahead",
        )

    assert route is not None
    assert route.name == "architecture-reviewer"
    assert route.route_reason == "explicit_intent"


@pytest.mark.asyncio
async def test_chat_history_reports_model_without_session(test_db, tmp_path):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agent/chat/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == ""
    assert payload["model"] == "haiku"
    assert payload["items"] == []
    assert payload["messages"] == []
    assert payload["repo_identity"] == str(tmp_path.resolve())
    assert payload["workspace_cwd"] == str(tmp_path.resolve())


@pytest.mark.asyncio
async def test_chat_history_defaults_to_latest_meaningful_scoped_session(test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    repo_identity = str(tmp_path.resolve())
    now = datetime.now(UTC)
    expected_session_id = await _create_chat_session(
        factory,
        repo_identity=repo_identity,
        workspace_cwd=repo_identity,
        updated_at=now - timedelta(minutes=5),
        events=[
            ("user_message", {"content": "Continue the repo-scoped thread"}),
            ("assistant_message", {"content": "Resuming the latest meaningful session", "final": True}),
        ],
    )
    await _create_chat_session(
        factory,
        repo_identity="/tmp/other-project",
        workspace_cwd="/tmp/other-project",
        updated_at=now,
        events=[
            ("user_message", {"content": "Wrong repo"}),
            ("assistant_message", {"content": "Should never be selected", "final": True}),
        ],
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agent/chat/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == expected_session_id
    assert payload["items"][0]["payload"]["content"] == "Continue the repo-scoped thread"


@pytest.mark.asyncio
async def test_chat_history_fresh_mode_skips_latest_session_resume(test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    repo_identity = str(tmp_path.resolve())
    now = datetime.now(UTC)
    await _create_chat_session(
        factory,
        repo_identity=repo_identity,
        workspace_cwd=repo_identity,
        updated_at=now - timedelta(minutes=1),
        events=[
            ("user_message", {"content": "Resume me"}),
            ("assistant_message", {"content": "Meaningful transcript", "final": True}),
        ],
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agent/chat/history", params={"fresh": "1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == ""
    assert payload["items"] == []
    assert payload["messages"] == []


@pytest.mark.asyncio
async def test_chat_session_list_filters_wrong_repo_and_marks_latest_resume_candidate(test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    repo_identity = str(tmp_path.resolve())
    now = datetime.now(UTC)
    older_session_id = await _create_chat_session(
        factory,
        repo_identity=repo_identity,
        workspace_cwd=repo_identity,
        updated_at=now - timedelta(minutes=10),
        events=[("assistant_message", {"content": "Bootstrap only", "final": True})],
    )
    latest_resume_id = await _create_chat_session(
        factory,
        repo_identity=repo_identity,
        workspace_cwd=repo_identity,
        updated_at=now - timedelta(minutes=2),
        events=[
            ("user_message", {"content": "Resume me"}),
            ("assistant_message", {"content": "Meaningful transcript", "final": True}),
        ],
    )
    await _create_chat_session(
        factory,
        repo_identity="/tmp/wrong-project",
        workspace_cwd="/tmp/wrong-project",
        updated_at=now,
        events=[("user_message", {"content": "Foreign session"})],
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agent/chat/sessions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_resume_session_id"] == latest_resume_id
    assert [session["id"] for session in payload["sessions"]] == [latest_resume_id, older_session_id]
    assert payload["sessions"][0]["is_resume_candidate"] is True
    assert payload["sessions"][1]["is_resume_candidate"] is False


@pytest.mark.asyncio
async def test_chat_history_rejects_wrong_project_session_id(test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    foreign_session_id = await _create_chat_session(
        factory,
        repo_identity="/tmp/other-project",
        workspace_cwd="/tmp/other-project",
        updated_at=datetime.now(UTC),
        events=[("user_message", {"content": "Do not load me"})],
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/agent/chat/history", params={"session_id": foreign_session_id})

    assert response.status_code == 409
    assert "different repo or workspace" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_post_rejects_wrong_project_session_id(monkeypatch, test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async def fake_run_phase(self, **kwargs):
        return RunResult(
            session_id="sdk-session-ignored",
            cost_usd=0.0,
            tokens_input=0,
            tokens_output=0,
            num_turns=1,
            output_text="Should not run",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )

    foreign_session_id = await _create_chat_session(
        factory,
        repo_identity="/tmp/other-project",
        workspace_cwd="/tmp/other-project",
        updated_at=datetime.now(UTC),
        events=[("user_message", {"content": "Do not post into me"})],
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
            json={"message": "hello", "session_id": foreign_session_id},
        )

    assert response.status_code == 409
    assert "different repo or workspace" in response.json()["detail"]


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
        history_payload, _ = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
        )

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
        await _wait_for_history_item(client, session_id, "assistant_message")

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
async def test_chat_feature_spec_request_creates_backlog_feature(
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
        return RunResult(
            session_id="sdk-session-feature-spec-create",
            cost_usd=0.02,
            tokens_input=8,
            tokens_output=12,
            num_turns=1,
            output_text=(
                "AGREEMENT: Add bookmark support as one bounded feature.\n\n"
                'FEATURE_SPEC_JSON: {"title":"Post bookmarks","description":"Allow signed-in '
                'users to save posts and review them from profile pages.","priority":77,'
                '"acceptance_criteria":["Users can bookmark and unbookmark a post",'
                '"Users can open a bookmarks list from their profile"],'
                '"dependencies":["Existing Flask-Login session flow"]}'
            ),
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
            json={"message": "Create a bounded feature spec for post bookmarks."},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Feature saved to backlog" in item["payload"].get("content", ""),
        )
        features_response = await client.get("/api/dashboard/features")
        feature_payload = features_response.json()
        created_feature = next(feature for feature in feature_payload["features"] if feature["title"] == "Post bookmarks")
        tasks_response = await client.get(f"/api/features/{created_feature['id']}/tasks")

    assert "Feature saved to backlog as `Post bookmarks`." in assistant_item["payload"]["content"]
    payload = feature_payload
    assert any(feature["title"] == "Post bookmarks" for feature in payload["features"])
    assert created_feature["priority"] == "77"
    assert "bookmark and unbookmark a post" in created_feature["description"]
    assert tasks_response.json() == []
    assert dispatched == []
    assert any(item["type"] == "assistant_message" for item in history_payload["items"])


@pytest.mark.asyncio
async def test_chat_natural_feature_request_routes_into_feature_backlog_lane(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        db.add(Project(name="demo", description="demo", language="python"))
        await db.commit()

    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured.update(kwargs)
        return RunResult(
            session_id="sdk-session-natural-feature-route",
            cost_usd=0.02,
            tokens_input=8,
            tokens_output=12,
            num_turns=1,
            output_text=(
                "AGREEMENT: Add bookmark support as one bounded feature.\n\n"
                'FEATURE_SPEC_JSON: {"title":"Post bookmarks","description":"Allow signed-in '
                'users to save posts and review them from profile pages.","priority":77,'
                '"acceptance_criteria":["Users can bookmark and unbookmark a post",'
                '"Users can open a bookmarks list from their profile"],'
                '"dependencies":["Existing Flask-Login session flow"]}'
            ),
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
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Feature saved to backlog" in item["payload"].get("content", ""),
        )
        features_response = await client.get("/api/dashboard/features")
        feature_payload = features_response.json()
        created_feature = next(feature for feature in feature_payload["features"] if feature["title"] == "Post bookmarks")
        tasks_response = await client.get(f"/api/features/{created_feature['id']}/tasks")

    assert captured["subagents"] is None
    assert "FEATURE_SPEC_JSON:" in str(captured["prompt"])
    assert "Documentation routing is active for this turn." not in str(captured["prompt"])
    payload = feature_payload
    assert any(feature["title"] == "Post bookmarks" for feature in payload["features"])
    tasks = tasks_response.json()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Deliver Post bookmarks"
    assert dispatched == [tasks[0]["id"]]
    assert "Created task `Deliver Post bookmarks` and started planning dispatch." in assistant_item["payload"]["content"]


@pytest.mark.asyncio
async def test_chat_feature_spec_can_use_ask_user_question_and_resume_to_feature_save(
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
        permission = await kwargs["can_use_tool"](
            "AskUserQuestion",
            {
                "questions": [
                    {
                        "header": "Bookmarks",
                        "question": "Where should bookmarks appear on the profile?",
                        "options": [
                            {
                                "label": "Dedicated tab",
                                "description": "Clearer first release and simpler routing. (Recommended)",
                            },
                            {
                                "label": "Activity feed",
                                "description": "Mix bookmarks into the existing profile activity stream.",
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
        assert updated_input["answers"]["Where should bookmarks appear on the profile?"] == "Dedicated tab"
        return RunResult(
            session_id="sdk-session-feature-question",
            cost_usd=0.03,
            tokens_input=10,
            tokens_output=16,
            num_turns=2,
            output_text=(
                "AGREEMENT: Add private post bookmarking with a dedicated profile tab.\n\n"
                'FEATURE_SPEC_JSON: {"title":"Private Post Bookmarks","description":"Allow '
                'signed-in users to bookmark posts privately and review them from a dedicated '
                'Bookmarks tab on their own profile.","priority":80,'
                '"acceptance_criteria":["Users can bookmark and unbookmark a post",'
                '"Users can open a dedicated Bookmarks tab from their own profile"],'
                '"dependencies":[]}'
            ),
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

        _, question_item = await _wait_for_history_item(client, session_id, "ask_user_question")
        assert question_item["status"] == "pending"
        assert question_item["payload"]["recommended_index"] == 0

        answer = await client.post(
            "/api/agent/chat/respond",
            json={
                "session_id": session_id,
                "event_id": question_item["id"],
                "selected_options": ["Dedicated tab"],
            },
        )
        assert answer.status_code == 200

        history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Feature saved to backlog" in item["payload"].get("content", ""),
        )
        features_response = await client.get("/api/dashboard/features")
        feature_payload = features_response.json()
        created_feature = next(
            feature for feature in feature_payload["features"] if feature["title"] == "Private Post Bookmarks"
        )
        tasks_response = await client.get(f"/api/features/{created_feature['id']}/tasks")

    updated_question = next(item for item in history_payload["items"] if item["id"] == question_item["id"])
    assert updated_question["payload"]["answered"] is True
    assert updated_question["payload"]["answer_value"] == "Dedicated tab"
    tasks = tasks_response.json()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Deliver Private Post Bookmarks"
    assert dispatched == [tasks[0]["id"]]
    assert "Created task `Deliver Private Post Bookmarks` and started planning dispatch." in assistant_item["payload"]["content"]


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
            predicate=lambda item: "Feature saved to backlog" in item["payload"].get("content", ""),
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
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Deliver Private Post Bookmarking"
    assert dispatched == [tasks[0]["id"]]
    assert len(captured_prompts) == 2
    assert "When there are a few clear choices, use AskUserQuestion" in captured_prompts[1]
    assert "continue the interview until the first implementation scope has no obvious gaps" in captured_prompts[1]
    assert "Created task `Deliver Private Post Bookmarking` and started planning dispatch." in assistant_item["payload"]["content"]


@pytest.mark.asyncio
async def test_chat_post_starts_background_run_and_persists_timeline(monkeypatch, test_db, tmp_path):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

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
        response = await client.post("/api/agent/chat", json={"message": "hello", "session_id": None})

        assert response.status_code == 200
        payload = response.json()
        assert payload["model"] == "haiku"
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


@pytest.mark.asyncio
async def test_documentation_routed_kb_validate_is_auto_allowed_without_manual_approval(
    monkeypatch, test_db, tmp_path
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured["subagents"] = kwargs.get("subagents")
        permission = await kwargs["can_use_tool"](
            "mcp__builder__kb_validate",
            {"kb_dir": "system-docs"},
            {},
        )
        assert getattr(permission, "behavior", "") == "allow"
        return RunResult(
            session_id="sdk-session-kb-allow",
            cost_usd=0.01,
            tokens_input=4,
            tokens_output=4,
            num_turns=1,
            output_text="KB validation allowed.",
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
            json={"message": "Check whether the knowledge base is current for this repo."},
        )
        session_id = response.json()["session_id"]
        history_payload, assistant_item = await _wait_for_history_item(
            client, session_id, "assistant_message"
        )

    assert captured["subagents"] == ("documentation-agent",)
    assert assistant_item["payload"]["content"] == "KB validation allowed."
    assert all(item["type"] != "tool_approval_request" for item in history_payload["items"])


@pytest.mark.asyncio
async def test_documentation_routed_kb_validate_surfaces_exact_deny_reason_for_unsafe_path(
    monkeypatch, test_db, tmp_path
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured["subagents"] = kwargs.get("subagents")
        permission = await kwargs["can_use_tool"](
            "mcp__builder__kb_validate",
            {"kb_dir": "../outside"},
            {},
        )
        assert "must stay under `.agent-builder/knowledge/`" in getattr(permission, "message", "")
        return RunResult(
            session_id="sdk-session-kb-deny",
            cost_usd=0.01,
            tokens_input=4,
            tokens_output=4,
            num_turns=1,
            output_text="KB validation was denied.",
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
            json={"message": "Check whether the knowledge base is current for this repo."},
        )
        session_id = response.json()["session_id"]
        history_payload, tool_item = await _wait_for_history_item(
            client,
            session_id,
            "tool_error",
            predicate=lambda item: item["payload"].get("tool_name") == "mcp__builder__kb_validate",
        )

    assert captured["subagents"] == ("documentation-agent",)
    assert tool_item["payload"]["diagnostic"]["summary"] == "mcp__builder__kb_validate denied"
    assert "must stay under `.agent-builder/knowledge/`" in tool_item["payload"]["diagnostic"]["error_message"]
    assert 'Retry with `{"kb_dir":"system-docs"}`' in tool_item["payload"]["diagnostic"]["next_action"]
    assert all(item["type"] != "tool_approval_request" for item in history_payload["items"])


@pytest.mark.asyncio
async def test_documentation_routed_kb_tools_skip_interactive_approval(monkeypatch, test_db, tmp_path):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured["subagents"] = kwargs.get("subagents")
        permission = await kwargs["can_use_tool"](
            "mcp__builder__kb_show",
            {"doc_id": "system-docs/system-architecture.md"},
            {},
        )
        updated_input = getattr(permission, "updated_input", None) or getattr(
            permission, "updatedInput", None
        )
        assert updated_input == {"doc_id": "system-docs/system-architecture.md"}
        return RunResult(
            session_id="sdk-session-docs-auto-approve",
            cost_usd=0.02,
            tokens_input=8,
            tokens_output=6,
            num_turns=1,
            output_text="Docs checked without approval.",
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
            json={"message": "Check whether the knowledge base is current for this repo."},
        )
        session_id = response.json()["session_id"]
        history_payload, assistant_item = await _wait_for_history_item(
            client, session_id, "assistant_message"
        )

    assert captured["subagents"] == ("documentation-agent",)
    assert all(item["type"] != "tool_approval_request" for item in history_payload["items"])
    assert assistant_item["payload"]["content"] == "Docs checked without approval."


@pytest.mark.asyncio
async def test_documentation_follow_up_continuation_keeps_kb_tools_auto_approved(
    monkeypatch, test_db, tmp_path
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    captured_prompts: list[str] = []

    async def fake_run_phase(self, **kwargs):
        captured_prompts.append(kwargs["prompt"])
        if len(captured_prompts) == 1:
            return RunResult(
                session_id="sdk-session-docs-initial",
                cost_usd=0.02,
                tokens_input=8,
                tokens_output=6,
                num_turns=1,
                output_text="Docs are stale.",
            )
        permission = await kwargs["can_use_tool"](
            "mcp__builder__kb_show",
            {"doc_id": "system-docs/system-architecture.md"},
            {},
        )
        updated_input = getattr(permission, "updated_input", None) or getattr(
            permission, "updatedInput", None
        )
        assert updated_input == {"doc_id": "system-docs/system-architecture.md"}
        return RunResult(
            session_id="sdk-session-docs-follow-up",
            cost_usd=0.02,
            tokens_input=8,
            tokens_output=6,
            num_turns=1,
            output_text="updated and verified",
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
        first = await client.post(
            "/api/agent/chat",
            json={"message": "Check whether the knowledge base is current for this repo."},
        )
        session_id = first.json()["session_id"]
        await _wait_for_history_item(client, session_id, "assistant_message")

        second = await client.post(
            "/api/agent/chat",
            json={"message": "please update", "session_id": session_id},
        )
        assert second.status_code == 200
        history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: item["payload"]["content"] == "updated and verified",
        )

    continuation_status = [
        item
        for item in history_payload["items"]
        if item["type"] == "specialist_status"
        and item["payload"].get("route_reason") == "specialist_continuation:documentation-agent"
    ]
    assert continuation_status
    assert all(item["type"] != "tool_approval_request" for item in history_payload["items"])
    assert "specialist_continuation:documentation-agent" in captured_prompts[1]
    assert assistant_item["payload"]["content"] == "updated and verified"


@pytest.mark.asyncio
async def test_documentation_routed_kb_contract_and_lint_skip_interactive_approval(
    monkeypatch, test_db, tmp_path
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured["subagents"] = kwargs.get("subagents")
        captured["prompt"] = kwargs["prompt"]
        contract_permission = await kwargs["can_use_tool"](
            "mcp__builder__kb_contract",
            {"doc_type": "testing", "sample_title": "Testing Required"},
            {},
        )
        lint_permission = await kwargs["can_use_tool"](
            "mcp__builder__kb_lint",
            {"doc_type": "testing", "content": "# draft"},
            {},
        )
        assert getattr(contract_permission, "behavior", "") == "allow"
        assert getattr(lint_permission, "behavior", "") == "allow"
        return RunResult(
            session_id="sdk-session-docs-contract-lint",
            cost_usd=0.02,
            tokens_input=8,
            tokens_output=6,
            num_turns=1,
            output_text="Contract and lint ran without approval.",
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
            json={"message": "Can documentation also be generated on testing required?"},
        )
        session_id = response.json()["session_id"]
        history_payload, assistant_item = await _wait_for_history_item(
            client, session_id, "assistant_message"
        )

    assert captured["subagents"] == ("documentation-agent",)
    assert '"resolved_action": "add"' in captured["prompt"]
    assert '"target_doc_type": "testing"' in captured["prompt"]
    assert '"testing_scope": "testing_required"' in captured["prompt"]
    assert all(item["type"] != "tool_approval_request" for item in history_payload["items"])
    assert assistant_item["payload"]["content"] == "Contract and lint ran without approval."


@pytest.mark.asyncio
async def test_documentation_routed_turn_still_prompts_for_unrelated_tools(monkeypatch, test_db, tmp_path):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured["subagents"] = kwargs.get("subagents")
        permission = await kwargs["can_use_tool"](
            "Bash",
            {"command": "npm publish", "description": "Publish the package"},
            {},
        )
        assert "wait" in getattr(permission, "message", "")
        return RunResult(
            session_id="sdk-session-docs-bash-approval",
            cost_usd=0.02,
            tokens_input=8,
            tokens_output=6,
            num_turns=1,
            output_text="Blocked on manual approval.",
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
            json={"message": "Check whether the knowledge base is current for this repo."},
        )
        session_id = response.json()["session_id"]
        _, approval_item = await _wait_for_history_item(client, session_id, "tool_approval_request")

    assert captured["subagents"] == ("documentation-agent",)
    assert approval_item["payload"]["tool_name"] == "Bash"


@pytest.mark.asyncio
async def test_forward_engineering_chat_writes_feature_list(monkeypatch, test_db, tmp_path):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")
    _write_forward_engineering_ready_state(tmp_path)

    async def fake_run_phase(self, **kwargs):
        assert kwargs["agent_name"] == "init-project-chat"
        return RunResult(
            session_id="sdk-init-project-1",
            cost_usd=0.05,
            tokens_input=20,
            tokens_output=10,
            num_turns=2,
            output_text=(
                "AGREEMENT:\n"
                "We agreed on a focused MVP for a personal budgeting web app.\n\n"
                "FEATURE_LIST_JSON:\n"
                "{\n"
                '  "metadata": {"project": "budget-mvp", "done": 0, "pending": 2},\n'
                '  "features": [\n'
                '    {"id": "feature-01", "title": "Capture expenses", "description": "Log daily spending quickly.", "status": "pending", "priority": "100", "acceptance_criteria": ["Create an expense with amount and category"], "dependencies": []},\n'
                '    {"id": "feature-02", "title": "See spending summary", "description": "Show totals by category and month.", "status": "pending", "priority": "99", "acceptance_criteria": ["Monthly totals are visible"], "dependencies": ["feature-01"]}\n'
                "  ]\n"
                "}"
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
        history = await client.get("/api/agent/chat/history")
        session_id = history.json()["session_id"]
        response = await client.post(
            "/api/agent/chat",
            json={"message": "Build me a budgeting app for freelancers.", "session_id": session_id},
        )
        assert response.status_code == 200
        assert response.json()["model"] == "opus"

        feature_list = tmp_path / ".claude" / "progress" / "feature-list.json"
        deadline = asyncio.get_running_loop().time() + 3.0
        while asyncio.get_running_loop().time() < deadline:
            history_payload = (
                await client.get("/api/agent/chat/history", params={"session_id": session_id})
            ).json()
            assistant_items = [
                item for item in history_payload["items"] if item["type"] == "assistant_message"
            ]
            if assistant_items and "Feature backlog saved" in assistant_items[-1]["payload"]["content"]:
                assistant_item = assistant_items[-1]
                break
            await asyncio.sleep(0.05)
        else:
            assistant_item = assistant_items[-1]

    assert "Feature backlog saved to `.claude/progress/feature-list.json`." in assistant_item["payload"]["content"]

    assert feature_list.exists()
    feature_payload = json.loads(feature_list.read_text(encoding="utf-8"))
    assert feature_payload["metadata"]["project"] == "budget-mvp"
    assert [feature["title"] for feature in feature_payload["features"]] == [
        "Capture expenses",
        "See spending summary",
    ]
