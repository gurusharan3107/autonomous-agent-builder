"""Agent feature-spec prompt contract regressions."""

from __future__ import annotations

from autonomous_agent_builder.embedded.server import agent_message_intent
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes


def test_general_chat_prompt_lets_model_classify_improvement_requests(tmp_path):
    message = (
        "Can you make the todo app easier to use? I want to switch between all todos, "
        "only unfinished todos, and completed todos, and I want to see how many are in each group."
    )

    prompt = agent_routes._general_chat_prompt(tmp_path, message)
    assert "you own intent understanding" in prompt
    assert "emit `FEATURE_SPEC_JSON:`" in prompt
    assert (
        "The operator does not need to know backlog, sprint, product backlog, or task terminology."
        in prompt
    )
    assert agent_routes._message_has_documentation_intent(message) is False


def test_forward_engineering_first_product_prompt_requires_user_specific_intake(tmp_path):
    prompt = agent_routes._general_chat_prompt(
        tmp_path,
        "I want to build a personal Habit Lab app for tracking daily habits.",
        runtime_sdk="codex_sdk",
        forward_engineering_context=True,
    )

    assert "the user's prompt still owns intent" in prompt
    assert "use model judgment to decide whether to answer directly" in prompt
    assert (
        "Do not use tool calls or structured questions just because this is a clean-slate workspace"
        in prompt
    )
    assert "get enough user-specific requirements" in prompt
    assert "not a generic MVP inferred from the product category" in prompt
    assert "only when they will materially improve the first backlog" in prompt
    assert "emit `FEATURE_SPEC_JSON:` without extra questioning" in prompt
    assert "audience, workflow, data, success criteria" in prompt
    assert "as many product-shaping questions or follow-up rounds" in prompt
    assert "Do not cap the total interview at one question or one structured request" in prompt
    assert "exactly 3 suggested `options`" in prompt
    assert "fourth path as an inline custom-answer text box" in prompt
    assert "Do not skip product tailoring by jumping straight to delivery approval." in prompt
    assert "request_user_input" in prompt


def test_first_product_prompt_is_not_delivery_continuation() -> None:
    message = "I want to build a personal Habit Lab app for tracking daily habits."

    assert agent_message_intent.message_requests_feature_spec(message) is True
    assert agent_message_intent.message_requests_feature_delivery(message) is False
    assert agent_message_intent.message_requests_autonomous_continuation(message) is False
    assert (
        agent_message_intent.message_requests_autonomous_continuation("Continue building my app.")
        is True
    )


def test_imperative_todo_improvement_prompt_requests_feature_spec() -> None:
    message = (
        "Add a small visible empty-state hint under the todo list that says what to do "
        "next when there are no visible todos. Keep existing todo behavior unchanged."
    )

    assert agent_message_intent.message_requests_feature_spec(message) is True
    assert agent_message_intent.message_requests_feature_delivery(message) is False
    assert agent_message_intent.message_requests_autonomous_continuation(message) is False


def test_feature_spec_prompt_bounds_codex_repo_discovery(tmp_path):
    prompt = agent_routes._feature_spec_chat_prompt(
        tmp_path,
        "I want overdue todos to stand out clearly.",
        runtime_sdk="codex_sdk",
    )

    assert "If the operator prompt is already specific enough" in prompt
    assert "skip shell/file tools" in prompt
    assert "avoid raw, --full, recursive, or broad file-listing commands" in prompt
    assert "cap shell output to a small command-specific window" in prompt


def test_build_it_followup_routes_to_feature_delivery():
    assert agent_message_intent.message_requests_feature_delivery("Build it.") is True
    assert agent_message_intent.message_confirms_feature_delivery("That sounds right.") is True
    assert (
        agent_message_intent.message_confirms_feature_delivery("Yes, please start it now.") is True
    )
    assert agent_message_intent.message_requests_autonomous_continuation("Start now.") is True


def test_feature_spec_prompt_injects_recent_context_on_followup(tmp_path):
    recent = "- User: I want to add a search feature\n- Builder Agent: What type of search?"
    prompt = agent_routes._feature_spec_chat_prompt(
        tmp_path,
        "Full-text search please.",
        runtime_sdk="codex_sdk",
        recent_context=recent,
    )
    assert "Full-text search please." in prompt
    assert "Prior session context for this intake turn" in prompt
    assert "I want to add a search feature" in prompt
    assert "What type of search?" in prompt


def test_feature_spec_prompt_without_recent_context_omits_section(tmp_path):
    prompt = agent_routes._feature_spec_chat_prompt(
        tmp_path,
        "Add a search box.",
        runtime_sdk="codex_sdk",
        recent_context="",
    )
    assert "Prior session context for this intake turn" not in prompt
    assert "Add a search box." in prompt


