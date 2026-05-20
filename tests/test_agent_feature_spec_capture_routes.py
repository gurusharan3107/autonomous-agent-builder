"""Agent feature-spec capture and confirmation route regressions."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import (
    FeatureStatus,
    Project,
)
from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server import agent_sprint_planning
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from tests.agent_route_test_support import (
    approve_pending_sprint_scope as _approve_pending_sprint_scope,
)
from tests.agent_route_test_support import (
    wait_for_history_item as _wait_for_history_item,
)


@pytest.mark.asyncio
async def test_ship_new_feature_prompt_creates_feature_before_sprint_planning(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        db.add(Project(name="demo", description="demo", language="javascript"))
        await db.commit()

    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured.update(kwargs)
        return RunResult(
            session_id="sdk-session-feature-before-sprint",
            cost_usd=0.01,
            tokens_input=7,
            tokens_output=8,
            num_turns=1,
            output_text=(
                "AGREEMENT: Add a focused due-today todo shortcut.\n\n"
                'FEATURE_SPEC_JSON: {"title":"Due today shortcut","description":"Let users '
                'quickly see todos due today without changing existing task data.","priority":70,'
                '"acceptance_criteria":["Users can open a due-today filtered view"],'
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
                    "Ship one small new todo feature like a normal operator. Pick the lowest-risk "
                    "feature that improves day-to-day use, create the backlog/sprint plan, and "
                    "keep the sprint efficient."
                )
            },
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        _history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
        )

    assert captured, assistant_item["payload"]["content"]
    assert "FEATURE_SPEC_JSON:" in str(captured["prompt"])
    assert "There are no product backlog items available for sprint planning." not in assistant_item[
        "payload"
    ]["content"]
    assert "I captured that improvement" in assistant_item["payload"]["content"]

@pytest.mark.asyncio
async def test_todo_app_improvement_prompt_uses_model_and_captures_feature(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        db.add(Project(name="demo", description="demo", language="javascript"))
        await db.commit()

    async def fake_run_phase(self, **kwargs):
        return RunResult(
            session_id="sdk-session-todo-filters",
            cost_usd=0.01,
            tokens_input=6,
            tokens_output=7,
            num_turns=1,
            output_text=(
                "AGREEMENT: Add todo filters and counts.\n\n"
                'FEATURE_SPEC_JSON: {"title":"Todo filters and counts","description":"Users can '
                'filter the todo list between all, unfinished, and completed items, with visible '
                'counts for each group.","priority":80,"acceptance_criteria":["A user can switch '
                'between all, unfinished, and completed todo views.","The UI shows counts for total, '
                'unfinished, and completed todos."],"dependencies":["Existing todo creation and completion state"]}'
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
    assert "Ready for Builder to start now" in assistant_item["payload"]["content"]
    assert "Tell me to build it" not in assistant_item["payload"]["content"]

@pytest.mark.asyncio
async def test_codex_feature_spec_lane_uses_turn_approval_gate(monkeypatch, test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        db.add(Project(name="demo", description="demo", language="javascript"))
        await db.commit()

    captured: dict[str, object] = {}

    class FakeCodexRuntime:
        name = "codex_sdk"
        model = "gpt-5.5"
        provider = "codex_subscription"

        async def run(self, prompt, **kwargs):
            captured["prompt"] = prompt
            captured.update(kwargs)
            return RunResult(
                session_id="sdk-session-codex-feature-spec",
                cost_usd=0.0,
                tokens_input=12,
                tokens_output=8,
                num_turns=1,
                output_text=(
                    "AGREEMENT: Make overdue todos stand out.\n\n"
                    'FEATURE_SPEC_JSON: {"title":"Make overdue todos stand out",'
                    '"description":"Highlight incomplete todos dated before today.",'
                    '"priority":50,"acceptance_criteria":["Overdue active todos are visibly '
                    'marked."],"dependencies":[]}'
                ),
            )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **kwargs: FakeCodexRuntime())

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
                    "I want to improve the todo app so overdue tasks stand out clearly."
                )
            },
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Make overdue todos stand out" in item["payload"].get(
                "content",
                "",
            ),
        )

    assert "FEATURE_SPEC_JSON:" in str(captured["prompt"])
    assert captured["approval_policy"] == "on-request"

@pytest.mark.asyncio
async def test_imperative_todo_improvement_uses_feature_spec_lane(monkeypatch, test_db, tmp_path):
    _, factory = test_db
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        db.add(Project(name="demo", description="demo", language="javascript"))
        await db.commit()

    captured: dict[str, object] = {}

    class FakeCodexRuntime:
        name = "codex_sdk"
        model = "gpt-5.5"
        provider = "codex_subscription"

        async def run(self, prompt, **kwargs):
            captured["prompt"] = prompt
            captured.update(kwargs)
            return RunResult(
                session_id="sdk-session-codex-empty-state-hint",
                cost_usd=0.0,
                tokens_input=12,
                tokens_output=8,
                num_turns=1,
                output_text=(
                    "AGREEMENT: Add a todo empty-state hint without changing existing behavior.\n\n"
                    'FEATURE_SPEC_JSON: {"title":"Todo empty-state hint",'
                    '"description":"Show a small hint when the current todo filter has no visible '
                    'todos, while preserving existing add, complete, filter, and persistence '
                    'behavior.","priority":50,"acceptance_criteria":["An empty visible todo list '
                    'shows a concise next-step hint.","Existing todo behavior is unchanged."],'
                    '"dependencies":[]}'
                ),
            )

    monkeypatch.setattr(agent_routes, "create_runtime", lambda **kwargs: FakeCodexRuntime())

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
                    "Add a small visible empty-state hint under the todo list that says what "
                    "to do next when there are no visible todos. Keep existing todo behavior "
                    "unchanged."
                )
            },
        )
        assert response.status_code == 200
        session_id = response.json()["session_id"]
        await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: "Todo empty-state hint" in item["payload"].get(
                "content",
                "",
            ),
        )

    assert "improvement-scoping guide" in str(captured["prompt"])
    assert "FEATURE_SPEC_JSON:" in str(captured["prompt"])
    assert captured["approval_policy"] == "on-request"

@pytest.mark.asyncio
async def test_natural_confirmation_routes_saved_feature_to_sprint_planning(
    monkeypatch, test_db, tmp_path
):
    _, factory = test_db
    dispatched: list[str] = []

    async def fake_schedule_task_dispatch(task_id: str) -> None:
        dispatched.append(task_id)

    monkeypatch.setattr(agent_routes, "_schedule_task_dispatch", fake_schedule_task_dispatch)
    monkeypatch.setattr(agent_sprint_planning, "schedule_task_dispatch", fake_schedule_task_dispatch)
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text("<html><body>embedded</body></html>", encoding="utf-8")

    async with factory() as db:
        db.add(Project(name="demo", description="demo", language="javascript"))
        await db.commit()

    async def fake_run_phase(self, **kwargs):
        return RunResult(
            session_id="sdk-session-todo-filters-confirm",
            cost_usd=0.01,
            tokens_input=6,
            tokens_output=7,
            num_turns=1,
            output_text=(
                "AGREEMENT: Add todo filters and counts.\n\n"
                'FEATURE_SPEC_JSON: {"title":"Todo filters and counts","description":"Users can '
                'filter the todo list between all, unfinished, and completed items, with visible '
                'counts for each group.","priority":80,"acceptance_criteria":["A user can switch '
                'between all, unfinished, and completed todo views.","The UI shows counts for total, '
                'unfinished, and completed todos."],"dependencies":["Existing todo creation and completion state"]}'
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
            predicate=lambda item: "Ready for Builder to start now" in item["payload"].get("content", ""),
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
            predicate=lambda item: "Builder prepared the work" in item["payload"].get("content", ""),
        )
        features_response = await client.get("/api/dashboard/features")

    feature = next(
        item for item in features_response.json()["features"] if item["title"] == "Todo filters and counts"
    )
    assert feature["status"] == FeatureStatus.SPRINT_PLANNED.value
    assert "Todo filters and counts" in assistant_item["payload"]["content"]
    assert dispatched
