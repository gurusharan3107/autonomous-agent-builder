from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

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
async def test_codex_app_server_runtime_routes_command_approvals_to_permission_callback(
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
            {"id": 2, "result": {"thread": {"id": "thread-approval"}}},
            {
                "id": 3,
                "result": {"turn": {"id": "turn-approval", "status": "inProgress"}},
            },
            {
                "id": 4,
                "method": "item/commandExecution/requestApproval",
                "params": {
                    "threadId": "thread-approval",
                    "turnId": "turn-approval",
                    "itemId": "cmd-approval",
                    "startedAtMs": 1778900000000,
                    "command": "rg -n overdue src test",
                    "cwd": str(tmp_path),
                    "commandActions": [{"type": "read", "command": "rg", "path": str(tmp_path)}],
                    "reason": "inspect repo",
                },
            },
            {
                "method": "item/agentMessage/delta",
                "params": {"delta": "Scoped without shell output."},
            },
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "tokenUsage": {
                        "last": {
                            "inputTokens": 25,
                            "cachedInputTokens": 20,
                            "outputTokens": 5,
                            "totalTokens": 30,
                        }
                    }
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-approval",
                    "turn": {"id": "turn-approval", "status": "completed", "error": None},
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
    permission_calls: list[tuple[str, dict[str, Any]]] = []

    class Deny:
        behavior = "deny"
        message = "No shell tools in feature scoping."

    async def can_use_tool(tool_name: str, input_data: dict[str, Any], _context: dict[str, Any]):
        permission_calls.append((tool_name, input_data))
        return Deny()

    runtime = CodexAppServerRuntime(model="gpt-5.5")
    result = await runtime.run(
        "Scope this improvement",
        agent="chat",
        workspace_path=str(tmp_path),
        approval_policy="on-request",
        can_use_tool=can_use_tool,
    )

    assert result.success is True
    assert process.stdin.messages[3]["params"]["approvalPolicy"] == "on-request"
    approval_response = next(message for message in process.stdin.messages if message.get("id") == 4)
    assert approval_response["result"]["decision"] == "decline"
    assert len(permission_calls) == 1
    tool_name, input_data = permission_calls[0]
    assert tool_name == "Bash"
    assert input_data["command"] == "rg -n overdue src test"
    assert input_data["cwd"] == str(tmp_path)
    assert input_data["command_actions"] == [
        {"type": "read", "command": "rg", "path": str(tmp_path)}
    ]
    assert input_data["reason"] == "inspect repo"
    assert input_data["approval"]["itemId"] == "cmd-approval"
    assert input_data["runtime_sdk"] == "codex_sdk"
    assert input_data["native_event"] == "item/commandExecution/requestApproval"


@pytest.mark.asyncio
async def test_codex_app_server_runtime_artifacts_large_command_output(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )
    large_output = "large-output-line\n" * 3000
    process = _FakeProcess(
        [
            {"id": 1, "result": {"userAgent": "codex-test"}},
            {"id": 2, "result": {"thread": {"id": "thread-large"}}},
            {
                "id": 3,
                "result": {"turn": {"id": "turn-large", "status": "inProgress"}},
            },
            {
                "method": "item/commandExecution/outputDelta",
                "params": {
                    "threadId": "thread-large",
                    "turnId": "turn-large",
                    "itemId": "cmd-1",
                    "delta": large_output,
                },
            },
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "thread-large",
                    "turnId": "turn-large",
                    "itemId": "msg-1",
                    "delta": "Done",
                },
            },
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "tokenUsage": {
                        "last": {
                            "inputTokens": 100,
                            "cachedInputTokens": 80,
                            "outputTokens": 5,
                            "reasoningOutputTokens": 0,
                            "totalTokens": 105,
                        }
                    }
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-large",
                    "turn": {"id": "turn-large", "status": "completed", "error": None},
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

    assert result.success is True
    observability = result.observability or {}
    optimization = observability["optimization_summary"]
    assert "large_command_output" not in optimization["avoidable_cost_flags"]
    assert optimization["event_accounting"]["largest_command_output_bytes"] < len(large_output)
    retention = observability["context_retention"]
    assert retention["resume_recommended"] is False
    assert "truncate_tool_output_before_reinjection" in retention["reinject_policy"]
    reinjection = observability["tool_output_reinjection"]
    assert reinjection["policy"] == "truncate_tool_output_before_reinjection"
    assert reinjection["status"] == "compacted"
    assert reinjection["largest_original_command_output_bytes"] >= len(large_output)
    assert "builder metrics show --json" in reinjection["bounded_retrieval_shortcut"]
    artifacts = observability["large_output_artifacts"]
    assert artifacts["count"] == 1
    artifact_path = Path(artifacts["artifact_path"])
    assert artifact_path.exists()
    artifact_text = artifact_path.read_text(encoding="utf-8")
    artifact_record = json.loads(artifact_text.splitlines()[0])
    assert artifact_record["event"]["params"]["delta"] == large_output
    command_event = next(
        event
        for event in (result.raw_events or [])
        if event.get("method") == "item/commandExecution/outputDelta"
    )
    compact_delta = command_event["params"]["delta"]
    assert "Builder compacted a large Codex command output" in compact_delta
    assert artifacts["artifact_relative_path"] in compact_delta
    assert large_output not in json.dumps(result.raw_events)


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
async def test_codex_app_server_runtime_retries_chunk_limit_in_fresh_thread(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )
    first_process = _FakeProcess(
        [
            {"id": 1, "result": {"userAgent": "codex-test"}},
            {"id": 2, "result": {"thread": {"id": "thread-bloated"}}},
            {
                "id": 3,
                "result": {"turn": {"id": "turn-bloated", "status": "inProgress"}},
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-bloated",
                    "turn": {
                        "id": "turn-bloated",
                        "status": "failed",
                        "error": "Separator is not found, and chunk exceed the limit",
                    },
                },
            },
        ]
    )
    second_process = _FakeProcess(
        [
            {"id": 1, "result": {"userAgent": "codex-test"}},
            {"id": 2, "result": {"thread": {"id": "thread-fresh"}}},
            {"id": 3, "result": {"turn": {"id": "turn-fresh", "status": "inProgress"}}},
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "thread-fresh",
                    "turnId": "turn-fresh",
                    "itemId": "item-fresh",
                    "delta": "Use bounded retrieval before reading large logs.",
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-fresh",
                    "turn": {"id": "turn-fresh", "status": "completed", "error": None},
                },
            },
        ]
    )
    processes = [first_process, second_process]

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return processes.pop(0)

    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    runtime = CodexAppServerRuntime(model="gpt-5.5")
    result = await runtime.run(
        "What should be optimized next?",
        agent="chat",
        workspace_path=str(tmp_path),
        session="thread-existing",
    )

    assert result.success is True
    assert result.session_id == "thread-fresh"
    assert result.output == "Use bounded retrieval before reading large logs."
    assert first_process.stdin.messages[2]["method"] == "thread/resume"
    assert first_process.stdin.messages[2]["params"]["threadId"] == "thread-existing"
    assert second_process.stdin.messages[2]["method"] == "thread/start"
    assert second_process.stdin.messages[2]["params"]["persistExtendedHistory"] is False
    retry_text = second_process.stdin.messages[3]["params"]["input"][0]["text"]
    assert "transport chunk limit" in retry_text
    assert "do not call shell or file-reading tools on this retry" in retry_text
    assert "builder metrics show --json" in retry_text
    assert "builder logs --error --json" in retry_text
    assert "What should be optimized next?" in retry_text


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
@pytest.mark.parametrize(
    "chunk_error",
    [
        "Separator is not found, and chunk exceed the limit",
        "Separator is found, but chunk is longer than limit",
    ],
)
async def test_codex_app_server_runtime_retries_chunking_process_error(
    monkeypatch,
    tmp_path: Path,
    chunk_error: str,
):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )
    calls: list[int] = []
    first_process = _FakeProcess(
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
                    "delta": chunk_error,
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
    )
    second_process = _FakeProcess(
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
    )
    process_results = [first_process, second_process]

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
    first_turn = first_process.stdin.messages[3]["params"]["input"][0]["text"]
    retry_turn = second_process.stdin.messages[3]["params"]["input"][0]["text"]
    assert first_turn == "Do the work"
    assert "transport chunk limit" in retry_turn
    assert "prefer compact Builder JSON commands" in retry_turn
    assert "avoid raw or --full outputs" in retry_turn
    assert "Never run raw, --full, recursive, or broad file-listing commands" in retry_turn


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
async def test_codex_app_server_runtime_fails_request_response_timeout_before_thread(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime._REQUEST_RESPONSE_TIMEOUT_SECONDS",
        0.01,
    )
    process = _IdleProcess([{"id": 1, "result": {"userAgent": "codex-test"}}])

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return process

    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    runtime = CodexAppServerRuntime(model="gpt-5.5")
    result = await runtime.run(
        "Do I need to approve anything?",
        agent="chat",
        workspace_path=str(tmp_path),
    )

    assert result.error is not None
    assert "Codex app-server response timeout" in result.error
    assert "thread/start response" in result.error
    assert result.session_id is None
    assert process.terminated is True


