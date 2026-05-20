"""OpenAI Realtime voice operator API for the builder Agent page."""

from __future__ import annotations

import asyncio
import json
import os
import re
from contextlib import suppress
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from autonomous_agent_builder.db.models import ChatEvent, ChatSession
from autonomous_agent_builder.db.session import get_session_factory
from autonomous_agent_builder.services.context_budget import (
    build_realtime_session_context_budget,
    build_realtime_tool_context_budget,
)
from autonomous_agent_builder.services.realtime_voice_ledger import (
    VOICE_LEDGER_EVENT_TYPES,
    build_realtime_voice_ledger,
)
from autonomous_agent_builder.services.realtime_voice_policy import (
    DEFAULT_REALTIME_VOICE_POLICY,
    VOICE_OPERATOR_INSTRUCTIONS,
)
from autonomous_agent_builder.services.voice_operator import (
    AgentOperatorService,
    HighRiskVoiceActionService,
    VoiceCostLedger,
    VoiceOperatorService,
    bind_voice_call_session,
)

router = APIRouter()


class RealtimeTextControlRequest(BaseModel):
    message: str = Field(..., min_length=1)
    call_id: str = ""
    session_id: str = ""
    fallback_to_agent: bool = False


class RealtimeTextControlResponse(BaseModel):
    handled: bool
    operator_message: str = ""
    assistant_message: str = ""
    tool_name: str = ""
    route: str = ""


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "get_builder_agent_update",
        "description": (
            "Read a compact current-state digest for simple factual status checks: "
            "current runtime, active run, pending operator items, Board task counts, "
            "sprint counts, blocked task names, recent provider-limit run status, "
            "and latest voice usage. Use this even when the operator says check with "
            "Builder or verify, as long as they only ask for a factual Board, sprint, "
            "blocked-task, or pending-approval read. Do not use this to inspect "
            "logs/metrics/observability, diagnose failures, do repo/generated-app "
            "work, or resolve disputed correctness; use delegate_to_builder_agent "
            "for those so the Agent page records the question and SDK-backed answer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "status_prompt": {
                    "type": "string",
                    "description": (
                        "Optional operator wording for the status question. "
                        "Use this when Board scope matters, for example when the "
                        "operator explicitly asks about older sprints."
                    ),
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "delegate_to_builder_agent",
        "description": (
            "Delegate an operator message to the builder Agent page chat lane. "
            "Use for Builder-directed work instructions, bug reports, product "
            "corrections, validation requests, logs/metrics/observability diagnosis, "
            "failure diagnosis, repo or generated-app work, disputed correctness, "
            "and status requests that need interpretation beyond the compact status "
            "digest. Do not use "
            "this for simple Board/sprint counts, blocked-task names, or pending "
            "approval checks; use get_builder_agent_update for those. "
            "Pass the operator's exact request as message; do not rewrite a "
            "feature or shipping request into a narrower investigation prompt. "
            "Use thread_mode=new when the operator intent starts a distinct topic, "
            "large task, or token-expensive investigation. Omit wait_for_completion "
            "for normal realtime handoffs so completion is event-driven."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The operator instruction to send to the builder agent.",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional existing Agent-page chat session id.",
                },
                "thread_mode": {
                    "type": "string",
                    "enum": ["current", "new", "auto"],
                    "description": (
                        "current continues the given/latest thread; new starts a fresh "
                        "Agent-page thread; auto lets Builder choose the latest thread."
                    ),
                },
                "routing_reason": {
                    "type": "string",
                    "description": "Short reason for current vs new thread routing.",
                },
                "wait_for_completion": {
                    "type": "boolean",
                    "description": (
                        "When true, Builder waits for the SDK-backed Agent task "
                        "and returns the refreshed voice digest."
                    ),
                },
                "completion_timeout_seconds": {
                    "type": "integer",
                    "description": "Maximum seconds to wait for the Agent task to finish.",
                },
            },
            "required": ["message"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "navigate_dashboard",
        "description": (
            "Navigate the visible Builder dashboard for a simple operator request "
            "like 'show me the board', 'open settings', 'go to metrics', 'show "
            "conversation', 'open voice', or 'show run trace'. This is a direct "
            "one-step control and does not require SDK-backed Agent analysis."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": (
                        "Destination page or tab: conversation, voice, run trace, "
                        "board, metrics, observability, backlog, knowledge, memory, "
                        "inbox, compare, or settings."
                    ),
                }
            },
            "required": ["target"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "open_run_trace",
        "description": (
            "Open an existing Builder run trace when the operator asks to see what "
            "happened in the last task run, last optimization run, or the agent run "
            "that led to a blocked state. This only navigates to recorded evidence; "
            "it does not analyze logs, diagnose failures, or mutate Builder state."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "selection": {
                    "type": "string",
                    "description": (
                        "Natural-language run reference from the operator, such as "
                        "'last optimization run' or 'run that led to blocked state'."
                    ),
                },
                "run_kind": {
                    "type": "string",
                    "enum": ["latest", "optimization", "blocked", "task"],
                    "description": "Optional deterministic run class to resolve.",
                },
                "intent": {
                    "type": "string",
                    "enum": ["open_only", "open_then_analyze"],
                    "description": (
                        "Use open_only when the operator only asks to show or open "
                        "the run trace. Use open_then_analyze when the operator asks "
                        "what issues happened, whether the run was efficient, why it "
                        "blocked, or for any interpretation of the loaded run trace."
                    ),
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional exact Board task id when already known.",
                },
                "run_id": {
                    "type": "string",
                    "description": "Optional exact Agent run id when already known.",
                },
                "analysis_request": {
                    "type": "string",
                    "description": (
                        "Operator's analysis request, required when intent is "
                        "open_then_analyze. Samantha first opens the resolved run "
                        "trace, then delegates this request to the SDK-backed Agent "
                        "with the run id and task id. Samantha does not analyze the "
                        "trace directly."
                    ),
                },
                "completion_timeout_seconds": {
                    "type": "integer",
                    "description": "Maximum seconds to wait for delegated run-trace analysis.",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "recover_board_task",
        "description": (
            "Recover a blocked or capability-limited Board task immediately through "
            "Builder's task recovery service when the operator asks to recover, "
            "resume, retry, or unblock that task. Use task_id when known; otherwise "
            "pass the operator's words in recovery_request. This does not dispatch "
            "the task unless the operator also asks to dispatch it. If Builder has "
            "no recoverable Board task, report that recovery is not available; do "
            "not convert historical chat failures into an approval or retry."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional existing Agent-page chat session id.",
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional Board task id to recover.",
                },
                "recovery_request": {
                    "type": "string",
                    "description": "Operator recovery intent, task title, or blocker summary.",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "dispatch_board_task",
        "description": (
            "Dispatch a dispatchable Board task through Builder's normal Board "
            "dispatch path when the operator asks to dispatch, start, continue, or "
            "run the recovered/current task. Use task_id when known; otherwise "
            "Builder selects the current best dispatchable task."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Optional Board task id to dispatch.",
                },
                "selection": {
                    "type": "string",
                    "description": "Optional natural-language task reference, such as 'the recovered task'.",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "answer_pending_builder_question",
        "description": "Answer a pending Agent-page question card.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Agent-page chat session id."},
                "event_id": {"type": "string", "description": "Pending question event id."},
                "answer": {"type": "string", "description": "Operator answer."},
            },
            "required": ["session_id", "event_id", "answer"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "recover_blocked_run",
        "description": (
            "Recover a blocked Board task through Builder's task recovery service when "
            "the operator explicitly asks to recover or resume blocked work. Match the "
            "operator's task title/id/reason against Board blockers; do not use this "
            "for sprint scope approval. This does not bypass approvals or mutate "
            "generated code directly. Compatibility is limited to Board-backed "
            "recovery; if no blocked Board task exists, return not_recoverable."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional existing Agent-page chat session id to recover.",
                },
                "recovery_request": {
                    "type": "string",
                    "description": "Operator recovery intent, blocker summary, or next step.",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "switch_builder_runtime",
        "description": (
            "Switch Builder's selected SDK/runtime for future runs only when the "
            "operator explicitly asks to change to Codex SDK or Claude Agent SDK. "
            "This preserves existing tasks, run history, metrics, observability, "
            "memory, knowledge, and backlog attribution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sdk": {
                    "type": "string",
                    "enum": ["codex_sdk", "claude"],
                    "description": "Target runtime SDK: codex_sdk or claude.",
                }
            },
            "required": ["sdk"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "prepare_high_risk_decision",
        "description": (
            "Prepare, but do not execute, an approval allow/deny decision. "
            "The operator must confirm the returned action id."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Agent-page chat session id."},
                "event_id": {"type": "string", "description": "Pending approval event id."},
                "decision": {"type": "string", "enum": ["allow", "deny"]},
                "reason": {"type": "string", "description": "Short operator reason."},
            },
            "required": ["session_id", "event_id", "decision", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "confirm_high_risk_action",
        "description": (
            "Execute a previously prepared high-risk voice action after explicit confirmation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action_id": {
                    "type": "string",
                    "description": "The action id returned by prepare_approval_decision.",
                }
            },
            "required": ["action_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "wait_for_user",
        "description": (
            "Take no Builder action only for silence, keyboard noise, music, room "
            "disturbance, side conversation, or speech clearly not addressed to "
            "Builder. Do not use for unclear Builder-directed requests."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Short reason the voice operator is waiting.",
                }
            },
            "additionalProperties": False,
        },
    },
]


def _session_config() -> str:
    return json.dumps(DEFAULT_REALTIME_VOICE_POLICY.session_config())


def _call_id_from_location(location: str | None) -> str:
    if not location:
        return ""
    return location.rstrip("/").split("/")[-1]


def _start_sideband_task(app: Any, call_id: str) -> None:
    if not call_id:
        return
    tasks = getattr(app.state, "realtime_voice_tasks", None)
    if not isinstance(tasks, dict):
        tasks = {}
        app.state.realtime_voice_tasks = tasks
    task = asyncio.create_task(_run_sideband(app, call_id))
    tasks[call_id] = task
    task.add_done_callback(lambda _task: tasks.pop(call_id, None))


def _is_simple_realtime_status_prompt(message: str) -> bool:
    normalized = " ".join(message.lower().replace("?", " ").split())
    if not normalized:
        return False
    heavy_terms = {
        "analyze",
        "diagnose",
        "debug",
        "evidence",
        "failing",
        "failure",
        "investigate",
        "logs",
        "metrics",
        "observability",
        "prove",
        "why",
    }
    if any(term in normalized for term in heavy_terms):
        return False
    status_terms = {
        "approval",
        "backlog",
        "blocked",
        "board",
        "doing",
        "done",
        "pending",
        "sprint",
        "status",
        "waiting",
    }
    status_phrases = (
        "where are we",
        "what is left",
        "what's left",
        "anything waiting",
        "how many tasks",
    )
    return any(term in normalized for term in status_terms) or any(
        phrase in normalized for phrase in status_phrases
    )


_REALTIME_NAVIGATION_TARGETS = (
    "agent",
    "conversation",
    "chat",
    "voice",
    "realtime",
    "realtime voice",
    "run trace",
    "trace",
    "board",
    "metrics",
    "observability",
    "logs",
    "knowledge",
    "memory",
    "backlog",
    "inbox",
    "compare",
    "settings",
)
_REALTIME_NAVIGATION_QUESTION_PREFIXES = (
    "why ",
    "how ",
    "what ",
    "what's ",
    "whats ",
    "which ",
    "where ",
    "when ",
)


def _simple_realtime_navigation_target(message: str) -> str:
    normalized = " ".join(message.lower().replace("?", " ").split())
    if not normalized:
        return ""
    if normalized.startswith(_REALTIME_NAVIGATION_QUESTION_PREFIXES):
        return ""
    navigation_markers = (
        "go to",
        "go back to",
        "take me to",
        "open",
        "show me",
        "show",
        "switch to",
        "navigate to",
    )
    marker_matches = [
        re.search(rf"\b{re.escape(marker)}\b", normalized) for marker in navigation_markers
    ]
    if not any(marker_matches):
        return ""
    if any(
        word in normalized for word in ("status", "state", "count", "counts", "left", "remaining")
    ):
        return ""
    for target in sorted(_REALTIME_NAVIGATION_TARGETS, key=len, reverse=True):
        if target in normalized:
            return target
    return ""


@router.post("/realtime/text-control", response_model=RealtimeTextControlResponse)
async def realtime_text_control(
    payload: RealtimeTextControlRequest,
    request: Request,
) -> RealtimeTextControlResponse:
    """Deterministically handle one-step typed Realtime operator intents."""

    message = payload.message.strip()
    call_id = payload.call_id.strip()
    session_id = payload.session_id.strip()
    if call_id and session_id:
        _bind_voice_call_session(request.app, call_id, session_id)

    voice_operator = VoiceOperatorService(request.app)
    navigation_target = _simple_realtime_navigation_target(message)
    if navigation_target:
        tool_call = {
            "name": "navigate_dashboard",
            "call_id": f"text_navigation_{call_id or 'local'}",
            "arguments": json.dumps({"target": message, "voice_call_id": call_id}),
        }
        await voice_operator.record_tool_event("voice_tool_call", call_id, tool_call)
        output = await voice_operator.handle_tool_call(tool_call, call_id=call_id)
        await voice_operator.record_tool_event(
            "voice_tool_output",
            call_id,
            tool_call,
            output=output,
        )
        await _record_realtime_context_budget(
            voice_operator,
            call_id,
            build_realtime_tool_context_budget(
                call_id=call_id,
                tool_call=tool_call,
                output=output,
                runtime_metadata=voice_operator.runtime_metadata(),
            ),
        )
        result = output.get("result") if isinstance(output, dict) else {}
        target = navigation_target.title()
        route = str(result.get("route") or "").strip() if isinstance(result, dict) else ""
        assistant_message = f"Opening {target}." if route else "I could not open that Builder page."
        return RealtimeTextControlResponse(
            handled=True,
            operator_message=message,
            assistant_message=assistant_message,
            tool_name="navigate_dashboard",
            route=route,
        )

    if not _is_simple_realtime_status_prompt(message):
        if payload.fallback_to_agent:
            tool_call = {
                "name": "delegate_to_builder_agent",
                "call_id": f"text_fallback_{call_id or 'local'}",
                "arguments": json.dumps(
                    {
                        "message": message,
                        "session_id": session_id,
                        "thread_mode": "auto",
                        "routing_reason": "typed Realtime fallback after connection was unavailable",
                        "wait_for_completion": False,
                    }
                ),
            }
            await voice_operator.record_tool_event("voice_tool_call", call_id, tool_call)
            output = await voice_operator.handle_tool_call(tool_call, call_id=call_id)
            await voice_operator.record_tool_event(
                "voice_tool_output",
                call_id,
                tool_call,
                output=output,
            )
            await _record_realtime_context_budget(
                voice_operator,
                call_id,
                build_realtime_tool_context_budget(
                    call_id=call_id,
                    tool_call=tool_call,
                    output=output,
                    runtime_metadata=voice_operator.runtime_metadata(),
                ),
            )
            result = output.get("result") if isinstance(output, dict) else {}
            delegated_session_id = (
                str(result.get("session_id") or "").strip() if isinstance(result, dict) else ""
            )
            assistant_message = (
                str(result.get("operator_message") or "").strip()
                if isinstance(result, dict)
                else ""
            )
            return RealtimeTextControlResponse(
                handled=True,
                operator_message=message,
                assistant_message=assistant_message or "Builder is working in Conversation.",
                tool_name="delegate_to_builder_agent",
                route=f"/?session={delegated_session_id}&mode=chat" if delegated_session_id else "",
            )
        return RealtimeTextControlResponse(handled=False)

    tool_call = {
        "name": "get_builder_agent_update",
        "call_id": f"text_status_{call_id or 'local'}",
        "arguments": json.dumps({"status_prompt": message}),
    }
    await voice_operator.record_tool_event("voice_tool_call", call_id, tool_call)
    output = await voice_operator.handle_tool_call(tool_call, call_id=call_id)
    await voice_operator.record_tool_event(
        "voice_tool_output",
        call_id,
        tool_call,
        output=output,
    )
    await _record_realtime_context_budget(
        voice_operator,
        call_id,
        build_realtime_tool_context_budget(
            call_id=call_id,
            tool_call=tool_call,
            output=output,
            runtime_metadata=voice_operator.runtime_metadata(),
        ),
    )
    status = output.get("status") if isinstance(output, dict) else {}
    assistant_message = ""
    if isinstance(status, dict):
        assistant_message = str(status.get("voice_digest") or "").strip()
    if not assistant_message:
        assistant_message = "Builder status is unavailable right now."
    return RealtimeTextControlResponse(
        handled=True,
        operator_message=message,
        assistant_message=assistant_message,
        tool_name="get_builder_agent_update",
    )


@router.post("/realtime/session")
async def create_realtime_session(request: Request) -> Response:
    """Create a Realtime WebRTC call for the Agent-page voice panel."""

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is required to start a Realtime voice session."
            " Add it to the Builder source environment, not the generated app .env, "
            "then restart builder start.",
        )

    sdp = (await request.body()).decode("utf-8")
    validation_sdp = sdp.lstrip()
    if not sdp.strip():
        raise HTTPException(status_code=400, detail="SDP offer body is required.")
    if not validation_sdp.startswith("v="):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "SDP offer must start with a session line.",
                "sdp_chars": len(sdp),
                "sdp_prefix": validation_sdp[:12],
            },
        )

    requested_session_id = request.headers.get("X-Agent-Session-Id")
    session_mode = str(request.headers.get("X-Agent-Session-Mode") or "").strip().lower()
    bound_session = None
    if requested_session_id or session_mode == "fresh":
        bound_session = await _resolve_voice_session(
            request.app,
            requested_session_id=requested_session_id,
            fresh=session_mode == "fresh",
            create_if_missing=session_mode == "fresh",
        )
    if requested_session_id and session_mode != "fresh" and bound_session is None:
        raise HTTPException(status_code=404, detail="Agent chat session not found for Realtime.")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            realtime_response = await client.post(
                "https://api.openai.com/v1/realtime/calls",
                headers={"Authorization": f"Bearer {api_key}"},
                files={
                    "sdp": (None, sdp),
                    "session": (None, _session_config()),
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI Realtime session request failed: {exc}",
        ) from exc

    answer_sdp = realtime_response.text
    if realtime_response.status_code >= 400:
        raise HTTPException(
            status_code=realtime_response.status_code,
            detail={
                "error": answer_sdp or "OpenAI Realtime session request failed.",
                "sdp_chars": len(sdp),
                "sdp_starts_with_session_line": validation_sdp.startswith("v="),
            },
        )

    location = realtime_response.headers.get("Location")
    call_id = _call_id_from_location(location)
    if call_id and bound_session is not None:
        _bind_voice_call_session(request.app, call_id, bound_session.id)
    _start_sideband_task(request.app, call_id)

    headers: dict[str, str] = {}
    if location:
        headers["Location"] = location
    if call_id:
        headers["X-Realtime-Call-Id"] = call_id
    if bound_session is not None:
        headers["X-Agent-Session-Id"] = bound_session.id

    return Response(
        content=answer_sdp,
        media_type="application/sdp",
        status_code=realtime_response.status_code,
        headers=headers,
    )


@router.get("/realtime/ledger")
async def realtime_ledger() -> dict[str, Any]:
    """Return persisted Realtime voice usage and prepared-action evidence."""

    session_factory = get_session_factory()
    async with session_factory() as db:
        result = await db.execute(
            select(ChatEvent)
            .where(ChatEvent.event_type.in_(VOICE_LEDGER_EVENT_TYPES))
            .order_by(ChatEvent.created_at.desc())
            .limit(50)
        )
        events = list(result.scalars().all())

    return build_realtime_voice_ledger(events)


async def _record_realtime_context_budget(
    voice_operator: VoiceOperatorService,
    call_id: str,
    payload: dict[str, Any],
) -> None:
    """Persist context evidence without making Realtime control depend on it."""

    with suppress(Exception):
        await voice_operator.record_context_budget(call_id, payload)


async def _run_sideband(app: Any, call_id: str) -> None:
    import websockets

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return

    voice_operator = VoiceOperatorService(app)
    url = f"wss://api.openai.com/v1/realtime?call_id={call_id}"
    try:
        async with websockets.connect(
            url,
            additional_headers={"Authorization": f"Bearer {api_key}"},
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "type": "realtime",
                            "instructions": VOICE_OPERATOR_INSTRUCTIONS,
                            "tools": TOOL_DEFINITIONS,
                            "tool_choice": "auto",
                        },
                    }
                )
            )
            await _record_realtime_context_budget(
                voice_operator,
                call_id,
                build_realtime_session_context_budget(
                    call_id=call_id,
                    instructions=VOICE_OPERATOR_INSTRUCTIONS,
                    tools=TOOL_DEFINITIONS,
                    runtime_metadata=voice_operator.runtime_metadata(),
                ),
            )
            handled_tool_call_ids: set[str] = set()
            while True:
                try:
                    raw_message = await _receive_sideband_message(ws)
                except StopAsyncIteration:
                    break
                try:
                    event = json.loads(raw_message)
                except json.JSONDecodeError:
                    continue
                await voice_operator.record_realtime_usage(call_id, event)
                for tool_call in _extract_tool_calls(event):
                    tool_call_id = str(tool_call.get("call_id") or "")
                    if tool_call_id and tool_call_id in handled_tool_call_ids:
                        continue
                    if tool_call_id:
                        handled_tool_call_ids.add(tool_call_id)
                    await voice_operator.record_tool_event(
                        "voice_tool_call",
                        call_id,
                        tool_call,
                    )
                    output = await voice_operator.handle_tool_call(tool_call, call_id=call_id)
                    await voice_operator.record_tool_event(
                        "voice_tool_output",
                        call_id,
                        tool_call,
                        output=output,
                    )
                    await _record_realtime_context_budget(
                        voice_operator,
                        call_id,
                        build_realtime_tool_context_budget(
                            call_id=call_id,
                            tool_call=tool_call,
                            output=output,
                            runtime_metadata=voice_operator.runtime_metadata(),
                        ),
                    )
                    await ws.send(
                        json.dumps(
                            {
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": tool_call.get("call_id", ""),
                                    "output": json.dumps(output),
                                },
                            }
                        )
                    )
                    if str(tool_call.get("name") or "") != "wait_for_user":
                        await ws.send(json.dumps({"type": "response.create"}))
    except websockets.exceptions.ConnectionClosed:
        return


