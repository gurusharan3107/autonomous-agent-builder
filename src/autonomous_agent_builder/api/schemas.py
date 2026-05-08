"""Pydantic schemas for API request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

# ── Projects ──


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    repo_url: str = ""
    language: str = "python"


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    repo_url: str
    language: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Features ──


class FeatureCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    priority: int = 0
    item_type: str = "feature"
    tags: list[str] = Field(default_factory=list)
    severity: str | None = None
    source: str = "manual"
    evidence: str = ""


class FeatureResponse(BaseModel):
    id: str
    project_id: str
    title: str
    description: str
    status: str
    priority: int
    item_type: str = "feature"
    tags: list[str] = Field(default_factory=list)
    severity: str | None = None
    source: str = "manual"
    evidence: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}


class BacklogItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    priority: int = 0
    item_type: str = "feature"
    tags: list[str] = Field(default_factory=list)
    severity: str | None = None
    source: str = "manual"
    evidence: str = ""

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def _accept_type_alias(cls, data: object) -> object:
        if isinstance(data, dict) and "type" in data and "item_type" not in data:
            return {**data, "item_type": data["type"]}
        return data


class BacklogItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = None
    priority: int | None = None
    item_type: str | None = None
    tags: list[str] | None = None
    severity: str | None = None
    source: str | None = None
    evidence: str | None = None

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def _accept_type_alias(cls, data: object) -> object:
        if isinstance(data, dict) and "type" in data and "item_type" not in data:
            return {**data, "item_type": data["type"]}
        return data


class BacklogItemResponse(FeatureResponse):
    type: str = "feature"


# ── Tasks ──


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    complexity: int = 1
    depends_on: dict[str, Any] | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    complexity: int | None = None
    depends_on: dict[str, Any] | None = None


class TaskResponse(BaseModel):
    id: str
    feature_id: str
    title: str
    description: str
    status: str
    phase: str | None = None
    complexity: int
    depends_on: dict[str, Any] | None
    retry_count: int
    blocked_reason: str | None
    blocked_at: datetime | None = None
    capability_limit_at: datetime | None = None
    capability_limit_reason: str | None
    provider_limit: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Gate Results ──


class GateResultResponse(BaseModel):
    id: str
    task_id: str
    gate_name: str
    status: str
    findings_count: int
    elapsed_ms: int
    error_code: str | None
    timeout: bool
    remediation_attempted: bool
    remediation_succeeded: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Agent Runs ──


class AgentRunResponse(BaseModel):
    id: str
    task_id: str
    agent_name: str
    session_id: str | None
    runtime_sdk: str = ""
    provider: str = ""
    model: str = ""
    effort: str | None = None
    cost_usd: float
    tokens_input: int
    tokens_output: int
    tokens_cached: int
    num_turns: int
    duration_ms: int
    stop_reason: str | None
    status: str
    error: str | None
    observability: dict | None = None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# ── Approvals ──


class ApprovalCreate(BaseModel):
    approver_email: str
    decision: str  # approve, reject, override, request_changes
    comment: str = ""
    reason: str = ""


class ApprovalGateResponse(BaseModel):
    id: str
    task_id: str
    gate_type: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Harnessability ──


class HarnessabilityResponse(BaseModel):
    id: str
    project_id: str
    score: int
    checks: dict[str, Any]
    recommendations: str
    routing_action: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Knowledge Base ──


class KBDocCreate(BaseModel):
    task_id: str
    doc_type: str = Field(pattern=r"^(adr|api_contract|schema|runbook|context)$")
    title: str = Field(min_length=1, max_length=255)
    content: str


class KBDocUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


class KBDocResponse(BaseModel):
    id: str
    task_id: str
    doc_type: str
    title: str
    content: str
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Dispatch ──


class DispatchRequest(BaseModel):
    """Request to dispatch a task through the SDLC pipeline."""

    task_id: str


class TaskRecoveryResponse(BaseModel):
    """Response for explicit operator recovery of a failed task."""

    status: str
    task_id: str
    previous_status: str
    current_status: str
    next_step: str
