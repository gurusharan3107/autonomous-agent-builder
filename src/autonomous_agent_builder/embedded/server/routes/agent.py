"""Agent chat API routes for embedded server."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from autonomous_agent_builder.agents.definitions import get_agent_definition
from autonomous_agent_builder.agents.execution_policy import resolve_agent_runtime_policy
from autonomous_agent_builder.agents.runner import AgentRunner, RunResult
from autonomous_agent_builder.agents.tool_registry import is_read_only_tool
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import (
    Approval,
    ApprovalDecision,
    ApprovalGate,
    ApprovalLog,
    BacklogItemType,
    ChatEvent,
    ChatSession,
    Feature,
    FeatureStatus,
    Sprint,
    Task,
    TaskStatus,
    set_task_status,
    utcnow,
)
from autonomous_agent_builder.db.session import get_db, get_session_factory
from autonomous_agent_builder.embedded.server import agent_chat_sessions, agent_chat_transcript
from autonomous_agent_builder.embedded.server.agent_api_models import (
    ChatHistoryResponse,
    ChatMetaResponse,
    ChatRequest,
    ChatRespondRequest,
    ChatRespondResponse,
    ChatResponse,
    ChatSessionItem,
    ChatSessionListResponse,
    RuntimeSettingsUpdate,
)
from autonomous_agent_builder.embedded.server.agent_chat_events import (
    append_chat_event as _append_chat_event,
)
from autonomous_agent_builder.embedded.server.agent_chat_events import (
    append_voice_final_summary_if_needed as _append_voice_final_summary_if_needed,
)
from autonomous_agent_builder.embedded.server.agent_chat_events import (
    update_request_event as _update_request_event,
)
from autonomous_agent_builder.embedded.server.agent_control_owners import (
    reconcile_session_control_owners,
)
from autonomous_agent_builder.embedded.server.agent_delivery_closeout import (
    append_delivery_closeout_if_ready as _append_delivery_closeout_if_ready,
)
from autonomous_agent_builder.embedded.server.agent_documentation_context import (
    documentation_context_pack as _documentation_context_pack,
)
from autonomous_agent_builder.embedded.server.agent_feature_delivery import (
    feature_for_delivery_permission_question as _feature_for_delivery_permission_question,
)
from autonomous_agent_builder.embedded.server.agent_feature_delivery import (
    latest_saved_feature_for_delivery as _latest_saved_feature_for_delivery,
)
from autonomous_agent_builder.embedded.server.agent_feature_delivery import (
    persist_feature_spec as _persist_feature_spec,
)
from autonomous_agent_builder.embedded.server.agent_feature_delivery import (
    schedule_task_dispatch as _schedule_task_dispatch,
)
from autonomous_agent_builder.embedded.server.agent_feature_payloads import (
    FEATURE_LIST_MARKER as _FEATURE_LIST_MARKER,
)
from autonomous_agent_builder.embedded.server.agent_feature_payloads import (
    extract_feature_list_payload as _extract_feature_list_payload,
)
from autonomous_agent_builder.embedded.server.agent_feature_payloads import (
    extract_feature_spec_payload as _extract_feature_spec_payload,
)
from autonomous_agent_builder.embedded.server.agent_feature_payloads import (
    session_has_pending_feature_spec as _session_has_pending_feature_spec,
)
from autonomous_agent_builder.embedded.server.agent_feature_payloads import (
    session_has_saved_feature_for_delivery as _session_has_saved_feature_for_delivery,
)
from autonomous_agent_builder.embedded.server.agent_message_intent import (
    message_confirms_feature_delivery as _message_confirms_feature_delivery,
)
from autonomous_agent_builder.embedded.server.agent_message_intent import (
    message_requests_ambiguous_continuation as _message_requests_ambiguous_continuation,
)
from autonomous_agent_builder.embedded.server.agent_message_intent import (
    message_requests_autonomous_continuation as _message_requests_autonomous_continuation,
)
from autonomous_agent_builder.embedded.server.agent_message_intent import (
    message_requests_feature_delivery as _message_requests_feature_delivery,
)
from autonomous_agent_builder.embedded.server.agent_message_intent import (
    message_requests_feature_spec as _message_requests_feature_spec,
)
from autonomous_agent_builder.embedded.server.agent_message_intent import (
    message_requests_read_only_status as _message_requests_read_only_status,
)
from autonomous_agent_builder.embedded.server.agent_message_intent import (
    message_requests_sprint_planning as _message_requests_sprint_planning,
)
from autonomous_agent_builder.embedded.server.agent_observability_context import (
    observability_context_for_prompt as _observability_context_for_prompt,
)
from autonomous_agent_builder.embedded.server.agent_project_context import (
    apply_chat_answers_to_project_context as _apply_chat_answers_to_project_context,
)
from autonomous_agent_builder.embedded.server.agent_project_context import (
    apply_forward_project_constraints as _apply_forward_project_constraints,
)
from autonomous_agent_builder.embedded.server.agent_project_context import (
    collect_ask_user_question_answers as _collect_ask_user_question_answers,
)
from autonomous_agent_builder.embedded.server.agent_project_context import (
    extract_technical_constraints as _extract_technical_constraints,
)
from autonomous_agent_builder.embedded.server.agent_project_context import (
    inject_feature_list_constraints as _inject_feature_list_constraints,
)
from autonomous_agent_builder.embedded.server.agent_runtime_status import (
    chat_run_status_payload as _chat_run_status_payload,
)
from autonomous_agent_builder.embedded.server.agent_runtime_status import (
    chat_runtime_metadata as _chat_runtime_metadata,
)
from autonomous_agent_builder.embedded.server.agent_runtime_status import (
    initial_status as _initial_status,
)
from autonomous_agent_builder.embedded.server.agent_runtime_status import (
    runtime_metadata_for_agent as _runtime_metadata_for_agent,
)
from autonomous_agent_builder.embedded.server.agent_sprint_planning import (
    append_persisted_delivery_permission_question_if_needed as _append_persisted_delivery_permission_question_if_needed,
)
from autonomous_agent_builder.embedded.server.agent_sprint_planning import (
    create_delivery_plan_for_approved_features as _create_delivery_plan_for_approved_features,
)
from autonomous_agent_builder.embedded.server.agent_sprint_planning import (
    handle_sprint_planning_turn as _handle_sprint_planning_turn,
)
from autonomous_agent_builder.embedded.server.agent_sprint_planning import (
    session_has_pending_sprint_planning as _session_has_pending_sprint_planning,
)
from autonomous_agent_builder.embedded.server.agent_tool_policy import (
    extract_tool_text_payload as _extract_tool_text_payload,
)
from autonomous_agent_builder.embedded.server.agent_tool_policy import (
    feature_spec_tool_denial as _feature_spec_tool_denial,
)
from autonomous_agent_builder.embedded.server.agent_tool_policy import (
    kb_validate_policy as _kb_validate_policy,
)
from autonomous_agent_builder.embedded.server.agent_tool_policy import (
    normalize_tool_response as _normalize_tool_response,
)
from autonomous_agent_builder.embedded.server.agent_tool_policy import (
    permission_allow as _permission_allow,
)
from autonomous_agent_builder.embedded.server.agent_tool_policy import (
    permission_deny as _permission_deny,
)
from autonomous_agent_builder.embedded.server.agent_tool_policy import (
    tool_summary as _tool_summary,
)
from autonomous_agent_builder.embedded.server.agent_workspace_surface import (
    has_generated_app_surface as _has_generated_app_surface,
)
from autonomous_agent_builder.embedded.server.chat_state import ChatSessionHub
from autonomous_agent_builder.embedded.server.chat_turn_direct_actions import (
    publish_direct_chat_turn_if_handled,
)
from autonomous_agent_builder.embedded.server.chat_turn_intent import (
    ChatRunTotals,
    ChatTurnCallbackState,
    ChatTurnIntent,
    resolve_chat_turn_intent,
)
from autonomous_agent_builder.embedded.server.chat_turn_prompting import (
    build_chat_turn_prompt_plan,
    publish_chat_context_budget,
)
from autonomous_agent_builder.embedded.server.chat_turn_publication import ChatTurnPublisher
from autonomous_agent_builder.embedded.server.chat_turn_runtime import run_chat_runtime_loop
from autonomous_agent_builder.embedded.server.documentation_routing import (
    DOCUMENTATION_AGENT_AUTO_APPROVE_TOOLS as _DOCUMENTATION_AGENT_AUTO_APPROVE_TOOLS,
)
from autonomous_agent_builder.embedded.server.documentation_routing import (
    ActiveSpecialistRoute,
    SpecialistRoutePolicy,
    normalized_follow_up_message,
    select_specialist_route,
)
from autonomous_agent_builder.embedded.server.documentation_routing import (
    message_has_documentation_intent as _message_has_documentation_intent,
)
from autonomous_agent_builder.embedded.server.documentation_routing import (
    message_matches_documentation_continuation as _message_matches_documentation_continuation,
)
from autonomous_agent_builder.logs.diagnostics import summarize_chat_event, summarize_tool_event
from autonomous_agent_builder.onboarding import (
    load_onboarding_state,
    publish_onboarding_snapshot,
    sync_forward_engineering_feature_backlog,
    write_feature_list_file,
)
from autonomous_agent_builder.runtime import create_runtime
from autonomous_agent_builder.services.project_context import request_project_root
from autonomous_agent_builder.services.readiness import (
    READY_STATE,
    assess_readiness,
    load_readiness_status,
)
from autonomous_agent_builder.services.runtime_settings import (
    persist_runtime_settings,
    reconcile_runtime_project_state,
    resolve_project_runtime_config,
    runtime_settings_payload,
)
from autonomous_agent_builder.services.task_dispatch_policy import (
    task_dispatch_sort_key,
    task_is_dispatchable,
)

router = APIRouter()

_INIT_PROJECT_MAX_REQUIREMENTS_CONTINUATIONS = 6
_USER_QUESTION_TOOL_NAMES = {
    "AskUserQuestion",
    "request_user_input",
}
def _project_root(request: Request) -> Path:
    return request_project_root(request)


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
    return await _first_dispatchable_task(db) is not None


async def _has_recoverable_task_state(db: AsyncSession) -> bool:
    return await _first_recoverable_task(db) is not None


async def _has_ready_delivery_feature_state(db: AsyncSession) -> bool:
    result = await db.execute(
        select(Feature.id)
        .where(Feature.item_type == BacklogItemType.FEATURE)
        .where(
            Feature.status.in_(
                [
                    FeatureStatus.BACKLOG,
                    FeatureStatus.SPRINT_BACKLOG,
                    FeatureStatus.SPRINT_CANDIDATE,
                    FeatureStatus.SPRINT_PLANNED,
                ]
            )
        )
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
            select(Task)
            .options(selectinload(Task.feature).selectinload(Feature.project))
            .where(Task.id.in_(generated_task_ids))
        )
        tasks_by_id = {task.id: task for task in task_result.scalars().all()}
        for task_id in generated_task_ids:
            task = tasks_by_id.get(task_id)
            if task is None or task.status == TaskStatus.DONE:
                continue
            if task_is_dispatchable(task):
                return task
            break

    result = await db.execute(
        select(Task)
        .options(selectinload(Task.feature).selectinload(Feature.project))
        .order_by(Task.updated_at.desc(), Task.created_at.desc())
    )
    dispatchable_tasks = sorted(
        [task for task in result.scalars().all() if task_is_dispatchable(task)],
        key=task_dispatch_sort_key,
    )
    return dispatchable_tasks[0] if dispatchable_tasks else None


async def _first_recoverable_task(db: AsyncSession) -> Task | None:
    recoverable_statuses = [
        TaskStatus.BLOCKED,
        TaskStatus.CAPABILITY_LIMIT,
        TaskStatus.FAILED,
    ]
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
        generated_task_order = {task_id: index for index, task_id in enumerate(generated_task_ids)}
        task_result = await db.execute(
            select(Task)
            .options(selectinload(Task.feature).selectinload(Feature.project))
            .where(Task.id.in_(generated_task_ids))
            .where(Task.status.in_(recoverable_statuses))
        )
        recoverable_tasks = sorted(
            task_result.scalars().all(),
            key=lambda task: generated_task_order.get(task.id, len(generated_task_order)),
        )
        if recoverable_tasks:
            return recoverable_tasks[0]

    result = await db.execute(
        select(Task)
        .options(selectinload(Task.feature).selectinload(Feature.project))
        .where(Task.status.in_(recoverable_statuses))
        .order_by(Task.updated_at.desc(), Task.created_at.desc())
    )
    return result.scalars().first()


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


def _stream_deltas_are_user_visible(runtime_name: str) -> bool:
    """Return whether runtime chunk deltas should be shown in the Agent transcript.

    The dashboard contract is to show Builder-owned, user-facing transcript text
    without leaking SDK-specific reasoning. Codex app-server deltas can surface
    draft/planning content before the final assistant message is settled, so the
    Agent page should wait for the completed assistant message instead.
    """

    return runtime_name != "codex_sdk"


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


def _normalized_follow_up_message(user_message: str) -> str:
    return normalized_follow_up_message(user_message)


async def _select_specialist_route(
    db: AsyncSession,
    project_root: Path,
    session_id: str,
    user_message: str,
) -> ActiveSpecialistRoute | None:
    return await select_specialist_route(
        db=db,
        project_root=project_root,
        session_id=session_id,
        user_message=user_message,
        policies=_SPECIALIST_ROUTE_POLICIES,
    )


def _general_chat_prompt(
    project_root: Path,
    user_message: str,
    documentation_context: dict[str, Any] | None = None,
    *,
    runtime_sdk: str = "",
    recent_context: str = "",
    model_backed_delivery_context: bool = False,
    forward_engineering_context: bool = False,
) -> str:
    question_guidance = _question_tool_guidance(runtime_sdk)
    continuation_guidance = ""
    if _message_requests_autonomous_continuation(user_message):
        continuation_guidance = (
            "\n\nAutonomous continuation mode is active for this turn.\n"
            "- Treat the user's message as a request to keep the build moving, not as a request "
            "for a status report or menu.\n"
            "- First inspect Builder-owned Board/task state with `mcp__builder__board`, "
            "`mcp__builder__task_show`, or `mcp__builder__task_status`.\n"
            "- Derive the next tool call from your responsibility as the Agent page operator: "
            "recover blocked work, dispatch ready work, or ask a bounded clarification.\n"
            "- If exactly one blocked, failed, or capability-limited Board task is the next "
            "blocking item, call `mcp__builder__task_recover` for that task and then "
            "`mcp__builder__task_dispatch` to continue it.\n"
            "- If there is an active or pending dispatchable task, call "
            "`mcp__builder__task_dispatch` for that exact task.\n"
            "- Do not ask the user which listed feature to build when the board already gives "
            "a deterministic next task by status and priority.\n"
            "- Ask the user only for genuinely missing product direction, credentials, external "
            "approval, or another decision that cannot be inferred from repo state.\n"
            "- If multiple tasks could be recovered or dispatched, use `AskUserQuestion` instead "
            "of guessing.\n"
        )
    elif model_backed_delivery_context:
        continuation_guidance = (
            "\n\nModel-backed delivery context is active for this turn.\n"
            "- The user's message must be interpreted by you, the selected runtime model; do not "
            "treat it as a fixed command or deterministic shortcut.\n"
            "- Use the available Builder tools to inspect the ready Board work, decide the next "
            "action, and choose any needed tool chain. Useful surfaces include Board/task state, "
            "task detail/status, and dispatch, but you choose which tools to call and in what "
            "order.\n"
            "- If Builder Board evidence shows a pending or otherwise dispatchable task for the "
            "approved sprint, dispatch that Board task with `mcp__builder__task_dispatch` before "
            "any source edits, shell commands, tests, or generated-app changes. The task pipeline "
            "owns implementation, verification, integration, and closeout evidence.\n"
            "- Do not use generic code-editing or shell tools to implement approved sprint work "
            "directly from this chat turn; that bypasses Board synchronization and pollutes the "
            "user-facing lifecycle.\n"
            "- The product goal is to continue the approved delivery without asking the operator "
            "for task IDs, backlog terms, sprint terms, or lifecycle terminology.\n"
            "- If the next product action is still ambiguous after bounded Builder evidence, use "
            "`AskUserQuestion` with plain product wording.\n"
        )
    forward_guidance = ""
    if forward_engineering_context:
        forward_guidance = (
            "\n\nForward-engineering project context is active for this turn.\n"
            "- This workspace is ready for a first app/product scope, but the user's prompt still "
            "owns intent. Do not treat every prompt as a request to start requirements gathering.\n"
            "- If the user is greeting you, checking whether the Agent page works, or otherwise "
            "not asking for product work, answer naturally and ask what they want to build only as "
            "an optional next step.\n"
            "- If the user names a product or app they want to build, use model judgment to decide "
            "whether to answer directly, ask product-tailoring questions, or emit "
            "`FEATURE_SPEC_JSON:`. Do not use tool calls or structured questions just because this "
            "is a clean-slate workspace; choose the minimum useful tool path for the actual prompt.\n"
            "- For broad first-product prompts, bias toward requirements intake before delivery "
            "approval. The goal is to get enough user-specific requirements that the first backlog "
            "is much closer to what this user actually wants, not a generic MVP inferred from the "
            "product category.\n"
            "- Ask runtime-native structured questions only when they will materially improve the "
            "first backlog. If the user already provided enough specific audience, workflow, data, "
            "success criteria, and product-tone constraints to make the first version genuinely "
            "tailored, emit `FEATURE_SPEC_JSON:` without extra questioning.\n"
            "- When questions are needed, ask as many product-shaping questions or follow-up rounds "
            "as the specification needs. Use one question when the answer changes the next follow-up; "
            "batch independent questions when that is more efficient. Do not cap the total interview "
            "at one question or one structured request. Each structured-choice question should have "
            "2-3 plain-language choices with the recommended option first.\n"
            "- Good first-product tailoring dimensions include: who will use it, the core daily "
            "workflow, what data matters, what outcome the user wants to see first, privacy or "
            "persistence expectations, and the product tone or interaction style. Do not ask for "
            "technical implementation details unless they materially affect the user experience.\n"
            "- Do not convert a first product idea directly into `Ready for Builder to start now` "
            "approval. Approval belongs after the product is tailored enough to describe the first "
            "shippable scope in user terms.\n"
        )
    prompt = (
        "You are a helpful AI assistant for the project rooted at "
        f"{project_root}.\n\n"
        "Answer the user's question directly. Use the repo context when it improves correctness. "
        "When the user references prior discussion, memory, recommendations, existing backlog, "
        "current sprint, board state, or project history, first inspect the relevant Builder "
        "surface with available tools such as builder memory search, builder backlog item list/show, "
        "builder task list/show, or compact repo commands before asking the user for missing context. "
        "For observability, metrics, or recommendation questions, analyze the operator's intent and "
        "use compact Builder-owned evidence first, such as bounded logs, metrics, and observability "
        "summaries; avoid raw or full outputs unless the compact evidence is insufficient. "
        "When answering from board state, distinguish global board counts from current or selected "
        "sprint counts when both are available. "
        "Allowed Builder actions in this chat lane: inspect read-only Builder state, explain what "
        "the state means, propose the next safe operator step, ask a bounded question, request "
        "explicit approval for a prepared action, and execute requested mutations through granted "
        "Builder tools when the exact target and consequence are clear or the visible approval path "
        "confirms them. Not allowed: invent a `don't-ask mode`, treat a broad instruction as "
        "approval, claim that you will mark, move, clear, delete, approve, deny, dispatch, or ship "
        "Builder backlog/Board/approval state unless an allowed Builder tool for that exact mutation "
        "has been granted and the visible approval/prepared-action path has confirmed the exact "
        "target and consequence. For bulk requests such as clearing backlog, "
        "marking everything shipped, or approving/denying many items, use runtime judgment to inspect "
        "read-only state first, then explain the risk and ask for the specific visible product action "
        "or approval needed; do not proceed silently. "
        "For free-form product requests, you own intent understanding. The operator does not need to "
        "know backlog, sprint, product backlog, or task terminology. If the user asks to add a feature "
        "or improve an existing app, decide whether the scope is clear enough. If it is unclear, ask the next "
        "plain product question through the runtime-native structured question mechanism. If it is clear, "
        "summarize the agreed improvement and emit `FEATURE_SPEC_JSON:` followed immediately by one raw "
        "JSON object with title, description, priority, acceptance_criteria, and dependencies. Do not "
        "tell the user to create backlog items, plan a sprint, or create tasks; Builder handles those "
        "internal lifecycle steps after the captured improvement is approved. "
        "Do not say you will check memory, backlog, board, or project state unless you actually use "
        "the corresponding tool in that turn. Ask for clarification only after bounded retrieval cannot "
        "resolve the missing context. "
        f"{question_guidance}\n\n"
        f"Project root: {project_root}\n\n"
        f"User: {user_message}"
        f"{continuation_guidance}"
        f"{forward_guidance}"
    )
    if recent_context.strip():
        prompt = (
            f"{prompt}\n\n"
            "Bounded retrieval context already available for this turn. Use this context before "
            "asking the user to restate prior discussion:\n"
            f"{recent_context.strip()}"
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


_RECENT_CONTEXT_TERMS = (
    "previous",
    "prior",
    "recent conversation",
    "conversation",
    "discussed",
    "recommendation",
    "recommendations",
    "backlog",
    "sprint",
    "board",
    "history",
    "memory",
)
_RECENT_CONTEXT_EVENT_LIMIT = 6
_RECENT_CONTEXT_ENTRY_CHARS = 280
def _message_needs_recent_context(user_message: str) -> bool:
    normalized = " ".join(user_message.lower().split())
    return any(term in normalized for term in _RECENT_CONTEXT_TERMS)


def _recent_chat_context_for_prompt(
    session: ChatSession,
    user_message: str,
    *,
    limit: int = _RECENT_CONTEXT_EVENT_LIMIT,
) -> str:
    """Build a compact deterministic transcript pack for referential chat turns."""
    if not _message_needs_recent_context(user_message):
        return ""
    entries: list[str] = []
    events = sorted(
        (event for event in session.events if event.event_type in agent_chat_transcript.VISIBLE_EVENT_TYPES),
        key=lambda event: event.created_at,
    )
    for event in events:
        event_type = event.event_type
        payload = event.payload_json or {}
        if event_type == "voice_operator_message":
            label = "Operator by voice"
            content = str(payload.get("content") or "").strip()
        elif event_type == "user_message":
            label = "Samantha delegated" if payload.get("source") == "realtime_voice" else "User"
            content = str(payload.get("content") or "").strip()
        elif event_type == "assistant_message":
            label = "Builder Agent"
            content = str(payload.get("content") or "").strip()
        elif event_type == "ask_user_question":
            label = "Pending question"
            content = str(payload.get("question") or payload.get("summary") or "").strip()
        elif event_type == "tool_approval_request":
            label = "Pending approval"
            content = str(payload.get("summary") or payload.get("tool_name") or "").strip()
        else:
            continue
        normalized = " ".join(content.split())
        if not normalized:
            continue
        truncated = len(normalized) > _RECENT_CONTEXT_ENTRY_CHARS
        preview = normalized[:_RECENT_CONTEXT_ENTRY_CHARS].rstrip()
        if truncated:
            preview = f"{preview}..."
        entries.append(f"- {label}: {preview}")
    if not entries:
        return "No prior Agent-page transcript events were found in this Builder session."
    selected = entries[-limit:]
    omitted = max(len(entries) - len(selected), 0)
    if omitted:
        selected.insert(0, f"- Context pack clipped {omitted} older event(s).")
    return "\n".join(selected)


def _feature_spec_chat_prompt(
    project_root: Path,
    user_message: str,
    *,
    runtime_sdk: str = "",
) -> str:
    question_guidance = _question_tool_guidance(runtime_sdk)
    return f"""You are the improvement-scoping guide for an already-initialized software project.

