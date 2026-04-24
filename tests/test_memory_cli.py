"""Tests for builder memory lifecycle commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from autonomous_agent_builder.cli.main import app

runner = CliRunner()


def test_memory_lifecycle_commands(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    result = runner.invoke(app, ["memory", "init", "--json"])
    assert result.exit_code == 0

    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "--type",
            "decision",
            "--phase",
            "design",
            "--entity",
            "kb",
            "--tags",
            "memory,friction",
            "--title",
            "Capture KB friction",
            "--content",
            "Remember what caused the issue and the safe path next time.",
            "--json",
        ],
    )
    assert result.exit_code == 0
    first = json.loads(result.stdout)
    first_slug = first["slug"]

    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "--type",
            "pattern",
            "--phase",
            "implementation",
            "--entity",
            "kb",
            "--tags",
            "reuse",
            "--title",
            "Reuse KB extraction pattern",
            "--content",
            "Use the system-docs extraction flow to rebuild local knowledge.",
            "--json",
        ],
    )
    assert result.exit_code == 0
    second = json.loads(result.stdout)
    second_slug = second["slug"]

    result = runner.invoke(app, ["memory", "relate", first_slug, "--to", second_slug, "--json"])
    assert result.exit_code == 0

    result = runner.invoke(
        app,
        ["memory", "flag", first_slug, "--reason", "needs consolidation", "--json"],
    )
    assert result.exit_code == 0

    result = runner.invoke(
        app,
        ["memory", "graduate", first_slug, "--into", "AGENTS.md", "--json"],
    )
    assert result.exit_code == 0

    result = runner.invoke(app, ["memory", "stats", "--json"])
    assert result.exit_code == 0
    stats = json.loads(result.stdout)
    assert stats["total"] == 2
    assert stats["types"]["decision"] == 1
    assert stats["types"]["pattern"] == 1
    assert stats["statuses"]["graduated"] == 1

    routing = json.loads((memory_root / "routing.json").read_text(encoding="utf-8"))
    entries = routing["entries"]
    decision = next(entry for entry in entries if entry["slug"] == first_slug)
    pattern = next(entry for entry in entries if entry["slug"] == second_slug)
    assert second_slug in decision["related"]
    assert first_slug in pattern["related"]
    assert decision["graduated_into"] == "AGENTS.md"


def test_memory_contract_and_lint_commands(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    result = runner.invoke(app, ["memory", "init", "--json"])
    assert result.exit_code == 0

    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "--type",
            "decision",
            "--phase",
            "implementation",
            "--entity",
            "builder-cli",
            "--tags",
            "cli,doctor",
            "--title",
            "Root doctor contract",
            "--content",
            "## Summary\n\nKeep a machine-readable startup path in the owner CLI.",
            "--json",
        ],
    )
    assert result.exit_code == 0

    result = runner.invoke(app, ["memory", "contract", "--json"])
    assert result.exit_code == 0
    contract = json.loads(result.stdout)
    assert "type" in contract["required_frontmatter"]
    assert "decision" in contract["allowed_types"]

    result = runner.invoke(app, ["memory", "lint", "--json"])
    assert result.exit_code == 0
    lint = json.loads(result.stdout)
    assert lint["passed"] is True
    assert lint["files_checked"] == 1


def test_memory_lint_fails_for_missing_related_target(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    decision_dir = memory_root / "decisions"
    decision_dir.mkdir(parents=True)
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    (decision_dir / "broken-memory.md").write_text(
        "---\n"
        "title: Broken memory\n"
        "type: decision\n"
        "date: 2026-04-21\n"
        "phase: implementation\n"
        "entity: builder-cli\n"
        "status: active\n"
        "related: [missing-memory]\n"
        "---\n\n"
        "## Summary\n\nThis entry points at a missing related slug.\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["memory", "lint", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("missing-memory" in issue["message"] for issue in payload["issues"])


def test_memory_lint_tolerates_legacy_entry_without_frontmatter(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    pattern_dir = memory_root / "patterns"
    pattern_dir.mkdir(parents=True)
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    (pattern_dir / "legacy-pattern.md").write_text(
        "Legacy pattern body without explicit frontmatter but with reusable guidance.\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["memory", "lint", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert any(issue["severity"] == "warning" for issue in payload["issues"])


def test_memory_invalidate_marks_irrelevant_entry_inactive(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    result = runner.invoke(app, ["memory", "init", "--json"])
    assert result.exit_code == 0

    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "--type",
            "pattern",
            "--phase",
            "implementation",
            "--entity",
            "builder-cli",
            "--tags",
            "cli,lifecycle",
            "--title",
            "Temporary workaround",
            "--content",
            "## Summary\n\nThis workaround only applies until the real contract lands.",
            "--json",
        ],
    )
    assert result.exit_code == 0
    slug = json.loads(result.stdout)["slug"]

    result = runner.invoke(
        app,
        ["memory", "invalidate", slug, "--reason", "replaced by durable contract", "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["memory"]["status"] == "invalidated"
    assert payload["memory"]["flag_reason"] == "replaced by durable contract"
