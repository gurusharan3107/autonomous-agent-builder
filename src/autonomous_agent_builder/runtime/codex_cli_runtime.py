"""Codex CLI runtime adapter.

Codex CLI is the OpenAI-side coding-agent harness for subscription-auth local
builder runs. It is intentionally separate from OpenAI Agents SDK because the
CLI owns workspace access, shell execution, sandboxing, approvals, and session
state.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from autonomous_agent_builder.runtime.interface import (
    AgentRuntime,
    RunResult,
    RuntimeCapabilities,
    RuntimeProbeResult,
)
from autonomous_agent_builder.services.codex_subscription_env import codex_subscription_env
from autonomous_agent_builder.services.provider_limits import (
    is_provider_limit_text,
    parse_reset_hint,
)


class CodexCliRuntime(AgentRuntime):
    """Run agents through `codex exec` using Codex CLI auth/session state."""

    def __init__(
        self,
        model: str | None = None,
        *,
        provider: str | None = None,
        sdk_name: str = "codex_cli",
        codex_profile: str | None = None,
        sandbox_mode: str = "workspace-write",
        approval_policy: str = "never",
    ):
        if sdk_name == "codex_sdk":
            raise ValueError("codex_sdk uses CodexAppServerRuntime; use codex_cli for codex exec.")
        self._model = model or "gpt-5.5"
        self._provider = provider or "codex_subscription"
        self._sdk_name = sdk_name
        self._codex_profile = codex_profile
        self._sandbox_mode = sandbox_mode
        self._approval_policy = approval_policy

    @property
    def name(self) -> str:
        return self._sdk_name

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return self._provider

    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            chat=True,
            streaming=True,
            tools=True,
            mcp=True,
            subagents=True,
            workspace_access=True,
            shell=True,
            sandboxing=True,
            approvals=True,
            session_resume=True,
            subscription_auth=True,
            api_key_auth=False,
            model_listing=False,
            provider_limit_detection=True,
            tracing=False,
        )

    async def run(
        self,
        input: str,
        *,
        agent: str,
        workspace_path: str | None = None,
        tools: list[str] | None = None,
        session: str | None = None,
        max_turns: int = 30,
        max_budget: float = 5.0,
        effort: str | None = None,
        approval_policy: str | None = None,
        on_chunk: Callable[[str], Any] | None = None,
        subagents: tuple[str, ...] | None = None,
        can_use_tool: Callable[..., Any] | None = None,
        on_tool_event: Callable[..., Any] | None = None,
    ) -> RunResult:
        """Execute a non-interactive Codex CLI turn."""
        if self._provider != "codex_subscription":
            return RunResult(
                error=(
                    f"{self.name} only supports provider=codex_subscription, got {self._provider}."
                ),
                stop_reason="configuration_error",
            )
        if shutil.which("codex") is None:
            return RunResult(
                error="Codex CLI not found on PATH.",
                stop_reason="configuration_error",
            )

        workspace = Path(workspace_path or Path.cwd()).resolve()
        attempts = 2
        for attempt in range(attempts):
            with tempfile.NamedTemporaryFile(
                prefix="aab-codex-",
                suffix=".txt",
                delete=False,
            ) as output_file:
                output_path = Path(output_file.name)

            cmd = self._build_command(
                prompt=input,
                workspace_path=workspace,
                output_path=output_path,
                session=session,
                effort=effort,
            )
            raw_events: list[dict[str, Any]] = []
            stream_parts: list[str] = []
            stderr_text = ""
            started_at = time.monotonic()
            duration_ms = 0

            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(workspace),
                    env=codex_subscription_env(),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                assert process.stdout is not None
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace").strip()
                    if not text:
                        continue
                    event = _loads_json_event(text)
                    if event is None:
                        stream_parts.append(text)
                        await _emit_chunk(on_chunk, text)
                        continue
                    raw_events.append(event)
                    delta = _event_delta(event)
                    if delta:
                        stream_parts.append(delta)
                        await _emit_chunk(on_chunk, delta)

                stderr_bytes = b""
                if process.stderr is not None:
                    stderr_bytes = await process.stderr.read()
                stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
                returncode = await process.wait()
                duration_ms = max(int((time.monotonic() - started_at) * 1000), 0)
            except asyncio.CancelledError:
                if "process" in locals():
                    process.kill()
                    await process.communicate()
                raise
            except Exception as exc:
                return RunResult(error=str(exc), stop_reason="process_error", raw_events=raw_events)
            finally:
                final_output = _read_output_file(output_path)
                with suppress(OSError):
                    output_path.unlink(missing_ok=True)

            session_id = _event_session_id(raw_events)
            event_error = _event_error(raw_events)
            metrics = _event_usage_metrics(raw_events)
            observability = self._observability(
                raw_events,
                metrics=metrics,
                effort=effort,
                duration_ms=duration_ms,
                session_id=session_id,
            )
            final_output = (
                final_output or _event_final_output(raw_events) or "".join(stream_parts).strip()
            )
            error_text = event_error or stderr_text
            if returncode != 0:
                if (
                    attempt == 0
                    and not is_provider_limit_text(error_text)
                    and _is_retryable_codex_process_error(error_text)
                ):
                    continue
                return self._error_result(
                    error_text or f"codex exec exited with status {returncode}",
                    session_id=session_id,
                    raw_events=raw_events,
                    duration_ms=duration_ms,
                    metrics=metrics,
                    observability=observability,
                )
            if error_text and is_provider_limit_text(error_text):
                return self._error_result(
                    error_text,
                    session_id=session_id,
                    raw_events=raw_events,
                    duration_ms=duration_ms,
                    metrics=metrics,
                    observability=observability,
                )
            if event_error:
                return RunResult(
                    session_id=session_id,
                    output=final_output,
                    error=event_error,
                    stop_reason="runtime_error",
                    tokens_input=metrics["input_tokens"],
                    tokens_output=metrics["output_tokens"],
                    tokens_cached=metrics["cached_input_tokens"],
                    num_turns=metrics["turns"],
                    duration_ms=duration_ms,
                    observability=observability,
                    raw_events=raw_events,
                )

            return RunResult(
                session_id=session_id,
                output=final_output,
                tokens_input=metrics["input_tokens"],
                tokens_output=metrics["output_tokens"],
                tokens_cached=metrics["cached_input_tokens"],
                num_turns=metrics["turns"],
                duration_ms=duration_ms,
                stop_reason=_event_stop_reason(raw_events) or "completed",
                observability=observability,
                raw_events=raw_events,
            )

        return RunResult(
            error="Codex CLI failed without returning a process result.",
            stop_reason="process_error",
        )

    def _build_command(
        self,
        *,
        prompt: str,
        workspace_path: Path,
        output_path: Path,
        session: str | None,
        effort: str | None,
    ) -> list[str]:
        effort_args = _reasoning_effort_args(effort)
        if session:
            cmd = [
                "codex",
                "exec",
                "resume",
                "--json",
                "--model",
                self._model,
                "--config",
                f'sandbox_mode="{self._sandbox_mode}"',
                "--config",
                f'approval_policy="{self._approval_policy}"',
                *effort_args,
                "--output-last-message",
                str(output_path),
                session,
                prompt,
            ]
            return cmd

        cmd = [
            "codex",
            "exec",
            "--json",
            "--cd",
            str(workspace_path),
            "--model",
            self._model,
            "--sandbox",
            self._sandbox_mode,
            "--config",
            f'approval_policy="{self._approval_policy}"',
            *effort_args,
            "--output-last-message",
            str(output_path),
            prompt,
        ]
        if self._codex_profile:
            cmd[2:2] = ["--profile", self._codex_profile]
        return cmd

    def _error_result(
        self,
        text: str,
        *,
        session_id: str | None,
        raw_events: list[dict[str, Any]],
        duration_ms: int = 0,
        metrics: dict[str, int] | None = None,
        observability: dict[str, Any] | None = None,
    ) -> RunResult:
        metrics = metrics or _event_usage_metrics(raw_events)
        result_kwargs = {
            "tokens_input": metrics["input_tokens"],
            "tokens_output": metrics["output_tokens"],
            "tokens_cached": metrics["cached_input_tokens"],
            "num_turns": metrics["turns"],
            "duration_ms": duration_ms,
            "observability": observability,
            "raw_events": raw_events,
        }
        if is_provider_limit_text(text):
            reset_at, reset_hint = parse_reset_hint(text)
            return RunResult(
                session_id=session_id,
                output=text,
                stop_reason="provider_limit",
                provider_limit={
                    "code": "provider_limit",
                    "reason": f"{self.name}_limit",
                    "reset_at": reset_at.isoformat() if reset_at else None,
                    "reset_hint": reset_hint,
                    "source": self.name,
                },
                **result_kwargs,
            )
        stop_reason = "auth_error" if _looks_like_auth_error(text) else "process_error"
        if _looks_like_sandbox_error(text):
            stop_reason = "sandbox_error"
        return RunResult(error=text, stop_reason=stop_reason, **result_kwargs)

    def _observability(
        self,
        events: list[dict[str, Any]],
        *,
        metrics: dict[str, int],
        effort: str | None,
        duration_ms: int,
        session_id: str | None,
    ) -> dict[str, Any]:
        event_types = [_event_kind(event) for event in events if _event_kind(event)]
        telemetry_source = "codex_cli_jsonl"
        return {
            "runtime_sdk": self.name,
            "provider": self._provider,
            "model": self._model,
            "effort": effort,
            "telemetry_source": telemetry_source,
            "protocol": "codex_exec_jsonl",
            "session_id": session_id,
            "turns": metrics["turns"],
            "input_tokens": metrics["input_tokens"],
            "output_tokens": metrics["output_tokens"],
            "cached_input_tokens": metrics["cached_input_tokens"],
            "reasoning_output_tokens": metrics["reasoning_output_tokens"],
            "total_tokens": metrics["input_tokens"] + metrics["output_tokens"],
            "duration_ms": duration_ms,
            "raw_event_count": len(events),
            "event_types": sorted(set(event_types)),
            "cost_source": "subscription_unmetered",
        }

    async def shutdown(self) -> None:
        pass

    async def health_check(self) -> bool:
        return shutil.which("codex") is not None

    async def probe(self) -> RuntimeProbeResult:
        codex_path = shutil.which("codex")
        if codex_path is None:
            return RuntimeProbeResult(
                ok=False,
                sdk=self.name,
                provider=self._provider,
                model=self._model,
                code=f"{self.name}_missing",
                message="Codex CLI was not found on PATH.",
                next=(
                    "Install Codex CLI, run `codex login`, then retry "
                    "`builder agent runtime probe --json`."
                ),
                capabilities=self.capabilities(),
            )
        version = await _codex_version()
        return RuntimeProbeResult(
            ok=True,
            sdk=self.name,
            provider=self._provider,
            model=self._model,
            code=f"{self.name}_available",
            message=(
                "Codex CLI is available. ChatGPT subscription auth is managed by `codex login`."
            ),
            next=(
                f"Run `builder agent runtime set --sdk {self.name} "
                "--provider codex_subscription --json` to activate."
            ),
            capabilities=self.capabilities(),
            detail={"codex_path": codex_path, "version": version},
        )


def _reasoning_effort_args(effort: str | None) -> list[str]:
    normalized = str(effort or "").strip().lower()
    if normalized not in {"minimal", "low", "medium", "high", "xhigh"}:
        return []
    return ["--config", f'model_reasoning_effort="{normalized}"']


async def _emit_chunk(callback: Callable[[str], Any] | None, text: str) -> None:
    if callback is None:
        return
    result = callback(text)
    if hasattr(result, "__await__"):
        await result


def _loads_json_event(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _event_kind(event: dict[str, Any]) -> str:
    return str(event.get("type") or event.get("event") or event.get("kind") or "").lower()


def _event_delta(event: dict[str, Any]) -> str:
    kind = _event_kind(event)
    for key in ("delta", "text_delta"):
        value = event.get(key)
        if isinstance(value, str):
            return value
    if "delta" in kind or kind.endswith(".delta"):
        return _string_from_keys(event, ("text", "content", "output"))
    return ""


def _event_final_output(events: list[dict[str, Any]]) -> str:
    final = ""
    for event in events:
        kind = _event_kind(event)
        if kind in {"final_output", "task_complete", "response.completed", "agent_message"}:
            final = _string_from_keys(event, ("output", "text", "content", "message")) or final
        for key in ("final_output", "final", "output_text"):
            value = event.get(key)
            if isinstance(value, str) and value.strip():
                final = value
    return final.strip()


def _event_session_id(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        for key in ("session_id", "sessionId", "conversation_id", "thread_id", "threadId"):
            value = event.get(key)
            if isinstance(value, str) and value.strip():
                return value
        session = event.get("session")
        if isinstance(session, dict):
            value = session.get("id") or session.get("session_id")
            if isinstance(value, str) and value.strip():
                return value
    return None


def _event_stop_reason(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        for key in ("stop_reason", "finish_reason", "reason"):
            value = event.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def _event_usage_metrics(events: list[dict[str, Any]]) -> dict[str, int]:
    metrics = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "reasoning_output_tokens": 0,
        "turns": 0,
    }
    for event in events:
        if _event_kind(event).endswith("turn.completed"):
            metrics["turns"] += 1
        usage = _event_usage(event)
        if not usage:
            continue
        metrics["input_tokens"] += _int_from_usage(
            usage,
            "input_tokens",
            "prompt_tokens",
        )
        metrics["output_tokens"] += _int_from_usage(
            usage,
            "output_tokens",
            "completion_tokens",
        )
        metrics["cached_input_tokens"] += _int_from_usage(
            usage,
            "cached_input_tokens",
            "cached_tokens",
            "cache_read_input_tokens",
        )
        metrics["reasoning_output_tokens"] += _int_from_usage(
            usage,
            "reasoning_output_tokens",
            "reasoning_tokens",
        )
    return metrics


def _event_usage(event: dict[str, Any]) -> dict[str, Any]:
    for key in ("usage", "token_usage", "tokens"):
        value = event.get(key)
        if isinstance(value, dict):
            return value
    for key in ("payload", "turn", "response", "metadata"):
        value = event.get(key)
        if not isinstance(value, dict):
            continue
        for usage_key in ("usage", "token_usage", "tokens"):
            usage = value.get(usage_key)
            if isinstance(usage, dict):
                return usage
    return {}


def _int_from_usage(usage: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return max(value, 0)
        if isinstance(value, float):
            return max(int(value), 0)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return 0


def _event_error(events: list[dict[str, Any]]) -> str:
    for event in events:
        kind = _event_kind(event)
        if "error" not in kind and "error" not in event:
            continue
        error = event.get("error")
        if isinstance(error, str):
            return error
        if isinstance(error, dict):
            return _string_from_keys(error, ("message", "detail", "error"))
        return _string_from_keys(event, ("message", "detail", "text"))
    return ""


def _string_from_keys(event: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = event.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            nested = _string_from_keys(value, ("text", "content", "message", "output"))
            if nested:
                return nested
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    nested = _string_from_keys(item, ("text", "content", "message", "output"))
                    if nested:
                        parts.append(nested)
            if parts:
                return "".join(parts)
    return ""


def _read_output_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


async def _codex_version() -> str:
    try:
        process = await asyncio.create_subprocess_exec(
            "codex",
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await process.communicate()
    except Exception:
        return ""
    return stdout.decode("utf-8", errors="replace").strip()


def _looks_like_auth_error(text: str) -> bool:
    lower = text.lower()
    fragments = ("not logged in", "login", "authentication", "auth")
    return any(fragment in lower for fragment in fragments)


def _looks_like_sandbox_error(text: str) -> bool:
    lower = text.lower()
    return "sandbox" in lower or "permission denied" in lower


def _is_retryable_codex_process_error(text: str) -> bool:
    lower = text.lower()
    return ("separator is not found" in lower and "chunk exceed" in lower) or (
        "separator is found" in lower and "chunk is longer than limit" in lower
    )