Your job is to turn a sufficiently bounded user request into one concrete improvement that Builder can ship.

Rules:
- Use the existing session context. Treat short follow-up replies as answers to your most recent clarifying question when they resolve it.
- Keep the scope to one implementation-sized feature.
- Use read-only repo context only when it materially improves correctness. If the operator prompt is already specific enough to define the improvement, skip shell/file tools and move directly to the next product question or feature payload.
- When repo discovery is necessary, keep it bounded: avoid raw, --full, recursive, or broad file-listing commands; cap shell output to a small command-specific window; prefer targeted `rg` and short file slices over dumping logs, build output, or whole files.
- If the operator names a product or app they want to build, use model judgment to decide whether the first shippable scope is already specific enough or whether user-specific requirements are still needed.
- For broad first-product prompts, bias toward product-tailoring questions before feature capture. The goal is to avoid a generic MVP inferred from the product category and instead capture enough user-specific requirements that the first backlog item matches this user.
- Ask as many product-shaping questions or follow-up rounds as the specification needs. Use one question when the answer changes the next follow-up; batch independent questions when that is more efficient. Do not cap the interview at one question or one structured request.
- Good first-product tailoring dimensions include: who will use it, the core daily workflow, what data matters, what outcome the user wants to see first, privacy or persistence expectations, and the product tone or interaction style. Do not ask for technical implementation details unless they materially affect the user experience.
- If the request is still ambiguous, continue the interview until the first implementation scope has no obvious gaps.
- Ask non-obvious clarifying questions that materially shape the feature contract.
- {question_guidance}
- Do not ask the user for technical facts that read-only repo discovery can answer.
- Do not repeat a question the user has already answered in the current session.
- Your responsibility stops at one agreed improvement. Do not invent task creation, dispatch, or execution progress in this lane.
- Do not produce documentation-agent output or maintained KB markdown.
- When the scope is ready, summarize the agreed feature briefly and emit the feature payload exactly as instructed below.

