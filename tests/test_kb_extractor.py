from __future__ import annotations

from pathlib import Path

from autonomous_agent_builder.knowledge.extractor import KnowledgeExtractor
from autonomous_agent_builder.knowledge.generators.architecture import ArchitectureGenerator
from autonomous_agent_builder.knowledge.evidence_graph import build_shared_evidence_graph


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_api_endpoints_doc_uses_live_route_inventory(tmp_path):
    extractor = KnowledgeExtractor(_repo_root(), tmp_path / "knowledge")

    content = extractor._normalize_reverse_engineering_content(
        "API Endpoints",
        "# API Endpoints\n\n## Overview\n\nPlaceholder overview.\n",
    )

    assert "/api/onboarding/status" in content
    assert "/api/dashboard/board" in content
    assert "/api/kb/search" in content
    assert "/api/dispatch" in content


def test_configuration_doc_uses_real_env_prefixes(tmp_path):
    extractor = KnowledgeExtractor(_repo_root(), tmp_path / "knowledge")

    content = extractor._normalize_reverse_engineering_content(
        "Configuration",
        "# Configuration\n\n## Overview\n\nPlaceholder overview.\n",
    )

    assert "`DB_`" in content
    assert "`AGENT_`" in content
    assert "`HARNESS_`" in content
    assert "AAB_PORT" in content


def test_code_structure_doc_includes_touch_guidance(tmp_path):
    extractor = KnowledgeExtractor(_repo_root(), tmp_path / "knowledge")

    content = extractor._normalize_reverse_engineering_content(
        "Code Structure",
        "# Code Structure\n\n## Overview\n\nPlaceholder overview.\n",
    )

    assert "## What to touch when" in content
    assert "src/autonomous_agent_builder/api/" in content
    assert "src/autonomous_agent_builder/knowledge/" in content
    assert "src/autonomous_agent_builder/orchestrator/" in content


def test_workflows_doc_includes_dispatch_and_onboarding_phases(tmp_path):
    extractor = KnowledgeExtractor(_repo_root(), tmp_path / "knowledge")

    content = extractor._normalize_reverse_engineering_content(
        "Workflows and Orchestration",
        "# Workflows and Orchestration\n\n## Overview\n\nPlaceholder overview.\n",
    )

    assert "pending -> planning" in content
    assert "quality_gates -> quality-gates" in content
    assert "`repo_detect`" in content
    assert "`kb_validate`" in content


def test_extractor_can_limit_generation_to_one_doc(tmp_path):
    extractor = KnowledgeExtractor(_repo_root(), tmp_path / "knowledge", doc_slugs=["system-architecture"])

    result = extractor.extract()

    generated = {document["filename"] for document in result["documents"]}
    assert generated == {"system-architecture.md"}
    assert (tmp_path / "knowledge" / ".evidence" / "system-architecture.json").exists()


def test_code_structure_grounded_blocks_handle_external_repo_layout(tmp_path):
    (tmp_path / "src" / "flask").mkdir(parents=True)
    (tmp_path / "src" / "flask" / "__init__.py").write_text("", encoding="utf-8")
    extractor = KnowledgeExtractor(tmp_path, tmp_path / ".agent-builder" / "knowledge" / "system-docs")

    blocks = extractor._grounded_evidence_blocks("Code Structure")

    assert blocks
    assert "### Package map" in blocks[0]
    assert "`flask`" in blocks[0]


def test_architecture_generator_falls_back_for_non_builder_repo(tmp_path):
    (tmp_path / "src" / "flask").mkdir(parents=True)
    (tmp_path / "src" / "flask" / "app.py").write_text("app = object()\n", encoding="utf-8")
    output_path = tmp_path / ".agent-builder" / "knowledge" / "system-docs"
    generator = ArchitectureGenerator(tmp_path, output_path=output_path)

    doc = generator.generate()

    assert doc is not None
    assert doc["title"] == "System Architecture"
    assert doc["verified"] is True
    assert "## Boundaries" in doc["content"]
    assert (output_path / ".evidence" / "system-architecture.json").exists()


