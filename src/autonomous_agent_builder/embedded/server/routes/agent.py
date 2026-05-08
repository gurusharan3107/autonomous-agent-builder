"""Agent chat API routes for embedded server."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from autonomous_agent_builder.agents.definitions import (
    get_agent_definition,
    get_subagent_definition,
)
from autonomous_agent_builder.agents.execution_policy import resolve_agent_runtime_policy
from autonomous_agent_builder.agents.runner import AgentRunner, RunResult
from autonomous_agent_builder.agents.tool_registry import is_read_only_tool
from autonomous_agent_builder.backlog_items import feature_to_item_payload, mirror_item_to_artifact
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import (
    Approval,
    ApprovalDecision,
    ApprovalGate,
    ApprovalLog,
    BacklogItemType,
    ChatEvent,
    ChatMessage,
    ChatSession,
    Feature,
    FeatureStatus,
    Project,
    Sprint,
    Task,
    TaskStatus,
    set_task_status,
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
    publish_onboarding_snapshot,
    select_delivery_project,
    sync_forward_engineering_feature_backlog,
    write_feature_list_file,
)
from autonomous_agent_builder.runtime import create_runtime
from autonomous_agent_builder.runtime.factory import resolve_runtime_config
from autonomous_agent_builder.services.readiness import (
    READY_STATE,
    assess_readiness,
    load_readiness_status,
)
from autonomous_agent_builder.services.runtime_guidance import (
    update_project_context_block,
)
from autonomous_agent_builder.services.runtime_settings import (
    persist_runtime_settings,
    reconcile_runtime_project_state,
    resolve_project_runtime_config,
    runtime_settings_payload,
)
from autonomous_agent_builder.services.sprint_execution import persist_sprint_execution_artifacts

router = APIRouter()

_FEATURE_LIST_MARKER = "FEATURE_LIST_JSON:"
_FEATURE_SPEC_MARKER = "FEATURE_SPEC_JSON:"
_INIT_PROJECT_MAX_REQUIREMENTS_CONTINUATIONS = 6
_FRAMEWORK_CONSTRAINTS = (
    ("flask", "Use Flask as the Python web framework"),
    ("fastapi", "Use FastAPI as the Python web framework"),
    ("django", "Use Django as the Python web framework"),
    ("express", "Use Express as the Node web framework"),
    ("next.js", "Use Next.js as the web framework"),
    ("nextjs", "Use Next.js as the web framework"),
    ("react", "Use React for the frontend"),
    ("vue", "Use Vue for the frontend"),
    ("svelte", "Use Svelte for the frontend"),
)
_STACK_CONSTRAINTS = (
    ("plain html and javascript", "Use plain HTML and JavaScript"),
    ("vanilla javascript", "Use vanilla JavaScript"),
    ("sqlite", "Use SQLite for persistence"),
    ("postgres", "Use PostgreSQL for persistence"),
    ("postgresql", "Use PostgreSQL for persistence"),
)
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
_USER_QUESTION_TOOL_NAMES = {
    "AskUserQuestion",
    "request_user_input",
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
    "i would like",
    "can you add",
    "could you add",
    "please add",
    "can you build",
    "could you build",
    "can you make",
    "could you make",
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
    "app",
    "todo",
    "todos",
    "filter",
    "filters",
    "active",
    "completed",
    "unfinished",
    "save",
    "bookmark",
    "bookmarks",
)
_FEATURE_DELIVERY_CONTINUE_PATTERNS = (
    "take this through",
    "next steps",
    "go ahead and implement",
    "go ahead and build",
    "build it",
    "build this",
    "implement this",
    "ship it",
    "ship this",
    "ship next",
    "ship the next",
    "ship the next feature",
    "do it",
    "deliver this",
    "dispatch it",
    "start delivery",
    "create the delivery task",
)
_NATURAL_DELIVERY_CONFIRMATION_PATTERNS = (
    "yes",
    "yes please",
    "please start",
    "start now",
    "start it now",
    "that sounds good",
    "that sounds right",
    "sounds good",
    "sounds right",
    "looks good",
    "let's do it",
    "lets do it",
)
_AUTONOMOUS_CONTINUATION_PATTERNS = (
    "continue building",
    "keep building",
    "keep going",
    "continue",
    "proceed",
    "go ahead",
    "get started",
    "move forward",
    "start with the task",
    "start the task",
    "continue my app",
    "continue the app",
    "continue this app",
    "continue the build",
    "continue building my app",
    "build my app",
    "finish my app",
    "finish it",
    "finish this",
    "complete it",
    "complete this",
    "next useful improvement",
    "next improvement",
    "ship the next useful",
    "ship the next improvement",
    "build the next useful",
    "build the next improvement",
)
_AMBIGUOUS_CONTINUATION_PATTERNS = (
    "continue",
    "proceed",
    "go ahead",
    "get started",
    "start with the task",
    "start the task",
)
_DELIVERY_PROGRESS_ACTION_TOKENS = {
    "continue",
    "proceed",
    "start",
    "plan",
    "build",
    "ship",
    "deliver",
    "implement",
    "execute",
    "queue",
    "finish",
    "complete",
    "advance",
    "move",
    "resume",
    "work",
}
_DELIVERY_PROGRESS_SCOPE_TOKENS = {
    "next",
    "sprint",
    "backlog",
    "feature",
    "improvement",
    "item",
    "task",
    "app",
    "product",
    "work",
}
_SPRINT_PLANNING_INTENT_PATTERNS = (
    "sprint planning",
    "start next sprint",
    "start the next sprint",
    "start a new sprint",
    "start new sprint",
    "plan the sprint",
    "plan sprint",
    "plan next sprint",
    "plan the next sprint",
    "queue the sprint",
    "queue these backlog items",
    "queue all backlog items",
    "queue all current backlog items",
    "queue all current product backlog items",
    "queue all product backlog items",
    "queue current backlog",
    "queue current product backlog",
    "move to sprint backlog",
)
_SPRINT_PLANNING_ALL_PATTERNS = (
    "all",
    "everything",
    "all current product backlog items",
    "all product backlog items",
    "entire product backlog",
    "current backlog",
)
_SPRINT_PLANNING_SELECTION_PROMPT = (
    "Sprint planning is ready. Reply with `all` to move every product backlog item into sprint backlog, "
    "or reply with one or more backlog IDs/titles."
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
    effort: str | None = None
    runtime_sdk: str | None = None
    provider: str | None = None
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
    effort: str | None = None
    runtime_sdk: str | None = None
    provider: str | None = None
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


class RuntimeSettingsUpdate(BaseModel):
    sdk: str
    provider: str | None = None
    model: str | None = None
    api_base_url: str | None = None
    api_key_env: str | None = None
    codex_profile: str | None = None
    sandbox_mode: str | None = None
    approval_policy: str | None = None
    tracing: str | None = None


class ChatMetaResponse(BaseModel):
    model: str
    effort: str | None = None
    runtime_sdk: str | None = None
    provider: str | None = None
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


async def _has_builder_work_state(db: AsyncSession) -> bool:
    for model in (Task, Feature):
        result = await db.execute(select(model.id).limit(1))
        if result.scalar_one_or_none() is not None:
            return True
    return False


async def _has_dispatchable_task_state(db: AsyncSession) -> bool:
    result = await db.execute(
        select(Task.id)
        .where(Task.status.in_([TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.PLANNING]))
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _first_dispatchable_task(db: AsyncSession) -> Task | None:
    sprint_result = await db.execute(
        select(Sprint)
        .where(Sprint.generated_task_ids.is_not(None))
        .order_by(Sprint.created_at.desc())
    )
    for sprint in sprint_result.scalars().all():
        generated_task_ids = [
            str(task_id).strip()
            for task_id in (sprint.generated_task_ids or [])
            if str(task_id).strip()
        ]
        if not generated_task_ids:
            continue
        task_result = await db.execute(
            select(Task).where(
                Task.id.in_(generated_task_ids),
                Task.status.in_([TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.PLANNING]),
            )
        )
        tasks_by_id = {task.id: task for task in task_result.scalars().all()}
        for task_id in generated_task_ids:
            task = tasks_by_id.get(task_id)
            if task is not None:
                return task

    result = await db.execute(
        select(Task)
        .where(Task.status.in_([TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.PLANNING]))
        .order_by(Task.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _first_pending_review_approval(db: AsyncSession) -> tuple[ApprovalGate, Task] | None:
    sprint_result = await db.execute(
        select(Sprint)
        .where(Sprint.generated_task_ids.is_not(None))
        .order_by(Sprint.created_at.desc())
    )
    for sprint in sprint_result.scalars().all():
        generated_task_ids = [
            str(task_id).strip()
            for task_id in (sprint.generated_task_ids or [])
            if str(task_id).strip()
        ]
        if not generated_task_ids:
            continue
        gate_result = await db.execute(
            select(ApprovalGate)
            .options(selectinload(ApprovalGate.task))
            .where(
                ApprovalGate.status == "pending",
                ApprovalGate.gate_type == "pr",
                ApprovalGate.task_id.in_(generated_task_ids),
            )
        )
        gates_by_task_id = {gate.task_id: gate for gate in gate_result.scalars().all()}
        for task_id in generated_task_ids:
            gate = gates_by_task_id.get(task_id)
            if gate is not None and gate.task is not None:
                return gate, gate.task

    result = await db.execute(
        select(ApprovalGate)
        .options(selectinload(ApprovalGate.task))
        .where(ApprovalGate.status == "pending", ApprovalGate.gate_type == "pr")
        .order_by(ApprovalGate.created_at.asc())
        .limit(1)
    )
    gate = result.scalar_one_or_none()
    if gate is None or gate.task is None:
        return None
    return gate, gate.task


async def _approve_review_gate_for_continuation(db: AsyncSession) -> Task | None:
    gate_and_task = await _first_pending_review_approval(db)
    if gate_and_task is None:
        return None
    gate, task = gate_and_task
    approval = Approval(
        approval_gate_id=gate.id,
        approver_email="agent-chat@local",
        decision=ApprovalDecision.APPROVE,
        comment="Approved from Agent chat continuation intent.",
    )
    db.add(approval)
    db.add(
        ApprovalLog(
            task_id=task.id,
            approver_email="agent-chat@local",
            decision=ApprovalDecision.APPROVE,
            reason="Approved from Agent chat continuation intent.",
        )
    )
    gate.status = ApprovalDecision.APPROVE.value
    gate.resolved_at = utcnow()
    set_task_status(task, TaskStatus.BUILD_VERIFY)
    task.blocked_reason = None
    task.blocked_at = None
    await db.flush()
    return task


def _has_generated_app_surface(project_root: Path) -> bool:
    ignored_names = {
        ".agent-builder",
        ".claude",
        ".git",
        ".memory",
        "AGENTS.md",
        "CLAUDE.md",
        "README",
        "README.md",
        "LICENSE",
        "LICENSE.md",
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "go.mod",
        "Cargo.toml",
        "pom.xml",
        "build.gradle",
        ".env",
        ".gitignore",
    }
    generated_dirs = {
        "src",
        "app",
        "api",
        "server",
        "frontend",
        "backend",
        "lib",
        "dist",
        "public",
        "scripts",
        "test",
        "tests",
    }
    for child in project_root.iterdir():
        name = child.name
        if name in ignored_names:
            continue
        if child.is_dir() and name in generated_dirs:
            return True
        if child.is_file() and child.suffix.lower() in {
            ".html",
            ".js",
            ".jsx",
            ".ts",
            ".tsx",
            ".css",
            ".py",
            ".go",
            ".rs",
        }:
            return True
    return False


async def _needs_init_project_bootstrap(project_root: Path, db: AsyncSession) -> bool:
    state = load_onboarding_state(project_root)
    readiness = load_readiness_status(project_root)
    return (
        bool(state.get("ready"))
        and state.get("onboarding_mode") == "forward_engineering"
        and readiness.get("state") == READY_STATE
        and not _feature_list_path(project_root).exists()
        and not await _has_builder_work_state(db)
        and not _has_generated_app_surface(project_root)
    )


def _runtime_metadata_for_agent(agent_name: str, project_root: Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    agent_def = get_agent_definition(agent_name)
    policy = resolve_agent_runtime_policy(agent_def, settings)
    runtime_config = (
        resolve_project_runtime_config(project_root)
        if project_root is not None
        else resolve_runtime_config(settings)
    )
    return {
        "model": str(runtime_config.get("model") or policy.model),
        "effort": policy.effort,
        "runtime_sdk": str(runtime_config.get("sdk") or ""),
        "provider": str(runtime_config.get("provider") or ""),
    }


def _chat_runtime_metadata(project_root: Path) -> dict[str, Any]:
    return _runtime_metadata_for_agent("chat", project_root)


def _chat_model_name(project_root: Path) -> str:
    return str(_chat_runtime_metadata(project_root)["model"])


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


def _latest_status(session: ChatSession, *, active_run: bool | None = None) -> dict[str, Any] | None:
    status_events = [event for event in session.events if event.event_type == "run_status"]
    if not status_events:
        return None
    latest = max(status_events, key=lambda event: event.created_at)
    payload = dict(latest.payload_json or {})
    if payload.get("running"):
        has_later_terminal_message = any(
            event.created_at > latest.created_at
            and event.event_type in {"assistant_message", "run_error"}
            and event.status == "completed"
            for event in session.events
        )
        if has_later_terminal_message:
            payload["running"] = False
            payload.setdefault("stop_reason", "completed_after_running_status")
        elif active_run is False:
            payload["running"] = False
            payload.setdefault("stop_reason", "stale_running_status_no_active_task")
    return payload


def _compatible_resume_session(session: ChatSession, runtime: Any) -> str | None:
    """Return a runtime-owned SDK session id only when it matches the active runtime."""
    sdk_session_id = str(session.sdk_session_id or "").strip()
    if not sdk_session_id:
        return None
    runtime_name = str(getattr(runtime, "name", "") or "")
    runtime_provider = str(getattr(runtime, "provider", "") or "")
    matching_statuses = [
        event
        for event in session.events
        if event.event_type == "run_status"
        and isinstance(event.payload_json, dict)
        and str(event.payload_json.get("sdk_session_id") or "") == sdk_session_id
    ]
    if not matching_statuses:
        status_events = [event for event in session.events if event.event_type == "run_status"]
        return None if status_events else sdk_session_id
    latest = max(matching_statuses, key=lambda event: event.created_at)
    payload = latest.payload_json or {}
    event_runtime = str(payload.get("runtime_sdk") or "")
    event_provider = str(payload.get("provider") or "")
    if event_runtime and runtime_name and event_runtime != runtime_name:
        return None
    if event_provider and runtime_provider and event_provider != runtime_provider:
        return None
    return sdk_session_id


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
    for attempt in range(5):
        try:
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
        except OperationalError as exc:
            if "database is locked" not in str(exc).lower() or attempt == 4:
                raise
            await asyncio.sleep(0.1 * (attempt + 1))
    raise RuntimeError("Unable to append chat event after retry")


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


def _initial_status(agent_name: str, project_root: Path | None = None) -> dict[str, Any]:
    agent_def = get_agent_definition(agent_name)
    return {
        **_runtime_metadata_for_agent(agent_name, project_root),
        "running": True,
        "current_turn": 0,
        "max_turns": agent_def.max_turns,
        "tokens_used": 0,
        "cost_usd": 0.0,
    }


def _extract_tool_text_payload(tool_response: Any) -> dict[str, Any]:
    if not isinstance(tool_response, dict):
        return {}
    content = tool_response.get("content")
    if not isinstance(content, list) or not content:
        return {}
    first = content[0]
    if not isinstance(first, dict) or first.get("type") != "text":
        return {}
    text = first.get("text")
    if not isinstance(text, str) or not text.strip():
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _permission_allow(updated_input: dict[str, Any]) -> Any:
    from claude_agent_sdk.types import PermissionResultAllow

    return PermissionResultAllow(updated_input=updated_input)


def _permission_deny(message: str) -> Any:
    from claude_agent_sdk.types import PermissionResultDeny

    return PermissionResultDeny(message=message)


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


def _deterministic_feature_spec_from_message(user_message: str) -> dict[str, Any] | None:
    lower_message = user_message.lower()
    todo_terms = {"todo", "todos", "unfinished", "completed", "active"}
    filter_terms = {"filter", "switch between", "all todos", "completed todos", "unfinished todos"}
    count_terms = {"count", "counts", "how many", "group"}
    if not (
        any(term in lower_message for term in todo_terms)
        and any(term in lower_message for term in filter_terms)
        and any(term in lower_message for term in count_terms)
    ):
        return None
    return _normalize_feature_spec_payload(
        {
            "title": "Todo filters and counts",
            "description": (
                "Users can filter the todo list between all, unfinished, and completed "
                "items, with visible counts for each group."
            ),
            "priority": 80,
            "acceptance_criteria": [
                "A user can switch between all, unfinished, and completed todo views.",
                "The UI shows counts for total, unfinished, and completed todos.",
                "Changing filters does not lose the current todo data or selection.",
            ],
            "dependencies": ["Existing todo creation and completion state"],
        }
    )


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
    if any(pattern in lower_message for pattern in _FEATURE_DELIVERY_CONTINUE_PATTERNS):
        return True
    if any(pattern in lower_message for pattern in _FEATURE_SPEC_INTENT_PATTERNS):
        return False
    if not any(pattern in lower_message for pattern in _FEATURE_REQUEST_ACTION_PATTERNS):
        return False
    return any(term in lower_message for term in _FEATURE_REQUEST_SCOPE_TERMS)


def _message_confirms_feature_delivery(user_message: str) -> bool:
    normalized = _normalize_planning_token(user_message)
    if not normalized:
        return False
    if normalized in _NATURAL_DELIVERY_CONFIRMATION_PATTERNS:
        return True
    return bool(
        re.search(r"\b(yes|please|sure|ok|okay)\b", normalized)
        and re.search(r"\b(start|plan|build|ship|do|deliver|continue|proceed)\b", normalized)
    )


def _message_requests_autonomous_continuation(user_message: str) -> bool:
    lower_message = user_message.lower()
    if "documentation" in lower_message or "feature doc" in lower_message:
        return False
    if any(pattern in lower_message for pattern in _AUTONOMOUS_CONTINUATION_PATTERNS):
        return True
    tokens = set(_normalize_planning_token(user_message).split())
    if not tokens:
        return False
    if tokens & _DELIVERY_PROGRESS_ACTION_TOKENS and tokens & _DELIVERY_PROGRESS_SCOPE_TOKENS:
        return True
    return False


def _message_requests_ambiguous_continuation(user_message: str) -> bool:
    normalized = _normalize_planning_token(user_message)
    if not normalized:
        return False
    if normalized in _AMBIGUOUS_CONTINUATION_PATTERNS:
        return True
    filler_tokens = {
        "can",
        "could",
        "you",
        "please",
        "now",
        "the",
        "with",
        "task",
        "ahead",
        "go",
        "start",
        "get",
        "started",
        "proceed",
        "continue",
    }
    tokens = set(normalized.split())
    return bool(tokens) and tokens <= filler_tokens


def _message_requests_delivery_lifecycle(user_message: str) -> bool:
    return (
        _message_requests_autonomous_continuation(user_message)
        or _message_requests_sprint_planning(user_message)
        or _message_requests_feature_delivery(user_message)
    )


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
        if (
            _FEATURE_SPEC_MARKER in content
            or "Feature saved to backlog as `" in content
            or ("I saved that as `" in content and "in the backlog" in content)
        ):
            return False
    return True


def _session_has_saved_feature_for_delivery(session: ChatSession) -> bool:
    for item in _history_items(session):
        if item.type != "assistant_message":
            continue
        content = str(item.payload.get("content", ""))
        if (
            "Feature saved to backlog as `" in content
            or ("I saved that as `" in content and "in the backlog" in content)
        ):
            return True
    return False


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
    delivery_lifecycle_request = _message_requests_delivery_lifecycle(user_message)
    recent_change_signal = _message_suggests_recent_change(user_message)
    latest_task = await _latest_task_context(db)
    task_has_doc_expectations = _task_has_doc_expectations(latest_task)
    if not force_route and (
        feature_spec_request
        or delivery_lifecycle_request
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
    *,
    runtime_sdk: str = "",
) -> str:
    question_guidance = _question_tool_guidance(runtime_sdk)
    continuation_guidance = ""
    if _message_requests_autonomous_continuation(user_message):
        continuation_guidance = (
            "\n\nAutonomous continuation mode is active for this turn.\n"
            "- Treat the user's message as a request to keep the build moving, not as a request "
            "for a status report or menu.\n"
            "- First inspect the builder board/task state with compact JSON commands such as "
            "`builder board show --json` and `builder backlog task list --json`.\n"
            "- If there is an active dispatchable task, continue it with "
            "`builder backlog task dispatch <task-id> --yes --json`.\n"
            "- Otherwise choose the highest-priority pending task and dispatch it with "
            "`builder backlog task dispatch <task-id> --yes --json`.\n"
            "- Do not ask the user which listed feature to build when the board already gives "
            "a deterministic next task by status and priority.\n"
            "- Ask the user only for genuinely missing product direction, credentials, external "
            "approval, or another decision that cannot be inferred from repo state.\n"
            "- If the provider limit or another recoverable runtime limit blocks progress, say "
            "which task is blocked and what should resume when the limit resets.\n"
        )
    prompt = (
        "You are a helpful AI assistant for the project rooted at "
        f"{project_root}.\n\n"
        "Answer the user's question directly. Use the repo context when it improves correctness. "
        f"{question_guidance}\n\n"
        f"Project root: {project_root}\n\n"
        f"User: {user_message}"
        f"{continuation_guidance}"
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
    *,
    runtime_sdk: str = "",
) -> str:
    question_guidance = _question_tool_guidance(runtime_sdk)
    return f"""You are the feature backlog planner for an already-initialized software project.

