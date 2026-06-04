"""Post-ship optimization CLI probe helpers.

Module-level functions extracted from Orchestrator for the CLI telemetry
probing and probe-summary logic used during post-ship optimization.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


def _json_object(text: str) -> dict[str, Any]:
    import json

    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


async def _post_ship_optimization_cli_probe(
    orchestrator: Any,
    project_root: Path,
) -> list[dict[str, str]]:
    """Run builder CLI telemetry/log probes before choosing the optimization action."""

    commands: list[tuple[str, list[str]]] = [
        (
            "builder metrics show --json --full",
            [
                sys.executable,
                "-m",
                "autonomous_agent_builder.cli.main",
                "metrics",
                "show",
                "--json",
                "--full",
            ],
        ),
        (
            "builder logs --info --compact --json",
            [
                sys.executable,
                "-m",
                "autonomous_agent_builder.cli.main",
                "logs",
                "--info",
                "--compact",
                "--json",
            ],
        ),
        (
            "builder logs analyze --session <latest-session> --json",
            [
                sys.executable,
                "-m",
                "autonomous_agent_builder.cli.main",
                "logs",
                "analyze",
                "--json",
            ],
        ),
    ]
    timeline: list[dict[str, str]] = []
    for label, argv in commands:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        payload = _json_object(stdout.decode(errors="replace"))
        summary = _post_ship_probe_summary(orchestrator, label, proc.returncode, payload)
        if proc.returncode != 0 and not summary:
            summary = stderr.decode(errors="replace").strip()[:180] or "command failed"
        timeline.append(
            {
                "command": label,
                "result": "pass" if proc.returncode == 0 else "fail",
                "summary": summary,
            }
        )
    return timeline


def _post_ship_probe_summary(
    orchestrator: Any,
    label: str,
    returncode: int,
    payload: dict[str, Any],
) -> str:
    if returncode != 0:
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            return str(error.get("message") or error.get("hint") or "command failed")[:180]
        return "command failed"
    if "metrics show" in label:
        decision = payload.get("optimization_decision")
        summary = payload.get("optimization_summary")
        next_action = (
            decision.get("next_action") if isinstance(decision, dict) else payload.get("next_step")
        )
        raw_tokens = (
            summary.get("raw_token_total")
            if isinstance(summary, dict)
            else payload.get("total_tokens")
        )
        parts = []
        if next_action:
            parts.append(f"candidate={next_action}")
        if raw_tokens:
            parts.append(f"raw_tokens={raw_tokens}")
        return "; ".join(parts) or "metrics inspected"
    if "logs --info" in label:
        items = payload.get("items")
        if isinstance(items, list):
            return f"compact_log_events={len(items)}"
        return "compact logs inspected"
    if "logs analyze" in label:
        counts = payload.get("counts")
        missing = payload.get("missing")
        if not isinstance(counts, dict):
            coverage = payload.get("observability_coverage")
            counts = coverage.get("counts") if isinstance(coverage, dict) else {}
            missing = coverage.get("missing_signals") if isinstance(coverage, dict) else missing
        parts = []
        if isinstance(counts, dict):
            if counts.get("tools") is not None:
                parts.append(f"tools={counts.get('tools')}")
            if counts.get("errors") is not None:
                parts.append(f"errors={counts.get('errors')}")
        if isinstance(missing, list) and missing:
            parts.append("missing=" + ",".join(str(item) for item in missing[:3]))
        return "; ".join(parts) or "observability analysis inspected"
    return "inspected"