When the scope is NOT ready:
- Ask the next highest-leverage question or compact set of independent
  questions through the runtime-native structured question mechanism described
  above. Continue for as many rounds as the product specification needs.

When the scope IS ready:
- Start the response with `AGREEMENT:` followed by a concise implementation-oriented summary.
- Then emit `FEATURE_SPEC_JSON:` followed immediately by one raw JSON object and nothing else after that object.

The JSON object must match this shape exactly:
{{
  "title": "Meaningful improvement title",
  "description": "What the improvement delivers and its boundaries",
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
            "`questions` array with concise `header` and `question` fields and exactly 3 "
            "suggested `options`, each with `label` and `description`; put the recommended "
            "option first and suffix its label with `(Recommended)`. The Agent page provides "
            "the fourth path as an inline custom-answer text box when the operator has something "
            "else in mind. This is operator-facing UI: use plain product wording and do not include "
            "internal terms such as backlog, sprint, task id, lifecycle, bounded, raw logs, full logs, "
            "chunk, or token pressure."
        )
    if normalized_sdk == "openai_agents":
        return (
            "When a bounded user decision is required, call the OpenAI Agents SDK "
            "`request_user_input` function tool rather than writing a manual multiple-choice "
            "list in plain text. Pass a `questions` array with concise `header` and `question` "
            "fields and exactly 3 suggested `options`, each with `label` and `description`; put "
            "the recommended option first and suffix its label with `(Recommended)`. The Agent page "
            "provides the fourth path as an inline custom-answer text box when the operator has "
            "something else in mind. This is operator-facing UI: use plain product wording and do not "
            "include internal terms such as backlog, sprint, task id, lifecycle, bounded, raw logs, "
            "full logs, chunk, or token pressure."
        )
    return (
        "When there are a few clear choices, use AskUserQuestion with concise headers, exactly "
        "3 suggested options, short labels, and the recommended option first. The Agent page "
        "provides the fourth path as an inline custom-answer text box when the operator has "
        "something else in mind. When any bounded user decision is required, use AskUserQuestion "
        "rather than writing a manual multiple-choice list in plain text. Never infer a `don't-ask "
        "mode`; if a user request needs a decision or approval, ask through the structured question "
        "or approval path. This is operator-facing UI: use plain product wording and do not include "
        "internal terms such as backlog, sprint, task id, lifecycle, bounded, raw logs, full logs, "
        "chunk, or token pressure."
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
- Ask the next highest-leverage question or compact set of independent
  questions through the runtime-native structured question mechanism described
  above. Continue for as many rounds as the product specification needs.

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


async def _resolve_chat_turn_intent(
    *,
    session: ChatSession,
    user_message: str,
    agent_name: str,
    active_specialist: ActiveSpecialistRoute | None,
) -> ChatTurnIntent:
    autonomous_continuation_requested = _message_requests_autonomous_continuation(user_message)
    ambiguous_continuation_requested = _message_requests_ambiguous_continuation(user_message)
    active_specialist_present = active_specialist is not None
    dispatchable_task_exists = False
    ready_delivery_feature_exists = False
    if agent_name == "chat" and not active_specialist_present:
        session_factory = get_session_factory()
        async with session_factory() as db:
            dispatchable_task_exists = await _has_dispatchable_task_state(db)
            ready_delivery_feature_exists = await _has_ready_delivery_feature_state(db)
    explicit_sprint_planning_intent = _message_requests_sprint_planning(user_message)
    review_approval_continuation_requested = False
    if autonomous_continuation_requested and agent_name == "chat" and not active_specialist_present:
        session_factory = get_session_factory()
        async with session_factory() as db:
            review_approval_continuation_requested = (
                await _first_pending_review_approval(db)
            ) is not None
    return resolve_chat_turn_intent(
        agent_name=agent_name,
        active_specialist_present=active_specialist_present,
        autonomous_continuation_requested=autonomous_continuation_requested,
        ambiguous_continuation_requested=ambiguous_continuation_requested,
        dispatchable_task_exists=dispatchable_task_exists,
        ready_delivery_feature_exists=ready_delivery_feature_exists,
        explicit_sprint_planning_intent=explicit_sprint_planning_intent,
        read_only_status_requested=_message_requests_read_only_status(user_message),
        documentation_intent_requested=_message_has_documentation_intent(user_message),
        feature_spec_message_requested=_message_requests_feature_spec(user_message),
        feature_delivery_message_requested=_message_requests_feature_delivery(user_message),
        feature_delivery_confirmed=_message_confirms_feature_delivery(user_message),
        session_has_saved_feature_for_delivery=_session_has_saved_feature_for_delivery(session),
        session_has_pending_feature_spec=_session_has_pending_feature_spec(session),
        session_has_pending_sprint_planning=_session_has_pending_sprint_planning(session),
        review_approval_continuation_requested=review_approval_continuation_requested,
    )


async def _publish_agent_run_error_result(
    *,
    session_id: str,
    hub: ChatSessionHub,
    agent_name: str,
    project_root: Path,
    active_specialist: ActiveSpecialistRoute | None,
    publish_specialist_status: Callable[..., Awaitable[None]],
    result: RunResult,
    totals: ChatRunTotals,
    max_turns: int,
) -> None:
    if active_specialist is not None:
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
    await hub.publish(session_id, agent_chat_transcript.serialize_event(error_event).model_dump(mode="json"))
    status_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload=_chat_run_status_payload(
            agent_name=agent_name,
            project_root=project_root,
            result=result,
            totals=totals,
            max_turns=max_turns,
            extra={"error": result.error},
        ),
        status="completed",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(status_event).model_dump(mode="json"))


async def _publish_provider_limit_result(
    *,
    session_id: str,
    hub: ChatSessionHub,
    agent_name: str,
    project_root: Path,
    active_specialist: ActiveSpecialistRoute | None,
    publish_specialist_status: Callable[..., Awaitable[None]],
    result: RunResult,
    totals: ChatRunTotals,
    max_turns: int,
) -> None:
    provider_limit = result.provider_limit or {
        "code": result.stop_reason or "capability_limit",
        "reason": result.output_text or "Agent run hit a capability limit.",
    }
    if active_specialist is not None:
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
        payload={
            "content": visible_response,
            "final": True,
            "provider_limit": provider_limit,
        },
        status="blocked",
        mirror_message=("assistant", visible_response, 0, 0.0),
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(assistant_event).model_dump(mode="json"))
    await _append_voice_final_summary_if_needed(
        session_id,
        assistant_event_id=assistant_event.id,
        content=visible_response,
        hub=hub,
    )
    status_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload=_chat_run_status_payload(
            agent_name=agent_name,
            project_root=project_root,
            result=result,
            totals=totals,
            max_turns=max_turns,
            stop_reason="provider_limit",
            extra={"provider_limit": provider_limit},
        ),
        status="blocked",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(status_event).model_dump(mode="json"))


