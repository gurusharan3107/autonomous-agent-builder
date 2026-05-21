"""Chat result publishing helpers extracted from routes/agent.py."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.db.models import ChatSession, utcnow
from autonomous_agent_builder.db.session import get_session_factory
from autonomous_agent_builder.embedded.server import agent_chat_transcript
from autonomous_agent_builder.embedded.server.agent_chat_events import (
    append_chat_event as _append_chat_event,
    append_voice_final_summary_if_needed as _append_voice_final_summary_if_needed,
)
from autonomous_agent_builder.embedded.server.agent_feature_delivery import (
    persist_feature_spec as _persist_feature_spec,
)
from autonomous_agent_builder.embedded.server.agent_feature_payloads import (
    extract_feature_list_payload as _extract_feature_list_payload,
    extract_feature_spec_payload as _extract_feature_spec_payload,
)
from autonomous_agent_builder.embedded.server.agent_project_context import (
    apply_chat_answers_to_project_context as _apply_chat_answers_to_project_context,
    apply_forward_project_constraints as _apply_forward_project_constraints,
    collect_ask_user_question_answers as _collect_ask_user_question_answers,
    extract_technical_constraints as _extract_technical_constraints,
    inject_feature_list_constraints as _inject_feature_list_constraints,
)
from autonomous_agent_builder.embedded.server.agent_runtime_status import (
    chat_run_status_payload as _chat_run_status_payload,
)
from autonomous_agent_builder.embedded.server.agent_sprint_planning import (
    append_persisted_delivery_permission_question_if_needed as _append_persisted_delivery_permission_question_if_needed,
    handle_sprint_planning_turn as _handle_sprint_planning_turn,
)
from autonomous_agent_builder.embedded.server.chat_state import ChatSessionHub
from autonomous_agent_builder.embedded.server.chat_turn_intent import ChatRunTotals
from autonomous_agent_builder.embedded.server.documentation_routing import ActiveSpecialistRoute
from autonomous_agent_builder.onboarding import (
    load_onboarding_state,
    sync_forward_engineering_feature_backlog,
    write_feature_list_file,
)
from autonomous_agent_builder.services.readiness import assess_readiness


async def _publish_agent_run_error_result(
    *,
    session_id: str,
    hub: ChatSessionHub,
    agent_name: str,
    project_root: Path,
    active_specialist: ActiveSpecialistRoute | None,
    publish_specialist_status: Callable[..., Awaitable[None]],
    result: RunResult,
    totals: ChatRunTotals,
    max_turns: int,
) -> None:
    if active_specialist is not None:
        await publish_specialist_status(
            "blocked",
            active_specialist.policy.blocked_summary,
            status="completed",
        )
    error_content = f"Error: {result.error}"
    error_event = await _append_chat_event(
        session_id,
        event_type="run_error",
        payload={"content": error_content},
        status="completed",
        mirror_message=("assistant", error_content, 0, 0.0),
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(error_event).model_dump(mode="json"))
    status_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload=_chat_run_status_payload(
            agent_name=agent_name,
            project_root=project_root,
            result=result,
            totals=totals,
            max_turns=max_turns,
            extra={"error": result.error},
        ),
        status="completed",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(status_event).model_dump(mode="json"))


async def _publish_provider_limit_result(
    *,
    session_id: str,
    hub: ChatSessionHub,
    agent_name: str,
    project_root: Path,
    active_specialist: ActiveSpecialistRoute | None,
    publish_specialist_status: Callable[..., Awaitable[None]],
    result: RunResult,
    totals: ChatRunTotals,
    max_turns: int,
) -> None:
    provider_limit = result.provider_limit or {
        "code": result.stop_reason or "capability_limit",
        "reason": result.output_text or "Agent run hit a capability limit.",
    }
    if active_specialist is not None:
        await publish_specialist_status(
            "blocked",
            active_specialist.policy.blocked_summary,
            status="completed",
        )
    limit_text = result.output_text or "The selected runtime hit a provider limit."
    visible_response = f"Provider limit blocked this run: {limit_text}"
    assistant_event = await _append_chat_event(
        session_id,
        event_type="assistant_message",
        payload={
            "content": visible_response,
            "final": True,
            "provider_limit": provider_limit,
        },
        status="blocked",
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
        payload=_chat_run_status_payload(
            agent_name=agent_name,
            project_root=project_root,
            result=result,
            totals=totals,
            max_turns=max_turns,
            stop_reason="provider_limit",
            extra={"provider_limit": provider_limit},
        ),
        status="blocked",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(status_event).model_dump(mode="json"))


async def _publish_successful_chat_result(
    *,
    session_id: str,
    user_message: str,
    hub: ChatSessionHub,
    agent_name: str,
    project_root: Path,
    active_specialist: ActiveSpecialistRoute | None,
    publish_specialist_status: Callable[..., Awaitable[None]],
    result: RunResult,
    run_totals: ChatRunTotals,
    max_turns: int,
) -> None:
    visible_response = result.output_text or "No response from agent"
    start_sprint_scope_after_response = False
    if agent_name == "init-project-chat":
        visible_response, feature_payload = _extract_feature_list_payload(
            project_root, visible_response
        )
        if feature_payload is not None:
            start_sprint_scope_after_response = True
            technical_constraints = _extract_technical_constraints(user_message)
            feature_payload = _inject_feature_list_constraints(
                feature_payload,
                technical_constraints,
            )
            write_feature_list_file(project_root, feature_payload)
            session_factory = get_session_factory()
            async with session_factory() as db:
                chat_answers = await _collect_ask_user_question_answers(db, session_id)
                if chat_answers:
                    _apply_chat_answers_to_project_context(project_root, chat_answers)
                await _apply_forward_project_constraints(
                    db,
                    project_root,
                    technical_constraints,
                )
                if await sync_forward_engineering_feature_backlog(db, project_root):
                    await db.commit()
            assess_readiness(
                project_root,
                onboarding_state=load_onboarding_state(project_root),
                write=True,
            )
            save_note = (
                "I captured the delivery scope and prepared Builder's internal plan. "
                "Next I will ask what to ship first."
            )
            visible_response = (
                f"{visible_response}\n\n{save_note}".strip() if visible_response else save_note
            )
    elif agent_name == "chat" and active_specialist is None:
        visible_response, feature_spec_payload = _extract_feature_spec_payload(visible_response)
        if feature_spec_payload is not None:
            session_factory = get_session_factory()
            async with session_factory() as db:
                feature = await _persist_feature_spec(db, feature_spec_payload)
            if feature is not None:
                save_note = (
                    f"I captured that improvement as `{feature.title}`. "
                    "Ready for Builder to start now, or should I hold?"
                )
                visible_response = (
                    f"{visible_response}\n\n{save_note}".strip() if visible_response else save_note
                )
    if active_specialist is not None:
        await publish_specialist_status(
            "completed",
            active_specialist.policy.completed_summary,
            status="completed",
        )

    session_factory = get_session_factory()
    async with session_factory() as db:
        session = await db.get(ChatSession, session_id)
        if session is not None and result.session_id:
            session.sdk_session_id = result.session_id
            session.updated_at = utcnow()
            await db.commit()

    assistant_event = await _append_chat_event(
        session_id,
        event_type="assistant_message",
        payload={"content": visible_response, "final": True},
        status="completed",
        mirror_message=(
            "assistant",
            visible_response,
            run_totals.token_total,
            run_totals.cost_usd,
        ),
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(assistant_event).model_dump(mode="json"))
    permission_question = await _append_persisted_delivery_permission_question_if_needed(
        session_id,
        assistant_event_id=assistant_event.id,
        response_text=visible_response,
        hub=hub,
    )
    if permission_question is None:
        await _append_voice_final_summary_if_needed(
            session_id,
            assistant_event_id=assistant_event.id,
            content=visible_response,
            hub=hub,
        )
    if start_sprint_scope_after_response:
        sprint_response = await _handle_sprint_planning_turn(
            session_id,
            "sprint planning",
            project_root,
            hub,
        )
        sprint_event = await _append_chat_event(
            session_id,
            event_type="assistant_message",
            payload={"content": sprint_response, "final": True},
            status="completed",
            mirror_message=("assistant", sprint_response, 0, 0.0),
        )
        await hub.publish(session_id, agent_chat_transcript.serialize_event(sprint_event).model_dump(mode="json"))
        await _append_voice_final_summary_if_needed(
            session_id,
            assistant_event_id=sprint_event.id,
            content=sprint_response,
            hub=hub,
        )
    status_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload=_chat_run_status_payload(
            agent_name=agent_name,
            project_root=project_root,
            result=result,
            totals=run_totals,
            max_turns=max_turns,
        ),
        status="completed",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(status_event).model_dump(mode="json"))
