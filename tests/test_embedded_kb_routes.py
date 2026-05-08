from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from autonomous_agent_builder.embedded.server.app import create_app
from autonomous_agent_builder.embedded.server.routes.knowledge_extraction import (
    ExtractionRequest,
)


@pytest.mark.asyncio
async def test_embedded_kb_routes_parse_multiline_frontmatter_tags(monkeypatch, tmp_path):
    knowledge_root = tmp_path / ".agent-builder" / "knowledge" / "system-docs"
    knowledge_root.mkdir(parents=True)
    (knowledge_root / "system-architecture.md").write_text(
        "---\n"
        'title: "System Architecture \\u2014 Runtime Map"\n'
        "tags:\n"
        "- architecture\n"
        "- runtime\n"
        "- system-docs\n"
        "version: 3\n"
        "---\n\n"
        "# System Architecture\n\n"
        "Runtime boundaries and ownership.\n",
        encoding="utf-8",
    )
    (knowledge_root / "technology-stack.md").write_text(
        "---\n"
        "title: Technology Stack\n"
        "tags:\n"
        "- runtime\n"
        "- system-docs\n"
        "---\n\n"
        "# Technology Stack\n\n"
        "Python and React stack summary.\n",
        encoding="utf-8",
    )

    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )

    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    monkeypatch.chdir(tmp_path)

    app = create_app(db_path=db_path, dashboard_path=dashboard_root, project_root=tmp_path)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        docs_response = await client.get("/api/kb/", params={"scope": "local"})
        assert docs_response.status_code == 200
        docs = docs_response.json()
        assert docs[0]["tags"] == ["architecture", "runtime", "system-docs"]
        assert docs[0]["title"] == "System Architecture — Runtime Map"
        assert docs[0]["version"] == 3

        tags_response = await client.get("/api/kb/tags", params={"scope": "local"})
        assert tags_response.status_code == 200
        tag_names = [tag["name"] for tag in tags_response.json()]
        assert "" not in tag_names
        assert "architecture" in tag_names
        assert "runtime" in tag_names

        related_response = await client.get(
            "/api/kb/system-docs/system-architecture.md/related",
            params={"scope": "local"},
        )
        assert related_response.status_code == 200
        related = related_response.json()["similar"]
        assert set(related[0]["shared_tags"]) == {"system-docs", "runtime"}
        assert related[0]["title"] == "Technology Stack"

        doc_response = await client.get(
            "/api/kb/system-docs/system-architecture.md",
            params={"scope": "local"},
        )
        assert doc_response.status_code == 200
        assert doc_response.json()["title"] == "System Architecture — Runtime Map"
        assert doc_response.json()["version"] == 3


@pytest.mark.asyncio
async def test_knowledge_documents_route_reads_all_local_knowledge_folders(monkeypatch, tmp_path):
    reverse_engineering_root = tmp_path / ".agent-builder" / "knowledge" / "system-docs"
    feature_root = tmp_path / ".agent-builder" / "knowledge" / "feature"
    reverse_engineering_root.mkdir(parents=True)
    feature_root.mkdir(parents=True)

    (reverse_engineering_root / "project-overview.md").write_text(
        "---\n"
        "title: Project Overview\n"
        "tags:\n"
        "- system-docs\n"
        "---\n\n"
        "# Project Overview\n\n"
        "Repository overview.\n",
        encoding="utf-8",
    )
    (feature_root / "onboarding.md").write_text(
        "---\n"
        "title: Onboarding Feature\n"
        "tags:\n"
        "- feature\n"
        "- onboarding\n"
        "---\n\n"
        "# Onboarding Feature\n\n"
        "Feature behavior and operator expectations.\n",
        encoding="utf-8",
    )

    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )

    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    monkeypatch.chdir(tmp_path)

    app = create_app(db_path=db_path, dashboard_path=dashboard_root, project_root=tmp_path)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        docs_response = await client.get("/api/knowledge/documents")
        assert docs_response.status_code == 200
        payload = docs_response.json()
        assert payload["total"] == 2
        assert {doc["filename"] for doc in payload["documents"]} == {
            "feature/onboarding.md",
            "system-docs/project-overview.md",
        }
        assert {doc["doc_type"] for doc in payload["documents"]} == {
            "feature",
            "system-docs",
        }

        status_response = await client.get("/api/knowledge/status")
        assert status_response.status_code == 200
        assert status_response.json()["document_count"] == 2


@pytest.mark.asyncio
async def test_knowledge_document_route_accepts_nested_paths(monkeypatch, tmp_path):
    feature_root = tmp_path / ".agent-builder" / "knowledge" / "feature"
    feature_root.mkdir(parents=True)
    (feature_root / "onboarding.md").write_text(
        "---\n"
        "title: Onboarding Feature\n"
        "tags:\n"
        "- feature\n"
        "- onboarding\n"
        "created: 2026-04-21T18:00:00\n"
        "auto_generated: false\n"
        "version: 1\n"
        "---\n\n"
        "# Onboarding Feature\n\n"
        "Feature behavior and operator expectations.\n",
        encoding="utf-8",
    )

    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>",
        encoding="utf-8",
    )

    db_path = tmp_path / ".agent-builder" / "agent_builder.db"
    monkeypatch.chdir(tmp_path)

    app = create_app(db_path=db_path, dashboard_path=dashboard_root, project_root=tmp_path)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        doc_response = await client.get("/api/knowledge/documents/feature/onboarding.md")
        assert doc_response.status_code == 200
        payload = doc_response.json()
        assert payload["filename"] == "feature/onboarding.md"
        assert payload["frontmatter"]["doc_type"] == "feature"
        assert payload["frontmatter"]["tags"] == ["feature", "onboarding"]


def test_extraction_request_accepts_validate_alias():
    request = ExtractionRequest.model_validate({"validate": False})
    assert request.run_validation is False

    payload = request.model_dump(by_alias=True)
    assert payload["validate"] is False
    assert "run_validation" not in payload
