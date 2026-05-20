"""Supporting service classes for the Realtime voice operator lane.

Extracted from voice_operator.py to keep that module under the complexity
baseline.  All public names here are re-exported through voice_operator.py so
existing import paths continue to work.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from autonomous_agent_builder.db.models import ChatEvent, ChatSession
from autonomous_agent_builder.services.voice_completion_digest import AgentVoiceDigestService
from autonomous_agent_builder.services.voice_operator_interaction import (
    compact_json_text as _compact_json_text,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    provider_limit_reason_is_current as _provider_limit_reason_is_current,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    question_options as _question_options,
)
from autonomous_agent_builder.services.voice_operator_interaction import (
    recommended_option_index as _recommended_option_index,
)
from autonomous_agent_builder.services.voice_thread_routing import (
    VoiceThreadRoute,
)

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class VoiceCapabilityDecision:
    """Structured Realtime-to-SDK capability agreement for one operator turn."""

    decision: str
    voice_action: str
    builder_route: str
    can_execute_now: bool
    blocker: str = ""
    operator_message: str = ""
    evidence_refs: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "voice_action": self.voice_action,
            "builder_route": self.builder_route,
            "can_execute_now": self.can_execute_now,
            "blocker": self.blocker,
            "operator_message": self.operator_message,
            "evidence_refs": list(self.evidence_refs),
        }


class VoiceCapabilityDecisionService:
    """Decide whether voice may answer, delegate, block, or reject a request."""

    _UNSUPPORTED_PHRASES = (
        "book a flight",
        "book flight",
        "buy a ticket",
        "calendar invite",
        "order food",
        "play music",
        "restaurant reservation",
        "send an email",
        "send email",
        "stock price",
        "weather forecast",
    )
    _IMPLEMENTATION_TERMS = (
        "build",
        "change",
        "code",
        "create",
        "dispatch",
        "fix",
        "generate",
        "implement",
        "modify",
        "ship",
        "update",
    )
    _VERIFICATION_TERMS = (
        "acceptance",
        "browser",
        "test",
        "validate",
        "verification",
        "verify",
    )
    _DIAGNOSIS_TERMS = (
        "analyze",
        "diagnose",
        "failure",
        "logs",
        "metrics",
        "observability",
        "root cause",
    )

    def decide(
        self,
        *,
        operator_utterance: str,
        route: VoiceThreadRoute,
        builder_status: dict[str, Any],
    ) -> VoiceCapabilityDecision:
        normalized = " ".join(operator_utterance.lower().split())
        direct = self._direct_decision(route, builder_status=builder_status)
        if direct is not None:
            return direct
        if self._looks_unsupported(normalized):
            return VoiceCapabilityDecision(
                decision="unsupported",
                voice_action="report_unsupported",
                builder_route="none",
                can_execute_now=False,
                blocker="unsupported_operator_request",
                operator_message=(
                    "Neither Realtime voice nor Builder can do that right now. "
                    "I can help with Builder status, approvals, recovery, and "
                    "software delivery work."
                ),
                evidence_refs=("voice_capability.unsupported_phrase",),
            )

        runtime_blocker = self._runtime_blocker(builder_status)
        if runtime_blocker:
            return VoiceCapabilityDecision(
                decision="blocked",
                voice_action="report_blocker",
                builder_route="agent_chat",
                can_execute_now=False,
                blocker=runtime_blocker,
                operator_message=(
                    "Builder cannot delegate that yet because the selected "
                    f"runtime is blocked: {runtime_blocker}. Ask me for current "
                    "status, switch runtime, or recover the blocked Builder work."
                ),
                evidence_refs=("current_runtime",),
            )

        provider_blocker = self._provider_limit_blocker(builder_status)
        if provider_blocker:
            return VoiceCapabilityDecision(
                decision="blocked",
                voice_action="report_blocker",
                builder_route="agent_chat",
                can_execute_now=False,
                blocker=provider_blocker,
                operator_message=(
                    "Builder cannot delegate that yet because the SDK recently "
                    f"hit a provider limit: {provider_blocker}. Ask me for "
                    "current status, switch runtime, or recover the blocked work."
                ),
                evidence_refs=("board_status.provider_limit_runs",),
            )

        builder_route = self._builder_route(normalized)
        return VoiceCapabilityDecision(
            decision="lifecycle_dispatch" if builder_route != "agent_chat" else "sdk_chat",
            voice_action="delegate",
            builder_route=builder_route,
            can_execute_now=True,
            operator_message="I will ask the Builder Agent to handle that.",
            evidence_refs=("voice_thread_route",),
        )

    def _direct_decision(
        self,
        route: VoiceThreadRoute,
        *,
        builder_status: dict[str, Any],
    ) -> VoiceCapabilityDecision | None:
        if route.route == "status":
            return VoiceCapabilityDecision(
                decision="voice_direct",
                voice_action="answer",
                builder_route="none",
                can_execute_now=True,
                operator_message="Realtime can answer from the compact Builder status.",
                evidence_refs=("builder_status",),
            )
        if route.route == "clarify":
            return VoiceCapabilityDecision(
                decision="requires_question",
                voice_action="ask_clarification",
                builder_route="none",
                can_execute_now=False,
                operator_message=route.clarifying_question,
                evidence_refs=("pending_operator_items",),
            )
        if route.route == "answer_pending":
            return VoiceCapabilityDecision(
                decision="requires_question",
                voice_action="answer",
                builder_route="none",
                can_execute_now=True,
                operator_message="Realtime can answer the pending Builder question.",
                evidence_refs=("pending_operator_items",),
            )
        if route.route == "approval_pending":
            return VoiceCapabilityDecision(
                decision="requires_approval",
                voice_action="ask_confirmation",
                builder_route="approval",
                can_execute_now=True,
                operator_message="Realtime must prepare the approval decision first.",
                evidence_refs=("pending_operator_items",),
            )
        if route.route == "recover":
            board = builder_status.get("board_status")
            blocked_tasks = []
            provider_limit_runs = []
            if isinstance(board, dict):
                blocked_tasks = list(board.get("blocked_tasks") or [])
                provider_limit_runs = list(board.get("provider_limit_runs") or [])
            if not blocked_tasks and not provider_limit_runs:
                return VoiceCapabilityDecision(
                    decision="not_recoverable",
                    voice_action="report_state",
                    builder_route="recovery",
                    can_execute_now=False,
                    blocker=(
                        "No blocked, failed, or capability-limited Board task is available "
                        "for recovery."
                    ),
                    operator_message=(
                        "I do not see a recoverable Board task. Open the relevant run trace "
                        "or ask Builder to diagnose the failure before attempting recovery."
                    ),
                    evidence_refs=(
                        "board_status.blocked_tasks",
                        "board_status.provider_limit_runs",
                    ),
                )
            return VoiceCapabilityDecision(
                decision="requires_approval",
                voice_action="ask_confirmation",
                builder_route="recovery",
                can_execute_now=True,
                operator_message="Realtime must prepare safe recovery before resuming work.",
                evidence_refs=("board_status.blocked_tasks",),
            )
        return None

    def _looks_unsupported(self, normalized: str) -> bool:
        return any(phrase in normalized for phrase in self._UNSUPPORTED_PHRASES)

    def _runtime_blocker(self, builder_status: dict[str, Any]) -> str:
        runtime = builder_status.get("current_runtime")
        if not isinstance(runtime, dict):
            return "current runtime status is unavailable"
        errors = runtime.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                return str(first.get("message") or first.get("code") or "runtime error")
            return str(first)
        if runtime.get("ok") is False:
            return "runtime settings are not valid"
        return ""

    def _provider_limit_blocker(self, builder_status: dict[str, Any]) -> str:
        board = builder_status.get("board_status")
        if not isinstance(board, dict):
            return ""
        runs = list(board.get("provider_limit_runs") or [])
        if runs:
            latest = runs[0]
            if isinstance(latest, dict) and bool(latest.get("provider_limit_current")):
                title = str(latest.get("task_title") or "a Builder task")
                provider = str(latest.get("provider") or "the selected provider")
                return f"{title} stopped on {provider} with provider_limit"
        for task in board.get("blocked_tasks") or []:
            if not isinstance(task, dict):
                continue
            reason = str(task.get("reason") or "")
            all_reasons = " ".join(
                str(task.get(key) or "")
                for key in ("reason", "blocked_reason", "capability_limit_reason")
            )
            if "provider_limit" in all_reasons or "provider limit" in all_reasons.lower():
                if not _provider_limit_reason_is_current(all_reasons):
                    continue
                title = str(task.get("title") or "a Builder task")
                return f"{title} is blocked by {reason}"
        return ""

    def _builder_route(self, normalized: str) -> str:
        if any(term in normalized for term in self._VERIFICATION_TERMS):
            if "feature" in normalized:
                return "feature_verifier"
            return "build_verifier"
        if any(term in normalized for term in self._IMPLEMENTATION_TERMS):
            if any(term in normalized for term in ("sprint", "dispatch", "ship")):
                return "sprint_dispatch"
            return "code_gen"
        if any(term in normalized for term in self._DIAGNOSIS_TERMS):
            return "agent_chat"
        return "agent_chat"


class PendingOperatorItemService:
    """Own pending question and approval retrieval for voice routing."""

    _PENDING_EVENT_TYPES = {
        "ask_user_question",
        "tool_approval_request",
        "voice_action_prepared",
    }
    _PENDING_APPROVAL_TYPES = {"tool_approval_request", "voice_action_prepared"}

    def pending_operator_item(self, event: ChatEvent) -> dict[str, Any]:
        payload = event.payload_json or {}
        item = {
            "event_id": event.id,
            "type": event.event_type,
            "summary": str(payload.get("summary") or ""),
            "question": str(payload.get("question") or ""),
            "tool_name": str(payload.get("tool_name") or ""),
            "description": str(payload.get("description") or ""),
        }
        if event.event_type == "ask_user_question":
            options = _question_options(payload)
            recommended_index = _recommended_option_index(payload, len(options))
            item["options"] = options
            item["recommended_index"] = recommended_index
            if 0 <= recommended_index < len(options):
                item["recommended_option"] = options[recommended_index]
        if event.event_type == "tool_approval_request":
            item["decision_prompt"] = (
                "Ask the operator whether to approve or deny this pending tool request."
            )
            item["tool_input_summary"] = _compact_json_text(payload.get("tool_input"))
        if event.event_type == "voice_action_prepared":
            item["summary"] = str(
                payload.get("summary")
                or payload.get("consequence_summary")
                or "Prepared voice action is waiting for confirmation."
            )
            item["action_kind"] = str(payload.get("action_kind") or payload.get("kind") or "")
            item["consequence_summary"] = str(payload.get("consequence_summary") or "")
            item["confirmation_phrase"] = str(payload.get("confirmation_phrase") or "")
            item["decision_prompt"] = (
                "Ask the operator whether to confirm or cancel this prepared voice action."
            )
        return item

    def pending_operator_items(self, events: list[ChatEvent]) -> list[dict[str, Any]]:
        return [
            self.pending_operator_item(event)
            for event in events
            if event.status == "pending" and event.event_type in self._PENDING_EVENT_TYPES
        ]

    def pending_approval_items(self, events: list[ChatEvent]) -> list[dict[str, Any]]:
        return [
            self.pending_operator_item(event)
            for event in events
            if event.status == "pending" and event.event_type in self._PENDING_APPROVAL_TYPES
        ]


class VoiceCompletionNotifier:
    """Own event-driven completion notification for voice delegations."""

    def __init__(self, app: Any, digest_service: AgentVoiceDigestService | None = None) -> None:
        self.app = app
        self.digest_service = digest_service or AgentVoiceDigestService()

    def schedule(self, session_id: str, task: asyncio.Task[Any]) -> None:
        def _done(completed: asyncio.Task[Any]) -> None:
            asyncio.create_task(self._record_completion(session_id, completed))

        task.add_done_callback(_done)

    async def _record_completion(self, session_id: str, task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            return
        error = task.exception()
        event = await self.digest_service.ensure_completion_digest(
            self.app,
            session_id,
            trigger="agent_task_done_callback",
        )
        if event is None:
            return
        payload = {
            "voice_final_summary_event_id": event.id,
            "source": "voice_completion_notifier",
            "trigger": "agent_task_done_callback",
            "status": "failed" if error else "completed",
        }
        if error:
            payload["error"] = str(error)
        # Lazy import to avoid circular dependency with voice_operator.py
        from autonomous_agent_builder.services.voice_operator import AgentOperatorService

        await AgentOperatorService(self.app).append_and_publish_voice_event(
            session_id,
            "voice_completion_notification",
            payload,
            status="failed" if error else "completed",
        )


@dataclass(frozen=True)
class VoiceAgentChatTarget:
    session: ChatSession
    resolved_thread_mode: str
    routing_reason: str
    agent_name: str
