from __future__ import annotations

import os
from pathlib import Path

from autonomous_agent_builder.cli.commands import init_impl


def _builder_source_env() -> Path:
    return Path(os.environ["AAB_BUILDER_SOURCE_ENV"])


def _patch_init_steps(monkeypatch):
    monkeypatch.setattr(init_impl, "_create_directory_structure", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(init_impl, "_copy_embedded_resources", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(init_impl, "_initialize_database", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(init_impl, "_generate_config", lambda *_args, **_kwargs: None)


def test_run_init_autodetects_node_language_from_package_json(tmp_path, monkeypatch):
    _patch_init_steps(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "package.json").write_text('{"name":"fixture"}')

    result = init_impl.run_init(
        project_name=None,
        language=None,
        framework=None,
        force=False,
        no_input=True,
    )

    assert result["success"] is True
    assert result["language"] == "node"
    assert result["runtime_guidance"]["status"] == "created"
    assert (tmp_path / "CLAUDE.md").exists()
    claude_md = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Claude Agent SDK" in claude_md
    assert "- Mode: forward_engineering" in claude_md
    assert "## Deterministic Commands" in claude_md
    assert not (tmp_path / ".env").exists()
    assert (tmp_path / ".agent-builder" / "onboarding-state.json").exists()
    env_text = _builder_source_env().read_text(encoding="utf-8")
    assert 'RUNTIME_SDK="claude"' in env_text
    assert 'AAB_CLAUDE_OTEL_ENABLED="1"' in env_text
    assert 'AAB_CLAUDE_OTEL_ENDPOINT="http://localhost:4318"' in env_text
    assert 'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="0"' in env_text
    assert 'AAB_CLAUDE_OTEL_LOG_TOOL_CONTENT="0"' in env_text
    assert ".agent-builder/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_run_init_creates_codex_agents_md_when_codex_sdk_selected(tmp_path, monkeypatch):
    _patch_init_steps(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _builder_source_env().write_text('RUNTIME_SDK="codex_sdk"\n', encoding="utf-8")

    result = init_impl.run_init(
        project_name="codex-app",
        language="python",
        framework="flask",
        force=False,
        no_input=True,
    )

    assert result["success"] is True
    assert result["runtime_guidance"]["status"] == "created"
    assert result["runtime_guidance"]["relative_path"] == "AGENTS.md"
    assert (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / "CLAUDE.md").exists()
    agents_md = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "Codex SDK" in agents_md
    assert "- Mode: forward_engineering" in agents_md
    env_text = _builder_source_env().read_text(encoding="utf-8")
    assert 'RUNTIME_SDK="codex_sdk"' in env_text
    assert 'AAB_CLAUDE_OTEL_ENABLED="0"' in env_text
    assert 'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="1"' in env_text


def test_run_init_repairs_initialized_codex_telemetry_split(tmp_path, monkeypatch):
    _patch_init_steps(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".agent-builder").mkdir()
    _builder_source_env().write_text(
        'RUNTIME_SDK="codex_sdk"\n'
        'AAB_CLAUDE_OTEL_ENABLED="1"\n'
        'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="1"\n',
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "Runtime guidance for Codex SDK agents working in this repository.\n"
        "## Project Context\n"
        "## Builder Contract\n"
        "## Deterministic Commands\n"
        "## Validation Contract\n"
        "## Telemetry And Observability\n"
        "## Context Discipline\n"
        "## Update Rules\n",
        encoding="utf-8",
    )

    result = init_impl.run_init(
        project_name="codex-app",
        language="python",
        framework=None,
        force=False,
        no_input=True,
    )

    assert result["success"] is True
    assert result["already_initialized"] is True
    assert result["runtime_guidance"]["status"] == "existing"
    assert "AAB_CLAUDE_OTEL_ENABLED" in result["telemetry_env"]["changed_keys"]
    assert result["readiness"]["state"] in {"agent_ready", "blocked"}
    env_text = _builder_source_env().read_text(encoding="utf-8")
    assert 'AAB_CLAUDE_OTEL_ENABLED="0"' in env_text
    assert 'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="1"' in env_text


def test_run_init_migrates_builder_agents_md_to_claude_md_when_claude_selected(
    tmp_path, monkeypatch
):
    _patch_init_steps(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".agent-builder").mkdir()
    _builder_source_env().write_text('RUNTIME_SDK="claude"\n', encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        "Runtime guidance for Codex SDK agents working in this repository.\n"
        "## Project Context\n"
        "## Builder Contract\n"
        "## Deterministic Commands\n"
        "## Validation Contract\n"
        "## Telemetry And Observability\n"
        "## Context Discipline\n"
        "## Update Rules\n",
        encoding="utf-8",
    )

    result = init_impl.run_init(
        project_name="claude-app",
        language="python",
        framework=None,
        force=False,
        no_input=True,
    )

    assert result["success"] is True
    assert result["runtime_guidance"]["status"] == "migrated"
    assert result["runtime_guidance"]["relative_path"] == "CLAUDE.md"
    assert (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "AGENTS.md").exists()
    assert "Claude Agent SDK" in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")


def test_run_init_appends_builder_gitignore_entry(tmp_path, monkeypatch):
    _patch_init_steps(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")

    result = init_impl.run_init(
        project_name="gitignore-test",
        language="python",
        framework=None,
        force=False,
        no_input=True,
    )

    assert result["success"] is True
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == (
        "__pycache__/\n.agent-builder/\n"
    )


def test_run_init_prefers_explicit_language_over_autodetect(tmp_path, monkeypatch):
    _patch_init_steps(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "package.json").write_text('{"name":"fixture"}')

    result = init_impl.run_init(
        project_name=None,
        language="python",
        framework=None,
        force=False,
        no_input=True,
    )

    assert result["success"] is True
    assert result["language"] == "python"


def test_run_init_preserves_existing_project_claude_md(tmp_path, monkeypatch):
    _patch_init_steps(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("# Existing\n", encoding="utf-8")

    result = init_impl.run_init(
        project_name="existing-doc",
        language="python",
        framework=None,
        force=False,
        no_input=True,
    )

    assert result["success"] is True
    assert result["runtime_guidance"]["status"] == "existing"
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == "# Existing\n"


def test_run_init_repairs_missing_claude_md_in_initialized_repo(tmp_path, monkeypatch):
    _patch_init_steps(monkeypatch)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".agent-builder").mkdir()

    result = init_impl.run_init(
        project_name="repair-doc",
        language="python",
        framework=None,
        force=False,
        no_input=True,
    )

    assert result["success"] is True
    assert result["already_initialized"] is True
    assert result["runtime_guidance"]["status"] == "created"
    assert (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / ".env").exists()
    assert (tmp_path / ".agent-builder" / "onboarding-state.json").exists()


def test_run_init_creates_forward_day0_contract_for_empty_repo(tmp_path, monkeypatch):
    _patch_init_steps(monkeypatch)
    monkeypatch.chdir(tmp_path)

    result = init_impl.run_init(
        project_name="shipcheck",
        language="python",
        framework="flask",
        force=False,
        no_input=True,
    )

    claude_md = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")

    assert result["success"] is True
    assert "- Mode: forward_engineering" in claude_md
    assert "- Framework: flask" in claude_md
    assert "- Setup: `unknown`" in claude_md
    assert "A route is not accepted unless a user can discover it" in claude_md


def test_run_init_rejects_builder_source_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src" / "autonomous_agent_builder" / "cli").mkdir(parents=True)
    (tmp_path / "src" / "autonomous_agent_builder" / "cli" / "main.py").write_text(
        "app = None\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "autonomous-agent-builder"\n',
        encoding="utf-8",
    )

    result = init_impl.run_init(
        project_name=None,
        language=None,
        framework=None,
        force=False,
        no_input=True,
    )

    assert result["error"].startswith("Cannot initialize the autonomous builder source repository")
