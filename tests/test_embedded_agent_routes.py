from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from autonomous_agent_builder.db.models import (
    ChatEvent,
    ChatSession,
)
from autonomous_agent_builder.embedded.server import agent_chat_transcript, agent_message_intent
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes


def test_typed_operator_prompt_contract_stays_model_backed() -> None:
    agent_source = Path(
        "src/autonomous_agent_builder/embedded/server/routes/agent.py"
    ).read_text(encoding="utf-8")
    claude_contract = Path("CLAUDE.md").read_text(encoding="utf-8")
    sdk_rubric = Path("docs/rubric/sdk-backed-agent-page-agent.md").read_text(
        encoding="utf-8"
    )
    behavior_rubric = Path(
        "docs/rubric/deterministic-vs-model-backed-agent-behavior.md"
    ).read_text(encoding="utf-8")
    runtime_contract = Path("docs/references/runtime-switch-dashboard-contract.md").read_text(
        encoding="utf-8"
    )

    assert "_deterministic_feature_spec_from_message" not in agent_source
    assert '"stop_reason": "deterministic_status_check"' not in agent_source
    assert "task_recovered_and_dispatched" not in agent_source
    assert "Typed operator prompts are different" in claude_contract
    assert "must stay model-backed" in sdk_rubric
    assert "Typed operator prompt interpretation is always model-backed" in behavior_rubric
    assert "not natural prompt interpretation" in runtime_contract


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

    status = agent_chat_transcript.latest_status(session, active_run=False)

    assert status is not None
    assert status["running"] is False
    assert status["stop_reason"] == "stale_running_status_no_active_task"


def test_general_chat_prompt_turns_continue_building_into_dispatch_request(tmp_path):
    prompt = agent_routes._general_chat_prompt(tmp_path, "Continue building my app.")

    assert "Autonomous continuation mode is active" in prompt
    assert "mcp__builder__board" in prompt
    assert "mcp__builder__task_dispatch" in prompt
    assert "Do not ask the user which listed feature to build" in prompt


def test_general_chat_prompt_requires_bounded_retrieval_before_missing_context_clarification(tmp_path):
    prompt = agent_routes._general_chat_prompt(
        tmp_path,
        "Please create the backlog for the sprint, starting with the notification feature recommendations discussed.",
    )

    assert "prior discussion, memory, recommendations, existing backlog" in prompt
    assert "first inspect the relevant Builder" in prompt
    assert "distinguish global board counts from current or selected sprint counts" in prompt
    assert "builder memory search" in prompt
    assert "builder backlog item list/show" in prompt
    assert "For observability, metrics, or recommendation questions" in prompt
    assert "use compact Builder-owned evidence first" in prompt
    assert "Do not say you will check memory, backlog, board, or project state unless you actually use" in prompt
    assert "Ask for clarification only after bounded retrieval cannot" in prompt

def test_sprint_planning_intent_accepts_numbered_sprint_language() -> None:
    assert agent_message_intent.message_requests_sprint_planning("Start Sprint 2 planning for feature-02")
    assert agent_message_intent.message_requests_sprint_planning("I want to start next sprint")


def test_delivery_progress_intent_does_not_require_exact_sprint_phrase() -> None:
    assert agent_message_intent.message_requests_autonomous_continuation("What should we build next?")
    assert agent_message_intent.message_requests_autonomous_continuation("Move the product forward")
    assert agent_message_intent.message_requests_autonomous_continuation("Please proceed")
    assert agent_message_intent.message_requests_autonomous_continuation("Can you go ahead?")
    assert agent_message_intent.message_requests_autonomous_continuation("Can you start with the task?")
    assert agent_message_intent.message_requests_ambiguous_continuation("Can you go ahead?")
    assert agent_message_intent.message_requests_ambiguous_continuation("Can you start with the task?")
    assert not agent_message_intent.message_requests_ambiguous_continuation("I want to start next sprint")
    assert not agent_message_intent.message_requests_autonomous_continuation("Update the documentation")
    assert not agent_message_intent.message_requests_autonomous_continuation(
        "Can you confirm the current status of the recovery action for the blocked task "
        "Verify Deterministic tests and build script for shipping?"
    )
    assert not agent_message_intent.message_requests_autonomous_continuation(
        "Can you verify whether the blocked task information is accurate?"
    )
