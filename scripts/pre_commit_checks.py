#!/usr/bin/env python3
"""Run deterministic pre-commit checks for builder changes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Check:
    code: str
    command: tuple[str, ...]
    why: str


DOC_OWNER_PREFIXES = (
    "docs/references/",
    "docs/workflows/",
    "docs/quality-gate/",
    "docs/design-docs/",
    "docs/plans/",
)
DOC_OWNER_FILES = {
    "docs/cli-validation.md",
    "docs/workflows/autonomous-lifecycle-validation.md",
    "docs/knowledge.md",
    "docs/claude-agent-sdk-integration.md",
}
CHANGELOG_FILE = "CHANGELOG.md"


def _repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        return Path.cwd()
    return Path(result.stdout.strip()).resolve()


def _git_lines(args: list[str], repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files(repo_root: Path) -> list[str]:
    staged = _git_lines(["diff", "--cached", "--name-only"], repo_root)
    if staged:
        return sorted(dict.fromkeys(staged))

    status = _git_lines(["status", "--short", "--untracked-files=all"], repo_root)
    files: list[str] = []
    for line in status:
        path = line[2:].strip()
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1].strip()
        if path:
            files.append(path)
    return sorted(path for path in dict.fromkeys(files) if not _is_local_generated_path(path))


def _is_local_generated_path(path: str) -> bool:
    return path == ".codex/environments" or path.startswith(".codex/environments/")


def _is_product_code_change(path: str) -> bool:
    if path.startswith("tests/"):
        return False
    if path.startswith("src/autonomous_agent_builder/dashboard/static/"):
        return False
    return path.startswith(("src/", "frontend/src/", "scripts/")) or path in {
        "pyproject.toml",
        "frontend/package.json",
    }


def _is_repo_doc_change(path: str) -> bool:
    return path in DOC_OWNER_FILES or any(path.startswith(prefix) for prefix in DOC_OWNER_PREFIXES)


def _requires_changelog_entry(path: str) -> bool:
    if path == CHANGELOG_FILE:
        return False
    if path.startswith("tests/"):
        return False
    if _is_local_generated_path(path):
        return False
    if _is_product_code_change(path) or _is_repo_doc_change(path):
        return True
    return path in {
        ".githooks/pre-commit",
        ".codex/config.toml",
        "AGENTS.md",
        "docs/REFERENCE.md",
    } or path.startswith(".codex/agents/")


def _requires_test_update(path: str) -> bool:
    """Behavioral product code whose change should come with a tests/ change.

    Scoped to importable builder Python under src/ — the surface where a
    behavioral change (renamed symbol, changed return/string an assertion
    pins) silently breaks the suite. Excludes static assets (no test
    coverage) and frontend (separate test story).
    """
    if not path.startswith("src/autonomous_agent_builder/"):
        return False
    if path.startswith("src/autonomous_agent_builder/dashboard/static/"):
        return False
    return path.endswith(".py")


def docs_sync_result(files: list[str]) -> dict[str, object]:
    code_changes = [path for path in files if _is_product_code_change(path)]
    doc_changes = [path for path in files if _is_repo_doc_change(path)]
    passed = not code_changes or bool(doc_changes)
    return {
        "code": "docs_sync_required",
        "command": "stage matching docs/references, docs/workflows, or owner docs with code changes",
        "why": "prevent workflow/reference docs from going stale when product code changes",
        "exit_code": 0 if passed else 2,
        "status": "passed" if passed else "failed",
        "code_changes": code_changes,
        "doc_changes": doc_changes,
        "stdout_tail": "",
        "stderr_tail": (
            ""
            if passed
            else (
                "Product code changed without a matching repo docs update. "
                "Update the relevant docs/references, docs/workflows, docs/quality-gate, "
                "or other docs owner surface before committing."
            )
        ),
    }


def changelog_sync_result(files: list[str]) -> dict[str, object]:
    changelog_changed = CHANGELOG_FILE in files
    tracked_changes = sorted(path for path in files if _requires_changelog_entry(path))
    passed = not tracked_changes or changelog_changed
    return {
        "code": "changelog_update_required",
        "command": "stage CHANGELOG.md with product, docs, hook, or operator-surface changes",
        "why": "keep compact project history synchronized with commit-worthy changes",
        "exit_code": 0 if passed else 3,
        "status": "passed" if passed else "failed",
        "tracked_changes": tracked_changes,
        "changelog_changed": changelog_changed,
        "stdout_tail": "",
        "stderr_tail": (
            ""
            if passed
            else (
                "Commit-worthy product, docs, hook, or operator-surface changes are staged "
                "without CHANGELOG.md. Add a compact evidence-first changelog entry before committing."
            )
        ),
    }


def tests_sync_result(files: list[str]) -> dict[str, object]:
    """Behavioral src/ change must be staged with a matching tests/ change.

    Peer to docs_sync_result / changelog_sync_result. Encodes the rule that
    repeatedly failed as prose: a behavioral change without a test update ships
    breakage that surfaces only when the suite is later run. The escape hatch is
    deliberate friction — stage the covering test (even a regression test) with
    the code, or, for a genuinely test-neutral change, an unrelated tests/ touch.
    """
    code_changes = [path for path in files if _requires_test_update(path)]
    test_changes = [path for path in files if path.startswith("tests/")]
    passed = not code_changes or bool(test_changes)
    return {
        "code": "tests_sync_required",
        "command": "stage a matching tests/ change with behavioral src/ changes",
        "why": "behavioral product code must ship with the test that proves it (root cause of recurring broken-suite commits)",
        "exit_code": 0 if passed else 4,
        "status": "passed" if passed else "failed",
        "code_changes": code_changes,
        "test_changes": test_changes,
        "stdout_tail": "",
        "stderr_tail": (
            ""
            if passed
            else (
                "Behavioral src/ code changed without a matching tests/ change. "
                "Stage the covering test (a regression test for the new behavior, or "
                "the updated assertions) before committing. If the change is genuinely "
                "test-neutral (docstrings, comments), stage the relevant test anyway to "
                "record that it was considered."
            )
        ),
    }


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
    if (
        path.startswith(".memory/")
        or path.endswith("commands/memory.py")
        or path == "tests/test_memory_cli.py"
    ):
        surfaces.add("memory")
    if (
        path.startswith("src/autonomous_agent_builder/cli/")
        or path.startswith("tests/test_builder_cli")
        or path == "scripts/pre_commit_checks.py"
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
    if path.startswith("docs/") or path == "AGENTS.md" or path.startswith("scripts/documentation"):
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


def _surfaces_from_changes(files: list[str]) -> set[str]:
    surfaces: set[str] = set()
    for path in files:
        surfaces.update(_surface_for_path(path))
    return surfaces or {"general"}


def checks_for_files(files: list[str]) -> list[Check]:
    surfaces = _surfaces_from_changes(files)
    checks = [
        Check(
            code="builder_lint",
            command=(sys.executable, "-m", "autonomous_agent_builder.cli.main", "lint", "--json"),
            why="run aggregate builder lint before every commit",
        )
    ]

    if "memory" in surfaces:
        checks.extend(
            [
                Check(
                    code="memory_cli_tests",
                    command=(sys.executable, "-m", "pytest", "tests/test_memory_cli.py", "-q"),
                    why="prove memory mutation, lint, reindex, and retrieval behavior",
                ),
                Check(
                    code="memory_contract_smoke",
                    command=(
                        sys.executable,
                        "-m",
                        "autonomous_agent_builder.cli.main",
                        "memory",
                        "contract",
                        "--json",
                    ),
                    why="prove agents can discover the memory template",
                ),
            ]
        )
    if "builder-cli" in surfaces:
        checks.append(
            Check(
                code="builder_cli_surface_tests",
                command=(
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_builder_cli_surfaces.py",
                    "-q",
                ),
                why="prove agent-facing CLI JSON/help contracts remain stable",
            )
        )
    if "codex-subagents" in surfaces:
        checks.extend(
            [
                Check(
                    code="codex_subagent_quality_gate_contract",
                    command=(
                        sys.executable,
                        "scripts/check_quality_gate_contracts.py",
                        "--target",
                        "docs/quality-gate/codex-subagents.md",
                    ),
                    why="prove the Codex subagents quality-gate doc validates its own contract",
                ),
                Check(
                    code="codex_subagent_gate",
                    command=(
                        sys.executable,
                        "scripts/check_codex_subagents.py",
                        "--repo-root",
                        ".",
                    ),
                    why="prove project Codex subagents remain registered and boundary-safe",
                ),
                Check(
                    code="codex_subagent_tests",
                    command=(sys.executable, "-m", "pytest", "tests/test_codex_subagents.py", "-q"),
                    why="prove the Codex subagent validator catches meaningful drift",
                ),
            ]
        )
    if "runtime" in surfaces:
        checks.append(
            Check(
                code="runtime_tests",
                command=(
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_claude_runtime.py",
                    "tests/test_runtime_interface.py",
                    "tests/test_execution_policy.py",
                    "tests/test_agent_runner.py",
                    "-q",
                ),
                why="prove runtime selection and execution policy behavior still work",
            )
        )
    if "agent-quality" in surfaces:
        checks.append(
            Check(
                code="agent_quality_definition_tests",
                command=(
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_definitions.py::TestAgentDefinitions::test_optimization_agent_is_post_ship_bounded_and_observability_grounded",
                    "tests/test_definitions.py::TestAgentDefinitions::test_all_have_prompt_templates",
                    "-q",
                ),
                why="prove agent definition tuning remains bounded and prompt templates stay valid",
            )
        )
    if "product-lifecycle" in surfaces:
        checks.append(
            Check(
                code="product_lifecycle_optimization_tests",
                command=(
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_sprint_execution.py::test_post_ship_optimization_probe_summarizes_cli_evidence",
                    "tests/test_sprint_execution.py::test_post_ship_optimization_refreshes_generated_app_sdk_guidance",
                    "-q",
                ),
                why="prove sprint execution optimization evidence remains aligned with product lifecycle telemetry",
            )
        )
    if "docs" in surfaces or "knowledge" in surfaces:
        checks.append(
            Check(
                code="quality_gate_contracts",
                command=(
                    sys.executable,
                    "scripts/check_quality_gate_contracts.py",
                    "--target",
                    "docs/quality-gate/builder-cli.md",
                ),
                why="prove quality-gate docs still read as gate contracts",
            )
        )
    if "dashboard" in surfaces:
        checks.append(
            Check(
                code="dashboard_design_tokens",
                command=(sys.executable, "scripts/check_dashboard_design_tokens.py", "--json"),
                why="prove dashboard styling stays on Builder tokens and does not reintroduce shadcn/Luma",
            )
        )
        checks.append(
            Check(
                code="dashboard_design_system_contract",
                command=(
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_dashboard_design_system_contract.py",
                    "-q",
                ),
                why="prove top-level dashboard pages import the canonical design-system owner",
            )
        )
        checks.append(
            Check(
                code="dashboard_unit_tests",
                command=(
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_dashboard_api.py",
                    "tests/test_codex_app_server_runtime.py",
                    "tests/test_embedded_dashboard_streams.py",
                    "-q",
                ),
                why=(
                    "prove deterministic dashboard API, runtime, and stream "
                    "projections still load for browser-visible surfaces"
                ),
            )
        )
    if surfaces == {"general"}:
        checks.append(
            Check(
                code="general_smoke_tests",
                command=(
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_builder_cli_surfaces.py",
                    "-q",
                ),
                why="run a bounded smoke suite for uncategorized changes",
            )
        )
    return checks


def _run_check(check: Check, repo_root: Path) -> dict[str, object]:
    env = dict(os.environ)
    src = str(repo_root / "src")
    env["PYTHONPATH"] = (
        src if not env.get("PYTHONPATH") else os.pathsep.join([src, env["PYTHONPATH"]])
    )
    result = subprocess.run(
        list(check.command),
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return {
        "code": check.code,
        "command": " ".join(check.command),
        "why": check.why,
        "exit_code": result.returncode,
        "status": "passed" if result.returncode == 0 else "failed",
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
    }


def main() -> int:
    repo_root = _repo_root()
    files = changed_files(repo_root)
    checks = checks_for_files(files)
    results = [
        docs_sync_result(files),
        changelog_sync_result(files),
        tests_sync_result(files),
        *[_run_check(check, repo_root) for check in checks],
    ]
    failed = [result for result in results if result["status"] == "failed"]
    payload = {
        "ok": not failed,
        "status": "passed" if not failed else "failed",
        "changed_files": files,
        "checks": results,
    }
    print(json.dumps(payload, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
