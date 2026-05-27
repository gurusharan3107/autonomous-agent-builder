"""Agent chat API routes for embedded server."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from autonomous_agent_builder.agents.definitions import get_agent_definition
from autonomous_agent_builder.agents.execution_policy import resolve_agent_runtime_policy
from autonomous_agent_builder.agents.runner import AgentRunner
from autonomous_agent_builder.agents.tool_registry import is_read_only_tool
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import (
    ChatEvent,
    ChatSession,
    utcnow,
)
from autonomous_agent_builder.db.session import get_db, get_session_factory
from autonomous_agent_builder.embedded.server import agent_chat_sessions, agent_chat_transcript
from autonomous_agent_builder.embedded.server.agent_api_models import (
    ChatHistoryResponse,
    ChatMetaResponse,
    ChatRequest,
    ChatRespondRequest,
    ChatRespondResponse,
    ChatResponse,
    ChatSessionItem,
    ChatSessionListResponse,
    RuntimeSettingsUpdate,
)
from autonomous_agent_builder.embedded.server.agent_board_state import (
    _approve_review_gate_for_continuation as _approve_review_gate_for_continuation,
)
from autonomous_agent_builder.embedded.server.agent_board_state import (
    _first_dispatchable_task as _first_dispatchable_task,
)
from autonomous_agent_builder.embedded.server.agent_board_state import (
    _first_pending_review_approval as _first_pending_review_approval,
)
from autonomous_agent_builder.embedded.server.agent_board_state import (
    _first_recoverable_task as _first_recoverable_task,
)
from autonomous_agent_builder.embedded.server.agent_board_state import (
    _has_builder_work_state as _has_builder_work_state,
)
from autonomous_agent_builder.embedded.server.agent_board_state import (
    _has_dispatchable_task_state as _has_dispatchable_task_state,
)
from autonomous_agent_builder.embedded.server.agent_board_state import (
    _has_ready_delivery_feature_state as _has_ready_delivery_feature_state,
)
from autonomous_agent_builder.embedded.server.agent_board_state import (
    _has_recoverable_task_state as _has_recoverable_task_state,
)
from autonomous_agent_builder.embedded.server.agent_board_state import (
    _needs_init_project_bootstrap as _needs_init_project_bootstrap,
)
from autonomous_agent_builder.embedded.server.agent_board_state import (
    _normalized_follow_up_message as _normalized_follow_up_message,
)
from autonomous_agent_builder.embedded.server.agent_board_state import (
    _stream_deltas_are_user_visible as _stream_deltas_are_user_visible,
)
from autonomous_agent_builder.embedded.server.agent_chat_events import (
    append_chat_event as _append_chat_event,
)
from autonomous_agent_builder.embedded.server.agent_chat_events import (
    update_request_event as _update_request_event,
)
from autonomous_agent_builder.embedded.server.agent_chat_result_publisher import (
    _publish_agent_run_error_result,
    _publish_provider_limit_result,
    _publish_successful_chat_result,
)
from autonomous_agent_builder.embedded.server.agent_control_owners import (
    reconcile_session_control_owners,
)
from autonomous_agent_builder.embedded.server.agent_delivery_closeout import (
    append_delivery_closeout_if_ready as _append_delivery_closeout_if_ready,
)
from autonomous_agent_builder.embedded.server.agent_delivery_continuation import (
    _complete_persisted_delivery_scope_approval,
    _continue_after_delivery_permission_question,
)
from autonomous_agent_builder.embedded.server.agent_feature_delivery import (
    feature_for_delivery_permission_question as _feature_for_delivery_permission_question,
)
from autonomous_agent_builder.embedded.server.agent_feature_delivery import (
    latest_saved_feature_for_delivery as _latest_saved_feature_for_delivery,
)
from autonomous_agent_builder.embedded.server.agent_feature_delivery import (
    schedule_task_dispatch as _schedule_task_dispatch,
)
from autonomous_agent_builder.embedded.server.agent_feature_payloads import (
    session_has_pending_feature_spec as _session_has_pending_feature_spec,
)
from autonomous_agent_builder.embedded.server.agent_feature_payloads import (
    session_has_saved_feature_for_delivery as _session_has_saved_feature_for_delivery,
)
from autonomous_agent_builder.embedded.server.agent_message_intent import (
    message_confirms_feature_delivery as _message_confirms_feature_delivery,
)
from autonomous_agent_builder.embedded.server.agent_message_intent import (
    message_requests_ambiguous_continuation as _message_requests_ambiguous_continuation,
)
from autonomous_agent_builder.embedded.server.agent_message_intent import (
    message_requests_autonomous_continuation as _message_requests_autonomous_continuation,
)
from autonomous_agent_builder.embedded.server.agent_message_intent import (
    message_requests_feature_delivery as _message_requests_feature_delivery,
)
from autonomous_agent_builder.embedded.server.agent_message_intent import (
    message_requests_sprint_planning as _message_requests_sprint_planning,
)
from autonomous_agent_builder.embedded.server.agent_observability_context import (
    observability_context_for_prompt as _observability_context_for_prompt,
)
from autonomous_agent_builder.embedded.server.agent_prompt_builders import (
    _SPECIALIST_ROUTE_POLICIES as _SPECIALIST_ROUTE_POLICIES,  # noqa: F401
)
from autonomous_agent_builder.embedded.server.agent_prompt_builders import (
    _feature_spec_chat_prompt as _feature_spec_chat_prompt,
)
from autonomous_agent_builder.embedded.server.agent_prompt_builders import (
    _general_chat_prompt as _general_chat_prompt,
)
from autonomous_agent_builder.embedded.server.agent_prompt_builders import (
    _init_project_chat_prompt as _init_project_chat_prompt,
)
from autonomous_agent_builder.embedded.server.agent_prompt_builders import (
    _init_project_continuation_prompt as _init_project_continuation_prompt,
)
from autonomous_agent_builder.embedded.server.agent_prompt_builders import (
    _init_project_requires_autonomous_continuation as _init_project_requires_autonomous_continuation,
)
from autonomous_agent_builder.embedded.server.agent_prompt_builders import (
    _message_matches_documentation_continuation as _message_matches_documentation_continuation,
)
from autonomous_agent_builder.embedded.server.agent_prompt_builders import (
    _message_needs_recent_context as _message_needs_recent_context,
)
from autonomous_agent_builder.embedded.server.agent_prompt_builders import (
    _question_tool_guidance as _question_tool_guidance,
)
from autonomous_agent_builder.embedded.server.agent_prompt_builders import (
    _recent_chat_context_for_prompt as _recent_chat_context_for_prompt,
)
from autonomous_agent_builder.embedded.server.agent_prompt_builders import (
    _select_specialist_route as _select_specialist_route,
)
from autonomous_agent_builder.embedded.server.agent_runtime_status import (
    chat_runtime_metadata as _chat_runtime_metadata,
)
from autonomous_agent_builder.embedded.server.agent_runtime_status import (
    initial_status as _initial_status,
)
from autonomous_agent_builder.embedded.server.agent_runtime_status import (
    runtime_metadata_for_agent as _runtime_metadata_for_agent,
)
from autonomous_agent_builder.embedded.server.agent_sprint_planning import (
    handle_sprint_planning_turn as _handle_sprint_planning_turn,
)
from autonomous_agent_builder.embedded.server.agent_sprint_planning import (
    session_has_pending_sprint_planning as _session_has_pending_sprint_planning,
)
from autonomous_agent_builder.embedded.server.agent_tool_policy import (
    extract_tool_text_payload as _extract_tool_text_payload,
)
from autonomous_agent_builder.embedded.server.agent_tool_policy import (
    feature_spec_tool_denial as _feature_spec_tool_denial,
)
from autonomous_agent_builder.embedded.server.agent_tool_policy import (
    kb_validate_policy as _kb_validate_policy,
)
from autonomous_agent_builder.embedded.server.agent_tool_policy import (
    normalize_tool_response as _normalize_tool_response,
)
from autonomous_agent_builder.embedded.server.agent_tool_policy import (
    permission_allow as _permission_allow,
)
from autonomous_agent_builder.embedded.server.agent_tool_policy import (
    permission_deny as _permission_deny,
)
from autonomous_agent_builder.embedded.server.agent_tool_policy import (
    tool_summary as _tool_summary,
)
from autonomous_agent_builder.embedded.server.chat_state import ChatSessionHub
from autonomous_agent_builder.embedded.server.chat_turn_direct_actions import (
    publish_direct_chat_turn_if_handled,
)
from autonomous_agent_builder.embedded.server.chat_turn_intent import (
    ChatTurnCallbackState,
    ChatTurnIntent,
    resolve_chat_turn_intent,
)
from autonomous_agent_builder.embedded.server.chat_turn_prompting import (
    build_chat_turn_prompt_plan,
    publish_chat_context_budget,
)
from autonomous_agent_builder.embedded.server.chat_turn_publication import ChatTurnPublisher
from autonomous_agent_builder.embedded.server.chat_turn_runtime import run_chat_runtime_loop
from autonomous_agent_builder.embedded.server.documentation_routing import (
    ActiveSpecialistRoute,
    SpecialistRoutePolicy,  # noqa: F401
)
from autonomous_agent_builder.embedded.server.documentation_routing import (
    message_has_documentation_intent as _message_has_documentation_intent,
)
from autonomous_agent_builder.embedded.server.documentation_routing import (
    resolve_documentation_action as _resolve_documentation_action,  # noqa: F401
)
from autonomous_agent_builder.logs.diagnostics import summarize_chat_event, summarize_tool_event
from autonomous_agent_builder.onboarding import publish_onboarding_snapshot
from autonomous_agent_builder.runtime import create_runtime
from autonomous_agent_builder.services.project_context import request_project_root
from autonomous_agent_builder.services.runtime_settings import (
    persist_runtime_settings,
    reconcile_runtime_project_state,
    resolve_project_runtime_config,
    runtime_settings_payload,
)

router = APIRouter()

_INIT_PROJECT_MAX_REQUIREMENTS_CONTINUATIONS = 6
_USER_QUESTION_TOOL_NAMES = {
    "AskUserQuestion",
    "request_user_input",
}
def _project_root(request: Request) -> Path:
    return request_project_root(request)


def _chat_hub(request: Request) -> ChatSessionHub:
    return request.app.state.chat_hub


async def _resolve_chat_turn_intent(
    *,
    session: ChatSession,
    user_message: str,
    agent_name: str,
    active_specialist: ActiveSpecialistRoute | None,
) -> ChatTurnIntent:
    autonomous_continuation_requested = _message_requests_autonomous_continuation(user_message)
    ambiguous_continuation_requested = _message_requests_ambiguous_continuation(user_message)
    active_specialist_present = active_specialist is not None
    dispatchable_task_exists = False
    ready_delivery_feature_exists = False
    if agent_name == "chat" and not active_specialist_present:
        session_factory = get_session_factory()
        async with session_factory() as db:
            dispatchable_task_exists = await _has_dispatchable_task_state(db)
            ready_delivery_feature_exists = await _has_ready_delivery_feature_state(db)
    explicit_sprint_planning_intent = _message_requests_sprint_planning(user_message)
    review_approval_continuation_requested = False
    if autonomous_continuation_requested and agent_name == "chat" and not active_specialist_present:
        session_factory = get_session_factory()
        async with session_factory() as db:
            review_approval_continuation_requested = (
                await _first_pending_review_approval(db)
            ) is not None
    return resolve_chat_turn_intent(
        agent_name=agent_name,
        active_specialist_present=active_specialist_present,
        autonomous_continuation_requested=autonomous_continuation_requested,
        ambiguous_continuation_requested=ambiguous_continuation_requested,
        dispatchable_task_exists=dispatchable_task_exists,
        ready_delivery_feature_exists=ready_delivery_feature_exists,
        explicit_sprint_planning_intent=explicit_sprint_planning_intent,
        feature_delivery_message_requested=_message_requests_feature_delivery(user_message),
        feature_delivery_confirmed=_message_confirms_feature_delivery(user_message),
        session_has_saved_feature_for_delivery=_session_has_saved_feature_for_delivery(session),
        session_has_pending_feature_spec=_session_has_pending_feature_spec(session),
        session_has_pending_sprint_planning=_session_has_pending_sprint_planning(session),
        review_approval_continuation_requested=review_approval_continuation_requested,
    )


async def _handle_chat_tool_event(
    state: ChatTurnCallbackState,
    publish_specialist_status: Callable[..., Awaitable[None]],
    event_data: dict[str, Any] | None = None,
    **event_kwargs: Any,
) -> None:
    event_data = {**(event_data or {}), **event_kwargs}
    requested_event_type = str(event_data.get("event_type") or "")
    tool_response = event_data.get("tool_response", event_data.get("output_preview", ""))
    event_type, content = _normalize_tool_response(tool_response)
    if requested_event_type and event_type == "tool_result":
        event_type = requested_event_type
    tool_name = str(event_data.get("tool_name", "") or "")
    if not tool_name:
        return
    tool_input = event_data.get("tool_input", {}) or {}
    payload = {
        "tool_name": tool_name,
        "tool_input": tool_input,
        "content": content,
        "diagnostic": summarize_tool_event(
            event_type=event_type,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_response=tool_response,
        ),
    }
    tool_use_id = event_data.get("tool_use_id")
    tool_event = await _append_chat_event(
        state.session_id,
        event_type=event_type,
        payload=payload,
        status="completed",
        tool_use_id=str(tool_use_id) if tool_use_id else None,
    )
    await state.hub.publish(
        state.session_id,
        agent_chat_transcript.serialize_event(tool_event).model_dump(mode="json"),
    )
    if (
        event_type == "tool_result"
        and state.agent_name == "chat"
        and tool_name == "mcp__builder__task_dispatch"
        and state.model_backed_delivery_context_requested
    ):
        dispatch_payload = _extract_tool_text_payload(tool_response)
        if dispatch_payload.get("status") == "dispatched":
            status_event = await _append_chat_event(
                state.session_id,
                event_type="run_status",
                payload={
                    **_runtime_metadata_for_agent(state.agent_name, state.project_root),
                    "running": False,
                    "current_turn": 0,
                    "max_turns": state.agent_max_turns,
                    "tokens_used": 0,
                    "cost_usd": 0.0,
                    "stop_reason": "task_dispatched",
                    "dispatch": {
                        "task_id": dispatch_payload.get("task_id"),
                        "status": dispatch_payload.get("status"),
                        "current_status": dispatch_payload.get("current_status"),
                    },
                },
                status="completed",
                tool_use_id=str(tool_use_id) if tool_use_id else None,
            )
            await state.hub.publish(
                state.session_id,
                agent_chat_transcript.serialize_event(status_event).model_dump(mode="json"),
            )
    if tool_name == "TodoWrite":
        todos = tool_input.get("todos", []) or []
        todo_event = await _append_chat_event(
            state.session_id,
            event_type="todo_snapshot",
            payload={
                "todos": todos,
                "pending_count": sum(1 for todo in todos if todo.get("status") == "pending"),
                "in_progress_count": sum(
                    1 for todo in todos if todo.get("status") == "in_progress"
                ),
                "completed_count": sum(
                    1 for todo in todos if todo.get("status") == "completed"
                ),
            },
            status="completed",
            tool_use_id=str(tool_use_id) if tool_use_id else None,
        )
        await state.hub.publish(
            state.session_id,
            agent_chat_transcript.serialize_event(todo_event).model_dump(mode="json"),
        )
    if state.active_specialist is not None:
        next_phase = ""
        if (
            tool_name.endswith("__kb_search")
            or tool_name.endswith("__task_show")
            or tool_name.endswith("__kb_contract")
        ):
            next_phase = "discovering"
        elif (
            tool_name.endswith("__kb_lint")
            or tool_name.endswith("__kb_add")
            or tool_name.endswith("__kb_update")
        ):
            next_phase = "publishing"
        elif tool_name.endswith("__kb_show") or tool_name.endswith("__kb_validate"):
            next_phase = "verifying"
        if next_phase and next_phase != state.specialist_phase:
            phase_label = next_phase.capitalize()
            await publish_specialist_status(
                next_phase,
                f"{state.active_specialist.policy.name} {phase_label.lower()} repo-local KB docs.",
                status="running",
            )
            state.specialist_phase = next_phase


async def _authorize_chat_tool(
    state: ChatTurnCallbackState,
    tool_name: str,
    input_data: dict[str, Any],
) -> Any:
    if tool_name in _USER_QUESTION_TOOL_NAMES:
        answers: dict[str, str] = {}
        for question in input_data.get("questions", []):
            display_question = agent_chat_transcript.operator_safe_question_payload(question)
            options = display_question.get("options", []) or []
            question_event = await _append_chat_event(
                state.session_id,
                event_type="ask_user_question",
                payload={
                    "header": display_question.get("header", ""),
                    "question": display_question.get("question", ""),
                    "options": options,
                    "multi_select": bool(display_question.get("multiSelect")),
                    "recommended_index": 0,
                    "answered": False,
                    "answer_value": "",
                },
                status="pending",
            )
            future = await state.hub.create_pending_answer(state.session_id, question_event.id)
            await state.hub.publish(
                state.session_id,
                agent_chat_transcript.serialize_event(question_event).model_dump(mode="json"),
            )
            response = await future
            answer_value = str(response.get("answer_value", "")).strip()
            answers[str(question.get("question", ""))] = answer_value

        return _permission_allow(
            {
                "questions": input_data.get("questions", []),
                "answers": answers,
            }
        )

    if state.feature_spec_requested:
        deny_tool, deny_reason = _feature_spec_tool_denial(tool_name)
        if deny_tool:
            denial_content = {
                "status": "error",
                "error": {
                    "code": "permission_denied",
                    "message": deny_reason,
                    "hint": "Use AskUserQuestion for the next bounded requirement decision or emit FEATURE_SPEC_JSON once the scope is ready.",
                    "detail": {
                        "tool_name": tool_name,
                        "lane": "feature_spec",
                    },
                },
                "schema_version": "1",
            }
            payload = {
                "tool_name": tool_name,
                "tool_input": input_data,
                "content": json.dumps(denial_content, ensure_ascii=True, sort_keys=True),
                "diagnostic": summarize_tool_event(
                    event_type="tool_error",
                    tool_name=tool_name,
                    tool_input=input_data,
                    tool_response=denial_content,
                ),
            }
            tool_event = await _append_chat_event(
                state.session_id,
                event_type="tool_error",
                payload=payload,
                status="completed",
            )
            await state.hub.publish(
                state.session_id,
                agent_chat_transcript.serialize_event(tool_event).model_dump(mode="json"),
            )
            return _permission_deny(deny_reason)

    if (
        state.active_specialist is not None
        and state.active_specialist.name == "documentation-agent"
        and tool_name == "mcp__builder__kb_validate"
    ):
        allowed, updated_input, deny_reason, next_action = _kb_validate_policy(
            state.project_root,
            input_data,
        )
        if allowed:
            return _permission_allow(updated_input)

        denial_content = {
            "status": "error",
            "error": {
                "code": "permission_denied",
                "message": deny_reason,
                "hint": next_action,
                "detail": {
                    "kb_dir": updated_input.get("kb_dir", "system-docs"),
                    "safe_lane": ".agent-builder/knowledge/<kb_dir>",
                },
            },
            "schema_version": "1",
        }
        payload = {
            "tool_name": tool_name,
            "tool_input": updated_input,
            "content": json.dumps(denial_content, ensure_ascii=True, sort_keys=True),
            "diagnostic": summarize_tool_event(
                event_type="tool_error",
                tool_name=tool_name,
                tool_input=updated_input,
                tool_response=denial_content,
            ),
        }
        tool_event = await _append_chat_event(
            state.session_id,
            event_type="tool_error",
            payload=payload,
            status="completed",
        )
        await state.hub.publish(
            state.session_id,
            agent_chat_transcript.serialize_event(tool_event).model_dump(mode="json"),
        )
        return _permission_deny(f"{deny_reason} {next_action}")

    if (
        state.active_specialist is not None
        and tool_name in state.active_specialist.policy.auto_approve_tools
    ):
        return _permission_allow(input_data)

    if state.agent_name == "chat" and is_read_only_tool(tool_name):
        return _permission_allow(input_data)

    if (
        state.agent_name == "chat"
        and state.active_specialist is None
        and state.model_backed_delivery_context_requested
        and tool_name
        in {
            "mcp__builder__task_dispatch",
            "mcp__builder__task_recover",
            "mcp__builder__backlog_item_update",
        }
    ):
        return _permission_allow(input_data)

    summary, description = _tool_summary(tool_name, input_data)
    approval_event = await _append_chat_event(
        state.session_id,
        event_type="tool_approval_request",
        payload={
            "tool_name": tool_name,
            "tool_input": input_data,
            "summary": summary,
            "description": description,
            "answered": False,
            "decision": "",
            "reason": "",
        },
        status="pending",
    )
    future = await state.hub.create_pending_answer(state.session_id, approval_event.id)
    await state.hub.publish(
        state.session_id,
        agent_chat_transcript.serialize_event(approval_event).model_dump(mode="json"),
    )
    response = await future
    decision = str(response.get("decision", "deny")).strip().lower() or "deny"
    reason = str(response.get("reason", "")).strip()
    if decision == "allow":
        return _permission_allow(response.get("updated_input") or input_data)
    return _permission_deny(reason or f"User denied {tool_name}.")


async def _run_chat_turn(app: Any, session_id: str, user_message: str) -> None:
    project_root = Path(app.state.project_root)
    hub: ChatSessionHub = app.state.chat_hub
    runner = AgentRunner(get_settings())
    runtime = create_runtime(**resolve_project_runtime_config(project_root))
    if hasattr(runtime, "_runner"):
        runtime._runner = runner
    session_factory = get_session_factory()
    active_specialist: ActiveSpecialistRoute | None = None
    async with session_factory() as db:
        session = await agent_chat_sessions.load_session(
            db, session_id, project_root=project_root, reject_scope_mismatch=True
        )
        if session is None:
            raise RuntimeError(f"Chat session '{session_id}' not found")
        agent_name = "chat"
        forward_engineering_context = await _needs_init_project_bootstrap(project_root, db)
        agent_def = get_agent_definition(agent_name)
        runtime_policy = resolve_agent_runtime_policy(agent_def, get_settings())
        resume_session = agent_chat_sessions.compatible_resume_session(session, runtime)
        active_specialist = await _select_specialist_route(
            db,
            project_root,
            session_id,
            user_message,
        )
    documentation_context = (
        active_specialist.context
        if active_specialist and active_specialist.name == "documentation-agent"
        else None
    )
    recent_context = _recent_chat_context_for_prompt(session, user_message)
    observability_context = _observability_context_for_prompt(project_root, user_message)
    if observability_context:
        recent_context = (
            f"{recent_context}\n{observability_context}"
            if recent_context.strip()
            else observability_context
        )
    specialist_active = active_specialist is not None
    specialist_phase = ""
    specialist_summary = ""
    model_backed_delivery_context_requested = False

    run_status_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload=_initial_status(agent_name, project_root),
        status="running",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(run_status_event).model_dump(mode="json"))

    async def publish_specialist_status(
        phase: str, content: str, *, status: str = "running"
    ) -> None:
        if active_specialist is None:
            return
        payload = {
            "specialist": active_specialist.name,
            "route_reason": active_specialist.route_reason,
            "phase": phase,
            "content": content,
        }
        specialist_event = await _append_chat_event(
            session_id,
            event_type="specialist_status",
            payload={
                **payload,
                "diagnostic": summarize_chat_event("specialist_status", payload),
            },
            status=status,
        )
        await hub.publish(session_id, agent_chat_transcript.serialize_event(specialist_event).model_dump(mode="json"))

    if specialist_active:
        specialist_phase = "discovering"
        specialist_summary = active_specialist.policy.active_summary
        await publish_specialist_status(
            specialist_phase,
            specialist_summary,
            status="running",
        )

    stream_user_visible = _stream_deltas_are_user_visible(runtime.name)
    callback_state = ChatTurnCallbackState(
        session_id=session_id,
        hub=hub,
        project_root=project_root,
        agent_name=agent_name,
        agent_max_turns=agent_def.max_turns,
        active_specialist=active_specialist,
        user_message=user_message,
        specialist_phase=specialist_phase,
    )
    turn_publisher = ChatTurnPublisher(
        session_id=session_id,
        hub=hub,
        runtime_metadata=_runtime_metadata_for_agent(agent_name, project_root),
        max_turns=agent_def.max_turns,
        append_chat_event=_append_chat_event,
        serialize_event=agent_chat_transcript.serialize_event,
    )

    async def on_stream(text: str) -> None:
        if stream_user_visible:
            await turn_publisher.publish_stream_delta(text)

    async def on_tool_event(event_data: dict[str, Any] | None = None, **event_kwargs: Any) -> None:
        await _handle_chat_tool_event(
            callback_state,
            publish_specialist_status,
            event_data,
            **event_kwargs,
        )

    async def can_use_tool(tool_name: str, input_data: dict[str, Any], context: Any) -> Any:
        return await _authorize_chat_tool(callback_state, tool_name, input_data)

    try:
        intent = await _resolve_chat_turn_intent(
            session=session,
            user_message=user_message,
            agent_name=agent_name,
            active_specialist=active_specialist,
        )
        model_backed_delivery_context_requested = intent.model_backed_delivery_context_requested
        feature_spec_requested = intent.feature_spec_requested
        callback_state.model_backed_delivery_context_requested = (
            model_backed_delivery_context_requested
        )
        callback_state.feature_spec_requested = feature_spec_requested
        if feature_spec_requested and not recent_context:
            recent_context = _recent_chat_context_for_prompt(session, user_message, force=True)
        if await publish_direct_chat_turn_if_handled(
            intent=intent,
            session_id=session_id,
            user_message=user_message,
            project_root=project_root,
            turn_publisher=turn_publisher,
            session_factory=get_session_factory(),
            approve_review_gate_for_continuation=_approve_review_gate_for_continuation,
            schedule_task_dispatch=_schedule_task_dispatch,
            latest_saved_feature_for_delivery=_latest_saved_feature_for_delivery,
            handle_sprint_planning_turn=_handle_sprint_planning_turn,
        ):
            return
        prompt_plan = build_chat_turn_prompt_plan(
            agent_name=agent_name,
            feature_spec_requested=feature_spec_requested,
            model_backed_delivery_context_requested=model_backed_delivery_context_requested,
            project_root=project_root,
            user_message=user_message,
            runtime_name=runtime.name,
            documentation_context=documentation_context,
            recent_context=recent_context,
            forward_engineering_context=forward_engineering_context,
            resume_session=resume_session,
            init_project_chat_prompt=_init_project_chat_prompt,
            feature_spec_chat_prompt=_feature_spec_chat_prompt,
            general_chat_prompt=_general_chat_prompt,
        )
        prompt = prompt_plan.prompt
        run_session = prompt_plan.run_session
        await publish_chat_context_budget(
            session_id=session_id,
            hub=hub,
            append_chat_event=_append_chat_event,
            serialize_event=agent_chat_transcript.serialize_event,
            agent_name=agent_name,
            prompt=prompt,
            user_message=user_message,
            recent_context=recent_context,
            documentation_context=documentation_context,
            observability_context=observability_context,
            runtime_metadata=_runtime_metadata_for_agent(agent_name, project_root),
            resume_session=run_session,
            specialist_active=specialist_active,
        )
        result, run_totals = await run_chat_runtime_loop(
            runtime=runtime,
            prompt=prompt,
            agent_name=agent_name,
            project_root=project_root,
            run_session=run_session,
            runtime_policy=runtime_policy,
            feature_spec_requested=feature_spec_requested,
            active_specialist=active_specialist,
            on_stream=on_stream,
            on_stream_usage=turn_publisher.publish_stream_usage,
            can_use_tool=can_use_tool,
            on_tool_event=on_tool_event,
            max_requirements_continuations=_INIT_PROJECT_MAX_REQUIREMENTS_CONTINUATIONS,
            requires_autonomous_continuation=_init_project_requires_autonomous_continuation,
            continuation_prompt=_init_project_continuation_prompt,
        )
        if result.error:
            await _publish_agent_run_error_result(
                session_id=session_id,
                hub=hub,
                agent_name=agent_name,
                project_root=project_root,
                active_specialist=active_specialist,
                publish_specialist_status=publish_specialist_status,
                result=result,
                totals=run_totals,
                max_turns=agent_def.max_turns,
            )
            return

        if result.stop_reason == "provider_limit":
            await _publish_provider_limit_result(
                session_id=session_id,
                hub=hub,
                agent_name=agent_name,
                project_root=project_root,
                active_specialist=active_specialist,
                publish_specialist_status=publish_specialist_status,
                result=result,
                totals=run_totals,
                max_turns=agent_def.max_turns,
            )
            return

        await _publish_successful_chat_result(
            session_id=session_id,
            user_message=user_message,
            hub=hub,
            agent_name=agent_name,
            project_root=project_root,
            active_specialist=active_specialist,
            publish_specialist_status=publish_specialist_status,
            result=result,
            run_totals=run_totals,
            max_turns=agent_def.max_turns,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if specialist_active:
            await publish_specialist_status(
                "blocked",
                f"{active_specialist.policy.name} stopped: {exc}",
                status="completed",
            )
        await turn_publisher.publish_terminal_error(exc)


async def _continue_after_persisted_response(
    app: Any,
    session_id: str,
    message: str,
) -> None:
    hub: ChatSessionHub = app.state.chat_hub
    task = asyncio.create_task(_run_chat_turn(app, session_id, message))
    attached = await hub.attach_run(session_id, task)
    if attached:
        return
    task.cancel()


@router.get("/agent/runtime")
async def get_runtime_settings(request: Request) -> dict[str, Any]:
    """Return the active runtime settings for the dashboard settings surface."""
    project_root = _project_root(request)
    return runtime_settings_payload(project_root)


@router.post("/agent/runtime")
async def update_runtime_settings(
    request: Request,
    payload: RuntimeSettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Persist runtime settings from the dashboard settings surface."""
    project_root = _project_root(request)
    previous = runtime_settings_payload(project_root, include_capabilities=False)
    result = persist_runtime_settings(
        project_root,
        sdk=payload.sdk,
        provider=payload.provider,
        model=payload.model,
        api_base_url=payload.api_base_url,
        api_key_env=payload.api_key_env,
        codex_profile=payload.codex_profile,
        sandbox_mode=payload.sandbox_mode,
        approval_policy=payload.approval_policy,
        tracing=payload.tracing,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    repair = reconcile_runtime_project_state(project_root)
    result["runtime_repair"] = repair
    sessions_result = await db.execute(
        select(ChatSession)
        .where(ChatSession.repo_identity == agent_chat_sessions.repo_identity(project_root))
        .where(ChatSession.workspace_cwd == agent_chat_sessions.workspace_cwd(project_root))
        .order_by(ChatSession.updated_at.desc())
        .limit(1)
    )
    session = sessions_result.scalar_one_or_none()
    if session is None:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, project_root)
        db.add(session)
        await db.flush()
    session.updated_at = utcnow()
    db.add(
        ChatEvent(
            session_id=session.id,
            event_type="runtime_settings_updated",
            payload_json={
                "previous_runtime_sdk": previous.get("sdk"),
                "selected_runtime_sdk": result.get("sdk"),
                "previous_provider": previous.get("provider"),
                "provider": result.get("provider"),
                "previous_model": previous.get("model"),
                "model": result.get("model"),
                "scope": "future_runs_only",
                "state_policy": "preserve_existing_tasks_runs_metrics_observability_memory_knowledge_backlog",
                "runtime_repair": repair,
            },
            status="completed",
        )
    )
    await publish_onboarding_snapshot(project_root)
    return result


