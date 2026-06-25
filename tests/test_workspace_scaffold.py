"""Unit tests for the scaffold helpers."""

from __future__ import annotations

from pathlib import Path

from autonomous_agent_builder.services.workspace_scaffold import (
    ScaffoldResult,
    build_scaffold_template_vars,
    parse_scaffold_result,
    should_scaffold,
    write_minimal_gate_config,
)


def test_should_scaffold_returns_true_for_empty_workspace(tmp_path) -> None:
    needs, detected = should_scaffold(str(tmp_path))

    assert needs is True
    assert detected == "unknown"


def test_should_scaffold_skips_when_python_already_present(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")

    needs, detected = should_scaffold(str(tmp_path))

    assert needs is False
    assert detected == "python"


def test_should_scaffold_runs_when_python_partial_only_requirements(tmp_path) -> None:
    # Regression for FINDING-20 (live devpulse run): requirements.txt alone
    # made _detect_language return "python", but pyproject.toml was missing
    # and the code_quality gate then errored with FileNotFoundError trying
    # to invoke ruff.
    (tmp_path / "requirements.txt").write_text("fastapi\n")

    needs, detected = should_scaffold(str(tmp_path))

    assert needs is True
    assert detected == "python"


def test_should_scaffold_skips_when_node_already_present(tmp_path) -> None:
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "eslint.config.js").write_text("module.exports = {};")

    needs, detected = should_scaffold(str(tmp_path))

    assert needs is False
    assert detected == "node"


def test_should_scaffold_runs_when_node_lacks_eslint_config(tmp_path) -> None:
    (tmp_path / "package.json").write_text("{}")

    needs, detected = should_scaffold(str(tmp_path))

    assert needs is True
    assert detected == "node"


def test_parse_scaffold_result_handles_well_formed_output() -> None:
    output = (
        "Decided python-cli stack and wrote minimum config.\n"
        'SCAFFOLD_RESULT_JSON: {"language": "python", "stack": "python-cli", '
        '"files_written": ["pyproject.toml", "src/demo/__init__.py"], '
        '"gate_set": ["ruff", "pytest"]}'
    )

    result = parse_scaffold_result(output)

    assert result.action == "scaffolded"
    assert result.language == "python"
    assert result.stack == "python-cli"
    assert result.files_written == ("pyproject.toml", "src/demo/__init__.py")
    assert result.gate_set == ("ruff", "pytest")


def test_parse_scaffold_result_blocks_on_missing_marker() -> None:
    result = parse_scaffold_result("I scaffolded the workspace successfully.")

    assert result.action == "blocked"
    assert result.reason.startswith("scaffold_failed:")
    assert "SCAFFOLD_RESULT_JSON" in result.reason


def test_parse_scaffold_result_blocks_on_malformed_json() -> None:
    result = parse_scaffold_result(
        "Done.\nSCAFFOLD_RESULT_JSON: {language: python}"  # missing quotes
    )

    assert result.action == "blocked"
    assert "malformed" in result.reason


def test_parse_scaffold_result_blocks_on_empty_output() -> None:
    result = parse_scaffold_result("")

    assert result.action == "blocked"
    assert result.reason.startswith("scaffold_failed:")


def test_parse_scaffold_result_blocks_when_language_missing() -> None:
    result = parse_scaffold_result('SCAFFOLD_RESULT_JSON: {"stack": "x", "files_written": []}')

    assert result.action == "blocked"
    assert "language" in result.reason


def test_build_scaffold_template_vars_renders_minimum_fields() -> None:
    vars_dict = build_scaffold_template_vars(
        feature_description="Real-time GitHub activity feed",
        project_name="devpulse",
        workspace_path="/tmp/devpulse",
    )

    assert vars_dict["feature_description"] == "Real-time GitHub activity feed"
    assert vars_dict["project_name"] == "devpulse"
    assert vars_dict["workspace_path"] == "/tmp/devpulse"
    assert vars_dict["operator_answers"] == "(none yet)"


def test_build_scaffold_template_vars_serialises_operator_answers() -> None:
    vars_dict = build_scaffold_template_vars(
        feature_description="x",
        project_name="p",
        workspace_path="/tmp/p",
        operator_answers={"stack": "web app"},
    )

    assert '"stack": "web app"' in vars_dict["operator_answers"]


def test_write_minimal_gate_config_python_creates_pyproject(tmp_path) -> None:
    # Live regression: scaffold agent ran 22 turns but didn't write
    # pyproject.toml. The deterministic fallback fills that gap when
    # language=python.
    (tmp_path / "requirements.txt").write_text("fastapi\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "demo").mkdir()

    wrote, written = write_minimal_gate_config(str(tmp_path), "python", "devpulse")

    assert wrote is True
    pyproject = tmp_path / "pyproject.toml"
    content = pyproject.read_text()
    assert "[tool.ruff" in content
    assert "[tool.pytest.ini_options]" in content
    assert "devpulse" in content
    assert (tmp_path / "src" / "demo" / "__init__.py").exists()
    needs, _ = should_scaffold(str(tmp_path))
    assert needs is False


def test_write_minimal_gate_config_node_creates_package_and_eslint(tmp_path) -> None:
    wrote, written = write_minimal_gate_config(str(tmp_path), "node", "devpulse")

    assert wrote is True
    assert (tmp_path / "package.json").exists()
    assert (tmp_path / "eslint.config.js").exists()
    needs, _ = should_scaffold(str(tmp_path))
    assert needs is False
    # ESLint config must use globals.browser so browser APIs (fetch, URL, etc.) resolve,
    # and must ignore node_modules + .agent-builder so bundled files are never linted.
    eslint_content = (tmp_path / "eslint.config.js").read_text()
    assert "globals.browser" in eslint_content
    assert 'from "globals"' in eslint_content
    assert ".agent-builder/**" in eslint_content
    assert "node_modules/**" in eslint_content
    # package.json must declare globals devDependency.
    import json as _json

    pkg = _json.loads((tmp_path / "package.json").read_text())
    assert "globals" in pkg.get("devDependencies", {})


def test_write_minimal_gate_config_unsupported_language_does_nothing(tmp_path) -> None:
    wrote, written = write_minimal_gate_config(str(tmp_path), "elixir", "demo")

    assert wrote is False
    assert written == []


def test_write_minimal_gate_config_python_idempotent(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "existing"\n[tool.ruff]\n[tool.pytest.ini_options]\n'
    )

    wrote, written = write_minimal_gate_config(str(tmp_path), "python", "demo")

    assert wrote is False
    assert tmp_path / "pyproject.toml" not in [Path(p) for p in written]


def test_scaffold_result_dataclass_is_frozen() -> None:
    result = ScaffoldResult(action="scaffolded", language="python")

    try:
        result.language = "node"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("ScaffoldResult should be immutable")
