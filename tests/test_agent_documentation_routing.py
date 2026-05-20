"""Tests for Agent documentation-specialist routing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from autonomous_agent_builder.embedded.server.routes import agent as agent_routes
from tests.agent_route_test_support import append_chat_event, create_chat_session


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
    session_id = await create_chat_session(
        factory,
        repo_identity=str(tmp_path.resolve()),
        workspace_cwd=str(tmp_path.resolve()),
        updated_at=now,
    )
    await append_chat_event(
        factory,
        session_id=session_id,
        event_type="user_message",
        payload={"content": "check docs"},
        created_at=now - timedelta(minutes=3),
    )
    await append_chat_event(
        factory,
        session_id=session_id,
        event_type="specialist_status",
        payload={"specialist": "documentation-agent", "phase": "completed", "content": "done"},
        created_at=now - timedelta(minutes=2),
    )
    await append_chat_event(
        factory,
        session_id=session_id,
        event_type="assistant_message",
        payload={"content": "stale docs found"},
        created_at=now - timedelta(minutes=1),
    )
    await append_chat_event(
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
    session_id = await create_chat_session(
        factory,
        repo_identity=str(tmp_path.resolve()),
        workspace_cwd=str(tmp_path.resolve()),
        updated_at=now,
    )
    await append_chat_event(
        factory,
        session_id=session_id,
        event_type="user_message",
        payload={"content": "hello"},
        created_at=now - timedelta(minutes=1),
    )
    await append_chat_event(
        factory,
        session_id=session_id,
        event_type="assistant_message",
        payload={"content": "hi"},
        created_at=now - timedelta(seconds=30),
    )
    await append_chat_event(
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
    session_id = await create_chat_session(
        factory,
        repo_identity=str(tmp_path.resolve()),
        workspace_cwd=str(tmp_path.resolve()),
        updated_at=now,
    )
    await append_chat_event(
        factory,
        session_id=session_id,
        event_type="user_message",
        payload={"content": "check docs"},
        created_at=now - timedelta(minutes=3),
    )
    await append_chat_event(
        factory,
        session_id=session_id,
        event_type="specialist_status",
        payload={"specialist": "documentation-agent", "phase": "completed", "content": "done"},
        created_at=now - timedelta(minutes=2),
    )
    await append_chat_event(
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
    session_id = await create_chat_session(
        factory,
        repo_identity=str(tmp_path.resolve()),
        workspace_cwd=str(tmp_path.resolve()),
        updated_at=now,
    )
    await append_chat_event(
        factory,
        session_id=session_id,
        event_type="user_message",
        payload={"content": "check docs"},
        created_at=now - timedelta(minutes=2),
    )
    await append_chat_event(
        factory,
        session_id=session_id,
        event_type="specialist_status",
        payload={"specialist": "documentation-agent", "phase": "completed", "content": "done"},
        created_at=now - timedelta(minutes=1),
    )
    await append_chat_event(
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
        explicit_intent_matcher=lambda message: agent_routes._normalized_follow_up_message(message)
        == "go ahead",
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
