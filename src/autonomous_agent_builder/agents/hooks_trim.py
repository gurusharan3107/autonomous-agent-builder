"""PostToolUse output-trim hook (G12).

Truncates large outputs from a curated set of noisy tools (Bash, Read, MCP
run_tests / run_linter) before the model re-reads them, while
`audit_log_tool_use` still records the full output for telemetry.
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()

_OUTPUT_TRIM_TOOLS = frozenset(
    {"Bash", "Read", "mcp__workspace__run_tests", "mcp__workspace__run_linter"}
)
_OUTPUT_TRIM_CHARS = 8_000


def _trim_bounded(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    marker = f"\n... ({len(text)} chars, trimmed by context hook)\n"
    head = max_chars // 2
    tail = max_chars - head - len(marker)
    return text[:head] + marker + text[-max(tail, 0) :], True


async def trim_tool_output_for_context(
    input: dict[str, Any],
    tool_use_id: str | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    """PostToolUse hook: truncate large outputs from noisy tools before model re-read.

    Targets a curated set only. _post_tool_audit still logs the full output.
    Returns updatedToolOutput / updatedMCPToolOutput only when truncation fires.
    SDK contract: for built-in Bash, updatedToolOutput must match
    {"stdout": ..., "stderr": ..., "interrupted": ...}.
    """
    tool_name = input.get("tool_name", "")
    if tool_name not in _OUTPUT_TRIM_TOOLS:
        return {}
    tool_response = input.get("tool_response")
    if not tool_response:
        return {}
    try:
        if tool_name.startswith("mcp__"):
            if isinstance(tool_response, dict):
                content = tool_response.get("content", [])
                if isinstance(content, list):
                    trimmed_content, was_trimmed = [], False
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            bounded, cut = _trim_bounded(item.get("text", ""), _OUTPUT_TRIM_CHARS)
                            trimmed_content.append({"type": "text", "text": bounded})
                            was_trimmed = was_trimmed or cut
                        else:
                            trimmed_content.append(item)
                    if was_trimmed:
                        return {
                            "hookSpecificOutput": {
                                "hookEventName": "PostToolUse",
                                "updatedMCPToolOutput": {
                                    **tool_response,
                                    "content": trimmed_content,
                                },
                            }
                        }
        else:
            if isinstance(tool_response, dict) and "stdout" in tool_response:
                stdout = str(tool_response.get("stdout", ""))
                bounded_stdout, cut = _trim_bounded(stdout, _OUTPUT_TRIM_CHARS)
                if cut:
                    stderr = str(tool_response.get("stderr", ""))
                    bounded_stderr, _ = _trim_bounded(stderr, 1000)
                    return {
                        "hookSpecificOutput": {
                            "hookEventName": "PostToolUse",
                            "updatedToolOutput": {
                                **tool_response,
                                "stdout": bounded_stdout,
                                "stderr": bounded_stderr,
                            },
                        }
                    }
            elif isinstance(tool_response, str):
                bounded, cut = _trim_bounded(tool_response, _OUTPUT_TRIM_CHARS)
                if cut:
                    return {
                        "hookSpecificOutput": {
                            "hookEventName": "PostToolUse",
                            "updatedToolOutput": bounded,
                        }
                    }
    except Exception as e:
        log.error("hook_error", hook="trim_tool_output_for_context", error=str(e))
    return {}
