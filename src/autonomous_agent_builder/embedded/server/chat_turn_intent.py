"""Agent chat-turn intent and callback state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ChatTurnIntent:
    autonomous_continuation_requested: bool
    ambiguous_continuation_requested: bool
    dispatchable_task_exists: bool
    ready_delivery_feature_exists: bool
    explicit_sprint_planning_intent: bool
    model_backed_delivery_context_requested: bool
    feature_delivery_followup_requested: bool
    feature_spec_requested: bool
    sprint_planning_requested: bool
    review_approval_continuation_requested: bool
    sprint_planning_intent: bool


@dataclass(frozen=True)
class ChatRunTotals:
    tokens_input: int
    tokens_output: int
    tokens_cached: int
    cost_usd: float
    duration_ms: int
    turns: int

    @property
    def token_total(self) -> int:
        return self.tokens_input + self.tokens_output


@dataclass
class ChatTurnCallbackState:
    session_id: str
    hub: Any
    project_root: Path
    agent_name: str
    agent_max_turns: int
    active_specialist: Any | None
    user_message: str
    feature_spec_requested: bool = False
    model_backed_delivery_context_requested: bool = False
    specialist_phase: str = ""
    # Tools the agent is already granted (its definition's allowed_tools). Under
    # permission_mode="default" the can_use_tool callback may be consulted for
    # these; auto-allowing them preserves historical silent-execution behavior so
    # enabling AskUserQuestion does not introduce approval-card friction.
    preapproved_tools: frozenset[str] = frozenset()


def resolve_chat_turn_intent(
    *,
    agent_name: str,
    active_specialist_present: bool,
    autonomous_continuation_requested: bool,
    ambiguous_continuation_requested: bool,
    dispatchable_task_exists: bool,
    ready_delivery_feature_exists: bool,
    explicit_sprint_planning_intent: bool,
    feature_delivery_message_requested: bool,
    feature_delivery_confirmed: bool,
    session_has_saved_feature_for_delivery: bool,
    session_has_pending_feature_spec: bool,
    session_has_pending_sprint_planning: bool,
    review_approval_continuation_requested: bool,
) -> ChatTurnIntent:
    chat_without_specialist = agent_name == "chat" and not active_specialist_present
    # Always route to the model — never skip the runtime based on text-match alone.
    model_backed_delivery_context_requested = chat_without_specialist
    feature_delivery_followup_requested = (
        chat_without_specialist
        and not dispatchable_task_exists
        and session_has_saved_feature_for_delivery
        and (feature_delivery_message_requested or feature_delivery_confirmed)
    )
    feature_spec_intent = (
        session_has_pending_feature_spec
        and not explicit_sprint_planning_intent
        and not (autonomous_continuation_requested and ready_delivery_feature_exists)
        and not feature_delivery_followup_requested
    )
    sprint_planning_intent = explicit_sprint_planning_intent or (
        session_has_pending_sprint_planning and not feature_spec_intent
    )
    feature_spec_requested = (
        chat_without_specialist and not sprint_planning_intent and feature_spec_intent
    )
    sprint_planning_requested = (
        chat_without_specialist
        and not feature_spec_requested
        and not feature_delivery_followup_requested
        and not dispatchable_task_exists
        and (not autonomous_continuation_requested or ready_delivery_feature_exists)
        and (sprint_planning_intent or autonomous_continuation_requested)
    )
    feature_delivery_followup_requested = (
        feature_delivery_followup_requested and not sprint_planning_requested
    )
    return ChatTurnIntent(
        autonomous_continuation_requested=autonomous_continuation_requested,
        ambiguous_continuation_requested=ambiguous_continuation_requested,
        dispatchable_task_exists=dispatchable_task_exists,
        ready_delivery_feature_exists=ready_delivery_feature_exists,
        explicit_sprint_planning_intent=explicit_sprint_planning_intent,
        model_backed_delivery_context_requested=model_backed_delivery_context_requested,
        feature_delivery_followup_requested=feature_delivery_followup_requested,
        feature_spec_requested=feature_spec_requested,
        sprint_planning_requested=sprint_planning_requested,
        review_approval_continuation_requested=review_approval_continuation_requested,
        sprint_planning_intent=sprint_planning_intent,
    )
