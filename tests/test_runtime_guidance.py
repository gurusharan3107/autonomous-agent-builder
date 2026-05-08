from __future__ import annotations

import json

from autonomous_agent_builder.services.runtime_guidance import (
    ensure_project_runtime_guidance,
    refresh_project_runtime_guidance,
    render_project_runtime_guidance,
    render_project_telemetry_env,
    telemetry_env_status,
)


def test_forward_runtime_guidance_template_contains_day0_contract() -> None:
    text = render_project_runtime_guidance(
        project_name="ShipCheck",
        mode="forward_engineering",
        language="python",
        framework="flask",
        app_type="web",
        persistence="sqlite",
        package_manager="pip",
    )

    assert "- Mode: forward_engineering" in text
    assert "- Setup: `unknown`" in text
    assert "- Smoke/browser check: `unknown`" in text
    assert "## Builder Agent Runtime Guidance" in text
    assert "`code-gen`: read this file before implementation" in text
    assert "`build-verifier`: run the narrowest deterministic build" in text
    assert "Any new script must have a trigger" in text
    assert "A route is not accepted unless a user can discover it" in text
    assert "- Selected runtime telemetry: enabled" in text
    assert "- Codex runtime telemetry: enabled only when `RUNTIME_SDK` starts with `codex_`" in text
    assert "Do not use this file as a changelog" in text


def test_reverse_runtime_guidance_template_contains_discovery_contract() -> None:
    text = render_project_runtime_guidance(
        project_name="ExistingApp",
        mode="reverse_engineering",
        language="node",
        framework="express",
        app_type="api",
        persistence="postgres",
        package_manager="npm",
        commands={"test": "npm run test", "build": "npm run build"},
        entrypoints=["server.js"],
        test_surfaces=["tests"],
    )

    assert "- Mode: reverse_engineering" in text
    assert "- Primary entrypoints: server.js" in text
    assert "- Test surfaces: tests" in text
    assert "- Test: `npm run test`" in text
    assert "- Build: `npm run build`" in text
    assert "## Builder Agent Runtime Guidance" in text
    assert "`optimization-agent`: start from builder preflight evidence" in text
    assert "Preserve existing architecture" in text
    assert "capture the baseline failure" in text
    assert "- Selected runtime telemetry: enabled" in text
    assert "- Codex runtime telemetry: enabled only when `RUNTIME_SDK` starts with `codex_`" in text


def test_codex_runtime_guidance_template_contains_agents_contract() -> None:
    text = render_project_runtime_guidance(
        project_name="ShipCheck",
        sdk="codex_sdk",
        mode="forward_engineering",
        language="python",
        framework="flask",
        app_type="web",
        persistence="sqlite",
        package_manager="pip",
    )

    assert "Runtime guidance for Codex SDK agents" in text
    assert "`CLAUDE.md`, when present, is for Claude Agent SDK agents" in text
    assert "Use Codex-native project instructions from this `AGENTS.md` file" in text
    assert "## Builder Agent Runtime Guidance" in text
    assert "`pr-creator`: summarize exact changed files" in text
    assert "`feature-verifier`: validate acceptance criteria" in text
    assert "- Claude OTEL telemetry: disabled while Codex is selected." in text
    assert "Do not use this file as a changelog" in text


