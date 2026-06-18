"""Voice usage cost accounting extracted from voice_operator.py."""

from __future__ import annotations

from typing import Any

from autonomous_agent_builder.db.models import ChatEvent
from autonomous_agent_builder.db.session import get_session_factory
from autonomous_agent_builder.services.realtime_voice_policy import DEFAULT_REALTIME_VOICE_POLICY


class VoiceCostLedger:
    """Own Realtime usage accounting and usefulness classification."""

    def __init__(self, app: Any | None = None) -> None:
        self.app = app

    async def record_usage(self, call_id: str, event: dict[str, Any]) -> None:
        if self.app is None:
            raise RuntimeError("VoiceCostLedger.record_usage requires an app")
        payload = self.usage_payload(call_id, event)
        if payload is None:
            return
        from autonomous_agent_builder.services.voice_operator import (
            AgentOperatorService,  # noqa: PLC0415
        )
        session = await AgentOperatorService(self.app).latest_or_new_voice_session(call_id=call_id)
        session_factory = get_session_factory()
        async with session_factory() as db:
            db.add(
                ChatEvent(
                    session_id=session.id,
                    event_type="voice_usage",
                    status="completed",
                    payload_json=payload,
                )
            )
            await db.commit()

    def usage_payload(self, call_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
        _raw_response = event.get("response")
        response: dict[str, Any] = _raw_response if isinstance(_raw_response, dict) else {}
        usage = response.get("usage") if response else event.get("usage")
        if str(event.get("type") or "") != "response.done" or not isinstance(usage, dict):
            return None
        input_details = usage.get("input_token_details")
        output_details = usage.get("output_token_details")
        input_details = input_details if isinstance(input_details, dict) else {}
        output_details = output_details if isinstance(output_details, dict) else {}
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        usefulness = self.classify_response_usefulness(response, usage)
        return {
            "voice_call_id": call_id,
            "model": str(response.get("model") or DEFAULT_REALTIME_VOICE_POLICY.model),
            "response_id": str(response.get("id") or ""),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": int(usage.get("total_tokens") or input_tokens + output_tokens),
            "cached_input_tokens": int(input_details.get("cached_tokens") or 0),
            "audio_input_tokens": int(input_details.get("audio_tokens") or 0),
            "text_input_tokens": int(input_details.get("text_tokens") or 0),
            "audio_output_tokens": int(output_details.get("audio_tokens") or 0),
            "text_output_tokens": int(output_details.get("text_tokens") or 0),
            "estimated_cost_usd": None,
            "cost_source": "usage_without_realtime_rate_card",
            "pricing_note": "Realtime usage captured; local rate card is not authoritative.",
            "source": "realtime_response_done",
            **usefulness,
        }

    def classify_response_usefulness(
        self,
        response: dict[str, Any],
        usage: dict[str, Any],
    ) -> dict[str, str]:
        status = str(response.get("status") or "completed").lower()
        if status in {"failed", "cancelled", "incomplete"}:
            return {
                "usefulness_category": "wasted_failed_response",
                "usefulness_reason": f"response status was {status}",
            }
        output = response.get("output")
        output_items = output if isinstance(output, list) else []
        if any(
            isinstance(item, dict) and item.get("type") == "function_call" for item in output_items
        ):
            return {
                "usefulness_category": "useful_tool_call",
                "usefulness_reason": "response executed a Builder-owned tool",
            }
        if int(usage.get("output_tokens") or 0) > 0 or output_items:
            return {
                "usefulness_category": "useful_voice_response",
                "usefulness_reason": "response produced a voice or text answer",
            }
        return {
            "usefulness_category": "wasted_empty_response",
            "usefulness_reason": "response completed without output or tool use",
        }
