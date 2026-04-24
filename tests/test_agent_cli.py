from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from autonomous_agent_builder.cli.commands import agent as agent_module
from autonomous_agent_builder.cli.main import app

runner = CliRunner()


def test_agent_documentation_refresh_json(monkeypatch, tmp_path: Path) -> None:
    validation_path = tmp_path / "kb-validate.json"
    validation_path.write_text('{"passed": true, "summary": "already current"}', encoding="utf-8")

    async def fake_bridge(payload, *, project_root):
        assert payload["passed"] is True
        assert project_root == tmp_path
        return {
            "status": "already_current",
            "mode": "no_op",
            "summary": "Maintained docs are already current.",
            "specialist": "documentation-agent",
            "bridge": "builder agent documentation-refresh",
            "actionable_doc_ids": [],
            "manual_attention_reasons": [],
            "bridge_invoked": False,
            "run": {},
            "result": {},
            "next_step": "builder knowledge validate --json",
        }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(agent_module, "run_documentation_refresh_bridge", fake_bridge)

    result = runner.invoke(
        app,
        ["agent", "documentation-refresh", "--validation", str(validation_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "already_current"
    assert payload["bridge"] == "builder agent documentation-refresh"
