from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import asyncio
import pytest

from autonomous_agent_builder.runtime.codex_app_server_runtime import CodexAppServerRuntime


class _FakeStdout:
    def __init__(self, messages: list[dict[str, Any]]):
        self._lines = [
            (json.dumps(message) + "\n").encode("utf-8") for message in messages
        ]

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)


class _IdleStdout:
    def __init__(self, messages: list[dict[str, Any]]):
        self._lines = [
            (json.dumps(message) + "\n").encode("utf-8") for message in messages
        ]

    async def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        await asyncio.sleep(60)
        return b""


class _FakeStderr:
    def __init__(self, text: str = ""):
        self.text = text

    async def read(self) -> bytes:
        return self.text.encode("utf-8")


class _FakeStdin:
    def __init__(self):
        self.messages: list[dict[str, Any]] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.messages.append(json.loads(data.decode("utf-8")))

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, messages: list[dict[str, Any]], *, stderr: str = ""):
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout(messages)
        self.stderr = _FakeStderr(stderr)
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = 1

    async def wait(self) -> int:
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


class _IdleProcess(_FakeProcess):
    def __init__(self, messages: list[dict[str, Any]]):
        super().__init__([])
        self.stdout = _IdleStdout(messages)


@pytest.mark.asyncio
async def test_codex_app_server_runtime_streams_and_parses_usage(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )
    process = _FakeProcess(
        [
            {"id": 1, "result": {"userAgent": "codex-test"}},
            {"id": 2, "result": {"thread": {"id": "thread-123"}}},
            {
                "id": 3,
                "result": {"turn": {"id": "turn-123", "status": "inProgress"}},
            },
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "thread-123",
                    "turnId": "turn-123",
                    "itemId": "item-1",
                    "delta": "Final answer",
                },
            },
            {
                "method": "item/started",
                "params": {
                    "item": {
                        "type": "toolCall",
                        "name": "Edit",
                        "input": {"file_path": "src/app.js"},
                    },
                },
            },
            {
                "method": "item/reasoning/delta",
                "params": {"delta": "Checking the existing search behavior."},
            },
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "threadId": "thread-123",
                    "turnId": "turn-123",
                    "tokenUsage": {
                        "last": {
                            "inputTokens": 10,
                            "cachedInputTokens": 2,
                            "outputTokens": 4,
                            "reasoningOutputTokens": 1,
                            "totalTokens": 14,
                        },
                        "total": {
                            "inputTokens": 10,
                            "cachedInputTokens": 2,
                            "outputTokens": 4,
                            "reasoningOutputTokens": 1,
                            "totalTokens": 14,
                        },
                    },
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-123",
                    "turn": {"id": "turn-123", "status": "completed", "error": None},
                },
            },
        ]
    )

    started_cmd: tuple[Any, ...] = ()

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        nonlocal started_cmd
        started_cmd = cmd
        return process

    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    chunks: list[str] = []
    tool_events: list[dict[str, Any]] = []

    async def record_tool_event(**event: Any) -> None:
        tool_events.append(event)

    runtime = CodexAppServerRuntime(model="gpt-5.5")
    result = await runtime.run(
        "Do the work",
        agent="chat",
        workspace_path=str(tmp_path),
        effort="medium",
        on_chunk=chunks.append,
        on_tool_event=record_tool_event,
    )

    assert result.success is True
    assert result.output == "Final answer"
    assert result.session_id == "thread-123"
    assert result.tokens_input == 10
    assert result.tokens_output == 4
    assert result.tokens_cached == 2
    assert chunks == ["Final answer"]
    assert {
        "event_type": "tool_use",
        "tool_name": "Edit",
        "tool_input": {"file_path": "src/app.js"},
        "output_preview": "item/started",
    } in tool_events
    assert {
        "event_type": "thinking",
        "tool_name": "item/reasoning/delta",
        "tool_input": {},
        "output_preview": "Checking the existing search behavior.",
    } in tool_events
    assert result.observability is not None
    assert result.observability["runtime_sdk"] == "codex_sdk"
    assert result.observability["protocol"] == "codex_app_server_jsonrpc"
    assert result.observability["telemetry_source"] == "codex_app_server_events"
    assert result.observability["native_user_input"] is True
    optimization = result.observability["optimization_summary"]
    assert optimization["primary_score"] == "raw_tokens"
    assert optimization["token_accounting"]["raw_total_tokens"] == 14
    assert optimization["token_accounting"]["noncached_plus_output_tokens"] == 12
    assert optimization["token_accounting"]["cache_ratio"] == 0.2
    assert optimization["event_accounting"]["raw_event_count"] >= 6
    assert started_cmd[:6] == (
        "codex",
        "app-server",
        "--listen",
        "stdio://",
        "--enable",
        "default_mode_request_user_input",
    )
    assert process.stdin.messages[0]["method"] == "initialize"
    assert process.stdin.messages[1]["method"] == "initialized"
    assert process.stdin.messages[2]["method"] == "thread/start"
    assert process.stdin.messages[2]["params"]["persistExtendedHistory"] is False
    assert process.stdin.messages[3]["method"] == "turn/start"
    assert process.stdin.messages[3]["params"]["effort"] == "medium"


