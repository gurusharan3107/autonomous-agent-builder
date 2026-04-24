from __future__ import annotations

from autonomous_agent_builder.cli.commands import init_impl


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
