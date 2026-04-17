"""Database models — 13 tables for the autonomous agent builder.

Tables: projects, features, tasks, quality_gates, gate_results,
approval_gates, approvals, agent_runs, agent_run_events, workspaces,
design_documents, harnessability_reports, approval_log.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    type_annotation_map = {dict[str, Any]: JSON}


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_uuid():
    return str(uuid4())


def _enum_values(enum_class):
    """Return enum values (not names) for SQLAlchemy Enum column type."""
    return [e.value for e in enum_class]


# ── Enums ──


class TaskStatus(enum.StrEnum):
    PENDING = "pending"
    PLANNING = "planning"
    DESIGN = "design"
    DESIGN_REVIEW = "design_review"
    IMPLEMENTATION = "implementation"
    QUALITY_GATES = "quality_gates"
    PR_CREATION = "pr_creation"
    REVIEW_PENDING = "review_pending"
    BUILD_VERIFY = "build_verify"
    DONE = "done"
    BLOCKED = "blocked"
    CAPABILITY_LIMIT = "capability_limit"
    FAILED = "failed"


class GateStatus(enum.StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    TIMEOUT = "timeout"
    ERROR = "error"
    PENDING = "pending"


class ApprovalDecision(enum.StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    OVERRIDE = "override"
    REQUEST_CHANGES = "request_changes"


class FeatureStatus(enum.StrEnum):
    BACKLOG = "backlog"
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    BLOCKED = "blocked"


class HarnessAction(enum.StrEnum):
    PROCEED = "proceed"
    ARCHITECT_REVIEW = "architect_review"
    REJECT = "reject"


# ── Models ──


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    repo_url: Mapped[str] = mapped_column(String(512), default="")
    language: Mapped[str] = mapped_column(String(50), default="python")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    features: Mapped[list[Feature]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    harnessability_reports: Mapped[list[HarnessabilityReport]] = relationship(
        back_populates="project"
    )


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[FeatureStatus] = mapped_column(
        Enum(FeatureStatus, values_callable=_enum_values), default=FeatureStatus.BACKLOG
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped[Project] = relationship(back_populates="features")
    tasks: Mapped[list[Task]] = relationship(back_populates="feature", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    feature_id: Mapped[str] = mapped_column(ForeignKey("features.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, values_callable=_enum_values), default=TaskStatus.PENDING
    )
    depends_on: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    complexity: Mapped[int] = mapped_column(Integer, default=1)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capability_limit_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    capability_limit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    dead_letter_queued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    feature: Mapped[Feature] = relationship(back_populates="tasks")
    gate_results: Mapped[list[GateResult]] = relationship(back_populates="task")
    agent_runs: Mapped[list[AgentRun]] = relationship(back_populates="task")
    approval_gates: Mapped[list[ApprovalGate]] = relationship(back_populates="task")
    workspace: Mapped[Workspace | None] = relationship(back_populates="task", uselist=False)


class QualityGate(Base):
    """Gate configuration — what gates exist and their settings."""

    __tablename__ = "quality_gates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    gate_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # code_quality, security, testing, dependency
    tier: Mapped[str] = mapped_column(
        String(20), default="pre_integration"
    )  # pre_integration, post_integration, nightly
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=60)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class GateResult(Base):
    __tablename__ = "gate_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    gate_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[GateStatus] = mapped_column(
        Enum(GateStatus, values_callable=_enum_values), nullable=False
    )
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    findings_count: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timeout: Mapped[bool] = mapped_column(Boolean, default=False)
    remediation_attempted: Mapped[bool] = mapped_column(Boolean, default=False)
    remediation_succeeded: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_of: Mapped[str | None] = mapped_column(ForeignKey("gate_results.id"), nullable=True)
    analysis_depth: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    task: Mapped[Task] = relationship(back_populates="gate_results")


class ApprovalGate(Base):
    __tablename__ = "approval_gates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    gate_type: Mapped[str] = mapped_column(String(50), nullable=False)  # planning, design, pr
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, approved, rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[Task] = relationship(back_populates="approval_gates")
    approvals: Mapped[list[Approval]] = relationship(back_populates="approval_gate")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    approval_gate_id: Mapped[str] = mapped_column(ForeignKey("approval_gates.id"), nullable=False)
    approver_email: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[ApprovalDecision] = mapped_column(
        Enum(ApprovalDecision, values_callable=_enum_values), nullable=False
    )
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    approval_gate: Mapped[ApprovalGate] = relationship(back_populates="approvals")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_version_sha: Mapped[str] = mapped_column(
        String(40), default=""
    )  # git SHA of definitions.py
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tokens_input: Mapped[int] = mapped_column(Integer, default=0)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0)
    tokens_cached: Mapped[int] = mapped_column(Integer, default=0)
    num_turns: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    stop_reason: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # end_turn, max_turns, budget_exceeded
    status: Mapped[str] = mapped_column(String(20), default="running")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[Task] = relationship(back_populates="agent_runs")
    events: Mapped[list[AgentRunEvent]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class AgentRunEvent(Base):
    __tablename__ = "agent_run_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_input: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output_preview: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[AgentRun] = relationship(back_populates="events")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, unique=True)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), default="")
    is_worktree: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    cleaned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[Task] = relationship(back_populates="workspace")


class DesignDocument(Base):
    __tablename__ = "design_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)  # adr, api_contract, schema
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HarnessabilityReport(Base):
    __tablename__ = "harnessability_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-8
    checks: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    recommendations: Mapped[str] = mapped_column(Text, default="")
    routing_action: Mapped[HarnessAction] = mapped_column(
        Enum(HarnessAction, values_callable=_enum_values), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="harnessability_reports")


class ApprovalLog(Base):
    """Immutable, append-only audit trail. No UPDATE or DELETE allowed.

    Enforced at application layer — no update/delete methods exposed.
    """

    __tablename__ = "approval_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    approver_email: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[ApprovalDecision] = mapped_column(
        Enum(ApprovalDecision, values_callable=_enum_values), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SecurityFinding(Base):
    """Security findings detected by PreToolUse/PostToolUse hooks.

    Stores prompt injection, egress, and other security events for audit and analysis.
    """

    __tablename__ = "security_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id"), nullable=False)
    # Type of security finding: prompt_injection, egress, etc.
    finding_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # HIGH, MEDIUM, LOW
    tool_name: Mapped[str] = mapped_column(String(50), nullable=False)
    pattern: Mapped[str] = mapped_column(String(100), nullable=False)  # pattern name/kind
    context_preview: Mapped[str] = mapped_column(Text, default="")  # truncated matched text
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatSession(Base):
    """Chat sessions for the agent chat interface.
    
    Stores conversation history for persistence across page reloads.
    """

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    sdk_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Claude SDK session ID
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    """Individual messages in a chat session."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[ChatSession] = relationship(back_populates="messages")