def test_extraction_metadata_expected_docs_match_generated_for_external_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='sample'\nversion='0.1.0'\n", encoding="utf-8")
    (tmp_path / "src" / "sample").mkdir(parents=True)
    (tmp_path / "src" / "sample" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "sample" / "app.py").write_text("app = object()\n", encoding="utf-8")

    output = tmp_path / ".agent-builder" / "knowledge" / "system-docs"
    extractor = KnowledgeExtractor(tmp_path, output, doc_slugs=["system-architecture"])
    captured: dict[str, list[str]] = {}

    def _capture_metadata(
        documents,
        errors,
        *,
        expected_documents,
        blocking_documents,
        non_blocking_documents,
    ):
        del documents, errors, blocking_documents, non_blocking_documents
        captured["expected"] = list(expected_documents)

    extractor._write_metadata = _capture_metadata  # type: ignore[method-assign]
    result = extractor.extract()

    generated = {Path(doc["filename"]).stem for doc in result["documents"]}
    expected = set(captured.get("expected", []))

    assert generated
    assert expected == generated


def test_targeted_extract_preserves_existing_collection_metadata(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='sample'\nversion='0.1.0'\ndependencies=['fastapi']\n",
        encoding="utf-8",
    )
    output = tmp_path / ".agent-builder" / "knowledge" / "system-docs"
    output.mkdir(parents=True)
    for slug in ("system-architecture", "dependencies", "technology-stack"):
        (output / f"{slug}.md").write_text(f"# {slug}\n", encoding="utf-8")

    extractor = KnowledgeExtractor(tmp_path, output, doc_slugs=["technology-stack"])
    captured: dict[str, list[str]] = {}

    class FakeGenerator:
        def generate(self, scope="full"):
            del scope
            return {
                "title": "Technology Stack",
                "doc_type": "system-docs",
                "tags": ["technology", "stack"],
                "preserve_content": True,
                "content": (
                    "# Technology Stack\n\n"
                    "## Overview\n\n"
                    "FastAPI with a Python backend.\n\n"
                    "## Boundaries\n\n"
                    "Covers runtime and toolchain surfaces.\n\n"
                    "## Invariants\n\n"
                    "- Keep dependency metadata aligned with manifests.\n\n"
                    "## Evidence\n\n"
                    "The repository declares FastAPI in pyproject.toml.\n\n"
                    "## Change guidance\n\n"
                    "Refresh after manifest changes.\n"
                ),
            }

    extractor.generators = [FakeGenerator()]
    extractor._generator_slugs = {id(extractor.generators[0]): "technology-stack"}

    def _capture_metadata(
        documents,
        errors,
        *,
        expected_documents,
        blocking_documents,
        non_blocking_documents,
    ):
        del documents, errors
        captured["expected"] = list(expected_documents)
        captured["blocking"] = list(blocking_documents)
        captured["non_blocking"] = list(non_blocking_documents)

    extractor._write_metadata = _capture_metadata  # type: ignore[method-assign]
    extractor.extract()

    assert captured["expected"] == ["dependencies", "system-architecture", "technology-stack"]
    assert captured["blocking"] == ["system-architecture", "dependencies", "technology-stack"]
    assert captured["non_blocking"] == []


def test_non_builder_generators_emit_contract_compliant_docs(tmp_path):
    (tmp_path / "README.md").write_text(
        "# Support Desk\n\nSupport operators triage tickets and monitor SLA breaches.\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='support-desk'\nversion='0.1.0'\ndependencies=['fastapi']\n",
        encoding="utf-8",
    )
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "routes.py").write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/tickets')\n\n"
        "@router.get('')\n"
        "def list_tickets(queue: str) -> list[str]:\n"
        "    \"\"\"List tickets in the support queue.\"\"\"\n"
        "    return []\n",
        encoding="utf-8",
    )
    (tmp_path / "app" / "models.py").write_text(
        'class Ticket:\n    """Support request raised by a customer."""\n    pass\n',
        encoding="utf-8",
    )
    (tmp_path / "app" / "services.py").write_text(
        'class TriageService:\n    """Routes tickets to the right queue based on urgency."""\n    pass\n',
        encoding="utf-8",
    )
    (tmp_path / "app" / "validators.py").write_text(
        'def validate_priority():\n    """Ensure urgent tickets always have an owner."""\n    return True\n',
        encoding="utf-8",
    )
    output = tmp_path / ".agent-builder" / "knowledge" / "system-docs"
    extractor = KnowledgeExtractor(
        tmp_path,
        output,
        doc_slugs=["project-overview", "code-structure", "api-endpoints", "business-overview"],
    )

    result = extractor.extract()

    assert result["errors"] == []


