from __future__ import annotations

from datetime import UTC, datetime, timedelta

from autonomous_agent_builder.db.models import Task, TaskPhase, TaskStatus
from autonomous_agent_builder.services.provider_limits import (
    clear_provider_limit,
    is_provider_limit_text,
    mark_provider_limit,
    parse_reset_hint,
    provider_limit_is_ready,
    provider_limit_payload,
)


def test_parse_reset_hint_absolute_time_rolls_forward() -> None:
    now = datetime(2026, 4, 29, 21, 0, tzinfo=UTC)

    reset_at, reset_hint = parse_reset_hint("You've hit your limit - resets 8:50pm", now=now)

    assert reset_hint == "resets 8:50pm"
    assert reset_at == datetime(2026, 4, 30, 20, 50, tzinfo=UTC)


def test_parse_reset_hint_absolute_time_with_timezone() -> None:
    now = datetime(2026, 4, 30, 12, 7, tzinfo=UTC)

    reset_at, reset_hint = parse_reset_hint(
        "You've hit your limit - resets 9:30pm (Asia/Calcutta)",
        now=now,
    )

    assert reset_hint == "resets 9:30pm"
    assert reset_at == datetime(2026, 4, 30, 16, 0, tzinfo=UTC)


def test_parse_reset_hint_relative_minutes() -> None:
    now = datetime(2026, 4, 29, 10, 0, tzinfo=UTC)

    reset_at, reset_hint = parse_reset_hint(
        "API Error: rate limit reached, resets in 45 minutes",
        now=now,
    )

    assert reset_hint == "resets in 45 minutes"
    assert reset_at == now + timedelta(minutes=45)


def test_codex_usage_limit_text_and_try_again_date_are_detected() -> None:
    text = (
        "You've hit your usage limit. Upgrade to Plus to continue using Codex, "
        "or try again at May 8th, 2026 12:02 PM."
    )

    reset_at, reset_hint = parse_reset_hint(text)

    assert is_provider_limit_text(text)
    assert reset_hint == "try again at May 8th, 2026 12:02 PM"
    assert reset_at == datetime(2026, 5, 8, 12, 2, tzinfo=UTC)


def test_codex_usage_limit_get_more_access_text_is_detected() -> None:
    text = (
        "You've hit your usage limit. To get more access now, send a request "
        "to your administrator."
    )

    assert is_provider_limit_text(text)


def test_mark_provider_limit_records_resume_metadata() -> None:
    now = datetime(2026, 4, 29, 10, 0, tzinfo=UTC)
    task = Task(
        id="task-limit",
        feature_id="feature-1",
        title="Provider limit",
        description="Exercise provider-limit blocking",
        status=TaskStatus.DESIGN,
        phase=TaskPhase.IMPLEMENTATION,
    )

    payload = mark_provider_limit(
        task,
        reason="SDK limit: provider_limit",
        output_text="You've hit your limit - resets in 30 minutes",
        now=now,
    )

    assert task.status == TaskStatus.CAPABILITY_LIMIT
    assert task.blocked_reason is not None
    assert task.blocked_reason.startswith("provider limit blocked:")
    assert task.capability_limit_reason == "SDK limit: provider_limit"
    assert payload["resume_status"] == "implementation"
    assert payload["reset_at"] == (now + timedelta(minutes=30)).isoformat()
    assert provider_limit_payload(task)["code"] == "provider_limit"
    assert not provider_limit_is_ready(task, now=now + timedelta(minutes=29))
    assert provider_limit_is_ready(task, now=now + timedelta(minutes=30))

    clear_provider_limit(task)

    assert task.blocked_reason is None
    assert provider_limit_payload(task) == {}
