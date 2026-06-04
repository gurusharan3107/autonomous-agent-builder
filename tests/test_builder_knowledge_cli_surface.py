"""Tests for builder knowledge CLI surfaces."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from autonomous_agent_builder.cli.main import app
from tests.builder_cli_surface_helpers import configure_local_kb, write_local_kb_doc

runner = CliRunner()


def test_kb_summary_resolves_search_query(monkeypatch, tmp_path):
    kb_root = configure_local_kb(monkeypatch, tmp_path)
    write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags:\n"
            "  - builder\n"
            "  - system-docs\n"
            "---\n\n"
            "# Project Overview\n\n"
            "## Overview\n\n"
            "Builder generates seed system docs for the local repo into durable project knowledge.\n\n"
            "## Architecture\n\n"
            "FastAPI plus CLI surfaces.\n"
        ),
    )

    result = runner.invoke(app, ["knowledge", "summary", "overview", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["matched_on"] in {"search", "name", "prefix"}
    assert payload["id"] == "system-docs/project-overview.md"
    assert "seed system docs" in payload["summary"]


def test_kb_summary_accepts_multiword_query(monkeypatch, tmp_path):
    kb_root = configure_local_kb(monkeypatch, tmp_path)
    write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder, system-docs, seed]\n"
            "---\n\n"
            "# Project Overview\n\n"
            "Builder generates seed system docs for the local repo.\n"
        ),
    )

    result = runner.invoke(app, ["knowledge", "summary", "project", "overview", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["matched_on"] in {"search", "name", "prefix"}
    assert payload["id"] == "system-docs/project-overview.md"


def test_kb_show_section_returns_only_requested_heading(monkeypatch, tmp_path):
    kb_root = configure_local_kb(monkeypatch, tmp_path)
    write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder]\n"
            "---\n\n"
            "# Project Overview\n\n"
            "## Overview\n\n"
            "Top summary.\n\n"
            "## Architecture\n\n"
            "Only this section should be returned.\n\n"
            "## Next Steps\n\n"
            "Follow-up."
        ),
    )

    result = runner.invoke(
        app,
        [
            "knowledge",
            "show",
            "system-docs/project-overview.md",
            "--section",
            "Architecture",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["section"] == "Architecture"
    assert payload["content"] == "Only this section should be returned."


def test_kb_show_resolves_multiword_query(monkeypatch, tmp_path):
    kb_root = configure_local_kb(monkeypatch, tmp_path)
    write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder, system-docs, seed]\n"
            "---\n\n"
            "# Project Overview\n\n"
            "## Overview\n\n"
            "Builder generates seed system docs for the local repo.\n"
        ),
    )

    result = runner.invoke(app, ["knowledge", "show", "project", "overview", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["matched_on"] in {"search", "name", "prefix"}
    assert payload["id"] == "system-docs/project-overview.md"


def test_kb_show_section_resolves_multiword_query(monkeypatch, tmp_path):
    kb_root = configure_local_kb(monkeypatch, tmp_path)
    write_local_kb_doc(
        kb_root,
        "system-docs/system-architecture.md",
        (
            "---\n"
            "title: System Architecture\n"
            "tags: [system-docs, architecture]\n"
            "---\n\n"
            "# System Architecture\n\n"
            "## Overview\n\n"
            "Top summary.\n\n"
            "## Change guidance\n\n"
            "Refresh the doc after runtime wiring changes.\n"
        ),
    )

    result = runner.invoke(
        app,
        [
            "knowledge",
            "show",
            "system",
            "architecture",
            "--section",
            "Change guidance",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["matched_on"] in {"search", "name", "prefix"}
    assert payload["section"] == "Change guidance"
    assert payload["content"] == "Refresh the doc after runtime wiring changes."


def test_kb_show_missing_doc_does_not_fuzzy_resolve(monkeypatch, tmp_path):
    kb_root = configure_local_kb(monkeypatch, tmp_path)
    write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder, system-docs, seed]\n"
            "---\n\n"
            "# Project Overview\n\n"
            "Builder generates seed system docs for the local repo.\n"
        ),
    )

    result = runner.invoke(app, ["knowledge", "show", "missing-doc", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"
    assert payload["error"]["detail"]["query"] == "missing-doc"


def test_kb_search_json_is_compact(monkeypatch, tmp_path):
    kb_root = configure_local_kb(monkeypatch, tmp_path)
    write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder, system-docs, seed]\n"
            "version: 2\n"
            "card_summary: Project purpose and operator-facing overview.\n"
            "---\n\n"
            "# Project Overview\n\n"
            "Builder generates seed system docs for the local repo.\n"
        ),
    )

    result = runner.invoke(app, ["knowledge", "search", "overview", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["query"] == "overview"
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "system-docs/project-overview.md"
    assert "content" not in payload["results"][0]
    assert payload["results"][0]["preview"] == "Project purpose and operator-facing overview."
    assert payload["next_step"] == 'builder knowledge summary "overview" --json'


def test_kb_list_json_is_compact_by_default_and_full_when_requested(monkeypatch, tmp_path):
    kb_root = configure_local_kb(monkeypatch, tmp_path)
    write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder, system-docs, seed]\n"
            "version: 2\n"
            "card_summary: Project purpose and operator-facing overview.\n"
            "---\n\n"
            "# Project Overview\n\n"
            "Builder generates seed system docs for the local repo.\n"
        ),
    )

    compact = runner.invoke(app, ["knowledge", "list", "--json"])
    full = runner.invoke(app, ["knowledge", "list", "--json", "--full"])

    assert compact.exit_code == 0
    compact_payload = json.loads(compact.stdout)
    assert compact_payload["count"] == 1
    assert "content" not in compact_payload["results"][0]
    assert (
        compact_payload["next_step"]
        == "builder knowledge show <doc-id> --section 'Change guidance' --json"
    )
    assert "tags" not in compact_payload["results"][0]
    assert "version" not in compact_payload["results"][0]

    assert full.exit_code == 0
    full_payload = json.loads(full.stdout)
    assert full_payload["count"] == 1
    assert "content" in full_payload["results"][0]
    assert (
        full_payload["next_step"]
        == "builder knowledge show <doc-id> --section 'Change guidance' --json"
    )


def test_kb_show_not_found_suggests_search(monkeypatch, tmp_path):
    kb_root = configure_local_kb(monkeypatch, tmp_path)
    write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder, system-docs, seed]\n"
            "---\n\n"
            "# Project Overview\n\n"
            "Builder generates seed system docs for the local repo.\n"
        ),
    )

    result = runner.invoke(app, ["knowledge", "show", "missing", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "not_found"
    assert 'builder knowledge search "missing" --json' in payload["error"]["hint"]


def test_kb_search_works_without_server_client(monkeypatch, tmp_path):
    kb_root = configure_local_kb(monkeypatch, tmp_path)
    write_local_kb_doc(
        kb_root,
        "system-docs/onboarding-modes-and-external-validation.md",
        (
            "---\n"
            "title: Onboarding Modes and External Validation\n"
            "tags: [feature, onboarding, external-validation, system-docs]\n"
            "---\n\n"
            "# Onboarding Modes and External Validation\n\n"
            "Onboarding is the canonical feature surface for clean-slate and existing-repo setup.\n"
        ),
    )
    monkeypatch.setenv("AAB_API_URL", "http://127.0.0.1:1")

    result = runner.invoke(
        app,
        [
            "knowledge",
            "search",
            "onboarding",
            "existing",
            "repo",
            "--type",
            "system-docs",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "system-docs/onboarding-modes-and-external-validation.md"
