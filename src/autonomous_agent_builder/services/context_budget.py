"""Builder-owned context budget evidence helpers."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any


def estimate_context_tokens(value: Any) -> int:
    """Return a deterministic local token estimate without storing raw content."""

    if value in (None, "", [], {}):
        return 0
    if isinstance(value, str):
        text = " ".join(value.split())
    else:
        try:
            text = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
        except (TypeError, ValueError):
            text = str(value)
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def context_digest(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        text = " ".join(value.split())
    else:
        try:
            text = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
        except (TypeError, ValueError):
            text = str(value)
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def context_component(name: str, value: Any, *, signal: str, source: str = "") -> dict[str, Any]:
    tokens = estimate_context_tokens(value)
    return {
        "name": name,
        "estimated_tokens": tokens,
        "signal_category": signal,
        "source": source,
        "digest": context_digest(value),
        "present": tokens > 0,
    }


def build_agent_context_budget(
    *,
    agent_name: str,
    prompt: str,
    user_message: str,
    recent_context: str,
    documentation_context: dict[str, Any] | None,
    observability_context: str,
    runtime_metadata: dict[str, Any],
    resume_session: str | None,
    specialist_active: bool,
) -> dict[str, Any]:
    components = [
        context_component(
            "user_prompt", user_message, signal="operator_intent", source="agent_page"
        ),
        context_component(
            "recent_transcript",
            recent_context,
            signal="conditional_reference_context" if recent_context else "not_sent",
            source="chat_events",
        ),
        context_component(
            "documentation_pack",
            documentation_context or {},
            signal="specialist_retrieval" if documentation_context else "not_sent",
            source="builder_knowledge",
        ),
        context_component(
            "observability_pack",
            observability_context,
            signal="bounded_builder_evidence" if observability_context else "not_sent",
            source="dashboard_observability_summary",
        ),
        context_component("final_prompt", prompt, signal="handoff_payload", source="agent_runtime"),
    ]
    return _budget_payload(
        lane="sdk_agent",
        stage="agent_prompt_assembly",
        components=components,
        runtime_metadata=runtime_metadata,
        correlation_id=f"agent:{agent_name}",
        extra={
            "agent_name": agent_name,
            "resume_session": bool(resume_session),
            "resume_session_id": str(resume_session or ""),
            "specialist_active": specialist_active,
        },
    )


def build_realtime_session_context_budget(
    *,
    call_id: str,
    instructions: str,
    tools: list[dict[str, Any]],
    runtime_metadata: dict[str, Any],
) -> dict[str, Any]:
    components = [
        context_component(
            "voice_instructions",
            instructions,
            signal="operator_contract",
            source="realtime_session_update",
        ),
        context_component(
            "tool_definitions",
            tools,
            signal="builder_tool_contract",
            source="realtime_session_update",
        ),
    ]
    return _budget_payload(
        lane="realtime_voice",
        stage="realtime_session_update",
        components=components,
        runtime_metadata=runtime_metadata,
        correlation_id=call_id,
        extra={"voice_call_id": call_id},
    )


def build_realtime_tool_context_budget(
    *,
    call_id: str,
    tool_call: dict[str, Any],
    output: dict[str, Any] | None,
    runtime_metadata: dict[str, Any],
) -> dict[str, Any]:
    tool_name = str(tool_call.get("name") or "")
    output_ok = bool(output.get("ok")) if isinstance(output, dict) and "ok" in output else None
    result_signal = (
        "useful_tool_result"
        if output_ok is True
        else "tool_result_error"
        if output_ok is False
        else "pending_tool_result"
    )
    components = [
        context_component(
            "tool_arguments",
            tool_call.get("arguments") or "{}",
            signal="operator_tool_intent",
            source=tool_name,
        ),
        context_component(
            "tool_output",
            output or {},
            signal=result_signal,
            source=tool_name,
        ),
    ]
    return _budget_payload(
        lane="realtime_voice",
        stage="realtime_tool_exchange",
        components=components,
        runtime_metadata=runtime_metadata,
        correlation_id=str(tool_call.get("call_id") or call_id),
        extra={
            "voice_call_id": call_id,
            "tool_name": tool_name,
            "tool_call_id": str(tool_call.get("call_id") or ""),
            "ok": output_ok,
        },
    )


def summarize_context_budgets(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate context_budget event payloads for dashboard and CLI surfaces."""

    lane_counts: Counter[str] = Counter()
    stage_counts: Counter[str] = Counter()
    signal_counts: Counter[str] = Counter()
    component_totals: dict[str, int] = {}
    total_estimated_tokens = 0
    latest: dict[str, Any] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        lane = str(event.get("lane") or "unknown")
        stage = str(event.get("stage") or "unknown")
        lane_counts[lane] += 1
        stage_counts[stage] += 1
        total_estimated_tokens += int(event.get("total_estimated_tokens") or 0)
        latest = event
        for component in event.get("component_estimates") or []:
            if not isinstance(component, dict):
                continue
            name = str(component.get("name") or "unknown")
            signal = str(component.get("signal_category") or "unknown")
            tokens = int(component.get("estimated_tokens") or 0)
            signal_counts[signal] += 1
            component_totals[name] = component_totals.get(name, 0) + tokens
    sorted_components = sorted(
        ({"name": name, "estimated_tokens": tokens} for name, tokens in component_totals.items()),
        key=lambda item: int(item["estimated_tokens"]),
        reverse=True,
    )
    return {
        "available": bool(events),
        "event_count": len(events),
        "total_estimated_tokens": total_estimated_tokens,
        "by_lane": _counter_rows(lane_counts, "lane"),
        "by_stage": _counter_rows(stage_counts, "stage"),
        "signal_counts": _counter_rows(signal_counts, "signal_category"),
        "top_components": sorted_components[:8],
        "latest": _compact_latest(latest),
    }


