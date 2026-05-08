"""Provider-limit detection and recovery metadata.

This module keeps quota/rate-limit handling deterministic and product-owned.
Claude Code/Agent SDK may surface provider limits as final text, process
errors, or StopFailure hook events; builder normalizes those signals into one
task payload that the Agent page and orchestrator can act on.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from autonomous_agent_builder.db.models import Task, TaskPhase, TaskStatus, set_task_status

_RESET_TIME_RE = re.compile(
    r"\breset(?:s|ting)?(?:\s+at|\s+around)?\s+"
    r"(?P<time>\d{1,2}(?::\d{2})?\s*(?:am|pm))\b",
    re.IGNORECASE,
)
_RESET_TIMEZONE_RE = re.compile(r"\((?P<zone>[A-Za-z_]+/[A-Za-z_]+)\)")
_RESET_IN_RE = re.compile(
    r"\breset(?:s|ting)?\s+in\s+"
    r"(?P<amount>\d+)\s*(?P<unit>minute|minutes|hour|hours)\b",
    re.IGNORECASE,
)
_TRY_AGAIN_AT_RE = re.compile(
    r"\btry\s+again\s+at\s+"
    r"(?P<month>[A-Za-z]+)\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?,\s+"
    r"(?P<year>\d{4})\s+"
    r"(?P<time>\d{1,2}:\d{2}\s*(?:am|pm))\b",
    re.IGNORECASE,
)

_RECOVERY_TARGETS = {
    TaskPhase.PLANNING.value: TaskStatus.PLANNING,
    TaskPhase.DESIGN.value: TaskStatus.DESIGN,
    TaskPhase.IMPLEMENTATION.value: TaskStatus.IMPLEMENTATION,
    TaskPhase.VERIFICATION.value: TaskStatus.QUALITY_GATES,
    TaskPhase.INTEGRATION.value: TaskStatus.PR_CREATION,
}


def is_provider_limit_text(text: str | None) -> bool:
    """Return true when text looks like a provider quota/rate-limit stop."""
    lower = str(text or "").lower()
    if not lower.strip():
        return False
    return (
        ("hit your limit" in lower and "reset" in lower)
        or ("out of extra usage" in lower and "reset" in lower)
        or (
            "usage limit" in lower
            and ("try again" in lower or "upgrade to plus" in lower or "get more access" in lower)
        )
        or "rate limit reached" in lower
        or "too many requests" in lower
        or "provider_limit" in lower
    )


def provider_limit_target_status(task: Task) -> TaskStatus:
    """Return the phase-preserving status to restore after a provider limit."""
    task_phase = task.phase.value if hasattr(task.phase, "value") else str(task.phase)
    return _RECOVERY_TARGETS.get(task_phase, TaskStatus.PLANNING)


def build_provider_limit_payload(
    task: Task,
    *,
    reason: str,
    output_text: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create compact metadata for Agent-page rendering and auto-resume."""
    detected_at = _as_utc(now)
    reset_at, reset_hint = parse_reset_hint(output_text or reason, now=detected_at)
    target_status = provider_limit_target_status(task)
    return {
        "code": "provider_limit",
        "reason": reason,
        "detected_at": detected_at.isoformat(),
        "reset_at": reset_at.isoformat() if reset_at else None,
        "reset_hint": reset_hint,
        "resume_status": target_status.value,
        "resume_task_id": task.id,
        "source": "claude_agent_sdk",
    }