async def _receive_sideband_message(ws: Any) -> str:
    recv = getattr(ws, "recv", None)
    if callable(recv):
        return str(await recv())
    return str(await ws.__anext__())


def _extract_tool_calls(event: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    event_type = str(event.get("type") or "")
    if event_type == "response.function_call_arguments.done":
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "function_call":
            calls.append(item)
        return calls
    if event_type != "response.done":
        return calls
    item = event.get("item")
    if isinstance(item, dict) and item.get("type") == "function_call":
        calls.append(item)
    response = event.get("response")
    if isinstance(response, dict):
        output = response.get("output")
        if isinstance(output, list):
            calls.extend(
                item
                for item in output
                if isinstance(item, dict) and item.get("type") == "function_call"
            )
    return calls


async def _handle_tool_call(
    app: Any,
    tool_call: dict[str, Any],
    *,
    call_id: str = "",
) -> dict[str, Any]:
    return await VoiceOperatorService(app).handle_tool_call(tool_call, call_id=call_id)


async def _record_voice_tool_event(
    app: Any,
    event_type: str,
    call_id: str,
    tool_call: dict[str, Any],
    *,
    output: dict[str, Any] | None = None,
) -> None:
    await VoiceOperatorService(app).record_tool_event(
        event_type,
        call_id,
        tool_call,
        output=output,
    )


async def _get_builder_status(
    app: Any,
    *,
    active_session_id: str = "",
    prefer_latest_summary: bool = False,
    status_prompt: str = "",
) -> dict[str, Any]:
    return await AgentOperatorService(app).get_builder_status(
        active_session_id=active_session_id,
        prefer_latest_summary=prefer_latest_summary,
        status_prompt=status_prompt,
    )


async def _send_agent_message(app: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    return await AgentOperatorService(app).send_message(arguments)


async def _recover_blocked_run(app: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    return await HighRiskVoiceActionService(app).prepare_recovery(arguments)


async def _answer_pending_question(app: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    return await AgentOperatorService(app).answer_pending_question(arguments)


async def _switch_builder_runtime(app: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    return await AgentOperatorService(app).switch_runtime(arguments)


async def _prepare_approval_decision(app: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    return await HighRiskVoiceActionService(app).prepare_approval_decision(arguments)


async def _confirm_high_risk_action(app: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    return await HighRiskVoiceActionService(app).confirm_action(arguments)


async def _wait_for_user(app: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    return await AgentOperatorService(app).wait_for_user(arguments)


async def _record_realtime_usage(app: Any, call_id: str, event: dict[str, Any]) -> None:
    await VoiceCostLedger(app).record_usage(call_id, event)


def _realtime_usage_payload(call_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
    return VoiceCostLedger().usage_payload(call_id, event)


def _voice_call_sessions(app: Any) -> dict[str, str]:
    sessions = getattr(app.state, "realtime_voice_call_sessions", None)
    if not isinstance(sessions, dict):
        sessions = {}
        app.state.realtime_voice_call_sessions = sessions
    return sessions


def _bind_voice_call_session(app: Any, call_id: str, session_id: str) -> None:
    bind_voice_call_session(app, call_id, session_id)


def _voice_call_session_id(app: Any, call_id: str) -> str:
    if not call_id:
        return ""
    session_id = _voice_call_sessions(app).get(call_id)
    return str(session_id or "")


async def _resolve_voice_session(
    app: Any,
    *,
    requested_session_id: str | None = None,
    fresh: bool = False,
    create_if_missing: bool = False,
) -> ChatSession | None:
    return await AgentOperatorService(app).resolve_voice_session(
        requested_session_id=requested_session_id,
        fresh=fresh,
        create_if_missing=create_if_missing,
    )


async def _latest_or_new_voice_session(app: Any, *, call_id: str = "") -> ChatSession:
    return await AgentOperatorService(app).latest_or_new_voice_session(call_id=call_id)


async def _answer_tool_approval(app: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    return await AgentOperatorService(app).answer_tool_approval(arguments)