@router.get("/agent/chat/sessions", response_model=ChatSessionListResponse)
async def list_chat_sessions(request: Request, db: AsyncSession = Depends(get_db)):
    """List available chat sessions so older threads remain accessible after reset."""
    project_root = _project_root(request)
    sessions = await agent_chat_sessions.list_scoped_sessions(db, project_root)
    latest_resume_session = agent_chat_sessions.latest_resume_candidate(sessions)

    return ChatSessionListResponse(
        repo_identity=agent_chat_sessions.repo_identity(project_root),
        workspace_cwd=agent_chat_sessions.workspace_cwd(project_root),
        latest_resume_session_id=latest_resume_session.id if latest_resume_session else None,
        sessions=[
            ChatSessionItem(
                id=session.id,
                sdk_session_id=session.sdk_session_id,
                created_at=session.created_at.isoformat(),
                updated_at=session.updated_at.isoformat(),
                message_count=len(agent_chat_transcript.history_items(session)),
                preview=agent_chat_sessions.session_preview(session),
                workspace_cwd=session.workspace_cwd,
                is_resume_candidate=latest_resume_session is not None
                and session.id == latest_resume_session.id,
            )
            for session in sessions
        ],
    )


@router.get("/agent/chat/meta", response_model=ChatMetaResponse)
async def get_chat_meta(request: Request):
    """Return stable chat-lane metadata used before a session exists."""
    project_root = _project_root(request)
    runtime_metadata = _chat_runtime_metadata(project_root)
    return ChatMetaResponse(
        model=runtime_metadata["model"],
        effort=runtime_metadata["effort"],
        runtime_sdk=runtime_metadata["runtime_sdk"],
        provider=runtime_metadata["provider"],
        repo_identity=agent_chat_sessions.repo_identity(project_root),
        workspace_cwd=agent_chat_sessions.workspace_cwd(project_root),
    )


