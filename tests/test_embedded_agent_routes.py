from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import (
    BacklogItemType,
    ChatEvent,
    ChatSession,
    Feature,
    FeatureStatus,
    Project,
    Sprint,
    Task,
    TaskStatus,
)
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from autonomous_agent_builder.onboarding import _INIT_PROJECT_BOOTSTRAP_MESSAGE
from autonomous_agent_builder.services.readiness import (
    READY_STATE,
    assess_readiness,
    load_readiness_status,
)
from autonomous_agent_builder.services.runtime_guidance import render_project_runtime_guidance


def _write_forward_engineering_ready_state(tmp_path) -> None:
    (tmp_path / "CLAUDE.md").write_text("# Test\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        "AAB_CLAUDE_OTEL_ENABLED=1\n"
        "AAB_CLAUDE_OTEL_ENDPOINT=http://localhost:4318\n"
        "AAB_CLAUDE_OTEL_SERVICE_NAME=test\n"
        "AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID=true\n",
        encoding="utf-8",
    )
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True, exist_ok=True)
    (agent_builder_dir / "config.yaml").write_text("project:\n  name: test\n", encoding="utf-8")
    (agent_builder_dir / "agent_builder.db").write_text("", encoding="utf-8")
    phases = [
        {
            "id": phase_id,
            "title": phase_id.replace("_", " ").title(),
            "status": "passed",
            "message": "",
            "started_at": None,
            "finished_at": None,
            "result": result,
            "error": None,
        }
        for phase_id, result in (
            ("repo_detect", {}),
            ("project_seed", {}),
            ("repo_scan", {}),
            ("work_item_seed", {}),
            ("kb_extract", {"skipped": True, "reason": "forward_engineering_onboarding"}),
            ("kb_validate", {"skipped": True, "reason": "forward_engineering_onboarding"}),
        )
    ]
    phases.append(
        {
            "id": "ready",
            "title": "Ready",
            "status": "passed",
            "message": "",
            "started_at": None,
            "finished_at": None,
            "result": {"ready": True},
            "error": None,
        }
    )
    (agent_builder_dir / "onboarding-state.json").write_text(
        json.dumps(
            {
                "repo": {"root": str(tmp_path), "name": tmp_path.name},
                "onboarding_mode": "forward_engineering",
                "current_phase": "ready",
                "ready": True,
                "updated_at": "2026-04-20T00:00:00+00:00",
                "phases": phases,
                "entity_counts": {"projects": 1, "features": 0, "tasks": 0},
                "kb_status": {"quality_gate": "deferred"},
                "scan_summary": {"important_files": []},
                "archives": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )
    assess_readiness(tmp_path, write=True)


def test_compatible_resume_session_rejects_session_from_previous_runtime():
    session = ChatSession(id="session-1", sdk_session_id="claude-sdk-session")
    session.events = [
        ChatEvent(
            session_id="session-1",
            event_type="run_status",
            payload_json={
                "sdk_session_id": "claude-sdk-session",
                "runtime_sdk": "claude",
                "provider": "claude_code",
            },
            created_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )
    ]

    class CodexRuntime:
        name = "codex_sdk"
        provider = "codex_subscription"

    assert agent_routes._compatible_resume_session(session, CodexRuntime()) is None


def test_compatible_resume_session_reuses_session_for_same_runtime():
    session = ChatSession(id="session-1", sdk_session_id="codex-sdk-session")
    session.events = [
        ChatEvent(
            session_id="session-1",
            event_type="run_status",
            payload_json={
                "sdk_session_id": "codex-sdk-session",
                "runtime_sdk": "codex_sdk",
                "provider": "codex_subscription",
            },
            created_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )
    ]

    class CodexRuntime:
        name = "codex_sdk"
        provider = "codex_subscription"

    assert agent_routes._compatible_resume_session(session, CodexRuntime()) == "codex-sdk-session"


def test_compatible_resume_session_rejects_unattributed_session_when_status_exists():
    session = ChatSession(id="session-1", sdk_session_id="stale-sdk-session")
    session.events = [
        ChatEvent(
            session_id="session-1",
            event_type="run_status",
            payload_json={
                "runtime_sdk": "codex_sdk",
                "provider": "codex_subscription",
            },
            created_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )
    ]

    class CodexRuntime:
        name = "codex_sdk"
        provider = "codex_subscription"

    assert agent_routes._compatible_resume_session(session, CodexRuntime()) is None


def test_latest_status_marks_running_false_without_active_task():
    session = ChatSession(id="session-1")
    session.events = [
        ChatEvent(
            session_id="session-1",
            event_type="run_status",
            payload_json={"running": True, "runtime_sdk": "codex_sdk"},
            created_at=datetime(2026, 5, 7, 12, 0, tzinfo=UTC),
        )
    ]

    status = agent_routes._latest_status(session, active_run=False)

    assert status is not None
    assert status["running"] is False
    assert status["stop_reason"] == "stale_running_status_no_active_task"


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


async def _approve_pending_sprint_scope(client: AsyncClient, session_id: str):
    _history_payload, approval_item = await _wait_for_history_item(
        client,
        session_id,
        "tool_approval_request",
        predicate=lambda item: item["payload"].get("tool_name") == "Sprint scope approval"
        and item["status"] == "pending",
    )
    assert approval_item["payload"]["summary"] == "Approve Sprint scope before task creation"
    approval = await client.post(
        "/api/agent/chat/respond",
        json={
            "session_id": session_id,
            "event_id": approval_item["id"],
            "decision": "allow",
        },
    )
    assert approval.status_code == 200
    return approval_item


def test_general_chat_prompt_turns_continue_building_into_dispatch_request(tmp_path):
    prompt = agent_routes._general_chat_prompt(tmp_path, "Continue building my app.")

    assert "Autonomous continuation mode is active" in prompt
    assert "builder board show --json" in prompt
    assert "builder backlog task dispatch <task-id> --yes --json" in prompt
    assert "Do not ask the user which listed feature to build" in prompt


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
async def test_runtime_settings_route_toggles_telemetry_lanes(test_db, tmp_path):
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
        response = await client.post("/api/agent/runtime", json={"sdk": "codex_sdk"})
        payload = response.json()

        assert response.status_code == 200
        assert payload["sdk"] == "codex_sdk"
        assert payload["telemetry"]["active_lane"] == "codex"

        env_text = (tmp_path / ".env").read_text(encoding="utf-8")
        assert 'RUNTIME_SDK="codex_sdk"' in env_text
        assert 'AAB_CLAUDE_OTEL_ENABLED="0"' in env_text
        assert 'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="1"' in env_text
        assert 'AAB_CODEX_TELEMETRY_SOURCE="codex_app_server_jsonrpc"' in env_text
        assert "AAB_CODEX_JSONL_TELEMETRY_ENABLED" not in env_text

        get_response = await client.get("/api/agent/runtime")
        get_payload = get_response.json()
        assert get_response.status_code == 200
        assert get_payload["sdk"] == "codex_sdk"
        assert get_payload["telemetry"]["active_lane"] == "codex"

        meta_response = await client.get("/api/agent/chat/meta")
        meta_payload = meta_response.json()
        assert meta_response.status_code == 200
        assert meta_payload["runtime_sdk"] == "codex_sdk"
        assert meta_payload["provider"] == "codex_subscription"
        assert meta_payload["model"] == "gpt-5.5"

        history_response = await client.get("/api/agent/chat/history", params={"fresh": "1"})
        history_payload = history_response.json()
        assert history_response.status_code == 200
        assert history_payload["runtime_sdk"] == "codex_sdk"
        assert history_payload["provider"] == "codex_subscription"
        assert history_payload["model"] == "gpt-5.5"


@pytest.mark.asyncio
async def test_runtime_settings_route_repairs_ready_state_without_onboarding(test_db, tmp_path):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    (tmp_path / "AGENTS.md").write_text(
        render_project_runtime_guidance(
            project_name="runtime-switch",
            sdk="codex_sdk",
            language="unknown",
            mode="forward_engineering",
        ),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        'RUNTIME_SDK="codex_sdk"\n'
        'RUNTIME_PROVIDER="codex_subscription"\n'
        'RUNTIME_MODEL="gpt-5.5"\n'
        'AAB_CLAUDE_OTEL_ENABLED="0"\n'
        'AAB_CLAUDE_OTEL_ENDPOINT="http://localhost:4318"\n'
        'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="1"\n'
        'AAB_CODEX_TELEMETRY_SOURCE="codex_app_server_jsonrpc"\n'
        'AAB_CODEX_TELEMETRY_COST_SOURCE="subscription_unmetered"\n',
        encoding="utf-8",
    )
    _write_forward_engineering_ready_state(tmp_path)
    (tmp_path / ".env").write_text(
        'RUNTIME_SDK="codex_sdk"\n'
        'RUNTIME_PROVIDER="codex_subscription"\n'
        'RUNTIME_MODEL="gpt-5.5"\n'
        'AAB_CLAUDE_OTEL_ENABLED="0"\n'
        'AAB_CLAUDE_OTEL_ENDPOINT="http://localhost:4318"\n'
        'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="1"\n'
        'AAB_CODEX_TELEMETRY_SOURCE="codex_app_server_jsonrpc"\n'
        'AAB_CODEX_TELEMETRY_COST_SOURCE="subscription_unmetered"\n',
        encoding="utf-8",
    )
    assess_readiness(tmp_path, write=True)

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/agent/runtime", json={"sdk": "claude"})
        payload = response.json()

        assert response.status_code == 200
        assert payload["sdk"] == "claude"
        assert payload["telemetry"]["active_lane"] == "claude"
        assert payload["runtime_repair"]["status"] == "ready"

        status_response = await client.get("/api/onboarding/status")
        status = status_response.json()

    assert status["ready"] is True
    assert status["current_phase"] == "ready"
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert 'RUNTIME_SDK="claude"' in env_text
    assert 'AAB_CLAUDE_OTEL_ENABLED="1"' in env_text
    assert 'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="0"' in env_text
    assert (tmp_path / "CLAUDE.md").exists()
    readiness = load_readiness_status(tmp_path)
    assert readiness["state"] == READY_STATE
    assert readiness["can_continue"] is True
    assert readiness.get("invalidated_by", []) == []


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
    # Conftest sets RUNTIME_MODEL=anthropic/claude-sonnet-4-6 (autouse).
    # API resolves that via resolve_project_runtime_config(project_root) on
    # the project root in scope and returns it as the chat metadata model.
    assert payload["model"] == "anthropic/claude-sonnet-4-6"
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
async def test_chat_turn_accepts_codex_keyword_tool_events(monkeypatch, test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async def fake_run_phase(self, **kwargs):
        await kwargs["on_tool_event"](
            event_type="tool_use",
            tool_name="shell_command",
            tool_input={"cmd": "npm test"},
            output_preview="item/started",
        )
        return RunResult(
            session_id="sdk-session-codex-keyword-event",
            cost_usd=0.0,
            tokens_input=0,
            tokens_output=0,
            num_turns=1,
            output_text="I started the command.",
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
        response = await client.post("/api/agent/chat", json={"message": "run tests"})
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        await _wait_for_history_item(client, session_id, "assistant_message")

    async with factory() as db:
        result = await db.execute(
            select(ChatEvent).where(
                ChatEvent.session_id == session_id,
                ChatEvent.event_type == "tool_use",
            )
        )
        event = result.scalar_one()

    assert event.payload_json["tool_name"] == "shell_command"
    assert event.payload_json["tool_input"] == {"cmd": "npm test"}
    assert event.payload_json["content"] == "item/started"
    assert event.payload_json["diagnostic"]["tool_name"] == "shell_command"


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
                output_text="Feature saved to backlog as `Personal todos`.",
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
            predicate=lambda item: "Feature saved to backlog" in item["payload"].get("content", ""),
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


def test_todo_app_improvement_prompt_routes_as_feature_request():
    message = (
        "Can you make the todo app easier to use? I want to switch between all todos, "
        "only unfinished todos, and completed todos, and I want to see how many are in each group."
    )

    assert agent_routes._message_requests_feature_spec(message) is True
    assert agent_routes._message_has_documentation_intent(message) is False


def test_build_it_followup_routes_to_feature_delivery():
    assert agent_routes._message_requests_feature_delivery("Build it.") is True
    assert agent_routes._message_confirms_feature_delivery("That sounds right.") is True
    assert agent_routes._message_confirms_feature_delivery("Yes, please start it now.") is True


@pytest.mark.asyncio
async def test_todo_app_improvement_prompt_creates_feature_without_llm(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        db.add(Project(name="demo", description="demo", language="javascript"))
        await db.commit()

    async def fail_run_phase(*_: object, **__: object) -> RunResult:
        raise AssertionError("obvious todo filter request should use deterministic feature spec")

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fail_run_phase,
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
                    "Can you make the todo app easier to use? I want to switch between "
                    "all todos, only unfinished todos, and completed todos, and I want "
                    "to see how many are in each group."
                )
            },
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Todo filters and counts" in item["payload"].get("content", ""),
        )
        features_response = await client.get("/api/dashboard/features")

    features = features_response.json()["features"]
    created = next(feature for feature in features if feature["title"] == "Todo filters and counts")
    assert "filter the todo list" in created["description"]
    assert "I can plan and start the next sprint for this now" in assistant_item["payload"]["content"]
    assert "Tell me to build it" not in assistant_item["payload"]["content"]


@pytest.mark.asyncio
async def test_natural_confirmation_routes_saved_feature_to_sprint_planning(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        db.add(Project(name="demo", description="demo", language="javascript"))
        await db.commit()

    async def fail_run_phase(*_: object, **__: object) -> RunResult:
        raise AssertionError("obvious todo filter request should use deterministic feature spec")

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fail_run_phase,
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
            json={
                "message": (
                    "Can you make the todo app easier to use? I want to switch between "
                    "all todos, only unfinished todos, and completed todos, and I want "
                    "to see how many are in each group."
                )
            },
        )
        assert first.status_code == 200
        session_id = first.json()["session_id"]
        await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "I can plan and start the next sprint" in item["payload"].get("content", ""),
        )

        second = await client.post(
            "/api/agent/chat",
            json={"session_id": session_id, "message": "That sounds right."},
        )
        assert second.status_code == 200
        await _approve_pending_sprint_scope(client, session_id)
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "created sprint plan" in item["payload"].get("content", ""),
        )
        features_response = await client.get("/api/dashboard/features")

    feature = next(
        item for item in features_response.json()["features"] if item["title"] == "Todo filters and counts"
    )
    assert feature["status"] == FeatureStatus.SPRINT_PLANNED.value
    assert "Todo filters and counts" in assistant_item["payload"]["content"]


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
    assert tasks == []
    assert dispatched == []
    assert "Feature saved to backlog as `Post bookmarks`." in assistant_item["payload"]["content"]
    assert "I can plan and start the next sprint for this now" in assistant_item["payload"]["content"]


