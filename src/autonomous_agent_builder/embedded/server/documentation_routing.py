"""Documentation-specialist routing policy for Agent chat."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.agents.definitions import get_subagent_definition
from autonomous_agent_builder.db.models import ChatEvent, Task
from autonomous_agent_builder.knowledge.maintained_freshness import CANONICAL_DOC_REF

DOC_INTENT_TERMS = (
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
DOC_CHANGE_TERMS = (
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
DOC_CREATE_TERMS = (
    "create",
    "generate",
    "add",
    "missing",
)
DOC_REFRESH_TERMS = (
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
TESTING_SCOPE_PATTERNS = (
    ("testing required", "testing_required"),
    ("testing by feature", "testing_by_feature"),
    ("reverse engineering testing", "reverse_engineering"),
    ("forward engineering testing", "forward_engineering"),
    ("end-to-end", "end_to_end"),
    ("end to end", "end_to_end"),
    ("e2e", "end_to_end"),
)
DOCUMENTATION_AGENT_AUTO_APPROVE_TOOLS = frozenset(
    get_subagent_definition("documentation-agent").tools
)
DOCUMENTATION_CONTINUATION_PHRASES = frozenset(
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


def message_has_documentation_intent(user_message: str) -> bool:
    lower_message = user_message.lower()
    return any(term in lower_message for term in DOC_INTENT_TERMS)


def message_suggests_recent_change(user_message: str) -> bool:
    lower_message = user_message.lower()
    return any(term in lower_message for term in DOC_CHANGE_TERMS)


def normalized_follow_up_message(user_message: str) -> str:
    collapsed = " ".join(user_message.lower().split())
    return re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", collapsed)


def message_matches_documentation_continuation(user_message: str) -> bool:
    normalized = normalized_follow_up_message(user_message)
    if not normalized or len(normalized.split()) > 4:
        return False
    return normalized in DOCUMENTATION_CONTINUATION_PHRASES


def task_required_docs(depends_on: dict[str, Any] | None) -> list[str]:
    if not isinstance(depends_on, dict):
        return []
    system_docs = depends_on.get("system_docs")
    if not isinstance(system_docs, dict):
        return []
    required_docs = system_docs.get("required_docs") or []
    if not isinstance(required_docs, list):
        return []
    return [str(item).strip() for item in required_docs if str(item).strip()]


def task_has_doc_expectations(task: Task | None) -> bool:
    if task is None:
        return False
    if task_required_docs(task.depends_on):
        return True
    haystacks = [
        str(task.title or "").lower(),
        str(task.description or "").lower(),
        str(getattr(task.feature, "title", "") or "").lower(),
        str(getattr(task.feature, "description", "") or "").lower(),
    ]
    return any(term in haystack for haystack in haystacks for term in DOC_INTENT_TERMS)


def documentation_testing_scope(user_message: str) -> str:
    lower_message = user_message.lower()
    for pattern, scope in TESTING_SCOPE_PATTERNS:
        if pattern in lower_message:
            return scope
    return ""


def documentation_target_doc_type(
    user_message: str, targeted_docs: list[dict[str, Any]]
) -> str:
    lower_message = user_message.lower()
    if documentation_testing_scope(user_message):
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


def documentation_mode(user_message: str, target_doc_type: str) -> str:
    lower_message = user_message.lower()
    if any(term in lower_message for term in DOC_CREATE_TERMS):
        return "create"
    if target_doc_type == "system-docs" or any(
        term in lower_message
        for term in ("knowledge base", "knowledgebase", "system doc", "system docs")
    ):
        return "refresh"
    if any(term in lower_message for term in DOC_REFRESH_TERMS):
        return "refresh"
    return "update"


def resolve_documentation_action(
    *,
    user_message: str,
    targeted_docs: list[dict[str, Any]],
    current_branch: str,
    canonical_ref: str = CANONICAL_DOC_REF,
) -> dict[str, Any]:
    target_doc_type = documentation_target_doc_type(user_message, targeted_docs)
    mode = documentation_mode(user_message, target_doc_type)
    testing_scope = documentation_testing_scope(user_message)
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


async def most_recent_specialist_before_current_turn(
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


async def select_specialist_route(
    *,
    db: AsyncSession,
    project_root: Path,
    session_id: str,
    user_message: str,
    policies: dict[str, SpecialistRoutePolicy],
) -> ActiveSpecialistRoute | None:
    for policy in policies.values():
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
            return ActiveSpecialistRoute(
                policy=policy, route_reason="explicit_intent", context=context
            )

    previous_specialist = await most_recent_specialist_before_current_turn(db, session_id)
    if previous_specialist:
        policy = policies.get(previous_specialist)
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

    for policy in policies.values():
        context = await policy.context_builder(db, project_root, user_message)
        if context is not None:
            route_reason = str(context.get("route_reason", "")).strip() or "implicit"
            return ActiveSpecialistRoute(policy=policy, route_reason=route_reason, context=context)

    return None
