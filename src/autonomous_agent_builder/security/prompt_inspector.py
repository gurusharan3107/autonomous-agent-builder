"""Prompt injection detection — two-layer defense via hooks.

Layer 1 (PreToolUse): Scan tool INPUTS for injection patterns before execution.
Catches cases where the agent was already influenced by prior injection.

Layer 2 (PostToolUse): Scan tool OUTPUT for injection patterns after execution.
Detects injections entering the agent context via tool output.

SDK limitation: PostToolUse cannot replace tool output, so Layer 2 injects a
systemMessage warning the agent to ignore injected instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass(frozen=True)
class InspectionResult:
    """Result of prompt injection inspection."""

    severity: str  # HIGH, MEDIUM, LOW
    pattern_name: str  # which pattern matched
    matched_text: str  # the offending text (truncated)
    reason: str  # human-readable explanation


# Tiered patterns — HIGH blocks, MEDIUM warns+logs, LOW logs only
# Extract long patterns as variables to stay within line length limits
_FORGET_PATTERN = (
    r"(?i)forget\s+(?:everything|all|your)(?:\s+your)?\s+"
    r"(instructions|rules|constraints)"
)
_EXFIL_PATTERN = (
    r"(?i)send\s+(this|the|all)\s+(data|content|file|secret)\s+to"
)

_INJECTION_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # HIGH: Direct instruction override (check more specific patterns first)
    (re.compile(r"(?i)system\s*:\s*you\s+are"), "HIGH", "system_prompt_inject"),
    (re.compile(r"(?i)ignore\s+(all\s+)?previous\s+instructions"), "HIGH", "instruction_override"),
    (re.compile(r"(?i)you\s+are\s+now\s+"), "HIGH", "identity_hijack"),
    (re.compile(_FORGET_PATTERN), "HIGH", "constraint_erase"),
    (re.compile(r"(?i)write\s+to\s+file\s+/etc/"), "HIGH", "system_file_write"),
    (re.compile(_EXFIL_PATTERN), "HIGH", "exfiltration_attempt"),
    # MEDIUM: Suspicious tool manipulation
    (re.compile(r"(?i)execute\s+this\s+command"), "MEDIUM", "command_injection"),
    (re.compile(r"(?i)run\s+the\s+following\s+(bash|shell|command)"), "MEDIUM", "shell_injection"),
    (re.compile(r"(?i)curl\s+.*\s+-d\s+"), "MEDIUM", "data_post"),
    # LOW: Informational
    (re.compile(r"(?i)base64\s+encode"), "LOW", "encoding_detected"),
]


async def inspect_tool_output(
    tool_name: str,
    tool_output: Any,
) -> InspectionResult | None:
    """Scan tool output text for injection patterns. Returns None if clean."""
    text = _extract_text(tool_output)
    if not text:
        return None

    for pattern, severity, name in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            return InspectionResult(
                severity=severity,
                pattern_name=name,
                matched_text=match.group()[:200],
                reason=f"Prompt injection pattern '{name}' detected in {tool_name} output",
            )

    return None


async def inspect_tool_input(
    tool_name: str,
    tool_input: dict[str, Any],
) -> InspectionResult | None:
    """Scan tool input for injection patterns. Returns None if clean."""
    for key, value in tool_input.items():
        if isinstance(value, str):
            text = value
        else:
            continue

        for pattern, severity, name in _INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                return InspectionResult(
                    severity=severity,
                    pattern_name=name,
                    matched_text=match.group()[:200],
                    reason=f"Prompt injection pattern '{name}' detected in {tool_name} {key}",
                )

    return None


def _extract_text(tool_output: Any) -> str:
    """Extract text from tool output for inspection."""
    if isinstance(tool_output, str):
        return tool_output

    if isinstance(tool_output, dict):
        if "content" in tool_output:
            content = tool_output["content"]
            if isinstance(content, list) and content:
                if isinstance(content[0], dict) and "text" in content[0]:
                    return content[0]["text"]
            elif isinstance(content, str):
                return content

        if "text" in tool_output:
            return tool_output["text"]

        # Fallback: stringify dict
        return str(tool_output)

    if isinstance(tool_output, list):
        # Flatten list of strings
        parts = [str(item) for item in tool_output]
        return " ".join(parts)

    return ""
