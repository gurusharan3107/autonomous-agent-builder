from __future__ import annotations

import json
from pathlib import Path

from autonomous_agent_builder.knowledge.architecture_evidence import (
    compute_dependency_hash,
    verify_evidence_manifest,
)
from autonomous_agent_builder.knowledge.generators.architecture import ArchitectureGenerator
from autonomous_agent_builder.knowledge.quality_gate import KnowledgeQualityGate


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_architecture_generator_emits_verified_manifest(tmp_path):
    output_path = tmp_path / "system-docs"
    generator = ArchitectureGenerator(_repo_root(), output_path=output_path)

    doc = generator.generate()

    manifest_path = output_path / ".evidence" / "system-architecture.json"
    graph_db_path = output_path / ".evidence" / "system-architecture.sqlite3"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert doc is not None
    assert doc["verified"] is True
    assert doc["evidence_manifest"] == ".evidence/system-architecture.json"
    assert manifest_path.exists()
    assert graph_db_path.exists()
    assert manifest["doc"] == "system-architecture"
    assert manifest["dependency_hash"] == doc["dependency_hash"]
    assert "## User mental model" in doc["content"]
    assert "## How work moves through the system" in doc["content"]
    assert "## Runtime diagram" in doc["content"]
    assert "## Lifecycle diagram" in doc["content"]
    assert "```mermaid" in doc["content"]
    assert "## Agent change map" in doc["content"]
    assert "## Evidence" in doc["content"]
    assert "## Proof for agents" in doc["content"]
    assert "src/autonomous_agent_builder/api/app.py" in doc["content"]
    assert "builder knowledge extract --force --doc system-architecture --json" in doc["content"]


def test_verify_evidence_manifest_rejects_invalid_line_range(tmp_path):
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    source_path = workspace_path / "src" / "example.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("value = 1\n", encoding="utf-8")

    manifest_path = tmp_path / "system-architecture.json"
    manifest_path.write_text(
        json.dumps(
            {
                "doc": "system-architecture",
                "source_commit": None,
                "extractor_version": "test",
                "dependency_hash": compute_dependency_hash(workspace_path, ["src/example.py"]),
                "dependencies": ["src/example.py"],
                "claims": [
                    {
                        "section": "Evidence",
                        "text": "Bad citation",
                        "citations": [
                            {
                                "path": "src/example.py",
                                "line_start": 1,
                                "line_end": 5,
                                "kind": "component",
                            }
                        ],
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    verification = verify_evidence_manifest(workspace_path, manifest_path)

    assert verification["valid"] is False
    assert any("Out-of-range citation" in issue for issue in verification["issues"])


def test_quality_gate_uses_targeted_expected_docs_and_manifest_freshness(tmp_path):
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    cited_file = workspace_path / "src" / "example.py"
    cited_file.parent.mkdir(parents=True)
    cited_file.write_text("class Example:\n    value = 1\n", encoding="utf-8")

    kb_path = tmp_path / ".agent-builder" / "knowledge" / "system-docs"
    evidence_dir = kb_path / ".evidence"
    evidence_dir.mkdir(parents=True)

    dependency_hash = compute_dependency_hash(workspace_path, ["src/example.py"])
    manifest_path = evidence_dir / "system-architecture.json"
    manifest_path.write_text(
        json.dumps(
            {
                "doc": "system-architecture",
                "source_commit": None,
                "extractor_version": "test",
                "dependency_hash": dependency_hash,
                "dependencies": ["src/example.py"],
                "claims": [
                    {
                        "section": "Evidence",
                        "text": "The architecture cites the example file.",
                        "citations": [
                            {
                                "path": "src/example.py",
                                "line_start": 1,
                                "line_end": 2,
                                "kind": "component",
                            }
                        ],
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (kb_path / "system-architecture.md").write_text(
        """---
title: System Architecture
tags:
  - architecture
  - system-docs
doc_type: system-docs
created: "2026-04-19T12:00:00"
auto_generated: true
version: 1
verified: true
authoritative: true
evidence_manifest: .evidence/system-architecture.json
dependency_hash: DEP_HASH
---
# System Architecture

## Overview

- The system is grounded in one cited file.

## Boundaries

- The example boundary is explicit.

## Invariants

- The cited file must stay in sync.

## Evidence

- `src/example.py:1-2` proves the pilot surface.

## Change guidance

- Run `builder knowledge extract --force --doc system-architecture --json` after changes.
""".replace("DEP_HASH", dependency_hash),
        encoding="utf-8",
    )
    (kb_path / "extraction-metadata.md").write_text(
        """---
title: Extraction Metadata
tags:
  - metadata
  - system-docs
doc_type: metadata
created: "2026-04-19T12:00:00"
auto_generated: true
version: 1
expected_documents:
  - system-architecture
blocking_documents:
  - system-architecture
non_blocking_documents: []
---
# Extraction Metadata

## Summary

Single-doc extraction.
""",
        encoding="utf-8",
    )
    (evidence_dir / "repo-index.json").write_text("{}", encoding="utf-8")

    gate = KnowledgeQualityGate(kb_path, workspace_path)

    assert gate._check_completeness().passed is True
    assert gate._check_citation_validity().passed is True
    assert gate._check_freshness().passed is True

    cited_file.write_text("class Example:\n    value = 2\n", encoding="utf-8")

    assert gate._check_freshness().passed is False


def test_quality_gate_ignores_inactive_maintained_docs_for_freshness(tmp_path):
    kb_path = tmp_path / ".agent-builder" / "knowledge" / "system-docs"
    kb_path.mkdir(parents=True)
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()

    (kb_path / "feature-doc.md").write_text(
        "---\n"
        "title: Feature Doc\n"
        "tags:\n"
        "- feature\n"
        "doc_type: feature\n"
        "doc_family: feature\n"
        "refresh_required: true\n"
        "lifecycle_status: superseded\n"
        "superseded_by: feature/replacement.md\n"
        "---\n\n"
        "# Feature Doc\n\n"
        "## Overview\n\n"
        "Old maintained doc.\n\n"
        "## Current behavior\n\n"
        "Old flow.\n\n"
        "## Boundaries\n\n"
        "Old boundaries.\n\n"
        "## Verification\n\n"
        "Old verification.\n\n"
        "## Change guidance\n\n"
        "Do not refresh.\n",
        encoding="utf-8",
    )
    (kb_path / "extraction-metadata.md").write_text(
        "---\n"
        "title: Extraction Metadata\n"
        "doc_type: metadata\n"
        "tags:\n"
        "- metadata\n"
        "---\n\n"
        "# Extraction Metadata\n\n"
        "## Summary\n\n"
        "Metadata.\n\n"
        "## Generated artifacts\n\n"
        "One doc.\n\n"
        "## Usage\n\n"
        "Use for testing.\n",
        encoding="utf-8",
    )

    gate = KnowledgeQualityGate(kb_path, workspace_path)
    assert gate._check_freshness().passed is True
