"""Direct Agent chat-turn actions that complete without provider runtime."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from autonomous_agent_builder.db.models import Feature, Task
from autonomous_agent_builder.embedded.server.chat_turn_intent import ChatTurnIntent
from autonomous_agent_builder.embedded.server.chat_turn_publication import ChatTurnPublisher

SessionFactory = Callable[[], Any]
ApproveReviewGate = Callable[[Any], Awaitable[Task | None]]
ScheduleTaskDispatch = Callable[[str], Awaitable[None]]
LatestSavedFeature = Callable[[Any, str], Awaitable[Feature | None]]
HandleSprintPlanning = Callable[..., Awaitable[str]]


async def publish_direct_chat_turn_if_handled(
    *,
    intent: ChatTurnIntent,
    session_id: str,
    user_message: str,
    project_root: Path,
    turn_publisher: ChatTurnPublisher,
    session_factory: SessionFactory,
    approve_review_gate_for_continuation: ApproveReviewGate,
    schedule_task_dispatch: ScheduleTaskDispatch,
    latest_saved_feature_for_delivery: LatestSavedFeature,
    handle_sprint_planning_turn: HandleSprintPlanning,
) -> bool:
    """Publish direct responses for intent branches that do not need the runtime."""

    if intent.review_approval_continuation_requested:
        async with session_factory() as db:
            task = await approve_review_gate_for_continuation(db)
            task_id = task.id if task is not None else ""
            task_title = task.title if task is not None else ""
            await db.commit()
        if task_id:
            await schedule_task_dispatch(task_id)
            await turn_publisher.publish_terminal_assistant_response(
                f"Approved review for `{task_title}` and started build verification.",
                stop_reason="review_approved_and_dispatched",
            )
            return True

    if intent.sprint_planning_requested:
        ambiguous_sprint_continuation_requested = (
            intent.autonomous_continuation_requested
            and not intent.sprint_planning_intent
            and intent.ambiguous_continuation_requested
        )
        visible_response = await handle_sprint_planning_turn(
            session_id,
            user_message,
            project_root,
            turn_publisher.hub,
            auto_select_first=(
                intent.autonomous_continuation_requested
                and not ambiguous_sprint_continuation_requested
            ),
        )
        await turn_publisher.publish_terminal_assistant_response(visible_response)
        return True

    if intent.feature_delivery_followup_requested:
        async with session_factory() as db:
            feature = await latest_saved_feature_for_delivery(db, user_message)
        if feature is not None:
            visible_response = await handle_sprint_planning_turn(
                session_id,
                feature.title,
                project_root,
                turn_publisher.hub,
                selected_feature_ids=[feature.id],
            )
            await turn_publisher.publish_terminal_assistant_response(visible_response)
            return True

    return False
