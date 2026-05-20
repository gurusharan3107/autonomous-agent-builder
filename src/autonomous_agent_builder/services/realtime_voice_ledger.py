"""Realtime voice usage and delegation ledger helpers."""

from __future__ import annotations

import os
from typing import Any, Protocol


class VoiceLedgerEvent(Protocol):
    id: str
    event_type: str
    status: str
    payload_json: dict[str, Any]


VOICE_LEDGER_EVENT_TYPES = (
    "user_message",
    "voice_action_prepared",
    "voice_digest",
    "voice_tool_call",
    "voice_tool_output",
    "voice_usage",
    "voice_wait",
)

REALTIME_RATE_ENV = {
    "input_text_tokens": "BUILDER_REALTIME_INPUT_TEXT_USD_PER_MILLION",
    "input_audio_tokens": "BUILDER_REALTIME_INPUT_AUDIO_USD_PER_MILLION",
    "output_text_tokens": "BUILDER_REALTIME_OUTPUT_TEXT_USD_PER_MILLION",
    "output_audio_tokens": "BUILDER_REALTIME_OUTPUT_AUDIO_USD_PER_MILLION",
    "cached_tokens": "BUILDER_REALTIME_CACHED_INPUT_USD_PER_MILLION",
}


def build_realtime_voice_ledger(events: list[VoiceLedgerEvent]) -> dict[str, Any]:
    """Build the dashboard-visible Realtime voice ledger from chat events."""

    usage = []
    prepared_actions = []
    delegated_messages = []
    digests = []
    tool_calls = []
    tool_outputs = []
    waits = []
    for event in events:
        payload = event.payload_json if isinstance(event.payload_json, dict) else {}
        if event.event_type == "voice_usage":
            usage.append({"event_id": event.id, "status": event.status, **payload})
        elif event.event_type == "voice_action_prepared":
            prepared_actions.append({"action_id": event.id, "status": event.status, **payload})
        elif event.event_type == "user_message" and payload.get("source") == "realtime_voice":
            delegated_messages.append({"event_id": event.id, "status": event.status, **payload})
        elif event.event_type == "voice_digest":
            digests.append({"event_id": event.id, "status": event.status, **payload})
        elif event.event_type == "voice_tool_call":
            tool_calls.append({"event_id": event.id, "status": event.status, **payload})
        elif event.event_type == "voice_tool_output":
            tool_outputs.append({"event_id": event.id, "status": event.status, **payload})
        elif event.event_type == "voice_wait":
            waits.append({"event_id": event.id, "status": event.status, **payload})

    response_count = len(usage)
    delegated_count = len(delegated_messages)
    confirmed_count = sum(
        1 for item in prepared_actions if item.get("prepared_status") == "executed"
    )
    failed_tool_outputs = sum(1 for item in tool_outputs if item.get("ok") is False)
    input_text_tokens = sum(int(item.get("text_input_tokens") or 0) for item in usage)
    input_audio_tokens = sum(int(item.get("audio_input_tokens") or 0) for item in usage)
    output_text_tokens = sum(int(item.get("text_output_tokens") or 0) for item in usage)
    output_audio_tokens = sum(int(item.get("audio_output_tokens") or 0) for item in usage)
    cached_tokens = sum(int(item.get("cached_input_tokens") or 0) for item in usage)
    useful_turns = sum(
        1 for item in usage if str(item.get("usefulness_category") or "").startswith("useful_")
    )
    wasted_turns = sum(
        1 for item in usage if str(item.get("usefulness_category") or "").startswith("wasted_")
    )
    usefulness_counts: dict[str, int] = {}
    for item in usage:
        category = str(item.get("usefulness_category") or "unclassified")
        usefulness_counts[category] = usefulness_counts.get(category, 0) + 1
    cost = _estimate_realtime_cost(
        input_text_tokens=input_text_tokens,
        input_audio_tokens=input_audio_tokens,
        output_text_tokens=output_text_tokens,
        output_audio_tokens=output_audio_tokens,
        cached_tokens=cached_tokens,
    )
    return {
        "usage": usage,
        "prepared_actions": prepared_actions,
        "delegated_messages": delegated_messages,
        "digests": digests,
        "tool_calls": tool_calls,
        "tool_outputs": tool_outputs,
        "waits": waits,
        "totals": {
            "responses": response_count,
            "input_tokens": sum(int(item.get("input_tokens") or 0) for item in usage),
            "output_tokens": sum(int(item.get("output_tokens") or 0) for item in usage),
            "total_tokens": sum(int(item.get("total_tokens") or 0) for item in usage),
            "input_text_tokens": input_text_tokens,
            "input_audio_tokens": input_audio_tokens,
            "output_text_tokens": output_text_tokens,
            "output_audio_tokens": output_audio_tokens,
            "cached_tokens": cached_tokens,
            "estimated_cost_usd": cost["estimated_cost_usd"],
            "cost_source": cost["cost_source"],
            "pricing_note": cost["pricing_note"],
            "delegated_messages": delegated_count,
            "voice_digests": len(digests),
            "tool_calls": len(tool_calls),
            "tool_outputs": len(tool_outputs),
            "failed_tool_outputs": failed_tool_outputs,
            "wait_events": len(waits),
            "prepared_actions": len(prepared_actions),
            "confirmed_actions": confirmed_count,
            "delegation_ratio": delegated_count / response_count if response_count else 0.0,
            "useful_turns": useful_turns,
            "wasted_turns": wasted_turns,
            "unclassified_turns": response_count - useful_turns - wasted_turns,
            "usefulness_counts": usefulness_counts,
            "usefulness_ratio": useful_turns / response_count if response_count else 0.0,
        },
    }


def _estimate_realtime_cost(
    *,
    input_text_tokens: int,
    input_audio_tokens: int,
    output_text_tokens: int,
    output_audio_tokens: int,
    cached_tokens: int,
) -> dict[str, Any]:
    rates = _configured_realtime_rates()
    if rates is None:
        return {
            "estimated_cost_usd": None,
            "cost_source": "usage_without_realtime_rate_card",
            "pricing_note": "Realtime usage captured; no local Realtime rate card is configured.",
        }

    usd = (
        input_text_tokens * rates["input_text_tokens"]
        + input_audio_tokens * rates["input_audio_tokens"]
        + output_text_tokens * rates["output_text_tokens"]
        + output_audio_tokens * rates["output_audio_tokens"]
        + cached_tokens * rates["cached_tokens"]
    ) / 1_000_000
    return {
        "estimated_cost_usd": round(usd, 6),
        "cost_source": "configured_realtime_rate_card",
        "pricing_note": "estimated from configured Realtime per-million-token rates",
    }


def _configured_realtime_rates() -> dict[str, float] | None:
    rates: dict[str, float] = {}
    for key, env_name in REALTIME_RATE_ENV.items():
        raw = os.environ.get(env_name)
        if raw is None or raw.strip() == "":
            return None
        try:
            value = float(raw)
        except ValueError:
            return None
        if value < 0:
            return None
        rates[key] = value
    return rates
