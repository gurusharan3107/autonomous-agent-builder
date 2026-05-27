"""Sprint planning and delivery approval helpers for Agent chat."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.backlog_items import feature_to_item_payload, mirror_item_to_artifact
from autonomous_agent_builder.db.models import (
    BacklogItemType,
    ChatEvent,
    ChatSession,
    Feature,
    FeatureStatus,
    Project,
)
from autonomous_agent_builder.db.session import get_session_factory
from autonomous_agent_builder.embedded.server import agent_chat_transcript
from autonomous_agent_builder.embedded.server.agent_chat_events import (
    append_chat_event as _append_chat_event,
)
from autonomous_agent_builder.embedded.server.agent_feature_delivery import schedule_task_dispatch
from autonomous_agent_builder.embedded.server.agent_message_intent import (
    SPRINT_PLANNING_SELECTION_PROMPT,
    message_selects_all_sprint_items,
    normalize_planning_token,
)
from autonomous_agent_builder.embedded.server.chat_state import ChatSessionHub
from autonomous_agent_builder.onboarding import select_delivery_project
from autonomous_agent_builder.services.sprint_execution import persist_sprint_execution_artifacts


def session_has_pending_sprint_planning(session: ChatSession) -> bool:
    assistant_items = [
        item
        for item in agent_chat_transcript.history_items(session)
        if item.type == "assistant_message"
    ]
    if not assistant_items:
        return False
    assistant_items.sort(key=lambda item: item.timestamp)
    contents = [str(item.payload.get("content", "")) for item in assistant_items]
    has_prompt = any(SPRINT_PLANNING_SELECTION_PROMPT in content for content in contents)
    if not has_prompt:
        return False
    resolved = any(
        "created sprint plan" in content
        or "created plan" in content
        or "Builder prepared the work" in content
        or "Sprint planning canceled" in content
        or "Delivery is on hold" in content
        or "Sprint planning scope was not approved" in content
        or "Delivery scope was not approved" in content
        or "received approval, and queued them" in content
        or "queue approval was denied" in content
        for content in contents
    )
    return not resolved


def _select_sprint_planning_features(
    user_message: str,
    backlog_items: list[Feature],
) -> list[Feature]:
    if not backlog_items:
        return []
    if message_selects_all_sprint_items(user_message):
        return backlog_items

    lower_message = user_message.lower()
    id_matches = {
        feature.id.lower() for feature in backlog_items if feature.id.lower() in lower_message
    }
    selected = [feature for feature in backlog_items if feature.id.lower() in id_matches]
    if selected:
        return selected

    normalized_message = normalize_planning_token(user_message)
    selected = []
    for feature in backlog_items:
        title_token = normalize_planning_token(feature.title)
        if title_token and title_token in normalized_message:
            selected.append(feature)
    return selected


def _feature_dependency_ids(feature: Feature) -> list[str]:
    dependencies = feature.dependencies if isinstance(feature.dependencies, list) else []
    return [str(item).strip() for item in dependencies if str(item).strip()]


def _feature_ready_for_next_sprint(
    feature: Feature, features_by_id: dict[str, Feature]
) -> bool:
    for dependency_id in _feature_dependency_ids(feature):
        dependency = features_by_id.get(dependency_id)
        if dependency is None or dependency.status != FeatureStatus.DONE:
            return False
    return True


def _next_sprint_candidates(features: list[Feature]) -> list[Feature]:
    features_by_id = {feature.id: feature for feature in features}
    product_backlog = [item for item in features if item.status == FeatureStatus.BACKLOG]
    ready = [
        feature
        for feature in product_backlog
        if _feature_ready_for_next_sprint(feature, features_by_id)
    ]
    return ready or product_backlog


def _format_sprint_planning_options(backlog_items: list[Feature]) -> str:
    return "\n".join(f"- `{f.id}` · P{f.priority} · {f.title}" for f in backlog_items)


async def _request_chat_approval(
    session_id: str,
    hub: ChatSessionHub,
    *,
    tool_name: str,
    tool_input: dict[str, Any],
    summary: str,
    description: str,
) -> dict[str, Any]:
    approval_event = await _append_chat_event(
        session_id,
        event_type="tool_approval_request",
        payload={
            "tool_name": tool_name,
            "tool_input": tool_input,
            "summary": summary,
            "description": description,
            "answered": False,
            "decision": "",
            "reason": "",
        },
        status="pending",
    )
    future = await hub.create_pending_answer(session_id, approval_event.id)
    await hub.publish(
        session_id,
        agent_chat_transcript.serialize_event(approval_event).model_dump(mode="json"),
    )
    return await future


async def _request_chat_question(
    session_id: str,
    hub: ChatSessionHub,
    *,
    header: str,
    question: str,
    options: list[dict[str, str]],
    multi_select: bool = False,
) -> str:
    question_event = await _append_chat_event(
        session_id,
        event_type="ask_user_question",
        payload={
            "header": header,
            "question": question,
            "options": options,
            "multi_select": multi_select,
            "recommended_index": 0,
            "answered": False,
            "answer_value": "",
        },
        status="pending",
    )
    future = await hub.create_pending_answer(session_id, question_event.id)
    await hub.publish(
        session_id,
        agent_chat_transcript.serialize_event(question_event).model_dump(mode="json"),
    )
    response = await future
    return str(response.get("answer_value", "")).strip()


async def append_persisted_delivery_permission_question_if_needed(
    session_id: str,
    *,
    assistant_event_id: str,
    response_text: str,
    hub: ChatSessionHub,
    force: bool = False,
) -> ChatEvent | None:
    if not force and not agent_chat_transcript.assistant_requests_delivery_permission(response_text):
        return None
    session_factory = get_session_factory()
    async with session_factory() as db:
        pending_result = await db.execute(
            select(ChatEvent)
            .where(ChatEvent.session_id == session_id)
            .where(ChatEvent.event_type == "ask_user_question")
            .where(ChatEvent.status == "pending")
        )
        existing_pending = pending_result.scalars().first()
        if existing_pending is not None:
            return existing_pending
    question_event = await _append_chat_event(
        session_id,
        event_type="ask_user_question",
        payload={
            "header": "Start Work?",
            "question": "Ready for Builder to start this improvement?",
            "options": [
                {
                    "label": "Start now",
                    "description": "Builder will prepare the work and begin the first safe change.",
                },
                {
                    "label": "Hold",
                    "description": "Keep the improvement captured without starting delivery.",
                },
            ],
            "multi_select": False,
            "recommended_index": 0,
            "answered": False,
            "answer_value": "",
            "source": "assistant_delivery_permission_prompt",
            "assistant_event_id": assistant_event_id,
        },
        status="pending",
    )
    await hub.publish(
        session_id,
        agent_chat_transcript.serialize_event(question_event).model_dump(mode="json"),
    )
    return question_event


async def handle_sprint_planning_turn(
    session_id: str,
    user_message: str,
    project_root: Path,
    hub: ChatSessionHub,
    *,
    selected_feature_ids: list[str] | None = None,
    auto_select_first: bool = False,
    skip_scope_approval: bool = False,
) -> str:
    session_factory = get_session_factory()
    selection_message = user_message
    selection_ids = selected_feature_ids
    project_id = ""
    selected_ids: list[str] = []
    while True:
        question: dict[str, Any] | None = None
        async with session_factory() as db:
            project = await select_delivery_project(
                db,
                selection_message,
                selected_feature_ids=selection_ids,
            )
            if project is None:
                return "Delivery is blocked because no Builder project exists yet."
            project_id = project.id
            feature_result = await db.execute(
                select(Feature)
                .where(Feature.project_id == project.id)
                .where(Feature.item_type == BacklogItemType.FEATURE)
                .order_by(Feature.priority.desc(), Feature.created_at.asc())
            )
            features = list(feature_result.scalars().all())
            product_backlog = [item for item in features if item.status == FeatureStatus.BACKLOG]
            next_sprint_candidates = _next_sprint_candidates(features)
            sprint_backlog = [
                item
                for item in features
                if item.status
                in {
                    FeatureStatus.SPRINT_BACKLOG,
                    FeatureStatus.SPRINT_CANDIDATE,
                    FeatureStatus.SPRINT_PLANNED,
                }
            ]

            if selection_ids is not None:
                selected = [item for item in next_sprint_candidates if item.id in selection_ids]
                if not selected:
                    already_selected = [item for item in features if item.id in selection_ids]
                    if already_selected:
                        statuses = ", ".join(
                            f"`{feature.id}` {feature.title} ({feature.status.value if hasattr(feature.status, 'value') else feature.status})"
                            for feature in already_selected
                        )
                        return f"Those improvements are not ready for a new delivery plan. Current state: {statuses}."
            else:
                selected = _select_sprint_planning_features(
                    selection_message,
                    next_sprint_candidates,
                )

            if selected:
                selected_ids = [feature.id for feature in selected]
                break
            if not product_backlog:
                if sprint_backlog:
                    titles = ", ".join(
                        f"`{feature.id}` {feature.title}" for feature in sprint_backlog
                    )
                    return (
                        "I already have captured improvements queued for delivery: "
                        f"{titles}. Tell Builder to continue when you want the next safe step."
                    )
                return (
                    "I do not have a captured improvement ready to ship yet. "
                    "Tell me the improvement you want, and I will ask the missing questions."
                )
            first_feature = next_sprint_candidates[0]
            if auto_select_first:
                selected_ids = [first_feature.id]
                break

            excluded = [item for item in product_backlog if item.id != first_feature.id]
            excluded_note = (
                "Excluded for next sprint: "
                + "; ".join(
                    f"{item.title} needs a later sprint to keep this one shippable"
                    for item in excluded[:3]
                )
                if excluded
                else "No excluded backlog items."
            )
            question = {
                "first_feature_id": first_feature.id,
                "product_backlog_ids": [feature.id for feature in product_backlog],
                "product_backlog_options": _format_sprint_planning_options(product_backlog),
                "options": [
                    {
                        "label": f"Ship this improvement: {first_feature.id} (Recommended)",
                        "description": (
                            f"{first_feature.title}. Keeps delivery focused on one shippable outcome. "
                            f"{excluded_note}"
                        ),
                    },
                    {
                        "label": "Ship all ready improvements",
                        "description": (
                            "Broader than the default; use only if these improvements must ship together."
                        ),
                    },
                    {
                        "label": "Hold delivery",
                        "description": "Keep the captured improvement unchanged.",
                    },
                ],
            }

        if question is None:
            continue
        answer_value = await _request_chat_question(
            session_id,
            hub,
            header="Delivery Scope",
            question="What should Builder ship next?",
            options=question["options"],
        )
        answer_lower = answer_value.lower()
        if answer_lower.startswith("ship this improvement"):
            selection_ids = [str(question["first_feature_id"])]
        elif answer_lower.startswith("ship all ready"):
            selection_ids = [str(item_id) for item_id in question["product_backlog_ids"]]
        elif answer_lower.startswith("hold"):
            return "Delivery is on hold. I kept the captured improvement unchanged."
        else:
            selection_message = answer_value
            selection_ids = None
        auto_select_first = False

    async with session_factory() as db:
        project = await db.get(Project, project_id)
        if project is None:
            return "Delivery is blocked because the selected project is no longer available."
        feature_result = await db.execute(
            select(Feature)
            .where(Feature.project_id == project.id)
            .where(Feature.id.in_(selected_ids))
            .options(selectinload(Feature.tasks))
            .order_by(Feature.priority.desc(), Feature.created_at.asc())
        )
        planned_features = list(feature_result.scalars().all())
        if not planned_features:
            return (
                "I could not match that answer to a ready improvement. "
                f"Current ready improvements:\n{_format_sprint_planning_options([])}"
            )
        if skip_scope_approval:
            return await create_delivery_plan_for_approved_features(
                session_id, project_root, selected_ids
            )
        approval_input = {
            "feature_ids": [feature.id for feature in planned_features],
            "features": [
                {
                    "id": feature.id,
                    "title": feature.title,
                    "priority": feature.priority,
                    "acceptance_criteria": list(feature.acceptance_criteria or []),
                }
                for feature in planned_features
            ],
            "next_step_if_approved": "Prepare the approved improvement and start delivery.",
        }

    approval = await _request_chat_approval(
        session_id,
        hub,
        tool_name="Delivery scope approval",
        tool_input=approval_input,
        summary="Approve this improvement before work starts",
        description=(
            "Builder selected the improvement to ship next. "
            "Approve only if this is the right product change."
        ),
    )
    decision = str(approval.get("decision", "deny")).strip().lower() or "deny"
    if decision != "allow":
        return "Delivery scope was not approved. I kept the captured improvement unchanged."
    return await create_delivery_plan_for_approved_features(
        session_id, project_root, selected_ids
    )


async def create_delivery_plan_for_approved_features(
    session_id: str,
    project_root: Path,
    selected_ids: list[str],
) -> str:
    if not selected_ids:
        return "Delivery scope approval did not include any selected improvements."
    session_factory = get_session_factory()
    async with session_factory() as db:
        feature_result = await db.execute(
            select(Feature)
            .where(Feature.id.in_(selected_ids))
            .options(selectinload(Feature.tasks))
            .order_by(Feature.priority.desc(), Feature.created_at.asc())
        )
        planned_features = list(feature_result.scalars().all())
        if not planned_features:
            return (
                "Delivery could not create work steps because the selected improvements changed."
            )
        project_ids = {feature.project_id for feature in planned_features}
        if len(project_ids) != 1:
            return "Delivery is blocked because the approved improvements span multiple projects."
        project = await db.get(Project, next(iter(project_ids)))
        if project is None:
            return "Delivery is blocked because the selected project is no longer available."
        artifacts = await persist_sprint_execution_artifacts(
            db, project, planned_features, chat_session_id=session_id
        )
        first_task = artifacts.get("tasks", [None])[0] if artifacts.get("tasks") else None
        first_task_id = str(getattr(first_task, "id", "") or "").strip()
        first_task_title = str(getattr(first_task, "title", "") or "").strip()
        for feature in planned_features:
            mirror_item_to_artifact(project_root, feature_to_item_payload(feature))
        plan = artifacts["plan"]
        db.add(
            ChatEvent(
                session_id=session_id,
                event_type="delivery_plan_created",
                payload_json={
                    "plan_id": plan["plan_id"],
                    "feature_ids": [feature.id for feature in planned_features],
                    "feature_titles": [feature.title for feature in planned_features],
                    "started_task_id": first_task_id,
                    "started_task_title": first_task_title,
                },
                status="completed",
            )
        )
        await db.commit()

    from autonomous_agent_builder.api.routes.dashboard_api import publish_board_snapshot
    async with session_factory() as db:
        await publish_board_snapshot(db)
    task_titles = [task.title for task in artifacts.get("tasks", [])]
    if not task_titles:
        return (
            "Delivery planning did not create work steps. "
            "Check the captured improvement before starting work."
        )
    first_task = artifacts.get("tasks", [None])[0]
    first_task_id = str(getattr(first_task, "id", "") or "").strip()
    if first_task_id:
        await schedule_task_dispatch(first_task_id)
    feature_titles = [feature.title for feature in planned_features if feature.title]
    feature_label = ", ".join(f"`{title}`" for title in feature_titles[:3])
    if not feature_label:
        feature_label = "the approved improvement"
    return (
        f"Approved. Builder prepared the work for {feature_label}. "
        "Delivery has started."
    )
