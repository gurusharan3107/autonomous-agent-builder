"""Agent chat API routes for embedded server."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from autonomous_agent_builder.agents.definitions import (
    get_agent_definition,
    get_subagent_definition,
)
from autonomous_agent_builder.agents.runner import AgentRunner, RunResult
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import (
    ChatEvent,
    ChatMessage,
    ChatSession,
    Feature,
    Project,
    Task,
    utcnow,
)
from autonomous_agent_builder.db.session import get_db, get_session_factory
from autonomous_agent_builder.embedded.server.chat_state import ChatSessionHub
from autonomous_agent_builder.knowledge.kb_paths import resolve_repo_local_kb_path
from autonomous_agent_builder.knowledge.maintained_freshness import (
    CANONICAL_DOC_REF,
    git_current_branch,
    git_head_for_ref,
    maintained_doc_report,
    resolve_canonical_doc_ref,
)
from autonomous_agent_builder.knowledge.publisher import parse_markdown_document
from autonomous_agent_builder.knowledge.retrieval import load_docs, search_docs
from autonomous_agent_builder.logs.diagnostics import summarize_chat_event, summarize_tool_event
from autonomous_agent_builder.onboarding import (
    _INIT_PROJECT_BOOTSTRAP_MESSAGE,
    ensure_init_project_bootstrap_session,
    load_onboarding_state,
    write_feature_list_file,
)

router = APIRouter()

_FEATURE_LIST_MARKER = "FEATURE_LIST_JSON:"
_FEATURE_SPEC_MARKER = "FEATURE_SPEC_JSON:"
_VISIBLE_EVENT_TYPES = {
    "user_message",
    "assistant_message",
    "ask_user_question",
    "tool_approval_request",
    "tool_result",
    "tool_error",
    "todo_snapshot",
    "specialist_status",
    "run_error",
}
_DOC_INTENT_TERMS = (
    "documentation",
    "document",
    "docs",
    "knowledge base",
    "knowledgebase",
    "kb",
    "feature doc",
    "testing doc",
    "maintained doc",
    "system doc",
)
_DOC_CHANGE_TERMS = (
    "implemented",
    "implementation",
    "changed",
    "updated",
    "fixed",
    "finished",
    "completed",
    "done",
    "shipped",
    "verify",
    "verified",
    "check",
    "review",
    "refresh",
)
_DOC_CREATE_TERMS = (
    "create",
    "generate",
    "add",
    "missing",
)
_DOC_REFRESH_TERMS = (
    "current",
    "currentness",
    "fresh",
    "freshness",
    "stale",
    "up to date",
    "up-to-date",
    "latest",
    "check",
    "verify",
    "validated",
    "updated",
    "refresh",
)
_TESTING_SCOPE_PATTERNS = (
    ("testing required", "testing_required"),
    ("testing by feature", "testing_by_feature"),
    ("reverse engineering testing", "reverse_engineering"),
    ("forward engineering testing", "forward_engineering"),
    ("end-to-end", "end_to_end"),
    ("end to end", "end_to_end"),
    ("e2e", "end_to_end"),
)
_FEATURE_SPEC_INTENT_PATTERNS = (
    "feature spec",
    "create feature",
    "add feature",
    "new feature",
    "backlog item",
    "add to backlog",
)
_FEATURE_REQUEST_ACTION_PATTERNS = (
    "i want",
    "we want",
    "i need",
    "we need",
    "can you add",
    "could you add",
    "please add",
    "can you build",
    "could you build",
    "can you implement",
    "could you implement",
    "please implement",
    "take this through",
    "next steps",
    "allow users to",
    "users should be able to",
    "users to be able to",
)
_FEATURE_REQUEST_SCOPE_TERMS = (
    "user",
    "users",
    "post",
    "posts",
    "profile",
    "page",
    "screen",
    "view",
    "save",
    "bookmark",
    "bookmarks",
)
_FEATURE_DELIVERY_CONTINUE_PATTERNS = (
    "take this through",
    "next steps",
    "go ahead and implement",
    "go ahead and build",
    "build this",
    "implement this",
    "ship this",
)
_FEATURE_SPEC_BLOCKED_TOOLS = frozenset(
    {
        "Bash",
        "mcp__builder__kb_add",
        "mcp__builder__kb_update",
        "mcp__builder__memory_add",
        "mcp__workspace__run_command",
        "mcp__workspace__run_tests",
        "mcp__workspace__run_linter",
    }
)
_DOCUMENTATION_AGENT_AUTO_APPROVE_TOOLS = frozenset(
    get_subagent_definition("documentation-agent").tools
)
_DOCUMENTATION_CONTINUATION_PHRASES = frozenset(
    {
        "update",
        "please update",
        "update them",
        "refresh",
        "refresh them",
        "go ahead",
        "do it",
        "please do it",
        "fix it",
    }
)


@dataclass(frozen=True)
class SpecialistRoutePolicy:
    name: str
    explicit_intent_matcher: Callable[[str], bool]
    continuation_matcher: Callable[[str], bool]
    context_builder: Callable[..., Awaitable[dict[str, Any] | None]]
    auto_approve_tools: frozenset[str]
    active_summary: str
    blocked_summary: str
    completed_summary: str


@dataclass(frozen=True)
class ActiveSpecialistRoute:
    policy: SpecialistRoutePolicy
    route_reason: str
    context: dict[str, Any]

    @property
    def name(self) -> str:
        return self.policy.name


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    model: str
    status: dict | None = None


class MessageItem(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str


class TimelineItem(BaseModel):
    id: str
    type: str
    status: str
    timestamp: str
    payload: dict[str, Any]


class ChatHistoryResponse(BaseModel):
    session_id: str
    sdk_session_id: str | None = None
    model: str
    repo_identity: str
    workspace_cwd: str
    items: list[TimelineItem]
    messages: list[MessageItem]
    status: dict | None = None


class ChatSessionItem(BaseModel):
    id: str
    sdk_session_id: str | None = None
    created_at: str
    updated_at: str
    message_count: int
    preview: str
    workspace_cwd: str | None = None
    is_resume_candidate: bool = False


class ChatSessionListResponse(BaseModel):
    repo_identity: str
    workspace_cwd: str
    latest_resume_session_id: str | None = None
    sessions: list[ChatSessionItem]


class ChatMetaResponse(BaseModel):
    model: str
    repo_identity: str
    workspace_cwd: str


class ChatRespondRequest(BaseModel):
    session_id: str
    event_id: str
    selected_options: list[str] = Field(default_factory=list)
    custom_text: str = ""
    decision: str | None = None
    reason: str = ""
    updated_input: dict[str, Any] | None = None


class ChatRespondResponse(BaseModel):
    ok: bool
    session_id: str
    event_id: str


def _project_root(request: Request) -> Path:
    return Path(getattr(request.app.state, "project_root", Path.cwd()))


def _repo_identity(project_root: Path) -> str:
    return str(project_root.resolve())


def _workspace_cwd(project_root: Path) -> str:
    return str(project_root.resolve())


def _chat_hub(request: Request) -> ChatSessionHub:
    return request.app.state.chat_hub


def _feature_list_path(project_root: Path) -> Path:
    return project_root / ".claude" / "progress" / "feature-list.json"


def _needs_init_project_bootstrap(project_root: Path) -> bool:
    state = load_onboarding_state(project_root)
    return (
        bool(state.get("ready"))
        and state.get("onboarding_mode") == "forward_engineering"
        and not _feature_list_path(project_root).exists()
    )


def _active_chat_agent_name(project_root: Path) -> str:
    return "init-project-chat" if _needs_init_project_bootstrap(project_root) else "chat"


def _chat_model_name(project_root: Path) -> str:
    return get_agent_definition(_active_chat_agent_name(project_root)).model


def _serialize_event(event: ChatEvent) -> TimelineItem:
    return TimelineItem(
        id=event.id,
        type=event.event_type,
        status=event.status,
        timestamp=event.created_at.isoformat(),
        payload=event.payload_json or {},
    )


def _legacy_message_item(message: ChatMessage) -> TimelineItem:
    event_type = "user_message" if message.role == "user" else "assistant_message"
    return TimelineItem(
        id=message.id,
        type=event_type,
        status="completed",
        timestamp=message.created_at.isoformat(),
        payload={"content": message.content, "final": True},
    )


def _history_items(session: ChatSession) -> list[TimelineItem]:
    if session.events:
        return [_serialize_event(event) for event in session.events if event.event_type in _VISIBLE_EVENT_TYPES]
    return [_legacy_message_item(message) for message in session.messages]


def _legacy_messages(items: list[TimelineItem]) -> list[MessageItem]:
    messages: list[MessageItem] = []
    for item in items:
        if item.type not in {"user_message", "assistant_message", "tool_error", "run_error"}:
            continue
        role = "user" if item.type == "user_message" else "assistant"
        content = str(item.payload.get("content", ""))
        if not content:
            continue
        messages.append(
            MessageItem(
                id=item.id,
                role=role,
                content=content,
                timestamp=item.timestamp,
            )
        )
    return messages


def _latest_status(session: ChatSession) -> dict[str, Any] | None:
    for event in reversed(session.events):
        if event.event_type == "run_status":
            return event.payload_json
    return None


def _stamp_session_scope(session: ChatSession, project_root: Path) -> None:
    session.repo_identity = _repo_identity(project_root)
    session.workspace_cwd = _workspace_cwd(project_root)


def _session_matches_scope(session: ChatSession, project_root: Path) -> bool:
    repo_identity = _repo_identity(project_root)
    workspace_cwd = _workspace_cwd(project_root)
    if session.repo_identity and session.repo_identity != repo_identity:
        return False
    if session.workspace_cwd and session.workspace_cwd != workspace_cwd:
        return False
    return True


def _session_has_meaningful_transcript(session: ChatSession) -> bool:
    items = _history_items(session)
    for item in items:
        if item.type == "user_message":
            return True
        if item.type == "assistant_message":
            content = str(item.payload.get("content", "")).strip()
            if content and content != _INIT_PROJECT_BOOTSTRAP_MESSAGE:
                return True
            continue
        if item.type in {"ask_user_question", "tool_approval_request", "run_error"}:
            return True
    return False


def _session_preview(session: ChatSession) -> str:
    items = _history_items(session)
    for item in items:
        if item.type == "user_message":
            content = str(item.payload.get("content", "")).strip()
            normalized = " ".join(content.split())
            if normalized:
                return normalized[:117] + "..." if len(normalized) > 120 else normalized
    for item in items:
        content = str(item.payload.get("content", "")).strip()
        normalized = " ".join(content.split())
        if normalized:
            return normalized[:117] + "..." if len(normalized) > 120 else normalized
    return "Empty session"


async def _load_session(
    db: AsyncSession,
    session_id: str | None,
    *,
    project_root: Path | None = None,
    reject_scope_mismatch: bool = False,
) -> ChatSession | None:
    if not session_id:
        return None
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(selectinload(ChatSession.events), selectinload(ChatSession.messages))
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None
    if project_root is not None:
        if not _session_matches_scope(session, project_root):
            if reject_scope_mismatch:
                raise HTTPException(
                    status_code=409,
                    detail="Chat session belongs to a different repo or workspace.",
                )
            return None
        if not session.repo_identity or not session.workspace_cwd:
            _stamp_session_scope(session, project_root)
            await db.flush()
    return session


async def _list_scoped_sessions(db: AsyncSession, project_root: Path) -> list[ChatSession]:
    result = await db.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.events), selectinload(ChatSession.messages))
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = result.scalars().all()
    scoped_sessions: list[ChatSession] = []
    for session in sessions:
        if not _session_matches_scope(session, project_root):
            continue
        if not session.repo_identity or not session.workspace_cwd:
            _stamp_session_scope(session, project_root)
            await db.flush()
        scoped_sessions.append(session)
    return scoped_sessions


def _latest_resume_candidate(sessions: list[ChatSession]) -> ChatSession | None:
    for session in sessions:
        if _session_has_meaningful_transcript(session):
            return session
    return None


async def _append_chat_event(
    session_id: str,
    *,
    event_type: str,
    payload: dict[str, Any],
    status: str = "completed",
    tool_use_id: str | None = None,
    response_to_event_id: str | None = None,
    mirror_message: tuple[str, str, int, float] | None = None,
) -> ChatEvent:
    session_factory = get_session_factory()
    async with session_factory() as db:
        session = await db.get(ChatSession, session_id)
        if session is None:
            raise RuntimeError(f"Chat session '{session_id}' not found")

        session.updated_at = utcnow()
        event = ChatEvent(
            session_id=session_id,
            event_type=event_type,
            payload_json=payload,
            status=status,
            tool_use_id=tool_use_id,
            response_to_event_id=response_to_event_id,
        )
        db.add(event)
        if mirror_message is not None:
            role, content, tokens_used, cost_usd = mirror_message
            db.add(
                ChatMessage(
                    session_id=session_id,
                    role=role,
                    content=content,
                    tokens_used=tokens_used,
                    cost_usd=cost_usd,
                )
            )
        await db.commit()
        await db.refresh(event)
        return event


async def _update_request_event(
    event_id: str,
    *,
    payload_patch: dict[str, Any],
    status: str,
    answer_event_type: str,
    answer_payload: dict[str, Any],
) -> ChatEvent:
    session_factory = get_session_factory()
    async with session_factory() as db:
        event = await db.get(ChatEvent, event_id)
        if event is None:
            raise RuntimeError(f"Chat event '{event_id}' not found")

        event_payload = dict(event.payload_json or {})
        event_payload.update(payload_patch)
        event.payload_json = event_payload
        event.status = status

        session = await db.get(ChatSession, event.session_id)
        if session is not None:
            session.updated_at = utcnow()

        db.add(
            ChatEvent(
                session_id=event.session_id,
                event_type=answer_event_type,
                payload_json=answer_payload,
                status="completed",
                response_to_event_id=event.id,
            )
        )
        await db.commit()
        await db.refresh(event)
        return event


def _initial_status(agent_name: str) -> dict[str, Any]:
    agent_def = get_agent_definition(agent_name)
    return {
        "running": True,
        "current_turn": 0,
        "max_turns": agent_def.max_turns,
        "tokens_used": 0,
        "cost_usd": 0.0,
    }


def _permission_allow(updated_input: dict[str, Any]) -> Any:
    try:
        from claude_agent_sdk.types import PermissionResultAllow

        return PermissionResultAllow(updated_input=updated_input)
    except ImportError:
        return SimpleNamespace(behavior="allow", updated_input=updated_input)


def _permission_deny(message: str) -> Any:
    try:
        from claude_agent_sdk.types import PermissionResultDeny

        return PermissionResultDeny(message=message)
    except ImportError:
        return SimpleNamespace(behavior="deny", message=message)


def _tool_summary(tool_name: str, input_data: dict[str, Any]) -> tuple[str, str]:
    if tool_name == "mcp__builder__kb_validate":
        kb_dir = str(input_data.get("kb_dir") or "system-docs").strip() or "system-docs"
        return (
            f"Validate repo-local KB `{kb_dir}`",
            "Claude needs approval to validate a repo-local knowledge directory.",
        )
    if tool_name == "Bash":
        command = str(input_data.get("command", "")).strip()
        description = str(input_data.get("description", "")).strip()
        return command or "Run shell command", description or "Claude needs approval to execute this command."
    if tool_name in {"Write", "Edit", "Read", "Glob", "Grep"}:
        path = str(
            input_data.get("file_path")
            or input_data.get("path")
            or input_data.get("pattern")
            or ""
        ).strip()
        summary = f"{tool_name} {path}".strip()
        return summary or tool_name, f"Claude needs approval to use `{tool_name}`."
    return tool_name, f"Claude needs approval to use `{tool_name}`."


def _truncate_preview(value: str, *, limit: int = 800) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _normalize_tool_response(tool_response: Any) -> tuple[str, str]:
    if isinstance(tool_response, dict):
        try:
            rendered = json.dumps(tool_response, ensure_ascii=True, sort_keys=True)
        except TypeError:
            rendered = str(tool_response)
    else:
        rendered = str(tool_response or "")

    lowered = rendered.lower()
    if '"status": "error"' in lowered or '"status":"error"' in lowered:
        return "tool_error", _truncate_preview(rendered)
    if lowered.startswith("error:") or "\nerror:" in lowered:
        return "tool_error", _truncate_preview(rendered)
    return "tool_result", _truncate_preview(rendered)


def _kb_validate_policy(project_root: Path, input_data: dict[str, Any]) -> tuple[bool, dict[str, Any], str, str]:
    normalized_kb_dir, kb_root, kb_path = resolve_repo_local_kb_path(
        input_data.get("kb_dir"),
        project_root=project_root,
    )
    updated_input = dict(input_data)
    updated_input["kb_dir"] = normalized_kb_dir
    requested_path = Path(normalized_kb_dir)
    if (
        requested_path.is_absolute()
        or ".." in requested_path.parts
        or (kb_path != kb_root and kb_root not in kb_path.parents)
    ):
        return (
            False,
            updated_input,
            "Denied `mcp__builder__kb_validate`: `kb_dir` must stay under `.agent-builder/knowledge/` in this repo.",
            'Retry with `{"kb_dir":"system-docs"}` or another relative directory under `.agent-builder/knowledge/`.',
        )
    return True, updated_input, "", ""


def _extract_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("No JSON object found in agent output.")


def _normalize_feature_list_payload(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    raw_features = payload.get("features", [])
    if not isinstance(raw_features, list) or not raw_features:
        raise ValueError("Feature list payload must include a non-empty features array.")

    normalized_features: list[dict[str, Any]] = []
    done = 0
    for index, feature in enumerate(raw_features, start=1):
        if not isinstance(feature, dict):
            continue
        title = str(feature.get("title", "")).strip()
        if not title:
            continue
        status = str(feature.get("status", "pending")).strip().lower() or "pending"
        if status == "done":
            done += 1
        normalized_features.append(
            {
                "id": str(feature.get("id") or f"feature-{index:02d}"),
                "title": title,
                "description": str(feature.get("description", "")).strip(),
                "status": status,
                "priority": str(feature.get("priority", max(1, 101 - index))),
                "acceptance_criteria": [
                    str(item).strip()
                    for item in feature.get("acceptance_criteria", [])
                    if str(item).strip()
                ],
                "dependencies": [
                    str(item).strip()
                    for item in feature.get("dependencies", [])
                    if str(item).strip()
                ],
            }
        )

    if not normalized_features:
        raise ValueError("Feature list payload did not contain any usable features.")

    pending = len(normalized_features) - done
    metadata = payload.get("metadata", {})
    project_name = (
        str(metadata.get("project", "")).strip() if isinstance(metadata, dict) else ""
    ) or project_root.name
    return {
        "metadata": {
            "project": project_name,
            "done": done,
            "pending": pending,
        },
        "features": normalized_features,
    }


def _extract_feature_list_payload(
    project_root: Path, text: str
) -> tuple[str, dict[str, Any] | None]:
    if _FEATURE_LIST_MARKER not in text:
        return text.strip(), None

    before, after = text.split(_FEATURE_LIST_MARKER, 1)
    payload = _normalize_feature_list_payload(project_root, _extract_json_object(after))
    return before.strip(), payload


def _feature_record_description(payload: dict[str, Any]) -> str:
    base = str(payload.get("description", "")).strip()
    acceptance_criteria = payload.get("acceptance_criteria", [])
    dependencies = payload.get("dependencies", [])
    sections: list[str] = []
    if base:
        sections.append(base)
    if acceptance_criteria:
        sections.append(
            "Acceptance criteria:\n"
            + "\n".join(f"- {item}" for item in acceptance_criteria if str(item).strip())
        )
    if dependencies:
        sections.append(
            "Dependencies:\n"
            + "\n".join(f"- {item}" for item in dependencies if str(item).strip())
        )
    return "\n\n".join(section for section in sections if section).strip()


def _normalize_feature_spec_payload(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    if not title:
        raise ValueError("Feature spec payload must include a title.")
    acceptance_criteria = [
        str(item).strip()
        for item in payload.get("acceptance_criteria", [])
        if str(item).strip()
    ]
    dependencies = [
        str(item).strip()
        for item in payload.get("dependencies", [])
        if str(item).strip()
    ]
    raw_priority = payload.get("priority", 50)
    try:
        priority = int(raw_priority)
    except (TypeError, ValueError):
        priority = 50
    return {
        "title": title,
        "description": _feature_record_description(
            {
                "description": str(payload.get("description", "")).strip(),
                "acceptance_criteria": acceptance_criteria,
                "dependencies": dependencies,
            }
        ),
        "priority": priority,
        "acceptance_criteria": acceptance_criteria,
        "dependencies": dependencies,
    }


def _extract_feature_spec_payload(text: str) -> tuple[str, dict[str, Any] | None]:
    if _FEATURE_SPEC_MARKER not in text:
        return text.strip(), None
    before, after = text.split(_FEATURE_SPEC_MARKER, 1)
    payload = _normalize_feature_spec_payload(_extract_json_object(after))
    return before.strip(), payload


def _message_requests_feature_spec(user_message: str) -> bool:
    lower_message = user_message.lower()
    if "documentation" in lower_message or "feature doc" in lower_message:
        return False
    if any(pattern in lower_message for pattern in _FEATURE_SPEC_INTENT_PATTERNS):
        return True
    if not any(pattern in lower_message for pattern in _FEATURE_REQUEST_ACTION_PATTERNS):
        return False
    return any(term in lower_message for term in _FEATURE_REQUEST_SCOPE_TERMS)


def _message_requests_feature_delivery(user_message: str) -> bool:
    lower_message = user_message.lower()
    if "documentation" in lower_message or "feature doc" in lower_message:
        return False
    if any(pattern in lower_message for pattern in _FEATURE_SPEC_INTENT_PATTERNS):
        return False
    if any(pattern in lower_message for pattern in _FEATURE_DELIVERY_CONTINUE_PATTERNS):
        return True
    if not any(pattern in lower_message for pattern in _FEATURE_REQUEST_ACTION_PATTERNS):
        return False
    return any(term in lower_message for term in _FEATURE_REQUEST_SCOPE_TERMS)


def _session_has_pending_feature_spec(session: ChatSession) -> bool:
    items = _history_items(session)
    if not items:
        return False
    requested = any(
        item.type == "user_message"
        and _message_requests_feature_spec(str(item.payload.get("content", "")))
        for item in items
    )
    if not requested:
        return False
    for item in items:
        if item.type != "assistant_message":
            continue
        content = str(item.payload.get("content", ""))
        if _FEATURE_SPEC_MARKER in content or "Feature saved to backlog as `" in content:
            return False
    return True


def _session_requests_feature_delivery(session: ChatSession) -> bool:
    items = _history_items(session)
    if not items:
        return False
    return any(
        item.type == "user_message"
        and _message_requests_feature_delivery(str(item.payload.get("content", "")))
        for item in items
    )


def _feature_spec_tool_denial(tool_name: str) -> tuple[bool, str]:
    if tool_name in _FEATURE_SPEC_BLOCKED_TOOLS:
        return (
            True,
            "Stay in the feature backlog interview lane. Use read-only repo discovery to ground "
            "the feature, then ask the next bounded user question with AskUserQuestion or emit "
            "FEATURE_SPEC_JSON once the scope is ready.",
        )
    if tool_name in {"Edit", "Write"}:
        return (
            True,
            "Stay in the feature backlog interview lane. Ask the next bounded user question "
            "with AskUserQuestion or emit FEATURE_SPEC_JSON before making implementation changes.",
        )
    return False, ""


def _message_has_documentation_intent(user_message: str) -> bool:
    lower_message = user_message.lower()
    return any(term in lower_message for term in _DOC_INTENT_TERMS)


def _message_suggests_recent_change(user_message: str) -> bool:
    lower_message = user_message.lower()
    return any(term in lower_message for term in _DOC_CHANGE_TERMS)


def _normalized_follow_up_message(user_message: str) -> str:
    collapsed = " ".join(user_message.lower().split())
    return re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", collapsed)


def _message_matches_documentation_continuation(user_message: str) -> bool:
    normalized = _normalized_follow_up_message(user_message)
    if not normalized or len(normalized.split()) > 4:
        return False
    return normalized in _DOCUMENTATION_CONTINUATION_PHRASES


def _task_required_docs(depends_on: dict[str, Any] | None) -> list[str]:
    if not isinstance(depends_on, dict):
        return []
    system_docs = depends_on.get("system_docs")
    if not isinstance(system_docs, dict):
        return []
    required_docs = system_docs.get("required_docs") or []
    if not isinstance(required_docs, list):
        return []
    return [str(item).strip() for item in required_docs if str(item).strip()]


def _task_has_doc_expectations(task: Task | None) -> bool:
    if task is None:
        return False
    if _task_required_docs(task.depends_on):
        return True
    haystacks = [
        str(task.title or "").lower(),
        str(task.description or "").lower(),
        str(getattr(task.feature, "title", "") or "").lower(),
        str(getattr(task.feature, "description", "") or "").lower(),
    ]
    return any(term in haystack for haystack in haystacks for term in _DOC_INTENT_TERMS)


def _documentation_testing_scope(user_message: str) -> str:
    lower_message = user_message.lower()
    for pattern, scope in _TESTING_SCOPE_PATTERNS:
        if pattern in lower_message:
            return scope
    return ""


def _documentation_target_doc_type(user_message: str, targeted_docs: list[dict[str, Any]]) -> str:
    lower_message = user_message.lower()
    if _documentation_testing_scope(user_message):
        return "testing"
    if "testing doc" in lower_message or "test documentation" in lower_message:
        return "testing"
    if any(str(doc.get("doc_type", "")) == "testing" for doc in targeted_docs):
        return "testing"
    if "feature doc" in lower_message or "feature documentation" in lower_message:
        return "feature"
    if any(str(doc.get("doc_type", "")) == "feature" for doc in targeted_docs):
        return "feature"
    return "system-docs"


def _documentation_mode(user_message: str, target_doc_type: str) -> str:
    lower_message = user_message.lower()
    if any(term in lower_message for term in _DOC_CREATE_TERMS):
        return "create"
    if target_doc_type == "system-docs" or any(
        term in lower_message for term in ("knowledge base", "knowledgebase", "system doc", "system docs")
    ):
        return "refresh"
    if any(term in lower_message for term in _DOC_REFRESH_TERMS):
        return "refresh"
    return "update"


def _resolve_documentation_action(
    *,
    user_message: str,
    targeted_docs: list[dict[str, Any]],
    current_branch: str,
    canonical_ref: str = CANONICAL_DOC_REF,
) -> dict[str, Any]:
    target_doc_type = _documentation_target_doc_type(user_message, targeted_docs)
    mode = _documentation_mode(user_message, target_doc_type)
    testing_scope = _documentation_testing_scope(user_message)
    freshness_mode = "canonical" if current_branch == canonical_ref else "advisory"
    doc_id = targeted_docs[0]["id"] if len(targeted_docs) == 1 else ""

    if target_doc_type == "system-docs":
        action = "extract" if freshness_mode == "canonical" else "advisory_only"
    elif mode == "create":
        action = "add" if not targeted_docs else "update"
    elif mode == "refresh" and freshness_mode != "canonical":
        action = "advisory_only"
    elif target_doc_type in {"feature", "testing"} and not targeted_docs:
        action = "add"
    elif target_doc_type in {"feature", "testing"} and len(targeted_docs) == 1:
        action = "update"
    elif target_doc_type in {"feature", "testing"} and len(targeted_docs) > 1:
        action = "blocked"
    else:
        action = "blocked"

    return {
        "action": action,
        "target_doc_type": target_doc_type,
        "mode": mode,
        "testing_scope": testing_scope,
        "freshness_mode": freshness_mode,
        "doc_id": doc_id,
        "requires_validate": action in {"add", "update", "extract"},
        "doc_exists": bool(targeted_docs),
        "targeted_doc_count": len(targeted_docs),
        "retry_budget": 1,
    }


async def _latest_task_context(db: AsyncSession) -> Task | None:
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.feature).selectinload(Feature.project))
        .order_by(Task.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _knowledge_doc_path(project_root: Path, doc_id: str) -> Path:
    return project_root / ".agent-builder" / "knowledge" / doc_id


def _doc_context_view(project_root: Path, doc: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "id": str(doc.get("id", "")),
        "title": str(doc.get("title", "")),
        "doc_type": str(doc.get("doc_type", "")),
        "task_id": str(doc.get("task_id", "")),
        "doc_family": str(doc.get("doc_family", "")),
        "tags": list(doc.get("tags", [])),
        "card_summary": str(doc.get("card_summary", "")),
        "detail_summary": str(doc.get("detail_summary", "")),
    }
    doc_path = _knowledge_doc_path(project_root, payload["id"])
    if not doc_path.exists():
        return payload
    parsed = parse_markdown_document(
        doc_path.read_text(encoding="utf-8"),
        default_doc_type=payload["doc_type"] or "context",
    )
    metadata = parsed.extra_fields
    payload.update(
        {
            "refresh_required": bool(metadata.get("refresh_required", False)),
            "updated": parsed.updated or "",
            "last_verified_at": str(metadata.get("last_verified_at", "") or ""),
            "lifecycle_status": str(metadata.get("lifecycle_status", "") or ""),
            "superseded_by": str(metadata.get("superseded_by", "") or ""),
            "linked_feature": str(metadata.get("linked_feature", "") or ""),
            "feature_id": str(metadata.get("feature_id", "") or ""),
            "documented_against_commit": str(metadata.get("documented_against_commit", "") or ""),
            "documented_against_ref": str(metadata.get("documented_against_ref", "") or ""),
            "owned_paths": metadata.get("owned_paths") if isinstance(metadata.get("owned_paths"), list) else [],
        }
    )
    return payload


def _search_targeted_docs(
    project_root: Path,
    *,
    query: str,
    task: Task | None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_doc(doc: dict[str, Any]) -> None:
        doc_id = str(doc.get("id", ""))
        if not doc_id or doc_id in seen or doc.get("doc_type") not in {"feature", "testing"}:
            return
        seen.add(doc_id)
        docs.append(_doc_context_view(project_root, doc))

    if task is not None:
        for doc in load_docs(scope="local"):
            if doc.get("doc_type") not in {"feature", "testing"}:
                continue
            if str(doc.get("task_id", "")) == task.id:
                add_doc(doc)
                if len(docs) >= limit:
                    return docs[:limit]
        for query_part in (task.title, getattr(task.feature, "title", "")):
            if not query_part:
                continue
            for doc in search_docs(query_part, scope="local", limit=limit):
                add_doc(doc)
                if len(docs) >= limit:
                    return docs[:limit]

    for doc in search_docs(query, scope="local", limit=limit):
        add_doc(doc)
        if len(docs) >= limit:
            break

    return docs[:limit]


def _freshness_candidates(project_root: Path, *, limit: int = 6) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for doc in load_docs(scope="local"):
        if doc.get("doc_type") not in {"feature", "testing"}:
            continue
        lifecycle_status = str(doc.get("lifecycle_status", "") or "").strip().lower()
        if lifecycle_status in {"superseded", "quarantined"}:
            continue
        metadata = {
            "created": doc.get("created_at", ""),
            "updated": doc.get("updated", ""),
            "linked_feature": doc.get("linked_feature", ""),
            "feature_id": doc.get("feature_id", ""),
            "task_id": doc.get("task_id", ""),
            "documented_against_commit": doc.get("documented_against_commit", ""),
            "documented_against_ref": doc.get("documented_against_ref", ""),
            "owned_paths": doc.get("owned_paths", []),
        }
        report = maintained_doc_report(
            workspace_path=project_root,
            doc_id=str(doc.get("id", "")),
            doc_type=str(doc.get("doc_type", "")),
            lifecycle_status=lifecycle_status or "active",
            metadata=metadata,
            created=str(doc.get("created_at", "") or ""),
            updated=str(doc.get("updated", "") or ""),
        ).to_dict()
        if report["status"] == "current":
            continue
        reports.append(report)
    reports.sort(key=lambda item: (item["blocking"], item["status"], item["doc_id"]), reverse=True)
    return reports[:limit]


async def _documentation_context_pack(
    db: AsyncSession,
    project_root: Path,
    user_message: str,
    *,
    route_reason_override: str | None = None,
    force_route: bool = False,
) -> dict[str, Any] | None:
    explicit_intent = _message_has_documentation_intent(user_message)
    feature_spec_request = _message_requests_feature_spec(user_message)
    recent_change_signal = _message_suggests_recent_change(user_message)
    latest_task = await _latest_task_context(db)
    task_has_doc_expectations = _task_has_doc_expectations(latest_task)
    if not force_route and (
        feature_spec_request
        or not explicit_intent
        and not (task_has_doc_expectations and recent_change_signal)
    ):
        return None

    task_payload: dict[str, Any] | None = None
    if latest_task is not None:
        task_payload = {
            "task_id": latest_task.id,
            "task_title": latest_task.title,
            "task_description": latest_task.description,
            "feature_id": latest_task.feature_id,
            "feature_title": getattr(latest_task.feature, "title", ""),
            "required_docs": _task_required_docs(latest_task.depends_on),
        }

    route_reason = route_reason_override or (
        "explicit_intent" if explicit_intent else "active_task_doc_expectation"
    )
    targeted_docs = _search_targeted_docs(
        project_root,
        query=user_message,
        task=latest_task,
        limit=4,
    )
    current_branch = git_current_branch(project_root) or ""
    canonical_ref = resolve_canonical_doc_ref(project_root)
    canonical_head = git_head_for_ref(project_root, canonical_ref) or ""
    resolution = _resolve_documentation_action(
        user_message=user_message,
        targeted_docs=targeted_docs,
        current_branch=current_branch,
        canonical_ref=canonical_ref,
    )
    return {
        "route_reason": route_reason,
        "project_root": str(project_root),
        "current_branch": current_branch,
        "canonical_ref": canonical_ref,
        "canonical_head": canonical_head,
        "canonical_refresh_mode": "canonical" if current_branch == canonical_ref else "advisory_only",
        "user_brief": " ".join(user_message.split())[:240],
        "task": task_payload,
        "recent_change_signal": recent_change_signal,
        "targeted_docs": targeted_docs,
        "resolved_action": resolution["action"],
        "target_doc_type": resolution["target_doc_type"],
        "mode": resolution["mode"],
        "testing_scope": resolution["testing_scope"],
        "freshness_mode": resolution["freshness_mode"],
        "doc_id": resolution["doc_id"],
        "requires_validate": resolution["requires_validate"],
        "doc_exists": resolution["doc_exists"],
        "targeted_doc_count": resolution["targeted_doc_count"],
        "retry_budget": resolution["retry_budget"],
        "freshness_candidates": _freshness_candidates(project_root),
    }


async def _most_recent_specialist_before_current_turn(
    db: AsyncSession,
    session_id: str,
    *,
    limit: int = 40,
) -> str | None:
    result = await db.execute(
        select(ChatEvent)
        .where(ChatEvent.session_id == session_id)
        .order_by(ChatEvent.created_at.desc(), ChatEvent.id.desc())
        .limit(limit)
    )
    user_message_count = 0
    for event in result.scalars():
        if event.event_type == "user_message":
            user_message_count += 1
            if user_message_count >= 2:
                break
            continue
        if user_message_count != 1 or event.event_type != "specialist_status":
            continue
        specialist = str((event.payload_json or {}).get("specialist", "")).strip()
        if specialist:
            return specialist
    return None


_SPECIALIST_ROUTE_POLICIES: dict[str, SpecialistRoutePolicy] = {
    "documentation-agent": SpecialistRoutePolicy(
        name="documentation-agent",
        explicit_intent_matcher=_message_has_documentation_intent,
        continuation_matcher=_message_matches_documentation_continuation,
        context_builder=_documentation_context_pack,
        auto_approve_tools=_DOCUMENTATION_AGENT_AUTO_APPROVE_TOOLS,
        active_summary="Documentation agent working on repo-local KB scope.",
        blocked_summary="Documentation agent hit a KB update or validation error.",
        completed_summary="Documentation refresh complete.",
    )
}


async def _select_specialist_route(
    db: AsyncSession,
    project_root: Path,
    session_id: str,
    user_message: str,
) -> ActiveSpecialistRoute | None:
    for policy in _SPECIALIST_ROUTE_POLICIES.values():
        if not policy.explicit_intent_matcher(user_message):
            continue
        context = await policy.context_builder(
            db,
            project_root,
            user_message,
            route_reason_override="explicit_intent",
            force_route=True,
        )
        if context is not None:
            return ActiveSpecialistRoute(policy=policy, route_reason="explicit_intent", context=context)

    previous_specialist = await _most_recent_specialist_before_current_turn(db, session_id)
    if previous_specialist:
        policy = _SPECIALIST_ROUTE_POLICIES.get(previous_specialist)
        if policy is not None and policy.continuation_matcher(user_message):
            route_reason = f"specialist_continuation:{policy.name}"
            context = await policy.context_builder(
                db,
                project_root,
                user_message,
                route_reason_override=route_reason,
                force_route=True,
            )
            if context is not None:
                return ActiveSpecialistRoute(
                    policy=policy,
                    route_reason=route_reason,
                    context=context,
                )

    for policy in _SPECIALIST_ROUTE_POLICIES.values():
        context = await policy.context_builder(db, project_root, user_message)
        if context is not None:
            route_reason = str(context.get("route_reason", "")).strip() or "implicit"
            return ActiveSpecialistRoute(policy=policy, route_reason=route_reason, context=context)

    return None


def _general_chat_prompt(
    project_root: Path,
    user_message: str,
    documentation_context: dict[str, Any] | None = None,
) -> str:
    prompt = (
        "You are a helpful AI assistant for the project rooted at "
        f"{project_root}.\n\n"
        "Answer the user's question directly. Use the repo context when it improves correctness. "
        "When a bounded user decision is required, use AskUserQuestion rather than writing a "
        "manual multiple-choice list in plain text.\n\n"
        f"Project root: {project_root}\n\n"
        f"User: {user_message}"
    )
    if not documentation_context:
        return prompt
    context_json = json.dumps(documentation_context, indent=2, sort_keys=True)
    return (
        f"{prompt}\n\n"
        "Documentation routing is active for this turn.\n"
        "- Invoke the `documentation-agent` specialist before your final answer.\n"
        "- Keep the work under `.agent-builder/knowledge` using canonical builder KB tools only.\n"
        "- Treat the maintained KB as shared product knowledge for both users and future agents.\n"
        "- Use the bounded context pack below first; fetch more through builder KB tools only if needed.\n"
        "- Respect the resolved documentation action from the context pack; do not make the specialist rediscover the lane from scratch.\n"
        "- For first-doc creation, the documentation agent must fetch the canonical KB contract and lint the draft before publishing.\n"
        "- Treat `main` as the canonical maintained-doc freshness baseline. On non-`main` branches, stay advisory-only and do not advance canonical commit baselines.\n"
        "- Use the `freshness_candidates` manifest to keep candidate selection diff-bounded before rereading maintained docs.\n"
        "- Refresh `system-docs` through the canonical extraction lane when broader app context is stale.\n"
        "- Ensure maintained feature docs remain agent-friendly: what the feature does, key files, change guidance, verification, and important reminders.\n"
        "- Do not edit repo docs under `docs/` or write memory.\n"
        "- If you still need a user decision, return to the main lane and use AskUserQuestion there.\n"
        "- Keep your final user-facing answer concise and normalize to one of: `already current`, "
        "`updated and verified`, or `partially updated; remaining gap: ...`.\n\n"
        "Documentation context pack:\n"
        f"{context_json}"
    )


def _feature_spec_chat_prompt(
    project_root: Path,
    user_message: str,
) -> str:
    return f"""You are the feature backlog planner for an already-initialized software project.

