"""Regression: the interactive chat lane must run under a permission mode that
keeps AskUserQuestion enabled.

Root cause this guards (IMP-018): the global ``permission_mode="dontAsk"``
bypasses the SDK ``can_use_tool`` callback. That callback (``_authorize_chat_tool``)
is the *only* place AskUserQuestion answers and tool-approval cards are produced,
so ``dontAsk`` silently disables structured operator questions and degrades the
requirements interview to free-text Q&A. The fix runs the ``chat`` agent under
``permission_mode="default"`` and auto-allows its pre-approved tools so no new
approval-card friction is introduced.
"""

from __future__ import annotations

import asyncio

import pytest

from autonomous_agent_builder.agents.definitions import get_agent_definition
from autonomous_agent_builder.embedded.server import agent_chat_transcript
from autonomous_agent_builder.embedded.server.chat_turn_intent import ChatTurnCallbackState
from autonomous_agent_builder.embedded.server.routes import agent as agent_routes


def test_chat_agent_runs_under_default_permission_mode() -> None:
    # "dontAsk" bypasses can_use_tool and disables AskUserQuestion. The interactive
    # operator lane must use a mode that invokes the callback.
    assert get_agent_definition("chat").permission_mode == "default"


def test_interview_prompt_does_not_claim_question_tool_disabled() -> None:
    prompt = get_agent_definition("init-project-chat").prompt_template
    assert "AskUserQuestion" in prompt
    # The old band-aid prose told the model the permission mode was 'dontAsk' and
    # that prompts were auto-approved. That misleading framing must not return.
    assert "dontAsk" not in prompt
    assert "auto-approved" not in prompt
    # The prompt should now affirm the tool is available, not hedge about it.
    assert "is available" in prompt.lower() or "is available in this lane" in prompt.lower()


class _FakeEvent:
    def __init__(self, event_id: int = 1) -> None:
        self.id = event_id


class _FakeSerialized:
    def model_dump(self, *_, **__):  # noqa: ANN002, ANN003
        return {}


class _FakeHub:
    def __init__(self, answer_value: str) -> None:
        self._answer_value = answer_value
        self.published: list = []

    async def create_pending_answer(self, _session_id, _event_id):
        fut: asyncio.Future = asyncio.Future()
        fut.set_result({"answer_value": self._answer_value})
        return fut

    async def publish(self, _session_id, payload):
        self.published.append(payload)


def _state(hub, preapproved=frozenset()) -> ChatTurnCallbackState:
    return ChatTurnCallbackState(
        session_id="sess-1",
        hub=hub,
        project_root=__import__("pathlib").Path("/tmp"),
        agent_name="chat",
        agent_max_turns=20,
        active_specialist=None,
        user_message="hi",
        preapproved_tools=preapproved,
    )


@pytest.mark.asyncio
async def test_authorize_chat_tool_collects_askuserquestion_answers(monkeypatch) -> None:
    async def _fake_append(*_args, **_kwargs):
        return _FakeEvent()

    monkeypatch.setattr(agent_routes, "_append_chat_event", _fake_append)
    monkeypatch.setattr(agent_chat_transcript, "serialize_event", lambda _e: _FakeSerialized())

    hub = _FakeHub(answer_value="PostgreSQL")
    state = _state(hub)
    result = await agent_routes._authorize_chat_tool(
        state,
        "AskUserQuestion",
        {
            "questions": [
                {
                    "question": "Which database should we use?",
                    "header": "Database",
                    "options": [{"label": "PostgreSQL"}, {"label": "SQLite"}],
                    "multiSelect": False,
                }
            ]
        },
    )
    # The callback must return the operator's answer to the model, not deny it.
    assert result.updated_input["answers"]["Which database should we use?"] == "PostgreSQL"


@pytest.mark.parametrize("tool_name", ["Edit", "Write", "Bash", "MultiEdit", "NotebookEdit"])
@pytest.mark.asyncio
async def test_authorize_chat_tool_denies_ungranted_mutating_builtins(
    monkeypatch, tool_name
) -> None:
    """IMP-020: the chat lane denies ungranted mutating built-ins (no approval
    card) and routes the model to capture-and-dispatch. An operator clicking
    Approve on a direct Edit/Write/Bash would bypass the dashboard-first
    backlog -> task -> approval -> execution lifecycle."""
    append_calls: list = []

    async def _fake_append(*args, **kwargs):
        append_calls.append((args, kwargs))
        return _FakeEvent()

    monkeypatch.setattr(agent_routes, "_append_chat_event", _fake_append)
    monkeypatch.setattr(agent_chat_transcript, "serialize_event", lambda _e: _FakeSerialized())

    hub = _FakeHub(answer_value="allow")  # would approve if a card were offered
    state = _state(hub)
    result = await agent_routes._authorize_chat_tool(
        state, tool_name, {"file_path": "/app/src/app.js", "command": "echo hi"}
    )
    # Denied, not approved — even though the fake hub would answer "allow".
    assert result.__class__.__name__ == "PermissionResultDeny"
    assert "task_dispatch" in result.message
    # A tool_error event is emitted so the operator sees the routing reason,
    # but NO pending approval card (create_pending_answer never called).
    assert append_calls, "expected a tool_error event to be appended"
    assert all(kwargs.get("event_type") == "tool_error" for _args, kwargs in append_calls)


@pytest.mark.asyncio
async def test_authorize_chat_tool_keeps_card_for_granted_mutating_tool(monkeypatch) -> None:
    """The deny is scoped to *ungranted* built-ins. A granted mutating built-in
    (in preapproved_tools) still auto-allows via the preapproved path — the
    tested approval-card flow for legitimately-granted tools is untouched."""
    append_calls: list = []

    async def _fake_append(*args, **kwargs):
        append_calls.append((args, kwargs))
        return _FakeEvent()

    monkeypatch.setattr(agent_routes, "_append_chat_event", _fake_append)
    monkeypatch.setattr(agent_chat_transcript, "serialize_event", lambda _e: _FakeSerialized())

    hub = _FakeHub(answer_value="")
    state = _state(hub, preapproved=frozenset({"Bash"}))
    result = await agent_routes._authorize_chat_tool(state, "Bash", {"command": "ls"})
    assert result.updated_input == {"command": "ls"}
    assert append_calls == []


@pytest.mark.asyncio
async def test_authorize_chat_tool_auto_allows_preapproved_tool(monkeypatch) -> None:
    append_calls: list = []

    async def _fake_append(*args, **kwargs):
        append_calls.append((args, kwargs))
        return _FakeEvent()

    monkeypatch.setattr(agent_routes, "_append_chat_event", _fake_append)
    monkeypatch.setattr(agent_chat_transcript, "serialize_event", lambda _e: _FakeSerialized())

    hub = _FakeHub(answer_value="")
    state = _state(hub, preapproved=frozenset({"mcp__builder__memory_add"}))
    result = await agent_routes._authorize_chat_tool(
        state, "mcp__builder__memory_add", {"text": "note"}
    )
    # Pre-approved tools execute without an approval card (no event appended).
    assert result.updated_input == {"text": "note"}
    assert append_calls == []
