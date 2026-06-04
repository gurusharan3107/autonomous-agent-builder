"""Tests for builder quality-gate CLI surface contracts."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from autonomous_agent_builder.cli import quality_gates as quality_gate_registry
from autonomous_agent_builder.cli.main import app

runner = CliRunner()


def test_quality_gate_quality_gates_json():
    result = runner.invoke(app, ["quality-gate", "quality-gates", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "quality-gates"
    assert "--json is the stable machine contract" in payload["expectations"]


def test_quality_gate_builder_cli_json():
    result = runner.invoke(app, ["quality-gate", "builder-cli", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "builder-cli"
    assert "builder --help" in payload["commands"]
    assert "builder agent --help" in payload["commands"]
    assert "builder backlog --help" in payload["commands"]
    assert "builder knowledge --help" in payload["commands"]
    assert "builder server status --json" in payload["commands"]
    assert "builder server doctor --json" in payload["commands"]
    assert "startup orientation follows doctor -> map -> context" in payload["expectations"]
    assert "builder start is the single startup owner for the local dashboard and API; do not add parallel start or dashboard-publish entrypoints" in payload["expectations"]
    assert "builder server is inspection and cleanup only; it must not become a parallel start lane" in payload["expectations"]
    assert any(
        item.startswith("the CLI is the product adapter over stable services and schemas")
        for item in payload["expectations"]
    )
    assert "local knowledge list/search/summary/show remain usable when AAB_API_URL is unset, wrong, or the builder server is down" in payload["expectations"]
    assert "before adding or renaming a builder command, inspect existing top-level and group help so new behavior extends an owned surface instead of creating a parallel one" in payload["expectations"]
    assert "builder quality-gate claude-agent-sdk --json" in payload["commands"]
    assert 'AAB_API_URL=http://127.0.0.1:1 builder knowledge search "system architecture" --type system-docs --limit 3 --json' in payload["commands"]
    assert "workflow quality-gate cli-for-agents" in payload["commands"]


def test_quality_gate_claude_agent_sdk_json():
    result = runner.invoke(app, ["quality-gate", "claude-agent-sdk", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "claude-agent-sdk"
    assert any(
        item.startswith("Claude SDK-facing changes remain limited to sdk=claude runtime execution mechanics")
        for item in payload["expectations"]
    )
    assert any(
        item.startswith("shared services or stable product APIs are the preferred internal integration path")
        for item in payload["expectations"]
    )


def test_quality_gate_modular_runtime_json():
    result = runner.invoke(app, ["quality-gate", "modular-runtime", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "modular-runtime"
    assert any(
        item.startswith("user-facing runtime selection exposes only claude and codex_sdk")
        for item in payload["expectations"]
    )
    assert "docs/references/runtime-settings.md" in payload["related_docs"]


def test_quality_gate_architecture_boundary_json():
    result = runner.invoke(app, ["quality-gate", "architecture-boundary", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "architecture-boundary"
    assert "workflow --docs-dir=docs read quality-gate/architecture-boundary" in payload["commands"]
    assert "builder quality-gate claude-md --json" in payload["commands"]
    assert any(
        item.startswith("runtime-boundary changes preserve the ownership split already documented")
        for item in payload["expectations"]
    )
    assert any(
        item.startswith("Codex subagents remain optional specialist lanes")
        for item in payload["expectations"]
    )


def test_quality_gate_lists_surfaces_json():
    result = runner.invoke(app, ["quality-gate", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["count"] >= 1
    assert any(item["surface"] == "builder-cli" for item in payload["surfaces"])
    assert any(item["surface"] == "claude-md" for item in payload["surfaces"])
    assert any(item["surface"] == "claude-agent-sdk" for item in payload["surfaces"])
    assert any(item["surface"] == "architecture-boundary" for item in payload["surfaces"])
    assert any(item["surface"] == "product-lifecycle" for item in payload["surfaces"])
    assert any(item["surface"] == "state-integrity" for item in payload["surfaces"])
    assert any(item["surface"] == "dashboard-ux" for item in payload["surfaces"])
    assert not any(item["surface"] == "architecture-invariants" for item in payload["surfaces"])
    assert not any(item["surface"] == "nonexistent" for item in payload["surfaces"])


@pytest.mark.parametrize(
    "surface",
    (
        "product-lifecycle",
        "state-integrity",
        "dashboard-ux",
    ),
)
def test_product_quality_gate_surfaces_json(surface: str):
    result = runner.invoke(app, ["quality-gate", surface, "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == surface
    assert payload["commands"]
    assert payload["expectations"]


def test_quality_gate_architecture_boundary_surface_json():
    result = runner.invoke(app, ["quality-gate", "architecture-boundary", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["title"] == "Architecture quality gate"
    assert any(
        item.startswith("runtime-boundary changes preserve the ownership split already documented")
        for item in payload["expectations"]
    )


def test_quality_gate_claude_md_surface_json():
    result = runner.invoke(app, ["quality-gate", "claude-md", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "claude-md"
    assert payload["title"] == "CLAUDE.md quality gate"
    assert "workflow --docs-dir=docs read quality-gate/claude-md" in payload["commands"]
    assert any(
        item.startswith("CLAUDE.md stays a runtime contract for this repo")
        for item in payload["expectations"]
    )


def test_quality_gate_surface_json():
    result = runner.invoke(app, ["quality-gate", "builder-cli", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "builder-cli"
    assert any(
        item.startswith("the knowledge lane still provides one coherent command family")
        for item in payload["expectations"]
    )


def test_quality_gate_claude_agent_sdk_surface_json():
    result = runner.invoke(app, ["quality-gate", "claude-agent-sdk", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "claude-agent-sdk"
    assert any(
        item.startswith("routing, blocked states, retries, and human checkpoints are not reassigned")
        for item in payload["expectations"]
    )


def test_gate_command_removed():
    result = runner.invoke(app, ["gate", "contract", "builder-cli", "--json"])

    assert result.exit_code != 0
    assert "No such command 'gate'" in result.stdout


def test_quality_gate_malformed_frontmatter_errors(monkeypatch, tmp_path):
    gate_dir = tmp_path / "quality-gate"
    gate_dir.mkdir()
    (gate_dir / "broken.md").write_text(
        "---\n"
        "title: Broken Gate\n"
        "surface: broken\n"
        "summary: bad\n"
        "commands: nope\n"
        "---\n\n"
        "# Broken\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(quality_gate_registry, "QUALITY_GATE_DIR", gate_dir)

    result = runner.invoke(app, ["quality-gate", "--json"])

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid_quality_gate_doc"
    assert "frontmatter" in payload["error"]["detail"]


def test_root_help_hides_gate_surface():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "│ gate" not in result.stdout