@pytest.mark.asyncio
async def test_codex_app_server_runtime_persists_history_only_when_resuming(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )
    process = _FakeProcess(
        [
            {"id": 1, "result": {"userAgent": "codex-test"}},
            {"id": 2, "result": {"thread": {"id": "thread-existing"}}},
            {"id": 3, "result": {"turn": {"id": "turn-123", "status": "inProgress"}}},
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "thread-existing",
                    "turnId": "turn-123",
                    "itemId": "item-1",
                    "delta": "Done",
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-existing",
                    "turn": {"id": "turn-123", "status": "completed", "error": None},
                },
            },
        ]
    )

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return process

    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    runtime = CodexAppServerRuntime(model="gpt-5.5")
    result = await runtime.run(
        "Continue the work",
        agent="chat",
        workspace_path=str(tmp_path),
        session="thread-existing",
    )

    assert result.success is True
    assert process.stdin.messages[2]["method"] == "thread/resume"
    assert process.stdin.messages[2]["params"]["threadId"] == "thread-existing"
    assert process.stdin.messages[2]["params"]["persistExtendedHistory"] is True


@pytest.mark.asyncio
async def test_codex_app_server_runtime_maps_request_user_input(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )
    process = _FakeProcess(
        [
            {"id": 1, "result": {"userAgent": "codex-test"}},
            {"id": 2, "result": {"thread": {"id": "thread-ask"}}},
            {
                "id": 3,
                "result": {"turn": {"id": "turn-ask", "status": "inProgress"}},
            },
            {
                "id": "question-1",
                "method": "item/tool/requestUserInput",
                "params": {
                    "threadId": "thread-ask",
                    "turnId": "turn-ask",
                    "itemId": "tool-1",
                    "questions": [
                        {
                            "id": "product_type",
                            "header": "Product",
                            "question": "What type of product should we build?",
                            "options": [
                                {
                                    "label": "SaaS dashboard",
                                    "description": "Operational product with task lanes.",
                                }
                            ],
                        }
                    ],
                },
            },
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "thread-ask",
                    "turnId": "turn-ask",
                    "itemId": "item-2",
                    "delta": "Agreement reached",
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-ask",
                    "turn": {"id": "turn-ask", "status": "completed", "error": None},
                },
            },
        ]
    )

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return process

    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    captured_questions: list[dict[str, Any]] = []

    class Allow:
        def __init__(self, updated_input: dict[str, Any]):
            self.updated_input = updated_input

    async def can_use_tool(tool_name: str, input_data: dict[str, Any], context: Any) -> Allow:
        captured_questions.append({"tool_name": tool_name, "input": input_data})
        return Allow(
            {
                "questions": input_data["questions"],
                "answers": {
                    "What type of product should we build?": "SaaS dashboard",
                },
            }
        )

    runtime = CodexAppServerRuntime(model="gpt-5.5")
    result = await runtime.run(
        "Start onboarding",
        agent="init-project-chat",
        workspace_path=str(tmp_path),
        can_use_tool=can_use_tool,
    )

    assert result.success is True
    assert captured_questions == [
        {
            "tool_name": "request_user_input",
            "input": {
                "questions": [
                    {
                        "header": "Product",
                        "question": "What type of product should we build?",
                        "options": [
                            {
                                "label": "SaaS dashboard",
                                "description": "Operational product with task lanes.",
                            }
                        ],
                        "multiSelect": False,
                        "recommendedIndex": 0,
                    }
                ],
                "runtime_sdk": "codex_sdk",
                "native_event": "item/tool/requestUserInput",
            },
        }
    ]
    assert process.stdin.messages[4] == {
        "id": "question-1",
        "result": {"answers": {"product_type": {"answers": ["SaaS dashboard"]}}},
    }
    assert result.observability is not None
    assert result.observability["request_user_input_count"] == 1


