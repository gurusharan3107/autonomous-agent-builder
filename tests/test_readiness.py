from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from autonomous_agent_builder.cli.main import app
from autonomous_agent_builder.onboarding import load_onboarding_state
from autonomous_agent_builder.services.readiness import (
    READY_STATE,
    assess_readiness,
    load_readiness_status,
)
from autonomous_agent_builder.services.runtime_guidance import render_project_runtime_guidance

runner = CliRunner()


@pytest.fixture(autouse=True)
def builder_source_env(monkeypatch, tmp_path: Path) -> Path:
    path = tmp_path.parent / f"{tmp_path.name}-builder-source.env"
    monkeypatch.setenv("AAB_BUILDER_SOURCE_ENV", str(path))
    return path


def _phase(phase_id: str, status: str = "passed", result: dict | None = None) -> dict:
    return {
        "id": phase_id,
        "title": phase_id.replace("_", " ").title(),
        "status": status,
        "message": "",
        "started_at": None,
        "finished_at": None,
        "result": result or {},
        "error": None,
    }


def _write_project(
    tmp_path: Path,
    *,
    mode: str,
    kb: bool = False,
    claude_md: bool = True,
    agents_md: bool = False,
    telemetry_env: bool = True,
    runtime_sdk: str = "claude",
) -> Path:
    root = tmp_path
    (root / ".git").mkdir()
    if claude_md:
        (root / "CLAUDE.md").write_text("# Test\n", encoding="utf-8")
    if agents_md:
        (root / "AGENTS.md").write_text("# Test\n", encoding="utf-8")
    if telemetry_env:
        if runtime_sdk.startswith("codex"):
            env_text = (
                f'RUNTIME_SDK="{runtime_sdk}"\n'
                'AAB_CLAUDE_OTEL_ENABLED="0"\n'
                'AAB_CLAUDE_OTEL_ENDPOINT="http://localhost:4318"\n'
                'AAB_CLAUDE_OTEL_SERVICE_NAME="test"\n'
                'AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID="true"\n'
                'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="1"\n'
                'AAB_CODEX_TELEMETRY_SOURCE="codex_app_server_jsonrpc"\n'
                'AAB_CODEX_TELEMETRY_COST_SOURCE="subscription_unmetered"\n'
            )
        else:
            env_text = (
                'RUNTIME_SDK="claude"\n'
                "AAB_CLAUDE_OTEL_ENABLED=1\n"
                "AAB_CLAUDE_OTEL_ENDPOINT=https://otel.example.com\n"
                "AAB_CLAUDE_OTEL_SERVICE_NAME=test\n"
                "AAB_CLAUDE_OTEL_INCLUDE_SESSION_ID=true\n"
                'AAB_CODEX_RUNTIME_TELEMETRY_ENABLED="0"\n'
            )
        Path(os.environ["AAB_BUILDER_SOURCE_ENV"]).write_text(env_text, encoding="utf-8")
    builder_dir = root / ".agent-builder"
    builder_dir.mkdir()
    (builder_dir / "config.yaml").write_text("project:\n  name: test\n", encoding="utf-8")
    (builder_dir / "agent_builder.db").write_text("", encoding="utf-8")
    phases = [
        _phase("repo_detect"),
        _phase("project_seed"),
        _phase("repo_scan"),
        _phase("work_item_seed"),
    ]
    if mode == "forward_engineering":
        (root / "README.md").write_text("# Test\n", encoding="utf-8")
        phases.extend(
            [
                _phase(
                    "kb_extract",
                    result={"skipped": True, "reason": "forward_engineering_onboarding"},
                ),
                _phase(
                    "kb_validate",
                    result={"skipped": True, "reason": "forward_engineering_onboarding"},
                ),
            ]
        )
        kb_status = {"quality_gate": "deferred"}
    else:
        (root / "src").mkdir()
        (root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
        phases.extend(
            [
                _phase("kb_extract", "passed" if kb else "pending"),
                _phase("kb_validate", "passed" if kb else "pending"),
            ]
        )
        kb_status = {"quality_gate": "passed" if kb else "pending"}
    phases.append(_phase("ready", "pending"))
    state = {
        "repo": {"root": str(root), "name": root.name, "language": "python", "framework": ""},
        "onboarding_mode": mode,
        "current_phase": "repo_scan",
        "ready": False,
        "started_at": None,
        "updated_at": "2026-04-29T00:00:00+00:00",
        "phases": phases,
        "entity_counts": {"projects": 1, "features": 1, "tasks": 1},
        "kb_status": kb_status,
        "scan_summary": {
            "entrypoints": ["src/main.py"] if mode == "reverse_engineering" else [],
            "important_files": ["src/main.py"] if mode == "reverse_engineering" else ["README.md"],
            "has_api": mode == "reverse_engineering",
        },
        "archives": [],
        "errors": [],
    }
    (builder_dir / "onboarding-state.json").write_text(json.dumps(state), encoding="utf-8")
    return root


def test_forward_readiness_skips_kb_and_allows_init_project_flow(tmp_path: Path) -> None:
    root = _write_project(tmp_path, mode="forward_engineering")

    payload = assess_readiness(root)

    assert payload["mode"] == "forward_engineering"
    assert payload["state"] == READY_STATE
    assert payload["can_continue"] is True
    skipped = {check["id"] for check in payload["checks"] if check["status"] == "skipped"}
    assert "forward_kb_extract_deferred" in skipped
    assert "forward_kb_validate_deferred" in skipped


def test_reverse_readiness_blocks_without_kb_validation(tmp_path: Path) -> None:
    root = _write_project(tmp_path, mode="reverse_engineering", kb=False)

    payload = assess_readiness(root)

    assert payload["mode"] == "reverse_engineering"
    assert payload["state"] == "blocked"
    assert payload["can_continue"] is False
    assert any(reason["code"] == "phase_kb_extract" for reason in payload["blocking_reasons"])


def test_readiness_blocks_without_project_claude_md(tmp_path: Path) -> None:
    root = _write_project(tmp_path, mode="forward_engineering", claude_md=False)

    payload = assess_readiness(root)

    assert payload["state"] == "blocked"
    assert any(reason["code"] == "project_claude_md" for reason in payload["blocking_reasons"])
    assert payload["next"][0]["command"] == "builder init"


def test_codex_readiness_requires_project_agents_md(tmp_path: Path) -> None:
    root = _write_project(
        tmp_path,
        mode="forward_engineering",
        claude_md=False,
        runtime_sdk="codex_sdk",
    )

    payload = assess_readiness(root)

    assert payload["state"] == "blocked"
    assert any(reason["code"] == "project_agents_md" for reason in payload["blocking_reasons"])
    assert not any(reason["code"] == "project_claude_md" for reason in payload["blocking_reasons"])


def test_codex_readiness_passes_with_project_agents_md(tmp_path: Path) -> None:
    root = _write_project(
        tmp_path,
        mode="forward_engineering",
        claude_md=False,
        agents_md=True,
        runtime_sdk="codex_sdk",
    )

    payload = assess_readiness(root)

    assert payload["state"] == READY_STATE
    assert "feature_list_present" not in payload["invalidated_by"]
    assert any(check["id"] == "project_agents_md" for check in payload["checks"])


def test_readiness_blocks_without_telemetry_env(tmp_path: Path) -> None:
    root = _write_project(tmp_path, mode="forward_engineering", telemetry_env=False)

    payload = assess_readiness(root)

    assert payload["state"] == "blocked"
    assert any(reason["code"] == "telemetry_env_config" for reason in payload["blocking_reasons"])


def test_readiness_blocks_when_telemetry_content_export_enabled(tmp_path: Path) -> None:
    root = _write_project(tmp_path, mode="forward_engineering")
    with Path(os.environ["AAB_BUILDER_SOURCE_ENV"]).open("a", encoding="utf-8") as handle:
        handle.write("AAB_CLAUDE_OTEL_LOG_TOOL_CONTENT=1\n")

    payload = assess_readiness(root)

    assert payload["state"] == "blocked"
    assert any(reason["code"] == "telemetry_content_safe" for reason in payload["blocking_reasons"])


def test_readiness_reports_optional_failure_when_local_otel_collector_is_unreachable(
    monkeypatch, tmp_path: Path
) -> None:
    def refuse_connection(*_args, **_kwargs):
        raise ConnectionRefusedError("collector not listening")

    monkeypatch.setattr(
        "autonomous_agent_builder.observability.collector.socket.create_connection",
        refuse_connection,
    )
    root = _write_project(tmp_path, mode="forward_engineering")
    env_path = Path(os.environ["AAB_BUILDER_SOURCE_ENV"])
    env_path.write_text(
        env_path.read_text(encoding="utf-8").replace(
            "AAB_CLAUDE_OTEL_ENDPOINT=https://otel.example.com",
            "AAB_CLAUDE_OTEL_ENDPOINT=http://localhost:4318",
        ),
        encoding="utf-8",
    )

    payload = assess_readiness(root)
    telemetry_check = next(
        check for check in payload["checks"] if check["id"] == "telemetry_env_config"
    )

    assert payload["state"] == READY_STATE
    assert payload["summary"]["optional_failed"] == 1
    assert not payload["blocking_reasons"]
    assert telemetry_check["status"] == "passed"
    assert telemetry_check["evidence"][0]["collector_reachable"] is False


def test_reverse_readiness_passes_with_kb_validation(tmp_path: Path) -> None:
    root = _write_project(tmp_path, mode="reverse_engineering", kb=True)

    payload = assess_readiness(root)

    assert payload["state"] == READY_STATE
    assert payload["summary"]["required_failed"] == 0


def test_readiness_passes_with_builder_created_day0_contract(tmp_path: Path) -> None:
    root = _write_project(tmp_path, mode="forward_engineering")
    (root / "CLAUDE.md").write_text(
        render_project_runtime_guidance(
            project_name="test",
            mode="forward_engineering",
            language="python",
            framework="flask",
        ),
        encoding="utf-8",
    )

    payload = assess_readiness(root)

    assert payload["state"] == READY_STATE
    assert not any(
        reason["code"] in {"runtime_guidance_contract", "deterministic_command_slots"}
        for reason in payload["blocking_reasons"]
    )


def test_status_does_not_invalidate_when_app_manifest_changes(tmp_path: Path) -> None:
    root = _write_project(tmp_path, mode="forward_engineering")
    assess_readiness(root)
    (root / "pyproject.toml").write_text("[project]\nname = 'changed'\n", encoding="utf-8")

    payload = load_readiness_status(root)

    assert payload["state"] == READY_STATE
    assert "manifest_hashes" not in payload["invalidated_by"]


def test_status_invalidates_when_project_claude_md_changes(tmp_path: Path) -> None:
    root = _write_project(tmp_path, mode="forward_engineering")
    assess_readiness(root)
    (root / "CLAUDE.md").write_text("# Changed\n", encoding="utf-8")

    payload = load_readiness_status(root)

    assert payload["state"] == "unknown"
    assert "runtime_guidance" in payload["invalidated_by"]


def test_forward_feature_list_creation_does_not_invalidate_readiness(tmp_path: Path) -> None:
    root = _write_project(tmp_path, mode="forward_engineering")
    assess_readiness(root)
    feature_list = root / ".claude" / "progress" / "feature-list.json"
    feature_list.parent.mkdir(parents=True)
    feature_list.write_text('{"features": []}\n', encoding="utf-8")

    payload = load_readiness_status(root)

    assert payload["state"] == READY_STATE


def test_onboarding_status_reassesses_stale_ready_state(tmp_path: Path) -> None:
    root = _write_project(tmp_path, mode="forward_engineering")
    state_path = root / ".agent-builder" / "onboarding-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_phase"] = "ready"
    state["ready"] = True
    state["phases"][-1]["status"] = "passed"
    state["phases"][-1]["result"] = {"ready": True}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    assess_readiness(root, onboarding_state=state, write=True)

    state["updated_at"] = "2026-05-03T00:00:00+00:00"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    stale = load_readiness_status(root)
    assert stale["state"] == "unknown"
    assert stale["invalidated_by"] == ["onboarding_state_hash"]

    loaded = load_onboarding_state(root)

    assert loaded["ready"] is True
    assert loaded["current_phase"] == "ready"
    repaired = load_readiness_status(root)
    assert repaired["state"] == READY_STATE
    assert repaired.get("invalidated_by", []) == []


