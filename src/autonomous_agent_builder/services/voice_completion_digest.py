"""Realtime voice completion digest service."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from autonomous_agent_builder.db.models import ChatEvent
from autonomous_agent_builder.db.session import get_session_factory
from autonomous_agent_builder.embedded.server import agent_chat_transcript
from autonomous_agent_builder.embedded.server.chat_state import ChatSessionHub


class AgentVoiceDigestService:
    """Create structured SDK-backed voice summaries for Realtime."""

    read_policy = "realtime_voice_reads_summary_only_not_tool_calls"

    def voice_summary_text(self, content: str, *, limit: int = 420) -> str:
        normalized = " ".join(str(content or "").split())
        if not normalized:
            return "Builder finished, but did not return a summary."
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: limit - 1].rstrip()}..."

    def build_digest_payload(
        self,
        *,
        session_id: str,
        assistant_event_id: str,
        content: str,
        voice_request_event_id: str = "",
        runtime_sdk: str = "",
        model: str = "",
        trigger: str = "agent_response",
    ) -> dict[str, Any]:
        spoken_summary = self.voice_summary_text(content)
        outcome = self._infer_outcome(content)
        payload = {
            "summary": spoken_summary,
            "spoken_summary": spoken_summary,
            "outcome": outcome,
            "blocker": self._infer_blocker(content, outcome),
            "next_decision": "",
            "recommended_next_action": self._recommended_next_action(outcome),
            "risk_level": "medium" if outcome in {"blocked", "failed"} else "low",
            "evidence_refs": [
                {
                    "kind": "agent_event",
                    "id": assistant_event_id,
                    "summary": "SDK-backed Agent final response",
                }
            ],
            "source_session_id": session_id,
            "assistant_event_id": assistant_event_id,
            "voice_request_event_id": voice_request_event_id,
            "runtime_sdk": runtime_sdk,
            "model": model,
            "cost_or_latency_note": "",
            "read_policy": self.read_policy,
            "source": "sdk_backed_agent",
            "target": "realtime_voice_ai",
            "digest_schema_version": "1",
            "completion_trigger": trigger,
        }
        if outcome in {"blocked", "failed"}:
            payload["next_decision"] = "Decide whether Builder should recover, retry, or pause."
        return payload

    async def ensure_completion_digest(
        self,
        app: Any,
        session_id: str,
        *,
        trigger: str,
    ) -> ChatEvent | None:
        session_factory = get_session_factory()
        async with session_factory() as db:
            event_result = await db.execute(
                select(ChatEvent)
                .where(ChatEvent.session_id == session_id)
                .order_by(ChatEvent.created_at.desc())
                .limit(80)
            )
            events = list(event_result.scalars().all())
            voice_request = next(
                (
                    event
                    for event in events
                    if event.event_type == "user_message"
                    and (event.payload_json or {}).get("speaker") == "realtime_voice_ai"
                    and (event.payload_json or {}).get("target") == "sdk_backed_agent"
                ),
                None,
            )
            if voice_request is None:
                return None
            pending_control = next(
                (
                    event
                    for event in events
                    if event.status == "pending"
                    and event.event_type in {"ask_user_question", "tool_approval_request"}
                ),
                None,
            )
            if pending_control is not None:
                return None
            existing = next(
                (
                    event
                    for event in events
                    if event.event_type == "voice_final_summary"
                    and str(event.status) in {"completed", "blocked", "failed", "pending"}
                ),
                None,
            )
            assistant = next(
                (
                    event
                    for event in events
                    if event.event_type == "assistant_message"
                    and str((event.payload_json or {}).get("content") or "").strip()
                ),
                None,
            )
            if existing is not None:
                payload = dict(existing.payload_json or {})
                if "spoken_summary" not in payload:
                    summary = str(payload.get("summary") or "")
                    payload.update(
                        self.build_digest_payload(
                            session_id=session_id,
                            assistant_event_id=str(payload.get("assistant_event_id") or ""),
                            content=summary,
                            voice_request_event_id=str(
                                payload.get("voice_request_event_id") or voice_request.id
                            ),
                            trigger=trigger,
                        )
                    )
                else:
                    payload.setdefault("completion_trigger", trigger)
                    payload.setdefault("summary", payload.get("spoken_summary") or "")
                    payload.setdefault("read_policy", self.read_policy)
                existing.payload_json = payload
                await db.commit()
                await db.refresh(existing)
                event = existing
            else:
                content = (
                    str((assistant.payload_json or {}).get("content") or "").strip()
                    if assistant
                    else ""
                )
                if not content:
                    content = "Builder finished. See the Agent page for the detailed result."
                assistant_event_id = assistant.id if assistant is not None else ""
                payload = self.build_digest_payload(
                    session_id=session_id,
                    assistant_event_id=assistant_event_id,
                    content=content,
                    voice_request_event_id=voice_request.id,
                    trigger=trigger,
                )
                event = ChatEvent(
                    session_id=session_id,
                    event_type="voice_final_summary",
                    status=self.event_status(payload["outcome"]),
                    payload_json=payload,
                )
                db.add(event)
                await db.commit()
                await db.refresh(event)

        hub: ChatSessionHub = app.state.chat_hub
        await hub.publish(
            session_id, agent_chat_transcript.serialize_event(event).model_dump(mode="json")
        )
        return event

    def _infer_outcome(self, content: str) -> str:
        normalized = str(content or "").lower()
        if any(term in normalized for term in ("provider limit", "blocked", "capability limit")):
            return "blocked"
        if any(term in normalized for term in ("failed", "error", "exception")):
            return "failed"
        if any(term in normalized for term in ("shipped", "merged", "published")):
            return "shipped"
        if "pending approval" in normalized:
            return "needs_approval"
        if "needs" in normalized and "operator" in normalized:
            return "needs_question"
        return "completed"

    def _infer_blocker(self, content: str, outcome: str) -> str:
        if outcome not in {"blocked", "failed"}:
            return ""
        return self.voice_summary_text(content, limit=220)

    def _recommended_next_action(self, outcome: str) -> str:
        if outcome == "needs_approval":
            return "Answer the pending approval."
        if outcome == "needs_question":
            return "Answer the pending Builder question."
        if outcome in {"blocked", "failed"}:
            return "Ask Builder to recover safely or inspect the evidence."
        return ""

    def event_status(self, outcome: str) -> str:
        if outcome in {"blocked", "failed"}:
            return outcome
        if outcome in {"needs_approval", "needs_question", "in_progress"}:
            return "pending"
        return "completed"

    def _event_status(self, outcome: str) -> str:
        return self.event_status(outcome)