@pytest.mark.asyncio
async def test_codex_app_server_runtime_maps_provider_limit_output(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )
    limit_text = (
        "You've hit your usage limit. To get more access now, send a request to "
        "your administrator."
    )
    process = _FakeProcess(
        [
            {"id": 1, "result": {"userAgent": "codex-test"}},
            {"id": 2, "result": {"thread": {"id": "thread-limit"}}},
            {
                "id": 3,
                "result": {"turn": {"id": "turn-limit", "status": "inProgress"}},
            },
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "thread-limit",
                    "turnId": "turn-limit",
                    "itemId": "item-limit",
                    "delta": limit_text,
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-limit",
                    "turn": {"id": "turn-limit", "status": "completed", "error": None},
                },
            },
        ]
    )

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return process

    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    runtime = CodexAppServerRuntime(model="gpt-5.5")
    result = await runtime.run("Do the work", agent="chat", workspace_path=str(tmp_path))

    assert result.error is None
    assert result.stop_reason == "provider_limit"
    assert result.hit_capability_limit is True
    assert result.provider_limit is not None
    assert result.provider_limit["source"] == "codex_sdk"


@pytest.mark.asyncio
async def test_codex_app_server_runtime_retries_chunking_process_error(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )
    calls: list[int] = []
    process_results = [
        _FakeProcess(
            [
                {"id": 1, "result": {"userAgent": "codex-test"}},
                {"id": 2, "result": {"thread": {"id": "thread-first"}}},
                {
                    "id": 3,
                    "result": {"turn": {"id": "turn-first", "status": "inProgress"}},
                },
                {
                    "method": "item/agentMessage/delta",
                    "params": {
                        "threadId": "thread-first",
                        "turnId": "turn-first",
                        "itemId": "item-first",
                        "delta": "Separator is not found, and chunk exceed the limit",
                    },
                },
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "thread-first",
                        "turn": {"id": "turn-first", "status": "completed", "error": None},
                    },
                },
            ]
        ),
        _FakeProcess(
            [
                {"id": 1, "result": {"userAgent": "codex-test"}},
                {"id": 2, "result": {"thread": {"id": "thread-second"}}},
                {
                    "id": 3,
                    "result": {"turn": {"id": "turn-second", "status": "inProgress"}},
                },
                {
                    "method": "item/agentMessage/delta",
                    "params": {
                        "threadId": "thread-second",
                        "turnId": "turn-second",
                        "itemId": "item-second",
                        "delta": "Recovered",
                    },
                },
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "thread-second",
                        "turn": {"id": "turn-second", "status": "completed", "error": None},
                    },
                },
            ]
        ),
    ]

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        calls.append(1)
        return process_results.pop(0)

    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    runtime = CodexAppServerRuntime(model="gpt-5.5")
    result = await runtime.run("Do the work", agent="designer", workspace_path=str(tmp_path))

    assert result.success is True
    assert result.output == "Recovered"
    assert result.session_id == "thread-second"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_codex_app_server_runtime_fails_idle_turn_without_hanging(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime._TURN_EVENT_IDLE_TIMEOUT_SECONDS",
        0.01,
    )
    process = _IdleProcess(
        [
            {"id": 1, "result": {"userAgent": "codex-test"}},
            {"id": 2, "result": {"thread": {"id": "thread-idle"}}},
            {
                "id": 3,
                "result": {"turn": {"id": "turn-idle", "status": "inProgress"}},
            },
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "thread-idle",
                    "turnId": "turn-idle",
                    "itemId": "item-idle",
                    "delta": "Created files",
                },
            },
        ]
    )

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return process

    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    runtime = CodexAppServerRuntime(model="gpt-5.5")
    result = await runtime.run("Do the work", agent="code-gen", workspace_path=str(tmp_path))

    assert result.error is not None
    assert "turn idle timeout" in result.error
    assert result.session_id == "thread-idle"
    assert process.terminated is True


@pytest.mark.asyncio
async def test_codex_app_server_runtime_accepts_output_when_process_closes_after_message(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )
    process = _FakeProcess(
        [
            {"id": 1, "result": {"userAgent": "codex-test"}},
            {"id": 2, "result": {"thread": {"id": "thread-closed"}}},
            {
                "id": 3,
                "result": {"turn": {"id": "turn-closed", "status": "inProgress"}},
            },
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "thread-closed",
                    "turnId": "turn-closed",
                    "itemId": "item-closed",
                    "delta": '{"status":"pass","browser_evidence":["today list visible"]}',
                },
            },
        ],
        stderr=(
            '{"level":"WARN","fields":{"message":"ignoring interface.defaultPrompt"}}\n'
            '{"level":"ERROR","name":"BatchSpanProcessor.Flush.ExportError"}'
        ),
    )

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return process

    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    runtime = CodexAppServerRuntime(model="gpt-5.5")
    result = await runtime.run("Do the work", agent="feature-verifier", workspace_path=str(tmp_path))

    assert result.success is True
    assert result.stop_reason == "process_closed_after_output"
    assert "today list visible" in result.output