async def _handle_chat_tool_event(
    state: ChatTurnCallbackState,
    publish_specialist_status: Callable[..., Awaitable[None]],
    event_data: dict[str, Any] | None = None,
    **event_kwargs: Any,
) -> None:
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
        state.session_id,
        event_type=event_type,
        payload=payload,
        status="completed",
        tool_use_id=str(tool_use_id) if tool_use_id else None,
    )
    await state.hub.publish(
        state.session_id,
        agent_chat_transcript.serialize_event(tool_event).model_dump(mode="json"),
    )
    if (
        event_type == "tool_result"
        and state.agent_name == "chat"
        and tool_name == "mcp__builder__task_dispatch"
        and (
            _message_requests_autonomous_continuation(state.user_message)
            or state.model_backed_delivery_context_requested
        )
    ):
        dispatch_payload = _extract_tool_text_payload(tool_response)
        if dispatch_payload.get("status") == "dispatched":
            status_event = await _append_chat_event(
                state.session_id,
                event_type="run_status",
                payload={
                    **_runtime_metadata_for_agent(state.agent_name, state.project_root),
                    "running": False,
                    "current_turn": 0,
                    "max_turns": state.agent_max_turns,
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
            await state.hub.publish(
                state.session_id,
                agent_chat_transcript.serialize_event(status_event).model_dump(mode="json"),
            )
    if tool_name == "TodoWrite":
        todos = tool_input.get("todos", []) or []
        todo_event = await _append_chat_event(
            state.session_id,
            event_type="todo_snapshot",
            payload={
                "todos": todos,
                "pending_count": sum(1 for todo in todos if todo.get("status") == "pending"),
                "in_progress_count": sum(
                    1 for todo in todos if todo.get("status") == "in_progress"
                ),
                "completed_count": sum(
                    1 for todo in todos if todo.get("status") == "completed"
                ),
            },
            status="completed",
            tool_use_id=str(tool_use_id) if tool_use_id else None,
        )
        await state.hub.publish(
            state.session_id,
            agent_chat_transcript.serialize_event(todo_event).model_dump(mode="json"),
        )
    if state.active_specialist is not None:
        next_phase = ""
        if (
            tool_name.endswith("__kb_search")
            or tool_name.endswith("__task_show")
            or tool_name.endswith("__kb_contract")
        ):
            next_phase = "discovering"
        elif (
            tool_name.endswith("__kb_lint")
            or tool_name.endswith("__kb_add")
            or tool_name.endswith("__kb_update")
        ):
            next_phase = "publishing"
        elif tool_name.endswith("__kb_show") or tool_name.endswith("__kb_validate"):
            next_phase = "verifying"
        if next_phase and next_phase != state.specialist_phase:
            phase_label = next_phase.capitalize()
            await publish_specialist_status(
                next_phase,
                f"{state.active_specialist.policy.name} {phase_label.lower()} repo-local KB docs.",
                status="running",
            )
            state.specialist_phase = next_phase


async def _authorize_chat_tool(
    state: ChatTurnCallbackState,
    tool_name: str,
    input_data: dict[str, Any],
) -> Any:
    if tool_name in _USER_QUESTION_TOOL_NAMES:
        answers: dict[str, str] = {}
        for question in input_data.get("questions", []):
            display_question = agent_chat_transcript.operator_safe_question_payload(question)
            options = display_question.get("options", []) or []
            try:
                recommended_index = int(question.get("recommendedIndex", 0) or 0)
            except (TypeError, ValueError):
                recommended_index = 0
            if (
                state.agent_name == "chat"
                and state.active_specialist is None
                and not state.feature_spec_requested
                and _message_requests_autonomous_continuation(state.user_message)
                and not _message_requests_ambiguous_continuation(state.user_message)
                and 0 <= recommended_index < len(options)
            ):
                recommended_option = options[recommended_index]
                answers[str(question.get("question", ""))] = str(
                    recommended_option.get("label", "")
                ).strip()
                continue
            question_event = await _append_chat_event(
                state.session_id,
                event_type="ask_user_question",
                payload={
                    "header": display_question.get("header", ""),
                    "question": display_question.get("question", ""),
                    "options": options,
                    "multi_select": bool(display_question.get("multiSelect")),
                    "recommended_index": 0,
                    "answered": False,
                    "answer_value": "",
                },
                status="pending",
            )
            future = await state.hub.create_pending_answer(state.session_id, question_event.id)
            await state.hub.publish(
                state.session_id,
                agent_chat_transcript.serialize_event(question_event).model_dump(mode="json"),
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

    if state.feature_spec_requested:
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
                state.session_id,
                event_type="tool_error",
                payload=payload,
                status="completed",
            )
            await state.hub.publish(
                state.session_id,
                agent_chat_transcript.serialize_event(tool_event).model_dump(mode="json"),
            )
            return _permission_deny(deny_reason)

    if (
        state.active_specialist is not None
        and state.active_specialist.name == "documentation-agent"
        and tool_name == "mcp__builder__kb_validate"
    ):
        allowed, updated_input, deny_reason, next_action = _kb_validate_policy(
            state.project_root,
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
            state.session_id,
            event_type="tool_error",
            payload=payload,
            status="completed",
        )
        await state.hub.publish(
            state.session_id,
            agent_chat_transcript.serialize_event(tool_event).model_dump(mode="json"),
        )
        return _permission_deny(f"{deny_reason} {next_action}")

    if (
        state.active_specialist is not None
        and tool_name in state.active_specialist.policy.auto_approve_tools
    ):
        return _permission_allow(input_data)

    if state.agent_name == "chat" and is_read_only_tool(tool_name):
        return _permission_allow(input_data)

    if (
        state.agent_name == "chat"
        and state.active_specialist is None
        and (
            (
                tool_name
                in {
                    "mcp__builder__task_dispatch",
                    "mcp__builder__task_recover",
                }
                and _message_requests_autonomous_continuation(state.user_message)
            )
            or (
                tool_name == "mcp__builder__task_dispatch"
                and state.model_backed_delivery_context_requested
            )
        )
    ):
        return _permission_allow(input_data)

    summary, description = _tool_summary(tool_name, input_data)
    approval_event = await _append_chat_event(
        state.session_id,
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
    future = await state.hub.create_pending_answer(state.session_id, approval_event.id)
    await state.hub.publish(
        state.session_id,
        agent_chat_transcript.serialize_event(approval_event).model_dump(mode="json"),
    )
    response = await future
    decision = str(response.get("decision", "deny")).strip().lower() or "deny"
    reason = str(response.get("reason", "")).strip()
    if decision == "allow":
        return _permission_allow(response.get("updated_input") or input_data)
    return _permission_deny(reason or f"User denied {tool_name}.")


async def _publish_successful_chat_result(
    *,
    session_id: str,
    user_message: str,
    hub: ChatSessionHub,
    agent_name: str,
    project_root: Path,
    active_specialist: ActiveSpecialistRoute | None,
    publish_specialist_status: Callable[..., Awaitable[None]],
    result: RunResult,
    run_totals: ChatRunTotals,
    max_turns: int,
) -> None:
    visible_response = result.output_text or "No response from agent"
    start_sprint_scope_after_response = False
    if agent_name == "init-project-chat":
        visible_response, feature_payload = _extract_feature_list_payload(
            project_root, visible_response
        )
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
                chat_answers = await _collect_ask_user_question_answers(db, session_id)
                if chat_answers:
                    _apply_chat_answers_to_project_context(project_root, chat_answers)
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
                "I captured the delivery scope and prepared Builder's internal plan. "
                "Next I will ask what to ship first."
            )
            visible_response = (
                f"{visible_response}\n\n{save_note}".strip() if visible_response else save_note
            )
    elif agent_name == "chat" and active_specialist is None:
        visible_response, feature_spec_payload = _extract_feature_spec_payload(visible_response)
        if feature_spec_payload is not None:
            session_factory = get_session_factory()
            async with session_factory() as db:
                feature = await _persist_feature_spec(db, feature_spec_payload)
            if feature is not None:
                save_note = (
                    f"I captured that improvement as `{feature.title}`. "
                    "Ready for Builder to start now, or should I hold?"
                )
                visible_response = (
                    f"{visible_response}\n\n{save_note}".strip() if visible_response else save_note
                )
    if active_specialist is not None:
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
            run_totals.token_total,
            run_totals.cost_usd,
        ),
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(assistant_event).model_dump(mode="json"))
    permission_question = await _append_persisted_delivery_permission_question_if_needed(
        session_id,
        assistant_event_id=assistant_event.id,
        response_text=visible_response,
        hub=hub,
    )
    if permission_question is None:
        await _append_voice_final_summary_if_needed(
            session_id,
            assistant_event_id=assistant_event.id,
            content=visible_response,
            hub=hub,
        )
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
        await hub.publish(session_id, agent_chat_transcript.serialize_event(sprint_event).model_dump(mode="json"))
        await _append_voice_final_summary_if_needed(
            session_id,
            assistant_event_id=sprint_event.id,
            content=sprint_response,
            hub=hub,
        )
    status_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload=_chat_run_status_payload(
            agent_name=agent_name,
            project_root=project_root,
            result=result,
            totals=run_totals,
            max_turns=max_turns,
        ),
        status="completed",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(status_event).model_dump(mode="json"))


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
        session = await agent_chat_sessions.load_session(
            db, session_id, project_root=project_root, reject_scope_mismatch=True
        )
        if session is None:
            raise RuntimeError(f"Chat session '{session_id}' not found")
        agent_name = "chat"
        forward_engineering_context = await _needs_init_project_bootstrap(project_root, db)
        agent_def = get_agent_definition(agent_name)
        runtime_policy = resolve_agent_runtime_policy(agent_def, get_settings())
        resume_session = agent_chat_sessions.compatible_resume_session(session, runtime)
        active_specialist = await _select_specialist_route(
            db,
            project_root,
            session_id,
            user_message,
        )
    documentation_context = (
        active_specialist.context
        if active_specialist and active_specialist.name == "documentation-agent"
        else None
    )
    recent_context = _recent_chat_context_for_prompt(session, user_message)
    observability_context = _observability_context_for_prompt(project_root, user_message)
    if observability_context:
        recent_context = (
            f"{recent_context}\n{observability_context}"
            if recent_context.strip()
            else observability_context
        )
    specialist_active = active_specialist is not None
    specialist_phase = ""
    specialist_summary = ""
    model_backed_delivery_context_requested = False

    run_status_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload=_initial_status(agent_name, project_root),
        status="running",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(run_status_event).model_dump(mode="json"))

    async def publish_specialist_status(
        phase: str, content: str, *, status: str = "running"
    ) -> None:
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
        await hub.publish(session_id, agent_chat_transcript.serialize_event(specialist_event).model_dump(mode="json"))

    if specialist_active:
        specialist_phase = "discovering"
        specialist_summary = active_specialist.policy.active_summary
        await publish_specialist_status(
            specialist_phase,
            specialist_summary,
            status="running",
        )

    stream_user_visible = _stream_deltas_are_user_visible(runtime.name)
    callback_state = ChatTurnCallbackState(
        session_id=session_id,
        hub=hub,
        project_root=project_root,
        agent_name=agent_name,
        agent_max_turns=agent_def.max_turns,
        active_specialist=active_specialist,
        user_message=user_message,
        specialist_phase=specialist_phase,
    )
    turn_publisher = ChatTurnPublisher(
        session_id=session_id,
        hub=hub,
        runtime_metadata=_runtime_metadata_for_agent(agent_name, project_root),
        max_turns=agent_def.max_turns,
        append_chat_event=_append_chat_event,
        serialize_event=agent_chat_transcript.serialize_event,
    )

    async def on_stream(text: str) -> None:
        if not stream_user_visible:
            return
        await turn_publisher.publish_stream_delta(text)

    async def on_tool_event(event_data: dict[str, Any] | None = None, **event_kwargs: Any) -> None:
        await _handle_chat_tool_event(
            callback_state,
            publish_specialist_status,
            event_data,
            **event_kwargs,
        )

    async def can_use_tool(tool_name: str, input_data: dict[str, Any], context: Any) -> Any:
        return await _authorize_chat_tool(callback_state, tool_name, input_data)

    try:
        intent = await _resolve_chat_turn_intent(
            session=session,
            user_message=user_message,
            agent_name=agent_name,
            active_specialist=active_specialist,
        )
        model_backed_delivery_context_requested = intent.model_backed_delivery_context_requested
        feature_spec_requested = intent.feature_spec_requested
        callback_state.model_backed_delivery_context_requested = (
            model_backed_delivery_context_requested
        )
        callback_state.feature_spec_requested = feature_spec_requested
        if await publish_direct_chat_turn_if_handled(
            intent=intent,
            session_id=session_id,
            user_message=user_message,
            project_root=project_root,
            turn_publisher=turn_publisher,
            session_factory=get_session_factory(),
            approve_review_gate_for_continuation=_approve_review_gate_for_continuation,
            schedule_task_dispatch=_schedule_task_dispatch,
            latest_saved_feature_for_delivery=_latest_saved_feature_for_delivery,
            handle_sprint_planning_turn=_handle_sprint_planning_turn,
        ):
            return
        prompt_plan = build_chat_turn_prompt_plan(
            agent_name=agent_name,
            feature_spec_requested=feature_spec_requested,
            model_backed_delivery_context_requested=model_backed_delivery_context_requested,
            project_root=project_root,
            user_message=user_message,
            runtime_name=runtime.name,
            documentation_context=documentation_context,
            recent_context=recent_context,
            forward_engineering_context=forward_engineering_context,
            resume_session=resume_session,
            init_project_chat_prompt=_init_project_chat_prompt,
            feature_spec_chat_prompt=_feature_spec_chat_prompt,
            general_chat_prompt=_general_chat_prompt,
        )
        prompt = prompt_plan.prompt
        run_session = prompt_plan.run_session
        await publish_chat_context_budget(
            session_id=session_id,
            hub=hub,
            append_chat_event=_append_chat_event,
            serialize_event=agent_chat_transcript.serialize_event,
            agent_name=agent_name,
            prompt=prompt,
            user_message=user_message,
            recent_context=recent_context,
            documentation_context=documentation_context,
            observability_context=observability_context,
            runtime_metadata=_runtime_metadata_for_agent(agent_name, project_root),
            resume_session=run_session,
            specialist_active=specialist_active,
        )
        result, run_totals = await run_chat_runtime_loop(
            runtime=runtime,
            prompt=prompt,
            agent_name=agent_name,
            project_root=project_root,
            run_session=run_session,
            runtime_policy=runtime_policy,
            feature_spec_requested=feature_spec_requested,
            active_specialist=active_specialist,
            on_stream=on_stream,
            can_use_tool=can_use_tool,
            on_tool_event=on_tool_event,
            max_requirements_continuations=_INIT_PROJECT_MAX_REQUIREMENTS_CONTINUATIONS,
            requires_autonomous_continuation=_init_project_requires_autonomous_continuation,
            continuation_prompt=_init_project_continuation_prompt,
        )
        if result.error:
            await _publish_agent_run_error_result(
                session_id=session_id,
                hub=hub,
                agent_name=agent_name,
                project_root=project_root,
                active_specialist=active_specialist,
                publish_specialist_status=publish_specialist_status,
                result=result,
                totals=run_totals,
                max_turns=agent_def.max_turns,
            )
            return

        if result.stop_reason == "provider_limit":
            await _publish_provider_limit_result(
                session_id=session_id,
                hub=hub,
                agent_name=agent_name,
                project_root=project_root,
                active_specialist=active_specialist,
                publish_specialist_status=publish_specialist_status,
                result=result,
                totals=run_totals,
                max_turns=agent_def.max_turns,
            )
            return

        await _publish_successful_chat_result(
            session_id=session_id,
            user_message=user_message,
            hub=hub,
            agent_name=agent_name,
            project_root=project_root,
            active_specialist=active_specialist,
            publish_specialist_status=publish_specialist_status,
            result=result,
            run_totals=run_totals,
            max_turns=agent_def.max_turns,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if specialist_active:
            await publish_specialist_status(
                "blocked",
                f"{active_specialist.policy.name} stopped: {exc}",
                status="completed",
            )
        await turn_publisher.publish_terminal_error(exc)


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


async def _continue_after_delivery_permission_question(
    app: Any,
    session_id: str,
    event: ChatEvent,
    *,
    answer_value: str,
) -> None:
    project_root = Path(app.state.project_root)
    hub: ChatSessionHub = app.state.chat_hub
    runtime_payload = _runtime_metadata_for_agent("chat", project_root)
    running_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload={
            **runtime_payload,
            "running": True,
            "current_turn": 0,
            "max_turns": get_agent_definition("chat").max_turns,
            "tokens_used": 0,
            "cost_usd": 0.0,
        },
        status="running",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(running_event).model_dump(mode="json"))

    answer_lower = answer_value.strip().lower()
    if answer_lower.startswith("hold"):
        visible_response = "Delivery is on hold. I kept the captured improvement unchanged."
        stop_reason = "delivery_permission_held"
    else:
        session_factory = get_session_factory()
        async with session_factory() as db:
            feature = await _feature_for_delivery_permission_question(db, event)
        if feature is None:
            visible_response = (
                "I could not find the captured improvement for this delivery decision. "
                "Please restate the improvement before starting work."
            )
            stop_reason = "delivery_permission_missing_feature"
        else:
            visible_response = await _handle_sprint_planning_turn(
                session_id,
                feature.title,
                project_root,
                hub,
                selected_feature_ids=[feature.id],
                skip_scope_approval=True,
            )
            stop_reason = "delivery_permission_selected_feature"

    assistant_event = await _append_chat_event(
        session_id,
        event_type="assistant_message",
        payload={"content": visible_response, "final": True},
        status="completed",
        mirror_message=("assistant", visible_response, 0, 0.0),
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(assistant_event).model_dump(mode="json"))
    await _append_voice_final_summary_if_needed(
        session_id,
        assistant_event_id=assistant_event.id,
        content=visible_response,
        hub=hub,
    )
    status_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload={
            **runtime_payload,
            "running": False,
            "current_turn": 0,
            "max_turns": get_agent_definition("chat").max_turns,
            "tokens_used": 0,
            "cost_usd": 0.0,
            "stop_reason": stop_reason,
        },
        status="completed",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(status_event).model_dump(mode="json"))


