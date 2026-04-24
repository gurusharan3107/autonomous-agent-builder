"""Tests for KB single-writer publishing and extractor write paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import autonomous_agent_builder.knowledge as knowledge_module
from autonomous_agent_builder.cli.main import app
from autonomous_agent_builder.knowledge.document_spec import DocumentLinter
from autonomous_agent_builder.knowledge.extractor import KnowledgeExtractor
from autonomous_agent_builder.knowledge.generators.base import BaseGenerator
from autonomous_agent_builder.knowledge.publisher import PublishError, publish_document
from autonomous_agent_builder.knowledge.quality_gate import KnowledgeQualityGate

runner = CliRunner()


class _DummyGenerator(BaseGenerator):
    def generate(self, scope: str = "full") -> dict[str, str] | None:
        return None


def _local_body() -> str:
    return (
        "## Overview\n\n"
        "This document explains the local KB publication workflow, why the builder CLI owns project-local knowledge bytes, and how operators should reason about the write path before changing knowledge surfaces.\n\n"
        "## Key points\n\n"
        "Only the CLI can publish KB bytes, agents may draft but not write directly, and the single-writer path preserves canonical frontmatter, versioning, and linter-backed format enforcement across the local collection.\n\n"
        "## Constraints or caveats\n\n"
        "Global publication is owned by workflow CLI, builder owns local KB bytes, and any change to the ownership boundary must preserve the current split between project retrieval and global article ingestion.\n\n"
        "## Operational next step\n\n"
        "Use builder knowledge update when changing an existing document, then rerun lint so the updated article still satisfies the local knowledge contract."
    )


def _global_body() -> str:
    return (
        "## Insight\n\n"
        "Single-writer KB publication prevents silent contract drift.\n\n"
        "## Evidence\n\n"
        "Legacy articles failed lint because provenance fields were never enforced.\n\n"
        "## Applicability\n\n"
        "Publish global articles through the CLI so missing provenance is surfaced immediately."
    )


def test_kb_add_local_and_dedupe(tmp_path, monkeypatch):
    local_root = tmp_path / ".agent-builder" / "knowledge"
    global_root = tmp_path / ".codex" / "knowledge"
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(local_root))
    monkeypatch.setenv("AAB_GLOBAL_KB_ROOT", str(global_root))

    result = runner.invoke(
        app,
        [
            "knowledge",
            "add",
            "--type",
            "context",
            "--title",
            "KB Publish Boundary",
            "--content",
            _local_body(),
            "--json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["scope"] == "local"
    assert payload["version"] == 1
    path = local_root / "context" / "kb-publish-boundary.md"
    assert path.exists()

    result = runner.invoke(
        app,
        [
            "knowledge",
            "add",
            "--type",
            "context",
            "--title",
            "KB Publish Boundary",
            "--content",
            _local_body(),
            "--json",
        ],
    )
    assert result.exit_code != 0
    assert (
        "already exists" in result.output
        or "Duplicate" in result.output
        or "unchanged" in result.output
    )


def test_document_linter_rejects_maintained_testing_doc_without_linkage_or_verification():
    markdown = (
        "---\n"
        "title: Broken Testing Doc\n"
        "tags:\n"
        "- testing\n"
        "doc_type: testing\n"
        "created: '2026-04-23T10:00:00'\n"
        "auto_generated: true\n"
        "doc_family: testing\n"
        "refresh_required: false\n"
        "documented_against_commit: daabd983e1c714e51bcff8940ded649cbd0b02bd\n"
        "documented_against_ref: main\n"
        "owned_paths:\n"
        "- tests/test_example.py\n"
        "---\n\n"
        "# Broken Testing Doc\n\n"
        "## Overview\n\n"
        "This doc is intentionally missing required maintained-doc metadata so the strict linter can reject it before publication.\n\n"
        "## Boundaries\n\n"
        "It claims to describe a testing surface.\n\n"
        "## Purpose\n\n"
        "Prove write-time enforcement exists.\n\n"
        "## Coverage\n\n"
        "One example test file.\n\n"
        "## Preconditions\n\n"
        "A strict linter run.\n\n"
        "## Procedure\n\n"
        "Attempt publication and expect a failure.\n\n"
        "## Evidence and follow-up\n\n"
        "Publication should fail before this enters the KB tree.\n"
    )

    linter = DocumentLinter(strict=True)
    assert linter.lint_content(markdown, "broken-testing-doc.md") is False
    report = linter.get_report()
    assert "require task or feature linkage" in report
    assert "require 'last_verified_at'" in report


def test_publish_document_rejects_maintained_testing_doc_without_linkage(tmp_path, monkeypatch):
    local_root = tmp_path / ".agent-builder" / "knowledge"
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(local_root))

    with pytest.raises(PublishError, match="require task or feature linkage"):
        publish_document(
            title="Broken Testing Doc",
            body=(
                "# Broken Testing Doc\n\n"
                "## Overview\n\n"
                "This doc is missing required maintained-doc linkage metadata and should fail at publish time.\n\n"
                "## Boundaries\n\n"
                "Testing surface only.\n\n"
                "## Purpose\n\n"
                "Exercise publish-time lint enforcement.\n\n"
                "## Coverage\n\n"
                "One broken example.\n\n"
                "## Preconditions\n\n"
                "A strict publish path.\n\n"
                "## Procedure\n\n"
                "Call publish_document.\n\n"
                "## Evidence and follow-up\n\n"
                "The write must be blocked.\n"
            ),
            doc_type="testing",
            tags=["testing"],
            scope="local",
            extra_fields={
                "doc_family": "testing",
                "documented_against_commit": "daabd983e1c714e51bcff8940ded649cbd0b02bd",
                "documented_against_ref": "main",
                "owned_paths": ["tests/test_example.py"],
                "last_verified_at": "2026-04-23",
                "refresh_required": False,
            },
        )


def test_kb_add_accepts_custom_tags_and_keeps_doc_type(tmp_path, monkeypatch):
    local_root = tmp_path / ".agent-builder" / "knowledge"
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(local_root))

    result = runner.invoke(
        app,
        [
            "knowledge",
            "add",
            "--type",
            "system-docs",
            "--tags",
            "feature,onboarding,feature",
            "--title",
            "Onboarding Modes and External Validation",
            "--content",
            (
                "# Onboarding Modes and External Validation\n\n"
                "This document captures onboarding mode behavior, generated artifacts, and the current embedded execution boundary for external validation.\n\n"
                "## Overview\n\n"
                "Onboarding is the canonical feature surface for initializing builder-managed state in a clean or existing repository, and it is the operator entrypoint that explains setup mode, generated artifacts, and when execution can safely proceed.\n\n"
                "## Boundaries\n\n"
                "This surface covers onboarding state, generated artifacts, embedded server validation, and external clean-repo checks. It does not own downstream task execution semantics or orchestrator dispatch behavior after planning is complete.\n\n"
                "## Invariants\n\n"
                "- Keep repo-local builder state under .agent-builder.\n"
                "- Keep generated onboarding backlog artifacts inspectable after the interview completes.\n"
                "- Keep onboarding retrieval grounded in one canonical local KB article when the operator asks how setup works.\n\n"
                "## Evidence\n\n"
                "External validation against a clean repo proved onboarding readiness, repo-local state creation, generated feature artifact output, and the current dispatch boundary. The same run showed that the operator can inspect progress through stable local surfaces without re-reading scattered code paths each time. It also confirmed that the KB article can carry feature-level tags through the CLI while remaining compliant with the system-docs retrieval contract.\n\n"
                "## Change guidance\n\n"
                "Refresh this document when onboarding artifacts or the external validation path changes."
            ),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["tags"] == ["system-docs", "seed", "feature", "onboarding"]

    path = local_root / "system-docs" / "onboarding-modes-and-external-validation.md"
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "- feature" in content
    assert "- onboarding" in content
    assert "- system-docs" in content


def test_kb_add_help_lists_supported_doc_types():
    result = runner.invoke(app, ["knowledge", "add", "--help"])

    assert result.exit_code == 0
    assert "system-docs" in result.stdout
    assert "metadata" in result.stdout
    assert "raw" in result.stdout
    assert "--documented-again" in result.stdout
    assert "--owned-paths" in result.stdout


def test_kb_update_bumps_version(tmp_path, monkeypatch):
    local_root = tmp_path / ".agent-builder" / "knowledge"
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(local_root))

    create = runner.invoke(
        app,
        [
            "knowledge",
            "add",
            "--type",
            "context",
            "--title",
            "Versioned Doc",
            "--content",
            _local_body(),
            "--json",
        ],
    )
    assert create.exit_code == 0
    created = json.loads(create.stdout)

    update = runner.invoke(
        app,
        [
            "knowledge",
            "update",
            created["id"],
            "--content",
            _local_body() + "\n\nExtra verification detail.",
            "--json",
        ],
    )
    assert update.exit_code == 0
    payload = json.loads(update.stdout)
    assert payload["version"] == 2


def test_kb_update_rewrites_tags_through_canonical_knowledge_surface(tmp_path, monkeypatch):
    local_root = tmp_path / ".agent-builder" / "knowledge"
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(local_root))

    create = runner.invoke(
        app,
        [
            "knowledge",
            "add",
            "--type",
            "context",
            "--title",
            "Knowledge Filtering Contract",
            "--feature",
            "--tag",
            "onboarding",
            "--content",
            _local_body(),
            "--json",
        ],
    )
    assert create.exit_code == 0
    created = json.loads(create.stdout)
    assert created["tags"] == ["context", "feature", "onboarding"]

    update = runner.invoke(
        app,
        [
            "knowledge",
            "update",
            created["id"],
            "--testing",
            "--tag",
            "browser",
            "--json",
        ],
    )
    assert update.exit_code == 0
    payload = json.loads(update.stdout)
    assert payload["tags"] == ["context", "testing", "browser"]


def test_kb_search_filters_by_tags(tmp_path, monkeypatch):
    local_root = tmp_path / ".agent-builder" / "knowledge"
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(local_root))

    first = runner.invoke(
        app,
        [
            "knowledge",
            "add",
            "--type",
            "context",
            "--title",
            "Feature Filter Doc",
            "--feature",
            "--tag",
            "onboarding",
            "--content",
            _local_body(),
            "--json",
        ],
    )
    assert first.exit_code == 0

    second = runner.invoke(
        app,
        [
            "knowledge",
            "add",
            "--type",
            "context",
            "--title",
            "Testing Filter Doc",
            "--testing",
            "--tag",
            "browser",
            "--content",
            _local_body(),
            "--json",
        ],
    )
    assert second.exit_code == 0

    search = runner.invoke(
        app,
        [
            "knowledge",
            "search",
            "filter",
            "--tag",
            "feature",
            "--json",
        ],
    )
    assert search.exit_code == 0
    payload = json.loads(search.stdout)
    assert payload["count"] == 1
    assert payload["results"][0]["title"] == "Feature Filter Doc"


def test_kb_add_global_is_rejected_with_workflow_hint(tmp_path, monkeypatch):
    local_root = tmp_path / ".agent-builder" / "knowledge"
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(local_root))

    result = runner.invoke(
        app,
        [
            "knowledge",
            "add",
            "--scope",
            "global",
            "--type",
            "raw",
            "--title",
            "Global KB Policy",
            "--content",
            _global_body(),
        ],
    )
    assert result.exit_code == 2
    assert "workflow knowledge ingest <file>" in result.output


def test_kb_update_global_is_rejected_with_workflow_hint(tmp_path, monkeypatch):
    local_root = tmp_path / ".agent-builder" / "knowledge"
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(local_root))

    result = runner.invoke(
        app,
        [
            "knowledge",
            "update",
            "raw/2026-03-27-legacy-article.md",
            "--scope",
            "global",
            "--source-author",
            "Anthropic",
            "--json",
        ],
    )
    assert result.exit_code == 2
    assert "workflow knowledge ingest <file>" in result.output


def test_publisher_rejects_global_scope_with_workflow_hint(tmp_path, monkeypatch):
    local_root = tmp_path / ".agent-builder" / "knowledge"
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(local_root))

    with pytest.raises(PublishError, match="workflow knowledge ingest <file>"):
        publish_document(
            title="Global KB Policy",
            body=_global_body(),
            doc_type="raw",
            tags=["evaluation"],
            scope="global",
            source_url="https://example.com/global-kb-policy",
            source_title="Global KB Policy",
            source_author="Test Author",
            date_published="2026-04-18",
        )


def test_extractor_helpers_publish_documents_through_collection(tmp_path, monkeypatch):
    local_root = tmp_path / ".agent-builder" / "knowledge"
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(local_root))

    extractor = KnowledgeExtractor(tmp_path, local_root / "system-docs")
    extractor._write_doc(
        "project-overview.md",
        {
            "title": "Project Overview",
            "doc_type": "system-docs",
            "tags": ["overview", "project", "delivery-system", "system-docs"],
            "wikilinks": ["System Architecture", "Technology Stack", "Workflows and Orchestration"],
            "content": (
                "## Overview\n\n"
                "Builder extracts project facts into durable local knowledge so operators and agents can understand the repository without re-reading the entire codebase every session, and so the dashboard and CLI share one stable system-docs surface.\n\n"
                "## Boundaries\n\n"
                "The CLI and API read from the same local KB root, while workflow CLI remains the owner for global article knowledge and external-source publication.\n\n"
                "## Invariants\n\n"
                "- Keep local KB publication owned by builder so generated repo docs stay canonical.\n"
                "- Preserve a single canonical write path so frontmatter, versions, and linter expectations remain aligned.\n\n"
                "## Evidence\n\n"
                "The repository contains extractor, publisher, API route, and CLI reader surfaces, all grounded in the same local knowledge directory and used by the dashboard and retrieval commands. This shared write and read path is what the single-writer contract is validating in this test fixture, and it proves that publication, retrieval, and UI consumption stay anchored to one canonical local corpus.\n\n"
                "## Change guidance\n\n"
                "Run lint after extraction to confirm document quality and verify that links, tags, and summaries still satisfy the system-docs contract."
            ),
        },
    )
    extractor._write_metadata(
        [
            {
                "type": "system-docs",
                "title": "Project Overview",
                "filename": "project-overview.md",
            }
        ],
        [],
        expected_documents=["project-overview"],
        blocking_documents=[],
        non_blocking_documents=["project-overview"],
    )

    linter = DocumentLinter(strict=True)
    assert linter.lint_file(local_root / "system-docs" / "project-overview.md")
    assert linter.lint_file(local_root / "system-docs" / "extraction-metadata.md")


def test_reverse_engineering_extractor_adds_tags_links_and_wikilinks(tmp_path, monkeypatch):
    local_root = tmp_path / ".agent-builder" / "knowledge"
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(local_root))

    extractor = KnowledgeExtractor(Path(__file__).resolve().parents[1], local_root / "system-docs")
    normalized = extractor._normalize_doc(
        {
            "title": "Workflows and Orchestration",
            "doc_type": "system-docs",
            "tags": ["workflow"],
            "content": (
                "## Overview\n\n"
                "Execution phases coordinate work across planning, implementation, and review.\n\n"
                "## Evidence\n\n"
                "The orchestrator dispatches based on phase state and routes work between roles.\n\n"
                "## Change guidance\n\n"
                "Update orchestrator evidence when flow definitions change."
            ),
        }
    )

    assert normalized["tags"] == ["workflows", "orchestration", "phases", "system-docs", "seed"]
    assert normalized["wikilinks"] == ["Agent System", "Project Overview", "System Architecture"]
    assert "## Related documents" in normalized["content"]
    assert "- [Agent System](agent-system.md)" in normalized["content"]
    assert "- [Project Overview](project-overview.md)" in normalized["content"]


def test_reverse_engineering_normalizer_strips_specificity_gate_markers(tmp_path, monkeypatch):
    local_root = tmp_path / ".agent-builder" / "knowledge"
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(local_root))

    extractor = KnowledgeExtractor(tmp_path, local_root / "system-docs")
    normalized = extractor._normalize_doc(
        {
            "title": "System Architecture",
            "doc_type": "system-docs",
            "tags": ["architecture"],
            "content": (
                "# System Architecture\n\n"
                "## Architecture Overview\n\n"
                "This document describes the high-level architecture of the system.\n\n"
                "## Integration Points\n\n"
                "- External APIs (if applicable)\n"
                "- File system\n"
            ),
        }
    )

    assert "This document describes" not in normalized["content"]
    assert "if applicable" not in normalized["content"]


def test_quality_gate_searchability_parses_yaml_list_tags(tmp_path):
    kb_root = tmp_path / "system-docs"
    kb_root.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (kb_root / "project-overview.md").write_text(
        "---\n"
        "title: Project Overview\n"
        "tags:\n"
        "- overview\n"
        "- project\n"
        "- delivery-system\n"
        "- system-docs\n"
        "doc_type: system-docs\n"
        "created: '2026-04-19T12:00:00'\n"
        "auto_generated: true\n"
        "version: 1\n"
        "---\n\n"
        "# Project Overview\n\n"
        "## Overview\n\n"
        "This document provides enough detail to satisfy the minimum quality thresholds while proving the quality gate can parse block-style YAML tag lists instead of only inline YAML arrays.\n"
    )

    gate = KnowledgeQualityGate(kb_root, workspace)
    check = gate._check_searchability()
    assert check.passed
    assert check.score == 1.0
    assert check.details["avg_tags"] == 4.0


def test_kb_extract_json_returns_machine_contract_on_success(tmp_path, monkeypatch):
    project_root = tmp_path
    (project_root / ".agent-builder").mkdir()
    monkeypatch.chdir(project_root)

    class FakeExtractor:
        def __init__(self, workspace_path, output_path, *, doc_slugs=None):
            self.output_path = output_path
            self.doc_slugs = doc_slugs

        def extract(self, scope="full"):
            self.output_path.mkdir(parents=True, exist_ok=True)
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

    class FakeDeterministicResult:
        passed = True
        score = 0.82
        summary = "Deterministic KB validation passed."

    class FakeDeterministicGate:
        def __init__(self, kb_path, workspace_path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self):
            return FakeDeterministicResult()

    monkeypatch.setattr(knowledge_module, "KnowledgeExtractor", FakeExtractor)
    monkeypatch.setattr("autonomous_agent_builder.knowledge.document_spec.lint_directory", lambda *_args, **_kwargs: (1, 0, 1))
    monkeypatch.setattr("autonomous_agent_builder.knowledge.quality_gate.KnowledgeQualityGate", FakeDeterministicGate)
    result = runner.invoke(app, ["knowledge", "extract", "--force", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["phase"] == "kb_extract"
    assert payload["engine"] == "deterministic"
    assert payload["lint"]["passed"] is True
    assert payload["validation"]["deterministic"]["passed"] is True
    assert payload["validation"]["agent_advisory"]["available"] is False
    assert payload["validation"]["agent_advisory"]["passed"] is False
    assert payload["next_step"]["action"] == "continue"


def test_kb_extract_json_returns_stop_contract_on_lint_failure(tmp_path, monkeypatch):
    project_root = tmp_path
    (project_root / ".agent-builder").mkdir()
    monkeypatch.chdir(project_root)

    class FakeExtractor:
        def __init__(self, workspace_path, output_path, *, doc_slugs=None):
            self.output_path = output_path
            self.doc_slugs = doc_slugs

        def extract(self, scope="full"):
            self.output_path.mkdir(parents=True, exist_ok=True)
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

    monkeypatch.setattr(knowledge_module, "KnowledgeExtractor", FakeExtractor)
    monkeypatch.setattr("autonomous_agent_builder.knowledge.document_spec.lint_directory", lambda *_args, **_kwargs: (0, 1, 1))

    result = runner.invoke(app, ["knowledge", "extract", "--force", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert payload["next_step"]["action"] == "stop"
    assert payload["next_step"]["reason"] == "lint_failed"
    assert payload["next_step"]["recommended_command"] == "builder knowledge lint --verbose"

def test_kb_extract_does_not_require_claude_preflight(tmp_path, monkeypatch):
    project_root = tmp_path
    (project_root / ".agent-builder").mkdir()
    monkeypatch.chdir(project_root)

    class FakeExtractor:
        def __init__(self, workspace_path, output_path, *, doc_slugs=None):
            self.output_path = output_path
            self.doc_slugs = doc_slugs

        def extract(self, scope="full"):
            self.output_path.mkdir(parents=True, exist_ok=True)
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

    monkeypatch.setattr(knowledge_module, "KnowledgeExtractor", FakeExtractor)
    monkeypatch.setattr("autonomous_agent_builder.knowledge.document_spec.lint_directory", lambda *_args, **_kwargs: (1, 0, 1))
    monkeypatch.setattr("autonomous_agent_builder.knowledge.quality_gate.KnowledgeQualityGate", lambda *_args, **_kwargs: type("Gate", (), {"validate": lambda self: type("Result", (), {"passed": True, "score": 1.0, "summary": "ok"})()})())

    result = runner.invoke(app, ["knowledge", "extract", "--force", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True


def test_kb_extract_help_mentions_canonical_orchestration_surface():
    result = runner.invoke(app, ["knowledge", "extract", "--help"])

    assert result.exit_code == 0
    assert "canonical owner for extraction" in result.stdout


def test_base_generator_skips_generated_and_archive_surfaces(tmp_path):
    src_file = tmp_path / "src" / "kept.py"
    src_file.parent.mkdir(parents=True)
    src_file.write_text("print('kept')\n", encoding="utf-8")

    generated_file = tmp_path / ".agent-builder" / "server" / "ignored.py"
    generated_file.parent.mkdir(parents=True)
    generated_file.write_text("print('ignored')\n", encoding="utf-8")

    archived_file = tmp_path / ".agent-builder.archive-20260419-150953" / "server" / "ignored.py"
    archived_file.parent.mkdir(parents=True)
    archived_file.write_text("print('ignored archive')\n", encoding="utf-8")

    generator = _DummyGenerator(tmp_path)
    files = generator._find_files("**/*.py", max_depth=5)

    assert src_file in files
    assert generated_file not in files
    assert archived_file not in files


def test_quality_gate_fails_on_generic_boilerplate(tmp_path):
    kb_root = tmp_path / "system-docs"
    kb_root.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "package.json").write_text('{\n  "name": "sample"\n}\n', encoding="utf-8")
    (kb_root / ".evidence").mkdir(parents=True)
    (kb_root / ".evidence" / "repo-index.json").write_text("{}", encoding="utf-8")
    (kb_root / ".evidence" / "technology-stack.json").write_text(
        json.dumps(
            {
                "doc": "technology-stack",
                "dependency_hash": "hash",
                "dependencies": ["package.json"],
                "claims": [
                    {
                        "section": "Overview",
                        "text": "Leaked builder template prose.",
                        "claim_type": "narrative_inference",
                        "citations": [
                            {
                                "path": "package.json",
                                "line_start": 1,
                                "line_end": 3,
                                "kind": "manifest",
                            }
                        ],
                    }
                ],
                "claim_types": ["narrative_inference"],
                "unresolved_claims": [],
                "contradicted_claims": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (kb_root / "technology-stack.md").write_text(
        "---\n"
        "title: Technology Stack\n"
        "tags:\n"
        "- system-docs\n"
        "- technology\n"
        "- stack\n"
        "doc_type: system-docs\n"
        "created: '2026-04-19T12:00:00'\n"
        "auto_generated: true\n"
        "version: 1\n"
        "verified: true\n"
        "authoritative: true\n"
        "evidence_manifest: .evidence/technology-stack.json\n"
        "dependency_hash: hash\n"
        "---\n\n"
        "# Technology Stack\n\n"
        "## Overview\n\n"
        "This builder CLI commands surface leaked from a template.\n",
        encoding="utf-8",
    )
    (kb_root / "extraction-metadata.md").write_text(
        "---\n"
        "title: Extraction Metadata\n"
        "tags:\n"
        "- metadata\n"
        "- system-docs\n"
        "doc_type: metadata\n"
        "created: '2026-04-19T12:00:00'\n"
        "auto_generated: true\n"
        "version: 1\n"
        "expected_documents:\n"
        "- technology-stack\n"
        "blocking_documents:\n"
        "- technology-stack\n"
        "non_blocking_documents: []\n"
        "---\n\n"
        "# Extraction Metadata\n",
        encoding="utf-8",
    )

    gate = KnowledgeQualityGate(kb_root, workspace)
    result = gate.validate()

    assert result.passed is False
    claim_validation = next(check for check in result.checks if check.name == "claim_validation")
    assert claim_validation.passed is False
    assert claim_validation.details is not None
    reasons = {item["reason"] for item in claim_validation.details["claim_failures"]}
    assert "disallowed_blocking_claim_type" in reasons or "template_leakage" in reasons


def test_extractor_treats_unchanged_documents_as_success(tmp_path, monkeypatch):
    local_root = tmp_path / ".agent-builder" / "knowledge"
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(local_root))

    extractor = KnowledgeExtractor(tmp_path, local_root / "system-docs")
    extractor._doc_profile = lambda _title: {
        "card_focus": "Project purpose, operating model, and what this repository is built to deliver.",
        "detail_focus": "Use this document to orient around the repository purpose, operator workflow, runtime shape, and the evidence surfaces that matter when refreshing local knowledge.",
        "overview_focus": "The repository turns project facts into durable local knowledge so operators and agents can inspect runtime structure, ownership boundaries, and next-step guidance without rereading the full codebase every time they need context.",
        "evidence_focus": "Use concrete repository structure, CLI surfaces, and published document paths as the proof surface.",
        "boundary_focus": "Primary boundaries include the extractor, publisher, CLI reader, and local knowledge collection that owns the generated files.",
        "invariant_focus": "Preserve the single-writer local knowledge path and the generated document contract.",
        "invariant_points": "Keep the local knowledge collection under builder ownership.|Regenerate artifacts when the underlying repository evidence changes.",
    }

    class FakeGenerator:
        def generate(self, scope="full"):
            return {
                "title": "Project Overview",
                "doc_type": "system-docs",
                "tags": ["overview"],
                "preserve_content": True,
                "content": (
                    "# Project Overview\n\n"
                    "## Overview\n\n"
                    "Builder extracts project facts into durable local knowledge so operators and agents can understand the repository without rereading the whole codebase, cross-check ownership boundaries, and refresh system-doc guidance after meaningful code changes.\n\n"
                    "## Boundaries\n\n"
                    "The generated document stays within the local builder-owned knowledge collection and does not try to publish global knowledge bytes.\n\n"
                    "## Invariants\n\n"
                    "- Preserve the single local write path so generated documents keep one canonical owner and do not drift into parallel publication paths.\n"
                    "- Preserve the published system-docs contract so titles, frontmatter, sections, and summaries stay readable for operators and retrieval clients.\n\n"
                    "## Evidence\n\n"
                    "The repository contains extractor, publisher, API route, and CLI reader surfaces grounded in one local knowledge directory, and this long-form evidence paragraph exists specifically so the strict section budget recognizes that the proof surface is substantive rather than placeholder prose or a short stub. It also explains why unchanged re-publishes should stay safe: the same canonical write path, same collection root, and same reader surfaces remain in place across repeated extraction runs.\n\n"
                    "## Change guidance\n\n"
                    "Run lint after extraction, verify the unchanged publish path still treats duplicate writes as success, and confirm the local collection remains the only writer-owned destination."
                ),
            }

    extractor.generators = [FakeGenerator()]

    first = extractor.extract()
    second = extractor.extract()

    assert first["errors"] == []
    assert second["errors"] == []
    assert second["documents"] == [
        {
            "type": "system-docs",
            "title": "Project Overview",
            "filename": "project-overview.md",
        }
    ]
