"""Egress monitor — audit network destinations from tool execution.

Extracts URLs, git remotes, S3 buckets, SSH targets, Docker pushes, and package
publishes from Bash command + output. Used for audit trail and compliance reporting.

Never blocks — audit only. Persists findings to SecurityFinding table via hook context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass(frozen=True)
class EgressDestination:
    """Network destination detected in tool execution."""

    kind: str  # url, git_remote, s3_bucket, ssh_target, docker_push, package_publish
    target: str  # the destination (hostname, URL, bucket)


_EGRESS_PATTERNS: dict[str, re.Pattern] = {
    "url": re.compile(r"(?i)(https?|ftp)://[^\s'\"<>|;&)]+"),
    "git_remote": re.compile(r"git@([^:]+):([^\s'\"]+)"),
    "s3_bucket": re.compile(r"s3://([^/\s'\"]+)"),
    "ssh_target": re.compile(r"ssh\s+(?:\S+@)?([a-zA-Z0-9][\w.-]+)"),
    "docker_push": re.compile(r"docker\s+push\s+([^\s'\"]+)"),
    "package_publish": re.compile(r"\b(npm publish|cargo publish|twine upload)\b"),
}


def extract_egress_destinations(command: str, output: str) -> list[EgressDestination]:
    """Extract network destinations from Bash command + output."""
    destinations = []

    for text in (command, output):
        if not text:
            continue

        for kind, pattern in _EGRESS_PATTERNS.items():
            for match in pattern.finditer(text):
                target = match.group()[:500]
                destinations.append(EgressDestination(kind=kind, target=target))

    return destinations


async def log_egress_destinations(
    input: dict[str, Any],
    tool_use_id: str | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    """PostToolUse hook: log network destinations for audit. Never blocks.

    SDK signature: (input: PostToolUseHookInput, tool_use_id, context: HookContext)
    """
    try:
        tool_name = input.get("tool_name", "")

        # Only monitor Bash tool for egress
        if tool_name != "Bash":
            return {}

        tool_input = input.get("tool_input", {})
        command = tool_input.get("command", "")
        tool_response = input.get("tool_response", "")
        output_text = _extract_text_from_response(tool_response)

        destinations = extract_egress_destinations(command, output_text)

        for dest in destinations:
            log.info(
                "egress_detected",
                kind=dest.kind,
                destination=dest.target,
                tool_use_id=tool_use_id,
                tool="Bash",
            )

        # Optionally persist to DB if context provides access
        if destinations and "persist_security_finding" in context:
            persist_fn = context["persist_security_finding"]
            for dest in destinations:
                await persist_fn(
                    finding_type="egress",
                    severity="INFO",
                    tool_name="Bash",
                    pattern=dest.kind,
                    context_preview=dest.target[:500],
                )

        return {}  # never blocks — audit only
    except Exception as e:
        log.error("hook_error", hook="egress_monitor", error=str(e))
        return {}


def _extract_text_from_response(tool_response: Any) -> str:
    """Extract text from tool response for egress pattern matching."""
    if isinstance(tool_response, str):
        return tool_response

    if isinstance(tool_response, dict):
        if "content" in tool_response:
            content = tool_response["content"]
            if isinstance(content, list) and content:
                if isinstance(content[0], dict) and "text" in content[0]:
                    return content[0]["text"]
            elif isinstance(content, str):
                return content

        if "text" in tool_response:
            return tool_response["text"]

    if isinstance(tool_response, list):
        parts = [str(item) for item in tool_response]
        return " ".join(parts)

    return ""
