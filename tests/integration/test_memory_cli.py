"""Builder memory CLI integration tests."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def command_env() -> dict[str, str]:
    """Return an env that can import the repo-local package."""
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )
    return env


def run_builder(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run builder from source without requiring an editable install."""
    return subprocess.run(
        [sys.executable, "-m", "autonomous_agent_builder.cli.main", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=command_env(),
    )


def memory_body(kind: str = "Pattern") -> str:
    return (
        f"## {kind}\n\n"
        "Store reusable builder memory through the CLI contract.\n\n"
        "## Agent Retrieval Summary\n\n"
        "Retrieve this memory when validating builder memory add/search behavior.\n\n"
        "## User-Facing Summary\n\n"
        "This memory verifies that saved content is visible and understandable.\n\n"
        "## Reusable Guidance\n\n"
        "- Use the canonical section template.\n"
        "- Keep retrieval wording explicit.\n\n"
        "## When To Apply\n\n"
        "Apply this when testing memory lifecycle behavior.\n\n"
        "## Retrieval Queries\n\n"
        "- memory integration test\n"
        "- builder memory add\n"
    )


def workflow_base_command() -> list[str]:
    """Resolve workflow for the current machine or skip the test."""
    workflow = shutil.which("workflow")
    if workflow:
        return [workflow]

    for candidate in (
        Path.home() / ".codex" / "bin" / "workflow.py",
        Path.home() / ".claude" / "bin" / "workflow.py",
    ):
        if candidate.exists():
            return [sys.executable, str(candidate)]

    pytest.skip("workflow command not available")


def run_workflow(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run workflow using the current control-plane launcher."""
    return subprocess.run(
        [*workflow_base_command(), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=command_env(),
    )


class TestBuilderMemoryIntegration:
    """Integration tests for builder memory CLI."""

    def test_memory_add_creates_valid_pattern(self, tmp_path: Path) -> None:
        """Test that builder memory add creates a valid pattern file."""
        memory_dir = tmp_path / ".memory"
        memory_dir.mkdir()

        result = run_builder(
            "memory",
            "add",
            "--type",
            "pattern",
            "--phase",
            "testing",
            "--entity",
            "test-entity",
            "--tags",
            "test,validation",
            "--title",
            "Test Pattern Memory",
            "--content",
            memory_body("Pattern"),
            cwd=tmp_path,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        memory_files = list((memory_dir / "patterns").glob("*.md"))
        assert memory_files, "No pattern file created"
        content = memory_files[0].read_text()
        assert "Store reusable builder memory through the CLI contract." in content

    def test_memory_add_creates_valid_decision(self, tmp_path: Path) -> None:
        """Test that builder memory add creates a valid decision file."""
        memory_dir = tmp_path / ".memory"
        memory_dir.mkdir()

        result = run_builder(
            "memory",
            "add",
            "--type",
            "decision",
            "--phase",
            "design",
            "--entity",
            "test-component",
            "--tags",
            "architecture,test",
            "--title",
            "Test Decision Memory",
            "--content",
            memory_body("Decision"),
            cwd=tmp_path,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert list((memory_dir / "decisions").glob("*.md")), "No decision file created"

    def test_memory_created_by_builder_is_queryable_by_builder(self, tmp_path: Path) -> None:
        """Test that builder-created memory can be searched through builder memory."""
        memory_dir = tmp_path / ".memory"
        memory_dir.mkdir()

        result = run_builder(
            "memory",
            "add",
            "--type",
            "pattern",
            "--phase",
            "testing",
            "--entity",
            "search-test",
            "--tags",
            "queryable,builder",
            "--title",
            "Findable Memory",
            "--content",
            memory_body("Pattern"),
            cwd=tmp_path,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        search_result = run_builder("memory", "search", "Findable", cwd=tmp_path)
        assert search_result.returncode == 0

    def test_memory_file_has_proper_structure(self, tmp_path: Path) -> None:
        """Test that created memory files have proper markdown structure."""
        memory_dir = tmp_path / ".memory"
        memory_dir.mkdir()

        result = run_builder(
            "memory",
            "add",
            "--type",
            "correction",
            "--phase",
            "implementation",
            "--entity",
            "test-module",
            "--tags",
            "bug,fix",
            "--title",
            "Test Correction",
            "--content",
            memory_body("Correction"),
            cwd=tmp_path,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        memory_files = list((memory_dir / "corrections").glob("*.md"))
        assert memory_files
        content = memory_files[0].read_text()
        assert len(content) > 50, "Memory file too short, likely missing content"


@pytest.mark.skipif(
    not (REPO_ROOT / ".memory").exists(),
    reason="Requires .memory directory in project root",
)
class TestMemoryInProjectContext:
    """Tests that require running in actual project context."""

    def test_builder_memory_list_works(self) -> None:
        """Test that builder memory list command works."""
        result = run_builder("memory", "list", cwd=REPO_ROOT)
        assert result.returncode == 0
        assert len(result.stdout) > 0

    def test_workflow_command_no_longer_owns_project_memory(self) -> None:
        """Test that workflow signals builder as the owning project-memory surface."""
        result = run_workflow("memory", "list", cwd=REPO_ROOT)
        assert result.returncode == 2
        combined = f"{result.stdout}\n{result.stderr}"
        assert "builder memory" in combined.lower()
