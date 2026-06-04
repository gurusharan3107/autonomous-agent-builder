"""High-risk voice action preparation and confirmation extracted from voice_operator.py."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from autonomous_agent_builder.db.models import (
    ChatEvent,
    Task,
    TaskStatus,
    utcnow,
)
from autonomous_agent_builder.db.session import get_session_factory
from autonomous_agent_builder.embedded.server import agent_chat_sessions
from autonomous_agent_builder.embedded.server.chat_state import ChatSessionHub
from autonomous_agent_builder.services.task_recovery import recover_failed_task
from autonomous_agent_builder.services.voice_operator_interaction import (
    select_recovery_task as _select_recovery_task,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    task_recovery_snapshot as _task_recovery_snapshot,
)


class HighRiskVoiceActionService:
    """Own prepared high-risk voice actions and confirmation."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def prepare_approval_decision(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session_id = str(arguments.get("session_id") or "").strip()
        event_id = str(arguments.get("event_id") or "").strip()
        decision = str(arguments.get("decision") or "").strip().lower()
        reason = str(arguments.get("reason") or "").strip()
        voice_call_id = str(arguments.get("voice_call_id") or "").strip()
        if not session_id or not event_id or decision not in {"allow", "deny"}:
            raise ValueError("session_id, event_id, and decision allow/deny are required")

        session_factory = get_session_factory()
        delegated_message = ""
        prepared: ChatEvent | None = None
        async with session_factory() as db:
            approval = await db.get(ChatEvent, event_id)
            if approval is None or approval.session_id != session_id:
                return {
                    "status": "not_pending_approval",
                    "message": (
                        "No pending approval matches that event. Treat this as normal Builder work "
                        "unless the operator explicitly names a pending approval."
                    ),
                    "recommended_tool": "delegate_to_builder_agent",
                    "session_id": session_id,
                    "event_id": event_id,
                }
            if approval.event_type != "tool_approval_request" or approval.status != "pending":
                delegated_message = reason.strip()
                if not delegated_message:
                    delegated_message = str(
                        (approval.payload_json or {}).get("content") or ""
                    ).strip()
            else:
                payload = approval.payload_json or {}
                tool_name = str(payload.get("tool_name") or "high-risk action")
                consequence = f'Voice will {decision} pending approval "{tool_name}".'
                confirmation_phrase = f"Confirm {decision} for approval event {event_id}."
                prepared = ChatEvent(
                    session_id=session_id,
                    event_type="voice_action_prepared",
                    status="pending",
                    payload_json=self._prepared_payload(
                        action_kind="approval_decision",
                        voice_call_id=voice_call_id,
                        session_id=session_id,
                        target_event_id=event_id,
                        target_entity_id=event_id,
                        proposed_decision=decision,
                        consequence_summary=consequence,
                        operator_reason=reason,
                        confirmation_phrase=confirmation_phrase,
                        transcript_excerpt=reason,
                        created_at=utcnow(),
                    ),
                )
                prepared.payload_json["target_session_id"] = session_id
                db.add(prepared)
                await db.commit()
                await db.refresh(prepared)
                prepared.payload_json = {**prepared.payload_json, "action_id": prepared.id}
                await db.commit()
                await db.refresh(prepared)

        if delegated_message:
            from autonomous_agent_builder.services.voice_operator import (
                AgentOperatorService,  # noqa: PLC0415
            )

            result = await AgentOperatorService(self.app).send_message(
                {
                    "session_id": session_id,
                    "message": delegated_message,
                    "thread_mode": "current",
                    "routing_reason": (
                        "voice approval tool targeted a non-approval event; safely "
                        "delegated as normal Builder work"
                    ),
                }
            )
            return {
                "status": "delegated_non_approval_request",
                "message": (
                    "That event is not a pending approval, so Builder delegated the request "
                    "through the normal Agent lane instead of preparing an approval."
                ),
                "delegation": result,
            }

        if prepared is None:
            return {
                "status": "not_pending_approval",
                "message": (
                    "That event is not a pending approval. Ask one concise clarification or "
                    "delegate the operator request through delegate_to_builder_agent."
                ),
                "recommended_tool": "delegate_to_builder_agent",
                "session_id": session_id,
                "event_id": event_id,
            }

        hub: ChatSessionHub = self.app.state.chat_hub
        await hub.publish(
            session_id,
            {
                "id": prepared.id,
                "type": prepared.event_type,
                "status": prepared.status,
                "timestamp": prepared.created_at.isoformat(),
                "payload": prepared.payload_json,
            },
        )
        return {
            "action_id": prepared.id,
            "requires_confirmation": True,
            "consequence_summary": prepared.payload_json["consequence_summary"],
            "confirmation_phrase": prepared.payload_json["confirmation_phrase"],
            "prepared_action": prepared.payload_json,
        }

    async def prepare_recovery(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session_id = str(arguments.get("session_id") or "").strip()
        recovery_request = str(arguments.get("recovery_request") or "").strip()
        voice_call_id = str(arguments.get("voice_call_id") or "").strip()
        project_root = Path(self.app.state.project_root)
        session_factory = get_session_factory()
        async with session_factory() as db:
            session = await self._resolve_recovery_session(db, project_root, session_id)
            blocked_tasks = await self._load_recoverable_board_tasks(db)
            task, matched_on = _select_recovery_task(blocked_tasks, recovery_request)
            if task is None:
                if len(blocked_tasks) > 1:
                    return {
                        "session_id": session.id,
                        "status": "clarification_required",
                        "message": (
                            "Multiple blocked Board tasks match poorly. Ask which task to recover."
                        ),
                        "blocked_tasks": [
                            _task_recovery_snapshot(item) for item in blocked_tasks[:5]
                        ],
                    }
                return {
                    "session_id": session.id,
                    "status": "not_recoverable",
                    "requires_confirmation": False,
                    "message": (
                        "No blocked, failed, or capability-limited Board task is available "
                        "for recovery."
                    ),
                    "operator_message": (
                        "I do not see a recoverable Board task. Open the relevant run trace "
                        "or ask Builder to diagnose the failure before attempting recovery."
                    ),
                    "blocked_tasks": [],
                    "recommended_tool": "open_run_trace",
                    "recovery_request": recovery_request,
                }

            task_snapshot = _task_recovery_snapshot(task)
            consequence = (
                f'Voice will recover blocked Board task "{task_snapshot["title"]}" '
                f"from {task_snapshot['status'].replace('_', ' ')}."
            )
            prepared = ChatEvent(
                session_id=session.id,
                event_type="voice_action_prepared",
                status="pending",
                payload_json=self._prepared_payload(
                    action_kind="recovery",
                    voice_call_id=voice_call_id,
                    session_id=session.id,
                    target_event_id="",
                    target_entity_id=task.id,
                    proposed_decision="recover",
                    consequence_summary=consequence,
                    operator_reason=recovery_request,
                    confirmation_phrase=f"Confirm recovery for task {task.id}.",
                    transcript_excerpt=recovery_request,
                    created_at=utcnow(),
                    result_json={
                        "task": task_snapshot,
                        "matched_on": matched_on,
                    },
                ),
            )
            prepared.payload_json["target_session_id"] = session.id
            prepared.payload_json["task"] = task_snapshot
            prepared.payload_json["matched_on"] = matched_on
            db.add(prepared)
            await db.commit()
            await db.refresh(prepared)
            prepared.payload_json = {**prepared.payload_json, "action_id": prepared.id}
            await db.commit()
            await db.refresh(prepared)

        hub: ChatSessionHub = self.app.state.chat_hub
        await hub.publish(
            session.id,
            {
                "id": prepared.id,
                "type": prepared.event_type,
                "status": prepared.status,
                "timestamp": prepared.created_at.isoformat(),
                "payload": prepared.payload_json,
            },
        )
        return {
            "session_id": session.id,
            "status": "confirmation_required",
            "action_id": prepared.id,
            "requires_confirmation": True,
            "consequence_summary": consequence,
            "confirmation_phrase": prepared.payload_json["confirmation_phrase"],
            "task": task_snapshot,
            "matched_on": matched_on,
            "prepared_action": prepared.payload_json,
        }

    async def recover_board_task(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session_id = str(arguments.get("session_id") or "").strip()
        task_id = str(arguments.get("task_id") or "").strip()
        recovery_request = str(
            arguments.get("recovery_request") or arguments.get("task") or ""
        ).strip()
        voice_call_id = str(arguments.get("voice_call_id") or "").strip()
        project_root = Path(self.app.state.project_root)
        session_factory = get_session_factory()
        async with session_factory() as db:
            session = await self._resolve_recovery_session(db, project_root, session_id)
            blocked_tasks = await self._load_recoverable_board_tasks(db)
            if task_id:
                task = next((item for item in blocked_tasks if item.id == task_id), None)
                matched_on = "task_id" if task is not None else ""
            else:
                task, matched_on = _select_recovery_task(blocked_tasks, recovery_request)
            if task is None:
                return {
                    "session_id": session.id,
                    "status": "no_recoverable_task",
                    "message": "No blocked Board task is recoverable from Realtime right now.",
                    "blocked_tasks": [_task_recovery_snapshot(item) for item in blocked_tasks[:5]],
                }
            task_snapshot = _task_recovery_snapshot(task)
            result = await recover_failed_task(task, db)

        from autonomous_agent_builder.services.voice_operator import (
            AgentOperatorService,  # noqa: PLC0415
        )

        event = await AgentOperatorService(self.app).append_and_publish_voice_event(
            session.id,
            "voice_control_action",
            {
                "action": "recover_task",
                "task": {
                    **task_snapshot,
                    "status": str(result.get("current_status") or task_snapshot["status"]),
                    "previous_status": str(result.get("previous_status") or ""),
                },
                "matched_on": matched_on,
                "result": result,
                "status": "recovered",
                "route": "/board",
                "source": "realtime_voice",
                "voice_call_id": voice_call_id,
            },
        )
        return {
            "session_id": session.id,
            "event_id": event.id,
            "status": "recovered_board_task",
            "task_id": task_snapshot["id"],
            "task_title": task_snapshot["title"],
            "previous_status": result.get("previous_status"),
            "current_status": result.get("current_status"),
            "route": "/board",
            "next_step": "dispatch_board_task",
        }

    async def confirm_action(self, arguments: dict[str, Any]) -> dict[str, Any]:
        action_id = str(arguments.get("action_id") or "").strip()
        confirmation_phrase = str(arguments.get("confirmation_phrase") or "").strip()
        transcript_excerpt = str(arguments.get("transcript_excerpt") or "").strip()
        session_factory = get_session_factory()
        async with session_factory() as db:
            action = await db.get(ChatEvent, action_id)
            if action is None or action.event_type != "voice_action_prepared":
                raise ValueError("Prepared action not found or already used")
            if action.status != "pending":
                raise ValueError("Prepared action not found or already used")
            payload = dict(action.payload_json or {})
            if self._is_expired(payload):
                payload["status"] = "expired"
                payload["prepared_status"] = "expired"
                action.payload_json = payload
                action.status = "expired"
                await db.commit()
                raise ValueError("Prepared action expired")
            payload["status"] = "confirmed"
            payload["prepared_status"] = "confirmed"
            payload["confirmed_at"] = utcnow().isoformat()
            payload["confirmation_phrase"] = confirmation_phrase or payload.get(
                "confirmation_phrase",
                "",
            )
            if transcript_excerpt:
                payload["transcript_excerpt"] = transcript_excerpt
            action.payload_json = payload
            await db.commit()

        from autonomous_agent_builder.services.voice_operator import (
            AgentOperatorService,  # noqa: PLC0415
        )

        agent = AgentOperatorService(self.app)

        if (
            payload.get("action_kind") == "approval_decision"
            or payload.get("kind") == "approval_decision"
        ):
            result = await agent.answer_tool_approval(
                {
                    "session_id": str(
                        payload.get("target_session_id") or payload.get("agent_session_id") or ""
                    ),
                    "event_id": str(payload.get("target_event_id") or ""),
                    "decision": str(payload.get("proposed_decision") or ""),
                    "reason": str(payload.get("operator_reason") or ""),
                }
            )
        elif payload.get("action_kind") == "recovery" or payload.get("kind") == "recovery":
            result = await self._execute_recovery(payload)
        else:
            raise ValueError(
                f"Unsupported prepared action: {payload.get('action_kind') or payload.get('kind')}"
            )

        async with session_factory() as db:
            action = await db.get(ChatEvent, action_id)
            if action is not None:
                updated = dict(action.payload_json or {})
                updated["status"] = "executed"
                updated["prepared_status"] = "executed"
                updated["executed_at"] = utcnow().isoformat()
                updated["result_json"] = result
                updated["result"] = result
                action.payload_json = updated
                action.status = "answered"
                await db.commit()
        return result

    async def _execute_recovery(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = str(payload.get("target_entity_id") or "")
        session_id = str(payload.get("agent_session_id") or payload.get("target_session_id") or "")
        if not task_id or not session_id:
            raise ValueError("Prepared recovery action is missing task or session id")
        session_factory = get_session_factory()
        async with session_factory() as db:
            task = await db.get(Task, task_id)
            if task is None:
                raise ValueError("Prepared recovery task not found")
            recovery_input = {
                "recovery_request": str(payload.get("operator_reason") or ""),
                "matched_on": str(payload.get("matched_on") or ""),
                "task": _task_recovery_snapshot(task),
            }
            try:
                recovery_result = await recover_failed_task(task, db)
            except HTTPException as exc:
                await db.rollback()
                recovery_result = {
                    "status": "not_recoverable",
                    "detail": exc.detail,
                    "task_id": recovery_input["task"]["id"],
                }

        from autonomous_agent_builder.services.voice_operator import (
            AgentOperatorService,  # noqa: PLC0415
        )

        agent = AgentOperatorService(self.app)
        await agent.append_and_publish_voice_event(
            session_id,
            "voice_operator_message",
            {
                "content": recovery_input["recovery_request"]
                or f"Recover blocked task {recovery_input['task']['title']}",
                "source": "realtime_voice",
                "speaker": "operator",
                "target": "builder_task_recovery",
                "thread_mode": "current",
                "routing_reason": "operator confirmed blocked Board task recovery",
            },
        )
        tool_event = await agent.append_and_publish_voice_event(
            session_id,
            "tool_result",
            {
                "tool_name": "recover_blocked_run",
                "tool_input": recovery_input,
                "content": json.dumps(recovery_result, ensure_ascii=True, sort_keys=True),
                "diagnostic": (
                    f"Recovered blocked Board task {recovery_input['task']['title']}"
                    if recovery_result.get("status") == "ok"
                    else f"Recovery did not run for {recovery_input['task']['title']}"
                ),
            },
        )
        return {
            "session_id": session_id,
            "status": (
                "recovered_blocked_task"
                if recovery_result.get("status") == "ok"
                else "recovery_not_run"
            ),
            "task": recovery_input["task"],
            "matched_on": recovery_input["matched_on"],
            "recovery": recovery_result,
            "event_id": tool_event.id,
        }

    async def _resolve_recovery_session(
        self,
        db: Any,
        project_root: Path,
        session_id: str,
    ) -> Any:
        if session_id:
            session = await agent_chat_sessions.load_session(
                db,
                session_id,
                project_root=project_root,
                reject_scope_mismatch=True,
            )
            if session is None:
                raise ValueError("Agent-page chat session not found")
            return session
        scoped_sessions = await agent_chat_sessions.list_scoped_sessions(db, project_root)
        session = agent_chat_sessions.latest_resume_candidate(scoped_sessions)
        if session is None:
            raise ValueError("No recoverable Agent-page chat session found")
        return session

    async def _load_recoverable_board_tasks(self, db: Any) -> list[Task]:
        blocked_statuses = [
            TaskStatus.BLOCKED,
            TaskStatus.CAPABILITY_LIMIT,
            TaskStatus.FAILED,
        ]
        result = await db.execute(
            select(Task)
            .where(Task.status.in_(blocked_statuses))
            .order_by(Task.updated_at.desc(), Task.created_at.desc())
        )
        return list(result.scalars().all())

    def _prepared_payload(
        self,
        *,
        action_kind: str,
        voice_call_id: str,
        session_id: str,
        target_event_id: str,
        target_entity_id: str,
        proposed_decision: str,
        consequence_summary: str,
        operator_reason: str,
        confirmation_phrase: str,
        transcript_excerpt: str,
        created_at: datetime,
        result_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        expires_at = created_at + timedelta(minutes=10)
        return {
            "action_id": "",
            "action_kind": action_kind,
            "kind": action_kind,
            "voice_call_id": voice_call_id,
            "agent_session_id": session_id,
            "target_session_id": session_id,
            "target_event_id": target_event_id,
            "target_entity_id": target_entity_id,
            "proposed_decision": proposed_decision,
            "consequence_summary": consequence_summary,
            "operator_reason": operator_reason,
            "status": "pending",
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "confirmed_at": "",
            "executed_at": "",
            "confirmation_phrase": confirmation_phrase,
            "transcript_excerpt": transcript_excerpt,
            "result_json": result_json or {},
            "prepared_status": "pending_confirmation",
            "source": "realtime_voice",
        }

    def _is_expired(self, payload: dict[str, Any]) -> bool:
        raw = str(payload.get("expires_at") or "")
        if not raw:
            return False
        try:
            expires_at = datetime.fromisoformat(raw)
        except ValueError:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at <= utcnow()
