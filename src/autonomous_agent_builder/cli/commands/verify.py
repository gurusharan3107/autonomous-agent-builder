"""Behavioral proof planner for changed builder product surfaces."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from autonomous_agent_builder.cli.client import EXIT_FAILURE, EXIT_SUCCESS
from autonomous_agent_builder.cli.output import render


@dataclass(frozen=True)
class Proof:
    code: str
    surface: str
    proof_type: str
    why: str
    command: str | None = None
    tool: str | None = None
    path: str | None = None
    blocking: bool = True
    executable: bool = True

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "surface": self.surface,
            "type": self.proof_type,
            "why": self.why,
            "blocking": self.blocking,
            "executable": self.executable,
        }
        if self.command:
            payload["command"] = self.command
        if self.tool:
            payload["tool"] = self.tool
        if self.path:
            payload["path"] = self.path
        return payload


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        timeout=15,
    )


def _changed_files(base: str | None = None) -> list[str]:
    if base:
        diff = _run_git(["diff", "--name-only", base, "--"])
        names = [line.strip() for line in diff.stdout.splitlines() if line.strip()]
    else:
        status = _run_git(["status", "--short"])
        names = []
        for line in status.stdout.splitlines():
            if not line.strip():
                continue
            # Porcelain v1 path begins at column 4. Rename rows use "old -> new".
            path = line[3:].strip()
            if " -> " in path:
                path = path.rsplit(" -> ", 1)[-1].strip()
            names.append(path)
    return sorted(path for path in dict.fromkeys(names) if not _is_local_generated_path(path))


def _is_local_generated_path(path: str) -> bool:
    return path == ".codex/environments" or path.startswith(".codex/environments/")


def _surface_for_path(path: str) -> set[str]:
    surfaces: set[str] = set()
    if (
        path.startswith(".codex/agents/")
        or path == ".codex/config.toml"
        or path == "AGENTS.md"
        or path == "docs/REFERENCE.md"
        or path == "docs/quality-gate/codex-subagents.md"
        or path == "scripts/check_codex_subagents.py"
        or path == "src/autonomous_agent_builder/codex_subagents.py"
        or path == "tests/test_codex_subagents.py"
    ):
        surfaces.add("codex-subagents")
    if path.startswith(".memory/") or path.endswith("commands/memory.py"):
        surfaces.add("memory")
    if (
        path.startswith("src/autonomous_agent_builder/cli/")
        or path.startswith("tests/test_builder_cli")
        or path == "scripts/pre_commit_checks.py"
        or path == "tests/test_pre_commit_checks.py"
        or path == ".githooks/pre-commit"
    ):
        surfaces.add("builder-cli")
    if path.startswith("src/autonomous_agent_builder/agents/definitions.py") or path.startswith(
        "tests/test_definitions.py"
    ):
        surfaces.add("agent-quality")
    if path.startswith("src/autonomous_agent_builder/orchestrator/") or path.startswith(
        "tests/test_sprint_execution.py"
    ):
        surfaces.add("product-lifecycle")
    if path == "AGENTS.md" or path.startswith("docs/") or path.startswith("scripts/documentation"):
        surfaces.add("docs")
    if path.startswith(".agent-builder/knowledge/") or "knowledge" in path:
        surfaces.add("knowledge")
    if (
        "runtime" in path
        or path.endswith("claude_runtime.py")
        or path == "src/autonomous_agent_builder/agents/runner.py"
        or path == "src/autonomous_agent_builder/agents/execution_policy.py"
        or path.startswith("tests/test_runtime")
        or path.startswith("tests/test_claude_runtime")
        or path == "tests/test_agent_runner.py"
        or path == "tests/test_execution_policy.py"
    ):
        surfaces.add("runtime")
    if (
        path.startswith("frontend/")
        or path.startswith("src/autonomous_agent_builder/embedded/")
        or path.startswith("tests/test_embedded")
        or path.startswith("tests/test_codex_app_server")
    ):
        surfaces.add("dashboard")
    return surfaces or {"general"}


def _surfaces_from_changes(files: list[str]) -> list[str]:
    if not files:
        return []
    surfaces: set[str] = set()
    for path in files:
        surfaces.update(_surface_for_path(path))
    return sorted(surfaces or {"general"})


def _proofs_for_surfaces(surfaces: list[str]) -> list[Proof]:
    proofs: list[Proof] = [
        Proof(
            code="structural_lint",
            surface="all",
            proof_type="lint",
            command="PYTHONPATH=src python -m autonomous_agent_builder.cli.main lint --json",
            why="confirm fast structural builder hygiene before behavioral proof",
        )
    ]

    if "memory" in surfaces:
        proofs.extend(
            [
                Proof(
                    code="memory_cli_tests",
                    surface="memory",
                    proof_type="unit_tests",
                    command="PYTHONPATH=src pytest tests/test_memory_cli.py -q",
                    why="prove memory add, contract, lint, reindex, and aggregate lint behavior",
                ),
                Proof(
                    code="memory_contract_smoke",
                    surface="memory",
                    proof_type="cli_smoke",
                    command=(
                        "PYTHONPATH=src python -m autonomous_agent_builder.cli.main "
                        "memory contract --json"
                    ),
                    why="prove agents can discover the required memory template",
                ),
            ]
        )
    if "builder-cli" in surfaces:
        proofs.append(
            Proof(
                code="builder_cli_surface_tests",
                surface="builder-cli",
                proof_type="unit_tests",
                command="PYTHONPATH=src pytest tests/test_builder_cli_surfaces.py -q",
                why="prove agent-facing CLI JSON/help contracts remain stable",
            )
        )
    if "codex-subagents" in surfaces:
        proofs.extend(
            [
                Proof(
                    code="codex_subagent_quality_gate_contract",
                    surface="codex-subagents",
                    proof_type="docs_contract",
                    command=(
                        "PYTHONPATH=src python scripts/check_quality_gate_contracts.py "
                        "--target docs/quality-gate/codex-subagents.md"
                    ),
                    why="prove the Codex subagents quality-gate doc validates its own contract",
                ),
                Proof(
                    code="codex_subagent_gate",
                    surface="codex-subagents",
                    proof_type="cli_smoke",
                    command="PYTHONPATH=src python scripts/check_codex_subagents.py --repo-root .",
                    why="prove project Codex subagents remain registered and boundary-safe",
                ),
                Proof(
                    code="codex_subagent_tests",
                    surface="codex-subagents",
                    proof_type="unit_tests",
                    command="PYTHONPATH=src pytest tests/test_codex_subagents.py -q",
                    why="prove the Codex subagent validator catches meaningful drift",
                ),
            ]
        )
    if "runtime" in surfaces:
        proofs.append(
            Proof(
                code="runtime_tests",
                surface="runtime",
                proof_type="unit_tests",
                command=(
                    "PYTHONPATH=src pytest tests/test_claude_runtime.py "
                    "tests/test_runtime_interface.py tests/test_execution_policy.py "
                    "tests/test_agent_runner.py -q"
                ),
                why="prove runtime selection and execution policy behavior still work",
            )
        )
    if "agent-quality" in surfaces:
        proofs.append(
            Proof(
                code="agent_quality_definition_tests",
                surface="agent-quality",
                proof_type="unit_tests",
                command=(
                    "PYTHONPATH=src pytest "
                    "tests/test_definitions.py::TestAgentDefinitions::test_optimization_agent_is_post_ship_bounded_and_observability_grounded "
                    "tests/test_definitions.py::TestAgentDefinitions::test_all_have_prompt_templates -q"
                ),
                why="prove agent definition tuning remains bounded and prompt templates stay valid",
            )
        )
    if "product-lifecycle" in surfaces:
        proofs.append(
            Proof(
                code="product_lifecycle_optimization_tests",
                surface="product-lifecycle",
                proof_type="unit_tests",
                command=(
                    "PYTHONPATH=src pytest "
                    "tests/test_sprint_execution.py::test_post_ship_optimization_probe_summarizes_cli_evidence "
                    "tests/test_sprint_execution.py::test_post_ship_optimization_refreshes_generated_app_sdk_guidance -q"
                ),
                why="prove sprint execution optimization evidence remains aligned with product lifecycle telemetry",
            )
        )
    if "docs" in surfaces or "knowledge" in surfaces:
        proofs.append(
            Proof(
                code="quality_gate_contracts",
                surface="docs",
                proof_type="docs_contract",
                command="PYTHONPATH=src python scripts/check_quality_gate_contracts.py --target docs/quality-gate/builder-cli.md",
                why="prove quality-gate docs still read as gate contracts, not owner docs",
            )
        )
    if "dashboard" in surfaces:
        proofs.append(
            Proof(
                code="dashboard_browser_proof",
                surface="dashboard",
                proof_type="browser_check",
                tool="Browser Use",
                path="/",
                why="prove dashboard-visible behavior still renders for the user",
                executable=False,
            )
        )
    if set(surfaces) == {"general"}:
        proofs.append(
            Proof(
                code="general_tests",
                surface="general",
                proof_type="unit_tests",
                command="PYTHONPATH=src pytest -q",
                why="prove general code changes do not regress the test suite",
            )
        )
    return proofs


def _execute_command(command: str) -> dict[str, Any]:
    env = dict(os.environ)
    package_src_root = Path(__file__).resolve().parents[3]
    repo_root = package_src_root.parent
    pythonpath_parts = [str(package_src_root)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    is_pytest = " pytest " in f" {command} "
    proof_cwd = (
        repo_root
        if is_pytest or command.strip().startswith("PYTHONPATH=src python scripts/")
        else Path.cwd()
    )
    result = subprocess.run(
        command,
        cwd=proof_cwd,
        env=env,
        shell=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return {
        "command": command,
        "cwd": str(proof_cwd),
        "exit_code": result.returncode,
        "status": "passed" if result.returncode == 0 else "failed",
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def verify_command(
    surface: str | None = typer.Option(
        None,
        "--surface",
        help="Verify a specific surface: memory, builder-cli, runtime, docs, knowledge, dashboard.",
    ),
    changed: bool = typer.Option(False, "--changed", help="Infer surfaces from git changed files."),
    base: str | None = typer.Option(None, "--base", help="Optional git base ref for --changed."),
    execute: bool = typer.Option(False, "--execute", help="Run executable proof commands."),
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Plan or execute behavioral proof for builder product changes."""
    changed_files = _changed_files(base=base) if changed or not surface else []
    surfaces = [surface] if surface else _surfaces_from_changes(changed_files)
    proofs = _proofs_for_surfaces(surfaces) if surfaces else []
    execution_results: list[dict[str, Any]] = []
    if execute:
        for proof in proofs:
            if proof.command and proof.executable:
                execution_results.append({"code": proof.code, **_execute_command(proof.command)})

    failed = [item for item in execution_results if item["status"] == "failed"]
    blocked_manual = [
        proof.to_payload()
        for proof in proofs
        if proof.blocking and (not proof.executable or not proof.command)
    ]
    status = "passed" if execute and not failed and not blocked_manual else "needs_proof"
    if not proofs:
        status = "passed"
    payload = {
        "ok": not failed,
        "status": status,
        "mode": "execute" if execute else "plan",
        "changed_files": changed_files,
        "selected_surfaces": surfaces,
        "required_proof": [proof.to_payload() for proof in proofs],
        "execution_results": execution_results,
        "manual_proof_required": blocked_manual,
        "agent_instruction": (
            "No changed product files require proof."
            if not proofs
            else (
                "Run the required proof in order. Do not mark the change ready until all blocking "
                "command proof passes and any manual Browser Use proof is completed."
            )
        ),
        "next_step": (
            "no_changed_files"
            if not proofs
            else (
                "complete manual proof"
                if blocked_manual
                else (
                    "fix failing proof"
                    if failed
                    else ("ready_for_commit" if execute else "builder verify --execute --json")
                )
            )
        ),
    }

    def fmt(data: dict[str, Any]) -> str:
        lines = ["Builder verify:", f"mode: {data['mode']}", f"status: {data['status']}"]
        lines.append(f"surfaces: {', '.join(data['selected_surfaces'])}")
        lines.append("required proof:")
        for proof in data["required_proof"]:
            target = proof.get("command") or f"{proof.get('tool')} {proof.get('path', '')}".strip()
            lines.append(f"- {proof['code']}: {target}")
        lines.append(f"next: {data['next_step']}")
        return "\n".join(lines)

    render(payload, fmt, use_json=json)
    sys.exit(EXIT_FAILURE if failed else EXIT_SUCCESS)
