from __future__ import annotations

import json
from pathlib import Path

import pytest

from autonomous_agent_builder.runtime.codex_cli_runtime import CodexCliRuntime


class _FakeStream:
    def __init__(self, lines: list[str]):
        self._lines = [line.encode("utf-8") for line in lines]

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)

    async def read(self) -> bytes:
        value = b"".join(self._lines)
        self._lines = []
        return value


class _FakeProcess:
    def __init__(self, *, stdout: list[str], stderr: str = "", returncode: int = 0):
        self.stdout = _FakeStream(stdout)
        self.stderr = _FakeStream([stderr] if stderr else [])
        self.returncode = returncode
        self.killed = False

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self.killed = True

    async def communicate(self):
        return b"", b""


@pytest.mark.asyncio
async def test_codex_cli_run_builds_subscription_command_and_parses_jsonl(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_cli_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )
    captured: dict[str, object] = {}

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["cwd"] = kwargs["cwd"]
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text("Final answer", encoding="utf-8")
        return _FakeProcess(
            stdout=[
                json.dumps({"type": "session.created", "session_id": "sess-123"}) + "\n",
                json.dumps({"type": "response.delta", "delta": "streamed"}) + "\n",
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 111,
                            "cached_input_tokens": 22,
                            "output_tokens": 33,
                            "reasoning_output_tokens": 4,
                        },
                    }
                )
                + "\n",
            ]
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_cli_runtime.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    chunks: list[str] = []
    runtime = CodexCliRuntime(model="gpt-5.5", codex_profile="builder")
    result = await runtime.run(
        "Do the work",
        agent="planner",
        workspace_path=str(tmp_path),
        effort="high",
        on_chunk=chunks.append,
    )

    cmd = captured["cmd"]
    assert result.success is True
    assert result.output == "Final answer"
    assert result.session_id == "sess-123"
    assert chunks == ["streamed"]
    assert captured["cwd"] == str(tmp_path)
    assert cmd[:3] == ["codex", "exec", "--profile"]
    assert "--json" in cmd
    assert "--cd" in cmd
    assert "--model" in cmd
    assert "gpt-5.5" in cmd
    assert "--sandbox" in cmd
    assert "workspace-write" in cmd
    assert 'approval_policy="never"' in cmd
    assert 'model_reasoning_effort="high"' in cmd
    assert "--output-last-message" in cmd
    assert result.tokens_input == 111
    assert result.tokens_output == 33
    assert result.tokens_cached == 22
    assert result.num_turns == 1
    assert result.observability is not None
    assert result.observability["runtime_sdk"] == "codex_cli"
    assert result.observability["telemetry_source"] == "codex_cli_jsonl"
    assert result.observability["reasoning_output_tokens"] == 4
    assert result.observability["cost_source"] == "subscription_unmetered"


@pytest.mark.asyncio
async def test_codex_cli_provider_limit_maps_to_capability_limit(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_cli_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return _FakeProcess(
            stdout=[],
            stderr="rate limit reached, resets in 1 hour",
            returncode=1,
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_cli_runtime.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    runtime = CodexCliRuntime(model="gpt-5.5")
    result = await runtime.run("Do the work", agent="planner", workspace_path=str(tmp_path))

    assert result.error is None
    assert result.stop_reason == "provider_limit"
    assert result.hit_capability_limit is True
    assert result.provider_limit is not None
    assert result.provider_limit["source"] == "codex_cli"


@pytest.mark.asyncio
async def test_codex_cli_usage_limit_event_maps_to_provider_limit(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_cli_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return _FakeProcess(
            stdout=[
                json.dumps({"type": "thread.started", "thread_id": "thread-limit"}) + "\n",
                json.dumps(
                    {
                        "type": "error",
                        "error": (
                            "You've hit your usage limit. Upgrade to Plus to continue "
                            "using Codex, or try again at May 8th, 2026 12:02 PM."
                        ),
                    }
                )
                + "\n",
                json.dumps(
                    {
                        "type": "turn.failed",
                        "error": {
                            "message": (
                                "You've hit your usage limit. Upgrade to Plus to continue "
                                "using Codex, or try again at May 8th, 2026 12:02 PM."
                            )
                        },
                    }
                )
                + "\n",
            ],
            returncode=1,
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_cli_runtime.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    runtime = CodexCliRuntime(model="gpt-5.5")
    result = await runtime.run("Do the work", agent="planner", workspace_path=str(tmp_path))

    assert result.error is None
    assert result.stop_reason == "provider_limit"
    assert result.provider_limit is not None
    assert result.provider_limit["source"] == "codex_cli"
    assert result.provider_limit["reset_at"] == "2026-05-08T12:02:00+00:00"


@pytest.mark.asyncio
async def test_codex_cli_uses_codex_jsonl_telemetry(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_cli_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text("SDK answer", encoding="utf-8")
        return _FakeProcess(
            stdout=[
                json.dumps({"type": "thread.started", "thread_id": "thread-1"}) + "\n",
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 10,
                            "output_tokens": 5,
                        },
                    }
                )
                + "\n",
            ]
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_cli_runtime.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    runtime = CodexCliRuntime(model="gpt-5.5")
    result = await runtime.run("Do the work", agent="planner", workspace_path=str(tmp_path))

    assert result.success is True
    assert result.session_id == "thread-1"
    assert result.tokens_input == 10
    assert result.tokens_output == 5
    assert result.observability is not None
    assert result.observability["runtime_sdk"] == "codex_cli"
    assert result.observability["telemetry_source"] == "codex_cli_jsonl"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chunk_error",
    [
        "Separator is not found, and chunk exceed the limit",
        "Separator is found, but chunk is longer than limit",
    ],
)
async def test_codex_cli_retries_retryable_chunking_process_error(
    monkeypatch,
    tmp_path: Path,
    chunk_error: str,
):
    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_cli_runtime.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )
    calls: list[list[str]] = []

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        calls.append(list(cmd))
        if len(calls) == 1:
            return _FakeProcess(
                stdout=[],
                stderr=chunk_error,
                returncode=1,
            )
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text("Recovered", encoding="utf-8")
        return _FakeProcess(stdout=[])

    monkeypatch.setattr(
        "autonomous_agent_builder.runtime.codex_cli_runtime.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    runtime = CodexCliRuntime(model="gpt-5.5")
    result = await runtime.run("Do the work", agent="pr-creator", workspace_path=str(tmp_path))

    assert result.success is True
    assert result.output == "Recovered"
    assert len(calls) == 2
