from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_HISTORICAL_SCOPE_TOKENS = (
    "older sprint",
    "older sprints",
    "previous sprint",
    "previous sprints",
    "earlier sprint",
    "earlier sprints",
    "past sprint",
    "past sprints",
    "all sprints",
    "across sprints",
    "entire board",
    "whole board",
    "full board",
)

_SPRINT_REFERENCE_RE = re.compile(r"\bsprint\s+\d+\b")


@dataclass(frozen=True)
class BoardStatusScope:
    scope: str
    current_sprint_label: str
    generated_task_ids: tuple[str, ...]

    @property
    def is_current_sprint(self) -> bool:
        return self.scope == "current_sprint" and bool(self.generated_task_ids)


def board_status_scope_from_message(message: str, current_sprint: Any) -> BoardStatusScope:
    label = str(getattr(current_sprint, "label", "") or "").strip()
    generated_task_ids = tuple(
        str(task_id).strip()
        for task_id in (getattr(current_sprint, "generated_task_ids", None) or [])
        if str(task_id).strip()
    )
    if current_sprint is None or not generated_task_ids:
        return BoardStatusScope(
            scope="all_sprints",
            current_sprint_label=label,
            generated_task_ids=generated_task_ids,
        )

    normalized_message = _normalize_text(message)
    normalized_label = _normalize_text(label)
    if _requests_historical_scope(normalized_message, normalized_label):
        return BoardStatusScope(
            scope="all_sprints",
            current_sprint_label=label,
            generated_task_ids=generated_task_ids,
        )

    return BoardStatusScope(
        scope="current_sprint",
        current_sprint_label=label,
        generated_task_ids=generated_task_ids,
    )


def board_response_task_ids(board_response: Any) -> set[str]:
    task_ids: set[str] = set()
    for lane in ("pending", "active", "review", "done", "blocked"):
        for item in getattr(board_response, lane, None) or []:
            task_id = str(getattr(item, "id", "") or "").strip()
            if task_id:
                task_ids.add(task_id)
    return task_ids


def board_status_projection_lines(
    *,
    scope: str,
    current_sprint_label: str,
    current_sprint_phase: str,
    queued_count: int,
    active_count: int,
    review_count: int,
    done_count: int,
    blocked_count: int,
    backlog_feature_count: int,
    backlog_done_count: int,
    backlog_open_count: int,
) -> list[str]:
    if scope == "current_sprint" and current_sprint_label:
        lines = [
            f"Current sprint Board status from Builder source of truth (`{current_sprint_label}`):"
        ]
    else:
        lines = ["Board status from Builder source of truth across sprints:"]

    lines.append(
        f"Queued {queued_count}, in progress {active_count}, needs review {review_count}, "
        f"shipped {done_count}, blocked {blocked_count}."
    )
    if backlog_feature_count:
        lines.append(
            f"Backlog features {backlog_done_count}/{backlog_feature_count} done, "
            f"{backlog_open_count} open."
        )
    if scope == "current_sprint" and current_sprint_label and current_sprint_phase == "shipped":
        lines.append(f"Current sprint `{current_sprint_label}` is shipped.")
    return lines


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _requests_historical_scope(normalized_message: str, normalized_label: str) -> bool:
    if not normalized_message:
        return False
    if any(token in normalized_message for token in _HISTORICAL_SCOPE_TOKENS):
        return True
    sprint_reference = _SPRINT_REFERENCE_RE.search(normalized_message)
    return bool(sprint_reference and sprint_reference.group(0) not in normalized_label)
