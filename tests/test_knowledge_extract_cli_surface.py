"""Tests for builder knowledge extract CLI surfaces."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from autonomous_agent_builder.cli.commands import kb as kb_module
from autonomous_agent_builder.cli.main import app
from autonomous_agent_builder.knowledge.agent_quality_gate import AgentQualityGateResult
from autonomous_agent_builder.knowledge.quality_gate import QualityCheck, QualityGateResult

runner = CliRunner()


def test_extract_pipeline_continues_when_agent_advisory_falls_back(tmp_path, monkeypatch):
    workspace_path = tmp_path
    kb_path = workspace_path / ".agent-builder" / "knowledge" / "system-docs"
    kb_path.mkdir(parents=True)

    class _FakeExtractor:
        def __init__(self, workspace_path: Path, output_path: Path, *, doc_slugs=None):
            self.workspace_path = workspace_path
            self.output_path = output_path
            self.doc_slugs = doc_slugs

        def extract(self, scope: str = "full"):
            return {
                "documents": [
                    {
                        "type": "system-docs",
                        "title": "Project Overview",
                        "filename": "project-overview.md",
                    }
                ],
                "errors": [],
            }

    class _FakeDeterministicGate:
        def __init__(self, kb_path: Path, workspace_path: Path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self):
            return QualityGateResult(
                passed=True,
                score=1.0,
                checks=[QualityCheck("specificity", True, 1.0, "passed")],
                summary="Quality Gate: PASSED (9/9 checks passed, score: 100.0%)",
            )

    class _FakeAgentGate:
        def __init__(self, kb_path: Path, workspace_path: Path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self):
            return AgentQualityGateResult(
                passed=True,
                score=1.0,
                summary="fallback",
                evaluation={
                    "fallback": "rule-based",
                    "fallback_reason": "Not logged in · Please run /login",
                },
                recommendations=["Run `/login` in Claude Code to restore agent-based evaluation."],
                agent_reasoning="deterministic fallback",
            )

    import autonomous_agent_builder.knowledge as knowledge_module
    import autonomous_agent_builder.knowledge.agent_quality_gate as agent_quality_gate_module
    import autonomous_agent_builder.knowledge.document_spec as document_spec_module
    import autonomous_agent_builder.knowledge.quality_gate as quality_gate_module

    monkeypatch.setattr(knowledge_module, "KnowledgeExtractor", _FakeExtractor)
    monkeypatch.setattr(document_spec_module, "lint_directory", lambda *_, **__: (12, 0, 12))
    monkeypatch.setattr(quality_gate_module, "KnowledgeQualityGate", _FakeDeterministicGate)
    monkeypatch.setattr(agent_quality_gate_module, "AgentKnowledgeQualityGate", _FakeAgentGate)

    payload = kb_module._run_extract_pipeline(
        workspace_path=workspace_path,
        kb_path=kb_path,
        scope="full",
        run_validation=True,
    )

    assert payload["passed"] is True
    assert payload["validation"]["deterministic"]["passed"] is True
    assert payload["validation"]["agent_advisory"]["available"] is False
    assert payload["validation"]["agent_advisory"]["summary"] == ""
    assert payload["next_step"]["action"] == "continue"
    assert payload["next_step"]["target_phase"] == "kb_ready"


def test_extract_pipeline_continues_when_agent_advisory_is_unavailable(tmp_path, monkeypatch):
    workspace_path = tmp_path
    kb_path = workspace_path / ".agent-builder" / "knowledge" / "system-docs"
    kb_path.mkdir(parents=True)

    class _FakeExtractor:
        def __init__(self, workspace_path: Path, output_path: Path, *, doc_slugs=None):
            self.workspace_path = workspace_path
            self.output_path = output_path
            self.doc_slugs = doc_slugs

        def extract(self, scope: str = "full"):
            return {
                "documents": [
                    {
                        "type": "system-docs",
                        "title": "System Architecture",
                        "filename": "system-architecture.md",
                    }
                ],
                "errors": [],
            }

    class _FakeDeterministicGate:
        def __init__(self, kb_path: Path, workspace_path: Path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self):
            return QualityGateResult(
                passed=True,
                score=1.0,
                checks=[QualityCheck("specificity", True, 1.0, "passed")],
                summary="Quality Gate: PASSED (10/10 checks passed, score: 100.0%)",
            )

    class _FakeAgentGate:
        def __init__(self, kb_path: Path, workspace_path: Path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self):
            return AgentQualityGateResult(
                passed=True,
                score=1.0,
                summary="fallback",
                evaluation={
                    "fallback": "rule-based",
                    "fallback_reason": "Not logged in · Please run /login",
                },
                recommendations=["Run `/login` in Claude Code to restore agent-based evaluation."],
                agent_reasoning="deterministic fallback",
            )

    import autonomous_agent_builder.knowledge as knowledge_module
    import autonomous_agent_builder.knowledge.agent_quality_gate as agent_quality_gate_module
    import autonomous_agent_builder.knowledge.document_spec as document_spec_module
    import autonomous_agent_builder.knowledge.quality_gate as quality_gate_module

    monkeypatch.setattr(knowledge_module, "KnowledgeExtractor", _FakeExtractor)
    monkeypatch.setattr(document_spec_module, "lint_directory", lambda *_, **__: (12, 0, 12))
    monkeypatch.setattr(quality_gate_module, "KnowledgeQualityGate", _FakeDeterministicGate)
    monkeypatch.setattr(agent_quality_gate_module, "AgentKnowledgeQualityGate", _FakeAgentGate)

    payload = kb_module._run_extract_pipeline(
        workspace_path=workspace_path,
        kb_path=kb_path,
        scope="full",
        run_validation=True,
    )

    assert payload["passed"] is True
    assert payload["validation"]["deterministic"]["passed"] is True
    assert payload["validation"]["agent_advisory"]["available"] is False
    assert payload["validation"]["agent_advisory"]["summary"] == ""
    assert payload["next_step"]["action"] == "continue"
    assert payload["next_step"]["reason"] == "deterministic_validation_passed"
    assert payload["next_step"]["target_phase"] == "kb_ready"


def test_extract_command_passes_doc_slug_to_pipeline(monkeypatch):
    captured: dict[str, object] = {}

    def fake_pipeline(**kwargs):
        captured.update(kwargs)
        return {
            "documents": [
                {
                    "type": "system-docs",
                    "title": "System Architecture",
                    "filename": "system-architecture.md",
                }
            ],
            "errors": [],
            "passed": True,
            "validation": {},
            "next_step": {"action": "continue"},
        }

    monkeypatch.setattr(kb_module, "_run_extract_pipeline", fake_pipeline)

    with runner.isolated_filesystem():
        Path(".agent-builder").mkdir()
        result = runner.invoke(app, ["knowledge", "extract", "--doc", "system-architecture", "--json"])

    assert result.exit_code == 0
    assert captured["doc_slug"] == "system-architecture"


def test_extract_pipeline_ignores_non_blocking_generator_errors(tmp_path, monkeypatch):
    workspace_path = tmp_path
    kb_path = workspace_path / ".agent-builder" / "knowledge" / "system-docs"
    kb_path.mkdir(parents=True)

    class _FakeExtractor:
        def __init__(self, workspace_path: Path, output_path: Path, *, doc_slugs=None):
            self.workspace_path = workspace_path
            self.output_path = output_path
            self.doc_slugs = doc_slugs

        def extract(self, scope: str = "full"):
            return {
                "documents": [
                    {
                        "type": "system-docs",
                        "title": "System Architecture",
                        "filename": "system-architecture.md",
                    }
                ],
                "errors": [
                    {
                        "generator": "ProjectOverviewGenerator",
                        "slug": "project-overview",
                        "error": "non-authoritative doc failed",
                    }
                ],
            }

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
            )

    import autonomous_agent_builder.knowledge as knowledge_module
    import autonomous_agent_builder.knowledge.document_spec as document_spec_module
    import autonomous_agent_builder.knowledge.quality_gate as quality_gate_module

    monkeypatch.setattr(knowledge_module, "KnowledgeExtractor", _FakeExtractor)
    monkeypatch.setattr(document_spec_module, "lint_directory", lambda *_, **__: (1, 0, 1))
    monkeypatch.setattr(quality_gate_module, "KnowledgeQualityGate", _FakeDeterministicGate)

    payload = kb_module._run_extract_pipeline(
        workspace_path=workspace_path,
        kb_path=kb_path,
        scope="full",
        run_validation=True,
    )

    assert payload["passed"] is True
    assert payload["errors"][0]["slug"] == "project-overview"
    assert payload["next_step"]["reason"] == "deterministic_validation_passed_with_non_blocking_errors"


def test_extract_command_rejects_noncanonical_output_dir():
    with runner.isolated_filesystem():
        Path(".agent-builder").mkdir()
        result = runner.invoke(app, ["knowledge", "extract", "--output-dir", "scratch", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert payload["errors"] == [{"stage": "preflight", "error": "noncanonical_output_dir"}]
    assert payload["next_step"]["reason"] == "noncanonical_output_dir"