Your job is to turn a sufficiently bounded user request into one concrete backlog feature.

Rules:
- Use the existing session context. Treat short follow-up replies as answers to your most recent clarifying question when they resolve it.
- Keep the scope to one implementation-sized feature.
- Use read-only repo context first when it improves correctness.
- If the request is still ambiguous, continue the interview until the first implementation scope has no obvious gaps.
- Ask non-obvious clarifying questions that materially shape the feature contract.
- When there are a few clear choices, use AskUserQuestion with concise headers, short labels, and the recommended option first.
- Do not ask the user for technical facts that read-only repo discovery can answer.
- Do not repeat a question the user has already answered in the current session.
- Your responsibility stops at one agreed backlog feature. Do not invent task creation, dispatch, or execution progress in this lane.
- Do not produce documentation-agent output or maintained KB markdown.
- When the scope is ready, summarize the agreed feature briefly and emit the feature payload exactly as instructed below.

When the scope is NOT ready:
- Ask the next highest-leverage question.

When the scope IS ready:
- Start the response with `AGREEMENT:` followed by a concise implementation-oriented summary.
- Then emit `FEATURE_SPEC_JSON:` followed immediately by one raw JSON object and nothing else after that object.

The JSON object must match this shape exactly:
{{
  "title": "Meaningful feature title",
  "description": "What the feature delivers and its boundaries",
  "priority": 50,
  "acceptance_criteria": ["observable outcome 1", "observable outcome 2"],
  "dependencies": []
}}

