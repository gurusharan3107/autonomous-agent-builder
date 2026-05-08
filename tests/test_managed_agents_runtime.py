"""Tests for the Managed Agents runtime adapter (Phase A).

Covers:
- Config loader missing-file / invalid-JSON / missing-role error paths
- Probe paths: missing API key, missing setup, beta-access success
- run() happy path: stream-first ordering, RunResult mapping (cost, tokens,
  session_id, num_turns, observability)
- Idle-break gate: requires_action does NOT break; end_turn does
- Custom tool round-trip: agent.custom_tool_use → builder_memory_search →
  user.custom_tool_result event sent
- Factory dispatch: RUNTIME_SDK=claude_managed produces a
  ManagedAgentsRuntime with correct provider/model
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from autonomous_agent_builder.runtime.interface import RuntimeProbeResult
from autonomous_agent_builder.runtime.managed_agents_custom_tools import (
    CustomToolRegistry,
)
from autonomous_agent_builder.runtime.managed_agents_runtime import (
    ManagedAgentsConfigError,
    ManagedAgentsRuntime,
    _agent_id_for_role,
    _environment_id,
    _estimate_cost,
    _load_managed_agents_config,
)

# ── Helpers ─────────────────────────────────────────────────────────────


def _write_config(project_root: Path, payload: dict[str, Any]) -> None:
    cfg_dir = project_root / ".agent-builder"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "managed_agents.json").write_text(json.dumps(payload))


def _event(**fields: Any) -> SimpleNamespace:
    """Build an SDK-shaped event object (attrs, not dict, to mirror the SDK)."""
    return SimpleNamespace(**fields)


class _FakeStream:
    """Async-iterator stand-in for `client.beta.sessions.events.stream(...)`."""

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


def _make_fake_client(
    *,
    session_id: str = "sesn_test",
    stream_events: list[Any] | None = None,
    sent_events: list[list[Any]] | None = None,
) -> Any:
    """Construct a mock anthropic.AsyncAnthropic with beta.sessions wired."""
    sent = sent_events if sent_events is not None else []

    @asynccontextmanager
    async def _stream_ctx(**_kwargs: Any):
        async with _FakeStream(stream_events or []) as s:
            yield s

    def _stream(**kwargs: Any):
        return _stream_ctx(**kwargs)

    async def _send(events: list[Any], session_id: str | None = None, **_kw: Any):
        sent.append(list(events))
        return SimpleNamespace(events=events)

    async def _create(**_kwargs: Any):
        return SimpleNamespace(id=session_id, status="running")

    async def _list(**_kwargs: Any):
        return SimpleNamespace(data=[])

    client = MagicMock()
    client.close = AsyncMock(return_value=None)
    client.beta.agents.list = AsyncMock(side_effect=_list)
    client.beta.sessions.create = AsyncMock(side_effect=_create)
    client.beta.sessions.events.send = AsyncMock(side_effect=_send)
    client.beta.sessions.events.stream = MagicMock(side_effect=_stream)
    return client


# ── Config loader ───────────────────────────────────────────────────────


def test_load_managed_agents_config_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(ManagedAgentsConfigError, match="not found"):
        _load_managed_agents_config(tmp_path)


def test_load_managed_agents_config_invalid_json_raises(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".agent-builder"
    cfg_dir.mkdir()
    (cfg_dir / "managed_agents.json").write_text("not json {")
    with pytest.raises(ManagedAgentsConfigError, match="invalid JSON"):
        _load_managed_agents_config(tmp_path)


def test_load_managed_agents_config_round_trip(tmp_path: Path) -> None:
    payload = {"agents": {"planner": "agent_001"}, "environment_id": "env_001"}
    _write_config(tmp_path, payload)
    assert _load_managed_agents_config(tmp_path) == payload


def test_agent_id_for_role_missing_raises() -> None:
    with pytest.raises(ManagedAgentsConfigError, match="No managed agent provisioned"):
        _agent_id_for_role({"agents": {}}, "planner")


def test_environment_id_missing_raises() -> None:
    with pytest.raises(ManagedAgentsConfigError, match="No managed-agents environment"):
        _environment_id({"environment_id": None})


# ── Pricing helper ──────────────────────────────────────────────────────


def test_estimate_cost_opus_47() -> None:
    # 1M input @ $5, 1M output @ $25, no cache
    cost = _estimate_cost("claude-opus-4-7", 1_000_000, 1_000_000, 0)
    assert cost == 30.0


def test_estimate_cost_with_cache_hits() -> None:
    # 100K input, 50K cache hits → uncached is 50K; output 100K
    cost = _estimate_cost("claude-opus-4-7", 100_000, 100_000, 50_000)
    expected = (
        (50_000 / 1_000_000) * 5.00
        + (50_000 / 1_000_000) * 0.50
        + (100_000 / 1_000_000) * 25.00
    )
    assert cost == round(expected, 6)


def test_estimate_cost_unknown_model_returns_zero() -> None:
    assert _estimate_cost("unknown-model", 100, 100, 0) == 0.0


# ── Probe ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_probe_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runtime = ManagedAgentsRuntime(
        config_loader=lambda: {"agents": {"planner": "a"}, "environment_id": "e"},
        client_factory=_make_fake_client,
    )
    result = await runtime.probe()
    assert isinstance(result, RuntimeProbeResult)
    assert result.ok is False
    assert result.code == "missing_api_key"


@pytest.mark.asyncio
async def test_probe_missing_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def _missing() -> dict[str, Any]:
        raise ManagedAgentsConfigError("config not found")

    runtime = ManagedAgentsRuntime(
        config_loader=_missing, client_factory=_make_fake_client
    )
    result = await runtime.probe()
    assert result.ok is False
    assert result.code == "missing_setup"


@pytest.mark.asyncio
async def test_probe_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    runtime = ManagedAgentsRuntime(
        config_loader=lambda: {"agents": {"planner": "a"}, "environment_id": "e"},
        client_factory=_make_fake_client,
    )
    result = await runtime.probe()
    assert result.ok is True
    assert result.code == "managed_agents_available"


# ── run() — happy path + RunResult mapping ─────────────────────────────


@pytest.mark.asyncio
async def test_run_happy_path_maps_run_result() -> None:
    """One agent.message + one span.model_request_end + idle end_turn."""
    sent: list[list[Any]] = []
    events = [
        _event(
            type="agent.message",
            content=[_event(type="text", text="planning result line 1")],
        ),
        _event(
            type="span.model_request_end",
            model_usage={
                "input_tokens": 1500,
                "output_tokens": 400,
                "cache_read_input_tokens": 1000,
                "cache_creation_input_tokens": 0,
            },
        ),
        _event(
            type="agent.message",
            content=[_event(type="text", text=" line 2")],
        ),
        _event(
            type="session.status_idle",
            stop_reason=_event(type="end_turn"),
        ),
    ]
    client = _make_fake_client(stream_events=events, sent_events=sent)
    runtime = ManagedAgentsRuntime(
        config_loader=lambda: {
            "agents": {"planner": "agent_planner_id"},
            "environment_id": "env_id",
        },
        client_factory=lambda: client,
    )

    result = await runtime.run("plan this feature", agent="planner")

    assert result.error is None, result.error
    assert result.session_id == "sesn_test"
    assert result.output == "planning result line 1 line 2"
    assert result.tokens_input == 1500
    assert result.tokens_output == 400
    assert result.tokens_cached == 1000
    assert result.num_turns == 2
    assert result.stop_reason == "end_turn"
    assert result.duration_ms >= 0
    # Cost: 500 uncached @ $5/M + 1000 cached @ $0.50/M + 400 output @ $25/M
    expected_cost = (
        (500 / 1_000_000) * 5.00
        + (1_000 / 1_000_000) * 0.50
        + (400 / 1_000_000) * 25.00
    )
    assert result.cost_usd == round(expected_cost, 6)
    assert result.observability is not None
    assert result.observability["managed_agents"]["session_id"] == "sesn_test"


@pytest.mark.asyncio
async def test_run_stream_opens_before_send() -> None:
    """Stream-first per MA Pattern 7: send() called only after stream() opens."""
    call_order: list[str] = []
    events = [
        _event(type="session.status_idle", stop_reason=_event(type="end_turn"))
    ]

    @asynccontextmanager
    async def _stream_ctx(**_kwargs: Any):
        call_order.append("stream_open")
        async with _FakeStream(events) as s:
            yield s

    async def _send(**_kw: Any):
        call_order.append("send")
        return SimpleNamespace()

    async def _create(**_kw: Any):
        return SimpleNamespace(id="sesn_x")

    client = MagicMock()
    client.close = AsyncMock(return_value=None)
    client.beta.sessions.create = AsyncMock(side_effect=_create)
    client.beta.sessions.events.send = AsyncMock(side_effect=_send)
    client.beta.sessions.events.stream = MagicMock(side_effect=lambda **kw: _stream_ctx(**kw))

    runtime = ManagedAgentsRuntime(
        config_loader=lambda: {"agents": {"planner": "a"}, "environment_id": "e"},
        client_factory=lambda: client,
    )
    await runtime.run("hello", agent="planner")

    # First the stream context opens, then send fires while stream is live.
    assert call_order[0] == "stream_open"
    assert "send" in call_order


@pytest.mark.asyncio
async def test_run_idle_with_requires_action_does_not_break() -> None:
    """Bare idle with stop_reason=requires_action keeps streaming; end_turn ends."""
    events = [
        _event(
            type="session.status_idle",
            stop_reason=_event(type="requires_action"),
        ),
        _event(type="agent.message", content=[_event(type="text", text="continued")]),
        _event(type="session.status_idle", stop_reason=_event(type="end_turn")),
    ]
    client = _make_fake_client(stream_events=events)
    runtime = ManagedAgentsRuntime(
        config_loader=lambda: {"agents": {"planner": "a"}, "environment_id": "e"},
        client_factory=lambda: client,
    )
    result = await runtime.run("hi", agent="planner")
    # The "continued" message after requires_action must be captured
    assert "continued" in result.output
    assert result.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_run_terminated_event_breaks() -> None:
    events = [
        _event(type="agent.message", content=[_event(type="text", text="oops")]),
        _event(type="session.status_terminated"),
        # Anything after terminated should NOT be processed
        _event(type="agent.message", content=[_event(type="text", text="ignored")]),
    ]
    client = _make_fake_client(stream_events=events)
    runtime = ManagedAgentsRuntime(
        config_loader=lambda: {"agents": {"planner": "a"}, "environment_id": "e"},
        client_factory=lambda: client,
    )
    result = await runtime.run("hi", agent="planner")
    assert result.stop_reason == "terminated"
    assert result.output == "oops"


@pytest.mark.asyncio
async def test_run_provider_limit_on_retries_exhausted() -> None:
    events = [
        _event(
            type="session.status_idle",
            stop_reason=_event(type="retries_exhausted"),
        ),
    ]
    client = _make_fake_client(stream_events=events)
    runtime = ManagedAgentsRuntime(
        config_loader=lambda: {"agents": {"planner": "a"}, "environment_id": "e"},
        client_factory=lambda: client,
    )
    result = await runtime.run("hi", agent="planner")
    assert result.stop_reason == "retries_exhausted"
    assert result.provider_limit is not None
    assert result.provider_limit["code"] == "retries_exhausted"


# ── Custom tool round-trip ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_custom_tool_round_trip_for_builder_memory_search() -> None:
    """agent.custom_tool_use → host handler runs → user.custom_tool_result sent."""
    sent: list[list[Any]] = []
    events = [
        _event(
            type="agent.custom_tool_use",
            id="sevt_tool_1",
            name="builder_memory_search",
            input={"query": "worktree"},
        ),
        _event(type="session.status_idle", stop_reason=_event(type="end_turn")),
    ]
    client = _make_fake_client(stream_events=events, sent_events=sent)

    registry = CustomToolRegistry()
    captured_inputs: list[dict[str, Any]] = []

    async def _handler(input_json: dict[str, Any]) -> str:
        captured_inputs.append(input_json)
        return "memory entry: prefer worktrees under /home/user/worktree/..."

    registry.register("builder_memory_search", _handler)

    runtime = ManagedAgentsRuntime(
        config_loader=lambda: {"agents": {"planner": "a"}, "environment_id": "e"},
        client_factory=lambda: client,
        custom_tool_registry=registry,
    )

    await runtime.run("research worktree convention", agent="planner")

    # Handler ran with the agent's input
    assert captured_inputs == [{"query": "worktree"}]
    # A user.custom_tool_result event was sent back referencing the tool_use id
    sent_flat = [e for batch in sent for e in batch]
    tool_results = [e for e in sent_flat if e.get("type") == "user.custom_tool_result"]
    assert len(tool_results) == 1
    result_event = tool_results[0]
    assert result_event["custom_tool_use_id"] == "sevt_tool_1"
    assert result_event["content"][0]["text"].startswith("memory entry:")


@pytest.mark.asyncio
async def test_unknown_custom_tool_yields_is_error_response() -> None:
    sent: list[list[Any]] = []
    events = [
        _event(
            type="agent.custom_tool_use",
            id="sevt_tool_2",
            name="not_registered",
            input={},
        ),
        _event(type="session.status_idle", stop_reason=_event(type="end_turn")),
    ]
    client = _make_fake_client(stream_events=events, sent_events=sent)
    runtime = ManagedAgentsRuntime(
        config_loader=lambda: {"agents": {"planner": "a"}, "environment_id": "e"},
        client_factory=lambda: client,
        # default registry has builder_memory_search, NOT `not_registered`
    )
    await runtime.run("hi", agent="planner")
    sent_flat = [e for batch in sent for e in batch]
    tool_results = [e for e in sent_flat if e.get("type") == "user.custom_tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0]["is_error"] is True
    assert "Unknown tool" in tool_results[0]["content"][0]["text"]


# ── Error paths ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_returns_error_when_config_missing() -> None:
    def _missing() -> dict[str, Any]:
        raise ManagedAgentsConfigError("not provisioned")

    runtime = ManagedAgentsRuntime(
        config_loader=_missing, client_factory=_make_fake_client
    )
    result = await runtime.run("hi", agent="planner")
    assert result.error is not None
    assert "not provisioned" in result.error
    assert result.session_id is None


@pytest.mark.asyncio
async def test_run_returns_error_when_role_missing() -> None:
    runtime = ManagedAgentsRuntime(
        config_loader=lambda: {"agents": {"designer": "a"}, "environment_id": "e"},
        client_factory=_make_fake_client,
    )
    result = await runtime.run("hi", agent="planner")
    assert result.error is not None
    assert "planner" in result.error


# ── Capabilities + name ─────────────────────────────────────────────────


def test_runtime_name_and_capabilities() -> None:
    runtime = ManagedAgentsRuntime(
        config_loader=lambda: {"agents": {"planner": "a"}, "environment_id": "e"},
        client_factory=_make_fake_client,
    )
    assert runtime.name == "claude_managed"
    assert runtime.provider == "anthropic_managed"
    caps = runtime.capabilities()
    assert caps.streaming is True
    assert caps.api_key_auth is True
    assert caps.subscription_auth is False
    assert caps.subagents is True
    assert caps.tracing is True


# ── Factory dispatch ───────────────────────────────────────────────────


def test_factory_dispatches_claude_managed_to_managed_agents_runtime() -> None:
    from autonomous_agent_builder.runtime.factory import (
        create_runtime,
        get_available_runtimes,
        get_implemented_runtimes,
        validate_runtime_config,
    )

    assert "claude_managed" in get_available_runtimes()
    assert "claude_managed" in get_implemented_runtimes()

    # Legal pair: claude_managed + anthropic_managed
    errors = validate_runtime_config(
        {"sdk": "claude_managed", "provider": "anthropic_managed"}
    )
    assert errors == []

    # Illegal pair: claude_managed + claude_code
    errors = validate_runtime_config(
        {"sdk": "claude_managed", "provider": "claude_code"}
    )
    assert any(e["code"] == "invalid_provider" for e in errors)

    rt = create_runtime(sdk="claude_managed", provider="anthropic_managed")
    assert rt.name == "claude_managed"
    assert rt.provider == "anthropic_managed"
