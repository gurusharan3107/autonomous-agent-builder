"""Project-context handoff helpers for the embedded Agent route."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.db.models import ChatEvent, Project
from autonomous_agent_builder.services.runtime_guidance import update_project_context_block

FRAMEWORK_CONSTRAINTS = (
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
STACK_CONSTRAINTS = (
    ("plain html and javascript", "Use plain HTML and JavaScript"),
    ("vanilla javascript", "Use vanilla JavaScript"),
    ("sqlite", "Use SQLite for persistence"),
    ("postgres", "Use PostgreSQL for persistence"),
    ("postgresql", "Use PostgreSQL for persistence"),
)

# Keyword -> (field, value) mapping. Order matters; first match wins per field.
PROJECT_CONTEXT_ANSWER_RULES: tuple[tuple[str, str, str], ...] = (
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
    ("browser localstorage", "persistence", "browser localStorage"),
    ("localstorage", "persistence", "browser localStorage"),
    ("sqlite", "persistence", "sqlite"),
    ("postgres", "persistence", "postgresql"),
    ("postgresql", "persistence", "postgresql"),
    ("in-memory", "persistence", "in-memory"),
    ("file (json", "persistence", "filesystem (json)"),
    ("python backend", "language", "python"),
    ("node backend", "language", "javascript"),
    ("flask", "framework", "flask"),
    ("fastapi", "framework", "fastapi"),
    ("django", "framework", "django"),
    ("express", "framework", "express"),
    ("next.js", "framework", "next.js"),
    ("react", "framework", "react"),
    ("vue", "framework", "vue"),
    ("svelte", "framework", "svelte"),
)

LANGUAGE_INFERENCE: tuple[tuple[str, str, str], ...] = (
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

PACKAGE_MANAGER_INFERENCE: tuple[tuple[str, str, str], ...] = (
    ("persistence", "browser localStorage", "none"),
    ("framework", "none (vanilla HTML/CSS/JS)", "none"),
    ("language", "python", "pip"),
    ("language", "javascript", "npm"),
    ("language", "typescript", "npm"),
)


async def collect_ask_user_question_answers(
    db: AsyncSession,
    session_id: str,
) -> dict[str, str]:
    """Read structured AskUserQuestion answers from the chat session log."""
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


def map_chat_answers_to_project_context(
    answers: dict[str, str],
) -> dict[str, str | None]:
    """Map structured chat answers to the five Project Context fields."""
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
    for keyword, field, value in PROJECT_CONTEXT_ANSWER_RULES:
        if fields.get(field) is not None:
            continue
        if keyword in haystack:
            fields[field] = value

    for source_field, source_value, language in LANGUAGE_INFERENCE:
        if fields.get("language") is not None:
            break
        if fields.get(source_field) == source_value:
            fields["language"] = language

    for source_field, source_value, pkg_mgr in PACKAGE_MANAGER_INFERENCE:
        if fields.get("package_manager") is not None:
            break
        if fields.get(source_field) == source_value:
            fields["package_manager"] = pkg_mgr

    return fields


def apply_chat_answers_to_project_context(
    project_root: Path,
    answers: dict[str, str],
) -> dict[str, str]:
    context_fields = map_chat_answers_to_project_context(answers)
    non_none_fields = {key: value for key, value in context_fields.items() if value is not None}
    if non_none_fields:
        update_project_context_block(project_root, **non_none_fields)
    return non_none_fields


def extract_technical_constraints(user_message: str) -> list[str]:
    lower_message = user_message.lower()
    constraints: list[str] = []
    seen: set[str] = set()
    for needle, constraint in (*FRAMEWORK_CONSTRAINTS, *STACK_CONSTRAINTS):
        if needle in lower_message and constraint not in seen:
            constraints.append(constraint)
            seen.add(constraint)
    return constraints


def inject_feature_list_constraints(
    feature_payload: dict[str, Any],
    constraints: list[str],
) -> dict[str, Any]:
    if not constraints:
        return feature_payload
    payload = dict(feature_payload)
    metadata = dict(
        payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
    )
    existing = metadata.get("technical_constraints", [])
    normalized_existing = (
        [str(item).strip() for item in existing if str(item).strip()]
        if isinstance(existing, list)
        else []
    )
    metadata["technical_constraints"] = list(dict.fromkeys([*normalized_existing, *constraints]))
    payload["metadata"] = metadata
    return payload


def append_target_claude_constraints(project_root: Path, constraints: list[str]) -> None:
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


async def apply_forward_project_constraints(
    db: AsyncSession,
    project_root: Path,
    constraints: list[str],
) -> None:
    if not constraints:
        return
    append_target_claude_constraints(project_root, constraints)
    result = await db.execute(select(Project).order_by(Project.created_at.desc()).limit(1))
    project = result.scalar_one_or_none()
    if project is None:
        return
    constraint_text = "User technical constraints: " + "; ".join(constraints) + "."
    if constraint_text not in project.description:
        project.description = f"{project.description}\n\n{constraint_text}".strip()
