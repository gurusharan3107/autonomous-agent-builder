"""Prompt assembly functions for agent chat turns."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.models import ChatSession
from autonomous_agent_builder.embedded.server import agent_chat_transcript
from autonomous_agent_builder.embedded.server.agent_documentation_context import (
    documentation_context_pack as _documentation_context_pack,
)
from autonomous_agent_builder.embedded.server.agent_feature_payloads import (
    FEATURE_LIST_MARKER as _FEATURE_LIST_MARKER,
)
from autonomous_agent_builder.embedded.server.documentation_routing import (
    DOCUMENTATION_AGENT_AUTO_APPROVE_TOOLS as _DOCUMENTATION_AGENT_AUTO_APPROVE_TOOLS,
)
from autonomous_agent_builder.embedded.server.documentation_routing import (
    ActiveSpecialistRoute,
    SpecialistRoutePolicy,
    select_specialist_route,
)
from autonomous_agent_builder.embedded.server.documentation_routing import (
    message_has_documentation_intent as _message_has_documentation_intent,
)
from autonomous_agent_builder.embedded.server.documentation_routing import (
    message_matches_documentation_continuation as _message_matches_documentation_continuation,
)

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
    _normalized_sdk = str(runtime_sdk or "")
    _question_tool = (
        "request_user_input"
        if _normalized_sdk.startswith("codex") or _normalized_sdk == "openai_agents"
        else "AskUserQuestion"
    )
    continuation_guidance = ""
    if model_backed_delivery_context:
        continuation_guidance = (
            "\n\nModel-backed delivery context is active for this turn.\n"
            "- The user's message must be interpreted by you, the selected runtime model; do not "
            "treat it as a fixed command or deterministic shortcut.\n"
            "- Use the available Builder tools to inspect the ready Board work, decide the next "
            "action, and choose any needed tool chain. Useful surfaces include Board/task state, "
            "task detail/status, and dispatch, but you choose which tools to call and in what "
            "order.\n"
            "- First inspect Builder-owned Board/task state with `mcp__builder__board`, "
            "`mcp__builder__task_show`, or `mcp__builder__task_status` to determine what is "
            "pending, blocked, or ready to dispatch.\n"
            "- If exactly one blocked, failed, or capability-limited Board task is the next "
            "blocking item, call `mcp__builder__task_recover` for that task and then "
            "`mcp__builder__task_dispatch` to continue it.\n"
            "- If Builder Board evidence shows a pending or otherwise dispatchable task for the "
            "approved sprint, dispatch that Board task with `mcp__builder__task_dispatch`.\n"
            "- Dispatch ONE task at a time. Never call `mcp__builder__task_dispatch` for "
            "multiple tasks in the same turn — wait for each response before dispatching the next.\n"
            "- Do not use generic code-editing or shell tools to implement approved sprint work "
            "directly from this chat turn; that bypasses Board synchronization and pollutes the "
            "user-facing lifecycle.\n"
            "- Do not ask the user which listed feature to build when the board already gives "
            "a deterministic next task by status and priority.\n"
            "- The product goal is to continue the approved delivery without asking the operator "
            "for task IDs, backlog terms, sprint terms, or lifecycle terminology.\n"
            "- If the next product action is still ambiguous after bounded Builder evidence, use "
            f"`{_question_tool}` with plain product wording.\n"
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
            "- Do not skip product tailoring by jumping straight to delivery approval. "
            "Approval belongs after the product is tailored enough to describe the first "
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
        "know backlog, sprint, product backlog, or task terminology. If the user asks to implement, "
        "add, or build a feature — first call `mcp__builder__backlog_item_list` to check whether "
        "a matching sprint_planned or backlog item already exists. If one exists with acceptance_criteria, "
        "use those criteria as the spec and dispatch the matching task via `mcp__builder__task_dispatch` "
        "(recovering it first with `mcp__builder__task_recover` if its status is failed or blocked); "
        "do not ask clarifying questions about scope that is already captured there. "
        "If no matching item exists, decide whether the scope is clear enough. If it is unclear, ask the next "
        "plain product question through the runtime-native structured question mechanism. If it is clear, "
        "summarize the agreed improvement and emit `FEATURE_SPEC_JSON:` followed immediately by one raw "
        "JSON object with title, description, priority, acceptance_criteria, and dependencies. Do not "
        "tell the user to create backlog items, plan a sprint, or create tasks; Builder handles those "
        "internal lifecycle steps after the captured improvement is approved. "
        "Do not say you will check memory, backlog, board, or project state unless you actually use "
        "the corresponding tool in that turn. Ask for clarification only after bounded retrieval cannot "
        "resolve the missing context. "
        "LOOKUP RULE — MANDATORY: When the user message contains words like 'implement', 'build', "
        "'add', or 'create' followed by a feature name, you MUST call `mcp__builder__backlog_item_list` "
        "as your FIRST action — before writing any response or asking any question. This rule has no "
        "exceptions. Only after the lookup result is in hand may you decide: dispatch if a matching "
        "item exists, or ask via the structured question tool if no match is found. Responding with "
        "plain-text clarifying questions without first calling `mcp__builder__backlog_item_list` is a "
        "hard rule violation.\n"
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
    # Compact separators: injected into the chat turn (non-cached) on every
    # KB-routed turn, so indentation whitespace is paid per turn. ~33% fewer
    # tokens, identical data. sort_keys kept for deterministic ordering.
    context_json = json.dumps(documentation_context, separators=(",", ":"), sort_keys=True)
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


def _message_needs_recent_context(user_message: str) -> bool:
    normalized = " ".join(user_message.lower().split())
    return any(term in normalized for term in _RECENT_CONTEXT_TERMS)


def _recent_chat_context_for_prompt(
    session: ChatSession,
    user_message: str,
    *,
    limit: int = _RECENT_CONTEXT_EVENT_LIMIT,
    force: bool = False,
) -> str:
    """Build a compact deterministic transcript pack for referential chat turns."""
    if not force and not _message_needs_recent_context(user_message):
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
    recent_context: str = "",
) -> str:
    question_guidance = _question_tool_guidance(runtime_sdk)
    prior_context_section = ""
    if recent_context.strip():
        prior_context_section = (
            "\n\nPrior session context for this intake turn. "
            "Use this to treat short follow-up answers as answers to the questions you last asked:\n"
            f"{recent_context.strip()}"
        )
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

User: {user_message}{prior_context_section}"""


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