@pytest.mark.asyncio
async def test_codex_app_server_runtime_fails_request_response_timeout_before_turn(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime._REQUEST_RESPONSE_TIMEOUT_SECONDS",
        0.01,
    )
    process = _IdleProcess(
        [
            {"id": 1, "result": {"userAgent": "codex-test"}},
            {"id": 2, "result": {"thread": {"id": "thread-timeout"}}},
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
        "Do I need to approve anything?",
        agent="chat",
        workspace_path=str(tmp_path),
    )

    assert result.error is not None
    assert "Codex app-server response timeout" in result.error
    assert "turn/start response" in result.error
    assert result.session_id == "thread-timeout"
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
    result = await runtime.run(
        "Do the work",
        agent="feature-verifier",
        workspace_path=str(tmp_path),
    )

    assert result.success is True
    assert result.stop_reason == "process_closed_after_output"
    assert "today list visible" in result.output


@pytest.mark.asyncio
async def test_codex_app_server_runtime_keeps_answer_when_turn_error_duplicates_output(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_app_server_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )
    answer = (
        "The next Builder optimization should be tool-output truncation before "
        "reinjection, with a paired bounded retrieval shortcut for repeated "
        "state lookups. Current evidence says the generated app is not the blocker."
    )
    process = _FakeProcess(
        [
            {"id": 1, "result": {"userAgent": "codex-test"}},
            {"id": 2, "result": {"thread": {"id": "thread-error-text"}}},
            {
                "id": 3,
                "result": {"turn": {"id": "turn-error-text", "status": "inProgress"}},
            },
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "thread-error-text",
                    "turnId": "turn-error-text",
                    "itemId": "item-error-text",
                    "delta": answer,
                },
            },
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "tokenUsage": {
                        "last": {
                            "inputTokens": 25,
                            "cachedInputTokens": 10,
                            "outputTokens": 15,
                            "reasoningOutputTokens": 0,
                            "totalTokens": 40,
                        }
                    }
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-error-text",
                    "turn": {
                        "id": "turn-error-text",
                        "status": "completed",
                        "error": answer,
                    },
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
        "What should be optimized next?",
        agent="chat",
        workspace_path=str(tmp_path),
    )

    assert result.success is True
    assert result.error is None
    assert result.output == answer
    assert result.stop_reason == "completed"
    assert result.observability is not None
    assert result.observability["ignored_turn_error"] is True