def test_recent_chat_context_for_prompt_force_bypasses_message_filter():
    from unittest.mock import MagicMock

    from autonomous_agent_builder.db.models import ChatEvent, ChatSession
    from autonomous_agent_builder.embedded.server.agent_prompt_builders import (
        _recent_chat_context_for_prompt,
    )

    event = MagicMock(spec=ChatEvent)
    event.event_type = "user_message"
    event.payload_json = {"content": "I want a developer pulse dashboard."}
    event.created_at = __import__("datetime").datetime(2026, 5, 21)

    session = MagicMock(spec=ChatSession)
    session.events = [event]

    short_answer = "Yes, for my engineering team."
    context_without_force = _recent_chat_context_for_prompt(session, short_answer)
    context_with_force = _recent_chat_context_for_prompt(session, short_answer, force=True)

    assert context_without_force == ""
    assert "developer pulse dashboard" in context_with_force


def test_feature_spec_prompt_requests_proposed_task_sizing(tmp_path):
    """IMP-027c: the intake prompt must ask the model to size proposed_tasks to the
    real change (one task for a trivial single-surface change)."""
    prompt = agent_routes._feature_spec_chat_prompt(
        tmp_path,
        "I want a small version label in the footer.",
        runtime_sdk="codex_sdk",
    )
    assert "proposed_tasks" in prompt
    assert "is ONE task" in prompt


def test_general_chat_prompt_mentions_proposed_tasks(tmp_path):
    prompt = agent_routes._general_chat_prompt(
        tmp_path,
        "Add a small empty-state hint under the todo list.",
    )
    assert "proposed_tasks" in prompt


def test_normalize_feature_spec_payload_carries_proposed_tasks() -> None:
    """The captured feature-spec payload preserves a model decomposition (length>=1)."""
    from autonomous_agent_builder.embedded.server.agent_feature_payloads import (
        normalize_feature_spec_payload,
        normalize_proposed_tasks,
    )

    payload = normalize_feature_spec_payload(
        {
            "title": "Footer version label",
            "description": "Static v0.1 label, not tied to any external source.",
            "acceptance_criteria": ["Footer shows v0.1"],
            "proposed_tasks": [
                {"title": "Add v0.1 footer label", "purpose": "show version"},
                "Verify label renders",  # bare-string form is accepted
            ],
        }
    )
    assert [task["title"] for task in payload["proposed_tasks"]] == [
        "Add v0.1 footer label",
        "Verify label renders",
    ]
    # junk and empty entries are dropped; non-lists yield empty
    assert normalize_proposed_tasks("nope") == []
    assert normalize_proposed_tasks([{"title": ""}, 42]) == []


# ---------------------------------------------------------------------------
# IMP-016: builder self-improvement intent classification
# ---------------------------------------------------------------------------


def test_builder_self_improvement_not_routed_as_feature_spec() -> None:
    """Builder-improvement asks must NOT be classified as app feature specs."""
    builder_asks = [
        "add a feature to builder",
        "fix builder's cost tracking",
        "improve the builder's sprint decomposition",
        "add cost tracking to the builder",
        "fix the builder",
        "improve builder performance",
        "update the builder's task decomposition logic",
        "can you add a feature to builder",
        "the builder's cost tracking is broken, please fix it",
        "fix builder",
        "improve builder",
    ]
    for msg in builder_asks:
        assert agent_message_intent.message_requests_feature_spec(msg) is False, (
            f"Expected False for builder-self ask: {msg!r}"
        )
        assert agent_message_intent.message_requests_feature_delivery(msg) is False, (
            f"Expected False for builder-self ask: {msg!r}"
        )


def test_builder_self_improvement_detected_by_system_terms() -> None:
    """High-signal builder-system terms are caught even without an explicit subject."""
    system_term_asks = [
        "fix the cost tracking",
        "improve cost tracking in this product",
        "the sprint decomposition is wrong",
        "update the quality gate logic",
        "the dispatch logic needs improvement",
        "builder's token tracking is off",
    ]
    for msg in system_term_asks:
        assert agent_message_intent.message_targets_builder_self(msg) is True, (
            f"Expected True for builder-system-term ask: {msg!r}"
        )


def test_app_improvement_asks_still_routed_correctly() -> None:
    """Genuine app feature requests must still be classified as feature specs."""
    app_asks = [
        "add a search feature to my todo app",
        "I want users to be able to filter todos",
        "build a user profile page",
        "add filtering to the app",
        "can you add dark mode to the app",
        "I need a way for users to export their data",
        "add a small visible empty-state hint under the todo list",
    ]
    for msg in app_asks:
        assert agent_message_intent.message_requests_feature_spec(msg) is True, (
            f"Expected True (feature spec) for app ask: {msg!r}"
        )
        # None of these should be flagged as builder-self
        assert agent_message_intent.message_targets_builder_self(msg) is False, (
            f"Expected False (not builder-self) for app ask: {msg!r}"
        )


def test_build_my_app_not_misclassified_as_builder_self() -> None:
    """'Build my app' / 'build it' must NOT be caught by the builder-self gate."""
    generic_build_asks = [
        "build my app",
        "build it",
        "build this feature",
        "continue building",
    ]
    for msg in generic_build_asks:
        assert agent_message_intent.message_targets_builder_self(msg) is False, (
            f"Expected False for generic build ask: {msg!r}"
        )
