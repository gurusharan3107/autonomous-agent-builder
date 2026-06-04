"""CLI contract tests for `builder knowledge validate`."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from autonomous_agent_builder.cli.main import app
from autonomous_agent_builder.knowledge.agent_quality_gate import AgentQualityGateResult
from autonomous_agent_builder.knowledge.quality_gate import QualityCheck, QualityGateResult

runner = CliRunner()


def test_validate_defaults_to_deterministic_only(tmp_path, monkeypatch):
    project_root = tmp_path
    kb_path = project_root / ".agent-builder" / "knowledge" / "system-docs"
    kb_path.mkdir(parents=True)
    monkeypatch.chdir(project_root)

    class _FakeDeterministicGate:
        def __init__(self, kb_path: Path, workspace_path: Path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self):
            return QualityGateResult(
                passed=True,
                score=1.0,
                checks=[QualityCheck("claim_validation", True, 1.0, "passed")],
                summary="Deterministic KB validation passed.",
                blocking_docs=["system-architecture"],
                non_blocking_docs=["project-overview"],
            )

    class _UnexpectedAgentGate:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("agent gate should not run by default")

    monkeypatch.setattr(
        "autonomous_agent_builder.knowledge.quality_gate.KnowledgeQualityGate",
        _FakeDeterministicGate,
    )
    monkeypatch.setattr(
        "autonomous_agent_builder.knowledge.agent_quality_gate.AgentKnowledgeQualityGate",
        _UnexpectedAgentGate,
    )

    result = runner.invoke(app, ["knowledge", "validate", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["blocking_docs"] == ["system-architecture"]
    assert payload["blocking_doc_count"] == 1
    assert (
        payload["progressive_disclosure"][1]["command"]
        == "builder knowledge show system-architecture --section 'Change guidance' --json"
    )
    assert payload["agent_advisory"]["available"] is False


def test_validate_use_agent_keeps_deterministic_result_authoritative(tmp_path, monkeypatch):
    project_root = tmp_path
    kb_path = project_root / ".agent-builder" / "knowledge" / "system-docs"
    kb_path.mkdir(parents=True)
    monkeypatch.chdir(project_root)

    class _FakeDeterministicGate:
        def __init__(self, kb_path: Path, workspace_path: Path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self):
            return QualityGateResult(
                passed=False,
                score=0.4,
                checks=[QualityCheck("claim_validation", False, 0.4, "failed")],
                summary="Deterministic KB validation failed.",
                blocking_docs=["system-architecture"],
                claim_failures=[
                    {
                        "doc": "system-architecture",
                        "section": "Manifest",
                        "claim": "Blocking doc leaked template text.",
                        "reason": "template_leakage",
                        "citations": [],
                    }
                ],
            )

    class _FakeAgentGate:
        def __init__(self, kb_path: Path, workspace_path: Path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self, model=None):
            return AgentQualityGateResult(
                passed=True,
                score=0.9,
                summary="Agent advisory would accept this.",
                evaluation={"criteria_scores": {"usefulness": 90}},
                recommendations=["No changes requested."],
                agent_reasoning="advisory only",
            )

    monkeypatch.setattr(
        "autonomous_agent_builder.knowledge.quality_gate.KnowledgeQualityGate",
        _FakeDeterministicGate,
    )
    monkeypatch.setattr(
        "autonomous_agent_builder.knowledge.agent_quality_gate.AgentKnowledgeQualityGate",
        _FakeAgentGate,
    )

    result = runner.invoke(app, ["knowledge", "validate", "--json", "--use-agent"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert isinstance(payload["claim_failures"][0], str)
    assert payload["progressive_disclosure"][-1]["command"] == "builder knowledge validate --json --full"
    assert payload["agent_advisory"]["available"] is True
    assert payload["agent_advisory"]["passed"] is True

    full_result = runner.invoke(app, ["knowledge", "validate", "--json", "--use-agent", "--full"])
    assert full_result.exit_code == 1
    full_payload = json.loads(full_result.stdout)
    assert isinstance(full_payload["claim_failures"][0], dict)
