"""Delivery permission and scope continuation handlers extracted from routes/agent.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autonomous_agent_builder.agents.definitions import get_agent_definition
from autonomous_agent_builder.db.models import ChatEvent
from autonomous_agent_builder.db.session import get_session_factory
from autonomous_agent_builder.embedded.server import agent_chat_transcript
from autonomous_agent_builder.embedded.server.agent_chat_events import (
    append_chat_event as _append_chat_event,
)
from autonomous_agent_builder.embedded.server.agent_chat_events import (
    append_voice_final_summary_if_needed as _append_voice_final_summary_if_needed,
)
from autonomous_agent_builder.embedded.server.agent_feature_delivery import (
    feature_for_delivery_permission_question as _feature_for_delivery_permission_question,
)
from autonomous_agent_builder.embedded.server.agent_runtime_status import (
    runtime_metadata_for_agent as _runtime_metadata_for_agent,
)
from autonomous_agent_builder.embedded.server.agent_sprint_planning import (
    create_delivery_plan_for_approved_features as _create_delivery_plan_for_approved_features,
)
from autonomous_agent_builder.embedded.server.agent_sprint_planning import (
    handle_sprint_planning_turn as _handle_sprint_planning_turn,
)
from autonomous_agent_builder.embedded.server.chat_state import ChatSessionHub


async def _continue_after_delivery_permission_question(
    app: Any,
    session_id: str,
    event: ChatEvent,
    *,
    answer_value: str,
) -> None:
    project_root = Path(app.state.project_root)
    hub: ChatSessionHub = app.state.chat_hub
    runtime_payload = _runtime_metadata_for_agent("chat", project_root)
    running_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload={
            **runtime_payload,
            "running": True,
            "current_turn": 0,
            "max_turns": get_agent_definition("chat").max_turns,
            "tokens_used": 0,
            "cost_usd": 0.0,
        },
        status="running",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(running_event).model_dump(mode="json"))

    answer_lower = answer_value.strip().lower()
    if answer_lower.startswith("hold"):
        visible_response = "Delivery is on hold. I kept the captured improvement unchanged."
        stop_reason = "delivery_permission_held"
    else:
        session_factory = get_session_factory()
        async with session_factory() as db:
            feature = await _feature_for_delivery_permission_question(db, event)
        if feature is None:
            visible_response = (
                "I could not find the captured improvement for this delivery decision. "
                "Please restate the improvement before starting work."
            )
            stop_reason = "delivery_permission_missing_feature"
        else:
            visible_response = await _handle_sprint_planning_turn(
                session_id,
                feature.title,
                project_root,
                hub,
                selected_feature_ids=[feature.id],
                skip_scope_approval=True,
            )
            stop_reason = "delivery_permission_selected_feature"

    assistant_event = await _append_chat_event(
        session_id,
        event_type="assistant_message",
        payload={"content": visible_response, "final": True},
        status="completed",
        mirror_message=("assistant", visible_response, 0, 0.0),
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(assistant_event).model_dump(mode="json"))
    await _append_voice_final_summary_if_needed(
        session_id,
        assistant_event_id=assistant_event.id,
        content=visible_response,
        hub=hub,
    )
    status_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload={
            **runtime_payload,
            "running": False,
            "current_turn": 0,
            "max_turns": get_agent_definition("chat").max_turns,
            "tokens_used": 0,
            "cost_usd": 0.0,
            "stop_reason": stop_reason,
        },
        status="completed",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(status_event).model_dump(mode="json"))


async def _complete_persisted_delivery_scope_approval(
    app: Any,
    session_id: str,
    event: ChatEvent,
    *,
    decision: str,
) -> None:
    project_root = Path(app.state.project_root)
    hub: ChatSessionHub = app.state.chat_hub
    runtime_payload = _runtime_metadata_for_agent("chat", project_root)
    running_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload={
            **runtime_payload,
            "running": True,
            "current_turn": 0,
            "max_turns": get_agent_definition("chat").max_turns,
            "tokens_used": 0,
            "cost_usd": 0.0,
        },
        status="running",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(running_event).model_dump(mode="json"))

    if decision == "allow":
        event_payload = event.payload_json if isinstance(event.payload_json, dict) else {}
        tool_input = event_payload.get("tool_input") if isinstance(event_payload, dict) else {}
        tool_input_data = tool_input if isinstance(tool_input, dict) else {}
        feature_ids = [
            str(feature_id).strip()
            for feature_id in tool_input_data.get("feature_ids", [])
            if str(feature_id).strip()
        ]
        visible_response = await _create_delivery_plan_for_approved_features(
            session_id,
            project_root,
            feature_ids,
        )
        stop_reason = "delivery_scope_approved_and_dispatched"
    else:
        visible_response = "Delivery scope was not approved. I kept the captured improvement unchanged."
        stop_reason = "delivery_scope_denied"

    assistant_event = await _append_chat_event(
        session_id,
        event_type="assistant_message",
        payload={"content": visible_response, "final": True},
        status="completed",
        mirror_message=("assistant", visible_response, 0, 0.0),
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(assistant_event).model_dump(mode="json"))
    await _append_voice_final_summary_if_needed(
        session_id,
        assistant_event_id=assistant_event.id,
        content=visible_response,
        hub=hub,
    )
    status_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload={
            **runtime_payload,
            "running": False,
            "current_turn": 0,
            "max_turns": get_agent_definition("chat").max_turns,
            "tokens_used": 0,
            "cost_usd": 0.0,
            "stop_reason": stop_reason,
        },
        status="completed",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(status_event).model_dump(mode="json"))
