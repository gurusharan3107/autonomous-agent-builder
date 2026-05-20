from __future__ import annotations

from types import SimpleNamespace

import pytest

from autonomous_agent_builder.embedded.server import agent_documentation_context as context


def test_doc_context_view_returns_compact_payload_when_source_missing(tmp_path) -> None:
    payload = context.doc_context_view(
        tmp_path,
        {
            "id": "feature/example.md",
            "title": "Example",
            "doc_type": "feature",
            "tags": ("agent", "docs"),
            "card_summary": "Card",
            "detail_summary": "Detail",
        },
    )

    assert payload == {
        "id": "feature/example.md",
        "title": "Example",
        "doc_type": "feature",
        "task_id": "",
        "doc_family": "",
        "tags": ["agent", "docs"],
        "card_summary": "Card",
        "detail_summary": "Detail",
    }


def test_search_targeted_docs_prefers_required_docs_and_deduplicates(monkeypatch, tmp_path) -> None:
    local_docs = [
        {"id": "feature/required.md", "doc_type": "feature", "title": "Required"},
        {"id": "feature/other.md", "doc_type": "feature", "title": "Other"},
    ]

    monkeypatch.setattr(context, "load_docs", lambda *, scope: list(local_docs))
    monkeypatch.setattr(
        context,
        "search_docs",
        lambda query, *, scope, limit: [
            {"id": "feature/required.md", "doc_type": "feature", "title": "Required"},
            {"id": "feature/other.md", "doc_type": "feature", "title": "Other"},
        ],
    )
    monkeypatch.setattr(
        context,
        "doc_context_view",
        lambda _project_root, doc: {"id": doc["id"], "title": doc["title"]},
    )
    task = SimpleNamespace(
        title="Task",
        feature=SimpleNamespace(title="Feature"),
        feature_id="feature-1",
        depends_on={"system_docs": {"required_docs": ["feature/required.md"]}},
    )

    docs = context.search_targeted_docs(tmp_path, query="docs", task=task, limit=4)

    assert docs == [
        {"id": "feature/required.md", "title": "Required"},
        {"id": "feature/other.md", "title": "Other"},
    ]


@pytest.mark.asyncio
async def test_documentation_context_pack_builds_forced_route(monkeypatch, tmp_path) -> None:
    task = SimpleNamespace(
        id="task-1",
        title="Refresh docs",
        description="Update feature docs",
        feature_id="feature-1",
        feature=SimpleNamespace(title="Feature", description="Feature docs"),
        depends_on={"system_docs": {"required_docs": ["feature/required.md"]}},
    )
    monkeypatch.setattr(context, "latest_task_context", lambda _db: _async_value(task))
    monkeypatch.setattr(
        context,
        "search_targeted_docs",
        lambda _project_root, *, query, task, limit: [{"id": "feature/required.md"}],
    )
    monkeypatch.setattr(context, "git_current_branch", lambda _project_root: "feature/docs")
    monkeypatch.setattr(context, "resolve_canonical_doc_ref", lambda _project_root: "main")
    monkeypatch.setattr(context, "git_head_for_ref", lambda _project_root, _ref: "abc123")
    monkeypatch.setattr(context, "freshness_candidates", lambda _project_root: [{"doc_id": "doc"}])

    pack = await context.documentation_context_pack(
        db=object(),
        project_root=tmp_path,
        user_message="please update docs",
        route_reason_override="continuation",
        force_route=True,
    )

    assert pack is not None
    assert pack["route_reason"] == "continuation"
    assert pack["canonical_refresh_mode"] == "advisory_only"
    assert pack["targeted_docs"] == [{"id": "feature/required.md"}]
    assert pack["task"]["required_docs"] == ["feature/required.md"]
    assert pack["freshness_candidates"] == [{"doc_id": "doc"}]


async def _async_value(value):
    return value
