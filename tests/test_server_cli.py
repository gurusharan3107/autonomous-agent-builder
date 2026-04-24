from __future__ import annotations

import sys
from types import SimpleNamespace

from typer.testing import CliRunner

from autonomous_agent_builder.cli.main import app

runner = CliRunner()


def test_server_start_uses_repo_local_port_when_flag_omitted(monkeypatch, tmp_path) -> None:
    project_root = tmp_path
    agent_builder_dir = project_root / ".agent-builder"
    agent_builder_dir.mkdir()
    (agent_builder_dir / "server.port").write_text("9876", encoding="utf-8")
    monkeypatch.chdir(project_root)

    called: dict[str, object] = {}

    def fake_run(app_path: str, *, host: str, port: int, reload: bool) -> None:
        called.update(
            {
                "app_path": app_path,
                "host": host,
                "port": port,
                "reload": reload,
            }
        )

    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=fake_run))

    result = runner.invoke(app, ["server", "start"])

    assert result.exit_code == 0
    assert called == {
        "app_path": "autonomous_agent_builder.api.app:app",
        "host": "0.0.0.0",
        "port": 9876,
        "reload": False,
    }


def test_server_start_flag_overrides_repo_local_port(monkeypatch, tmp_path) -> None:
    project_root = tmp_path
    agent_builder_dir = project_root / ".agent-builder"
    agent_builder_dir.mkdir()
    (agent_builder_dir / "server.port").write_text("9876", encoding="utf-8")
    monkeypatch.chdir(project_root)

    called: dict[str, object] = {}

    def fake_run(app_path: str, *, host: str, port: int, reload: bool) -> None:
        called.update(
            {
                "app_path": app_path,
                "host": host,
                "port": port,
                "reload": reload,
            }
        )

    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=fake_run))

    result = runner.invoke(app, ["server", "start", "--port", "9988"])

    assert result.exit_code == 0
    assert called["port"] == 9988
