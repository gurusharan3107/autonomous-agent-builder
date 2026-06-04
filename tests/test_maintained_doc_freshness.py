from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

from autonomous_agent_builder.knowledge.maintained_freshness import (
    maintained_doc_report,
    resolve_canonical_doc_ref,
)
from autonomous_agent_builder.knowledge.quality_gate import KnowledgeQualityGate


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write_doc(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).strip() + "\n", encoding="utf-8")


def test_maintained_doc_report_detects_owned_path_changes_on_main(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    tracked = repo / "src" / "feature.py"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    baseline = _git(repo, "rev-parse", "HEAD")

    tracked.write_text("value = 2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "change feature")

    report = maintained_doc_report(
        workspace_path=repo,
        doc_id="system-docs/feature-doc.md",
        doc_type="feature",
        lifecycle_status="active",
        metadata={
            "documented_against_commit": baseline,
            "documented_against_ref": "main",
            "owned_paths": ["src/feature.py"],
            "created": "2026-04-23T01:00:00",
            "updated": "2026-04-23T01:05:00",
        },
        created="2026-04-23T01:00:00",
        updated="2026-04-23T01:05:00",
    )

    assert report.status == "stale"
    assert report.blocking is True
    assert report.matched_changed_paths == ["src/feature.py"]
    assert report.current_main_commit


def test_resolve_canonical_doc_ref_falls_back_to_master_when_main_missing(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "master")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    tracked = repo / "src" / "feature.py"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")

    assert resolve_canonical_doc_ref(repo) == "master"

    report = maintained_doc_report(
        workspace_path=repo,
        doc_id="bookmark-spec",
        doc_type="feature",
        lifecycle_status="active",
        metadata={
            "documented_against_commit": _git(repo, "rev-parse", "HEAD"),
            "documented_against_ref": "master",
            "owned_paths": ["src/feature.py"],
            "created": "2026-04-23T01:00:00",
            "updated": "2026-04-23T01:05:00",
        },
        created="2026-04-23T01:00:00",
        updated="2026-04-23T01:05:00",
    )

    assert report.status == "current"
    assert report.blocking is False


def test_quality_gate_soft_migration_warns_for_older_doc_without_commit_baseline(tmp_path):
    repo = tmp_path / "repo"
    kb_root = repo / ".agent-builder" / "knowledge" / "system-docs"
    kb_root.mkdir(parents=True)
    repo.mkdir(exist_ok=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "src").mkdir()
    (repo / "src" / "feature.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")

    _write_doc(
        kb_root / "older-feature-doc.md",
        """
        ---
        title: Older Feature Doc
        tags: [feature]
        doc_type: feature
        doc_family: feature
        created: "2026-04-20T10:00:00"
        updated: "2026-04-20T10:05:00"
        auto_generated: true
        version: 1
        refresh_required: true
        linked_feature: onboarding
        feature_id: feat-onboarding
        ---
        # Older Feature Doc

        ## Overview

        Legacy doc.

        ## Current behavior

        Old behavior.

        ## Boundaries

        Tracks onboarding docs.

        ## Verification

        Read the KB.

        ## Change guidance

        Update when behavior changes.
        """,
    )
    _write_doc(
        kb_root / "extraction-metadata.md",
        """
        ---
        title: Extraction Metadata
        tags: [metadata]
        doc_type: metadata
        created: "2026-04-19T12:00:00"
        auto_generated: true
        version: 1
        ---
        # Extraction Metadata

        ## Summary

        Metadata.
        """,
    )

    result = KnowledgeQualityGate(kb_root, repo).validate()
    freshness = next(check for check in result.checks if check.name == "freshness")

    assert freshness.passed is True
    assert "migration warning" in freshness.message
    assert freshness.details is not None
    assert freshness.details["issues"] == []
    assert freshness.details["warnings"] == [
        "older-feature-doc: missing documented_against_commit"
    ]


def test_quality_gate_blocks_newer_doc_missing_commit_baseline(tmp_path):
    repo = tmp_path / "repo"
    kb_root = repo / ".agent-builder" / "knowledge" / "system-docs"
    kb_root.mkdir(parents=True)
    repo.mkdir(exist_ok=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "src").mkdir()
    (repo / "src" / "feature.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")

    _write_doc(
        kb_root / "new-feature-doc.md",
        """
        ---
        title: New Feature Doc
        tags: [feature]
        doc_type: feature
        doc_family: feature
        created: "2026-04-24T10:00:00"
        updated: "2026-04-24T10:05:00"
        auto_generated: true
        version: 2
        refresh_required: true
        linked_feature: onboarding
        feature_id: feat-onboarding
        ---
        # New Feature Doc

        ## Overview

        Fresh doc.

        ## Current behavior

        Current behavior.

        ## Boundaries

        Tracks onboarding docs.

        ## Verification

        Read the KB.

        ## Change guidance

        Update when behavior changes.
        """,
    )
    _write_doc(
        kb_root / "extraction-metadata.md",
        """
        ---
        title: Extraction Metadata
        tags: [metadata]
        doc_type: metadata
        created: "2026-04-19T12:00:00"
        auto_generated: true
        version: 1
        ---
        # Extraction Metadata

        ## Summary

        Metadata.
        """,
    )

    result = KnowledgeQualityGate(kb_root, repo).validate()
    freshness = next(check for check in result.checks if check.name == "freshness")

    assert freshness.passed is False
    assert "missing documented_against_commit" in freshness.details["issues"][0]