Project root: {project_root}

User: {user_message}"""


async def _latest_project_id(db: AsyncSession) -> str | None:
    result = await db.execute(select(Project).order_by(Project.created_at.desc()).limit(1))
    project = result.scalar_one_or_none()
    return project.id if project is not None else None


async def _persist_feature_spec(db: AsyncSession, payload: dict[str, Any]) -> Feature | None:
    project_id = await _latest_project_id(db)
    if not project_id:
        return None
    feature = Feature(
        project_id=project_id,
        title=payload["title"],
        description=payload["description"],
        priority=payload["priority"],
    )
    db.add(feature)
    await db.commit()
    await db.refresh(feature)
    return feature


async def _create_feature_delivery_task(
    db: AsyncSession,
    feature: Feature,
    payload: dict[str, Any],
) -> Task:
    acceptance_criteria = [
        f"- {item}" for item in payload.get("acceptance_criteria", []) if str(item).strip()
    ]
    description_sections = [str(payload.get("description", "")).strip()]
    if acceptance_criteria:
        description_sections.append("Acceptance criteria:\n" + "\n".join(acceptance_criteria))
    task = Task(
        feature_id=feature.id,
        title=f"Deliver {feature.title}",
        description="\n\n".join(section for section in description_sections if section).strip(),
        complexity=min(max(len(acceptance_criteria), 1), 3),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def _schedule_task_dispatch(task_id: str) -> None:
    from autonomous_agent_builder.embedded.server.routes.tasks import _run_dispatch

    asyncio.create_task(_run_dispatch(task_id))


def _init_project_chat_prompt(project_root: Path, user_message: str) -> str:
    return f"""You are the requirements-phase interviewer for a brand-new software project.

