"""Tests for knowledge.retrieval — cache + preview-only scoring (Council 2026-05-08 Item 5)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from autonomous_agent_builder.knowledge import retrieval


def _write_context_doc(root: Path, file_name: str, *, title: str, body: str) -> None:
    path = root / "context" / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
title: {title}
doc_type: context
tags: [context]
---
# {title}

{body}
""",
        encoding="utf-8",
    )


@pytest.fixture
def kb_root(tmp_path, monkeypatch):
    """Stub a local KB root with two documents."""
    root = tmp_path / "kb" / "context"
    root.mkdir(parents=True)
    (root / "doc-a.md").write_text(
        """---
title: Auth Boundary
doc_type: context
tags: [security, boundary]
card_summary: OneCLI is the local auth boundary.
detail_summary: All Claude child processes must receive scrubbed env.
---
# Auth Boundary

Body content with the word PROVIDER_AUTH_ENV_KEYS appearing here only.
""",
        encoding="utf-8",
    )
    (root / "doc-b.md").write_text(
        """---
title: Phase Model
doc_type: context
tags: [orchestrator, phase]
card_summary: Orchestrator is the single writer for phase transitions.
detail_summary: Provider-limit is a first-class blocked state.
---
# Phase Model

Body content mentioning PROVIDER_AUTH_ENV_KEYS in the body only.
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        retrieval,
        "knowledge_root",
        lambda scope="local": tmp_path / "kb" if scope != "global" else tmp_path / "global",
    )
    retrieval.reset_docs_cache()
    yield tmp_path / "kb"
    retrieval.reset_docs_cache()


def test_load_docs_caches_by_root_mtime(kb_root, monkeypatch):
    calls = {"count": 0}
    real_serialize = retrieval._serialize_doc

    def counting_serialize(path, scope):
        calls["count"] += 1
        return real_serialize(path, scope)

    monkeypatch.setattr(retrieval, "_serialize_doc", counting_serialize)

    first = retrieval.load_docs("local")
    after_first = calls["count"]
    assert after_first == 2

    second = retrieval.load_docs("local")
    assert calls["count"] == after_first, "second call should be served from cache"
    assert second is first or second == first


def test_load_docs_invalidates_when_root_mtime_changes(kb_root, monkeypatch):
    retrieval.load_docs("local")
    cached_size = len(retrieval._DOCS_CACHE)
    assert cached_size >= 1

    new_doc = kb_root / "context" / "doc-c.md"
    new_doc.write_text(
        """---
title: New Doc
doc_type: context
---
# New Doc

Fresh body.
""",
        encoding="utf-8",
    )
    # Bump the kb root mtime explicitly — the cache key is the root mtime,
    # which won't always update from a nested-file change on every filesystem.
    future = time.time() + 5
    os.utime(kb_root, (future, future))

    refreshed = retrieval.load_docs("local")
    assert any(doc["title"] == "New Doc" for doc in refreshed)


def test_load_docs_cache_isolated_by_resolved_root_with_same_mtime(tmp_path, monkeypatch):
    root_a = tmp_path / "project-a" / ".agent-builder" / "knowledge"
    root_b = tmp_path / "project-b" / ".agent-builder" / "knowledge"
    _write_context_doc(root_a, "doc-a.md", title="Project A Doc", body="Only project A.")
    _write_context_doc(root_b, "doc-b.md", title="Project B Doc", body="Only project B.")
    timestamp = time.time() + 10
    os.utime(root_a, (timestamp, timestamp))
    os.utime(root_b, (timestamp, timestamp))

    selected_root = {"path": root_a}
    monkeypatch.setattr(
        retrieval,
        "knowledge_root",
        lambda scope="local": selected_root["path"]
        if scope != "global"
        else tmp_path / "global",
    )
    retrieval.reset_docs_cache()

    first = retrieval.load_docs("local")
    selected_root["path"] = root_b
    second = retrieval.load_docs("local")

    assert [doc["title"] for doc in first] == ["Project A Doc"]
    assert [doc["title"] for doc in second] == ["Project B Doc"]
    assert len(retrieval._DOCS_CACHE) == 2
    retrieval.reset_docs_cache()


def test_score_doc_default_skips_full_content_body(kb_root):
    doc = {
        "title": "Some Doc",
        "tags": ["security"],
        "card_summary": "",
        "detail_summary": "",
        "preview": "irrelevant preview",
        "content": "this body mentions provider_auth_env_keys exactly once",
    }
    score_default = retrieval._score_doc(doc, "provider_auth_env_keys")
    score_deep = retrieval._score_doc(doc, "provider_auth_env_keys", deep=True)

    assert score_default == 0, "default scoring must not match content body"
    assert score_deep > 0, "deep scoring must include the content body"


def test_search_docs_strips_content_from_results_by_default(kb_root):
    results = retrieval.search_docs("phase", scope="local", limit=5)
    assert results, "expected at least one match for 'phase'"
    for doc in results:
        assert "content" not in doc
        assert doc.get("preview") is not None or doc.get("card_summary") is not None


def test_search_docs_include_content_returns_full_body(kb_root):
    results = retrieval.search_docs(
        "phase", scope="local", limit=5, include_content=True
    )
    assert results
    assert any("content" in doc for doc in results)