def test_project_overview_ignores_readme_badge_markup(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text(
        "# Full Stack FastAPI Template\n\n"
        '<a href="https://github.com/example/actions"><img src="badge.svg" alt="Build"></a>\n'
        '<a href="https://example.com/coverage"><img src="coverage.svg" alt="Coverage"></a>\n\n'
        "Production-ready FastAPI and React application template for teams shipping CRUD, authentication, "
        "admin workflows, background jobs, and deployment automation without rebuilding the stack from scratch.\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='fastapi-full-stack-template'\nversion='0.1.0'\n",
        encoding="utf-8",
    )
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "AAB_LOCAL_KB_ROOT", str(tmp_path / ".agent-builder" / "knowledge")
    )

    output = tmp_path / ".agent-builder" / "knowledge" / "system-docs"
    extractor = KnowledgeExtractor(tmp_path, output, doc_slugs=["project-overview"])

    result = extractor.extract()

    assert result["errors"] == []
    published = sorted(tmp_path.rglob("project-overview.md"))
    assert published
    content = published[0].read_text(encoding="utf-8")
    assert "<img" not in content
    assert "## Overview" in content
    assert "## Boundaries" in content
    assert "## Invariants" in content
    assert "## Evidence" in content
    assert "## Change guidance" in content


def test_external_repo_blocking_and_configuration_docs_normalize_to_system_doc_shape(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text(
        "# Flasky Clone\n\n"
        "A small Flask application with configuration classes, templates, tests, and package manifests that "
        "should still produce canonical builder system-docs during reverse-engineering extraction.\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.0.0\n"
        "Flask-SQLAlchemy==3.1.1\n"
        "Flask-Login==0.6.3\n"
        "pytest==8.4.2\n",
        encoding="utf-8",
    )
    (tmp_path / "config.py").write_text(
        "class Config:\n"
        "    SECRET_KEY: str = 'dev'\n"
        "    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False\n\n"
        "class DevelopmentConfig(Config):\n"
        "    DEBUG: bool = True\n\n"
        "class TestingConfig(Config):\n"
        "    TESTING: bool = True\n\n"
        "class ProductionConfig(Config):\n"
        "    DEBUG: bool = False\n",
        encoding="utf-8",
    )
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("from flask import Flask\napp = Flask(__name__)\n", encoding="utf-8")
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "AAB_LOCAL_KB_ROOT", str(tmp_path / ".agent-builder" / "knowledge")
    )

    output = tmp_path / ".agent-builder" / "knowledge" / "system-docs"
    extractor = KnowledgeExtractor(
        tmp_path,
        output,
        doc_slugs=["project-overview", "technology-stack", "dependencies", "configuration"],
    )

    result = extractor.extract()

    assert result["errors"] == []
    for filename in (
        "project-overview.md",
        "technology-stack.md",
        "dependencies.md",
        "configuration.md",
    ):
        path = output / filename
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "## Overview" in content
        assert "## Boundaries" in content
        assert "## Invariants" in content
        assert "## Evidence" in content
        assert "## Change guidance" in content


def test_shared_graph_detects_top_level_flask_entrypoint(tmp_path):
    (tmp_path / "requirements.txt").write_text("Flask==3.0.0\n", encoding="utf-8")
    (tmp_path / "flasky.py").write_text(
        "from flask import Flask\n"
        "app = Flask(__name__)\n\n"
        "@app.cli.command()\n"
        "def hello():\n"
        "    return 'hello'\n",
        encoding="utf-8",
    )

    graph = build_shared_evidence_graph(
        tmp_path,
        tmp_path / ".agent-builder" / "knowledge" / "system-docs",
    )

    entrypoints = [
        node["properties"]["path"]
        for node in graph["nodes"]
        if node.get("kind") == "entrypoint"
    ]
    assert "flasky.py" in entrypoints
