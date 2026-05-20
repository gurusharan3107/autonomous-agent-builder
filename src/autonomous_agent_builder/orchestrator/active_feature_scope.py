"""Active feature scope reminder rendering for orchestrator prompts."""

from __future__ import annotations

import json
from typing import Any

from autonomous_agent_builder.db.models import Task


def build_active_feature_scope_reminder(
    task: Task,
    sprint_payload: dict[str, Any],
) -> str:
    """Render a ``<system-reminder>`` block describing the active feature.

    Per-task variants belong in the user message as a ``<system-reminder>``
    block so the cached system prefix stays warm across task dispatches.
    """
    feature = getattr(task, "feature", None)
    if feature is None:
        return ""
    title = str(getattr(feature, "title", "") or "").strip()
    description = str(getattr(feature, "description", "") or "").strip()
    criteria_raw = getattr(feature, "acceptance_criteria", None) or []
    criteria = [str(item).strip() for item in criteria_raw if str(item).strip()]

    own_hint = str(sprint_payload.get("file_ownership_hint", "") or "").strip()
    own_key = str(sprint_payload.get("task_key", "") or "").strip()
    sibling_hints = sibling_task_ownership_hints(task, own_key)

    if not (title or description or criteria or own_hint):
        return ""
    lines = ["<system-reminder>"]
    lines.append("Active feature scope (sprint task)")
    if title:
        lines.append(f"Feature: {title}")
    if description:
        lines.append(f"Description: {description}")
    if criteria:
        lines.append("Acceptance criteria (the verifier WILL check these):")
        lines.extend(f"- {item}" for item in criteria)
    if own_hint or sibling_hints:
        lines.append("")
        lines.append("Task ownership boundary (your slice of this feature)")
        if own_hint:
            lines.append(f"You OWN: {own_hint}")
        if sibling_hints:
            lines.append("Out of scope (other sprint tasks own these — do NOT implement):")
            lines.extend(f"- {hint}" for hint in sibling_hints)
        lines.append(
            "Stay strictly inside your ownership. Producing work that lands "
            "in another task's ownership causes that task to ghost-run later "
            "with nothing to do — leaving its acceptance unverified."
        )
    lines.append("")
    lines.append(
        "Do not introduce stack choices that contradict CLAUDE.md "
        "## Project Context. If the acceptance criteria conflict with what "
        "you would otherwise build, surface a blocker instead of silently "
        "diverging."
    )
    lines.append("</system-reminder>\n\n")
    return "\n".join(lines)


def sibling_task_ownership_hints(task: Task, own_key: str) -> list[str]:
    """Extract sibling sprint tasks' file ownership hints from design context."""
    depends_on = task.depends_on if isinstance(task.depends_on, dict) else {}
    phase_context = depends_on.get("phase_context")
    if not isinstance(phase_context, dict):
        return []
    design_raw = phase_context.get("design_context")
    if not isinstance(design_raw, str):
        return []
    try:
        design = json.loads(design_raw)
    except (TypeError, ValueError):
        return []
    hints = design.get("task_file_ownership_hints") if isinstance(design, dict) else None
    if not isinstance(hints, list):
        return []
    out: list[str] = []
    for entry in hints:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("task_key", "") or "").strip()
        if own_key and key == own_key:
            continue
        ownership = str(entry.get("ownership", "") or "").strip()
        entry_title = str(entry.get("title", "") or "").strip()
        if not ownership:
            continue
        out.append(f"{entry_title} → {ownership}" if entry_title else ownership)
    return out
