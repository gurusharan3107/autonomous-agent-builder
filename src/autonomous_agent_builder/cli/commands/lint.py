"""Aggregate structural lint for fast builder product hygiene."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import typer

from autonomous_agent_builder.cli.client import EXIT_FAILURE, EXIT_SUCCESS
from autonomous_agent_builder.cli.commands import memory
from autonomous_agent_builder.cli.output import render
from autonomous_agent_builder.cli.quality_gates import QualityGateError, list_quality_gate_contracts
from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.knowledge.document_spec import lint_directory
from autonomous_agent_builder.knowledge.quality_gate import KnowledgeQualityGate
from autonomous_agent_builder.services.readiness import compact_status, load_readiness_status


def _check_memory() -> dict[str, Any]:
    payload = memory._lint_memory_entries()  # noqa: SLF001 - aggregate CLI reuses command-owned check.
    return {
        "name": "memory",
        "command": "builder memory lint --json",
        "status": "passed" if payload.get("passed") else "failed",
        "passed": bool(payload.get("passed")),
        "summary": (
            f"{payload.get('files_checked', 0)} files checked, "
            f"{payload.get('error_count', 0)} errors, {payload.get('warning_count', 0)} warnings"
        ),
        "details": payload,
    }


def _check_quality_gates() -> dict[str, Any]:
    try:
        contracts = list_quality_gate_contracts()
    except QualityGateError as exc:
        return {
            "name": "quality_gates",
            "command": "builder quality-gate --json",
            "status": "failed",
            "passed": False,
            "summary": "quality-gate docs are malformed",
            "details": {"error": str(exc)},
        }
    return {
        "name": "quality_gates",
        "command": "builder quality-gate --json",
        "status": "passed",
        "passed": True,
        "summary": f"{len(contracts)} quality-gate contracts loaded",
        "details": {
            "count": len(contracts),
            "surfaces": [contract.surface for contract in contracts],
        },
    }


def _check_knowledge() -> dict[str, Any]:
    agent_builder_dir = Path(".agent-builder")
    kb_path = agent_builder_dir / "knowledge" / "system-docs"
    if not agent_builder_dir.exists() or not kb_path.exists():
        return {
            "name": "knowledge",
            "command": "builder knowledge validate --json",
            "status": "skipped",
            "passed": True,
            "summary": "knowledge base not initialized",
            "details": {"path": str(kb_path)},
        }

    lint_output = io.StringIO()
    with contextlib.redirect_stdout(lint_output):
        lint_passed, lint_failed, lint_total = lint_directory(kb_path, strict=False)
    deterministic_result = KnowledgeQualityGate(kb_path, Path.cwd()).validate()
    passed = lint_failed == 0 and lint_total > 0 and deterministic_result.passed
    return {
        "name": "knowledge",
        "command": "builder knowledge validate --json",
        "status": "passed" if passed else "failed",
        "passed": passed,
        "summary": deterministic_result.summary,
        "details": {
            "lint": {
                "passed": lint_failed == 0 and lint_total > 0,
                "counts": {"passed": lint_passed, "failed": lint_failed, "total": lint_total},
                "output": lint_output.getvalue().strip(),
            },
            "deterministic_validation": deterministic_result.to_dict(),
        },
    }


def _check_cli_surface() -> dict[str, Any]:
    command = [sys.executable, "-m", "autonomous_agent_builder.cli.main", "--help"]
    source_root = Path(__file__).resolve().parents[3]
    pythonpath_parts = [str(source_root)]
    if os.environ.get("PYTHONPATH"):
        pythonpath_parts.append(str(os.environ["PYTHONPATH"]))
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(pythonpath_parts)}
    result = subprocess.run(command, cwd=Path.cwd(), env=env, capture_output=True, text=True, timeout=15)
    output = f"{result.stdout}\n{result.stderr}"
    expected = ("doctor", "lint", "quality-gate", "memory", "knowledge", "readiness")
    missing = [item for item in expected if item not in output]
    passed = result.returncode == 0 and not missing
    return {
        "name": "cli_surface",
        "command": "builder --help",
        "status": "passed" if passed else "failed",
        "passed": passed,
        "summary": (
            "root help exposes expected agent-facing commands"
            if passed
            else f"root help missing expected commands: {', '.join(missing)}"
        ),
        "details": {
            "exit_code": result.returncode,
            "missing": missing,
            "expected": list(expected),
        },
    }


def _check_config() -> dict[str, Any]:
    try:
        settings = get_settings()
    except Exception as exc:  # pragma: no cover - defensive against env-specific settings errors.
        return {
            "name": "config",
            "command": "builder lint --json",
            "status": "failed",
            "passed": False,
            "summary": "settings failed to parse",
            "details": {"error": str(exc)},
        }
    runtime_sdk = getattr(getattr(settings, "runtime", None), "sdk", "")
    return {
        "name": "config",
        "command": "builder lint --json",
        "status": "passed",
        "passed": True,
        "summary": "settings parsed successfully",
        "details": {"runtime_sdk": runtime_sdk},
    }


def _check_readiness() -> dict[str, Any]:
    project_root = Path.cwd()
    if not (project_root / ".agent-builder").exists():
        return {
            "name": "readiness",
            "command": "builder readiness status --json",
            "status": "skipped",
            "passed": True,
            "summary": "readiness not initialized",
            "details": {"project_root": str(project_root)},
        }
    payload = load_readiness_status(project_root)
    compact = compact_status(payload)
    required = ("mode", "state", "can_continue", "blocking_reasons", "invalidated_by", "next")
    missing = [key for key in required if key not in compact]
    passed = not missing
    return {
        "name": "readiness",
        "command": "builder readiness status --json",
        "status": "passed" if passed else "failed",
        "passed": passed,
        "summary": "readiness status schema is readable" if passed else "readiness status schema is incomplete",
        "details": {"missing": missing, "status": compact},
    }


def lint_command(
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Run fast structural lint checks across builder-owned product surfaces."""
    checks = [
        _check_memory(),
        _check_quality_gates(),
        _check_knowledge(),
        _check_cli_surface(),
        _check_config(),
        _check_readiness(),
    ]
    failed = [check for check in checks if check["status"] == "failed"]
    skipped = [check for check in checks if check["status"] == "skipped"]
    payload = {
        "ok": not failed,
        "status": "ok" if not failed else "error",
        "passed": not failed,
        "checks": checks,
        "summary": {
            "total": len(checks),
            "passed": sum(1 for check in checks if check["status"] == "passed"),
            "failed": len(failed),
            "skipped": len(skipped),
        },
        "next_step": (
            "ready_for_behavioral_validation"
            if not failed
            else str(failed[0].get("command") or "builder lint --json")
        ),
    }

    def fmt(data: dict[str, Any]) -> str:
        lines = ["Builder lint:", ""]
        for check in data["checks"]:
            lines.append(f"- {check['name']}: {check['status']} — {check['summary']}")
        lines.extend(["", f"next: {data['next_step']}"])
        return "\n".join(lines)

    render(payload, fmt, use_json=json)
    sys.exit(EXIT_SUCCESS if not failed else EXIT_FAILURE)
