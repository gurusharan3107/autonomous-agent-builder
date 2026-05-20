"""Pydantic contracts for the embedded Agent API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
