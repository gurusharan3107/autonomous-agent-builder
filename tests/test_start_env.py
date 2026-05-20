from __future__ import annotations

from pathlib import Path

from autonomous_agent_builder.cli.commands import start_impl as start_impl_module


def test_run_start_loads_builder_source_env_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir()
    app_env = tmp_path / ".env"
    app_env.write_text(
        'RUNTIME_SDK="codex_sdk"\nCLAUDE_CODE_OAUTH_TOKEN=generated-token\n',
        encoding="utf-8",
    )
    builder_env = tmp_path / "builder-source" / ".env"
    builder_env.parent.mkdir()
    builder_env.write_text(
        "OPENAI_API_KEY=builder-realtime-key\nCLAUDE_CODE_OAUTH_TOKEN=builder-token\n",
        encoding="utf-8",
    )

    loaded: list[tuple[Path, bool]] = []

    def fake_load_dotenv(path: Path, *, override: bool = False) -> None:
        loaded.append((path, override))

    monkeypatch.setattr(start_impl_module, "load_dotenv", fake_load_dotenv)
    monkeypatch.setenv("AAB_BUILDER_SOURCE_ENV", str(builder_env))

    result = start_impl_module._load_start_env(agent_builder_dir)

    assert result == [builder_env]
    assert loaded == [(builder_env, False)]