@pytest.mark.asyncio
async def test_chat_saved_feature_delivery_followup_routes_through_sprint_backlog_and_queue_approval(
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
            session_id="sdk-session-feature-followup",
            cost_usd=0.02,
            tokens_input=8,
            tokens_output=12,
            num_turns=1,
            output_text=(
                "AGREEMENT: Add one focused regression test.\n\n"
                'FEATURE_SPEC_JSON: {"title":"__html__ escaping regression",'
                '"description":"Confirm trusted HTML representation is not double escaped.",'
                '"priority":82,'
                '"acceptance_criteria":["One focused regression test covers __html__ escaping"],'
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
        first = await client.post(
            "/api/agent/chat",
            json={"message": "Create a feature spec for __html__ escaping regression."},
        )
        assert first.status_code == 200
        session_id = first.json()["session_id"]
        await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Feature saved to backlog" in item["payload"].get("content", ""),
        )

        async def fail_run_phase(self, **kwargs):
            raise AssertionError("Saved feature delivery follow-up should not invoke Claude.")

        monkeypatch.setattr(
            "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
            fail_run_phase,
        )
        second = await client.post(
            "/api/agent/chat",
            json={
                "message": "Ship this saved feature now. Create the delivery task and dispatch it.",
                "session_id": session_id,
            },
        )
        assert second.status_code == 200
        await _approve_pending_sprint_scope(client, session_id)
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "created sprint plan" in item["payload"].get("content", ""),
        )
        features_response = await client.get("/api/dashboard/features")
        feature_payload = features_response.json()
        created_feature = next(
            feature
            for feature in feature_payload["features"]
            if feature["title"] == "__html__ escaping regression"
        )
        tasks_response = await client.get(f"/api/features/{created_feature['id']}/tasks")
        task_result = await db.execute(select(Task).where(Task.feature_id == created_feature["id"]))
        task_rows = list(task_result.scalars().all())

    tasks = tasks_response.json()
    assert len(tasks) == 3
    assert {task["title"] for task in tasks} == {
        "Implement core app behavior for __html__ escaping regression",
        "Cover persistence and tests for __html__ escaping regression",
        "Verify __html__ escaping regression for shipping",
    }
    assert all(task.depends_on["sprint_execution"]["skip_task_planning"] is True for task in task_rows)
    assert all(task.depends_on["sprint_execution"]["skip_task_design"] is True for task in task_rows)
    assert dispatched == []
    assert created_feature["status"] == FeatureStatus.SPRINT_PLANNED.value
    assert "created sprint plan" in assistant_item["payload"]["content"]