@router.get("/agent/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    request: Request,
    session_id: str | None = None,
    fresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Get chat history for a session."""

    project_root = _project_root(request)
    session = await agent_chat_sessions.load_session(
        db,
        session_id,
        project_root=project_root,
        reject_scope_mismatch=bool(session_id),
    )
    scoped_sessions = await agent_chat_sessions.list_scoped_sessions(db, project_root)

    if not fresh and session is None and session_id is None:
        session = agent_chat_sessions.latest_resume_candidate(scoped_sessions)

    if not fresh and session is None and session_id is None and scoped_sessions:
        session = scoped_sessions[0]

    if session is None:
        runtime_metadata = _chat_runtime_metadata(project_root)
        return ChatHistoryResponse(
            session_id="",
            sdk_session_id=None,
            model=runtime_metadata["model"],
            effort=runtime_metadata["effort"],
            runtime_sdk=runtime_metadata["runtime_sdk"],
            provider=runtime_metadata["provider"],
            repo_identity=agent_chat_sessions.repo_identity(project_root),
            workspace_cwd=agent_chat_sessions.workspace_cwd(project_root),
            items=[],
            messages=[],
            status=None,
        )

    if await _append_delivery_closeout_if_ready(session.id, project_root, db):
        await db.commit()
        await db.refresh(session, attribute_names=["events", "messages"])
        reloaded_session = await agent_chat_sessions.load_session(
            db,
            session.id,
            project_root=project_root,
            reject_scope_mismatch=True,
        )
        if reloaded_session is not None:
            session = reloaded_session
    if await reconcile_session_control_owners(
        session,
        db,
        feature_resolver=_feature_for_delivery_permission_question,
    ):
        await db.commit()
        await db.refresh(session, attribute_names=["events", "messages"])

    items = agent_chat_transcript.history_items(session)
    runtime_metadata = _chat_runtime_metadata(project_root)
    active_run = await _chat_hub(request).has_active_run(session.id)
    status = agent_chat_transcript.latest_status(session, active_run=active_run)
    thread_runtime_metadata = agent_chat_transcript.thread_runtime_metadata(runtime_metadata, status)
    return ChatHistoryResponse(
        session_id=session.id,
        sdk_session_id=session.sdk_session_id,
        model=thread_runtime_metadata["model"],
        effort=thread_runtime_metadata["effort"],
        runtime_sdk=thread_runtime_metadata["runtime_sdk"],
        provider=thread_runtime_metadata["provider"],
        repo_identity=agent_chat_sessions.repo_identity(project_root),
        workspace_cwd=agent_chat_sessions.workspace_cwd(project_root),
        items=items,
        messages=agent_chat_transcript.legacy_messages(items),
        status=status,
    )


@router.get("/agent/chat/stream")
async def chat_stream(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Stream live chat session timeline events as SSE."""

    project_root = _project_root(request)
    session = await agent_chat_sessions.load_session(
        db, session_id, project_root=project_root, reject_scope_mismatch=True
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    hub = _chat_hub(request)
    queue = await hub.register_session(session_id)
    runtime_metadata = _chat_runtime_metadata(project_root)
    active_run = await hub.has_active_run(session_id)
    status = agent_chat_transcript.latest_status(session, active_run=active_run)
    thread_runtime_metadata = agent_chat_transcript.thread_runtime_metadata(runtime_metadata, status)
    if await reconcile_session_control_owners(
        session,
        db,
        feature_resolver=_feature_for_delivery_permission_question,
    ):
        await db.commit()
        await db.refresh(session, attribute_names=["events", "messages"])
    items = agent_chat_transcript.history_items(session)
    snapshot = ChatHistoryResponse(
        session_id=session.id,
        sdk_session_id=session.sdk_session_id,
        model=thread_runtime_metadata["model"],
        effort=thread_runtime_metadata["effort"],
        runtime_sdk=thread_runtime_metadata["runtime_sdk"],
        provider=thread_runtime_metadata["provider"],
        repo_identity=agent_chat_sessions.repo_identity(project_root),
        workspace_cwd=agent_chat_sessions.workspace_cwd(project_root),
        items=items,
        messages=agent_chat_transcript.legacy_messages(items),
        status=status,
    ).model_dump(mode="json")

    async def event_generator():
        try:
            yield {"event": "snapshot", "data": json.dumps(snapshot)}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield {"event": event["event"], "data": json.dumps(event["data"])}
                except TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            await hub.unregister_session(session_id, queue)

    return EventSourceResponse(event_generator())


@router.post("/agent/chat", response_model=ChatResponse)
async def agent_chat(
    request: ChatRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """Persist a user turn, then launch the agent run asynchronously."""

    project_root = _project_root(req)
    agent_name = "chat"
    runtime_metadata = _runtime_metadata_for_agent(agent_name, project_root)

    session = await agent_chat_sessions.load_session(
        db,
        request.session_id,
        project_root=project_root,
        reject_scope_mismatch=bool(request.session_id),
    )
    if session is None:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, project_root)
        db.add(session)
        await db.flush()
        await db.commit()
        session = await agent_chat_sessions.load_session(db, session.id, project_root=project_root)

    if session is None:
        raise HTTPException(status_code=500, detail="Failed to initialize chat session")

    hub = _chat_hub(req)
    if not await hub.reserve_run(session.id):
        raise HTTPException(
            status_code=409, detail="This chat session is waiting on the current run."
        )

    try:
        user_event = await _append_chat_event(
            session.id,
            event_type="user_message",
            payload={"content": request.message},
            status="completed",
            mirror_message=("user", request.message, 0, 0.0),
        )
        await hub.publish(session.id, agent_chat_transcript.serialize_event(user_event).model_dump(mode="json"))
    except Exception:
        await hub.release_run(session.id)
        raise

    task = asyncio.create_task(_run_chat_turn(req.app, session.id, request.message))
    attached = await hub.attach_reserved_run(session.id, task)
    if not attached:
        task.cancel()
        await hub.release_run(session.id)
        raise HTTPException(status_code=409, detail="This chat session is already running.")

    return ChatResponse(
        response="Run started.",
        session_id=session.id,
        model=runtime_metadata["model"],
        effort=runtime_metadata["effort"],
        runtime_sdk=runtime_metadata["runtime_sdk"],
        provider=runtime_metadata["provider"],
        status=_initial_status(agent_name, project_root),
    )


@router.post("/agent/chat/respond", response_model=ChatRespondResponse)
async def respond_to_chat_event(
    request: ChatRespondRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """Submit an answer for a pending question or tool approval card."""

    hub = _chat_hub(req)
    event = await db.get(ChatEvent, request.event_id)
    if event is None or event.session_id != request.session_id:
        raise HTTPException(status_code=404, detail="Chat interaction not found")
    event_payload = event.payload_json or {}
    persisted_pending = (
        event.status == "pending"
        and event.event_type in {"ask_user_question", "tool_approval_request"}
        and not bool(event_payload.get("answered"))
    )
    has_live_waiter = await hub.has_pending_answer(request.event_id)
    if not has_live_waiter and not persisted_pending:
        raise HTTPException(status_code=409, detail="This interaction is no longer pending.")

    if event.event_type == "ask_user_question":
        answer_value = request.custom_text.strip()
        if not answer_value:
            answer_value = ", ".join(
                option.strip() for option in request.selected_options if option.strip()
            )
        if not answer_value:
            raise HTTPException(
                status_code=400, detail="Select an option or provide a custom answer."
            )

        updated_event = await _update_request_event(
            db,
            event,
            payload_patch={"answered": True, "answer_value": answer_value},
            status="answered",
            answer_event_type="ask_user_question_answer",
            answer_payload={
                "question": event.payload_json.get("question", ""),
                "answer_value": answer_value,
            },
        )
        await hub.publish(
            request.session_id, agent_chat_transcript.serialize_event(updated_event).model_dump(mode="json")
        )
        if has_live_waiter:
            resolved = await hub.resolve_pending_answer(
                request.event_id,
                {"answer_value": answer_value},
            )
            if not resolved:
                raise HTTPException(
                    status_code=409, detail="This interaction is no longer pending."
                )
        else:
            source = str(event.payload_json.get("source") or "")
            if source == "assistant_delivery_permission_prompt":
                task = asyncio.create_task(
                    _continue_after_delivery_permission_question(
                        req.app,
                        request.session_id,
                        event,
                        answer_value=answer_value,
                    )
                )
                attached = await hub.attach_run(request.session_id, task)
                if not attached:
                    task.cancel()
                    raise HTTPException(
                        status_code=409, detail="This chat session is already running."
                    )
            else:
                question = str(event.payload_json.get("question") or "the pending question")
                await _continue_after_persisted_response(
                    req.app,
                    request.session_id,
                    f'Operator answered pending question "{question}": {answer_value}',
                )
        return ChatRespondResponse(
            ok=True, session_id=request.session_id, event_id=request.event_id
        )

    if event.event_type != "tool_approval_request":
        raise HTTPException(status_code=400, detail="Unsupported chat interaction type")

    decision = (request.decision or "").strip().lower()
    if decision not in {"allow", "deny"}:
        raise HTTPException(
            status_code=400, detail="Tool approvals require an allow or deny decision."
        )

    updated_event = await _update_request_event(
        db,
        event,
        payload_patch={"answered": True, "decision": decision, "reason": request.reason.strip()},
        status="answered",
        answer_event_type="tool_approval_answer",
        answer_payload={
            "tool_name": event.payload_json.get("tool_name", ""),
            "decision": decision,
            "reason": request.reason.strip(),
        },
    )
    await hub.publish(request.session_id, agent_chat_transcript.serialize_event(updated_event).model_dump(mode="json"))
    response_payload = {
        "decision": decision,
        "reason": request.reason.strip(),
        "updated_input": request.updated_input,
    }
    if has_live_waiter:
        resolved = await hub.resolve_pending_answer(request.event_id, response_payload)
        if not resolved:
            raise HTTPException(status_code=409, detail="This interaction is no longer pending.")
    else:
        tool_name = str(event.payload_json.get("tool_name") or "requested tool")
        if tool_name == "Delivery scope approval":
            await _complete_persisted_delivery_scope_approval(
                req.app,
                request.session_id,
                event,
                decision=decision,
            )
        else:
            await _continue_after_persisted_response(
                req.app,
                request.session_id,
                f'Operator answered pending approval for "{tool_name}": {decision}. Reason: {request.reason.strip()}',
            )
    return ChatRespondResponse(ok=True, session_id=request.session_id, event_id=request.event_id)