Your job is to turn a sufficiently bounded user request into one concrete backlog feature.

Rules:
- Use the existing session context. Treat short follow-up replies as answers to your most recent clarifying question when they resolve it.
- Keep the scope to one implementation-sized feature.
- Use read-only repo context first when it improves correctness.
- If the request is still ambiguous, continue the interview until the first implementation scope has no obvious gaps.
- Ask non-obvious clarifying questions that materially shape the feature contract.
- {question_guidance}
- Do not ask the user for technical facts that read-only repo discovery can answer.
- Do not repeat a question the user has already answered in the current session.
- Your responsibility stops at one agreed backlog feature. Do not invent task creation, dispatch, or execution progress in this lane.
- Do not produce documentation-agent output or maintained KB markdown.
- When the scope is ready, summarize the agreed feature briefly and emit the feature payload exactly as instructed below.

When the scope is NOT ready:
- Ask the next highest-leverage question through the runtime-native structured
  question mechanism described above.

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


def _init_project_requires_autonomous_continuation(response_text: str) -> bool:
    """Requirements onboarding may stop only at the final backlog payload."""

    response = response_text.strip()
    if not response:
        return True
    return _FEATURE_LIST_MARKER not in response


def _init_project_continuation_prompt(
    project_root: Path,
    *,
    previous_response: str,
    runtime_sdk: str = "",
) -> str:
    question_guidance = _question_tool_guidance(runtime_sdk)
    prior_response = previous_response.strip() or "(empty response)"
    return f"""Continue the forward-engineering requirements interview for the project rooted at {project_root}.

The previous assistant response ended without a structured question or final
backlog payload. Treat it as internal scratch, not as the completed user-facing
stop:

{prior_response}

Rules:
- Do not acknowledge, recap, or confirm the selected answer.
- Decide whether the first shippable scope is ready.
- If scope is not ready, immediately ask the next highest-leverage bounded
  product decision through the runtime-native structured question mechanism.
- If scope is ready, emit `AGREEMENT:` and `FEATURE_LIST_JSON:` exactly as the
  requirements prompt requires.
- {question_guidance}
"""