def mark_provider_limit(
    task: Task,
    *,
    reason: str,
    output_text: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Move a task into provider-limit blocked state with structured metadata."""
    detected_at = _as_utc(now)
    payload = build_provider_limit_payload(
        task,
        reason=reason,
        output_text=output_text,
        now=detected_at,
    )
    depends_on = dict(task.depends_on or {})
    depends_on["provider_limit"] = payload
    task.depends_on = depends_on
    set_task_status(task, TaskStatus.CAPABILITY_LIMIT)
    task.capability_limit_at = detected_at
    task.capability_limit_reason = reason
    task.dead_letter_queued_at = detected_at
    task.blocked_at = detected_at
    task.blocked_reason = provider_limit_blocked_reason(payload)
    return payload


def provider_limit_blocked_reason(payload: dict[str, Any]) -> str:
    reset_at = str(payload.get("reset_at") or "").strip()
    reset_hint = str(payload.get("reset_hint") or "").strip()
    resume_status = str(payload.get("resume_status") or "").strip()
    if reset_at:
        return (
            "provider limit blocked: reset_at="
            f"{reset_at}; builder will resume at {resume_status or 'the preserved phase'}."
        )
    if reset_hint:
        return (
            "provider limit blocked: "
            f"{reset_hint}; builder will retry when the reset time is known."
        )
    return "provider limit blocked: builder will retry after the provider limit resets."


def provider_limit_payload(task: Task) -> dict[str, Any]:
    depends_on = task.depends_on if isinstance(task.depends_on, dict) else {}
    payload = depends_on.get("provider_limit")
    return payload if isinstance(payload, dict) else {}


def provider_limit_is_ready(task: Task, *, now: datetime | None = None) -> bool:
    """Return true when provider-limit metadata says the task can resume."""
    payload = provider_limit_payload(task)
    reset_at = _parse_iso_datetime(payload.get("reset_at"))
    if reset_at is None:
        return False
    return reset_at <= _as_utc(now)


def clear_provider_limit(task: Task) -> None:
    depends_on = dict(task.depends_on or {})
    depends_on.pop("provider_limit", None)
    task.depends_on = depends_on or None
    task.blocked_reason = None
    task.blocked_at = None
    task.capability_limit_at = None
    task.capability_limit_reason = None
    task.dead_letter_queued_at = None


def parse_reset_hint(
    text: str | None,
    *,
    now: datetime | None = None,
) -> tuple[datetime | None, str]:
    """Parse common Claude provider-limit reset hints without model help."""
    source = " ".join(str(text or "").split()).strip()
    if not source:
        return None, ""
    base = _as_utc(now)

    relative = _RESET_IN_RE.search(source)
    if relative:
        amount = int(relative.group("amount"))
        unit = relative.group("unit").lower()
        delta = timedelta(hours=amount) if unit.startswith("hour") else timedelta(minutes=amount)
        return base + delta, relative.group(0)

    absolute = _RESET_TIME_RE.search(source)
    if absolute:
        parsed = _parse_clock_time(
            absolute.group("time"),
            now=base,
            timezone_name=_reset_timezone(source[absolute.end() :]),
        )
        return parsed, absolute.group(0)

    try_again_at = _TRY_AGAIN_AT_RE.search(source)
    if try_again_at:
        parsed = _parse_calendar_time(
            try_again_at,
            timezone_name=_reset_timezone(source[try_again_at.end() :]),
        )
        return parsed, try_again_at.group(0)

    return None, ""


def _parse_clock_time(
    value: str,
    *,
    now: datetime,
    timezone_name: str | None = None,
) -> datetime | None:
    compact = value.strip().lower().replace(" ", "")
    match = re.match(r"^(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?(?P<ampm>am|pm)$", compact)
    if not match:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or "0")
    if hour < 1 or hour > 12 or minute > 59:
        return None
    if match.group("ampm") == "pm" and hour != 12:
        hour += 12
    if match.group("ampm") == "am" and hour == 12:
        hour = 0
    timezone = _load_zoneinfo(timezone_name) or UTC
    local_now = now.astimezone(timezone)
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)


def _parse_calendar_time(
    match: re.Match[str],
    *,
    timezone_name: str | None = None,
) -> datetime | None:
    value = (
        f"{match.group('month')} {match.group('day')} {match.group('year')} "
        f"{match.group('time')}"
    )
    try:
        parsed = datetime.strptime(value, "%B %d %Y %I:%M %p")
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%b %d %Y %I:%M %p")
        except ValueError:
            return None
    timezone = _load_zoneinfo(timezone_name) or UTC
    return parsed.replace(tzinfo=timezone).astimezone(UTC)


def _reset_timezone(value: str) -> str | None:
    match = _RESET_TIMEZONE_RE.search(value)
    return match.group("zone") if match else None


def _load_zoneinfo(value: str | None) -> ZoneInfo | None:
    if not value:
        return None
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return None


def _parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc(parsed)


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
