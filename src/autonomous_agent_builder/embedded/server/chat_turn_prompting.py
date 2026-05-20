"""Prompt and context-budget preparation for embedded Agent chat turns."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autonomous_agent_builder.db.models import ChatEvent
from autonomous_agent_builder.services.context_budget import build_agent_context_budget

AppendChatEvent = Callable[..., Awaitable[ChatEvent]]
SerializeChatEvent = Callable[[ChatEvent], Any]
PromptBuilder = Callable[..., str]


@dataclass(frozen=True)
class ChatTurnPromptPlan:
    prompt: str
    run_session: str | None


def build_chat_turn_prompt_plan(
    *,
    agent_name: str,
    feature_spec_requested: bool,
    model_backed_delivery_context_requested: bool,
    project_root: Path,
    user_message: str,
    runtime_name: str,
    documentation_context: str | None,
    recent_context: str,
    forward_engineering_context: str | None,
    resume_session: str | None,
    init_project_chat_prompt: PromptBuilder,
    feature_spec_chat_prompt: PromptBuilder,
    general_chat_prompt: PromptBuilder,
) -> ChatTurnPromptPlan:
    if agent_name == "init-project-chat":
        prompt = init_project_chat_prompt(
            project_root,
            user_message,
            runtime_sdk=runtime_name,
        )
    elif feature_spec_requested:
        prompt = feature_spec_chat_prompt(
            project_root,
            user_message,
            runtime_sdk=runtime_name,
        )
    else:
        prompt = general_chat_prompt(
            project_root,
            user_message,
            documentation_context,
            runtime_sdk=runtime_name,
            recent_context=recent_context,
            model_backed_delivery_context=model_backed_delivery_context_requested,
            forward_engineering_context=forward_engineering_context,
        )
    return ChatTurnPromptPlan(
        prompt=prompt,
        run_session=None if model_backed_delivery_context_requested else resume_session,
    )


async def publish_chat_context_budget(
    *,
    session_id: str,
    hub: Any,
    append_chat_event: AppendChatEvent,
    serialize_event: SerializeChatEvent,
    agent_name: str,
    prompt: str,
    user_message: str,
    recent_context: str,
    documentation_context: str | None,
    observability_context: str,
    runtime_metadata: dict[str, Any],
    resume_session: str | None,
    specialist_active: bool,
) -> None:
    context_budget_event = await append_chat_event(
        session_id,
        event_type="context_budget",
        payload=build_agent_context_budget(
            agent_name=agent_name,
            prompt=prompt,
            user_message=user_message,
            recent_context=recent_context,
            documentation_context=documentation_context,
            observability_context=observability_context,
            runtime_metadata=runtime_metadata,
            resume_session=resume_session,
            specialist_active=specialist_active,
        ),
        status="completed",
    )
    await hub.publish(session_id, serialize_event(context_budget_event).model_dump(mode="json"))