async def _complete_persisted_delivery_scope_approval(
    app: Any,
    session_id: str,
    event: ChatEvent,
    *,
    decision: str,
) -> None:
    project_root = Path(app.state.project_root)
    hub: ChatSessionHub = app.state.chat_hub
    runtime_payload = _runtime_metadata_for_agent("chat", project_root)
    running_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload={
            **runtime_payload,
            "running": True,
            "current_turn": 0,
            "max_turns": get_agent_definition("chat").max_turns,
            "tokens_used": 0,
            "cost_usd": 0.0,
        },
        status="running",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(running_event).model_dump(mode="json"))

    if decision == "allow":
        event_payload = event.payload_json if isinstance(event.payload_json, dict) else {}
        tool_input = event_payload.get("tool_input") if isinstance(event_payload, dict) else {}
        tool_input_data = tool_input if isinstance(tool_input, dict) else {}
        feature_ids = [
            str(feature_id).strip()
            for feature_id in tool_input_data.get("feature_ids", [])
            if str(feature_id).strip()
        ]
        visible_response = await _create_delivery_plan_for_approved_features(
            session_id,
            project_root,
            feature_ids,
        )
        stop_reason = "delivery_scope_approved_and_dispatched"
    else:
        visible_response = "Delivery scope was not approved. I kept the captured improvement unchanged."
        stop_reason = "delivery_scope_denied"

    assistant_event = await _append_chat_event(
        session_id,
        event_type="assistant_message",
        payload={"content": visible_response, "final": True},
        status="completed",
        mirror_message=("assistant", visible_response, 0, 0.0),
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(assistant_event).model_dump(mode="json"))
    await _append_voice_final_summary_if_needed(
        session_id,
        assistant_event_id=assistant_event.id,
        content=visible_response,
        hub=hub,
    )
    status_event = await _append_chat_event(
        session_id,
        event_type="run_status",
        payload={
            **runtime_payload,
            "running": False,
            "current_turn": 0,
            "max_turns": get_agent_definition("chat").max_turns,
            "tokens_used": 0,
            "cost_usd": 0.0,
            "stop_reason": stop_reason,
        },
        status="completed",
    )
    await hub.publish(session_id, agent_chat_transcript.serialize_event(status_event).model_dump(mode="json"))


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
        .where(ChatSession.repo_identity == agent_chat_sessions.repo_identity(project_root))
        .where(ChatSession.workspace_cwd == agent_chat_sessions.workspace_cwd(project_root))
        .order_by(ChatSession.updated_at.desc())
        .limit(1)
    )
    session = sessions_result.scalar_one_or_none()
    if session is None:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, project_root)
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
    sessions = await agent_chat_sessions.list_scoped_sessions(db, project_root)
    latest_resume_session = agent_chat_sessions.latest_resume_candidate(sessions)

    return ChatSessionListResponse(
        repo_identity=agent_chat_sessions.repo_identity(project_root),
        workspace_cwd=agent_chat_sessions.workspace_cwd(project_root),
        latest_resume_session_id=latest_resume_session.id if latest_resume_session else None,
        sessions=[
            ChatSessionItem(
                id=session.id,
                sdk_session_id=session.sdk_session_id,
                created_at=session.created_at.isoformat(),
                updated_at=session.updated_at.isoformat(),
                message_count=len(agent_chat_transcript.history_items(session)),
                preview=agent_chat_sessions.session_preview(session),
                workspace_cwd=session.workspace_cwd,
                is_resume_candidate=latest_resume_session is not None
                and session.id == latest_resume_session.id,
            )
            for session in sessions
        ],
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
        repo_identity=agent_chat_sessions.repo_identity(project_root),
        workspace_cwd=agent_chat_sessions.workspace_cwd(project_root),
    )