Your job is to keep the conversation focused on defining the first shippable scope and
product direction before delivery work begins.

Rules:
- Ask only the highest-leverage follow-up questions needed to remove ambiguity.
- Prefer specific, product-shaping questions over generic brainstorming.
- Use bounded repo, workflow, knowledge, or web context when it materially improves correctness.
- When there are a few clear choices, use AskUserQuestion with concise headers, short labels, and the recommended option first.
- Do not generate feature JSON until the user has clearly agreed the scope is ready.
- Once scope is ready, summarize the agreement and emit the feature backlog payload exactly as instructed below.

When the scope is NOT ready:
- Ask the next highest-leverage question.

When the user clearly confirms the scope IS ready:
- Start the response with `AGREEMENT:` followed by a concise scope summary.
- Then emit `FEATURE_LIST_JSON:` followed immediately by one raw JSON object and nothing else after that object.

The JSON object must match this shape exactly:
{{
  "metadata": {{
    "project": "{project_root.name}",
    "done": 0,
    "pending": <number of pending features>
  }},
  "features": [
    {{
      "id": "feature-01",
      "title": "Meaningful feature title",
      "description": "What the feature delivers",
      "status": "pending",
      "priority": "100",
      "acceptance_criteria": ["observable outcome 1", "observable outcome 2"],
      "dependencies": []
    }}
  ]
}}

