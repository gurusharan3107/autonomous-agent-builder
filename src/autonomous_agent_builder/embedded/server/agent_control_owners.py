"""Control-owner reconciliation for embedded Agent conversation events."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.models import ChatEvent, ChatSession, Feature

FeatureResolver = Callable[[AsyncSession, ChatEvent], Awaitable[Feature | None]]


async def _supersede_voice_summary_decision_echoes(
    session: ChatSession,
    db: AsyncSession,
) -> bool:
    pending_questions: dict[str, ChatEvent] = {}
    for event in session.events:
        if event.event_type != "ask_user_question" or event.status != "pending":
            continue
        payload = event.payload_json if isinstance(event.payload_json, dict) else {}
        if payload.get("source") != "assistant_delivery_permission_prompt":
            continue
        assistant_event_id = str(payload.get("assistant_event_id") or "").strip()
        if assistant_event_id:
            pending_questions[assistant_event_id] = event
    if not pending_questions:
        return False

    changed = False
    superseded_summary_ids: dict[str, ChatEvent] = {}
    for event in session.events:
        if event.event_type != "voice_final_summary":
            continue
        payload = dict(event.payload_json or {})
        decision_event = pending_questions.get(str(payload.get("assistant_event_id") or "").strip())
        if decision_event is None:
            continue
        if event.status == "superseded":
            superseded_summary_ids[event.id] = decision_event
            continue
        payload.update(
            {
                "superseded_by_event_id": decision_event.id,
                "superseded_reason": "pending_decision_controls_operator_response",
            }
        )
        event.payload_json = payload
        event.status = "superseded"
        superseded_summary_ids[event.id] = decision_event
        changed = True
    for event in session.events:
        if event.event_type != "voice_completion_notification" or event.status == "superseded":
            continue
        payload = dict(event.payload_json or {})
        summary_event_id = str(payload.get("voice_final_summary_event_id") or "").strip()
        decision_event = superseded_summary_ids.get(summary_event_id)
        if decision_event is None:
            continue
        payload.update(
            {
                "superseded_by_event_id": decision_event.id,
                "superseded_reason": "pending_decision_controls_operator_response",
            }
        )
        event.payload_json = payload
        event.status = "superseded"
        changed = True
    if changed:
        await db.flush()
    return changed


async def _supersede_redundant_delivery_scope_approvals(
    session: ChatSession,
    db: AsyncSession,
    *,
    feature_resolver: FeatureResolver,
) -> bool:
    approved_feature_ids: set[str] = set()
    question_ids: list[str] = []
    for event in session.events:
        if event.event_type != "ask_user_question" or event.status != "answered":
            continue
        payload = event.payload_json if isinstance(event.payload_json, dict) else {}
        if payload.get("source") != "assistant_delivery_permission_prompt":
            continue
        answer = str(payload.get("answer_value") or "").strip().lower()
        if answer.startswith("hold"):
            continue
        feature = await feature_resolver(db, event)
        if feature is None:
            continue
        approved_feature_ids.add(feature.id)
        question_ids.append(event.id)
    if not approved_feature_ids:
        return False

    changed = False
    for event in session.events:
        if event.event_type != "tool_approval_request" or event.status == "superseded":
            continue
        payload = dict(event.payload_json or {})
        if payload.get("tool_name") != "Delivery scope approval":
            continue
        tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
        feature_ids = {
            str(feature_id).strip()
            for feature_id in tool_input.get("feature_ids", [])
            if str(feature_id).strip()
        }
        if not feature_ids.intersection(approved_feature_ids):
            continue
        payload.update(
            {
                "superseded_by_event_id": question_ids[-1],
                "superseded_reason": "delivery_permission_answer_controls_delivery_start",
            }
        )
        event.payload_json = payload
        event.status = "superseded"
        changed = True
    if changed:
        await db.flush()
    return changed


async def reconcile_session_control_owners(
    session: ChatSession,
    db: AsyncSession,
    *,
    feature_resolver: FeatureResolver,
) -> bool:
    """Supersede duplicate decision surfaces after one owner controls the response."""
    changed = False
    if await _supersede_voice_summary_decision_echoes(session, db):
        changed = True
    if await _supersede_redundant_delivery_scope_approvals(
        session,
        db,
        feature_resolver=feature_resolver,
    ):
        changed = True
    return changed
