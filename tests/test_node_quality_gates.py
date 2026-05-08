"""Node workspace quality gate behavior."""

from __future__ import annotations

import os

import pytest

from autonomous_agent_builder.quality_gates.base import GateStatus
from autonomous_agent_builder.quality_gates.code_quality import CodeQualityGate
from autonomous_agent_builder.quality_gates.testing import TestingGate as NodeTestingGate


@pytest.fixture
def node_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "package.json").write_text(
        '{\n'
        '  "scripts": {\n'
        '    "lint": "eslint src",\n'
        '    "build": "tsc && vite build",\n'
        '    "test": "vitest run"\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    (workspace / "tsconfig.json").write_text("{}", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npm = bin_dir / "npm"
    npm.write_text(
        "#!/usr/bin/env bash\n"
        "set -u\n"
        "echo npm \"$@\"\n"
        "if [[ \"$*\" == \"run lint\" && \"${AAB_FAKE_NPM_FAIL_LINT:-}\" == \"1\" ]]; then exit 2; fi\n"
        "if [[ \"$*\" == \"run build\" && \"${AAB_FAKE_NPM_FAIL_BUILD:-}\" == \"1\" ]]; then exit 2; fi\n"
        "if [[ \"$*\" == \"test\" && \"${AAB_FAKE_NPM_FAIL_TEST:-}\" == \"1\" ]]; then exit 2; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    npm.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return workspace


@pytest.mark.asyncio
async def test_code_quality_autodetects_node_and_runs_lint_build(node_workspace):
    result = await CodeQualityGate(language="python").run(str(node_workspace))

    assert result.status == GateStatus.PASS
    assert result.evidence["tool"] == "npm"
    assert [check["command"] for check in result.evidence["checks"]] == [
        "npm run lint",
        "npm run build",
    ]


@pytest.mark.asyncio
async def test_code_quality_fails_when_package_lint_fails(node_workspace, monkeypatch):
    monkeypatch.setenv("AAB_FAKE_NPM_FAIL_LINT", "1")

    result = await CodeQualityGate(language="python").run(str(node_workspace))

    assert result.status == GateStatus.FAIL
    assert result.error_code == "LINT_FAILED"
    assert result.remediation_possible is True


@pytest.mark.asyncio
async def test_testing_gate_autodetects_node_and_runs_package_test(node_workspace):
    result = await NodeTestingGate(language="python").run(str(node_workspace))

    assert result.status == GateStatus.PASS
    assert result.evidence["tool"] == "npm"
    assert result.evidence["command"] == "npm test"


@pytest.mark.asyncio
async def test_testing_gate_runs_node_test_script_without_injected_run_arg(tmp_path, monkeypatch):
    workspace = tmp_path / "node-test-workspace"
    workspace.mkdir()
    (workspace / "package.json").write_text(
        '{\n'
        '  "scripts": {\n'
        '    "test": "node --test"\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npm = bin_dir / "npm"
    npm.write_text(
        "#!/usr/bin/env bash\n"
        "set -u\n"
        "echo npm \"$@\"\n"
        "if [[ \"$*\" == \"test -- --run\" ]]; then exit 2; fi\n"
        "if [[ \"$*\" == \"test\" ]]; then exit 0; fi\n"
        "exit 3\n",
        encoding="utf-8",
    )
    npm.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    result = await NodeTestingGate(language="node").run(str(workspace))

    assert result.status == GateStatus.PASS
    assert result.evidence["command"] == "npm test"


@pytest.mark.asyncio
async def test_flask_language_runs_python_quality_gate(tmp_path, monkeypatch):
    workspace = tmp_path / "flask-workspace"
    workspace.mkdir()
    (workspace / "app.py").write_text("print('hello')\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ruff = bin_dir / "ruff"
    ruff.write_text("#!/usr/bin/env bash\necho '[]'\nexit 0\n", encoding="utf-8")
    ruff.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    result = await CodeQualityGate(language="Flask").run(str(workspace))

    assert result.status == GateStatus.PASS
    assert result.error_code is None
    assert result.evidence["tool"] == "ruff"


@pytest.mark.asyncio
async def test_flask_language_runs_python_testing_gate(tmp_path, monkeypatch):
    workspace = tmp_path / "flask-workspace"
    workspace.mkdir()
    (workspace / "app.py").write_text("print('hello')\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pytest_bin = bin_dir / "pytest"
    pytest_bin.write_text("#!/usr/bin/env bash\necho '1 passed'\nexit 0\n", encoding="utf-8")
    pytest_bin.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    result = await NodeTestingGate(language="Flask").run(str(workspace))

    assert result.status == GateStatus.PASS
    assert result.error_code is None
    assert result.evidence["tool"] == "pytest"
