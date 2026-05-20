"""Tests for complexity quality-gate CLI contracts."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from autonomous_agent_builder.cli.main import app

runner = CliRunner()


def test_quality_gate_complexity_json():
    result = runner.invoke(app, ["quality-gate", "complexity", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "complexity"
    assert "builder lint --complexity-report --json" in payload["commands"]
    assert any(
        item.startswith("current historical hotspots are allowed only")
        for item in payload["expectations"]
    )
    assert any("above 500 lines" in item for item in payload["expectations"])


def test_quality_gate_list_includes_complexity_surface():
    result = runner.invoke(app, ["quality-gate", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert any(item["surface"] == "complexity" for item in payload["surfaces"])


def test_builder_cli_gate_points_to_complexity_report():
    result = runner.invoke(app, ["quality-gate", "builder-cli", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "builder lint --complexity-report --json" in payload["commands"]