def _question_tool_guidance(runtime_sdk: str) -> str:
    """Return runtime-native guidance for structured user-choice questions."""
    normalized_sdk = str(runtime_sdk or "")
    if normalized_sdk.startswith("codex"):
        return (
            "When a bounded user decision is required, call the Codex `request_user_input` "
            "tool rather than writing a manual multiple-choice list in plain text. Pass a "
            "`questions` array with concise `header` and `question` fields and 2-3 `options`, "
            "each with `label` and `description`; put the recommended option first and suffix "
            "its label with `(Recommended)`."
        )
    if normalized_sdk == "openai_agents":
        return (
            "When a bounded user decision is required, call the OpenAI Agents SDK "
            "`request_user_input` function tool rather than writing a manual multiple-choice "
            "list in plain text. Pass a `questions` array with concise `header` and `question` "
            "fields and 2-3 `options`, each with `label` and `description`; put the recommended "
            "option first and suffix its label with `(Recommended)`."
        )
    return (
        "When there are a few clear choices, use AskUserQuestion with concise headers, "
        "short labels, and the recommended option first. When any bounded user decision "
        "is required, use AskUserQuestion rather than writing a manual multiple-choice "
        "list in plain text."
    )


# Deterministic post-chat handoff: structured AskUserQuestion answers from the
# init-project-chat interview map to the 5 ## Project Context fields in
# target CLAUDE.md. The chat agent's job is to extract scope; the orchestrator
# (this code) deterministically transcribes those answers into the file the
# code-gen agent reads. See plan: P5 / sprint-1 validation findings.

# Keyword → (field, value) mapping. Order matters — first match wins per field.
# Lowercase substring match against the chosen answer label.
_PROJECT_CONTEXT_ANSWER_RULES: tuple[tuple[str, str, str], ...] = (
    # Interface / app_type
    ("vanilla javascript", "framework", "none (vanilla HTML/CSS/JS)"),
    ("vanilla html", "framework", "none (vanilla HTML/CSS/JS)"),
    ("vanilla html/js", "framework", "none (vanilla HTML/CSS/JS)"),
    ("plain html", "framework", "none (vanilla HTML/CSS/JS)"),
    ("plain html/css/js", "framework", "none (vanilla HTML/CSS/JS)"),
    ("no framework", "framework", "none (vanilla HTML/CSS/JS)"),
    ("single html file", "app_type", "web (single-file SPA)"),
    ("single html", "app_type", "web (single-file SPA)"),
    ("web app", "app_type", "web (browser SPA)"),
    ("browser ui", "app_type", "web (browser SPA)"),
    ("single-page", "app_type", "web (browser SPA)"),
    ("cli (terminal)", "app_type", "cli"),
    ("command-line", "app_type", "cli"),
    ("rest api", "app_type", "rest api"),
    ("json api", "app_type", "rest api"),
    # Persistence
    ("browser localstorage", "persistence", "browser localStorage"),
    ("localstorage", "persistence", "browser localStorage"),
    ("sqlite", "persistence", "sqlite"),
    ("postgres", "persistence", "postgresql"),
    ("postgresql", "persistence", "postgresql"),
    ("in-memory", "persistence", "in-memory"),
    ("file (json", "persistence", "filesystem (json)"),
    # Language hints (often implied by stack choice)
    ("python backend", "language", "python"),
    ("node backend", "language", "javascript"),
    # Framework hints
    ("flask", "framework", "flask"),
    ("fastapi", "framework", "fastapi"),
    ("django", "framework", "django"),
    ("express", "framework", "express"),
    ("next.js", "framework", "next.js"),
    ("react", "framework", "react"),
    ("vue", "framework", "vue"),
    ("svelte", "framework", "svelte"),
)

