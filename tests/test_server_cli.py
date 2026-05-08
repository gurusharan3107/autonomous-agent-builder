from __future__ import annotations

from typer.testing import CliRunner

from autonomous_agent_builder.cli.commands import start_impl
from autonomous_agent_builder.cli.main import app

runner = CliRunner()


def test_server_start_uses_repo_local_port_when_flag_omitted(monkeypatch, tmp_path) -> None:
    project_root = tmp_path
    agent_builder_dir = project_root / ".agent-builder"
    agent_builder_dir.mkdir()
    (agent_builder_dir / "agent_builder.db").write_text("", encoding="utf-8")
    (agent_builder_dir / "server.port").write_text("9876", encoding="utf-8")
    monkeypatch.chdir(project_root)

    called: dict[str, object] = {}

    def fake_start_uvicorn(
        agent_builder_dir, server_path, db_path, dashboard_path, host, port, debug
    ) -> None:
        called.update(
            {
                "agent_builder_dir": agent_builder_dir,
                "server_path": server_path,
                "db_path": db_path,
                "dashboard_path": dashboard_path,
                "host": host,
                "port": port,
                "debug": debug,
            }
        )

    monkeypatch.setattr(start_impl, "_start_uvicorn", fake_start_uvicorn)

    result = runner.invoke(app, ["start"])

    assert result.exit_code == 0
    assert called["host"] == "127.0.0.1"
    assert called["port"] == 9876
    assert called["debug"] is False
    assert called["agent_builder_dir"] == agent_builder_dir
    assert called["db_path"] == agent_builder_dir / "agent_builder.db"


def test_server_start_flag_overrides_repo_local_port(monkeypatch, tmp_path) -> None:
    project_root = tmp_path
    agent_builder_dir = project_root / ".agent-builder"
    agent_builder_dir.mkdir()
    (agent_builder_dir / "agent_builder.db").write_text("", encoding="utf-8")
    (agent_builder_dir / "server.port").write_text("9876", encoding="utf-8")
    monkeypatch.chdir(project_root)

    called: dict[str, object] = {}

    def fake_start_uvicorn(
        agent_builder_dir, server_path, db_path, dashboard_path, host, port, debug
    ) -> None:
        called.update(
            {
                "agent_builder_dir": agent_builder_dir,
                "server_path": server_path,
                "db_path": db_path,
                "dashboard_path": dashboard_path,
                "host": host,
                "port": port,
                "debug": debug,
            }
        )

    monkeypatch.setattr(start_impl, "_start_uvicorn", fake_start_uvicorn)

    result = runner.invoke(app, ["start", "--port", "9988"])

    assert result.exit_code == 0
    assert called["port"] == 9988
