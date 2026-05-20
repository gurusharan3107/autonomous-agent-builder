"""Deterministic routing for Realtime voice operator utterances."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VoiceThreadRoute:
    """Deterministic routing decision for an operator utterance."""

    route: str
    thread_mode: str
    confidence: float
    routing_reason: str
    clarifying_question: str = ""
    target_session_id: str = ""
    target_event_id: str = ""
    high_impact: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "thread_mode": self.thread_mode,
            "confidence": self.confidence,
            "routing_reason": self.routing_reason,
            "clarifying_question": self.clarifying_question,
            "target_session_id": self.target_session_id,
            "target_event_id": self.target_event_id,
            "high_impact": self.high_impact,
        }


class VoiceThreadRouter:
    """Route voice utterances before they reach the SDK-backed Agent."""

    _ANSWER_PREFIXES = (
        "yes",
        "no",
        "use ",
        "choose ",
        "go with ",
        "select ",
        "pick ",
        "the ",
        "all ",
        "recommended",
    )
    _APPROVAL_WORDS = (
        "approve",
        "allow",
        "deny",
        "reject",
        "decline",
        "go ahead",
        "confirmed",
        "confirm",
    )
    _SHORT_APPROVAL_RESPONSES = {"yes", "yep", "yeah", "okay", "ok", "no", "nope"}
    _STATUS_PHRASES = (
        "status",
        "where are we",
        "what is builder doing",
        "what's builder doing",
        "progress",
        "update",
    )
    _STATUS_INTENT_PHRASES = (
        "check",
        "show",
        "tell me",
        "how many",
        "what is",
        "what are",
        "where are",
        "list",
        "count",
    )
    _STATUS_SCOPE_TERMS = (
        "approval",
        "approvals",
        "backlog",
        "blocked",
        "blocker",
        "board",
        "pending",
        "prepared action",
        "provider limit",
        "sdk limit",
        "sprint",
        "sprints",
        "task status",
        "tasks",
    )
    _STATUS_DELEGATION_TERMS = (
        "diagnose",
        "diagnosis",
        "error",
        "failed",
        "failure",
        "generated app",
        "logs",
        "metrics",
        "observability",
        "repo",
        "why",
    )
    _NEW_TOPIC_PHRASES = (
        "new topic",
        "separate",
        "different task",
        "another task",
        "start a new",
        "product correction",
        "broad investigation",
    )
    _RECOVERY_PHRASES = (
        "recover",
        "recovery",
        "resume blocked",
        "retry blocked",
        "unblock",
    )

    def route(
        self,
        *,
        operator_utterance: str,
        latest_session_id: str,
        active_run: bool,
        pending_operator_items: list[dict[str, Any]],
        latest_voice_summary: dict[str, Any] | None = None,
    ) -> VoiceThreadRoute:
        utterance = operator_utterance.strip()
        normalized = " ".join(utterance.lower().split())
        question_items = [
            item for item in pending_operator_items if item.get("type") == "ask_user_question"
        ]
        approval_items = [
            item for item in pending_operator_items if item.get("type") == "tool_approval_request"
        ]

        if self._looks_like_status(normalized):
            return VoiceThreadRoute(
                route="status",
                thread_mode="current",
                confidence=0.95,
                routing_reason="operator asked for Builder status",
                target_session_id=latest_session_id,
            )

        if self._looks_like_approval(normalized) or (
            approval_items and not question_items and normalized in self._SHORT_APPROVAL_RESPONSES
        ):
            if len(approval_items) == 1:
                return VoiceThreadRoute(
                    route="approval_pending",
                    thread_mode="current",
                    confidence=0.9,
                    routing_reason="operator approval maps to one pending approval",
                    target_session_id=latest_session_id,
                    target_event_id=str(approval_items[0].get("event_id") or ""),
                    high_impact=True,
                )
            if len(approval_items) > 1:
                return VoiceThreadRoute(
                    route="clarify",
                    thread_mode="current",
                    confidence=0.9,
                    routing_reason="multiple pending approvals match the utterance",
                    clarifying_question="Which pending approval should I use?",
                    target_session_id=latest_session_id,
                    high_impact=True,
                )

        if self._looks_like_answer(normalized):
            if len(question_items) == 1:
                return VoiceThreadRoute(
                    route="answer_pending",
                    thread_mode="current",
                    confidence=0.9,
                    routing_reason="operator answer maps to one pending question",
                    target_session_id=latest_session_id,
                    target_event_id=str(question_items[0].get("event_id") or ""),
                )
            if len(question_items) > 1:
                return VoiceThreadRoute(
                    route="clarify",
                    thread_mode="current",
                    confidence=0.9,
                    routing_reason="multiple pending questions match the utterance",
                    clarifying_question="Which pending question should I answer?",
                    target_session_id=latest_session_id,
                )

        if self._looks_like_new_topic(normalized):
            return VoiceThreadRoute(
                route="new",
                thread_mode="new",
                confidence=0.8,
                routing_reason="operator started a distinct topic",
                target_session_id="",
            )

        if self._looks_like_recovery(normalized):
            return VoiceThreadRoute(
                route="recover",
                thread_mode="current",
                confidence=0.86,
                routing_reason="operator requested recovery of blocked Builder work",
                target_session_id=latest_session_id,
                high_impact=True,
            )

        if active_run and len(normalized.split()) <= 16:
            return VoiceThreadRoute(
                route="current",
                thread_mode="current",
                confidence=0.75,
                routing_reason="short follow-up while Builder is active",
                target_session_id=latest_session_id,
            )

        return VoiceThreadRoute(
            route="new",
            thread_mode="new",
            confidence=0.65,
            routing_reason="default to a fresh Agent thread for substantial work",
            target_session_id="",
        )

    def _looks_like_answer(self, normalized: str) -> bool:
        if not normalized:
            return False
        if len(normalized.split()) > 18:
            return False
        return normalized.startswith(self._ANSWER_PREFIXES) or normalized in {
            "all of them",
            "both",
            "the first one",
            "the second one",
            "the third one",
        }

    def _looks_like_approval(self, normalized: str) -> bool:
        return any(word in normalized for word in self._APPROVAL_WORDS)

    def _looks_like_status(self, normalized: str) -> bool:
        if any(term in normalized for term in self._STATUS_DELEGATION_TERMS):
            return False
        if any(phrase in normalized for phrase in self._STATUS_PHRASES):
            return True
        if not any(term in normalized for term in self._STATUS_SCOPE_TERMS):
            return False
        return any(phrase in normalized for phrase in self._STATUS_INTENT_PHRASES)

    def _looks_like_new_topic(self, normalized: str) -> bool:
        return any(phrase in normalized for phrase in self._NEW_TOPIC_PHRASES)

    def _looks_like_recovery(self, normalized: str) -> bool:
        return any(phrase in normalized for phrase in self._RECOVERY_PHRASES)
