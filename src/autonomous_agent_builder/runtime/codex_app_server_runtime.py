"""Codex app-server runtime adapter.

This adapter uses the local `codex app-server` JSON-RPC transport. It is the
deep-integration Codex path: Codex CLI login owns auth, while app-server exposes
thread state, streamed events, token usage, approvals, and structured
`tool/requestUserInput` requests.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from autonomous_agent_builder.agents.runner import capture_workspace_diff
from autonomous_agent_builder.runtime.interface import (
    AgentRuntime,
    RunResult,
    RuntimeCapabilities,
    RuntimeProbeResult,
)
from autonomous_agent_builder.services.codex_optimization import (
    LARGE_OUTPUT_BYTES,
    codex_run_optimization_summary,
)
from autonomous_agent_builder.services.codex_subscription_env import codex_subscription_env
from autonomous_agent_builder.services.provider_limits import (
    is_provider_limit_text,
    parse_reset_hint,
)

_TURN_EVENT_IDLE_TIMEOUT_SECONDS = 120.0
_REQUEST_RESPONSE_TIMEOUT_SECONDS = 30.0
_COMPACT_OUTPUT_PREVIEW_CHARS = 1600
_COMMAND_OUTPUT_KEYS = ("output", "text", "content", "stdout", "stderr", "delta")
_BOUNDED_RETRIEVAL_SHORTCUT = (
    "Bounded retrieval shortcut: prefer compact Builder JSON commands. Start with "
    "`builder metrics show --json` and "
    "`builder logs --error --json`; use `builder logs --info --compact --json` for "
    "status context, and only run `builder logs analyze --session <id-or-prefix> --json` "
    "for one selected run; avoid raw or --full outputs unless the compact evidence is "
    "insufficient."
)


class CodexAppServerRuntime(AgentRuntime):
    """Run Codex through app-server JSON-RPC with native interaction events."""

    def __init__(
        self,
        model: str | None = None,
        *,
        provider: str | None = None,
        codex_profile: str | None = None,
        sandbox_mode: str = "workspace-write",
        approval_policy: str = "never",
    ):
        self._model = model or "gpt-5.5"
        self._provider = provider or "codex_subscription"
        self._codex_profile = codex_profile
        self._sandbox_mode = sandbox_mode
        self._approval_policy = approval_policy

    @property
    def name(self) -> str:
        return "codex_sdk"

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
            native_user_input=True,
            mcp_elicitations=True,
            request_permissions=True,
            app_server_events=True,
            token_usage_stream=True,
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
        """Execute a Codex app-server turn with one retry for known transport chunking failures."""
        attempts = 2
        last_result: RunResult | None = None
        turn_input = input
        for attempt in range(attempts):
            retrying_after_chunk_limit = attempt > 0 and last_result is not None
            result = await self._run_once(
                turn_input,
                agent=agent,
                workspace_path=workspace_path,
                tools=tools,
                session=None if retrying_after_chunk_limit else session,
                max_turns=max_turns,
                max_budget=max_budget,
                effort=effort,
                approval_policy=approval_policy,
                on_chunk=on_chunk,
                subagents=subagents,
                can_use_tool=can_use_tool,
                on_tool_event=on_tool_event,
            )
            last_result = result
            if attempt == 0 and result.error and _is_retryable_codex_process_error(result.error):
                turn_input = _chunk_limit_retry_prompt(input)
                continue
            return result
        return last_result or RunResult(
            error="Codex app-server failed without returning a process result.",
            stop_reason="process_error",
        )

    async def _run_once(
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
        """Execute a Codex app-server turn."""
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
        raw_events: list[dict[str, Any]] = []
        output_parts: list[str] = []
        latest_usage: dict[str, int] = {}
        request_user_input_count = 0
        started_at = time.monotonic()
        thread_id: str | None = None

        process = await self._start_process()
        stderr_task = None
        try:
            assert process.stdin is not None
            assert process.stdout is not None
            if process.stderr is not None:
                stderr_task = asyncio.create_task(process.stderr.read())

            seq = _RequestSeq()
            await _send(
                process,
                {
                    "id": seq.next(),
                    "method": "initialize",
                    "params": {
                        "clientInfo": {
                            "name": "autonomous_agent_builder",
                            "title": "Autonomous Agent Builder",
                            "version": "0.1.0",
                        },
                        "capabilities": {"experimentalApi": True},
                    },
                },
            )
            init_response = await _read_until_response(
                process,
                raw_events,
                1,
                operation="initialize",
                timeout_seconds=_REQUEST_RESPONSE_TIMEOUT_SECONDS,
            )
            init_error = _response_error(init_response)
            if init_error:
                return self._error_result(init_error, None, raw_events, started_at)

            await _send(process, {"method": "initialized", "params": {}})

            thread_method = "thread/resume" if session else "thread/start"
            thread_params = self._thread_params(workspace, session=session)
            thread_request_id = seq.next()
            await _send(
                process,
                {"id": thread_request_id, "method": thread_method, "params": thread_params},
            )
            thread_response = await _read_until_response(
                process,
                raw_events,
                thread_request_id,
                operation=thread_method,
                timeout_seconds=_REQUEST_RESPONSE_TIMEOUT_SECONDS,
            )
            thread_error = _response_error(thread_response)
            if thread_error:
                return self._error_result(thread_error, None, raw_events, started_at)
            thread_id = _nested_string(thread_response, ("result", "thread", "id")) or session
            if not thread_id:
                return self._error_result(
                    "Codex app-server did not return a thread id.",
                    None,
                    raw_events,
                    started_at,
                )

            turn_request_id = seq.next()
            await _send(
                process,
                {
                    "id": turn_request_id,
                    "method": "turn/start",
                    "params": self._turn_params(
                        thread_id,
                        input,
                        workspace,
                        effort,
                        approval_policy=approval_policy,
                    ),
                },
            )
            turn_response = await _read_until_response(
                process,
                raw_events,
                turn_request_id,
                operation="turn/start",
                timeout_seconds=_REQUEST_RESPONSE_TIMEOUT_SECONDS,
            )
            turn_error = _response_error(turn_response)
            if turn_error:
                return self._error_result(turn_error, thread_id, raw_events, started_at)
            while True:
                try:
                    message = await _read_message(
                        process,
                        timeout_seconds=_TURN_EVENT_IDLE_TIMEOUT_SECONDS,
                    )
                except TimeoutError:
                    return self._error_result(
                        (
                            "Codex app-server turn idle timeout: no JSON-RPC event arrived "
                            f"for {_TURN_EVENT_IDLE_TIMEOUT_SECONDS:.0f}s while waiting for "
                            "turn/completed."
                        ),
                        thread_id,
                        raw_events,
                        started_at,
                        metrics=latest_usage,
                    )
                raw_events.append(message)
                if "id" in message and "method" in message:
                    method = str(message.get("method") or "")
                    if method == "item/tool/requestUserInput":
                        request_user_input_count += 1
                        await self._handle_request_user_input(process, message, can_use_tool)
                    elif method == "item/commandExecution/requestApproval":
                        await self._handle_command_execution_approval(
                            process,
                            message,
                            can_use_tool,
                        )
                    elif method == "item/fileChange/requestApproval":
                        await self._handle_file_change_approval(
                            process,
                            message,
                            can_use_tool,
                        )
                    else:
                        await _send(
                            process,
                            {
                                "id": message.get("id"),
                                "error": {
                                    "code": -32000,
                                    "message": f"Unsupported Codex server request: {method}",
                                },
                            },
                        )
                    continue

                method = str(message.get("method") or "")
                params = message.get("params") if isinstance(message.get("params"), dict) else {}
                if method == "item/agentMessage/delta":
                    delta = str(params.get("delta") or "")
                    if delta:
                        output_parts.append(delta)
                        if on_chunk is not None:
                            maybe_await = on_chunk(delta)
                            if hasattr(maybe_await, "__await__"):
                                await maybe_await
                elif method in {"item/started", "item/completed"}:
                    await _emit_codex_item_event(on_tool_event, method, params)
                    item = params.get("item") if isinstance(params.get("item"), dict) else {}
                    if method == "item/completed" and item.get("type") == "agentMessage":
                        text = str(item.get("text") or "")
                        if text:
                            output_parts = [text]
                elif "thinking" in method.lower() or "reason" in method.lower():
                    await _emit_codex_item_event(on_tool_event, method, params)
                elif method == "thread/tokenUsage/updated":
                    latest_usage = _usage_from_token_event(params)
                elif method == "turn/completed":
                    break

            duration_ms = int((time.monotonic() - started_at) * 1000)
            final_output = "".join(output_parts).strip()
            completed = _last_turn_completed(raw_events)
            turn_error = _turn_error(completed)
            large_output_artifacts = _materialize_large_command_output_artifacts(
                workspace,
                raw_events,
                session_id=thread_id,
            )
            result_events = _compact_large_command_output_events(
                raw_events,
                large_output_artifacts,
            )
            observability = self._observability(
                result_events,
                metrics=latest_usage,
                agent_name=agent,
                prompt_text=input,
                output_text=final_output,
                status="completed",
                effort=effort,
                duration_ms=duration_ms,
                session_id=thread_id,
                request_user_input_count=request_user_input_count,
                large_output_artifacts=large_output_artifacts,
            )
            if turn_error:
                if final_output and _turn_error_duplicates_output(turn_error, final_output):
                    return RunResult(
                        session_id=thread_id,
                        output=final_output,
                        tokens_input=latest_usage.get("input_tokens", 0),
                        tokens_output=latest_usage.get("output_tokens", 0),
                        tokens_cached=latest_usage.get("cached_input_tokens", 0),
                        num_turns=1,
                        duration_ms=duration_ms,
                        stop_reason=_turn_status(completed) or "completed_with_turn_error_text",
                        diff_summary=capture_workspace_diff(str(workspace)),
                        observability={
                            **observability,
                            "status": "completed_with_turn_error_text",
                            "ignored_turn_error": True,
                        },
                        raw_events=result_events,
                    )
                return self._error_result(
                    turn_error,
                    thread_id,
                    result_events,
                    started_at,
                    observability=observability,
                    metrics=latest_usage,
                )
            if _is_retryable_codex_process_error(final_output):
                return self._error_result(
                    final_output,
                    thread_id,
                    result_events,
                    started_at,
                    observability=observability,
                    metrics=latest_usage,
                )
            if is_provider_limit_text(final_output):
                return self._error_result(
                    final_output,
                    thread_id,
                    result_events,
                    started_at,
                    observability=observability,
                    metrics=latest_usage,
                )
            return RunResult(
                session_id=thread_id,
                output=final_output,
                tokens_input=latest_usage.get("input_tokens", 0),
                tokens_output=latest_usage.get("output_tokens", 0),
                tokens_cached=latest_usage.get("cached_input_tokens", 0),
                num_turns=1,
                duration_ms=duration_ms,
                stop_reason=_turn_status(completed) or "completed",
                diff_summary=capture_workspace_diff(str(workspace)),
                observability=observability,
                raw_events=result_events,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            final_output = "".join(output_parts).strip()
            if final_output and _is_process_closed_after_output_error(exc):
                large_output_artifacts = _materialize_large_command_output_artifacts(
                    workspace,
                    raw_events,
                    session_id=thread_id,
                )
                result_events = _compact_large_command_output_events(
                    raw_events,
                    large_output_artifacts,
                )
                return RunResult(
                    session_id=thread_id,
                    output=final_output,
                    tokens_input=latest_usage.get("input_tokens", 0),
                    tokens_output=latest_usage.get("output_tokens", 0),
                    tokens_cached=latest_usage.get("cached_input_tokens", 0),
                    num_turns=1,
                    duration_ms=duration_ms,
                    stop_reason="process_closed_after_output",
                    diff_summary=capture_workspace_diff(str(workspace)),
                    observability=self._observability(
                        result_events,
                        metrics=latest_usage,
                        agent_name=agent,
                        prompt_text=input,
                        output_text=final_output,
                        status="completed_with_transport_close",
                        effort=effort,
                        duration_ms=duration_ms,
                        session_id=thread_id,
                        request_user_input_count=request_user_input_count,
                        large_output_artifacts=large_output_artifacts,
                    ),
                    raw_events=result_events,
                )
            stderr_text = _compact_runtime_stderr(await _stderr_text(stderr_task))
            text = str(exc)
            if stderr_text:
                text = f"{text}; stderr: {stderr_text}"
            return self._error_result(
                text,
                thread_id,
                raw_events,
                started_at,
                duration_ms=duration_ms,
            )
        finally:
            await _shutdown_process(process)

    async def _start_process(self) -> asyncio.subprocess.Process:
        cmd = [
            "codex",
            "app-server",
            "--listen",
            "stdio://",
            "--enable",
            "default_mode_request_user_input",
        ]
        if self._codex_profile:
            cmd.extend(["--config", f'profile="{self._codex_profile}"'])
        return await asyncio.create_subprocess_exec(
            *cmd,
            env=codex_subscription_env(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    def _thread_params(self, workspace: Path, *, session: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {
            "cwd": str(workspace),
            "model": self._model,
            "approvalPolicy": self._approval_policy,
            "sandbox": _sandbox_mode(self._sandbox_mode),
            "persistExtendedHistory": bool(session),
        }
        if session:
            params["threadId"] = session
        return params

    def _turn_params(
        self,
        thread_id: str,
        prompt: str,
        workspace: Path,
        effort: str | None,
        approval_policy: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "threadId": thread_id,
            "input": [{"type": "text", "text": prompt}],
            "cwd": str(workspace),
            "model": self._model,
            "approvalPolicy": approval_policy or self._approval_policy,
            "sandboxPolicy": _sandbox_policy(self._sandbox_mode, workspace),
        }
        normalized_effort = _reasoning_effort(effort)
        if normalized_effort:
            params["effort"] = normalized_effort
        return params

    async def _handle_request_user_input(
        self,
        process: asyncio.subprocess.Process,
        message: dict[str, Any],
        can_use_tool: Callable[..., Any] | None,
    ) -> None:
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        questions = _builder_questions(params.get("questions"))
        answers_by_id: dict[str, dict[str, list[str]]] = {}
        if can_use_tool is None:
            for question in params.get("questions", []) or []:
                if isinstance(question, dict):
                    answers_by_id[str(question.get("id") or question.get("question") or "")] = {
                        "answers": []
                    }
        else:
            permission = await can_use_tool(
                "request_user_input",
                {
                    "questions": questions,
                    "runtime_sdk": self.name,
                    "native_event": "item/tool/requestUserInput",
                },
                {},
            )
            updated_input = getattr(permission, "updated_input", None) or getattr(
                permission, "updatedInput", None
            )
            answer_map = {}
            if isinstance(updated_input, dict):
                raw_answers = updated_input.get("answers", {})
                if isinstance(raw_answers, dict):
                    answer_map = {str(k): str(v) for k, v in raw_answers.items()}
            for raw_question in params.get("questions", []) or []:
                if not isinstance(raw_question, dict):
                    continue
                qid = str(raw_question.get("id") or raw_question.get("question") or "")
                question_text = str(raw_question.get("question") or "")
                answer = answer_map.get(question_text) or answer_map.get(qid) or ""
                answers_by_id[qid] = {"answers": [answer] if answer else []}

        await _send(
            process,
            {"id": message.get("id"), "result": {"answers": answers_by_id}},
        )

    async def _handle_command_execution_approval(
        self,
        process: asyncio.subprocess.Process,
        message: dict[str, Any],
        can_use_tool: Callable[..., Any] | None,
    ) -> None:
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        decision = "decline"
        if can_use_tool is not None:
            permission = await can_use_tool(
                "Bash",
                {
                    "command": params.get("command") or "",
                    "cwd": params.get("cwd") or "",
                    "command_actions": params.get("commandActions") or [],
                    "reason": params.get("reason") or "",
                    "approval": params,
                    "runtime_sdk": self.name,
                    "native_event": "item/commandExecution/requestApproval",
                },
                {},
            )
            if _permission_allows(permission):
                decision = "accept"
        await _send(process, {"id": message.get("id"), "result": {"decision": decision}})

    async def _handle_file_change_approval(
        self,
        process: asyncio.subprocess.Process,
        message: dict[str, Any],
        can_use_tool: Callable[..., Any] | None,
    ) -> None:
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        decision = "decline"
        if can_use_tool is not None:
            permission = await can_use_tool(
                "Edit",
                {
                    "grant_root": params.get("grantRoot") or "",
                    "reason": params.get("reason") or "",
                    "approval": params,
                    "runtime_sdk": self.name,
                    "native_event": "item/fileChange/requestApproval",
                },
                {},
            )
            if _permission_allows(permission):
                decision = "accept"
        await _send(process, {"id": message.get("id"), "result": {"decision": decision}})

    def _error_result(
        self,
        text: str,
        session_id: str | None,
        raw_events: list[dict[str, Any]],
        started_at: float,
        *,
        duration_ms: int | None = None,
        metrics: dict[str, int] | None = None,
        observability: dict[str, Any] | None = None,
    ) -> RunResult:
        duration = (
            duration_ms if duration_ms is not None else int((time.monotonic() - started_at) * 1000)
        )
        metrics = metrics or {}
        observability = observability or self._observability(
            raw_events,
            metrics=metrics,
            effort=None,
            duration_ms=duration,
            session_id=session_id,
            request_user_input_count=0,
        )
        result_kwargs = {
            "session_id": session_id,
            "tokens_input": metrics.get("input_tokens", 0),
            "tokens_output": metrics.get("output_tokens", 0),
            "tokens_cached": metrics.get("cached_input_tokens", 0),
            "num_turns": metrics.get("turns", 0),
            "duration_ms": duration,
            "observability": observability,
            "raw_events": raw_events,
        }
        if is_provider_limit_text(text):
            reset_at, reset_hint = parse_reset_hint(text)
            return RunResult(
                output=text,
                stop_reason="provider_limit",
                provider_limit={
                    "code": "provider_limit",
                    "reason": "codex_sdk_limit",
                    "reset_at": reset_at.isoformat() if reset_at else None,
                    "reset_hint": reset_hint,
                    "source": self.name,
                },
                **result_kwargs,
            )
        return RunResult(error=text, stop_reason=_error_stop_reason(text), **result_kwargs)

    def _observability(
        self,
        events: list[dict[str, Any]],
        *,
        metrics: dict[str, int],
        effort: str | None,
        duration_ms: int,
        session_id: str | None,
        request_user_input_count: int,
        agent_name: str = "",
        prompt_text: str = "",
        output_text: str = "",
        status: str = "completed",
        prompt_budget: dict[str, Any] | None = None,
        large_output_artifacts: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event_types = [_message_type(event) for event in events if _message_type(event)]
        optimization_summary = codex_run_optimization_summary(
            events=events,
            metrics=metrics,
            agent_name=agent_name,
            prompt_text=prompt_text,
            output_text=output_text,
            status=status,
            prompt_budget=prompt_budget,
        )
        payload = {
            "runtime_sdk": self.name,
            "provider": self._provider,
            "model": self._model,
            "effort": effort,
            "telemetry_source": "codex_app_server_events",
            "protocol": "codex_app_server_jsonrpc",
            "session_id": session_id,
            "turns": metrics.get("turns", 1 if session_id else 0),
            "input_tokens": metrics.get("input_tokens", 0),
            "output_tokens": metrics.get("output_tokens", 0),
            "cached_input_tokens": metrics.get("cached_input_tokens", 0),
            "reasoning_output_tokens": metrics.get("reasoning_output_tokens", 0),
            "total_tokens": metrics.get("total_tokens", 0),
            "duration_ms": duration_ms,
            "raw_event_count": len(events),
            "event_types": sorted(set(event_types)),
            "request_user_input_count": request_user_input_count,
            "native_user_input": True,
            "mcp_elicitations": True,
            "request_permissions": True,
            "cost_source": "subscription_unmetered",
            "optimization_summary": optimization_summary,
        }
        if large_output_artifacts and large_output_artifacts.get("count"):
            payload["large_output_artifacts"] = large_output_artifacts
            payload["tool_output_reinjection"] = {
                "policy": "truncate_tool_output_before_reinjection",
                "status": "compacted",
                "artifact_count": large_output_artifacts.get("count", 0),
                "largest_original_command_output_bytes": large_output_artifacts.get(
                    "largest_command_output_bytes",
                    0,
                ),
                "runtime_event_stream": "compact_previews_only",
                "bounded_retrieval_shortcut": _BOUNDED_RETRIEVAL_SHORTCUT,
            }
            payload["context_retention"] = {
                "resume_recommended": False,
                "reason": "large_command_output_artifact",
                "reinject_policy": (
                    "truncate_tool_output_before_reinjection;"
                    "full_command_output_stored_as_builder_artifact;"
                    "runtime_events_return_compact_previews"
                ),
                "artifact_path": large_output_artifacts.get("artifact_path", ""),
                "event_count": large_output_artifacts.get("count", 0),
                "largest_command_output_bytes": large_output_artifacts.get(
                    "largest_command_output_bytes",
                    0,
                ),
            }
        return payload

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
                code="codex_sdk_missing",
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
            code="codex_sdk_available",
            message=(
                "Codex app-server is available. ChatGPT subscription auth is managed by "
                "`codex login`."
            ),
            next=(
                "Run a dashboard Agent-page turn to exercise native Codex "
                "`tool/requestUserInput` and app-server telemetry."
            ),
            capabilities=self.capabilities(),
            detail={"codex_path": codex_path, "version": version},
        )


class _RequestSeq:
    def __init__(self) -> None:
        self.value = 0

    def next(self) -> int:
        self.value += 1
        return self.value


def _materialize_large_command_output_artifacts(
    workspace: Path,
    events: list[dict[str, Any]],
    *,
    session_id: str | None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    largest_command_output_bytes = 0
    for index, event in enumerate(events):
        command_output_bytes = _command_output_text_size(event)
        largest_command_output_bytes = max(largest_command_output_bytes, command_output_bytes)
        if command_output_bytes < LARGE_OUTPUT_BYTES:
            continue
        records.append(
            {
                "event_index": index,
                "method": str(event.get("method") or ""),
                "command_output_bytes": command_output_bytes,
                "event_bytes": len(json.dumps(event, ensure_ascii=True, sort_keys=True)),
                "event": event,
            }
        )

    if not records:
        return {
            "count": 0,
            "largest_command_output_bytes": largest_command_output_bytes,
        }

    relative_path = (
        Path(".agent-builder")
        / "runtime-artifacts"
        / "codex-app-server"
        / f"{int(time.time() * 1000)}-{_safe_artifact_id(session_id)}-large-output.jsonl"
    )
    artifact_path = workspace / relative_path
    try:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            "\n".join(json.dumps(record, ensure_ascii=True, sort_keys=True) for record in records)
            + "\n",
            encoding="utf-8",
        )
        status = "stored"
        error = ""
    except Exception as exc:  # pragma: no cover - defensive evidence path
        status = "error"
        error = f"{type(exc).__name__}: {exc}"

    return {
        "count": len(records),
        "status": status,
        "artifact_path": str(artifact_path),
        "artifact_relative_path": str(relative_path),
        "largest_command_output_bytes": largest_command_output_bytes,
        "event_indices": [int(record["event_index"]) for record in records],
        "event_methods": [str(record["method"]) for record in records],
        "compacted_for_runtime_result": True,
        "error": error,
    }


def _compact_large_command_output_events(
    events: list[dict[str, Any]],
    artifact_metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    large_indices = {int(index) for index in artifact_metadata.get("event_indices", [])}
    if not large_indices:
        return events

    compacted: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        if index not in large_indices:
            compacted.append(event)
            continue
        event_copy = _json_copy(event)
        marker = _artifact_marker(event, artifact_metadata, event_index=index)
        if not _replace_command_output_text(event_copy, marker):
            event_copy["params"] = {
                "builder_compacted": True,
                "summary": marker,
                "original_method": str(event.get("method") or ""),
            }
        compacted.append(event_copy)
    return compacted


def _command_output_text_size(event: dict[str, Any]) -> int:
    text = _first_command_output_text(event)
    if text:
        return len(text)
    if not _is_command_output_event(event):
        return 0
    params = event.get("params") if isinstance(event.get("params"), dict) else {}
    return len(json.dumps(params, ensure_ascii=True, sort_keys=True))


def _first_command_output_text(event: dict[str, Any]) -> str:
    if not _is_command_output_event(event):
        return ""
    params = event.get("params") if isinstance(event.get("params"), dict) else {}
    item = params.get("item") if isinstance(params.get("item"), dict) else {}
    for container in (item, params):
        text = _first_text_value(container, _COMMAND_OUTPUT_KEYS)
        if text:
            return text
    return ""


def _is_command_output_event(event: dict[str, Any]) -> bool:
    method = str(event.get("method") or "")
    if "commandExecution" in method:
        return True
    params = event.get("params") if isinstance(event.get("params"), dict) else {}
    item = params.get("item") if isinstance(params.get("item"), dict) else {}
    item_type = str(item.get("type") or params.get("type") or "").lower()
    tool_name = str(
        item.get("name") or item.get("toolName") or item.get("tool_name") or item.get("title") or ""
    ).lower()
    haystack = f"{method.lower()} {item_type} {tool_name}"
    return any(marker in haystack for marker in ("command", "bash", "shell", "exec", "terminal"))


def _replace_command_output_text(event: dict[str, Any], marker: str) -> bool:
    params = event.get("params") if isinstance(event.get("params"), dict) else {}
    item = params.get("item") if isinstance(params.get("item"), dict) else {}
    replaced = False
    for container in (item, params):
        for key in _COMMAND_OUTPUT_KEYS:
            if key not in container:
                continue
            value = container.get(key)
            if isinstance(value, (str, dict, list)):
                container[key] = marker
                replaced = True
    return replaced


def _artifact_marker(
    event: dict[str, Any],
    artifact_metadata: dict[str, Any],
    *,
    event_index: int,
) -> str:
    text = _first_command_output_text(event)
    preview = _compact_event_text(text, limit=_COMPACT_OUTPUT_PREVIEW_CHARS) if text else ""
    path = str(
        artifact_metadata.get("artifact_relative_path")
        or artifact_metadata.get("artifact_path")
        or ""
    )
    size = _command_output_text_size(event)
    parts = [
        "Builder compacted a large Codex command output before returning runtime evidence.",
        f"artifact={path}#event-{event_index}",
        f"original_chars={size}",
    ]
    if preview:
        parts.append(f"preview={preview}")
    return " ".join(parts)


def _first_text_value(value: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        item = value.get(key)
        if isinstance(item, str):
            return item
        if isinstance(item, (dict, list)):
            return json.dumps(item, ensure_ascii=True, sort_keys=True)
    return ""


def _json_copy(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, ensure_ascii=True))


def _permission_allows(permission: Any) -> bool:
    behavior = str(
        getattr(permission, "behavior", "")
        or getattr(permission, "decision", "")
        or getattr(permission, "type", "")
        or ""
    ).lower()
    if behavior == "allow":
        return True
    return permission.__class__.__name__.lower().endswith("allow")


def _safe_artifact_id(value: str | None) -> str:
    raw = str(value or "unknown-thread")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in raw)
    safe = safe.strip("-_")[:80]
    return safe or "unknown-thread"


async def _send(process: asyncio.subprocess.Process, message: dict[str, Any]) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(message, ensure_ascii=True).encode("utf-8") + b"\n")
    await process.stdin.drain()


async def _emit_codex_item_event(
    on_tool_event: Callable[..., Any] | None,
    method: str,
    params: dict[str, Any],
) -> None:
    if on_tool_event is None:
        return
    item = params.get("item") if isinstance(params.get("item"), dict) else {}
    item_type = str(item.get("type") or params.get("type") or method).strip()
    lower = f"{method} {item_type}".lower()
    if "agentmessage" in lower:
        return
    event_type = "runtime_event"
    if "thinking" in lower or "reason" in lower:
        event_type = "thinking"
    elif "tool" in lower or "function" in lower or "command" in lower:
        event_type = "tool_use"
    elif method == "item/started":
        event_type = "runtime_item_started"
    elif method == "item/completed":
        event_type = "runtime_item_completed"
    tool_name = str(
        item.get("name")
        or item.get("toolName")
        or item.get("tool_name")
        or item.get("title")
        or item_type
        or method
    )
    preview = _compact_event_text(
        item.get("text")
        or item.get("output")
        or item.get("content")
        or params.get("delta")
        or params.get("text")
        or method
    )
    payload = item.get("input") if isinstance(item.get("input"), dict) else {}
    maybe_await = on_tool_event(
        event_type=event_type,
        tool_name=tool_name,
        tool_input=payload,
        output_preview=preview,
    )
    if hasattr(maybe_await, "__await__"):
        await maybe_await


async def _read_message(
    process: asyncio.subprocess.Process,
    *,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    assert process.stdout is not None
    if timeout_seconds is None:
        line = await process.stdout.readline()
    else:
        line = await asyncio.wait_for(process.stdout.readline(), timeout=timeout_seconds)
    if not line:
        raise RuntimeError("Codex app-server closed stdout.")
    return json.loads(line.decode("utf-8", errors="replace"))


async def _read_until_response(
    process: asyncio.subprocess.Process,
    raw_events: list[dict[str, Any]],
    request_id: int | str,
    *,
    operation: str,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    while True:
        try:
            message = await _read_message(process, timeout_seconds=timeout_seconds)
        except TimeoutError as exc:
            timeout_text = f" after {timeout_seconds:.0f}s" if timeout_seconds is not None else ""
            raise TimeoutError(
                f"Codex app-server response timeout{timeout_text} while waiting for "
                f"{operation} response."
            ) from exc
        raw_events.append(message)
        if message.get("id") == request_id and ("result" in message or "error" in message):
            return message


async def _shutdown_process(process: asyncio.subprocess.Process) -> None:
    with suppress(Exception):
        if process.stdin is not None:
            process.stdin.close()
    if process.returncode is None:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except TimeoutError:
            process.kill()
            with suppress(Exception):
                await process.wait()


async def _stderr_text(stderr_task: asyncio.Task[bytes] | None) -> str:
    if stderr_task is None:
        return ""
    if not stderr_task.done():
        stderr_task.cancel()
        with suppress(asyncio.CancelledError):
            await stderr_task
        return ""
    try:
        return stderr_task.result().decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def _response_error(message: dict[str, Any]) -> str:
    error = message.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or "")
    if isinstance(error, str):
        return error
    return ""


def _is_process_closed_after_output_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "closed stdout" in text or "expecting value" in text


def _compact_runtime_stderr(stderr_text: str, *, limit: int = 800) -> str:
    lines = []
    for line in str(stderr_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if (
            "ignoring interface." in lower
            or "batchspanprocessor.flush.exporterror" in lower
            or "failed during the export process" in lower
            or "opentelemetry_sdk" in lower
        ):
            continue
        lines.append(stripped)
    text = " ".join(lines)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _nested_string(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return str(current or "")


def _compact_event_text(value: Any, *, limit: int = 500) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=True, sort_keys=True)
    else:
        text = str(value or "")
    text = " ".join(text.strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _builder_questions(raw_questions: Any) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for raw in raw_questions or []:
        if not isinstance(raw, dict):
            continue
        questions.append(
            {
                "header": raw.get("header", ""),
                "question": raw.get("question", ""),
                "options": raw.get("options", []) or [],
                "multiSelect": False,
                "recommendedIndex": 0,
            }
        )
    return questions


def _usage_from_token_event(params: dict[str, Any]) -> dict[str, int]:
    usage = params.get("tokenUsage") if isinstance(params.get("tokenUsage"), dict) else {}
    last = usage.get("last") if isinstance(usage.get("last"), dict) else {}
    total = usage.get("total") if isinstance(usage.get("total"), dict) else {}
    source = last or total
    return {
        "input_tokens": _int(source.get("inputTokens")),
        "output_tokens": _int(source.get("outputTokens")),
        "cached_input_tokens": _int(source.get("cachedInputTokens")),
        "reasoning_output_tokens": _int(source.get("reasoningOutputTokens")),
        "total_tokens": _int(source.get("totalTokens")),
        "turns": 1,
    }


def _last_turn_completed(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        if event.get("method") == "turn/completed":
            params = event.get("params")
            return params if isinstance(params, dict) else {}
    return {}


def _turn_status(completed: dict[str, Any]) -> str:
    turn = completed.get("turn") if isinstance(completed.get("turn"), dict) else {}
    return str(turn.get("status") or "")


def _turn_error(completed: dict[str, Any]) -> str:
    turn = completed.get("turn") if isinstance(completed.get("turn"), dict) else {}
    error = turn.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("codexErrorInfo") or "")
    return str(error or "")


def _turn_error_duplicates_output(error: str, output: str) -> bool:
    normalized_error = " ".join(error.split())
    normalized_output = " ".join(output.split())
    if not normalized_error or not normalized_output:
        return False
    if normalized_error == normalized_output:
        return True
    return len(normalized_output) >= 120 and normalized_error in normalized_output


def _message_type(event: dict[str, Any]) -> str:
    if "method" in event:
        return str(event.get("method") or "")
    if "id" in event and "result" in event:
        return "response.result"
    if "id" in event and "error" in event:
        return "response.error"
    return ""


def _sandbox_mode(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"read-only", "readonly", "read_only"}:
        return "read-only"
    if normalized in {"danger-full-access", "danger_full_access", "dangerfullaccess"}:
        return "danger-full-access"
    return "workspace-write"


def _sandbox_policy(value: str, workspace: Path) -> dict[str, Any]:
    normalized = _sandbox_mode(value)
    if normalized == "read-only":
        return {"type": "readOnly", "networkAccess": False}
    if normalized == "danger-full-access":
        return {"type": "dangerFullAccess"}
    return {
        "type": "workspaceWrite",
        "writableRoots": [str(workspace)],
        "networkAccess": False,
    }


def _reasoning_effort(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"none", "minimal", "low", "medium", "high", "xhigh"}:
        return normalized
    return None


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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


def _error_stop_reason(text: str) -> str:
    lower = text.lower()
    if "not logged in" in lower or "login" in lower or "authentication" in lower:
        return "auth_error"
    if "sandbox" in lower or "permission denied" in lower:
        return "sandbox_error"
    return "runtime_error"


def _is_retryable_codex_process_error(text: str) -> bool:
    lower = text.lower()
    return ("separator is not found" in lower and "chunk exceed" in lower) or (
        "separator is found" in lower and "chunk is longer than limit" in lower
    )


def _chunk_limit_retry_prompt(prompt: str) -> str:
    return (
        f"{prompt}\n\n"
        "The previous Codex app-server attempt hit a transport chunk limit while "
        "handling this same operator request. Retry the request as a normal model "
        "turn, but keep tool usage bounded. If the request can be answered from "
        "the operator prompt plus compact Builder evidence, do not call shell or "
        "file-reading tools on this retry. "
        f"{_BOUNDED_RETRIEVAL_SHORTCUT} "
        "Never run raw, --full, recursive, or broad file-listing commands on the "
        "retry. Cap any necessary shell output to a small, command-specific window "
        "and summarize findings instead of pasting large logs or file contents."
    )