def test_onboarding_status_ignores_stale_blocker_when_ready_passed(tmp_path: Path) -> None:
    root = _write_project(tmp_path, mode="forward_engineering")
    state_path = root / ".agent-builder" / "onboarding-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_phase"] = "repo_detect"
    state["ready"] = False
    state["errors"] = [{"phase": "repo_detect", "error": "Claude rate limit"}]
    state["phases"][0]["status"] = "blocked"
    state["phases"][0]["error"] = "Claude rate limit"
    state["phases"][-1]["status"] = "passed"
    state["phases"][-1]["result"] = {"ready": True}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    assess_readiness(root, onboarding_state=state, write=True)

    loaded = load_onboarding_state(root)

    assert loaded["ready"] is True
    assert loaded["current_phase"] == "ready"
    assert loaded["errors"] == []


def test_forward_ready_project_stays_ready_after_generated_app_files(tmp_path: Path) -> None:
    root = _write_project(tmp_path, mode="forward_engineering")
    state = json.loads((root / ".agent-builder" / "onboarding-state.json").read_text())
    state["ready"] = True
    state["current_phase"] = "ready"
    for phase in state["phases"]:
        phase["status"] = "passed"
    (root / ".agent-builder" / "onboarding-state.json").write_text(
        json.dumps(state),
        encoding="utf-8",
    )
    (root / "app.py").write_text("print('generated app')\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname = 'generated'\n", encoding="utf-8")

    payload = assess_readiness(root)

    assert payload["state"] == READY_STATE
    assert not any(
        reason["code"] == "forward_workspace_shape" for reason in payload["blocking_reasons"]
    )


def test_readiness_cli_status_missing_is_unknown(tmp_path: Path) -> None:
    result = runner.invoke(app, ["readiness", "status", "--project-root", str(tmp_path), "--json"])

    assert result.exit_code == 3
    payload = json.loads(result.stdout)
    assert payload["state"] == "unknown"
    assert payload["exit_code"] == 3
    assert payload["next"][0]["command"] == "builder readiness assess --json"
    assert payload["actionable_next"] == "builder readiness assess --json"
    assert (
        payload["progressive_disclosure"][1]["command"] == "builder readiness status --json --full"
    )
    assert "phases" not in payload


def test_readiness_cli_assess_returns_blocked_exit_code(tmp_path: Path) -> None:
    root = _write_project(tmp_path, mode="reverse_engineering", kb=False)

    result = runner.invoke(app, ["readiness", "assess", "--project-root", str(root), "--json"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["state"] == "blocked"
    assert payload["exit_code"] == 2

    full_result = runner.invoke(
        app,
        ["readiness", "assess", "--project-root", str(root), "--json", "--full"],
    )
    assert full_result.exit_code == 2
    full_payload = json.loads(full_result.stdout)
    assert "checks" in full_payload
    assert full_payload["blocking_reasons"][0]["evidence"]
