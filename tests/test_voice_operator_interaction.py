"""Realtime voice operator interaction helper regressions."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autonomous_agent_builder.services.voice_operator_interaction import (
    approval_decision_from_utterance,
    bind_voice_call_session,
    dashboard_route_for_target,
    resolve_question_answer_value,
    runtime_display_name,
    voice_call_session_id,
    voice_runtime_sdk,
)


def test_resolve_question_answer_value_matches_recommended_and_multi_select():
    payload = {
        "recommended_index": 1,
        "multi_select": True,
        "options": [
            {"label": "FastAPI", "description": "Python API"},
            {"label": "Next.js (Recommended)", "description": "React app"},
        ],
    }

    assert resolve_question_answer_value("recommended", payload) == "Next.js (Recommended)"
    assert resolve_question_answer_value("all of them", payload) == "FastAPI, Next.js (Recommended)"
    assert resolve_question_answer_value("use next.js", payload) == "Next.js (Recommended)"


@pytest.mark.parametrize(
    ("message", "decision"),
    [
        ("yes, go ahead", "allow"),
        ("do not approve that", "deny"),
        ("tell me more", ""),
    ],
)
def test_approval_decision_from_utterance(message: str, decision: str):
    assert approval_decision_from_utterance(message) == decision


def test_runtime_and_dashboard_target_normalization():
    assert voice_runtime_sdk("Codex app-server") == "codex_sdk"
    assert voice_runtime_sdk("Claude Code") == "claude"
    assert runtime_display_name("codex_sdk") == "Codex SDK"
    assert dashboard_route_for_target("open the run trace") == "/?mode=trace"


def test_unknown_runtime_sdk_is_rejected():
    with pytest.raises(ValueError, match="sdk must be Codex SDK"):
        voice_runtime_sdk("unknown")


def test_voice_call_session_binding_initializes_app_state():
    app = SimpleNamespace(state=SimpleNamespace())

    bind_voice_call_session(app, "rtc_call", "session-1")

    assert voice_call_session_id(app, "rtc_call") == "session-1"
    assert voice_call_session_id(app, "") == ""
