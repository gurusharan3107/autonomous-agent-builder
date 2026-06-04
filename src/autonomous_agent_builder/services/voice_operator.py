"""Builder-owned services for the Realtime voice operator lane."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.db.models import (
    AgentRun,
    ChatEvent,
    ChatSession,
    Feature,
    Task,
    TaskStatus,
)
from autonomous_agent_builder.db.session import get_session_factory
from autonomous_agent_builder.embedded.server import agent_chat_sessions, agent_chat_transcript
from autonomous_agent_builder.embedded.server.chat_state import ChatSessionHub
from autonomous_agent_builder.services.dispatch_lock import reserve_dispatch
from autonomous_agent_builder.services.runtime_settings import (
    persist_runtime_settings,
    reconcile_runtime_project_state,
    runtime_settings_payload,
)
from autonomous_agent_builder.services.task_dispatch_policy import (
    task_dispatch_sort_key as _task_dispatch_sort_key,
)
from autonomous_agent_builder.services.task_dispatch_policy import (
    task_is_dispatchable as _task_is_dispatchable,
)
from autonomous_agent_builder.services.task_dispatch_policy import (
    task_status_value as _task_status_value,
)
from autonomous_agent_builder.services.voice_completion_digest import AgentVoiceDigestService
from autonomous_agent_builder.services.voice_operator_interaction import (
    NAVIGATION_TARGETS as _NAVIGATION_TARGETS,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    agent_run_trace_snapshot as _agent_run_trace_snapshot,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    approval_decision_from_utterance as _approval_decision_from_utterance,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    approval_reminder_prompt_text as _approval_reminder_prompt_text,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    bind_voice_call_session,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    dashboard_route_for_target as _dashboard_route_for_target,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    normalize_match_text as _normalize_match_text,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    resolve_question_answer_value as _resolve_question_answer_value,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    runtime_display_name as _runtime_display_name,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    task_dispatch_snapshot as _task_dispatch_snapshot,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    voice_call_session_id as _voice_call_session_id,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    voice_runtime_sdk as _voice_runtime_sdk,
)
from autonomous_agent_builder.services.voice_operator_support import (
    PendingOperatorItemService,
    VoiceAgentChatTarget,
    VoiceCapabilityDecision,
    VoiceCapabilityDecisionService,
    VoiceCompletionNotifier,
)
from autonomous_agent_builder.services.voice_cost_ledger import VoiceCostLedger
from autonomous_agent_builder.services.voice_high_risk_actions import HighRiskVoiceActionService
from autonomous_agent_builder.services.voice_operator_board_status import (
    load_voice_board_status as _load_voice_board_status,
)
from autonomous_agent_builder.services.voice_operator_digest_builder import build_voice_digest
from autonomous_agent_builder.services.voice_thread_routing import (
    VoiceThreadRoute,
    VoiceThreadRouter,
)

_BLOCKED_TRACE_TASK_STATUSES = {
    TaskStatus.BLOCKED.value,
    TaskStatus.CAPABILITY_LIMIT.value,
    TaskStatus.FAILED.value,
}


def _compact_realtime_event_text(value: Any, *, max_length: int = 360) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def _voice_tool_output_evidence(output: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    result = output.get("result") if isinstance(output.get("result"), dict) else None
    status = output.get("status") if isinstance(output.get("status"), dict) else None
    source = result or status
    if not isinstance(source, dict):
        return evidence

    result_status = source.get("status")
    if isinstance(result_status, str) and result_status.strip():
        evidence["result_status"] = result_status.strip()
    completion_status = source.get("completion_status")
    if isinstance(completion_status, str) and completion_status.strip():
        evidence["completion_status"] = completion_status.strip()
    recommended_tool = source.get("recommended_tool")
    if isinstance(recommended_tool, str) and recommended_tool.strip():
        evidence["recommended_tool"] = recommended_tool.strip()
    capability_decision = source.get("capability_decision")
    if isinstance(capability_decision, dict):
        decision = capability_decision.get("decision")
        if isinstance(decision, str) and decision.strip():
            evidence["capability_decision"] = decision.strip()
    for message_key in ("operator_message", "message", "voice_digest", "summary"):
        message = source.get(message_key)
        if isinstance(message, str) and message.strip():
            evidence["result_message"] = _compact_realtime_event_text(message)
            break
    return evidence



class AgentOperatorService:
    """Own public Agent-page operations used by Realtime voice."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.pending_items = PendingOperatorItemService()
        self.digest_service = AgentVoiceDigestService()
        self.completion_notifier = VoiceCompletionNotifier(app, self.digest_service)
        self.capability_decisions = VoiceCapabilityDecisionService()

    async def get_builder_status(
        self,
        *,
        active_session_id: str = "",
        prefer_latest_summary: bool = False,
        status_prompt: str = "",
    ) -> dict[str, Any]:
        project_root = Path(self.app.state.project_root)
        hub: ChatSessionHub = self.app.state.chat_hub
        session_factory = get_session_factory()
        async with session_factory() as db:
            board_status = await self.load_voice_board_status(db, status_prompt=status_prompt)
            current_runtime = runtime_settings_payload(project_root, include_capabilities=False)
            session = None
            if active_session_id:
                session = await db.get(ChatSession, active_session_id)
            if session is None:
                result = await db.execute(
                    select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(1)
                )
                session = result.scalar_one_or_none()
            if session is None:
                voice_digest = self.voice_digest(
                    active_run=False,
                    pending_count=0,
                    board_status=board_status,
                    prefer_latest_summary=prefer_latest_summary,
                    status_prompt=status_prompt,
                )
                return {
                    "project_root": str(project_root),
                    "latest_session_id": "",
                    "active_run": False,
                    "voice_digest": voice_digest,
                    "current_runtime": current_runtime,
                    "board_status": board_status,
                    "latest_voice_summary": None,
                    "pending_operator_items": [],
                }
            event_result = await db.execute(
                select(ChatEvent)
                .where(ChatEvent.session_id == session.id)
                .order_by(ChatEvent.created_at.desc())
                .limit(40)
            )
            events = list(event_result.scalars().all())

        pending = self.pending_items.pending_operator_items(events)
        latest_voice_summary = next(
            (
                {
                    "event_id": event.id,
                    "summary": str(
                        (event.payload_json or {}).get("spoken_summary")
                        or (event.payload_json or {}).get("summary")
                        or ""
                    ),
                    "assistant_event_id": str(
                        (event.payload_json or {}).get("assistant_event_id") or ""
                    ),
                    "read_policy": str((event.payload_json or {}).get("read_policy") or ""),
                    "outcome": str((event.payload_json or {}).get("outcome") or ""),
                    "evidence_refs": list((event.payload_json or {}).get("evidence_refs") or []),
                }
                for event in events
                if event.event_type == "voice_final_summary"
                and str(event.status) in {"completed", "blocked", "failed", "pending"}
            ),
            None,
        )
        active_run = await hub.has_active_run(session.id)
        voice_digest = self.voice_digest(
            active_run=active_run,
            pending_count=len(pending),
            board_status=board_status,
            prefer_latest_summary=prefer_latest_summary,
            latest_voice_summary=str(latest_voice_summary["summary"]) if latest_voice_summary else "",
            status_prompt=status_prompt,
        )
        async with session_factory() as db:
            db.add(
                ChatEvent(
                    session_id=session.id,
                    event_type="voice_digest",
                    status="completed",
                    payload_json={
                        "digest": voice_digest,
                        "current_runtime": current_runtime,
                        "pending_operator_count": len(pending),
                        "active_run": active_run,
                        "board_status": board_status,
                        "latest_voice_summary_event_id": (
                            latest_voice_summary["event_id"] if latest_voice_summary else ""
                        ),
                        "source": "realtime_voice",
                    },
                )
            )
            await db.commit()
        return {
            "project_root": str(project_root),
            "latest_session_id": session.id,
            "active_run": active_run,
            "voice_digest": voice_digest,
            "current_runtime": current_runtime,
            "board_status": board_status,
            "latest_voice_summary": latest_voice_summary,
            "pending_operator_items": pending,
        }

    async def pending_approval_prompt(
        self,
        *,
        active_session_id: str = "",
        call_id: str = "",
    ) -> dict[str, Any] | None:
        """Build and record a concise voice prompt for unresolved approvals."""

        session_factory = get_session_factory()
        async with session_factory() as db:
            session = None
            if active_session_id:
                session = await db.get(ChatSession, active_session_id)
            if session is None:
                result = await db.execute(
                    select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(1)
                )
                session = result.scalar_one_or_none()
            if session is None:
                return None
            event_result = await db.execute(
                select(ChatEvent)
                .where(ChatEvent.session_id == session.id)
                .order_by(ChatEvent.created_at.desc())
                .limit(40)
            )
            events = list(event_result.scalars().all())

        pending_approvals = self.pending_items.pending_approval_items(events)
        if not pending_approvals:
            return None

        first = pending_approvals[0]
        prompt_text = _approval_reminder_prompt_text(first, len(pending_approvals))
        event = await self.append_and_publish_voice_event(
            session.id,
            "voice_approval_prompt",
            {
                "voice_call_id": call_id,
                "pending_approval_count": len(pending_approvals),
                "pending_item": first,
                "prompt": prompt_text,
                "source": "realtime_voice",
            },
        )
        return {
            "session_id": session.id,
            "event_id": event.id,
            "prompt": prompt_text,
            "pending_approval_count": len(pending_approvals),
            "pending_item": first,
        }

    def _voice_route_and_capability(
        self,
        *,
        arguments: dict[str, Any],
        message: str,
        active_session_id: str,
        status: dict[str, Any],
    ) -> tuple[VoiceThreadRoute, VoiceCapabilityDecision]:
        if bool(arguments.get("bypass_voice_routing")):
            route = VoiceThreadRoute(
                route="current",
                thread_mode="current",
                confidence=1.0,
                routing_reason=str(arguments.get("routing_reason") or "service-directed recovery"),
                target_session_id=active_session_id or str(status.get("latest_session_id") or ""),
            )
        else:
            route = VoiceThreadRouter().route(
                operator_utterance=message,
                latest_session_id=str(status.get("latest_session_id") or ""),
                active_run=bool(status.get("active_run")),
                pending_operator_items=list(status.get("pending_operator_items") or []),
                latest_voice_summary=status.get("latest_voice_summary"),
            )
        capability_decision = self.capability_decisions.decide(
            operator_utterance=message,
            route=route,
            builder_status=status,
        )
        if bool(arguments.get("bypass_voice_routing")):
            capability_decision = VoiceCapabilityDecision(
                decision="sdk_chat",
                voice_action="delegate",
                builder_route="agent_chat",
                can_execute_now=True,
                operator_message="Service-directed recovery may delegate to Agent chat.",
                evidence_refs=("bypass_voice_routing",),
            )
        return route, capability_decision

    async def _direct_voice_route_response(
        self,
        *,
        route: VoiceThreadRoute,
        capability_decision: VoiceCapabilityDecision,
        status: dict[str, Any],
        message: str,
    ) -> dict[str, Any] | None:
        if capability_decision.decision in {"blocked", "unsupported", "not_recoverable"}:
            blocked_status = (
                "unsupported_request"
                if capability_decision.decision == "unsupported"
                else "not_recoverable"
                if capability_decision.decision == "not_recoverable"
                else "capability_blocked"
            )
            return {
                "status": blocked_status,
                "completion_status": blocked_status,
                "operator_message": capability_decision.operator_message,
                "voice_route": route.as_dict(),
                "capability_decision": capability_decision.as_dict(),
            }
        if route.route == "status":
            return {
                "status": "read_only_status",
                "builder_status": status,
                "completion_status": "direct_status",
                "completion_digest": status,
                "voice_route": route.as_dict(),
                "capability_decision": capability_decision.as_dict(),
            }
        if route.route == "clarify":
            return {
                "status": "clarification_required",
                "clarifying_question": route.clarifying_question,
                "voice_route": route.as_dict(),
                "capability_decision": capability_decision.as_dict(),
            }
        if route.route == "answer_pending":
            answered = await self.answer_pending_question(
                {
                    "session_id": route.target_session_id,
                    "event_id": route.target_event_id,
                    "answer": message,
                }
            )
            return {
                "status": "answered_pending_question",
                "result": answered,
                "voice_route": route.as_dict(),
                "capability_decision": capability_decision.as_dict(),
            }
        if route.route == "approval_pending":
            return await self._approval_pending_voice_response(
                route=route,
                capability_decision=capability_decision,
                message=message,
            )
        if route.route == "recover":
            result = await HighRiskVoiceActionService(self.app).prepare_recovery(
                {"session_id": route.target_session_id, "recovery_request": message}
            )
            return {
                "status": result.get("status", "recovery_prepared"),
                "result": result,
                "voice_route": route.as_dict(),
                "capability_decision": capability_decision.as_dict(),
            }
        return None

    async def _approval_pending_voice_response(
        self,
        *,
        route: VoiceThreadRoute,
        capability_decision: VoiceCapabilityDecision,
        message: str,
    ) -> dict[str, Any]:
        decision = _approval_decision_from_utterance(message)
        if not decision:
            return {
                "status": "clarification_required",
                "clarifying_question": "Should I approve or deny the pending approval?",
                "voice_route": route.as_dict(),
                "capability_decision": capability_decision.as_dict(),
            }
        prepared = await HighRiskVoiceActionService(self.app).prepare_approval_decision(
            {
                "session_id": route.target_session_id,
                "event_id": route.target_event_id,
                "decision": decision,
                "reason": message,
            }
        )
        if not prepared.get("requires_confirmation"):
            return {
                "status": str(prepared.get("status") or "approval_not_prepared"),
                "result": prepared,
                "voice_route": route.as_dict(),
                "capability_decision": capability_decision.as_dict(),
            }
        return {
            "status": "confirmation_required",
            "result": prepared,
            "voice_route": route.as_dict(),
            "capability_decision": capability_decision.as_dict(),
        }

    async def _resolve_voice_agent_chat_target(
        self,
        *,
        arguments: dict[str, Any],
        route: VoiceThreadRoute,
        project_root: Path,
        agent_routes: Any,
    ) -> VoiceAgentChatTarget:
        session_id = str(arguments.get("session_id") or "").strip() or None
        thread_mode_default = "current" if session_id else route.thread_mode
        thread_mode = (
            str(arguments.get("thread_mode") or thread_mode_default or "auto").strip().lower()
        )
        if thread_mode not in {"current", "new", "auto"}:
            thread_mode = "auto"
        routing_reason = str(arguments.get("routing_reason") or route.routing_reason).strip()
        requested_session_id = session_id
        if thread_mode == "new":
            requested_session_id = None
        session_factory = get_session_factory()
        async with session_factory() as db:
            session = None
            if requested_session_id:
                session = await agent_chat_sessions.load_session(
                    db,
                    requested_session_id,
                    project_root=project_root,
                    reject_scope_mismatch=True,
                )
            scoped_sessions: list[Any] = []
            if not requested_session_id and thread_mode in {"current", "auto"}:
                scoped_sessions = await agent_chat_sessions.list_scoped_sessions(db, project_root)
                session = agent_chat_sessions.latest_resume_candidate(scoped_sessions)
            if session is None:
                session = ChatSession()
                agent_chat_sessions.stamp_session_scope(session, project_root)
                db.add(session)
                await db.flush()
                await db.commit()
                session = await agent_chat_sessions.load_session(
                    db,
                    session.id,
                    project_root=project_root,
                )
            if session is None:
                raise RuntimeError("Failed to initialize voice chat session")
            needs_bootstrap = await agent_routes._needs_init_project_bootstrap(project_root, db)
            agent_name = "init-project-chat" if needs_bootstrap else "chat"
            resolved_thread_mode = (
                "new" if session.id != requested_session_id and thread_mode == "new" else "current"
            )
            if not requested_session_id and thread_mode == "auto":
                resolved_thread_mode = "current" if scoped_sessions else "new"
            elif not requested_session_id and thread_mode == "current" and not scoped_sessions:
                resolved_thread_mode = "new"
        return VoiceAgentChatTarget(
            session=session,
            resolved_thread_mode=resolved_thread_mode,
            routing_reason=routing_reason,
            agent_name=agent_name,
        )

    def _already_running_voice_handoff_response(
        self,
        *,
        target: VoiceAgentChatTarget,
        capability_decision: VoiceCapabilityDecision,
        project_root: Path,
        trigger: str,
    ) -> dict[str, Any]:
        runtime_metadata = runtime_settings_payload(project_root, include_capabilities=False)
        return {
            "session_id": target.session.id,
            "thread_mode": target.resolved_thread_mode,
            "routing_reason": target.routing_reason,
            "capability_decision": capability_decision.as_dict(),
            "completion_status": "running",
            "completion_digest": None,
            "completion_notification": {
                "mode": "already_running",
                "trigger": trigger,
            },
            "status": {
                "running": True,
                "runtime_sdk": runtime_metadata.get("sdk") or runtime_metadata.get("raw_sdk") or "",
                "provider": runtime_metadata.get("provider") or "",
            },
            "operator_message": "Builder is already working in Conversation.",
        }

    async def send_message(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from autonomous_agent_builder.embedded.server.routes import agent as agent_routes

        message = str(arguments.get("message") or "").strip()
        if not message:
            raise ValueError("message is required")

        active_session_id = str(arguments.get("session_id") or "").strip()
        status = await self.get_builder_status(active_session_id=active_session_id)
        route, capability_decision = self._voice_route_and_capability(
            arguments=arguments,
            message=message,
            active_session_id=active_session_id,
            status=status,
        )
        direct_response = await self._direct_voice_route_response(
            route=route,
            capability_decision=capability_decision,
            status=status,
            message=message,
        )
        if direct_response is not None:
            return direct_response

        project_root = Path(self.app.state.project_root)
        target = await self._resolve_voice_agent_chat_target(
            arguments=arguments,
            route=route,
            project_root=project_root,
            agent_routes=agent_routes,
        )
        session = target.session
        resolved_thread_mode = target.resolved_thread_mode
        routing_reason = target.routing_reason
        agent_name = target.agent_name
        hub: ChatSessionHub = self.app.state.chat_hub

        run_reserved = await hub.reserve_run(session.id)
        if not run_reserved:
            return self._already_running_voice_handoff_response(
                target=target,
                capability_decision=capability_decision,
                project_root=project_root,
                trigger="voice_handoff_deduped",
            )

        try:
            voice_operator_event = await agent_routes._append_chat_event(
                session.id,
                event_type="voice_operator_message",
                payload={
                    "content": message,
                    "source": "realtime_voice",
                    "speaker": "operator",
                    "target": "realtime_voice_ai",
                    "thread_mode": resolved_thread_mode,
                    "routing_reason": routing_reason,
                },
                status="completed",
            )
            await hub.publish(
                session.id,
                agent_chat_transcript.serialize_event(voice_operator_event).model_dump(mode="json"),
            )

            user_event = await agent_routes._append_chat_event(
                session.id,
                event_type="user_message",
                payload={
                    "content": message,
                    "source": "realtime_voice",
                    "speaker": "realtime_voice_ai",
                    "target": "sdk_backed_agent",
                    "participant_label": "Samantha",
                    "thread_mode": resolved_thread_mode,
                    "routing_reason": routing_reason,
                },
                status="completed",
                mirror_message=("user", message, 0, 0.0),
            )
            await hub.publish(
                session.id,
                agent_chat_transcript.serialize_event(user_event).model_dump(mode="json"),
            )

            voice_call_id = str(arguments.get("voice_call_id") or "").strip()
            if voice_call_id:
                bind_voice_call_session(self.app, voice_call_id, session.id)
            if active_session_id and active_session_id != session.id:
                await self.append_and_publish_voice_event(
                    active_session_id,
                    "voice_control_action",
                    {
                        "source": "realtime_voice",
                        "action": "bind_agent_session",
                        "session_id": session.id,
                        "route": f"/?session={session.id}&mode=chat",
                        "summary": "Opened Builder thread for Samantha handoff.",
                    },
                )

            task = asyncio.create_task(agent_routes._run_chat_turn(self.app, session.id, message))
            attached = await hub.attach_reserved_run(session.id, task)
            if not attached:
                task.cancel()
                await hub.release_run(session.id)
                return self._already_running_voice_handoff_response(
                    target=target,
                    capability_decision=capability_decision,
                    project_root=project_root,
                    trigger="voice_handoff_attach_deduped",
                )
        except Exception:
            await hub.release_run(session.id)
            raise
        self.completion_notifier.schedule(session.id, task)

        completion_status = "running"
        completion_digest: dict[str, Any] | None = None
        wait_for_completion = bool(arguments.get("wait_for_completion", True))
        completion_timeout = int(arguments.get("completion_timeout_seconds") or 120)
        completion_timeout = max(min(completion_timeout, 600), 1)
        if wait_for_completion:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=completion_timeout)
                completion_status = "completed"
                await self.digest_service.ensure_completion_digest(
                    self.app,
                    session.id,
                    trigger="synchronous_tool_wait",
                )
                completion_digest = await self.get_builder_status(prefer_latest_summary=True)
            except TimeoutError:
                completion_status = "still_running"

        return {
            "session_id": session.id,
            "thread_mode": resolved_thread_mode,
            "routing_reason": routing_reason,
            "capability_decision": capability_decision.as_dict(),
            "completion_status": completion_status,
            "completion_digest": completion_digest,
            "completion_notification": {
                "mode": "event_driven",
                "trigger": "agent_task_done_callback",
            },
            "status": agent_routes._initial_status(agent_name, project_root),
        }

    async def recover_blocked_agent_run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_root = Path(self.app.state.project_root)
        session_id = str(arguments.get("session_id") or "").strip()
        recovery_request = str(arguments.get("recovery_request") or "").strip()
        session_factory = get_session_factory()
        async with session_factory() as db:
            session = None
            if session_id:
                session = await agent_chat_sessions.load_session(
                    db,
                    session_id,
                    project_root=project_root,
                    reject_scope_mismatch=True,
                )
                if session is None:
                    raise ValueError("Agent-page chat session not found")
            else:
                scoped_sessions = await agent_chat_sessions.list_scoped_sessions(db, project_root)
                session = agent_chat_sessions.latest_resume_candidate(scoped_sessions)
            if session is None:
                raise ValueError("No recoverable Agent-page chat session found")

            latest_blocker = ""
            for event in sorted(session.events, key=lambda item: item.created_at, reverse=True):
                if event.event_type not in {"run_error", "tool_error", "run_status"}:
                    continue
                payload = event.payload_json or {}
                latest_blocker = str(
                    payload.get("content")
                    or payload.get("error")
                    or payload.get("stop_reason")
                    or payload.get("status")
                    or ""
                ).strip()
                if latest_blocker:
                    break

        recovery_message = (
            "Recover the blocked Agent-page run. Preserve existing builder state, "
            "use the normal Agent page lifecycle, do not bypass approvals, and leave "
            "visible evidence in the transcript."
        )
        if latest_blocker:
            recovery_message += f"\n\nLatest visible blocker: {latest_blocker}"
        if recovery_request:
            recovery_message += f"\n\nOperator recovery request: {recovery_request}"

        result = await self.send_message(
            {
                "session_id": session.id,
                "message": recovery_message,
                "thread_mode": "current",
                "routing_reason": "voice recovery fallback through Agent page",
                "bypass_voice_routing": True,
            }
        )
        return {
            "session_id": result["session_id"],
            "recovery_message": recovery_message,
            "status": result["status"],
        }

    async def answer_pending_question(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from autonomous_agent_builder.embedded.server.routes import agent as agent_routes

        session_id = str(arguments.get("session_id") or "").strip()
        event_id = str(arguments.get("event_id") or "").strip()
        answer = str(arguments.get("answer") or "").strip()
        if not session_id or not event_id or not answer:
            raise ValueError("session_id, event_id, and answer are required")

        session_factory = get_session_factory()
        async with session_factory() as db:
            event = await db.get(ChatEvent, event_id)
            if event is None or event.session_id != session_id:
                raise ValueError("Pending question not found")
            if event.event_type != "ask_user_question" or event.status != "pending":
                raise ValueError("Event is not a pending question")
            event_payload = event.payload_json or {}
            answer_value = _resolve_question_answer_value(answer, event_payload)
            question = str(event_payload.get("question") or "the pending question")
            updated_event = await agent_routes._update_request_event(
                db,
                event,
                payload_patch={
                    "answered": True,
                    "answer": answer,
                    "answer_value": answer_value,
                },
                status="answered",
                answer_event_type="ask_user_question_answer",
                answer_payload={"question": question, "answer_value": answer_value},
            )
        hub: ChatSessionHub = self.app.state.chat_hub
        await hub.publish(
            session_id,
            agent_chat_transcript.serialize_event(updated_event).model_dump(mode="json"),
        )
        if await hub.has_pending_answer(event_id):
            await hub.resolve_pending_answer(event_id, {"answer_value": answer_value})
        else:
            await agent_routes._continue_after_persisted_response(
                self.app,
                session_id,
                f'Operator answered pending question "{question}" by voice: {answer_value}',
            )
        return {
            "session_id": session_id,
            "event_id": event_id,
            "answered": True,
            "answer_value": answer_value,
        }

    async def answer_tool_approval(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from autonomous_agent_builder.embedded.server.routes import agent as agent_routes

        session_id = str(arguments.get("session_id") or "").strip()
        event_id = str(arguments.get("event_id") or "").strip()
        decision = str(arguments.get("decision") or "").strip().lower()
        reason = str(arguments.get("reason") or "").strip()
        if not session_id or not event_id or decision not in {"allow", "deny"}:
            raise ValueError("session_id, event_id, and decision allow/deny are required")

        session_factory = get_session_factory()
        async with session_factory() as db:
            event = await db.get(ChatEvent, event_id)
            if event is None or event.session_id != session_id:
                raise ValueError("Pending approval not found")
            if event.event_type != "tool_approval_request" or event.status != "pending":
                raise ValueError("Event is not a pending approval")
            updated_event = await agent_routes._update_request_event(
                db,
                event,
                payload_patch={"answered": True, "decision": decision, "reason": reason},
                status="answered",
                answer_event_type="tool_approval_answer",
                answer_payload={"decision": decision, "reason": reason},
            )
        hub: ChatSessionHub = self.app.state.chat_hub
        await hub.publish(
            session_id,
            agent_chat_transcript.serialize_event(updated_event).model_dump(mode="json"),
        )
        response_payload = {"decision": decision, "reason": reason, "updated_input": None}
        if await hub.has_pending_answer(event_id):
            await hub.resolve_pending_answer(event_id, response_payload)
        else:
            await agent_routes._continue_after_persisted_response(
                self.app,
                session_id,
                f'Operator confirmed pending approval by voice: "{decision}". Reason: {reason}',
            )
        return {"session_id": session_id, "event_id": event_id, "decision": decision}

    async def wait_for_user(self, arguments: dict[str, Any]) -> dict[str, Any]:
        reason = str(arguments.get("reason") or "waiting for operator").strip()
        session_factory = get_session_factory()
        async with session_factory() as db:
            result = await db.execute(
                select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(1)
            )
            session = result.scalar_one_or_none()
            if session is None:
                session = ChatSession()
                project_root = str(Path(self.app.state.project_root))
                session.repo_identity = project_root
                session.workspace_cwd = project_root
                db.add(session)
                await db.flush()
            db.add(
                ChatEvent(
                    session_id=session.id,
                    event_type="voice_wait",
                    status="completed",
                    payload_json={"reason": reason, "source": "realtime_voice"},
                )
            )
            await db.commit()
        return {"status": "waiting", "reason": reason}

    async def switch_runtime(self, arguments: dict[str, Any]) -> dict[str, Any]:
        sdk = _voice_runtime_sdk(arguments.get("sdk") or arguments.get("target_sdk"))
        voice_call_id = str(arguments.get("voice_call_id") or "").strip()
        project_root = Path(self.app.state.project_root)
        previous = runtime_settings_payload(project_root, include_capabilities=False)
        result = persist_runtime_settings(project_root, sdk=sdk)
        if not result.get("ok"):
            raise ValueError(str(result))
        repair = reconcile_runtime_project_state(project_root)
        result["runtime_repair"] = repair
        session = await self.latest_or_new_voice_session(call_id=voice_call_id)
        state_policy = "preserve_existing_tasks_runs_metrics_observability_memory_knowledge_backlog"
        await self.append_and_publish_voice_event(
            session.id,
            "runtime_settings_updated",
            {
                "previous_runtime_sdk": previous.get("sdk"),
                "selected_runtime_sdk": result.get("sdk"),
                "previous_provider": previous.get("provider"),
                "provider": result.get("provider"),
                "previous_model": previous.get("model"),
                "model": result.get("model"),
                "scope": "future_runs_only",
                "state_policy": state_policy,
                "runtime_repair": repair,
                "source": "realtime_voice",
                "voice_call_id": voice_call_id,
            },
        )
        status = (
            "runtime_unchanged" if previous.get("sdk") == result.get("sdk") else "runtime_switched"
        )
        return {
            "status": status,
            "previous_runtime_sdk": previous.get("sdk"),
            "selected_runtime_sdk": result.get("sdk"),
            "provider": result.get("provider"),
            "model": result.get("model"),
            "scope": "future_runs_only",
            "state_policy": state_policy,
            "runtime_repair": repair,
            "telemetry": result.get("telemetry"),
            "voice_digest": (
                f"Current runtime is now {_runtime_display_name(str(result.get('sdk') or ''))}. "
                "This applies to future runs only; existing tasks, run history, metrics, "
                "observability, memory, knowledge, and backlog attribution are preserved."
            ),
        }

    async def navigate_dashboard(self, arguments: dict[str, Any]) -> dict[str, Any]:
        target = str(arguments.get("target") or arguments.get("page") or "").strip()
        route = _dashboard_route_for_target(target)
        if not route:
            return {
                "status": "clarification_required",
                "message": (
                    "Which Builder page should I open? I can open Conversation, Voice, "
                    "Run trace, Board, Metrics, Observability, Backlog, Knowledge, "
                    "Memory, Inbox, Compare, or Settings."
                ),
                "supported_targets": sorted(_NAVIGATION_TARGETS),
            }
        voice_call_id = str(arguments.get("voice_call_id") or "").strip()
        session = await self.latest_or_new_voice_session(call_id=voice_call_id)
        event = await self.append_and_publish_voice_event(
            session.id,
            "voice_navigation_request",
            {
                "target": target,
                "route": route,
                "source": "realtime_voice",
                "voice_call_id": voice_call_id,
            },
        )
        return {
            "status": "navigation_requested",
            "target": target,
            "route": route,
            "session_id": session.id,
            "event_id": event.id,
        }

    async def open_run_trace(self, arguments: dict[str, Any]) -> dict[str, Any]:
        selection = str(arguments.get("selection") or arguments.get("query") or "").strip()
        run_kind = str(arguments.get("run_kind") or arguments.get("kind") or "").strip()
        run_id = str(arguments.get("run_id") or "").strip()
        task_id = str(arguments.get("task_id") or "").strip()
        intent = str(arguments.get("intent") or "").strip()
        analysis_request = str(arguments.get("analysis_request") or "").strip()
        if intent == "open_then_analyze" and not analysis_request:
            analysis_request = selection or "Analyze the loaded run trace."
        voice_call_id = str(arguments.get("voice_call_id") or "").strip()
        session = await self.latest_or_new_voice_session(call_id=voice_call_id)

        session_factory = get_session_factory()
        async with session_factory() as db:
            run, matched_on = await self._resolve_trace_run(
                db,
                selection=selection,
                run_kind=run_kind,
                run_id=run_id,
                task_id=task_id,
            )

        if run is None:
            return {
                "status": "no_matching_run_trace",
                "message": (
                    "I could not find a recorded task or agent run trace for that request. "
                    "Ask for the last task run, last optimization run, or the run for a blocked task."
                ),
                "session_id": session.id,
            }

        task = run.task
        route = f"/?mode=trace&task={run.task_id}&run={run.id}"
        event = await self.append_and_publish_voice_event(
            session.id,
            "voice_navigation_request",
            {
                "target": "run trace",
                "route": route,
                "action": "open_run_trace",
                "selection": selection,
                "run_kind": run_kind,
                "intent": intent or ("open_then_analyze" if analysis_request else "open_only"),
                "analysis_request": analysis_request,
                "matched_on": matched_on,
                "run": _agent_run_trace_snapshot(run),
                "task": _task_dispatch_snapshot(task) if task is not None else {"id": run.task_id},
                "source": "realtime_voice",
                "voice_call_id": voice_call_id,
            },
        )
        response: dict[str, Any] = {
            "status": "navigation_requested",
            "target": "run trace",
            "route": route,
            "session_id": session.id,
            "event_id": event.id,
            "run_id": run.id,
            "task_id": run.task_id,
            "agent_name": run.agent_name,
            "matched_on": matched_on,
            "analysis_request": analysis_request,
            "voice_digest": (
                f"Opening the run trace for {run.agent_name} on "
                f"{task.title if task is not None else 'the selected task'}."
            ),
        }
        if analysis_request:
            delegated_message = (
                "Analyze the run trace currently loaded on the Agent page. "
                f"Run id: {run.id}. Task id: {run.task_id}. "
                f"Agent: {run.agent_name}. "
                f"Task: {task.title if task is not None else 'unknown task'}. "
                f"Operator request: {analysis_request}. "
                "Use Builder-owned run trace, logs, metrics, and task evidence. "
                "Do not infer from memory alone."
            )
            response["delegation"] = await self.send_message(
                {
                    "message": delegated_message,
                    "session_id": session.id,
                    "thread_mode": "current",
                    "routing_reason": "Samantha loaded the requested run trace and delegated analysis to the SDK-backed Agent",
                    "wait_for_completion": True,
                    "completion_timeout_seconds": int(
                        arguments.get("completion_timeout_seconds") or 120
                    ),
                    "bypass_voice_routing": True,
                }
            )
        return response

    async def dispatch_board_task(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from autonomous_agent_builder.embedded.server.routes import tasks as task_routes

        task_id = str(arguments.get("task_id") or "").strip()
        selection = str(arguments.get("selection") or arguments.get("task") or "").strip()
        voice_call_id = str(arguments.get("voice_call_id") or "").strip()
        session = await self.latest_or_new_voice_session(call_id=voice_call_id)
        session_factory = get_session_factory()
        async with session_factory() as db:
            task = await self._resolve_dispatch_task(db, task_id=task_id, selection=selection)
            if task is None:
                return {
                    "status": "no_dispatchable_task",
                    "message": "No dispatchable Board task is available.",
                    "session_id": session.id,
                }
            task_status = _task_status_value(task)
            if not _task_is_dispatchable(task):
                return {
                    "status": "task_not_dispatchable",
                    "task": _task_dispatch_snapshot(task),
                    "message": (
                        "That task is not dispatchable from Realtime right now. "
                        "It may need recovery, approval, or a different Builder lane first."
                    ),
                    "session_id": session.id,
                }
            if not reserve_dispatch(task.id):
                event = await self.append_and_publish_voice_event(
                    session.id,
                    "voice_control_action",
                    {
                        "action": "dispatch_task",
                        "task": _task_dispatch_snapshot(task),
                        "status": "already_running",
                        "source": "realtime_voice",
                        "voice_call_id": voice_call_id,
                    },
                )
                return {
                    "status": "already_running",
                    "task_id": task.id,
                    "current_status": task_status,
                    "session_id": session.id,
                    "event_id": event.id,
                }
            snapshot = _task_dispatch_snapshot(task)

        asyncio.create_task(task_routes._run_dispatch(snapshot["id"]))
        event = await self.append_and_publish_voice_event(
            session.id,
            "voice_control_action",
            {
                "action": "dispatch_task",
                "task": snapshot,
                "status": "dispatched",
                "route": "/board",
                "source": "realtime_voice",
                "voice_call_id": voice_call_id,
            },
        )
        return {
            "status": "dispatched",
            "task_id": snapshot["id"],
            "task_title": snapshot["title"],
            "current_status": snapshot["status"],
            "route": "/board",
            "session_id": session.id,
            "event_id": event.id,
        }

    async def _resolve_dispatch_task(
        self,
        db: Any,
        *,
        task_id: str = "",
        selection: str = "",
    ) -> Task | None:
        query = (
            select(Task)
            .options(selectinload(Task.feature).selectinload(Feature.project))
            .order_by(Task.updated_at.desc(), Task.created_at.desc())
        )
        if task_id:
            result = await db.execute(query.where(Task.id == task_id))
            return result.scalar_one_or_none()
        result = await db.execute(query)
        tasks = list(result.scalars().all())
        normalized_selection = _normalize_match_text(selection)
        if normalized_selection:
            for task in tasks:
                if task.id and task.id.lower() in normalized_selection:
                    return task
            for task in tasks:
                title = _normalize_match_text(task.title)
                if title and title in normalized_selection:
                    return task
        dispatchable = [task for task in tasks if _task_is_dispatchable(task)]
        if not dispatchable:
            return None
        return sorted(dispatchable, key=_task_dispatch_sort_key)[0]

    async def _resolve_trace_run(
        self,
        db: Any,
        *,
        selection: str,
        run_kind: str,
        run_id: str,
        task_id: str,
    ) -> tuple[AgentRun | None, str]:
        base = select(AgentRun).options(selectinload(AgentRun.task).selectinload(Task.feature))
        if run_id:
            run = await db.get(
                AgentRun,
                run_id,
                options=[selectinload(AgentRun.task).selectinload(Task.feature)],
            )
            return run, "run_id" if run is not None else ""

        normalized = _normalize_match_text(" ".join([selection, run_kind]))
        if task_id:
            result = await db.execute(
                base.where(AgentRun.task_id == task_id)
                .order_by(AgentRun.started_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none(), "task_id"

        if "optimization" in normalized or "optimisation" in normalized:
            result = await db.execute(
                base.where(AgentRun.agent_name.ilike("%optimization%"))
                .order_by(AgentRun.started_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none(), "agent_name"

        if any(term in normalized for term in ("blocked", "blocker", "failed", "capability limit")):
            result = await db.execute(
                base.join(AgentRun.task)
                .where(
                    or_(
                        Task.status.in_(_BLOCKED_TRACE_TASK_STATUSES),
                        Task.blocked_reason.is_not(None),
                        Task.capability_limit_reason.is_not(None),
                    )
                )
                .order_by(AgentRun.started_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none(), "blocked_task"

        if normalized:
            result = await db.execute(
                base.join(AgentRun.task)
                .where(
                    or_(
                        Task.title.ilike(f"%{selection}%"),
                        AgentRun.agent_name.ilike(f"%{selection}%"),
                    )
                )
                .order_by(AgentRun.started_at.desc())
                .limit(1)
            )
            matched = result.scalar_one_or_none()
            if matched is not None:
                return matched, "selection"

        result = await db.execute(base.order_by(AgentRun.started_at.desc()).limit(1))
        return result.scalar_one_or_none(), "latest_run"

    async def append_and_publish_voice_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        status: str = "completed",
    ) -> ChatEvent:
        from autonomous_agent_builder.embedded.server.routes import agent as agent_routes

        event = await agent_routes._append_chat_event(
            session_id,
            event_type=event_type,
            payload=payload,
            status=status,
        )
        hub: ChatSessionHub = self.app.state.chat_hub
        await hub.publish(session_id, agent_chat_transcript.serialize_event(event).model_dump(mode="json"))
        return event

    async def resolve_voice_session(
        self,
        *,
        requested_session_id: str | None = None,
        fresh: bool = False,
        create_if_missing: bool = False,
    ) -> ChatSession | None:
        project_root = Path(self.app.state.project_root)
        session_factory = get_session_factory()
        async with session_factory() as db:
            session = None
            requested_session_id = str(requested_session_id or "").strip()
            if requested_session_id and not fresh:
                session = await agent_chat_sessions.load_session(
                    db,
                    requested_session_id,
                    project_root=project_root,
                    reject_scope_mismatch=True,
                )
            if session is None and create_if_missing:
                session = ChatSession()
                agent_chat_sessions.stamp_session_scope(session, project_root)
                db.add(session)
                await db.commit()
                await db.refresh(session)
            return session

    async def latest_or_new_voice_session(self, *, call_id: str = "") -> ChatSession:
        bound_session_id = _voice_call_session_id(self.app, call_id)
        if bound_session_id:
            session = await self.resolve_voice_session(
                requested_session_id=bound_session_id,
                create_if_missing=False,
            )
            if session is not None:
                return session
        session_factory = get_session_factory()
        async with session_factory() as db:
            result = await db.execute(
                select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(1)
            )
            session = result.scalar_one_or_none()
            if session is not None:
                return session
            session = ChatSession()
            project_root = str(Path(self.app.state.project_root))
            session.repo_identity = project_root
            session.workspace_cwd = project_root
            db.add(session)
            await db.commit()
            await db.refresh(session)
            return session

    async def load_voice_board_status(self, db: Any, *, status_prompt: str = "") -> dict[str, Any]:
        return await _load_voice_board_status(db, status_prompt=status_prompt)

    def voice_digest(
        self,
        *,
        active_run: bool,
        pending_count: int,
        board_status: dict[str, Any] | None = None,
        prefer_latest_summary: bool = False,
        latest_voice_summary: str = "",
        status_prompt: str = "",
    ) -> str:
        return build_voice_digest(
            active_run=active_run,
            pending_count=pending_count,
            board_status=board_status,
            prefer_latest_summary=prefer_latest_summary,
            latest_voice_summary=latest_voice_summary,
            status_prompt=status_prompt,
        )


class VoiceOperatorService:
    """Own Realtime tool execution and evidence recording."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.agent = AgentOperatorService(app)
        self.high_risk = HighRiskVoiceActionService(app)
        self.cost_ledger = VoiceCostLedger(app)

    def runtime_metadata(self) -> dict[str, Any]:
        project_root = Path(self.app.state.project_root)
        runtime = runtime_settings_payload(project_root, include_capabilities=False)
        return {
            "runtime_sdk": runtime.get("sdk") or runtime.get("raw_sdk") or "",
            "provider": runtime.get("provider") or "",
            "model": runtime.get("model") or "",
            "effort": runtime.get("effort") or runtime.get("preference") or "",
        }

    async def handle_tool_call(
        self,
        tool_call: dict[str, Any],
        *,
        call_id: str = "",
    ) -> dict[str, Any]:
        name = str(tool_call.get("name") or "")
        try:
            arguments = json.loads(str(tool_call.get("arguments") or "{}"))
        except json.JSONDecodeError:
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        active_session_id = _voice_call_session_id(self.app, call_id)
        if active_session_id and name not in {"get_builder_status", "get_builder_agent_update"}:
            arguments.setdefault("session_id", active_session_id)
        if call_id:
            arguments.setdefault("voice_call_id", call_id)
        if name == "delegate_to_builder_agent" and "wait_for_completion" not in arguments:
            arguments["wait_for_completion"] = False

        try:
            if name in {"get_builder_status", "get_builder_agent_update"}:
                return {
                    "ok": True,
                    "status": await self.agent.get_builder_status(
                        active_session_id=active_session_id,
                        status_prompt=str(
                            arguments.get("status_prompt") or arguments.get("message") or ""
                        ),
                    ),
                }
            if name in {"send_agent_message", "delegate_to_builder_agent"}:
                return {"ok": True, "result": await self.agent.send_message(arguments)}
            if name in {"navigate_dashboard", "open_dashboard_page"}:
                return {"ok": True, "result": await self.agent.navigate_dashboard(arguments)}
            if name in {"open_run_trace", "show_run_trace"}:
                return {"ok": True, "result": await self.agent.open_run_trace(arguments)}
            if name in {"dispatch_board_task", "dispatch_recovered_task"}:
                return {"ok": True, "result": await self.agent.dispatch_board_task(arguments)}
            if name in {"recover_board_task", "recover_task"}:
                return {"ok": True, "result": await self.high_risk.recover_board_task(arguments)}
            if name in {"answer_pending_question", "answer_pending_builder_question"}:
                return {"ok": True, "result": await self.agent.answer_pending_question(arguments)}
            if name in {"switch_builder_runtime", "set_builder_runtime"}:
                return {"ok": True, "result": await self.agent.switch_runtime(arguments)}
            if name == "recover_blocked_run":
                return {"ok": True, "result": await self.high_risk.prepare_recovery(arguments)}
            if name in {"prepare_approval_decision", "prepare_high_risk_decision"}:
                return {
                    "ok": True,
                    "result": await self.high_risk.prepare_approval_decision(arguments),
                }
            if name == "confirm_high_risk_action":
                return {"ok": True, "result": await self.high_risk.confirm_action(arguments)}
            if name == "wait_for_user":
                return {"ok": True, "result": await self.agent.wait_for_user(arguments)}
            return {"ok": False, "error": f"Unsupported voice tool: {name}"}
        except Exception as exc:  # noqa: BLE001 - tool errors must be returned to Realtime
            if (
                name in {"send_agent_message", "delegate_to_builder_agent"}
                and "already running" in str(exc).lower()
            ):
                return {
                    "ok": True,
                    "result": {
                        "session_id": str(arguments.get("session_id") or ""),
                        "completion_status": "running",
                        "completion_notification": {
                            "mode": "already_running",
                            "trigger": "voice_handoff_deduped",
                        },
                        "operator_message": "Builder is already working in Conversation.",
                    },
                }
            return {"ok": False, "error": str(exc)}

    async def record_tool_event(
        self,
        event_type: str,
        call_id: str,
        tool_call: dict[str, Any],
        *,
        output: dict[str, Any] | None = None,
    ) -> None:
        session = await self.agent.latest_or_new_voice_session(call_id=call_id)
        tool_name = str(tool_call.get("name") or "")
        payload: dict[str, Any] = {
            "voice_call_id": call_id,
            "tool_name": tool_name,
            "tool_call_id": str(tool_call.get("call_id") or ""),
            "source": "realtime_voice",
        }
        if event_type == "voice_tool_call":
            payload["arguments"] = tool_call.get("arguments") or "{}"
        if output is not None:
            payload["ok"] = bool(output.get("ok"))
            payload.update(_voice_tool_output_evidence(output))
            if output.get("ok") is False:
                payload["error"] = str(output.get("error") or "")

        session_factory = get_session_factory()
        async with session_factory() as db:
            db.add(
                ChatEvent(
                    session_id=session.id,
                    event_type=event_type,
                    status="completed" if payload.get("ok", True) else "failed",
                    payload_json=payload,
                )
            )
            await db.commit()

    async def record_context_budget(self, call_id: str, payload: dict[str, Any]) -> None:
        session = await self.agent.latest_or_new_voice_session(call_id=call_id)
        event_payload = {"voice_call_id": call_id, **payload}
        session_factory = get_session_factory()
        async with session_factory() as db:
            db.add(
                ChatEvent(
                    session_id=session.id,
                    event_type="context_budget",
                    status="completed",
                    payload_json=event_payload,
                )
            )
            await db.commit()

    async def record_realtime_usage(self, call_id: str, event: dict[str, Any]) -> None:
        await self.cost_ledger.record_usage(call_id, event)


