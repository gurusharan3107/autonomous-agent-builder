"""Tests for operator-safe Agent transcript content."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from autonomous_agent_builder.db.models import ChatEvent
from autonomous_agent_builder.embedded.server import agent_chat_transcript


def test_operator_question_payload_removes_internal_lifecycle_terms() -> None:
    payload = agent_chat_transcript.operator_safe_question_payload(
        {
            "header": "Approval",
            "question": (
                "Should the next agreed improvement be a bounded approval/status "
                "recovery feature for this project?"
            ),
            "options": [
                {
                    "label": "Yes, scope it (Recommended)",
                    "description": (
                        "Define one shippable improvement that makes approval/blocker "
                        "status recoverable without large logs."
                    ),
                },
                {
                    "label": "Different backlog item",
                    "description": (
                        "Use the next turn to name a different app-facing improvement to scope."
                    ),
                },
            ],
            "multiSelect": False,
        }
    )

    rendered_text = json.dumps(payload)
    assert "backlog" not in rendered_text.lower()
    assert "bounded" not in rendered_text.lower()
    assert "large logs" not in rendered_text.lower()
    assert "approval/status" not in rendered_text.lower()
    assert "a an" not in rendered_text.lower()
    assert payload["options"][0]["label"] == "Yes, define it (Recommended)"
    assert payload["options"][1]["label"] == "Different improvement"


def test_serialize_event_sanitizes_existing_question_payloads() -> None:
    event = ChatEvent(
        id="question-1",
        session_id="session-1",
        event_type="ask_user_question",
        status="pending",
        created_at=datetime(2026, 5, 16, tzinfo=UTC),
        payload_json={
            "header": "Approval",
            "question": (
                "Should the next agreed improvement be a bounded approval/status "
                "recovery feature for this project?"
            ),
            "options": [
                {
                    "label": "Different backlog item",
                    "description": (
                        "Use the next turn to name a different app-facing improvement to scope."
                    ),
                }
            ],
        },
    )

    item = agent_chat_transcript.serialize_event(event)
    rendered_text = json.dumps(item.payload)
    assert "backlog" not in rendered_text.lower()
    assert "bounded" not in rendered_text.lower()
    assert "a an" not in rendered_text.lower()
    assert item.payload["options"][0]["label"] == "Different improvement"


def test_serialize_event_sanitizes_delivery_permission_assistant_content() -> None:
    event = ChatEvent(
        id="assistant-1",
        session_id="session-1",
        event_type="assistant_message",
        status="completed",
        created_at=datetime(2026, 5, 16, tzinfo=UTC),
        payload_json={
            "content": (
                "Ship one approval/status recovery improvement.\n\n"
                "Ready for Builder to start now, or should I hold?"
            ),
            "final": True,
        },
    )

    item = agent_chat_transcript.serialize_event(event)
    content = item.payload["content"]
    assert "approval/status" not in content.lower()
    assert "Ready for Builder to start now" in content