Project root: {project_root}

User: {user_message}"""


async def _run_chat_turn(app: Any, session_id: str, user_message: str) -> None:
    project_root = Path(app.state.project_root)
    hub: ChatSessionHub = app.state.chat_hub
    runner = AgentRunner(get_settings())
    agent_name = _active_chat_agent_name(project_root)
    agent_def = get_agent_definition(agent_name)

    session_factory = get_session_factory()
    active_specialist: ActiveSpecialistRoute | None = None
    async with session_factory() as db:
        session = await _load_session(db, session_id, project_root=project_root, reject_scope_mismatch=True)
        if session is None:
            raise RuntimeError(f"Chat session '{session_id}' not found")
        resume_session = session.sdk_session_id
        if agent_name == "chat":
            active_specialist = await _select_specialist_route(
                db,
                project_root,
                session_id,
                user_message,
            )
    documentation_context = (
        active_specialist.context if active_specialist and active_specialist.name == "documentation-agent" else None
    )
    specialist_active = active_specialist is not None
    specialist_phase = ""
    specialist_summary = ""

    run_status_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload=_initial_status(agent_name),
        status="running",
    )
    await hub.publish(session_id, _serialize_event(run_status_event).model_dump(mode="json"))

    async def publish_specialist_status(phase: str, content: str, *, status: str = "running") -> None:
        if active_specialist is None:
            return
        payload = {
            "specialist": active_specialist.name,
            "route_reason": active_specialist.route_reason,
            "phase": phase,
            "content": content,
        }
        specialist_event = await _append_chat_event(
            session_id,
            event_type="specialist_status",
            payload={
                **payload,
                "diagnostic": summarize_chat_event("specialist_status", payload),
            },
            status=status,
        )
        await hub.publish(session_id, _serialize_event(specialist_event).model_dump(mode="json"))

    if specialist_active:
        specialist_phase = "discovering"
        specialist_summary = active_specialist.policy.active_summary
        await publish_specialist_status(
            specialist_phase,
            specialist_summary,
            status="running",
        )

    async def on_stream(text: str) -> None:
        await hub.publish(
            session_id,
            {
                "id": f"stream:{session_id}",
                "type": "assistant_stream_delta",
                "status": "streaming",
                "timestamp": utcnow().isoformat(),
                "payload": {"content": text},
            },
        )

    async def on_tool_event(event_data: dict[str, Any]) -> None:
        nonlocal specialist_phase
        event_type, content = _normalize_tool_response(event_data.get("tool_response", ""))
        tool_name = str(event_data.get("tool_name", "") or "")
        if not tool_name:
            return
        payload = {
            "tool_name": tool_name,
            "tool_input": event_data.get("tool_input", {}) or {},
            "content": content,
            "diagnostic": summarize_tool_event(
                event_type=event_type,
                tool_name=tool_name,
                tool_input=event_data.get("tool_input", {}) or {},
                tool_response=event_data.get("tool_response", ""),
            ),
        }
        tool_use_id = event_data.get("tool_use_id")
        tool_event = await _append_chat_event(
            session_id,
            event_type=event_type,
            payload=payload,
            status="completed",
            tool_use_id=str(tool_use_id) if tool_use_id else None,
        )
        await hub.publish(session_id, _serialize_event(tool_event).model_dump(mode="json"))
        if tool_name == "TodoWrite":
            todos = event_data.get("tool_input", {}).get("todos", []) or []
            todo_event = await _append_chat_event(
                session_id,
                event_type="todo_snapshot",
                payload={
                    "todos": todos,
                    "pending_count": sum(1 for todo in todos if todo.get("status") == "pending"),
                    "in_progress_count": sum(1 for todo in todos if todo.get("status") == "in_progress"),
                    "completed_count": sum(1 for todo in todos if todo.get("status") == "completed"),
                },
                status="completed",
                tool_use_id=str(tool_use_id) if tool_use_id else None,
            )
            await hub.publish(session_id, _serialize_event(todo_event).model_dump(mode="json"))
        if specialist_active:
            next_phase = ""
            if tool_name.endswith("__kb_search") or tool_name.endswith("__task_show"):
                next_phase = "discovering"
            elif tool_name.endswith("__kb_contract"):
                next_phase = "discovering"
            elif tool_name.endswith("__kb_lint"):
                next_phase = "publishing"
            elif tool_name.endswith("__kb_add") or tool_name.endswith("__kb_update"):
                next_phase = "publishing"
            elif tool_name.endswith("__kb_show") or tool_name.endswith("__kb_validate"):
                next_phase = "verifying"
            if next_phase and next_phase != specialist_phase:
                phase_label = next_phase.capitalize()
                await publish_specialist_status(
                    next_phase,
                    f"{active_specialist.policy.name} {phase_label.lower()} repo-local KB docs.",
                    status="running",
                )
                specialist_phase = next_phase

    async def can_use_tool(tool_name: str, input_data: dict[str, Any], context: Any) -> Any:
        if tool_name == "AskUserQuestion":
            answers: dict[str, str] = {}
            for question in input_data.get("questions", []):
                question_event = await _append_chat_event(
                    session_id,
                    event_type="ask_user_question",
                    payload={
                        "header": question.get("header", ""),
                        "question": question.get("question", ""),
                        "options": question.get("options", []),
                        "multi_select": bool(question.get("multiSelect")),
                        "recommended_index": 0,
                        "answered": False,
                        "answer_value": "",
                    },
                    status="pending",
                )
                future = await hub.create_pending_answer(session_id, question_event.id)
                await hub.publish(
                    session_id,
                    _serialize_event(question_event).model_dump(mode="json"),
                )
                response = await future
                answer_value = str(response.get("answer_value", "")).strip()
                answers[str(question.get("question", ""))] = answer_value

            return _permission_allow(
                {
                    "questions": input_data.get("questions", []),
                    "answers": answers,
                }
            )

        if feature_spec_requested:
            deny_tool, deny_reason = _feature_spec_tool_denial(tool_name)
            if deny_tool:
                denial_content = {
                    "status": "error",
                    "error": {
                        "code": "permission_denied",
                        "message": deny_reason,
                        "hint": "Use AskUserQuestion for the next bounded requirement decision or emit FEATURE_SPEC_JSON once the scope is ready.",
                        "detail": {
                            "tool_name": tool_name,
                            "lane": "feature_spec",
                        },
                    },
                    "schema_version": "1",
                }
                payload = {
                    "tool_name": tool_name,
                    "tool_input": input_data,
                    "content": json.dumps(denial_content, ensure_ascii=True, sort_keys=True),
                    "diagnostic": summarize_tool_event(
                        event_type="tool_error",
                        tool_name=tool_name,
                        tool_input=input_data,
                        tool_response=denial_content,
                    ),
                }
                tool_event = await _append_chat_event(
                    session_id,
                    event_type="tool_error",
                    payload=payload,
                    status="completed",
                )
                await hub.publish(session_id, _serialize_event(tool_event).model_dump(mode="json"))
                return _permission_deny(deny_reason)

        if (
            active_specialist is not None
            and active_specialist.name == "documentation-agent"
            and tool_name == "mcp__builder__kb_validate"
        ):
            allowed, updated_input, deny_reason, next_action = _kb_validate_policy(
                project_root,
                input_data,
            )
            if allowed:
                return _permission_allow(updated_input)

            denial_content = {
                "status": "error",
                "error": {
                    "code": "permission_denied",
                    "message": deny_reason,
                    "hint": next_action,
                    "detail": {
                        "kb_dir": updated_input.get("kb_dir", "system-docs"),
                        "safe_lane": ".agent-builder/knowledge/<kb_dir>",
                    },
                },
                "schema_version": "1",
            }
            payload = {
                "tool_name": tool_name,
                "tool_input": updated_input,
                "content": json.dumps(denial_content, ensure_ascii=True, sort_keys=True),
                "diagnostic": summarize_tool_event(
                    event_type="tool_error",
                    tool_name=tool_name,
                    tool_input=updated_input,
                    tool_response=denial_content,
                ),
            }
            tool_event = await _append_chat_event(
                session_id,
                event_type="tool_error",
                payload=payload,
                status="completed",
            )
            await hub.publish(session_id, _serialize_event(tool_event).model_dump(mode="json"))
            return _permission_deny(f"{deny_reason} {next_action}")

        if active_specialist is not None and tool_name in active_specialist.policy.auto_approve_tools:
            return _permission_allow(input_data)

        summary, description = _tool_summary(tool_name, input_data)
        approval_event = await _append_chat_event(
            session_id,
            event_type="tool_approval_request",
            payload={
                "tool_name": tool_name,
                "tool_input": input_data,
                "summary": summary,
                "description": description,
                "answered": False,
                "decision": "",
                "reason": "",
            },
            status="pending",
        )
        future = await hub.create_pending_answer(session_id, approval_event.id)
        await hub.publish(
            session_id,
            _serialize_event(approval_event).model_dump(mode="json"),
        )
        response = await future
        decision = str(response.get("decision", "deny")).strip().lower() or "deny"
        reason = str(response.get("reason", "")).strip()
        if decision == "allow":
            return _permission_allow(response.get("updated_input") or input_data)
        return _permission_deny(reason or f"User denied {tool_name}.")

    try:
        feature_spec_requested = (
            agent_name == "chat"
            and active_specialist is None
            and (
                _message_requests_feature_spec(user_message)
                or _session_has_pending_feature_spec(session)
            )
        )
        feature_delivery_requested = feature_spec_requested and _session_requests_feature_delivery(session)
        prompt = (
            _init_project_chat_prompt(project_root, user_message)
            if agent_name == "init-project-chat"
            else _feature_spec_chat_prompt(project_root, user_message)
            if feature_spec_requested
            else _general_chat_prompt(project_root, user_message, documentation_context)
        )
        result: RunResult = await runner.run_phase(
            agent_name=agent_name,
            prompt=prompt,
            workspace_path=str(project_root),
            resume_session=resume_session,
            subagents=(active_specialist.name,) if active_specialist is not None else None,
            on_stream=on_stream,
            can_use_tool=can_use_tool,
            on_tool_event=on_tool_event,
        )

        if result.error:
            if specialist_active:
                await publish_specialist_status(
                    "blocked",
                    active_specialist.policy.blocked_summary,
                    status="completed",
                )
            error_content = f"Error: {result.error}"
            error_event = await _append_chat_event(
                session_id,
                event_type="run_error",
                payload={"content": error_content},
                status="completed",
                mirror_message=("assistant", error_content, 0, 0.0),
            )
            await hub.publish(session_id, _serialize_event(error_event).model_dump(mode="json"))
            status_event = await _append_chat_event(
                session_id,
                event_type="run_status",
                payload={
                    "running": False,
                    "error": result.error,
                    "sdk_session_id": result.session_id,
                    "duration_ms": result.duration_ms,
                    "stop_reason": result.stop_reason,
                },
                status="completed",
            )
            await hub.publish(session_id, _serialize_event(status_event).model_dump(mode="json"))
            return

        visible_response = result.output_text or "No response from agent"
        if agent_name == "init-project-chat":
            visible_response, feature_payload = _extract_feature_list_payload(project_root, visible_response)
            if feature_payload is not None:
                write_feature_list_file(project_root, feature_payload)
                save_note = (
                    "Feature backlog saved to `.claude/progress/feature-list.json`. "
                    "Open Backlog to review it."
                )
            visible_response = (
                f"{visible_response}\n\n{save_note}".strip()
                if visible_response
                else save_note
            )
        elif feature_spec_requested:
            visible_response, feature_spec_payload = _extract_feature_spec_payload(visible_response)
            if feature_spec_payload is not None:
                session_factory = get_session_factory()
                async with session_factory() as db:
                    feature = await _persist_feature_spec(db, feature_spec_payload)
                    delivery_task = None
                    if feature is not None and feature_delivery_requested:
                        delivery_task = await _create_feature_delivery_task(
                            db, feature, feature_spec_payload
                        )
                if feature is not None:
                    if delivery_task is not None:
                        await _schedule_task_dispatch(delivery_task.id)
                        save_note = (
                            f"Feature saved to backlog as `{feature.title}`. "
                            f"Created task `{delivery_task.title}` and started planning dispatch. "
                            "Open Board to follow progress."
                        )
                    else:
                        save_note = (
                            f"Feature saved to backlog as `{feature.title}`. "
                            "Open Backlog to review it."
                        )
                    visible_response = (
                        f"{visible_response}\n\n{save_note}".strip()
                        if visible_response
                        else save_note
                    )
        if specialist_active:
            await publish_specialist_status(
                "completed",
                active_specialist.policy.completed_summary,
                status="completed",
            )

        session_factory = get_session_factory()
        async with session_factory() as db:
            session = await db.get(ChatSession, session_id)
            if session is not None and result.session_id:
                session.sdk_session_id = result.session_id
                session.updated_at = utcnow()
                await db.commit()

        assistant_event = await _append_chat_event(
            session_id,
            event_type="assistant_message",
            payload={"content": visible_response, "final": True},
            status="completed",
            mirror_message=(
                "assistant",
                visible_response,
                result.tokens_input + result.tokens_output,
                result.cost_usd,
            ),
        )
        await hub.publish(session_id, _serialize_event(assistant_event).model_dump(mode="json"))
        status_event = await _append_chat_event(
            session_id,
            event_type="run_status",
            payload={
                "running": False,
                "current_turn": result.num_turns,
                "max_turns": agent_def.max_turns,
                "tokens_used": result.tokens_input + result.tokens_output,
                "cost_usd": result.cost_usd,
                "sdk_session_id": result.session_id,
                "duration_ms": result.duration_ms,
                "stop_reason": result.stop_reason,
            },
            status="completed",
        )
        await hub.publish(session_id, _serialize_event(status_event).model_dump(mode="json"))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if specialist_active:
            await publish_specialist_status(
                "blocked",
                f"{active_specialist.policy.name} stopped: {exc}",
                status="completed",
            )
        error_content = f"Error: {exc}"
        error_event = await _append_chat_event(
            session_id,
            event_type="run_error",
            payload={"content": error_content},
            status="completed",
            mirror_message=("assistant", error_content, 0, 0.0),
        )
        await hub.publish(session_id, _serialize_event(error_event).model_dump(mode="json"))
        status_event = await _append_chat_event(
            session_id,
            event_type="run_status",
            payload={"running": False, "error": str(exc)},
            status="completed",
        )
        await hub.publish(session_id, _serialize_event(status_event).model_dump(mode="json"))


@router.get("/agent/chat/sessions", response_model=ChatSessionListResponse)
async def list_chat_sessions(request: Request, db: AsyncSession = Depends(get_db)):
    """List available chat sessions so older threads remain accessible after reset."""
    project_root = _project_root(request)
    sessions = await _list_scoped_sessions(db, project_root)
    latest_resume_session = _latest_resume_candidate(sessions)

    return ChatSessionListResponse(
        repo_identity=_repo_identity(project_root),
        workspace_cwd=_workspace_cwd(project_root),
        latest_resume_session_id=latest_resume_session.id if latest_resume_session else None,
        sessions=[
            ChatSessionItem(
                id=session.id,
                sdk_session_id=session.sdk_session_id,
                created_at=session.created_at.isoformat(),
                updated_at=session.updated_at.isoformat(),
                message_count=len(_history_items(session)),
                preview=_session_preview(session),
                workspace_cwd=session.workspace_cwd,
                is_resume_candidate=latest_resume_session is not None and session.id == latest_resume_session.id,
            )
            for session in sessions
        ]
    )


@router.get("/agent/chat/meta", response_model=ChatMetaResponse)
async def get_chat_meta(request: Request):
    """Return stable chat-lane metadata used before a session exists."""
    project_root = _project_root(request)
    return ChatMetaResponse(
        model=_chat_model_name(project_root),
        repo_identity=_repo_identity(project_root),
        workspace_cwd=_workspace_cwd(project_root),
    )


@router.get("/agent/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    request: Request,
    session_id: str | None = None,
    fresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Get chat history for a session, bootstrapping init-project chat when needed."""

    project_root = _project_root(request)
    session = await _load_session(
        db,
        session_id,
        project_root=project_root,
        reject_scope_mismatch=bool(session_id),
    )
    scoped_sessions = await _list_scoped_sessions(db, project_root)

    if not fresh and session is None and session_id is None:
        session = _latest_resume_candidate(scoped_sessions)

    if not fresh and session is None and _needs_init_project_bootstrap(project_root):
        bootstrap_session_id = await ensure_init_project_bootstrap_session(project_root, db)
        await db.commit()
        session = await _load_session(db, bootstrap_session_id, project_root=project_root)

    if not fresh and session is None and session_id is None and scoped_sessions:
        session = scoped_sessions[0]

    if session is None:
        return ChatHistoryResponse(
            session_id="",
            sdk_session_id=None,
            model=_chat_model_name(project_root),
            repo_identity=_repo_identity(project_root),
            workspace_cwd=_workspace_cwd(project_root),
            items=[],
            messages=[],
            status=None,
        )

    items = _history_items(session)
    return ChatHistoryResponse(
        session_id=session.id,
        sdk_session_id=session.sdk_session_id,
        model=_chat_model_name(project_root),
        repo_identity=_repo_identity(project_root),
        workspace_cwd=_workspace_cwd(project_root),
        items=items,
        messages=_legacy_messages(items),
        status=_latest_status(session),
    )


