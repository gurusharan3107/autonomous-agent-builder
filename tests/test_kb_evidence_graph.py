from __future__ import annotations

import json
from pathlib import Path

from autonomous_agent_builder.cli.commands import kb as kb_module
from autonomous_agent_builder.knowledge.evidence_graph import (
    build_shared_evidence_graph,
    render_blocking_doc,
)
from autonomous_agent_builder.knowledge.extractor import KnowledgeExtractor
from autonomous_agent_builder.knowledge.quality_gate import KnowledgeQualityGate


def _seed_fastapi_repo(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        "[project]\n"
        "name='sample'\n"
        "version='0.1.0'\n"
        "dependencies=['fastapi>=0.115.0']\n",
        encoding="utf-8",
    )
    (root / "src" / "sample").mkdir(parents=True)
    (root / "src" / "sample" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "sample" / "app.py").write_text("app = object()\n", encoding="utf-8")


def test_shared_evidence_graph_is_byte_stable_for_same_repo(tmp_path):
    _seed_fastapi_repo(tmp_path)
    collection = tmp_path / ".agent-builder" / "knowledge" / "system-docs"
    collection.mkdir(parents=True)

    build_shared_evidence_graph(tmp_path, collection)
    first = (collection / ".evidence" / "graph.json").read_text(encoding="utf-8")

    build_shared_evidence_graph(tmp_path, collection)
    second = (collection / ".evidence" / "graph.json").read_text(encoding="utf-8")

    assert first == second


def test_extract_pipeline_reports_graph_metadata_for_blocking_docs(tmp_path, monkeypatch):
    _seed_fastapi_repo(tmp_path)
    kb_path = tmp_path / ".agent-builder" / "knowledge" / "system-docs"
    kb_path.mkdir(parents=True)
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(tmp_path / ".agent-builder" / "knowledge"))

    payload = kb_module._run_extract_pipeline(
        workspace_path=tmp_path,
        kb_path=kb_path,
        scope="full",
        run_validation=False,
        doc_slug="system-architecture",
    )

    assert payload["passed"] is True
    assert payload["graph"]["artifact_path"].endswith(".evidence/graph.json")
    assert payload["graph"]["workspace_profile"] == "python_fastapi_service"
    assert payload["validation"]["deterministic"]["summary"] == "Validation skipped by request."


def test_quality_gate_exposes_graph_metadata_for_external_repo(tmp_path, monkeypatch):
    _seed_fastapi_repo(tmp_path)
    collection = tmp_path / ".agent-builder" / "knowledge" / "system-docs"
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(tmp_path / ".agent-builder" / "knowledge"))
    extractor = KnowledgeExtractor(tmp_path, collection, doc_slugs=["system-architecture"])
    result = extractor.extract()

    assert result["errors"] == []

    gate = KnowledgeQualityGate(collection, tmp_path).validate()

    assert gate.passed is True
    assert gate.workspace_profile == "python_fastapi_service"
    assert gate.graph_artifact.endswith(".evidence/graph.json")
    assert gate.blocking_render_status["system-architecture"]["rendered_from_graph"] is True
    assert gate.unresolved_item_counts["system-architecture"] == 0

    graph = json.loads((collection / ".evidence" / "graph.json").read_text(encoding="utf-8"))
    doc = (collection / "system-architecture.md").read_text(encoding="utf-8")
    assert graph["workspace_profile"] == "python_fastapi_service"
    assert "src/autonomous_agent_builder/" not in doc


def test_shared_evidence_graph_ignores_claude_worktrees(tmp_path):
    _seed_fastapi_repo(tmp_path)
    collection = tmp_path / ".agent-builder" / "knowledge" / "system-docs"
    collection.mkdir(parents=True)

    leaked_route = (
        tmp_path
        / ".claude"
        / "worktrees"
        / "test-access"
        / "src"
        / "autonomous_agent_builder"
        / "embedded"
        / "server"
        / "routes"
        / "knowledge_extraction.py"
    )
    leaked_route.parent.mkdir(parents=True)
    leaked_route.write_text(
        "from fastapi import APIRouter\n"
        'router = APIRouter(prefix="/leak")\n'
        '@router.get("/bad")\n'
        "def bad():\n"
        "    return {}\n",
        encoding="utf-8",
    )

    graph = build_shared_evidence_graph(tmp_path, collection)
    doc = render_blocking_doc(
        "system-architecture",
        graph,
        workspace_path=tmp_path,
        collection_path=collection,
    )

    serialized = json.dumps(graph)
    assert ".claude/worktrees/test-access" not in serialized
    assert ".claude/worktrees/test-access" not in doc["content"]