# When app_type or framework implies a language, fill it in if not already set.
_LANGUAGE_INFERENCE: tuple[tuple[str, str, str], ...] = (
    ("framework", "none (vanilla HTML/CSS/JS)", "javascript"),
    ("app_type", "web (browser SPA)", "javascript"),
    ("framework", "flask", "python"),
    ("framework", "fastapi", "python"),
    ("framework", "django", "python"),
    ("framework", "express", "javascript"),
    ("framework", "next.js", "typescript"),
    ("framework", "react", "javascript"),
    ("framework", "vue", "javascript"),
    ("framework", "svelte", "javascript"),
    ("persistence", "browser localStorage", "javascript"),
)

# When language/persistence implies a package manager, fill it in if not set.
_PACKAGE_MANAGER_INFERENCE: tuple[tuple[str, str, str], ...] = (
    ("persistence", "browser localStorage", "none"),
    ("framework", "none (vanilla HTML/CSS/JS)", "none"),
    ("language", "python", "pip"),
    ("language", "javascript", "npm"),
    ("language", "typescript", "npm"),
)


async def _collect_ask_user_question_answers(
    db: AsyncSession,
    session_id: str,
) -> dict[str, str]:
    """Read structured AskUserQuestion answers from the chat session log.

    Returns ``{question_text: chosen_label}`` aggregated across every
    AskUserQuestion tool_result in the session. Empty dict when no
    AskUserQuestion tool runs are recorded yet.
    """
    result = await db.execute(
        select(ChatEvent)
        .where(ChatEvent.session_id == session_id)
        .where(ChatEvent.event_type == "tool_result")
        .order_by(ChatEvent.created_at)
    )
    answers: dict[str, str] = {}
    for event in result.scalars().all():
        payload = event.payload_json or {}
        if not isinstance(payload, dict):
            continue
        if payload.get("tool_name") != "AskUserQuestion":
            continue
        tool_input = payload.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            continue
        event_answers = tool_input.get("answers") or {}
        if not isinstance(event_answers, dict):
            continue
        for question, answer in event_answers.items():
            answer_str = str(answer).strip()
            if not answer_str:
                continue
            answers[str(question)] = answer_str
    return answers


def _map_chat_answers_to_project_context(
    answers: dict[str, str],
) -> dict[str, str | None]:
    """Deterministic mapper: structured chat answers → 5 Project Context fields.

    Matches lowercase substrings of the chosen answer label against an
    ordered rule table. First rule that fires per field wins; subsequent
    rules for the same field are ignored. Inference tables fill in
    derivable fields (language from framework, package_manager from
    language, etc.).

    Returns ``{language, framework, app_type, persistence, package_manager}``
    with values that are either a concrete string or ``None`` if undecidable.
    Only non-None values should be passed to ``update_project_context_block``.
    """
    fields: dict[str, str | None] = {
        "language": None,
        "framework": None,
        "app_type": None,
        "persistence": None,
        "package_manager": None,
    }
    if not answers:
        return fields

    haystack = " | ".join(answers.values()).lower()
    for keyword, field, value in _PROJECT_CONTEXT_ANSWER_RULES:
        if fields.get(field) is not None:
            continue
        if keyword in haystack:
            fields[field] = value

    for source_field, source_value, language in _LANGUAGE_INFERENCE:
        if fields.get("language") is not None:
            break
        if fields.get(source_field) == source_value:
            fields["language"] = language

    for source_field, source_value, pkg_mgr in _PACKAGE_MANAGER_INFERENCE:
        if fields.get("package_manager") is not None:
            break
        if fields.get(source_field) == source_value:
            fields["package_manager"] = pkg_mgr

    return fields


def _extract_technical_constraints(user_message: str) -> list[str]:
    lower_message = user_message.lower()
    constraints: list[str] = []
    seen: set[str] = set()
    for needle, constraint in (*_FRAMEWORK_CONSTRAINTS, *_STACK_CONSTRAINTS):
        if needle in lower_message and constraint not in seen:
            constraints.append(constraint)
            seen.add(constraint)
    return constraints


def _inject_feature_list_constraints(
    feature_payload: dict[str, Any],
    constraints: list[str],
) -> dict[str, Any]:
    if not constraints:
        return feature_payload
    payload = dict(feature_payload)
    metadata = dict(payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {})
    existing = metadata.get("technical_constraints", [])
    normalized_existing = (
        [str(item).strip() for item in existing if str(item).strip()]
        if isinstance(existing, list)
        else []
    )
    metadata["technical_constraints"] = list(dict.fromkeys([*normalized_existing, *constraints]))
    payload["metadata"] = metadata
    return payload


