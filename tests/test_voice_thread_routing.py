"""Realtime voice thread routing regressions."""

from __future__ import annotations

from autonomous_agent_builder.services.voice_thread_routing import VoiceThreadRouter


def test_status_question_routes_to_current_builder_status():
    route = VoiceThreadRouter().route(
        operator_utterance="what is builder doing?",
        latest_session_id="session-1",
        active_run=False,
        pending_operator_items=[],
    )

    assert route.route == "status"
    assert route.thread_mode == "current"
    assert route.target_session_id == "session-1"
    assert route.as_dict()["routing_reason"] == "operator asked for Builder status"


def test_single_pending_question_answer_routes_to_question_event():
    route = VoiceThreadRouter().route(
        operator_utterance="use recommended",
        latest_session_id="session-1",
        active_run=True,
        pending_operator_items=[
            {"type": "ask_user_question", "event_id": "event-question-1"},
        ],
    )

    assert route.route == "answer_pending"
    assert route.thread_mode == "current"
    assert route.target_event_id == "event-question-1"
    assert not route.high_impact


def test_multiple_pending_approvals_request_clarification():
    route = VoiceThreadRouter().route(
        operator_utterance="approve it",
        latest_session_id="session-1",
        active_run=True,
        pending_operator_items=[
            {"type": "tool_approval_request", "event_id": "event-approval-1"},
            {"type": "tool_approval_request", "event_id": "event-approval-2"},
        ],
    )

    assert route.route == "clarify"
    assert route.thread_mode == "current"
    assert route.high_impact
    assert route.clarifying_question == "Which pending approval should I use?"


def test_recovery_and_new_topic_routes_remain_distinct():
    router = VoiceThreadRouter()

    recovery = router.route(
        operator_utterance="recover the blocked task",
        latest_session_id="session-1",
        active_run=False,
        pending_operator_items=[],
    )
    new_topic = router.route(
        operator_utterance="start a new product correction",
        latest_session_id="session-1",
        active_run=True,
        pending_operator_items=[],
    )

    assert recovery.route == "recover"
    assert recovery.thread_mode == "current"
    assert recovery.high_impact
    assert new_topic.route == "new"
    assert new_topic.thread_mode == "new"
    assert new_topic.target_session_id == ""
