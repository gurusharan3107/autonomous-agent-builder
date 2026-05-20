"""Structured operator-decision handoff helpers for orchestrator phases."""

from __future__ import annotations

import json
import re

from autonomous_agent_builder.db.models import Task, TaskStatus, set_task_status

OPERATOR_DECISION_MARKER = "OPERATOR_DECISION_JSON:"


def apply_operator_decision_handoff(task: Task, output_text: str) -> bool:
    payload = extract_operator_decision(output_text)
    if payload is None:
        return False
    depends_on = dict(task.depends_on or {})
    depends_on["operator_decision"] = payload
    task.depends_on = depends_on
    set_task_status(task, TaskStatus.BLOCKED)
    phase = str(payload.get("phase", "") or "phase").strip() or "phase"
    question = str(payload.get("question", "") or "").strip()
    summary = str(payload.get("summary", "") or "").strip()
    detail = question or summary or "operator decision required"
    task.blocked_reason = f"{phase} blocked: {detail}"
    return True


def clear_operator_decision_handoff(task: Task) -> None:
    if not isinstance(task.depends_on, dict) or "operator_decision" not in task.depends_on:
        return
    depends_on = dict(task.depends_on)
    depends_on.pop("operator_decision", None)
    task.depends_on = depends_on


def extract_operator_decision(output_text: str) -> dict[str, object] | None:
    text = str(output_text or "")
    marker_index = text.find(OPERATOR_DECISION_MARKER)
    if marker_index < 0:
        return None
    raw = text[marker_index + len(OPERATOR_DECISION_MARKER) :].strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.S)
        if match is None:
            return None
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        return None
    options = payload.get("options")
    return {
        "phase": str(payload.get("phase", "") or "").strip(),
        "summary": str(payload.get("summary", "") or "").strip(),
        "question": str(payload.get("question", "") or "").strip(),
        "options": [str(item).strip() for item in options] if isinstance(options, list) else [],
        "recommended_option": str(payload.get("recommended_option", "") or "").strip(),
    }