def _append_target_claude_constraints(project_root: Path, constraints: list[str]) -> None:
    if not constraints:
        return
    claude_path = project_root / "CLAUDE.md"
    if not claude_path.exists():
        return
    content = claude_path.read_text(encoding="utf-8")
    lines = [f"- {constraint}" for constraint in constraints if constraint.strip()]
    if not lines:
        return
    marker = "## Project Constraints"
    if marker not in content:
        claude_path.write_text(
            f"{content.rstrip()}\n\n{marker}\n" + "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        return
    existing_lines = set(content.splitlines())
    missing = [line for line in lines if line not in existing_lines]
    if missing:
        claude_path.write_text(
            f"{content.rstrip()}\n" + "\n".join(missing) + "\n",
            encoding="utf-8",
        )


async def _apply_forward_project_constraints(
    db: AsyncSession,
    project_root: Path,
    constraints: list[str],
) -> None:
    if not constraints:
        return
    _append_target_claude_constraints(project_root, constraints)
    result = await db.execute(select(Project).order_by(Project.created_at.desc()).limit(1))
    project = result.scalar_one_or_none()
    if project is None:
        return
    constraint_text = "User technical constraints: " + "; ".join(constraints) + "."
    if constraint_text not in project.description:
        project.description = f"{project.description}\n\n{constraint_text}".strip()


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
        acceptance_criteria=[
            str(item).strip()
            for item in payload.get("acceptance_criteria", [])
            if str(item).strip()
        ],
        dependencies=[
            str(item).strip()
            for item in payload.get("dependencies", [])
            if str(item).strip()
        ],
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
    dependencies = [
        f"- {item}" for item in payload.get("dependencies", []) if str(item).strip()
    ]
    description_sections = [str(payload.get("description", "")).strip()]
    if acceptance_criteria:
        description_sections.append("Acceptance criteria:\n" + "\n".join(acceptance_criteria))
    if dependencies:
        description_sections.append("Dependencies:\n" + "\n".join(dependencies))
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


async def _latest_saved_feature_for_delivery(
    db: AsyncSession,
    user_message: str,
) -> Feature | None:
    result = await db.execute(
        select(Feature)
        .options(selectinload(Feature.tasks))
        .order_by(Feature.priority.desc(), Feature.created_at.desc())
        .limit(25)
    )
    features = list(result.scalars().all())
    if not features:
        return None

    lower_message = user_message.lower()
    for feature in features:
        if feature.title.lower() in lower_message:
            return feature
    deliverable = [
        feature
        for feature in features
        if feature.status
        in {
            FeatureStatus.BACKLOG,
            FeatureStatus.PLANNING,
        }
    ]
    if "todo" in lower_message or "backlog" in lower_message:
        product_backlog = [
            feature
            for feature in deliverable
            if "todo" in f"{feature.title} {feature.description}".lower()
            or feature.status == FeatureStatus.BACKLOG
        ]
        if product_backlog:
            return product_backlog[0]
    if deliverable:
        return deliverable[0]
    return features[0]


async def _ensure_feature_delivery_task(db: AsyncSession, feature: Feature) -> tuple[Task, bool]:
    title = f"Deliver {feature.title}"
    for task in feature.tasks:
        if task.title == title:
            return task, False

    task = await _create_feature_delivery_task(
        db,
        feature,
        {
            "description": feature.description,
            "acceptance_criteria": list(feature.acceptance_criteria or []),
            "dependencies": list(feature.dependencies or []),
        },
    )
    return task, True


async def _schedule_task_dispatch(task_id: str) -> None:
    from autonomous_agent_builder.embedded.server.routes.tasks import _run_dispatch

    asyncio.create_task(_run_dispatch(task_id))


def _message_requests_sprint_planning(user_message: str) -> bool:
    lower_message = user_message.lower()
    if any(pattern in lower_message for pattern in _SPRINT_PLANNING_INTENT_PATTERNS):
        return True
    return re.search(r"\bsprint\s+\d+\s+planning\b", lower_message) is not None


def _session_has_pending_sprint_planning(session: ChatSession) -> bool:
    assistant_items = [
        item for item in _history_items(session) if item.type == "assistant_message"
    ]
    if not assistant_items:
        return False
    assistant_items.sort(key=lambda item: item.timestamp)
    contents = [str(item.payload.get("content", "")) for item in assistant_items]
    has_prompt = any(_SPRINT_PLANNING_SELECTION_PROMPT in content for content in contents)
    if not has_prompt:
        return False
    resolved = any(
        "created sprint plan" in content
        or "Sprint planning canceled" in content
        or "Sprint planning scope was not approved" in content
        or "received approval, and queued them" in content
        or "queue approval was denied" in content
        for content in contents
    )
    return not resolved


def _normalize_planning_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _message_selects_all_sprint_items(user_message: str) -> bool:
    normalized = _normalize_planning_token(user_message)
    if not normalized:
        return False
    if normalized in _SPRINT_PLANNING_ALL_PATTERNS:
        return True
    return bool(re.search(r"\ball\b", normalized)) and "backlog" in normalized


def _select_sprint_planning_features(
    user_message: str,
    backlog_items: list[Feature],
) -> list[Feature]:
    if not backlog_items:
        return []
    if _message_selects_all_sprint_items(user_message):
        return backlog_items

    lower_message = user_message.lower()
    id_matches = {
        feature.id.lower()
        for feature in backlog_items
        if feature.id.lower() in lower_message
    }
    selected = [feature for feature in backlog_items if feature.id.lower() in id_matches]
    if selected:
        return selected

    normalized_message = _normalize_planning_token(user_message)
    selected = []
    for feature in backlog_items:
        title_token = _normalize_planning_token(feature.title)
        if title_token and title_token in normalized_message:
            selected.append(feature)
    return selected


def _feature_dependency_ids(feature: Feature) -> list[str]:
    dependencies = feature.dependencies if isinstance(feature.dependencies, list) else []
    return [str(item).strip() for item in dependencies if str(item).strip()]


def _feature_ready_for_next_sprint(feature: Feature, features_by_id: dict[str, Feature]) -> bool:
    for dependency_id in _feature_dependency_ids(feature):
        dependency = features_by_id.get(dependency_id)
        if dependency is None or dependency.status != FeatureStatus.DONE:
            return False
    return True


def _next_sprint_candidates(features: list[Feature]) -> list[Feature]:
    features_by_id = {feature.id: feature for feature in features}
    product_backlog = [item for item in features if item.status == FeatureStatus.BACKLOG]
    ready = [
        feature
        for feature in product_backlog
        if _feature_ready_for_next_sprint(feature, features_by_id)
    ]
    return ready or product_backlog


def _format_sprint_planning_options(backlog_items: list[Feature]) -> str:
    lines = []
    for feature in backlog_items:
        lines.append(
            f"- `{feature.id}` · P{feature.priority} · {feature.title}"
        )
    return "\n".join(lines)


async def _request_chat_approval(
    session_id: str,
    hub: ChatSessionHub,
    *,
    tool_name: str,
    tool_input: dict[str, Any],
    summary: str,
    description: str,
) -> dict[str, Any]:
    approval_event = await _append_chat_event(
        session_id,
        event_type="tool_approval_request",
        payload={
            "tool_name": tool_name,
            "tool_input": tool_input,
            "summary": summary,
            "description": description,
            "answered": False,
            "decision": "",
            "reason": "",
        },
        status="pending",
    )
    future = await hub.create_pending_answer(session_id, approval_event.id)
    await hub.publish(session_id, _serialize_event(approval_event).model_dump(mode="json"))
    return await future


async def _request_chat_question(
    session_id: str,
    hub: ChatSessionHub,
    *,
    header: str,
    question: str,
    options: list[dict[str, str]],
    multi_select: bool = False,
) -> str:
    question_event = await _append_chat_event(
        session_id,
        event_type="ask_user_question",
        payload={
            "header": header,
            "question": question,
            "options": options,
            "multi_select": multi_select,
            "recommended_index": 0,
            "answered": False,
            "answer_value": "",
        },
        status="pending",
    )
    future = await hub.create_pending_answer(session_id, question_event.id)
    await hub.publish(session_id, _serialize_event(question_event).model_dump(mode="json"))
    response = await future
    return str(response.get("answer_value", "")).strip()


async def _handle_sprint_planning_turn(
    session_id: str,
    user_message: str,
    project_root: Path,
    hub: ChatSessionHub,
    *,
    selected_feature_ids: list[str] | None = None,
    auto_select_first: bool = False,
) -> str:
    session_factory = get_session_factory()
    async with session_factory() as db:
        project = await select_delivery_project(
            db,
            user_message,
            selected_feature_ids=selected_feature_ids,
        )
        if project is None:
            return "Sprint planning is blocked because no builder project exists yet."

        feature_result = await db.execute(
            select(Feature)
            .where(Feature.project_id == project.id)
            .where(Feature.item_type == BacklogItemType.FEATURE)
            .order_by(Feature.priority.desc(), Feature.created_at.asc())
        )
        features = list(feature_result.scalars().all())
        product_backlog = [item for item in features if item.status == FeatureStatus.BACKLOG]
        next_sprint_candidates = _next_sprint_candidates(features)
        sprint_backlog = [
            item
            for item in features
            if item.status
            in {
                FeatureStatus.SPRINT_BACKLOG,
                FeatureStatus.SPRINT_CANDIDATE,
                FeatureStatus.SPRINT_PLANNED,
            }
        ]

        if selected_feature_ids is not None:
            selected = [item for item in next_sprint_candidates if item.id in selected_feature_ids]
            if not selected:
                already_selected = [item for item in features if item.id in selected_feature_ids]
                if already_selected:
                    statuses = ", ".join(
                        f"`{feature.id}` {feature.title} ({feature.status.value if hasattr(feature.status, 'value') else feature.status})"
                        for feature in already_selected
                    )
                    return f"Those items are no longer in product backlog. Current state: {statuses}."
        else:
            selected = _select_sprint_planning_features(user_message, next_sprint_candidates)
        if not selected:
            if not product_backlog:
                if sprint_backlog:
                    titles = ", ".join(f"`{feature.id}` {feature.title}" for feature in sprint_backlog)
                    return (
                        "There are no product backlog items to pull into the sprint. "
                        f"Current sprint backlog: {titles}."
                    )
                return "There are no product backlog items available for sprint planning."
            first_feature = next_sprint_candidates[0]
            if auto_select_first:
                selected = [first_feature]
            else:
                excluded = [item for item in product_backlog if item.id != first_feature.id]
                excluded_note = (
                    "Excluded for next sprint: "
                    + "; ".join(f"{item.title} needs a later sprint to keep this one shippable" for item in excluded[:3])
                    if excluded
                    else "No excluded backlog items."
                )
                answer_value = await _request_chat_question(
                    session_id,
                    hub,
                    header="Sprint Scope",
                    question="Which backlog outcome should the next sprint plan now?",
                    options=[
                        {
                            "label": f"Plan first shippable feature: {first_feature.id} (Recommended)",
                            "description": (
                                f"{first_feature.title}. Keeps the sprint focused on one shippable outcome. "
                                f"{excluded_note}"
                            ),
                        },
                        {
                            "label": "Plan all backlog items",
                            "description": (
                                "Broader than the default; use only if these items are required to ship the "
                                "first feature."
                            ),
                        },
                        {
                            "label": "Cancel sprint planning",
                            "description": "Leave the product backlog unchanged.",
                        },
                    ],
                )
                answer_lower = answer_value.lower()
                if answer_lower.startswith("plan first shippable feature"):
                    selected = [first_feature]
                elif answer_lower.startswith("plan all backlog"):
                    selected = product_backlog
                elif answer_lower.startswith("cancel"):
                    return "Sprint planning canceled. Product backlog was left unchanged."
                else:
                    selected = _select_sprint_planning_features(answer_value, next_sprint_candidates)
                    if not selected:
                        return (
                            "Sprint planning could not match that answer to current backlog items. "
                            f"Current product backlog:\n{_format_sprint_planning_options(product_backlog)}"
                        )

        selected_ids = [feature.id for feature in selected]
        feature_result = await db.execute(
            select(Feature)
            .where(Feature.project_id == project.id)
            .where(Feature.id.in_(selected_ids))
            .options(selectinload(Feature.tasks))
            .order_by(Feature.priority.desc(), Feature.created_at.asc())
        )
        planned_features = list(feature_result.scalars().all())
        approval = await _request_chat_approval(
            session_id,
            hub,
            tool_name="Sprint scope approval",
            tool_input={
                "feature_ids": [feature.id for feature in planned_features],
                "features": [
                    {
                        "id": feature.id,
                        "title": feature.title,
                        "priority": feature.priority,
                        "acceptance_criteria": list(feature.acceptance_criteria or []),
                    }
                    for feature in planned_features
                ],
                "next_step_if_approved": "Create sprint plan and Board tasks for the approved scope.",
            },
            summary="Approve Sprint scope before task creation",
            description=(
                "The Agent selected backlog outcome(s) for the next sprint. "
                "Approve only if this scope should move from product backlog into a sprint plan and create Board tasks."
            ),
        )
        decision = str(approval.get("decision", "deny")).strip().lower() or "deny"
        if decision != "allow":
            return "Sprint planning scope was not approved. Product backlog was left unchanged."
        artifacts = await persist_sprint_execution_artifacts(db, project, planned_features)
        for feature in planned_features:
            mirror_item_to_artifact(project_root, feature_to_item_payload(feature))
        await db.commit()

    from autonomous_agent_builder.api.routes.dashboard_api import publish_board_snapshot

    async with session_factory() as db:
        await publish_board_snapshot(db)

    task_titles = [task.title for task in artifacts.get("tasks", [])]
    plan = artifacts["plan"]
    sprint = artifacts["sprint"]
    if not task_titles:
        return (
            "Sprint planning did not create implementation tasks. "
            "Check the backlog state before dispatching work."
        )
    return (
        f"Approved {sprint.label} scope and created sprint plan `{plan['plan_id']}`. "
        f"`{sprint.label}` is now in implementation with {len(task_titles)} generated task(s) "
        f"for {len(planned_features)} backlog outcome(s): "
        f"{', '.join(f'`{title}`' for title in task_titles[:5])}. "
        "Open Board to dispatch the first implementation task."
    )


def _init_project_chat_prompt(
    project_root: Path,
    user_message: str,
    *,
    runtime_sdk: str = "",
) -> str:
    question_guidance = _question_tool_guidance(runtime_sdk)
    return f"""You are the requirements-phase interviewer for a brand-new software project.

Your job is to keep the conversation focused on defining the first shippable scope and
product direction before delivery work begins.

Rules:
- Ask only the highest-leverage follow-up questions needed to remove ambiguity.
- Prefer specific, product-shaping questions over generic brainstorming.
- Use bounded repo, workflow, knowledge, or web context when it materially improves correctness.
- {question_guidance}
- After the user answers a structured question, do not stop with an acknowledgement,
  recap, or confirmation of the selected answer.
- Keep going autonomously until you either ask the next structured question or emit
  the final `FEATURE_LIST_JSON` payload.
- Every non-final response in this phase must be a runtime-native structured
  question request. Do not write the next requirement question as plain assistant text.
- Do not generate feature JSON until the user has clearly agreed the scope is ready.
- Once scope is ready, summarize the agreement and emit the feature backlog payload exactly as instructed below.

When the scope is NOT ready:
- Ask the next highest-leverage question through the runtime-native structured
  question mechanism described above.

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
    runtime = create_runtime(**resolve_project_runtime_config(project_root))
    if hasattr(runtime, "_runner"):
        runtime._runner = runner
    session_factory = get_session_factory()
    active_specialist: ActiveSpecialistRoute | None = None
    async with session_factory() as db:
        session = await _load_session(db, session_id, project_root=project_root, reject_scope_mismatch=True)
        if session is None:
            raise RuntimeError(f"Chat session '{session_id}' not found")
        agent_name = (
            "init-project-chat"
            if await _needs_init_project_bootstrap(project_root, db)
            else "chat"
        )
        agent_def = get_agent_definition(agent_name)
        runtime_policy = resolve_agent_runtime_policy(agent_def, get_settings())
        resume_session = _compatible_resume_session(session, runtime)
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
        payload=_initial_status(agent_name, project_root),
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

    async def on_tool_event(event_data: dict[str, Any] | None = None, **event_kwargs: Any) -> None:
        nonlocal specialist_phase
        event_data = {**(event_data or {}), **event_kwargs}
        requested_event_type = str(event_data.get("event_type") or "")
        tool_response = event_data.get("tool_response", event_data.get("output_preview", ""))
        event_type, content = _normalize_tool_response(tool_response)
        if requested_event_type and event_type == "tool_result":
            event_type = requested_event_type
        tool_name = str(event_data.get("tool_name", "") or "")
        if not tool_name:
            return
        tool_input = event_data.get("tool_input", {}) or {}
        payload = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "content": content,
            "diagnostic": summarize_tool_event(
                event_type=event_type,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_response=tool_response,
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
        if (
            event_type == "tool_result"
            and agent_name == "chat"
            and tool_name == "mcp__builder__task_dispatch"
            and _message_requests_autonomous_continuation(user_message)
        ):
            dispatch_payload = _extract_tool_text_payload(tool_response)
            if dispatch_payload.get("status") == "dispatched":
                status_event = await _append_chat_event(
                    session_id,
                    event_type="run_status",
                    payload={
                        **_runtime_metadata_for_agent(agent_name, project_root),
                        "running": False,
                        "current_turn": 0,
                        "max_turns": agent_def.max_turns,
                        "tokens_used": 0,
                        "cost_usd": 0.0,
                        "stop_reason": "task_dispatched",
                        "dispatch": {
                            "task_id": dispatch_payload.get("task_id"),
                            "status": dispatch_payload.get("status"),
                            "current_status": dispatch_payload.get("current_status"),
                        },
                    },
                    status="completed",
                    tool_use_id=str(tool_use_id) if tool_use_id else None,
                )
                await hub.publish(
                    session_id,
                    _serialize_event(status_event).model_dump(mode="json"),
                )
        if tool_name == "TodoWrite":
            todos = tool_input.get("todos", []) or []
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
        if tool_name in _USER_QUESTION_TOOL_NAMES:
            answers: dict[str, str] = {}
            for question in input_data.get("questions", []):
                options = question.get("options", []) or []
                try:
                    recommended_index = int(question.get("recommendedIndex", 0) or 0)
                except (TypeError, ValueError):
                    recommended_index = 0
                if (
                    agent_name == "chat"
                    and active_specialist is None
                    and not feature_spec_requested
                    and _message_requests_autonomous_continuation(user_message)
                    and not _message_requests_ambiguous_continuation(user_message)
                    and 0 <= recommended_index < len(options)
                ):
                    recommended_option = options[recommended_index]
                    answers[str(question.get("question", ""))] = str(
                        recommended_option.get("label", "")
                    ).strip()
                    continue
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

        if agent_name == "chat" and is_read_only_tool(tool_name):
            return _permission_allow(input_data)

        if (
            agent_name == "chat"
            and active_specialist is None
            and tool_name == "mcp__builder__task_dispatch"
            and _message_requests_autonomous_continuation(user_message)
            and not _message_requests_ambiguous_continuation(user_message)
        ):
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
        autonomous_continuation_requested = _message_requests_autonomous_continuation(user_message)
        dispatchable_task_exists = False
        if autonomous_continuation_requested and agent_name == "chat" and active_specialist is None:
            session_factory = get_session_factory()
            async with session_factory() as db:
                dispatchable_task_exists = await _has_dispatchable_task_state(db)
        sprint_planning_intent = _message_requests_sprint_planning(
            user_message,
        ) or _session_has_pending_sprint_planning(session)
        feature_spec_requested = (
            agent_name == "chat"
            and active_specialist is None
            and not sprint_planning_intent
            and (
                _message_requests_feature_spec(user_message)
                or _session_has_pending_feature_spec(session)
            )
        )
        sprint_planning_requested = (
            agent_name == "chat"
            and active_specialist is None
            and not feature_spec_requested
            and not dispatchable_task_exists
            and (sprint_planning_intent or autonomous_continuation_requested)
        )
        feature_delivery_followup_requested = (
            agent_name == "chat"
            and active_specialist is None
            and not feature_spec_requested
            and not sprint_planning_requested
            and (
                _message_requests_feature_delivery(user_message)
                or (
                    _session_has_saved_feature_for_delivery(session)
                    and _message_confirms_feature_delivery(user_message)
                )
            )
        )
        review_approval_continuation_requested = False
        if autonomous_continuation_requested and agent_name == "chat" and active_specialist is None:
            session_factory = get_session_factory()
            async with session_factory() as db:
                review_approval_continuation_requested = (
                    await _first_pending_review_approval(db)
                ) is not None
        if review_approval_continuation_requested:
            session_factory = get_session_factory()
            async with session_factory() as db:
                task = await _approve_review_gate_for_continuation(db)
                task_id = task.id if task is not None else ""
                task_title = task.title if task is not None else ""
                await db.commit()
            if task_id:
                await _schedule_task_dispatch(task_id)
                visible_response = f"Approved review for `{task_title}` and started build verification."
                assistant_event = await _append_chat_event(
                    session_id,
                    event_type="assistant_message",
                    payload={"content": visible_response, "final": True},
                    status="completed",
                    mirror_message=("assistant", visible_response, 0, 0.0),
                )
                await hub.publish(
                    session_id,
                    _serialize_event(assistant_event).model_dump(mode="json"),
                )
                status_event = await _append_chat_event(
                    session_id,
                    event_type="run_status",
                    payload={
                        **_runtime_metadata_for_agent(agent_name, project_root),
                        "running": False,
                        "current_turn": 0,
                        "max_turns": agent_def.max_turns,
                        "tokens_used": 0,
                        "cost_usd": 0.0,
                        "stop_reason": "review_approved_and_dispatched",
                    },
                    status="completed",
                )
                await hub.publish(
                    session_id,
                    _serialize_event(status_event).model_dump(mode="json"),
                )
                return
        if (
            autonomous_continuation_requested
            and dispatchable_task_exists
            and not feature_delivery_followup_requested
            and agent_name == "chat"
            and active_specialist is None
        ):
            session_factory = get_session_factory()
            async with session_factory() as db:
                task = await _first_dispatchable_task(db)
            if task is not None:
                await _schedule_task_dispatch(task.id)
                visible_response = f"Started `{task.title}`. I will continue from the current sprint task."
                assistant_event = await _append_chat_event(
                    session_id,
                    event_type="assistant_message",
                    payload={"content": visible_response, "final": True},
                    status="completed",
                    mirror_message=("assistant", visible_response, 0, 0.0),
                )
                await hub.publish(
                    session_id,
                    _serialize_event(assistant_event).model_dump(mode="json"),
                )
                status_event = await _append_chat_event(
                    session_id,
                    event_type="run_status",
                    payload={
                        **_runtime_metadata_for_agent(agent_name, project_root),
                        "running": False,
                        "current_turn": 0,
                        "max_turns": agent_def.max_turns,
                        "tokens_used": 0,
                        "cost_usd": 0.0,
                        "stop_reason": "task_dispatched",
                    },
                    status="completed",
                )
                await hub.publish(
                    session_id,
                    _serialize_event(status_event).model_dump(mode="json"),
                )
                return
        if sprint_planning_requested:
            ambiguous_continuation_requested = (
                autonomous_continuation_requested
                and not sprint_planning_intent
                and _message_requests_ambiguous_continuation(user_message)
            )
            visible_response = await _handle_sprint_planning_turn(
                session_id,
                user_message,
                project_root,
                hub,
                auto_select_first=autonomous_continuation_requested
                and not ambiguous_continuation_requested,
            )
            assistant_event = await _append_chat_event(
                session_id,
                event_type="assistant_message",
                payload={"content": visible_response, "final": True},
                status="completed",
                mirror_message=("assistant", visible_response, 0, 0.0),
            )
            await hub.publish(session_id, _serialize_event(assistant_event).model_dump(mode="json"))
            status_event = await _append_chat_event(
                session_id,
                event_type="run_status",
                payload={
                    **_runtime_metadata_for_agent(agent_name, project_root),
                    "running": False,
                    "current_turn": 0,
                    "max_turns": agent_def.max_turns,
                    "tokens_used": 0,
                    "cost_usd": 0.0,
                },
                status="completed",
            )
            await hub.publish(session_id, _serialize_event(status_event).model_dump(mode="json"))
            return
        if feature_delivery_followup_requested:
            session_factory = get_session_factory()
            async with session_factory() as db:
                feature = await _latest_saved_feature_for_delivery(db, user_message)
            if feature is not None:
                visible_response = await _handle_sprint_planning_turn(
                    session_id,
                    feature.title,
                    project_root,
                    hub,
                    selected_feature_ids=[feature.id],
                )
                assistant_event = await _append_chat_event(
                    session_id,
                    event_type="assistant_message",
                    payload={"content": visible_response, "final": True},
                    status="completed",
                    mirror_message=("assistant", visible_response, 0, 0.0),
                )
                await hub.publish(session_id, _serialize_event(assistant_event).model_dump(mode="json"))
                status_event = await _append_chat_event(
                    session_id,
                    event_type="run_status",
                    payload={
                        **_runtime_metadata_for_agent(agent_name, project_root),
                        "running": False,
                        "current_turn": 0,
                        "max_turns": agent_def.max_turns,
                        "tokens_used": 0,
                        "cost_usd": 0.0,
                    },
                    status="completed",
                )
                await hub.publish(session_id, _serialize_event(status_event).model_dump(mode="json"))
                return
        if feature_spec_requested:
            deterministic_feature_spec = _deterministic_feature_spec_from_message(user_message)
            if deterministic_feature_spec is not None:
                session_factory = get_session_factory()
                async with session_factory() as db:
                    feature = await _persist_feature_spec(db, deterministic_feature_spec)
                if feature is not None:
                    visible_response = (
                        f"Feature saved to backlog as `{feature.title}`. "
                        "I can plan and start the next sprint for this now, or keep it in the backlog."
                    )
                    assistant_event = await _append_chat_event(
                        session_id,
                        event_type="assistant_message",
                        payload={"content": visible_response, "final": True},
                        status="completed",
                        mirror_message=("assistant", visible_response, 0, 0.0),
                    )
                    await hub.publish(
                        session_id,
                        _serialize_event(assistant_event).model_dump(mode="json"),
                    )
                    status_event = await _append_chat_event(
                        session_id,
                        event_type="run_status",
                        payload={
                            **_runtime_metadata_for_agent(agent_name, project_root),
                            "running": False,
                            "current_turn": 0,
                            "max_turns": agent_def.max_turns,
                            "tokens_used": 0,
                            "cost_usd": 0.0,
                            "stop_reason": "deterministic_feature_spec",
                        },
                        status="completed",
                    )
                    await hub.publish(
                        session_id,
                        _serialize_event(status_event).model_dump(mode="json"),
                    )
                    return
        prompt = (
            _init_project_chat_prompt(
                project_root,
                user_message,
                runtime_sdk=runtime.name,
            )
            if agent_name == "init-project-chat"
            else _feature_spec_chat_prompt(
                project_root,
                user_message,
                runtime_sdk=runtime.name,
            )
            if feature_spec_requested
            else _general_chat_prompt(
                project_root,
                user_message,
                documentation_context,
                runtime_sdk=runtime.name,
            )
        )
        run_session = resume_session
        result: RunResult | None = None
        total_tokens_input = 0
        total_tokens_output = 0
        total_cost_usd = 0.0
        total_duration_ms = 0
        total_turns = 0
        for continuation_index in range(_INIT_PROJECT_MAX_REQUIREMENTS_CONTINUATIONS):
            result = await runtime.run(
                prompt,
                agent=agent_name,
                workspace_path=str(project_root),
                session=run_session,
                effort=runtime_policy.effort,
                subagents=(active_specialist.name,) if active_specialist is not None else None,
                on_chunk=on_stream,
                can_use_tool=can_use_tool,
                on_tool_event=on_tool_event,
            )
            total_tokens_input += result.tokens_input
            total_tokens_output += result.tokens_output
            total_cost_usd += result.cost_usd
            total_duration_ms += result.duration_ms
            total_turns += result.num_turns
            if result.error or agent_name != "init-project-chat":
                break
            visible_probe = result.output_text or ""
            if not _init_project_requires_autonomous_continuation(visible_probe):
                break
            if continuation_index == _INIT_PROJECT_MAX_REQUIREMENTS_CONTINUATIONS - 1:
                break
            run_session = result.session_id or run_session
            prompt = _init_project_continuation_prompt(
                project_root,
                previous_response=visible_probe,
                runtime_sdk=runtime.name,
            )

        if result is None:
            raise RuntimeError("Agent run did not start.")

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
                    **_runtime_metadata_for_agent(agent_name, project_root),
                    "running": False,
                    "error": result.error,
                    "current_turn": total_turns,
                    "max_turns": agent_def.max_turns,
                    "tokens_used": total_tokens_input + total_tokens_output,
                    "cost_usd": total_cost_usd,
                    "sdk_session_id": result.session_id,
                    "duration_ms": total_duration_ms,
                    "stop_reason": result.stop_reason,
                    "observability": result.observability or {},
                },
                status="completed",
            )
            await hub.publish(session_id, _serialize_event(status_event).model_dump(mode="json"))
            return

        if result.stop_reason == "provider_limit":
            provider_limit = result.provider_limit or {
                "code": result.stop_reason or "capability_limit",
                "reason": result.output_text or "Agent run hit a capability limit.",
            }
            if specialist_active:
                await publish_specialist_status(
                    "blocked",
                    active_specialist.policy.blocked_summary,
                    status="completed",
                )
            limit_text = result.output_text or "The selected runtime hit a provider limit."
            visible_response = f"Provider limit blocked this run: {limit_text}"
            assistant_event = await _append_chat_event(
                session_id,
                event_type="assistant_message",
                payload={"content": visible_response, "final": True, "provider_limit": provider_limit},
                status="blocked",
                mirror_message=("assistant", visible_response, 0, 0.0),
            )
            await hub.publish(session_id, _serialize_event(assistant_event).model_dump(mode="json"))
            status_event = await _append_chat_event(
                session_id,
                event_type="run_status",
                payload={
                    **_runtime_metadata_for_agent(agent_name, project_root),
                    "running": False,
                    "current_turn": total_turns,
                    "max_turns": agent_def.max_turns,
                    "tokens_used": total_tokens_input + total_tokens_output,
                    "cost_usd": total_cost_usd,
                    "sdk_session_id": result.session_id,
                    "duration_ms": total_duration_ms,
                    "stop_reason": "provider_limit",
                    "provider_limit": provider_limit,
                    "observability": result.observability or {},
                },
                status="blocked",
            )
            await hub.publish(session_id, _serialize_event(status_event).model_dump(mode="json"))
            return

        visible_response = result.output_text or "No response from agent"
        start_sprint_scope_after_response = False
        if agent_name == "init-project-chat":
            visible_response, feature_payload = _extract_feature_list_payload(project_root, visible_response)
            if feature_payload is not None:
                start_sprint_scope_after_response = True
                technical_constraints = _extract_technical_constraints(user_message)
                feature_payload = _inject_feature_list_constraints(
                    feature_payload,
                    technical_constraints,
                )
                write_feature_list_file(project_root, feature_payload)
                session_factory = get_session_factory()
                async with session_factory() as db:
                    # Deterministic post-chat handoff: read structured
                    # AskUserQuestion answers from this session's chat events
                    # and rewrite the 5 ## Project Context fields in
                    # CLAUDE.md so the dispatched code-gen agent sees the
                    # user-decided stack instead of init-time auto-detected
                    # defaults. Plan: P5; Bug: code-gen built Flask for a
                    # vanilla-JS scope.
                    chat_answers = await _collect_ask_user_question_answers(db, session_id)
                    if chat_answers:
                        context_fields = _map_chat_answers_to_project_context(chat_answers)
                        non_none_fields = {k: v for k, v in context_fields.items() if v is not None}
                        if non_none_fields:
                            update_project_context_block(project_root, **non_none_fields)
                    await _apply_forward_project_constraints(
                        db,
                        project_root,
                        technical_constraints,
                    )
                    if await sync_forward_engineering_feature_backlog(db, project_root):
                        await db.commit()
                assess_readiness(
                    project_root,
                    onboarding_state=load_onboarding_state(project_root),
                    write=True,
                )
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
                if feature is not None:
                    save_note = (
                        f"Feature saved to backlog as `{feature.title}`. "
                        "I can plan and start the next sprint for this now, or keep it in the backlog."
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
                total_tokens_input + total_tokens_output,
                total_cost_usd,
            ),
        )
        await hub.publish(session_id, _serialize_event(assistant_event).model_dump(mode="json"))
        if start_sprint_scope_after_response:
            sprint_response = await _handle_sprint_planning_turn(
                session_id,
                "sprint planning",
                project_root,
                hub,
            )
            sprint_event = await _append_chat_event(
                session_id,
                event_type="assistant_message",
                payload={"content": sprint_response, "final": True},
                status="completed",
                mirror_message=("assistant", sprint_response, 0, 0.0),
            )
            await hub.publish(session_id, _serialize_event(sprint_event).model_dump(mode="json"))
        status_event = await _append_chat_event(
            session_id,
            event_type="run_status",
            payload={
                **_runtime_metadata_for_agent(agent_name, project_root),
                "running": False,
                "current_turn": total_turns,
                "max_turns": agent_def.max_turns,
                "tokens_used": total_tokens_input + total_tokens_output,
                "cost_usd": total_cost_usd,
                "sdk_session_id": result.session_id,
                "duration_ms": total_duration_ms,
                "stop_reason": result.stop_reason,
                "observability": result.observability or {},
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
            payload={
                **_runtime_metadata_for_agent(agent_name, project_root),
                "running": False,
                "error": str(exc),
            },
            status="completed",
        )
        await hub.publish(session_id, _serialize_event(status_event).model_dump(mode="json"))


async def _continue_after_persisted_response(
    app: Any,
    session_id: str,
    message: str,
) -> None:
    hub: ChatSessionHub = app.state.chat_hub
    task = asyncio.create_task(_run_chat_turn(app, session_id, message))
    attached = await hub.attach_run(session_id, task)
    if attached:
        return
    task.cancel()


@router.get("/agent/runtime")
async def get_runtime_settings(request: Request) -> dict[str, Any]:
    """Return the active runtime settings for the dashboard settings surface."""
    project_root = _project_root(request)
    return runtime_settings_payload(project_root)


@router.post("/agent/runtime")
async def update_runtime_settings(
    request: Request,
    payload: RuntimeSettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Persist runtime settings from the dashboard settings surface."""
    project_root = _project_root(request)
    previous = runtime_settings_payload(project_root, include_capabilities=False)
    result = persist_runtime_settings(
        project_root,
        sdk=payload.sdk,
        provider=payload.provider,
        model=payload.model,
        api_base_url=payload.api_base_url,
        api_key_env=payload.api_key_env,
        codex_profile=payload.codex_profile,
        sandbox_mode=payload.sandbox_mode,
        approval_policy=payload.approval_policy,
        tracing=payload.tracing,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result)
    repair = reconcile_runtime_project_state(project_root)
    result["runtime_repair"] = repair
    sessions_result = await db.execute(
        select(ChatSession)
        .where(ChatSession.repo_identity == _repo_identity(project_root))
        .where(ChatSession.workspace_cwd == _workspace_cwd(project_root))
        .order_by(ChatSession.updated_at.desc())
        .limit(1)
    )
    session = sessions_result.scalar_one_or_none()
    if session is None:
        session = ChatSession()
        _stamp_session_scope(session, project_root)
        db.add(session)
        await db.flush()
    session.updated_at = utcnow()
    db.add(
        ChatEvent(
            session_id=session.id,
            event_type="runtime_settings_updated",
            payload_json={
                "previous_runtime_sdk": previous.get("sdk"),
                "selected_runtime_sdk": result.get("sdk"),
                "previous_provider": previous.get("provider"),
                "provider": result.get("provider"),
                "previous_model": previous.get("model"),
                "model": result.get("model"),
                "scope": "future_runs_only",
                "state_policy": "preserve_existing_tasks_runs_metrics_observability_memory_knowledge_backlog",
                "runtime_repair": repair,
            },
            status="completed",
        )
    )
    await publish_onboarding_snapshot(project_root)
    return result


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
    runtime_metadata = _chat_runtime_metadata(project_root)
    return ChatMetaResponse(
        model=runtime_metadata["model"],
        effort=runtime_metadata["effort"],
        runtime_sdk=runtime_metadata["runtime_sdk"],
        provider=runtime_metadata["provider"],
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

    if not fresh and session is None and await _needs_init_project_bootstrap(project_root, db):
        bootstrap_session_id = await ensure_init_project_bootstrap_session(project_root, db)
        await db.commit()
        session = await _load_session(db, bootstrap_session_id, project_root=project_root)

    if not fresh and session is None and session_id is None and scoped_sessions:
        session = scoped_sessions[0]

    if session is None:
        runtime_metadata = _chat_runtime_metadata(project_root)
        return ChatHistoryResponse(
            session_id="",
            sdk_session_id=None,
            model=runtime_metadata["model"],
            effort=runtime_metadata["effort"],
            runtime_sdk=runtime_metadata["runtime_sdk"],
            provider=runtime_metadata["provider"],
            repo_identity=_repo_identity(project_root),
            workspace_cwd=_workspace_cwd(project_root),
            items=[],
            messages=[],
            status=None,
        )

    items = _history_items(session)
    runtime_metadata = _chat_runtime_metadata(project_root)
    active_run = await _chat_hub(request).has_active_run(session.id)
    return ChatHistoryResponse(
        session_id=session.id,
        sdk_session_id=session.sdk_session_id,
        model=runtime_metadata["model"],
        effort=runtime_metadata["effort"],
        runtime_sdk=runtime_metadata["runtime_sdk"],
        provider=runtime_metadata["provider"],
        repo_identity=_repo_identity(project_root),
        workspace_cwd=_workspace_cwd(project_root),
        items=items,
        messages=_legacy_messages(items),
        status=_latest_status(session, active_run=active_run),
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
    runtime_metadata = _chat_runtime_metadata(project_root)
    active_run = await hub.has_active_run(session_id)
    snapshot = ChatHistoryResponse(
        session_id=session.id,
        sdk_session_id=session.sdk_session_id,
        model=runtime_metadata["model"],
        effort=runtime_metadata["effort"],
        runtime_sdk=runtime_metadata["runtime_sdk"],
        provider=runtime_metadata["provider"],
        repo_identity=_repo_identity(project_root),
        workspace_cwd=_workspace_cwd(project_root),
        items=_history_items(session),
        messages=_legacy_messages(_history_items(session)),
        status=_latest_status(session, active_run=active_run),
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
    needs_init_bootstrap = await _needs_init_project_bootstrap(project_root, db)
    agent_name = "init-project-chat" if needs_init_bootstrap else "chat"
    runtime_metadata = _runtime_metadata_for_agent(agent_name, project_root)

    session = await _load_session(
        db,
        request.session_id,
        project_root=project_root,
        reject_scope_mismatch=bool(request.session_id),
    )
    if session is None and request.session_id and needs_init_bootstrap:
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
        model=runtime_metadata["model"],
        effort=runtime_metadata["effort"],
        runtime_sdk=runtime_metadata["runtime_sdk"],
        provider=runtime_metadata["provider"],
        status=_initial_status(agent_name, project_root),
    )


@router.post("/agent/chat/respond", response_model=ChatRespondResponse)
async def respond_to_chat_event(
    request: ChatRespondRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """Submit an answer for a pending question or tool approval card."""

    hub = _chat_hub(req)
    event = await db.get(ChatEvent, request.event_id)
    if event is None or event.session_id != request.session_id:
        raise HTTPException(status_code=404, detail="Chat interaction not found")
    event_payload = event.payload_json or {}
    persisted_pending = (
        event.status == "pending"
        and event.event_type in {"ask_user_question", "tool_approval_request"}
        and not bool(event_payload.get("answered"))
    )
    has_live_waiter = await hub.has_pending_answer(request.event_id)
    if not has_live_waiter and not persisted_pending:
        raise HTTPException(status_code=409, detail="This interaction is no longer pending.")

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
        if has_live_waiter:
            resolved = await hub.resolve_pending_answer(
                request.event_id,
                {"answer_value": answer_value},
            )
            if not resolved:
                raise HTTPException(status_code=409, detail="This interaction is no longer pending.")
        else:
            question = str(event.payload_json.get("question") or "the pending question")
            await _continue_after_persisted_response(
                req.app,
                request.session_id,
                f'Operator answered pending question "{question}": {answer_value}',
            )
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
    response_payload = {
        "decision": decision,
        "reason": request.reason.strip(),
        "updated_input": request.updated_input,
    }
    if has_live_waiter:
        resolved = await hub.resolve_pending_answer(request.event_id, response_payload)
        if not resolved:
            raise HTTPException(status_code=409, detail="This interaction is no longer pending.")
    else:
        tool_name = str(event.payload_json.get("tool_name") or "requested tool")
        await _continue_after_persisted_response(
            req.app,
            request.session_id,
            f'Operator answered pending approval for "{tool_name}": {decision}. Reason: {request.reason.strip()}',
        )
    return ChatRespondResponse(ok=True, session_id=request.session_id, event_id=request.event_id)