def test_runtime_guidance_migrates_builder_claude_md_to_agents_md(tmp_path) -> None:
    (tmp_path / ".env").write_text('RUNTIME_SDK="codex_sdk"\n', encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(
        render_project_runtime_guidance(
            project_name="ShipCheck",
            sdk="claude",
            mode="forward_engineering",
            language="python",
        ),
        encoding="utf-8",
    )

    result = ensure_project_runtime_guidance(
        tmp_path,
        project_name="ShipCheck",
        mode="forward_engineering",
        language="python",
    )

    assert result["status"] == "migrated"
    assert result["relative_path"] == "AGENTS.md"
    assert (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / "CLAUDE.md").exists()
    assert "Runtime guidance for Codex SDK agents" in (tmp_path / "AGENTS.md").read_text(
        encoding="utf-8"
    )


def test_refresh_runtime_guidance_updates_builder_generated_files_with_discovered_commands(
    tmp_path,
) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "dev": "vite --host 127.0.0.1",
                    "test": "vitest run",
                    "lint": "eslint .",
                    "build": "vite build",
                },
                "dependencies": {"@vitejs/plugin-react": "latest", "vite": "latest"},
                "devDependencies": {"vitest": "latest"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    state_dir = tmp_path / ".agent-builder"
    state_dir.mkdir()
    (state_dir / "onboarding-state.json").write_text(
        json.dumps(
            {
                "onboarding_mode": "forward_engineering",
                "repo": {"name": "Todo App", "language": "node"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        render_project_runtime_guidance(
            project_name="Todo App",
            sdk="codex_sdk",
            mode="forward_engineering",
            language="unknown",
        ),
        encoding="utf-8",
    )
    (tmp_path / "CLAUDE.md").write_text(
        render_project_runtime_guidance(
            project_name="Todo App",
            sdk="claude",
            mode="forward_engineering",
            language="unknown",
        ),
        encoding="utf-8",
    )

    result = refresh_project_runtime_guidance(tmp_path)

    assert result["status"] == "updated"
    assert result["updated_files"] == ["CLAUDE.md", "AGENTS.md"]
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "- Package manager: npm" in text
    assert "- Setup: `npm install`" in text
    assert "- Dev server: `npm run dev`" in text
    assert "- Test: `npm run test`" in text
    assert "- Lint: `npm run lint`" in text
    assert "- Build: `npm run build`" in text
    assert "## Builder Agent Runtime Guidance" in text
    assert "`code-gen`: read this file before implementation" in text
    assert "`optimization-agent`: start from builder preflight evidence" in text
    claude_text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "## Builder Agent Runtime Guidance" in claude_text
    assert "Any new script must have a trigger" in claude_text


def test_refresh_runtime_guidance_preserves_user_authored_agents_md(tmp_path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    original = "# Custom Agent Rules\n\nDo not replace this file.\n"
    (tmp_path / "AGENTS.md").write_text(original, encoding="utf-8")

    result = refresh_project_runtime_guidance(tmp_path, project_name="Custom")

    assert result["status"] == "unchanged"
    assert result["updated_files"] == []
    assert result["skipped_files"] == [
        {"path": "AGENTS.md", "reason": "not_builder_generated"}
    ]
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == original


def test_telemetry_env_template_enables_safe_local_defaults() -> None:
    text = render_project_telemetry_env(project_name="Ship Check")

    assert "AAB_CLAUDE_OTEL_ENABLED=1" in text
    assert "AAB_CLAUDE_OTEL_ENDPOINT=http://localhost:4318" in text
    assert "AAB_CLAUDE_OTEL_SERVICE_NAME=ship-check" in text
    assert "AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID=true" in text
    assert "AAB_CODEX_RUNTIME_TELEMETRY_ENABLED=0" in text
    assert "AAB_CODEX_TELEMETRY_SOURCE=codex_runtime_events" in text
    assert "AAB_CLAUDE_OTEL_LOG_TOOL_CONTENT" not in text


def test_telemetry_env_status_distinguishes_unreachable_local_collector(
    monkeypatch, tmp_path
) -> None:
    def refuse_connection(*_args, **_kwargs):
        raise ConnectionRefusedError("collector not listening")

    monkeypatch.setattr(
        "autonomous_agent_builder.observability.collector.socket.create_connection",
        refuse_connection,
    )
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                'RUNTIME_SDK="claude"',
                "AAB_CLAUDE_OTEL_ENABLED=1",
                "AAB_CLAUDE_OTEL_ENDPOINT=http://localhost:4318",
                "AAB_CLAUDE_OTEL_SERVICE_NAME=test",
                "AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID=true",
                'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="0"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    status = telemetry_env_status(tmp_path)

    assert status["ok"] is False
    assert status["status"] == "configured_unreachable"
    assert status["endpoint_configured"] is True
    assert status["collector_reachable"] is False
    assert status["collector"]["checked"] is True