@router.get("/agent/chat/stream")
async def chat_stream(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Stream live chat session timeline events as SSE."""

    project_root = _project_root(request)
    session = await _load_session(db, session_id, project_root=project_root, reject_scope_mismatch=True)
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    hub = _chat_hub(request)
    queue = await hub.register_session(session_id)
    snapshot = ChatHistoryResponse(
        session_id=session.id,
        model=_chat_model_name(project_root),
        repo_identity=_repo_identity(project_root),
        workspace_cwd=_workspace_cwd(project_root),
        items=_history_items(session),
        messages=_legacy_messages(_history_items(session)),
        status=_latest_status(session),
    ).model_dump(mode="json")

    async def event_generator():
        try:
            yield {"event": "snapshot", "data": json.dumps(snapshot)}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield {"event": event["event"], "data": json.dumps(event["data"])}
                except TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            await hub.unregister_session(session_id, queue)

    return EventSourceResponse(event_generator())


@router.post("/agent/chat", response_model=ChatResponse)
async def agent_chat(
    request: ChatRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """Persist a user turn, then launch the agent run asynchronously."""

    project_root = _project_root(req)
    agent_name = _active_chat_agent_name(project_root)
    agent_def = get_agent_definition(agent_name)

    session = await _load_session(
        db,
        request.session_id,
        project_root=project_root,
        reject_scope_mismatch=bool(request.session_id),
    )
    if session is None and _needs_init_project_bootstrap(project_root):
        bootstrap_session_id = await ensure_init_project_bootstrap_session(project_root, db)
        await db.commit()
        session = await _load_session(db, bootstrap_session_id, project_root=project_root)

    if session is None:
        session = ChatSession()
        _stamp_session_scope(session, project_root)
        db.add(session)
        await db.flush()
        await db.commit()
        session = await _load_session(db, session.id, project_root=project_root)

    if session is None:
        raise HTTPException(status_code=500, detail="Failed to initialize chat session")

    hub = _chat_hub(req)
    if await hub.has_active_run(session.id):
        raise HTTPException(status_code=409, detail="This chat session is waiting on the current run.")

    user_event = await _append_chat_event(
        session.id,
        event_type="user_message",
        payload={"content": request.message},
        status="completed",
        mirror_message=("user", request.message, 0, 0.0),
    )
    await hub.publish(session.id, _serialize_event(user_event).model_dump(mode="json"))

    task = asyncio.create_task(_run_chat_turn(req.app, session.id, request.message))
    attached = await hub.attach_run(session.id, task)
    if not attached:
        task.cancel()
        raise HTTPException(status_code=409, detail="This chat session is already running.")

    return ChatResponse(
        response="Run started.",
        session_id=session.id,
        model=agent_def.model,
        status=_initial_status(agent_name),
    )


@router.post("/agent/chat/respond", response_model=ChatRespondResponse)
async def respond_to_chat_event(
    request: ChatRespondRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """Submit an answer for a pending question or tool approval card."""

    hub = _chat_hub(req)
    if not await hub.has_pending_answer(request.event_id):
        raise HTTPException(status_code=409, detail="This interaction is no longer pending.")

    event = await db.get(ChatEvent, request.event_id)
    if event is None or event.session_id != request.session_id:
        raise HTTPException(status_code=404, detail="Chat interaction not found")

    if event.event_type == "ask_user_question":
        answer_value = request.custom_text.strip()
        if not answer_value:
            answer_value = ", ".join(option.strip() for option in request.selected_options if option.strip())
        if not answer_value:
            raise HTTPException(status_code=400, detail="Select an option or provide a custom answer.")

        updated_event = await _update_request_event(
            request.event_id,
            payload_patch={"answered": True, "answer_value": answer_value},
            status="answered",
            answer_event_type="ask_user_question_answer",
            answer_payload={
                "question": event.payload_json.get("question", ""),
                "answer_value": answer_value,
            },
        )
        await hub.publish(request.session_id, _serialize_event(updated_event).model_dump(mode="json"))
        resolved = await hub.resolve_pending_answer(
            request.event_id,
            {"answer_value": answer_value},
        )
        if not resolved:
            raise HTTPException(status_code=409, detail="This interaction is no longer pending.")
        return ChatRespondResponse(ok=True, session_id=request.session_id, event_id=request.event_id)

    if event.event_type != "tool_approval_request":
        raise HTTPException(status_code=400, detail="Unsupported chat interaction type")

    decision = (request.decision or "").strip().lower()
    if decision not in {"allow", "deny"}:
        raise HTTPException(status_code=400, detail="Tool approvals require an allow or deny decision.")

    updated_event = await _update_request_event(
        request.event_id,
        payload_patch={"answered": True, "decision": decision, "reason": request.reason.strip()},
        status="answered",
        answer_event_type="tool_approval_answer",
        answer_payload={
            "tool_name": event.payload_json.get("tool_name", ""),
            "decision": decision,
            "reason": request.reason.strip(),
        },
    )
    await hub.publish(request.session_id, _serialize_event(updated_event).model_dump(mode="json"))
    resolved = await hub.resolve_pending_answer(
        request.event_id,
        {
            "decision": decision,
            "reason": request.reason.strip(),
            "updated_input": request.updated_input,
        },
    )
    if not resolved:
        raise HTTPException(status_code=409, detail="This interaction is no longer pending.")
    return ChatRespondResponse(ok=True, session_id=request.session_id, event_id=request.event_id)
