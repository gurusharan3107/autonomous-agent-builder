"""Tests for builder memory lifecycle commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from autonomous_agent_builder.cli.main import app

runner = CliRunner()


def _template_body(kind: str = "Decision") -> str:
    return (
        f"## {kind}\n\n"
        "Keep a machine-readable startup path in the owner CLI.\n\n"
        "## Agent Retrieval Summary\n\n"
        "Retrieve this memory when changing the builder memory surface or CLI contract.\n\n"
        "## User-Facing Summary\n\n"
        "This memory keeps the dashboard explanation aligned with the agent retrieval path.\n\n"
        "## Reusable Guidance\n\n"
        "- Prefer structured memory sections.\n"
        "- Keep retrieval language explicit.\n\n"
        "## When To Apply\n\n"
        "Apply this when saving reusable builder decisions, patterns, or corrections.\n\n"
        "## Retrieval Queries\n\n"
        "- builder memory template\n"
        "- agent friendly memory\n"
    )


def _assert_post_mutation(payload: dict, slug: str) -> None:
    post_mutation = payload["post_mutation"]
    assert post_mutation["reindexed"] is True
    assert post_mutation["lint_passed"] is True
    assert post_mutation["retrieval_checked"] is True
    assert post_mutation["retrieval_passed"] is True
    assert post_mutation["retrieved_slug"] == slug


def test_memory_lifecycle_commands(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    result = runner.invoke(app, ["memory", "init", "--json"])
    assert result.exit_code == 0

    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "--type",
            "decision",
            "--phase",
            "design",
            "--entity",
            "kb",
            "--tags",
            "memory,friction",
            "--title",
            "Capture KB friction",
            "--content",
            _template_body("Decision"),
            "--json",
        ],
    )
    assert result.exit_code == 0
    first = json.loads(result.stdout)
    first_slug = first["slug"]
    _assert_post_mutation(first, first_slug)

    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "--type",
            "pattern",
            "--phase",
            "implementation",
            "--entity",
            "kb",
            "--tags",
            "reuse",
            "--title",
            "Reuse KB extraction pattern",
            "--content",
            _template_body("Pattern"),
            "--json",
        ],
    )
    assert result.exit_code == 0
    second = json.loads(result.stdout)
    second_slug = second["slug"]
    _assert_post_mutation(second, second_slug)

    result = runner.invoke(app, ["memory", "relate", first_slug, "--to", second_slug, "--json"])
    assert result.exit_code == 0
    _assert_post_mutation(json.loads(result.stdout), first_slug)

    result = runner.invoke(
        app,
        ["memory", "flag", first_slug, "--reason", "needs consolidation", "--json"],
    )
    assert result.exit_code == 0
    _assert_post_mutation(json.loads(result.stdout), first_slug)

    result = runner.invoke(
        app,
        ["memory", "graduate", first_slug, "--into", "AGENTS.md", "--json"],
    )
    assert result.exit_code == 0
    _assert_post_mutation(json.loads(result.stdout), first_slug)

    result = runner.invoke(app, ["memory", "stats", "--json"])
    assert result.exit_code == 0
    stats = json.loads(result.stdout)
    assert stats["total"] == 2
    assert stats["types"]["decision"] == 1
    assert stats["types"]["pattern"] == 1
    assert stats["statuses"]["graduated"] == 1

    routing = json.loads((memory_root / "routing.json").read_text(encoding="utf-8"))
    entries = routing["entries"]
    decision = next(entry for entry in entries if entry["slug"] == first_slug)
    pattern = next(entry for entry in entries if entry["slug"] == second_slug)
    assert second_slug in decision["related"]
    assert first_slug in pattern["related"]
    assert decision["graduated_into"] == "AGENTS.md"


def test_memory_contract_and_lint_commands(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    result = runner.invoke(app, ["memory", "init", "--json"])
    assert result.exit_code == 0

    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "--type",
            "decision",
            "--phase",
            "implementation",
            "--entity",
            "builder-cli",
            "--tags",
            "cli,doctor",
            "--title",
            "Root doctor contract",
            "--content",
            _template_body("Decision"),
            "--json",
        ],
    )
    assert result.exit_code == 0

    result = runner.invoke(app, ["memory", "contract", "--json"])
    assert result.exit_code == 0
    contract = json.loads(result.stdout)
    assert "type" in contract["required_frontmatter"]
    assert "decision" in contract["allowed_types"]
    assert contract["recommended_body_sections"] == [
        "Decision / Pattern / Correction",
        "Agent Retrieval Summary",
        "User-Facing Summary",
        "Reusable Guidance",
        "When To Apply",
        "Retrieval Queries",
    ]
    assert "sample_markdown" not in contract
    assert contract["actionable_next"].startswith("builder memory add")
    assert contract["progressive_disclosure"][-1]["command"] == "builder memory contract --json --full"

    result = runner.invoke(app, ["memory", "contract", "--json", "--full"])
    assert result.exit_code == 0
    contract = json.loads(result.stdout)
    sample = contract["sample_markdown"]
    assert "## Decision" in sample
    assert "## Agent Retrieval Summary" in sample
    assert "## User-Facing Summary" in sample
    assert "## Reusable Guidance" in sample
    assert "## When To Apply" in sample
    assert "## Retrieval Queries" in sample

    result = runner.invoke(app, ["memory", "lint", "--json"])
    assert result.exit_code == 0
    lint = json.loads(result.stdout)
    assert lint["passed"] is True
    assert lint["files_checked"] == 1


def test_memory_lint_fails_for_active_memory_missing_template(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    decision_dir = memory_root / "decisions"
    decision_dir.mkdir(parents=True)
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    (decision_dir / "unstructured-memory.md").write_text(
        "---\n"
        "title: Unstructured memory\n"
        "type: decision\n"
        "date: 2026-05-04\n"
        "phase: implementation\n"
        "entity: builder-cli\n"
        "status: active\n"
        "---\n\n"
        "## Summary\n\nThis lacks the required agent-friendly memory template.\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["memory", "lint", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("## Decision" in issue["message"] for issue in payload["issues"])
    assert any("## Agent Retrieval Summary" in issue["message"] for issue in payload["issues"])


def test_memory_lint_fails_for_missing_related_target(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    decision_dir = memory_root / "decisions"
    decision_dir.mkdir(parents=True)
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    (decision_dir / "broken-memory.md").write_text(
        "---\n"
        "title: Broken memory\n"
        "type: decision\n"
        "date: 2026-04-21\n"
        "phase: implementation\n"
        "entity: builder-cli\n"
        "status: active\n"
        "related: [missing-memory]\n"
        "---\n\n"
        "## Summary\n\nThis entry points at a missing related slug.\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["memory", "lint", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert any("missing-memory" in issue["message"] for issue in payload["issues"])


def test_memory_lint_tolerates_legacy_entry_without_frontmatter(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    pattern_dir = memory_root / "patterns"
    pattern_dir.mkdir(parents=True)
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    (pattern_dir / "legacy-pattern.md").write_text(
        "Legacy pattern body without explicit frontmatter but with reusable guidance.\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["memory", "lint", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert any(issue["severity"] == "warning" for issue in payload["issues"])


def test_memory_add_reindexes_lints_and_checks_retrieval(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    decision_dir = memory_root / "decisions"
    decision_dir.mkdir(parents=True)
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    (decision_dir / "existing-decision.md").write_text(
        "---\n"
        "title: Existing decision\n"
        "type: decision\n"
        "date: 2026-05-04\n"
        "phase: validation\n"
        "entity: memory-cli\n"
        "status: active\n"
        "---\n\n"
        + _template_body("Decision"),
        encoding="utf-8",
    )
    (memory_root / "routing.json").write_text('{"items":[]}\n', encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "--type",
            "pattern",
            "--phase",
            "implementation",
            "--entity",
            "memory-cli",
            "--tags",
            "memory,reindex",
            "--title",
            "Post mutation memory checks",
            "--content",
            _template_body("Pattern"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    _assert_post_mutation(payload, payload["slug"])
    assert payload["post_mutation"]["memory_count"] == 2

    result = runner.invoke(app, ["memory", "stats", "--json"])
    assert result.exit_code == 0
    stats = json.loads(result.stdout)
    assert stats["total"] == 2


def test_memory_add_fails_when_post_mutation_lint_fails(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    result = runner.invoke(app, ["memory", "init", "--json"])
    assert result.exit_code == 0

    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "--type",
            "decision",
            "--phase",
            "implementation",
            "--entity",
            "memory-cli",
            "--tags",
            "memory,lint",
            "--title",
            "Invalid post mutation memory",
            "--content",
            "## Summary\n\nThis should be rejected by post-mutation lint.\n",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["post_mutation"]["lint_passed"] is False
    assert payload["post_mutation"]["retrieval_passed"] is True
    assert any("## Decision" in issue["message"] for issue in payload["post_mutation"]["issues"])


def test_memory_invalidate_marks_irrelevant_entry_inactive(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    result = runner.invoke(app, ["memory", "init", "--json"])
    assert result.exit_code == 0

    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "--type",
            "pattern",
            "--phase",
            "implementation",
            "--entity",
            "builder-cli",
            "--tags",
            "cli,lifecycle",
            "--title",
            "Temporary workaround",
            "--content",
            _template_body("Pattern"),
            "--json",
        ],
    )
    assert result.exit_code == 0
    slug = json.loads(result.stdout)["slug"]

    result = runner.invoke(
        app,
        ["memory", "invalidate", slug, "--reason", "replaced by durable contract", "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["memory"]["status"] == "invalidated"
    assert payload["memory"]["flag_reason"] == "replaced by durable contract"
    _assert_post_mutation(payload, slug)


def test_builder_lint_aggregates_fast_structural_checks(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["memory", "init", "--json"])
    assert result.exit_code == 0
    result = runner.invoke(
        app,
        [
            "memory",
            "add",
            "--type",
            "decision",
            "--phase",
            "validation",
            "--entity",
            "builder-lint",
            "--tags",
            "lint,aggregate",
            "--title",
            "Builder lint contract",
            "--content",
            _template_body("Decision"),
            "--json",
        ],
    )
    assert result.exit_code == 0

    result = runner.invoke(app, ["lint", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["summary"]["failed"] == 0
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["memory"]["status"] == "passed"
    assert checks["quality_gates"]["status"] == "passed"
    assert checks["knowledge"]["status"] == "skipped"
    assert checks["cli_surface"]["status"] == "passed"
    assert checks["config"]["status"] == "passed"
    assert checks["complexity"]["status"] == "passed"
    assert checks["readiness"]["status"] == "skipped"
    assert payload["summary"] == {"total": 7, "passed": 5, "failed": 0, "skipped": 2}
    assert payload["next_step"] == "ready_for_behavioral_validation"


def test_builder_lint_complexity_report_is_non_blocking(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sample.py").write_text("def ok():\n    return 1\n", encoding="utf-8")

    result = runner.invoke(app, ["lint", "--complexity-report", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["mode"] == "complexity_report"
    assert payload["blocking"] is False
    assert payload["report"]["files_scanned"] == 1
    assert payload["report"]["summary"]["violations"] == 0


def test_builder_lint_fails_when_memory_template_lint_fails(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    decision_dir = memory_root / "decisions"
    decision_dir.mkdir(parents=True)
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))
    monkeypatch.chdir(tmp_path)
    (decision_dir / "bad-memory.md").write_text(
        "---\n"
        "title: Bad memory\n"
        "type: decision\n"
        "date: 2026-05-04\n"
        "phase: validation\n"
        "entity: builder-lint\n"
        "status: active\n"
        "---\n\n"
        "## Summary\n\nThis should fail aggregate lint.\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["lint", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["memory"]["status"] == "failed"
    assert "details" not in checks["memory"]
    assert checks["memory"]["diagnostics"]["full_payload_command"] == "builder lint --json --full"
    assert payload["next_step"] == "builder memory lint --json"
    assert payload["actionable_next"] == "builder memory lint --json"
    assert payload["progressive_disclosure"][1]["command"] == "builder lint --json --full"


def test_builder_verify_changed_plans_surface_proof(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()

    from autonomous_agent_builder.cli.commands import verify as verify_module

    monkeypatch.setattr(
        verify_module,
        "_changed_files",
        lambda base=None: [
            "src/autonomous_agent_builder/cli/commands/memory.py",
            ".memory/decisions/example.md",
        ],
    )

    result = runner.invoke(app, ["verify", "--changed", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["mode"] == "plan"
    assert payload["status"] == "needs_proof"
    assert payload["selected_surfaces"] == ["builder-cli", "memory"]
    proof_codes = {proof["code"] for proof in payload["required_proof"]}
    assert "structural_lint" in proof_codes
    assert "memory_cli_tests" in proof_codes
    assert "memory_contract_smoke" in proof_codes
    assert "builder_cli_surface_tests" in proof_codes
    assert "Run the required proof in order" in payload["agent_instruction"]


def test_builder_verify_execute_runs_command_proof(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from autonomous_agent_builder.cli.commands import verify as verify_module

    monkeypatch.setattr(verify_module, "_changed_files", lambda base=None: [])
    monkeypatch.setattr(
        verify_module,
        "_proofs_for_surfaces",
        lambda surfaces: [
            verify_module.Proof(
                code="echo_proof",
                surface="general",
                proof_type="unit_tests",
                command="python -c 'print(\"ok\")'",
                why="test execution path",
            )
        ],
    )

    result = runner.invoke(app, ["verify", "--surface", "general", "--execute", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["mode"] == "execute"
    assert payload["status"] == "passed"
    assert payload["execution_results"][0]["status"] == "passed"
    assert payload["execution_results"][0]["cwd"] == str(tmp_path)
    assert payload["next_step"] == "ready_for_commit"
