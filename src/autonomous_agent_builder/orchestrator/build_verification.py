"""Build verification policy helpers for orchestrator lifecycle phases."""

from __future__ import annotations

import json
import re
from typing import Any

from autonomous_agent_builder.services.sprint_execution import SPRINT_EXECUTION_KEY

_SPRINT_FEATURE_VERIFY_TASK_KEYS = {"browser-verification", "tests-browser-proof"}

# Keywords that indicate a task touches user-facing UI/dashboard/frontend surfaces.
# Used by is_ui_task to decide whether real-browser proof is required.
_UI_KEYWORDS = frozenset(
    [
        "ui",
        "frontend",
        "dashboard",
        "browser",
        "web",
        "html",
        "css",
        "react",
        "vue",
        "angular",
        "svelte",
        "page",
        "component",
        "button",
        "form",
        "modal",
        "dialog",
        "panel",
        "screen",
        "view",
        "layout",
        "style",
        "theme",
        "design",
        "visual",
        "display",
        "render",
        "canvas",
        "chart",
        "graph",
        "widget",
        "tab",
        "menu",
        "nav",
        "sidebar",
    ]
)


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


def is_ui_task(task: Any, feature: Any = None) -> bool:
    """Return True when the task/feature involves user-facing UI/dashboard/frontend changes.

    Checks the feature title, description, and acceptance criteria for known UI
    keywords. Used by the real-browser gate (IMP-019) to decide whether
    ``mcp__browser__*`` verification is required and, when the bridge is
    unavailable, whether to emit a ``browser_evidence_tier: unavailable``
    warning instead of silently accepting jsdom-only proof.
    """
    text_parts: list[str] = []
    if feature is not None:
        text_parts.append(str(getattr(feature, "title", "") or ""))
        text_parts.append(str(getattr(feature, "description", "") or ""))
        criteria = getattr(feature, "acceptance_criteria", None) or []
        if isinstance(criteria, list):
            text_parts.extend(str(c) for c in criteria)
    # Also check task title/description when available.
    text_parts.append(str(getattr(task, "title", "") or ""))
    text_parts.append(str(getattr(task, "description", "") or ""))
    combined = " ".join(text_parts).lower()
    return any(kw in combined for kw in _UI_KEYWORDS)


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


def browser_evidence_tier(
    output_text: str, *, bridge_available: bool, is_ui: bool = False
) -> dict[str, Any]:
    """Classify the real-browser-proof tier of a feature-verifier result (IMP-019).

    Non-blocking advisory — real-browser proof (`mcp__browser__*` screenshots /
    URLs in the verifier's ``browser_evidence``) is the strongest acceptance
    tier; jsdom/command proof is accepted when the browser bridge is
    unavailable. Returns ``{"tier": ..., "advisory": str | None,
    "browser_evidence_tier": str}``:
    - ``real_browser`` — verifier produced live browser evidence.
    - ``jsdom_fallback`` — no browser evidence and the bridge was unavailable
      for a non-UI task (acceptable weaker tier).
    - ``unavailable`` — task IS user-facing (UI/dashboard/frontend) but the
      browser bridge was unavailable; a warning is emitted so the gap is
      visible without blocking CI.
    - ``no_browser_proof`` — the bridge WAS available but the verifier produced
      no browser evidence (the gap IMP-019 targets; advisory set).
    - ``na`` — task is not user-facing; real-browser proof is not required.

    The ``browser_evidence_tier`` key is a copy of ``tier`` included for
    queryable structured evidence (readable by ``builder logs analyze`` without
    re-parsing raw transcripts).

    This is intentionally not a hard gate: blocking ships on browser proof must
    not break headless/CI environments where the bridge cannot launch.
    """
    payload = _json_object_from_text(output_text)
    evidence = payload.get("browser_evidence")
    has_browser_evidence = isinstance(evidence, list) and any(
        str(item).strip() for item in evidence
    )
    if has_browser_evidence:
        result: dict[str, Any] = {"tier": "real_browser", "advisory": None}
    elif not bridge_available and is_ui:
        result = {
            "tier": "unavailable",
            "advisory": (
                "Task is user-facing (UI/dashboard/frontend) but the browser bridge was "
                "unavailable; real-browser proof could not be collected. Acceptance is "
                "jsdom/command-tier only — re-run with the Hermes Chrome bridge active "
                "to obtain real-browser evidence."
            ),
        }
    elif not bridge_available:
        result = {
            "tier": "jsdom_fallback",
            "advisory": (
                "Feature accepted without real-browser proof — the browser bridge was "
                "unavailable; this is jsdom/command-tier evidence."
            ),
        }
    else:
        result = {
            "tier": "no_browser_proof",
            "advisory": (
                "Browser bridge was available but the verifier produced no real-browser "
                "evidence; acceptance is jsdom/command-tier only. Prefer mcp__browser__* "
                "proof for user-facing web features."
            ),
        }
    # Duplicate tier into the queryable field so callers can read it without
    # re-parsing raw output text (IMP-019 evidence-tier requirement).
    result["browser_evidence_tier"] = result["tier"]
    return result


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
