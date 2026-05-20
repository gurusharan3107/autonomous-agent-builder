"""Build verification policy helpers for orchestrator lifecycle phases."""

from __future__ import annotations

import json
import re
from typing import Any

from autonomous_agent_builder.services.sprint_execution import SPRINT_EXECUTION_KEY

_SPRINT_FEATURE_VERIFY_TASK_KEYS = {"browser-verification", "tests-browser-proof"}


def task_sprint_execution_payload(task: Any) -> dict:
    depends_on = task.depends_on if isinstance(task.depends_on, dict) else {}
    payload = depends_on.get(SPRINT_EXECUTION_KEY)
    return payload if isinstance(payload, dict) else {}


def use_deterministic_evidence_collector(task: Any) -> bool:
    sprint_payload = task_sprint_execution_payload(task)
    if not sprint_payload:
        return False
    workspace = getattr(task, "workspace", None)
    return bool(workspace and getattr(workspace, "path", ""))


def use_deterministic_build_verifier(task: Any) -> bool:
    sprint_payload = task_sprint_execution_payload(task)
    if not sprint_payload:
        return False
    workspace = getattr(task, "workspace", None)
    return bool(workspace and getattr(workspace, "path", ""))


def is_sprint_feature_verification_task(task: Any) -> bool:
    sprint_payload = task_sprint_execution_payload(task)
    task_key = str(sprint_payload.get("task_key") or "").strip()
    return task_key in _SPRINT_FEATURE_VERIFY_TASK_KEYS


def sprint_branch_name(sprint: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (sprint.label or "sprint").lower()).strip("-")
    slug = slug or "sprint"
    return f"sprint/{sprint.id[:8]}-{slug}"


def build_verifier_failure(output_text: str) -> str | None:
    lines = [line.strip() for line in str(output_text or "").splitlines() if line.strip()]
    failing_lines = [
        line
        for line in lines
        if re.search(r"(?:^|`|\s)FAIL(?:\s|:|$)", line.replace("*", " "))
        and not is_advisory_verifier_failure(line)
    ]
    if not failing_lines:
        return None
    detail = "; ".join(failing_lines[:3])
    return f"build_verification_failed: {detail}"


def feature_verifier_failure(output_text: str) -> str | None:
    payload = _json_object_from_text(output_text)
    status = str(payload.get("status") or "").strip().lower()
    if status in {"", "pass", "passed"}:
        return None
    recommended = str(payload.get("recommended_next_action") or "").strip()
    detail = recommended or str(output_text or "").strip()[:500] or "feature verifier failed"
    return f"feature_acceptance_failed: verifier_status={status}: {detail}"


def is_advisory_verifier_failure(line: str) -> bool:
    lower = line.lower()
    return "git status" in lower and "fail" in lower and "not a git repository" in lower


def _json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _json_object_from_text(text: str) -> dict[str, Any]:
    value = _json_object(text)
    if value:
        return value
    raw = str(text or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    return _json_object(raw[start : end + 1])