@router.get("/agent/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    request: Request,
    session_id: str | None = None,
    fresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Get chat history for a session."""

    project_root = _project_root(request)
    session = await agent_chat_sessions.load_session(
        db,
        session_id,
        project_root=project_root,
        reject_scope_mismatch=bool(session_id),
    )
    scoped_sessions = await agent_chat_sessions.list_scoped_sessions(db, project_root)

    if not fresh and session is None and session_id is None:
        session = agent_chat_sessions.latest_resume_candidate(scoped_sessions)

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
            repo_identity=agent_chat_sessions.repo_identity(project_root),
            workspace_cwd=agent_chat_sessions.workspace_cwd(project_root),
            items=[],
            messages=[],
            status=None,
        )

    if await _append_delivery_closeout_if_ready(session.id, project_root, db):
        await db.commit()
        await db.refresh(session, attribute_names=["events", "messages"])
        reloaded_session = await agent_chat_sessions.load_session(
            db,
            session.id,
            project_root=project_root,
            reject_scope_mismatch=True,
        )
        if reloaded_session is not None:
            session = reloaded_session
    if await reconcile_session_control_owners(
        session,
        db,
        feature_resolver=_feature_for_delivery_permission_question,
    ):
        await db.commit()
        await db.refresh(session, attribute_names=["events", "messages"])

    items = agent_chat_transcript.history_items(session)
    runtime_metadata = _chat_runtime_metadata(project_root)
    active_run = await _chat_hub(request).has_active_run(session.id)
    status = agent_chat_transcript.latest_status(session, active_run=active_run)
    thread_runtime_metadata = agent_chat_transcript.thread_runtime_metadata(runtime_metadata, status)
    return ChatHistoryResponse(
        session_id=session.id,
        sdk_session_id=session.sdk_session_id,
        model=thread_runtime_metadata["model"],
        effort=thread_runtime_metadata["effort"],
        runtime_sdk=thread_runtime_metadata["runtime_sdk"],
        provider=thread_runtime_metadata["provider"],
        repo_identity=agent_chat_sessions.repo_identity(project_root),
        workspace_cwd=agent_chat_sessions.workspace_cwd(project_root),
        items=items,
        messages=agent_chat_transcript.legacy_messages(items),
        status=status,
    )


@router.get("/agent/chat/stream")
async def chat_stream(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Stream live chat session timeline events as SSE."""

    project_root = _project_root(request)
    session = await agent_chat_sessions.load_session(
        db, session_id, project_root=project_root, reject_scope_mismatch=True
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    hub = _chat_hub(request)
    queue = await hub.register_session(session_id)
    runtime_metadata = _chat_runtime_metadata(project_root)
    active_run = await hub.has_active_run(session_id)
    status = agent_chat_transcript.latest_status(session, active_run=active_run)
    thread_runtime_metadata = agent_chat_transcript.thread_runtime_metadata(runtime_metadata, status)
    if await reconcile_session_control_owners(
        session,
        db,
        feature_resolver=_feature_for_delivery_permission_question,
    ):
        await db.commit()
        await db.refresh(session, attribute_names=["events", "messages"])
    items = agent_chat_transcript.history_items(session)
    snapshot = ChatHistoryResponse(
        session_id=session.id,
        sdk_session_id=session.sdk_session_id,
        model=thread_runtime_metadata["model"],
        effort=thread_runtime_metadata["effort"],
        runtime_sdk=thread_runtime_metadata["runtime_sdk"],
        provider=thread_runtime_metadata["provider"],
        repo_identity=agent_chat_sessions.repo_identity(project_root),
        workspace_cwd=agent_chat_sessions.workspace_cwd(project_root),
        items=items,
        messages=agent_chat_transcript.legacy_messages(items),
        status=status,
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
    agent_name = "chat"
    runtime_metadata = _runtime_metadata_for_agent(agent_name, project_root)

    session = await agent_chat_sessions.load_session(
        db,
        request.session_id,
        project_root=project_root,
        reject_scope_mismatch=bool(request.session_id),
    )
    if session is None:
        session = ChatSession()
        agent_chat_sessions.stamp_session_scope(session, project_root)
        db.add(session)
        await db.flush()
        await db.commit()
        session = await agent_chat_sessions.load_session(db, session.id, project_root=project_root)

    if session is None:
        raise HTTPException(status_code=500, detail="Failed to initialize chat session")

    hub = _chat_hub(req)
    if not await hub.reserve_run(session.id):
        raise HTTPException(
            status_code=409, detail="This chat session is waiting on the current run."
        )

    try:
        user_event = await _append_chat_event(
            session.id,
            event_type="user_message",
            payload={"content": request.message},
            status="completed",
            mirror_message=("user", request.message, 0, 0.0),
        )
        await hub.publish(session.id, agent_chat_transcript.serialize_event(user_event).model_dump(mode="json"))
    except Exception:
        await hub.release_run(session.id)
        raise

    task = asyncio.create_task(_run_chat_turn(req.app, session.id, request.message))
    attached = await hub.attach_reserved_run(session.id, task)
    if not attached:
        task.cancel()
        await hub.release_run(session.id)
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
            answer_value = ", ".join(
                option.strip() for option in request.selected_options if option.strip()
            )
        if not answer_value:
            raise HTTPException(
                status_code=400, detail="Select an option or provide a custom answer."
            )

        updated_event = await _update_request_event(
            db,
            event,
            payload_patch={"answered": True, "answer_value": answer_value},
            status="answered",
            answer_event_type="ask_user_question_answer",
            answer_payload={
                "question": event.payload_json.get("question", ""),
                "answer_value": answer_value,
            },
        )
        await hub.publish(
            request.session_id, agent_chat_transcript.serialize_event(updated_event).model_dump(mode="json")
        )
        if has_live_waiter:
            resolved = await hub.resolve_pending_answer(
                request.event_id,
                {"answer_value": answer_value},
            )
            if not resolved:
                raise HTTPException(
                    status_code=409, detail="This interaction is no longer pending."
                )
        else:
            source = str(event.payload_json.get("source") or "")
            if source == "assistant_delivery_permission_prompt":
                task = asyncio.create_task(
                    _continue_after_delivery_permission_question(
                        req.app,
                        request.session_id,
                        event,
                        answer_value=answer_value,
                    )
                )
                attached = await hub.attach_run(request.session_id, task)
                if not attached:
                    task.cancel()
                    raise HTTPException(
                        status_code=409, detail="This chat session is already running."
                    )
            else:
                question = str(event.payload_json.get("question") or "the pending question")
                await _continue_after_persisted_response(
                    req.app,
                    request.session_id,
                    f'Operator answered pending question "{question}": {answer_value}',
                )
        return ChatRespondResponse(
            ok=True, session_id=request.session_id, event_id=request.event_id
        )

    if event.event_type != "tool_approval_request":
        raise HTTPException(status_code=400, detail="Unsupported chat interaction type")

    decision = (request.decision or "").strip().lower()
    if decision not in {"allow", "deny"}:
        raise HTTPException(
            status_code=400, detail="Tool approvals require an allow or deny decision."
        )

    updated_event = await _update_request_event(
        db,
        event,
        payload_patch={"answered": True, "decision": decision, "reason": request.reason.strip()},
        status="answered",
        answer_event_type="tool_approval_answer",
        answer_payload={
            "tool_name": event.payload_json.get("tool_name", ""),
            "decision": decision,
            "reason": request.reason.strip(),
        },
    )
    await hub.publish(request.session_id, agent_chat_transcript.serialize_event(updated_event).model_dump(mode="json"))
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
        if tool_name == "Delivery scope approval":
            await _complete_persisted_delivery_scope_approval(
                req.app,
                request.session_id,
                event,
                decision=decision,
            )
        else:
            await _continue_after_persisted_response(
                req.app,
                request.session_id,
                f'Operator answered pending approval for "{tool_name}": {decision}. Reason: {request.reason.strip()}',
            )
    return ChatRespondResponse(ok=True, session_id=request.session_id, event_id=request.event_id)
