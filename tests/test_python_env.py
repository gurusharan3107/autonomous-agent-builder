"""Owned Python workspace env provisioning — the single interpreter/deps rule.

Regression home for the systemic bug where the testing gate, build_verify, the
materialized checkout, and the workspace test tool each ran pytest under an
interpreter without the app's deps installed → ModuleNotFoundError → wasted LLM
gate-remediation. All test-running phases now route through this module.
"""

from __future__ import annotations

import sys

from autonomous_agent_builder.quality_gates import python_env

PYPROJECT_DEV = "[project]\nname='x'\n[project.optional-dependencies]\ndev = ['pytest']\n"
PYPROJECT_NODEV = "[project]\nname='x'\n"


def test_setup_commands_noop_when_venv_present(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_DEV, encoding="utf-8")
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("")
    assert python_env.setup_commands(tmp_path) == []


def test_setup_commands_dev_extra_installs_dev(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_DEV, encoding="utf-8")
    cmds = python_env.setup_commands(tmp_path)
    assert cmds[0] == [sys.executable, "-m", "venv", str(tmp_path / ".venv")]
    assert cmds[1][-3:] == ["-e", ".[dev]", "-q"]
    assert len(cmds) == 2  # no separate pytest install needed


def test_setup_commands_no_dev_extra_adds_pytest(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_NODEV, encoding="utf-8")
    cmds = python_env.setup_commands(tmp_path)
    assert [c for c in cmds if "venv" in c]  # venv create present
    assert any(c[-3:] == ["-e", ".", "-q"] for c in cmds)  # base install
    assert any(c[-2:] == ["pytest", "-q"] for c in cmds)  # explicit pytest


def test_setup_commands_requirements_txt(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")
    cmds = python_env.setup_commands(tmp_path)
    assert any("requirements.txt" in c for c in cmds)
    assert any(c[-2:] == ["pytest", "-q"] for c in cmds)


def test_pytest_argv_prefers_venv_interpreter(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_DEV, encoding="utf-8")
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("")
    argv = python_env.pytest_argv(tmp_path, extra=["-q"])
    assert argv == [str(venv_python), "-m", "pytest", "-q"]


def test_pytest_argv_falls_back_to_sys_executable_without_venv(tmp_path):
    argv = python_env.pytest_argv(tmp_path)
    assert argv[0] == sys.executable
    assert argv[1:] == ["-m", "pytest"]


def test_is_environmental_failure_detects_missing_module():
    out = (
        "ImportError while importing test module 'tests/test_api.py'.\n"
        "E   ModuleNotFoundError: No module named 'flask'\n"
    )
    assert python_env.is_environmental_failure(out) is True


def test_is_environmental_failure_false_for_assertion_failure():
    out = "tests/test_x.py::test_add FAILED\nE   assert 1 == 2\n"
    assert python_env.is_environmental_failure(out) is False
    assert python_env.is_environmental_failure("") is False


def test_is_python_workspace(tmp_path):
    assert python_env.is_python_workspace(tmp_path) is False
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_NODEV, encoding="utf-8")
    assert python_env.is_python_workspace(tmp_path) is True
