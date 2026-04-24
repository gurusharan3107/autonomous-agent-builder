"""Claude runtime helpers for SDK-backed and optional CLI-backed helper lanes."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.onecli_runtime import prepare_onecli_runtime_env


@dataclass(frozen=True)
class ClaudeAvailability:
    available: bool
    backend: str
    message: str = ""


def _normalized_backend() -> str:
    backend = get_settings().agent.auth_backend.strip().lower()
    if backend not in {"auto", "cli", "sdk"}:
        return "auto"
    return backend


def resolve_claude_backend() -> str:
    """Resolve the Claude execution backend for the current environment."""
    backend = _normalized_backend()
    if backend != "auto":
        return backend
    if importlib.util.find_spec("claude_agent_sdk") is not None:
        return "sdk"
    return "cli" if shutil.which("claude") else "sdk"


async def check_claude_availability(
    workspace_path: Path,
    model: str,
    *,
    allowed_tools: list[str] | None = None,
    permission_mode: str | None = None,
) -> ClaudeAvailability:
    """Probe the configured Claude backend with a minimal prompt."""
    backend = resolve_claude_backend()
    probe_timeout = float(get_settings().agent.availability_probe_timeout_seconds)
    try:
        await asyncio.wait_for(
            run_claude_prompt(
                "Reply with exactly OK.",
                workspace_path=workspace_path,
                model=model,
                # Keep the availability probe tool-free so the CLI prompt cannot
                # be misparsed by variadic tool flags.
                allowed_tools=None,
                permission_mode=permission_mode,
                timeout_seconds=probe_timeout,
            ),
            timeout=probe_timeout,
        )
    except TimeoutError:
        return ClaudeAvailability(
            available=False,
            backend=backend,
            message=f"Claude availability probe timed out after {probe_timeout:g}s.",
        )
    except Exception as exc:
        return ClaudeAvailability(available=False, backend=backend, message=str(exc))
    return ClaudeAvailability(available=True, backend=backend)


def require_claude_available(
    workspace_path: Path,
    model: str,
    *,
    allowed_tools: list[str] | None = None,
    permission_mode: str | None = None,
) -> ClaudeAvailability:
    """Synchronous wrapper for availability probing."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        availability = asyncio.run(
            check_claude_availability(
                workspace_path=workspace_path,
                model=model,
                allowed_tools=allowed_tools,
                permission_mode=permission_mode,
            )
        )
        if not availability.available:
            raise RuntimeError(availability.message or "Claude is unavailable.") from None
        return availability
    raise RuntimeError(
        "require_claude_available() cannot run inside an active event loop; "
        "use `await check_claude_availability(...)` instead."
    )


async def run_claude_prompt(
    prompt: str,
    *,
    workspace_path: Path,
    model: str,
    allowed_tools: list[str] | None = None,
    permission_mode: str | None = None,
    timeout_seconds: float | None = None,
) -> str:
    """Execute a one-shot Claude prompt using the configured backend."""
    backend = resolve_claude_backend()
    timeout = timeout_seconds or float(get_settings().agent.query_timeout_seconds)
    runner = (
        _run_claude_cli_prompt
        if backend == "cli"
        else _run_claude_sdk_prompt
    )
    try:
        return await asyncio.wait_for(
            runner(
                prompt,
                workspace_path=workspace_path,
                model=model,
                allowed_tools=allowed_tools,
                permission_mode=permission_mode,
            ),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise RuntimeError(
            f"Claude {backend} prompt timed out after {timeout:g}s."
        ) from exc


async def _run_claude_cli_prompt(
    prompt: str,
    *,
    workspace_path: Path,
    model: str,
    allowed_tools: list[str] | None = None,
    permission_mode: str | None = None,
) -> str:
    if shutil.which("claude") is None:
        raise RuntimeError("Claude CLI is not installed or not on PATH.")

    command = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "text",
        "--model",
        model,
        "--permission-mode",
        permission_mode or get_settings().agent.permission_mode,
        "--permission-prompt-tool",
        "reject",
    ]

    if allowed_tools is not None:
        if allowed_tools:
            command.extend(["--tools", *allowed_tools])
        else:
            command.extend(["--tools", ""])
        if allowed_tools:
            command.extend(["--allowed-tools", *allowed_tools])

    onecli_env = await prepare_onecli_runtime_env()
    process_env = {**os.environ, **onecli_env.env} if onecli_env.active else None

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(workspace_path),
        env=process_env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await process.communicate()
    except asyncio.CancelledError:
        process.kill()
        await process.communicate()
        raise
    stdout_text = stdout.decode("utf-8", errors="replace").strip()
    stderr_text = stderr.decode("utf-8", errors="replace").strip()

    if process.returncode != 0:
        raise RuntimeError(stderr_text or stdout_text or "Claude CLI prompt failed.")
    if not stdout_text:
        raise RuntimeError("Claude CLI returned no output.")
    return stdout_text


async def _run_claude_sdk_prompt(
    prompt: str,
    *,
    workspace_path: Path,
    model: str,
    allowed_tools: list[str] | None = None,
    permission_mode: str | None = None,
) -> str:
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query

    onecli_env = await prepare_onecli_runtime_env()

    options = ClaudeAgentOptions(
        model=model,
        cwd=workspace_path,
        max_turns=5,
        allowed_tools=allowed_tools or [],
        permission_mode=permission_mode or get_settings().agent.permission_mode,
        env=onecli_env.env if onecli_env.active else {},
        # Prevent the spawned CLI from blocking on interactive permission prompts
        # when running headless (no TTY). "reject" is Claude CLI's built-in no-op handler.
        permission_prompt_tool_name="reject",
    )

    output_parts: list[str] = []
    error_result: str | None = None
    final_result: str | None = None

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                text = getattr(block, "text", None)
                if text:
                    output_parts.append(text)
        elif isinstance(message, ResultMessage):
            if message.is_error:
                error_result = message.result or "Claude SDK query failed."
            if message.result:
                final_result = message.result

    if error_result:
        raise RuntimeError(error_result)

    response = "\n".join(output_parts).strip() or (final_result or "").strip()
    if not response:
        raise RuntimeError("Claude SDK returned no output.")
    return response