@pytest.mark.asyncio
async def test_go_ahead_dispatches_first_pending_sprint_task_without_manual_board(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        feature = Feature(
            project_id=project.id,
            title="Todo filters and counts",
            description="Filter todos by completion state.",
            status=FeatureStatus.SPRINT_PLANNED,
            priority=80,
            acceptance_criteria=["Users can filter all, active, and completed todos."],
        )
        db.add(feature)
        await db.flush()
        task = Task(
            feature_id=feature.id,
            title="Implement core app behavior for Todo filters and counts",
            description="Add filter state and counters.",
            status=TaskStatus.PENDING,
        )
        older_feature = Feature(
            project_id=project.id,
            title="Older setup work",
            description="Seeded setup task.",
            status=FeatureStatus.PLANNING,
            priority=10,
        )
        db.add(older_feature)
        await db.flush()
        db.add(
            Task(
                feature_id=older_feature.id,
                title="Older pending setup task",
                description="Should not be dispatched before the active sprint task.",
                status=TaskStatus.PENDING,
            )
        )
        db.add(task)
        await db.flush()
        db.add(
            Sprint(
                project_id=project.id,
                label="Sprint 1",
                approved_feature_ids=[feature.id],
                generated_task_ids=[task.id],
            )
        )
        await db.commit()
        task_id = task.id

    async def fail_run_phase(self, **kwargs):
        raise AssertionError("Go-ahead dispatch should not invoke the chat LLM.")

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fail_run_phase,
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
        response = await client.post("/api/agent/chat", json={"message": "Go ahead."})
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Started `Implement core app behavior" in item["payload"].get("content", ""),
        )
        status_events = []
        for _ in range(20):
            async with factory() as db:
                status_result = await db.execute(
                    select(ChatEvent).where(
                        ChatEvent.session_id == session_id,
                        ChatEvent.event_type == "run_status",
                    )
                )
                status_events = [
                    event
                    for event in status_result.scalars().all()
                    if event.payload_json.get("stop_reason") == "task_dispatched"
                ]
            if status_events:
                break
            await asyncio.sleep(0.05)

    assert dispatched == [task_id]
    assert "I will continue from the current sprint task" in assistant_item["payload"]["content"]
    assert status_events
    assert status_events[0].payload_json["tokens_used"] == 0
    assert status_events[0].payload_json["cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_chat_sprint_planning_recommends_one_feature_and_creates_task_breakdown(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        db.add(
            Feature(
                id="feature-blocked",
                project_id=project.id,
                title="Dependent future item",
                description="future",
                priority=120,
                dependencies=["feature-missing"],
            )
        )
        db.add(
            Feature(
                project_id=project.id,
                title="Already selected sprint item",
                description="existing sprint work",
                priority=110,
                status=FeatureStatus.SPRINT_BACKLOG,
            )
        )
        db.add(Feature(project_id=project.id, title="Backlog item one", description="one", priority=100))
        db.add(Feature(project_id=project.id, title="Backlog item two", description="two", priority=90))
        await db.commit()

    async def fail_run_phase(self, **kwargs):
        raise AssertionError("Sprint planning should run through the deterministic agent chat lane.")

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fail_run_phase,
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/agent/chat", json={"message": "I want to do sprint planning."})
        assert first.status_code == 200
        session_id = first.json()["session_id"]
        _history_payload, prompt_item = await _wait_for_history_item(
            client,
            session_id,
            "ask_user_question",
            predicate=lambda item: item["payload"].get("header") == "Sprint Scope",
        )
        recommended_label = prompt_item["payload"]["options"][0]["label"]
        assert recommended_label.startswith("Plan first shippable feature:")
        assert "Dependent future item" not in recommended_label
        assert "Keeps the sprint focused on one shippable outcome" in prompt_item["payload"]["options"][0]["description"]
        assert prompt_item["payload"]["options"][1]["label"] == "Plan all backlog items"

        selection = await client.post(
            "/api/agent/chat/respond",
            json={
                "session_id": session_id,
                "event_id": prompt_item["id"],
                "selected_options": [recommended_label],
            },
        )
        assert selection.status_code == 200
        board_before_approval = await client.get("/api/dashboard/board")
        assert board_before_approval.json()["pending"] == []
        await _approve_pending_sprint_scope(client, session_id)
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "created sprint plan" in item["payload"].get("content", ""),
        )
        features_response = await client.get("/api/dashboard/features")
        board_response = await client.get("/api/dashboard/board")

    feature_payload = features_response.json()
    queued_features = {feature["title"]: feature["status"] for feature in feature_payload["features"]}
    assert queued_features["Backlog item one"] == FeatureStatus.SPRINT_PLANNED.value
    assert queued_features["Backlog item two"] == FeatureStatus.BACKLOG.value
    assert queued_features["Dependent future item"] == FeatureStatus.BACKLOG.value
    assert queued_features["Already selected sprint item"] == FeatureStatus.SPRINT_BACKLOG.value
    board_payload = board_response.json()
    assert len(board_payload["pending"]) == 3
    assert {item["feature_title"] for item in board_payload["pending"]} == {"Backlog item one"}
    assert board_payload["current_sprint"]["active_phase"] == "implementation"
    assert board_payload["current_sprint"]["phase_statuses"]["implementation"] == "active"
    assert "with 3 generated task(s)" in assistant_item["payload"]["content"]


@pytest.mark.asyncio
async def test_chat_sprint_planning_named_feature_requires_scope_approval_before_tasks(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        project = Project(name="demo", description="demo", language="javascript")
        db.add(project)
        await db.flush()
        db.add(Feature(project_id=project.id, title="Backlog item one", description="one", priority=100))
        db.add(Feature(project_id=project.id, title="Backlog item two", description="two", priority=90))
        await db.commit()

    async def fail_run_phase(self, **kwargs):
        raise AssertionError("Sprint planning should use deterministic dashboard lifecycle.")

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fail_run_phase,
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
            json={"message": 'Plan Sprint 1 for the backlog item "Backlog item one" only.'},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _history_payload, approval_item = await _wait_for_history_item(
            client,
            session_id,
            "tool_approval_request",
            predicate=lambda item: item["payload"].get("tool_name") == "Sprint scope approval",
        )
        board_before_approval = await client.get("/api/dashboard/board")
        assert board_before_approval.json()["pending"] == []

        denial = await client.post(
            "/api/agent/chat/respond",
            json={
                "session_id": session_id,
                "event_id": approval_item["id"],
                "decision": "deny",
                "reason": "Review the scope first.",
            },
        )
        assert denial.status_code == 200
        await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Sprint planning scope was not approved" in item["payload"].get("content", ""),
        )
        board_after_denial = await client.get("/api/dashboard/board")

    assert board_after_denial.json()["pending"] == []


@pytest.mark.asyncio
async def test_chat_start_next_sprint_infers_first_ready_backlog_item_without_scope_prompt(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        project = Project(name="todo app", description="personal todo app", language="typescript")
        db.add(project)
        await db.flush()
        db.add(
            Feature(
                id="feature-01",
                project_id=project.id,
                title="Todo Creation And Editing",
                description="done",
                priority=100,
                status=FeatureStatus.DONE,
            )
        )
        db.add(
            Feature(
                id="feature-02",
                project_id=project.id,
                title="Local Browser Persistence",
                description="done",
                priority=90,
                status=FeatureStatus.DONE,
                dependencies=["feature-01"],
            )
        )
        db.add(
            Feature(
                id="feature-03",
                project_id=project.id,
                title="Today List View",
                description="next ready feature",
                priority=80,
                dependencies=["feature-01", "feature-02"],
            )
        )
        db.add(
            Feature(
                id="feature-04",
                project_id=project.id,
                title="Completion Workflow",
                description="later feature",
                priority=70,
                dependencies=["feature-03"],
            )
        )
        await db.commit()

    async def fail_run_phase(self, **kwargs):
        raise AssertionError("Next sprint inference should stay in the deterministic chat lane.")

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fail_run_phase,
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/agent/chat", json={"message": "I want to start next sprint"})
        assert first.status_code == 200
        session_id = first.json()["session_id"]
        await _approve_pending_sprint_scope(client, session_id)
        history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "created sprint plan" in item["payload"].get("content", ""),
        )
        features_response = await client.get("/api/dashboard/features")

    assert "Today List View" in assistant_item["payload"]["content"]
    history_items = history_payload["items"]
    assert not any(item["type"] == "ask_user_question" for item in history_items)
    statuses = {feature["id"]: feature["status"] for feature in features_response.json()["features"]}
    assert statuses["feature-03"] == FeatureStatus.SPRINT_PLANNED.value
    assert statuses["feature-04"] == FeatureStatus.BACKLOG.value


@pytest.mark.asyncio
async def test_chat_ambiguous_go_ahead_asks_for_sprint_scope_before_mutating(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        project = Project(name="todo app", description="personal todo app", language="typescript")
        db.add(project)
        await db.flush()
        db.add(
            Feature(
                id="feature-03",
                project_id=project.id,
                title="Today List View",
                description="next ready feature",
                priority=80,
            )
        )
        await db.commit()

    async def fail_run_phase(self, **kwargs):
        raise AssertionError("Ambiguous continuation should use the deterministic question lane.")

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fail_run_phase,
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/agent/chat", json={"message": "Can you go ahead?"})
        assert first.status_code == 200
        session_id = first.json()["session_id"]
        _history_payload, prompt_item = await _wait_for_history_item(
            client,
            session_id,
            "ask_user_question",
            predicate=lambda item: item["payload"].get("header") == "Sprint Scope",
        )
        features_response = await client.get("/api/dashboard/features")

    assert prompt_item["payload"]["options"][0]["label"].startswith(
        "Plan first shippable feature: feature-03"
    )
    statuses = {feature["id"]: feature["status"] for feature in features_response.json()["features"]}
    assert statuses["feature-03"] == FeatureStatus.BACKLOG.value


def test_sprint_planning_intent_accepts_numbered_sprint_language() -> None:
    assert agent_routes._message_requests_sprint_planning("Start Sprint 2 planning for feature-02")
    assert agent_routes._message_requests_sprint_planning("I want to start next sprint")


def test_delivery_progress_intent_does_not_require_exact_sprint_phrase() -> None:
    assert agent_routes._message_requests_autonomous_continuation("What should we build next?")
    assert agent_routes._message_requests_autonomous_continuation("Move the product forward")
    assert agent_routes._message_requests_autonomous_continuation("Please proceed")
    assert agent_routes._message_requests_autonomous_continuation("Can you go ahead?")
    assert agent_routes._message_requests_autonomous_continuation("Can you start with the task?")
    assert agent_routes._message_requests_ambiguous_continuation("Can you go ahead?")
    assert agent_routes._message_requests_ambiguous_continuation("Can you start with the task?")
    assert not agent_routes._message_requests_ambiguous_continuation("I want to start next sprint")
    assert not agent_routes._message_requests_autonomous_continuation("Update the documentation")


@pytest.mark.asyncio
async def test_chat_sprint_planning_direct_queue_all_product_backlog_items_creates_sprint_tasks(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        project = Project(name="demo", description="demo", language="python")
        db.add(project)
        await db.flush()
        db.add(Feature(project_id=project.id, title="Backlog item one", description="one", priority=100))
        db.add(Feature(project_id=project.id, title="Backlog item two", description="two", priority=90))
        await db.commit()

    async def fail_run_phase(self, **kwargs):
        raise AssertionError("Direct sprint queueing should use the deterministic chat lane.")

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fail_run_phase,
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
            json={"message": "Queue all current product backlog items for the sprint."},
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        await _approve_pending_sprint_scope(client, session_id)
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            timeout=10.0,
            predicate=lambda item: "created sprint plan" in item["payload"].get("content", ""),
        )
        board_response = await client.get("/api/dashboard/board")

    board_payload = board_response.json()
    assert len(board_payload["pending"]) == 6
    assert board_payload["current_sprint"]["active_phase"] == "implementation"
    assert "with 6 generated task(s)" in assistant_item["payload"]["content"]


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
    assert tasks == []
    assert dispatched == []
    assert "Feature saved to backlog as `Private Post Bookmarks`." in assistant_item["payload"]["content"]
    assert "I can plan and start the next sprint for this now" in assistant_item["payload"]["content"]


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
async def test_continue_building_auto_approves_builder_task_dispatch(
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
        feature = Feature(
            project_id=project.id,
            title="Existing work",
            description="Marks the workspace as past bootstrap for chat continuation.",
            status=FeatureStatus.BACKLOG,
            item_type=BacklogItemType.FEATURE,
        )
        db.add(feature)
        await db.flush()
        db.add(
            Task(
                feature_id=feature.id,
                title="Existing dispatchable task",
                description="A pending task should make continuation dispatch task work before sprint planning.",
            )
        )
        await db.commit()

    async def fake_run_phase(self, **kwargs):
        permission = await kwargs["can_use_tool"](
            "mcp__builder__task_dispatch",
            {"task_id": "task-1"},
            {},
        )
        assert getattr(permission, "behavior", "") == "allow"
        assert getattr(permission, "updated_input", {}) == {"task_id": "task-1"}
        return RunResult(
            session_id="sdk-session-task-dispatch-auto",
            cost_usd=0.01,
            tokens_input=4,
            tokens_output=4,
            num_turns=1,
            output_text="Continuing the selected board task.",
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

    assert not any(item["type"] == "tool_approval_request" for item in history_payload["items"])


@pytest.mark.asyncio
async def test_continue_building_records_terminal_dispatch_status(
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
        feature = Feature(
            project_id=project.id,
            title="Existing work",
            description="Marks the workspace as past bootstrap for chat continuation.",
            status=FeatureStatus.BACKLOG,
            item_type=BacklogItemType.FEATURE,
        )
        db.add(feature)
        await db.flush()
        db.add(
            Task(
                feature_id=feature.id,
                title="Existing dispatchable task",
                description="A pending task should make continuation dispatch task work before sprint planning.",
                status=TaskStatus.PENDING,
            )
        )
        await db.commit()

    class FakeRuntime:
        name = "claude"

        async def run(self, *args, **kwargs):
            await kwargs["on_tool_event"](
                {
                    "tool_name": "mcp__builder__task_dispatch",
                    "tool_input": {"task_id": "task-1"},
                    "tool_response": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "status": "dispatched",
                                        "task_id": "task-1",
                                        "current_status": "implementation",
                                    }
                                ),
                            }
                        ],
                        "metadata": {"exit_code": 0},
                    },
                    "tool_use_id": "tool-dispatch-1",
                }
            )
            return RunResult(
                session_id="sdk-session-task-dispatch-auto",
                cost_usd=0.01,
                tokens_input=4,
                tokens_output=4,
                num_turns=1,
                output_text="Continuing the selected board task.",
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
            json={"message": "Continue building my app."},
        )
        session_id = response.json()["session_id"]
        await _wait_for_history_item(client, session_id, "assistant_message")

    dispatch_statuses = []
    for _ in range(20):
        async with factory() as db:
            result = await db.execute(
                select(ChatEvent).where(
                    ChatEvent.session_id == session_id,
                    ChatEvent.event_type == "run_status",
                )
            )
            dispatch_statuses = [
                event
                for event in result.scalars().all()
                if event.payload_json.get("stop_reason") == "task_dispatched"
            ]
        if dispatch_statuses:
            break
        await asyncio.sleep(0.05)

    assert dispatch_statuses
    assert dispatch_statuses[0].payload_json["running"] is False
    assert dispatch_statuses[0].payload_json["dispatch"] == {
        "task_id": "task-1",
        "status": "dispatched",
        "current_status": "implementation",
    }


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
    assert tasks == []
    assert dispatched == []
    assert len(captured_prompts) == 2
    assert "When there are a few clear choices, use AskUserQuestion" in captured_prompts[1]
    assert "continue the interview until the first implementation scope has no obvious gaps" in captured_prompts[1]
    assert "Feature saved to backlog as `Private Post Bookmarking`." in assistant_item["payload"]["content"]
    assert "I can plan and start the next sprint for this now" in assistant_item["payload"]["content"]


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
        # Conftest sets RUNTIME_MODEL=anthropic/claude-sonnet-4-6 (autouse).
        assert payload["model"] == "anthropic/claude-sonnet-4-6"
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

        def __init__(self):
            self.calls = 0

        async def run(self, input: str, **kwargs):
            self.calls += 1
            captured_prompts.append(input)
            if self.calls > 1:
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
                tokens_input=10,
                tokens_output=5,
                num_turns=1,
                output_text="Great, I will use effort balance.",
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
            predicate=lambda item: "Feature backlog saved" in item["payload"].get("content", ""),
        )
        history_payload, sprint_scope_item = await _wait_for_history_item(
            client,
            session_id,
            "ask_user_question",
            predicate=lambda item: item["payload"].get("header") == "Sprint Scope",
        )
        sprint_answer = await client.post(
            "/api/agent/chat/respond",
            json={
                "session_id": session_id,
                "event_id": sprint_scope_item["id"],
                "selected_options": [sprint_scope_item["payload"]["options"][0]["label"]],
            },
        )
        assert sprint_answer.status_code == 200
        await _approve_pending_sprint_scope(client, session_id)
        history_payload, sprint_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Approved Sprint 1 scope" in item["payload"].get("content", "")
            or "Approved Sprint 2 scope" in item["payload"].get("content", ""),
        )

    assert captured_prompts
    assert "request_user_input" in captured_prompts[0]
    assert "AskUserQuestion" not in captured_prompts[0]
    assert "do not stop with an acknowledgement" in captured_prompts[0]
    assert "Every non-final response in this phase" in captured_prompts[0]
    assert "previous assistant response ended without a structured question" in captured_prompts[1]
    updated_question = next(item for item in history_payload["items"] if item["id"] == question_item["id"])
    assert updated_question["payload"]["answered"] is True
    assert updated_question["payload"]["answer_value"] == "Effort balance (Recommended)"
    assert "Great, I will use effort balance" not in assistant_item["payload"]["content"]
    assert "Feature backlog saved" in assistant_item["payload"]["content"]
    assert sprint_scope_item["status"] == "pending"
    assert sprint_scope_item["payload"]["options"][0]["label"].startswith(
        "Plan first shippable feature:"
    )
    assert "created sprint plan" in sprint_item["payload"]["content"]


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
async def test_mission_aligned_delivery_prompt_does_not_route_to_documentation_agent(
    monkeypatch, test_db, tmp_path
):
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
            predicate=lambda item: "created sprint plan" in item["payload"].get("content", ""),
        )

    assert "Today List View" in assistant_item["payload"]["content"]
    assert all(item["type"] != "specialist_status" for item in history_payload["items"])
    assert all(item["type"] != "ask_user_question" for item in history_payload["items"])


@pytest.mark.asyncio
async def test_forward_engineering_chat_writes_feature_list(monkeypatch, test_db, tmp_path):
    dashboard_root = tmp_path.parent / f"{tmp_path.name}-dashboard"
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
            json={
                "message": (
                    "Build me a budgeting app for freelancers. Use Flask with plain HTML "
                    "and JavaScript."
                ),
                "session_id": session_id,
            },
        )
        assert response.status_code == 200
        assert response.json()["model"] == agent_routes._runtime_metadata_for_agent(
            "init-project-chat"
        )["model"]

        feature_list = tmp_path / ".claude" / "progress" / "feature-list.json"
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            timeout=10.0,
            predicate=lambda item: "Feature backlog saved" in item["payload"].get("content", ""),
        )

    assert "Feature backlog saved to `.claude/progress/feature-list.json`." in assistant_item["payload"]["content"]

    assert feature_list.exists()
    feature_payload = json.loads(feature_list.read_text(encoding="utf-8"))
    assert feature_payload["metadata"]["project"] == "budget-mvp"
    assert [feature["title"] for feature in feature_payload["features"]] == [
        "Capture expenses",
        "See spending summary",
    ]
    assert feature_payload["metadata"]["technical_constraints"] == [
        "Use Flask as the Python web framework",
        "Use plain HTML and JavaScript",
    ]
    claude_text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "## Project Constraints" in claude_text
    assert "- Use Flask as the Python web framework" in claude_text
    assert "- Use plain HTML and JavaScript" in claude_text
    readiness = load_readiness_status(tmp_path)
    assert readiness["state"] == READY_STATE
    assert "runtime_guidance" not in readiness.get("invalidated_by", [])


@pytest.mark.asyncio
async def test_forward_engineering_chat_marks_provider_limit_blocked(monkeypatch, test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path.parent / f"{tmp_path.name}-dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")
    _write_forward_engineering_ready_state(tmp_path)

    async def fake_run_phase(self, **kwargs):
        assert kwargs["agent_name"] == "init-project-chat"
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
        _payload, assistant_item = await _wait_for_history_item(
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
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")
    _write_forward_engineering_ready_state(tmp_path)
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
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            timeout=10.0,
            predicate=lambda item: item["payload"].get("content") == "Normal chat route.",
        )

    assert assistant_item["payload"]["content"] == "Normal chat route."


@pytest.mark.asyncio
async def test_forward_engineering_new_thread_does_not_reuse_bootstrap_session(monkeypatch, test_db, tmp_path):
    _write_forward_engineering_ready_state(tmp_path)
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

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
        _, assistant_item = await _wait_for_history_item(
            client,
            new_session_id,
            "assistant_message",
            timeout=10.0,
            predicate=lambda item: item["payload"].get("content") == "New thread accepted.",
        )

    assert assistant_item["payload"]["content"] == "New thread accepted."
