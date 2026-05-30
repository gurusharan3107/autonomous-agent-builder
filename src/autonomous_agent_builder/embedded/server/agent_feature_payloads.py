"""Feature payload parsing and session predicates for the embedded Agent route."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from autonomous_agent_builder.db.models import ChatSession
from autonomous_agent_builder.embedded.server import agent_chat_transcript
from autonomous_agent_builder.embedded.server.agent_message_intent import (
    message_requests_feature_delivery,
    message_requests_feature_spec,
    operator_visible_feature_scope_text,
)

FEATURE_LIST_MARKER = "FEATURE_LIST_JSON:"
FEATURE_SPEC_MARKER = "FEATURE_SPEC_JSON:"
_CAPTURED_FEATURE_TITLE_PATTERNS = (
    # Accept any backlog-item type noun (feature/improvement/optimization/
    # incident) — save_note is now type-aware (IMP-015).
    re.compile(r"I captured that [\w-]+ as `([^`]+)`", re.IGNORECASE),
    re.compile(r"Feature saved to backlog as `([^`]+)`", re.IGNORECASE),
    re.compile(r"I saved that as `([^`]+)`(?:[^.]*in the backlog)?", re.IGNORECASE),
)


def content_announces_captured_feature(content: str) -> bool:
    """True if assistant text announces a captured backlog item, for any type
    noun (feature/improvement/optimization/incident). Type-agnostic per IMP-015."""
    return any(pattern.search(content) for pattern in _CAPTURED_FEATURE_TITLE_PATTERNS)


def extract_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("No JSON object found in agent output.")


def normalize_feature_list_payload(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    raw_features = payload.get("features", [])
    if not isinstance(raw_features, list) or not raw_features:
        raise ValueError("Feature list payload must include a non-empty features array.")

    normalized_features: list[dict[str, Any]] = []
    done = 0
    for index, feature in enumerate(raw_features, start=1):
        if not isinstance(feature, dict):
            continue
        title = str(feature.get("title", "")).strip()
        if not title:
            continue
        status = str(feature.get("status", "pending")).strip().lower() or "pending"
        if status == "done":
            done += 1
        normalized_features.append(
            {
                "id": str(feature.get("id") or f"feature-{index:02d}"),
                "title": title,
                "description": str(feature.get("description", "")).strip(),
                "status": status,
                "priority": str(feature.get("priority", max(1, 101 - index))),
                "acceptance_criteria": [
                    str(item).strip()
                    for item in feature.get("acceptance_criteria", [])
                    if str(item).strip()
                ],
                "dependencies": [
                    str(item).strip()
                    for item in feature.get("dependencies", [])
                    if str(item).strip()
                ],
            }
        )

    if not normalized_features:
        raise ValueError("Feature list payload did not contain any usable features.")

    pending = len(normalized_features) - done
    metadata = payload.get("metadata", {})
    project_name = (
        str(metadata.get("project", "")).strip() if isinstance(metadata, dict) else ""
    ) or project_root.name
    return {
        "metadata": {
            "project": project_name,
            "done": done,
            "pending": pending,
        },
        "features": normalized_features,
    }


def extract_feature_list_payload(
    project_root: Path, text: str
) -> tuple[str, dict[str, Any] | None]:
    if FEATURE_LIST_MARKER not in text:
        return text.strip(), None

    before, after = text.split(FEATURE_LIST_MARKER, 1)
    payload = normalize_feature_list_payload(project_root, extract_json_object(after))
    return before.strip(), payload


def feature_record_description(payload: dict[str, Any]) -> str:
    base = str(payload.get("description", "")).strip()
    acceptance_criteria = payload.get("acceptance_criteria", [])
    dependencies = payload.get("dependencies", [])
    sections: list[str] = []
    if base:
        sections.append(base)
    if acceptance_criteria:
        sections.append(
            "Acceptance criteria:\n"
            + "\n".join(f"- {item}" for item in acceptance_criteria if str(item).strip())
        )
    if dependencies:
        sections.append(
            "Dependencies:\n" + "\n".join(f"- {item}" for item in dependencies if str(item).strip())
        )
    return "\n\n".join(section for section in sections if section).strip()


def normalize_feature_spec_payload(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    if not title:
        raise ValueError("Feature spec payload must include a title.")
    acceptance_criteria = [
        str(item).strip() for item in payload.get("acceptance_criteria", []) if str(item).strip()
    ]
    dependencies = [
        str(item).strip() for item in payload.get("dependencies", []) if str(item).strip()
    ]
    raw_priority = payload.get("priority", 50)
    try:
        priority = int(raw_priority)
    except (TypeError, ValueError):
        priority = 50
    return {
        "title": title,
        "description": feature_record_description(
            {
                "description": str(payload.get("description", "")).strip(),
                "acceptance_criteria": acceptance_criteria,
                "dependencies": dependencies,
            }
        ),
        "priority": priority,
        "acceptance_criteria": acceptance_criteria,
        "dependencies": dependencies,
    }


def extract_feature_spec_payload(text: str) -> tuple[str, dict[str, Any] | None]:
    if FEATURE_SPEC_MARKER not in text:
        return text.strip(), None
    before, after = text.split(FEATURE_SPEC_MARKER, 1)
    payload = normalize_feature_spec_payload(extract_json_object(after))
    return operator_visible_feature_scope_text(before), payload


def session_has_pending_feature_spec(session: ChatSession) -> bool:
    items = agent_chat_transcript.history_items(session)
    if not items:
        return False
    requested = any(
        item.type == "user_message"
        and message_requests_feature_spec(str(item.payload.get("content", "")))
        for item in items
    )
    if not requested:
        return False
    for item in items:
        if item.type != "assistant_message":
            continue
        content = str(item.payload.get("content", ""))
        if FEATURE_SPEC_MARKER in content or content_announces_captured_feature(content):
            return False
    return True


def session_has_saved_feature_for_delivery(session: ChatSession) -> bool:
    for item in agent_chat_transcript.history_items(session):
        if item.type != "assistant_message":
            continue
        content = str(item.payload.get("content", ""))
        if content_announces_captured_feature(content):
            return True
    return False


def session_requests_feature_delivery(session: ChatSession) -> bool:
    items = agent_chat_transcript.history_items(session)
    if not items:
        return False
    return any(
        item.type == "user_message"
        and message_requests_feature_delivery(str(item.payload.get("content", "")))
        for item in items
    )


def captured_feature_title_from_text(content: str) -> str:
    for pattern in _CAPTURED_FEATURE_TITLE_PATTERNS:
        match = pattern.search(content)
        if match:
            return match.group(1).strip()
    return ""