def _budget_payload(
    *,
    lane: str,
    stage: str,
    components: list[dict[str, Any]],
    runtime_metadata: dict[str, Any],
    correlation_id: str,
    extra: dict[str, Any],
) -> dict[str, Any]:
    total = sum(int(item.get("estimated_tokens") or 0) for item in components)
    signal_value = _signal_value(components)
    return {
        "schema_version": "1",
        "lane": lane,
        "stage": stage,
        "correlation_id": correlation_id,
        "runtime_sdk": str(runtime_metadata.get("runtime_sdk") or ""),
        "provider": str(runtime_metadata.get("provider") or ""),
        "model": str(runtime_metadata.get("model") or ""),
        "effort": str(runtime_metadata.get("effort") or ""),
        "component_estimates": components,
        "total_estimated_tokens": total,
        "signal_value": signal_value,
        "signal_category": signal_value["category"],
        "privacy_policy": "local_estimates_no_raw_prompt_or_tool_content",
        **extra,
    }


def _signal_value(components: list[dict[str, Any]]) -> dict[str, Any]:
    sent = [item for item in components if int(item.get("estimated_tokens") or 0) > 0]
    useful = [
        item
        for item in sent
        if str(item.get("signal_category") or "") not in {"not_sent", "handoff_payload"}
    ]
    total = sum(int(item.get("estimated_tokens") or 0) for item in sent)
    useful_tokens = sum(int(item.get("estimated_tokens") or 0) for item in useful)
    ratio = useful_tokens / total if total else 0.0
    if not sent:
        category = "none"
    elif ratio >= 0.5:
        category = "high"
    elif ratio > 0:
        category = "mixed"
    else:
        category = "low"
    return {
        "category": category,
        "useful_component_count": len(useful),
        "sent_component_count": len(sent),
        "useful_token_ratio": round(ratio, 4),
    }


def _counter_rows(counter: Counter[str], key_name: str) -> list[dict[str, Any]]:
    return [
        {key_name: key, "count": value}
        for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _compact_latest(event: dict[str, Any]) -> dict[str, Any]:
    if not event:
        return {}
    return {
        key: event.get(key)
        for key in (
            "lane",
            "stage",
            "runtime_sdk",
            "provider",
            "model",
            "effort",
            "total_estimated_tokens",
            "signal_category",
            "correlation_id",
        )
        if event.get(key) not in ("", None)
    }
