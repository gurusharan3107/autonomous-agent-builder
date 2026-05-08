"""Tests for Phase D outcomes integration.

Covers:
- FeatureOutcome synthesis from builder Feature fields
- run_outcome end-to-end: user.define_outcome event sent, grader
  verdict captured, RunResult.stop_reason mapped
- All four terminal outcome verdicts (satisfied / max_iterations_reached
  / failed / interrupted) round-trip through RunResult
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from autonomous_agent_builder.runtime.managed_agents_outcome import (
    FeatureOutcome,
    build_feature_outcome,
)
from autonomous_agent_builder.runtime.managed_agents_runtime import (
    ManagedAgentsConfigError,
    ManagedAgentsRuntime,
)

# ── Helpers (re-used from test_managed_agents_runtime.py) ──


def _event(**fields: Any) -> SimpleNamespace:
    return SimpleNamespace(**fields)


class _FakeStream:
    def __init__(self, events: list[Any]):
        self._events = list(events)

    async def __aenter__(self) -> _FakeStream:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    def __aiter__(self) -> _FakeStream:
        return self

    async def __anext__(self) -> Any:
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)


def _make_outcome_client(
    *,
    session_id: str = "sesn_outcome",
    stream_events: list[Any] | None = None,
    sent_events: list[list[Any]] | None = None,
) -> Any:
    sent = sent_events if sent_events is not None else []

    @asynccontextmanager
    async def _stream_ctx(**_kwargs: Any):
        async with _FakeStream(stream_events or []) as s:
            yield s

    async def _send(events: list[Any], **_kw: Any):
        sent.append(list(events))
        return SimpleNamespace(events=events)

    async def _create(**_kwargs: Any):
        return SimpleNamespace(id=session_id, status="running")

    client = MagicMock()
    client.close = AsyncMock(return_value=None)
    client.beta.sessions.create = AsyncMock(side_effect=_create)
    client.beta.sessions.events.send = AsyncMock(side_effect=_send)
    client.beta.sessions.events.stream = MagicMock(
        side_effect=lambda **kw: _stream_ctx(**kw)
    )
    return client


# ── FeatureOutcome synthesis ──


def test_build_feature_outcome_with_criteria_emits_numbered_rubric() -> None:
    outcome = build_feature_outcome(
        feature_title="Add bookmarks",
        feature_description="Users can bookmark posts.",
        acceptance_criteria=[
            "Bookmark button persists across reloads",
            "Bookmarks are private per user",
        ],
        max_iterations_cap=5,
    )
    assert outcome.description.startswith("Add bookmarks")
    assert "1. Bookmark button persists across reloads" in outcome.rubric
    assert "2. Bookmarks are private per user" in outcome.rubric
    # 2 criteria, cap of 5 → 2 iterations
    assert outcome.max_iterations == 2


def test_build_feature_outcome_caps_iterations() -> None:
    outcome = build_feature_outcome(
        feature_title="Big feature",
        feature_description="",
        acceptance_criteria=[f"criterion {i}" for i in range(10)],
        max_iterations_cap=3,
    )
    assert outcome.max_iterations == 3


def test_build_feature_outcome_handles_empty_criteria() -> None:
    outcome = build_feature_outcome(
        feature_title="Vague feature",
        feature_description="No clear acceptance criteria.",
        acceptance_criteria=[],
    )
    # Should not crash; rubric explains the situation
    assert "none provided" in outcome.rubric
    assert outcome.max_iterations == 1


def test_build_feature_outcome_strips_whitespace_only_criteria() -> None:
    outcome = build_feature_outcome(
        feature_title="t",
        feature_description="",
        acceptance_criteria=["", "  ", "real criterion"],
    )
    assert "1. real criterion" in outcome.rubric
    assert outcome.max_iterations == 1


def test_feature_outcome_as_event_payload_shape() -> None:
    outcome = FeatureOutcome(
        description="Add login",
        rubric="1. user can sign in\n2. token expires after 1h",
        max_iterations=2,
    )
    payload = outcome.as_event_payload()
    assert payload["type"] == "user.define_outcome"
    assert payload["description"] == "Add login"
    assert payload["rubric"] == {"type": "text", "content": outcome.rubric}
    assert payload["max_iterations"] == 2


# ── run_outcome end-to-end ──


@pytest.mark.asyncio
async def test_run_outcome_sends_define_outcome_event_not_user_message() -> None:
    """The kickoff event MUST be `user.define_outcome` for the rubric path."""
    sent: list[list[Any]] = []
    events = [
        _event(
            type="span.outcome_evaluation_end",
            result="satisfied",
            explanation="all criteria met",
            iteration=0,
        ),
        _event(type="session.status_idle", stop_reason=_event(type="end_turn")),
    ]
    client = _make_outcome_client(stream_events=events, sent_events=sent)

    runtime = ManagedAgentsRuntime(
        config_loader=lambda: {
            "agents": {"feature-verifier": "agent_fv"},
            "environment_id": "env_x",
        },
        client_factory=lambda: client,
    )
    result = await runtime.run_outcome(
        agent="feature-verifier",
        description="Build a DCF model",
        rubric="1. has a DCF tab\n2. uses 5y of history",
        max_iterations=3,
    )

    assert result.error is None, result.error
    sent_flat = [e for batch in sent for e in batch]
    kickoff = sent_flat[0]
    assert kickoff["type"] == "user.define_outcome"
    assert kickoff["description"] == "Build a DCF model"
    assert kickoff["rubric"]["type"] == "text"
    assert kickoff["max_iterations"] == 3


@pytest.mark.asyncio
async def test_run_outcome_clamps_max_iterations_to_ma_limit() -> None:
    """MA caps at 20; runtime clamps defensively."""
    sent: list[list[Any]] = []
    events = [
        _event(type="session.status_idle", stop_reason=_event(type="end_turn"))
    ]
    client = _make_outcome_client(stream_events=events, sent_events=sent)

    runtime = ManagedAgentsRuntime(
        config_loader=lambda: {
            "agents": {"feature-verifier": "agent_fv"},
            "environment_id": "env_x",
        },
        client_factory=lambda: client,
    )
    await runtime.run_outcome(
        agent="feature-verifier",
        description="x",
        rubric="1. x",
        max_iterations=999,  # well above MA's max of 20
    )
    sent_flat = [e for batch in sent for e in batch]
    assert sent_flat[0]["max_iterations"] == 20


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "verdict,expected_stop",
    [
        ("satisfied", "outcome_satisfied"),
        ("max_iterations_reached", "max_iterations_reached"),
        ("failed", "outcome_failed"),
        ("interrupted", "interrupted"),
    ],
)
async def test_run_outcome_maps_terminal_verdict_to_stop_reason(
    verdict: str, expected_stop: str
) -> None:
    events = [
        _event(
            type="span.outcome_evaluation_end",
            result=verdict,
            explanation=f"verdict={verdict}",
            iteration=0,
        ),
        _event(type="session.status_idle", stop_reason=_event(type="end_turn")),
    ]
    client = _make_outcome_client(stream_events=events)
    runtime = ManagedAgentsRuntime(
        config_loader=lambda: {
            "agents": {"feature-verifier": "agent_fv"},
            "environment_id": "env_x",
        },
        client_factory=lambda: client,
    )
    result = await runtime.run_outcome(
        agent="feature-verifier",
        description="x",
        rubric="1. x",
        max_iterations=3,
    )
    assert result.stop_reason == expected_stop
    assert result.observability is not None
    outcome_obs = result.observability["managed_agents"]["outcome"]
    assert outcome_obs["result"] == verdict
    assert outcome_obs["explanation"] == f"verdict={verdict}"


@pytest.mark.asyncio
async def test_run_outcome_keeps_only_terminal_verdict_when_multiple_iterations() -> None:
    """Grader emits one `_end` per iteration; we keep the last terminal one."""
    events = [
        _event(
            type="span.outcome_evaluation_end",
            result="needs_revision",
            explanation="iter 0 incomplete",
            iteration=0,
        ),
        _event(
            type="span.outcome_evaluation_end",
            result="needs_revision",
            explanation="iter 1 still incomplete",
            iteration=1,
        ),
        _event(
            type="span.outcome_evaluation_end",
            result="satisfied",
            explanation="iter 2 complete",
            iteration=2,
        ),
        _event(type="session.status_idle", stop_reason=_event(type="end_turn")),
    ]
    client = _make_outcome_client(stream_events=events)
    runtime = ManagedAgentsRuntime(
        config_loader=lambda: {
            "agents": {"feature-verifier": "agent_fv"},
            "environment_id": "env_x",
        },
        client_factory=lambda: client,
    )
    result = await runtime.run_outcome(
        agent="feature-verifier",
        description="x",
        rubric="1. x",
        max_iterations=5,
    )
    assert result.stop_reason == "outcome_satisfied"
    assert result.observability["managed_agents"]["outcome_iterations"] == 3
    # Last verdict is the terminal one, not "needs_revision"
    assert (
        result.observability["managed_agents"]["outcome"]["result"] == "satisfied"
    )
    assert result.observability["managed_agents"]["outcome"]["iteration"] == 2


@pytest.mark.asyncio
async def test_run_outcome_returns_error_when_config_missing() -> None:
    def _missing() -> dict[str, Any]:
        raise ManagedAgentsConfigError("not provisioned")

    runtime = ManagedAgentsRuntime(
        config_loader=_missing, client_factory=lambda: _make_outcome_client()
    )
    result = await runtime.run_outcome(
        agent="feature-verifier",
        description="x",
        rubric="1. x",
    )
    assert result.error is not None
    assert "not provisioned" in result.error
