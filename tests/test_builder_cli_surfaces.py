"""Tests for builder retrieval and control-plane CLI surfaces."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from autonomous_agent_builder.agents.tool_registry import _SDK_BUILTINS
from autonomous_agent_builder.agents.tools.cli_tools import CLI_TOOLS
from autonomous_agent_builder.cli.commands import kb as kb_module
from autonomous_agent_builder.cli.commands import map as map_module
from autonomous_agent_builder.cli.commands import memory as memory_module
from autonomous_agent_builder.cli.commands import board as board_module
from autonomous_agent_builder.cli.commands import agent as agent_module
from autonomous_agent_builder.cli.commands import metrics as metrics_module
from autonomous_agent_builder.cli.commands import start_impl as start_impl_module
from autonomous_agent_builder.cli.commands import project as project_module
from autonomous_agent_builder.cli.commands import task as task_module
from autonomous_agent_builder.cli.commands import run as run_module
from autonomous_agent_builder.cli.commands import approval as approval_module
from autonomous_agent_builder.cli import quality_gates as quality_gate_registry
from autonomous_agent_builder.cli import main as main_module
from autonomous_agent_builder.cli.client import BuilderConnectivityError
from autonomous_agent_builder.cli.main import app
from autonomous_agent_builder.knowledge.agent_quality_gate import AgentQualityGateResult
from autonomous_agent_builder.knowledge.quality_gate import QualityCheck, QualityGateResult

runner = CliRunner()


def _assert_agent_json_contract(payload: dict, *, ok: bool = True) -> None:
    assert payload["ok"] is ok
    assert isinstance(payload["status"], str)
    assert isinstance(payload["exit_code"], int)
    assert payload["schema_version"] == "1"
    assert isinstance(payload["token_estimate"], int)
    assert isinstance(payload["truncated"], bool)


def _configure_local_kb(monkeypatch, tmp_path: Path) -> Path:
    project_root = tmp_path
    kb_root = project_root / ".agent-builder" / "knowledge"
    kb_root.mkdir(parents=True)
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(kb_root))
    return kb_root


def _write_local_kb_doc(kb_root: Path, doc_id: str, content: str) -> Path:
    path = kb_root / doc_id
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class _PathClient:
    def __init__(self, mapping: dict[str, object]):
        self.mapping = mapping

    def get(self, path: str, **params):
        key = path
        if params:
            if path == "/projects/":
                key = "/projects/"
            elif path == "/tasks":
                key = "/tasks"
            elif path == "/gates":
                key = "/gates"
            elif path == "/runs":
                key = "/runs"
            elif path == "/approval-gates":
                key = "/approval-gates"
        if key not in self.mapping:
            raise kb_module.AabApiError(404, {"detail": f"missing {key}"})
        value = self.mapping[key]
        if callable(value):
            return value(path, **params)
        return value

    def post(self, path: str, data=None):
        key = f"POST:{path}"
        if key not in self.mapping:
            raise kb_module.AabApiError(404, {"detail": f"missing {key}"})
        value = self.mapping[key]
        return value(path, data=data) if callable(value) else value

    def close(self) -> None:
        return None


def test_kb_summary_resolves_search_query(monkeypatch, tmp_path):
    kb_root = _configure_local_kb(monkeypatch, tmp_path)
    _write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags:\n"
            "  - builder\n"
            "  - system-docs\n"
            "---\n\n"
            "# Project Overview\n\n"
            "## Overview\n\n"
            "Builder generates seed system docs for the local repo into durable project knowledge.\n\n"
            "## Architecture\n\n"
            "FastAPI plus CLI surfaces.\n"
        ),
    )

    result = runner.invoke(app, ["knowledge", "summary", "overview", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["matched_on"] in {"search", "name", "prefix"}
    assert payload["id"] == "system-docs/project-overview.md"
    assert "seed system docs" in payload["summary"]


def test_kb_summary_accepts_multiword_query(monkeypatch, tmp_path):
    kb_root = _configure_local_kb(monkeypatch, tmp_path)
    _write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder, system-docs, seed]\n"
            "---\n\n"
            "# Project Overview\n\n"
            "Builder generates seed system docs for the local repo.\n"
        ),
    )

    result = runner.invoke(app, ["knowledge", "summary", "project", "overview", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["matched_on"] in {"search", "name", "prefix"}
    assert payload["id"] == "system-docs/project-overview.md"


def test_kb_show_section_returns_only_requested_heading(monkeypatch, tmp_path):
    kb_root = _configure_local_kb(monkeypatch, tmp_path)
    _write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder]\n"
            "---\n\n"
            "# Project Overview\n\n"
            "## Overview\n\n"
            "Top summary.\n\n"
            "## Architecture\n\n"
            "Only this section should be returned.\n\n"
            "## Next Steps\n\n"
            "Follow-up."
        ),
    )

    result = runner.invoke(
        app,
        [
            "knowledge",
            "show",
            "system-docs/project-overview.md",
            "--section",
            "Architecture",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["section"] == "Architecture"
    assert payload["content"] == "Only this section should be returned."


def test_kb_show_resolves_multiword_query(monkeypatch, tmp_path):
    kb_root = _configure_local_kb(monkeypatch, tmp_path)
    _write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder, system-docs, seed]\n"
            "---\n\n"
            "# Project Overview\n\n"
            "## Overview\n\n"
            "Builder generates seed system docs for the local repo.\n"
        ),
    )

    result = runner.invoke(app, ["knowledge", "show", "project", "overview", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["matched_on"] in {"search", "name", "prefix"}
    assert payload["id"] == "system-docs/project-overview.md"


def test_kb_show_section_resolves_multiword_query(monkeypatch, tmp_path):
    kb_root = _configure_local_kb(monkeypatch, tmp_path)
    _write_local_kb_doc(
        kb_root,
        "system-docs/system-architecture.md",
        (
            "---\n"
            "title: System Architecture\n"
            "tags: [system-docs, architecture]\n"
            "---\n\n"
            "# System Architecture\n\n"
            "## Overview\n\n"
            "Top summary.\n\n"
            "## Change guidance\n\n"
            "Refresh the doc after runtime wiring changes.\n"
        ),
    )

    result = runner.invoke(
        app,
        [
            "knowledge",
            "show",
            "system",
            "architecture",
            "--section",
            "Change guidance",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["matched_on"] in {"search", "name", "prefix"}
    assert payload["section"] == "Change guidance"
    assert payload["content"] == "Refresh the doc after runtime wiring changes."


def test_kb_show_missing_doc_does_not_fuzzy_resolve(monkeypatch, tmp_path):
    kb_root = _configure_local_kb(monkeypatch, tmp_path)
    _write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder, system-docs, seed]\n"
            "---\n\n"
            "# Project Overview\n\n"
            "Builder generates seed system docs for the local repo.\n"
        ),
    )

    result = runner.invoke(app, ["knowledge", "show", "missing-doc", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"
    assert payload["error"]["detail"]["query"] == "missing-doc"


def test_kb_search_json_is_compact(monkeypatch, tmp_path):
    kb_root = _configure_local_kb(monkeypatch, tmp_path)
    _write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder, system-docs, seed]\n"
            "version: 2\n"
            "card_summary: Project purpose and operator-facing overview.\n"
            "---\n\n"
            "# Project Overview\n\n"
            "Builder generates seed system docs for the local repo.\n"
        ),
    )

    result = runner.invoke(app, ["knowledge", "search", "overview", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["query"] == "overview"
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "system-docs/project-overview.md"
    assert "content" not in payload["results"][0]
    assert payload["results"][0]["preview"] == "Project purpose and operator-facing overview."
    assert payload["next_step"] == 'builder knowledge summary "overview" --json'


def test_kb_list_json_is_compact_by_default_and_full_when_requested(monkeypatch, tmp_path):
    kb_root = _configure_local_kb(monkeypatch, tmp_path)
    _write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder, system-docs, seed]\n"
            "version: 2\n"
            "card_summary: Project purpose and operator-facing overview.\n"
            "---\n\n"
            "# Project Overview\n\n"
            "Builder generates seed system docs for the local repo.\n"
        ),
    )

    compact = runner.invoke(app, ["knowledge", "list", "--json"])
    full = runner.invoke(app, ["knowledge", "list", "--json", "--full"])

    assert compact.exit_code == 0
    compact_payload = json.loads(compact.stdout)
    assert compact_payload["count"] == 1
    assert "content" not in compact_payload["results"][0]
    assert compact_payload["next_step"] == "builder knowledge show <doc-id> --section 'Change guidance' --json"
    assert "tags" not in compact_payload["results"][0]
    assert "version" not in compact_payload["results"][0]

    assert full.exit_code == 0
    full_payload = json.loads(full.stdout)
    assert full_payload["count"] == 1
    assert "content" in full_payload["results"][0]
    assert full_payload["next_step"] == "builder knowledge show <doc-id> --section 'Change guidance' --json"


def test_kb_show_not_found_suggests_search(monkeypatch, tmp_path):
    kb_root = _configure_local_kb(monkeypatch, tmp_path)
    _write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder, system-docs, seed]\n"
            "---\n\n"
            "# Project Overview\n\n"
            "Builder generates seed system docs for the local repo.\n"
        ),
    )

    result = runner.invoke(app, ["knowledge", "show", "missing", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "not_found"
    assert 'builder knowledge search "missing" --json' in payload["error"]["hint"]


def test_kb_search_works_without_server_client(monkeypatch, tmp_path):
    kb_root = _configure_local_kb(monkeypatch, tmp_path)
    _write_local_kb_doc(
        kb_root,
        "system-docs/onboarding-modes-and-external-validation.md",
        (
            "---\n"
            "title: Onboarding Modes and External Validation\n"
            "tags: [feature, onboarding, external-validation, system-docs]\n"
            "---\n\n"
            "# Onboarding Modes and External Validation\n\n"
            "Onboarding is the canonical feature surface for clean-slate and existing-repo setup.\n"
        ),
    )
    monkeypatch.setenv("AAB_API_URL", "http://127.0.0.1:1")

    result = runner.invoke(
        app,
        ["knowledge", "search", "onboarding", "existing", "repo", "--type", "system-docs", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "system-docs/onboarding-modes-and-external-validation.md"


def test_quality_gate_quality_gates_json():
    result = runner.invoke(app, ["quality-gate", "quality-gates", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "quality-gates"
    assert "--json is the stable machine contract" in payload["expectations"]


def test_quality_gate_builder_cli_json():
    result = runner.invoke(app, ["quality-gate", "builder-cli", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "builder-cli"
    assert "builder --help" in payload["commands"]
    assert "builder agent --help" in payload["commands"]
    assert "builder backlog --help" in payload["commands"]
    assert "builder knowledge --help" in payload["commands"]
    assert "startup orientation follows doctor -> map -> context" in payload["expectations"]
    assert "builder start is the single startup owner for the local dashboard and API; do not add parallel start or dashboard-publish entrypoints" in payload["expectations"]
    assert any(
        item.startswith("the CLI is the product adapter over stable services and schemas")
        for item in payload["expectations"]
    )
    assert "local knowledge list/search/summary/show remain usable when AAB_API_URL is unset, wrong, or the builder server is down" in payload["expectations"]
    assert "before adding or renaming a builder command, inspect existing top-level and group help so new behavior extends an owned surface instead of creating a parallel one" in payload["expectations"]
    assert "builder quality-gate claude-agent-sdk --json" in payload["commands"]
    assert 'AAB_API_URL=http://127.0.0.1:1 builder knowledge search "system architecture" --type system-docs --limit 3 --json' in payload["commands"]
    assert "workflow quality-gate cli-for-agents" in payload["commands"]


def test_builder_help_exposes_single_startup_owner():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "builder start --port 9876 Start the local dashboard and API" in result.stdout
    assert "│ server" not in result.stdout


def test_publish_dashboard_assets_builds_frontend_and_copies_dist(monkeypatch, tmp_path: Path):
    project_root = tmp_path
    frontend_dir = project_root / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "package.json").write_text('{"name":"frontend"}', encoding="utf-8")
    dist_dir = frontend_dir / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html>built</html>", encoding="utf-8")
    (dist_dir / "app.js").write_text("console.log('built')", encoding="utf-8")
    dashboard_dir = project_root / ".agent-builder" / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "stale.txt").write_text("old", encoding="utf-8")

    calls: list[tuple[list[str], Path]] = []

    def fake_run(cmd, cwd=None, check=None):
        calls.append((cmd, Path(cwd)))
        return None

    monkeypatch.setattr(start_impl_module.subprocess, "run", fake_run)

    result = start_impl_module._publish_dashboard_assets(project_root, dashboard_dir)

    assert result == {}
    assert calls == [(["npm", "run", "build"], frontend_dir)]
    assert not (dashboard_dir / "stale.txt").exists()
    assert (dashboard_dir / "index.html").read_text(encoding="utf-8") == "<html>built</html>"
    assert (dashboard_dir / "app.js").read_text(encoding="utf-8") == "console.log('built')"


def test_run_start_defaults_to_9876_and_reuses_that_port(monkeypatch, tmp_path: Path):
    agent_builder_dir = tmp_path / ".agent-builder"
    server_dir = agent_builder_dir / "server"
    dashboard_dir = agent_builder_dir / "dashboard"
    agent_builder_dir.mkdir()
    server_dir.mkdir()
    dashboard_dir.mkdir()
    (agent_builder_dir / "agent_builder.db").write_text("", encoding="utf-8")

    writes: list[int] = []
    kills: list[int] = []
    starts: list[tuple[str, int]] = []

    def fake_write_port_file(port: int, _dir: Path) -> None:
        writes.append(port)

    def fake_kill_process_on_port(port: int) -> bool:
        kills.append(port)
        return True

    def fake_publish_dashboard_assets(project_root: Path, dashboard_path: Path) -> dict[str, object]:
        assert project_root == tmp_path
        assert dashboard_path == dashboard_dir
        return {}

    def fake_start_uvicorn(*, server_path: Path, db_path: Path, dashboard_path: Path, host: str, port: int, debug: bool) -> None:
        starts.append((host, port))

    monkeypatch.setattr(start_impl_module, "_publish_dashboard_assets", fake_publish_dashboard_assets)
    monkeypatch.setattr(start_impl_module, "_start_uvicorn", fake_start_uvicorn)

    import autonomous_agent_builder.cli.port_manager as port_manager_module

    monkeypatch.setattr(port_manager_module, "write_port_file", fake_write_port_file)
    monkeypatch.setattr(port_manager_module, "kill_process_on_port", fake_kill_process_on_port)

    result = start_impl_module.run_start(agent_builder_dir=agent_builder_dir, port=None, host="127.0.0.1", debug=False)

    assert result["error"] == "Server failed to start"
    assert writes == [9876]
    assert kills == [9876]
    assert starts == [("127.0.0.1", 9876)]


def test_quality_gate_claude_agent_sdk_json():
    result = runner.invoke(app, ["quality-gate", "claude-agent-sdk", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "claude-agent-sdk"
    assert any(
        item.startswith("SDK-facing changes remain limited to runtime execution mechanics")
        for item in payload["expectations"]
    )
    assert any(
        item.startswith("shared services or stable product APIs are the preferred internal integration path")
        for item in payload["expectations"]
    )


def test_quality_gate_architecture_boundary_json():
    result = runner.invoke(app, ["quality-gate", "architecture-boundary", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "architecture-boundary"
    assert "workflow --docs-dir=docs read quality-gate/architecture-boundary" in payload["commands"]
    assert "builder quality-gate claude-md --json" in payload["commands"]
    assert any(
        item.startswith("runtime-boundary changes preserve the ownership split already documented")
        for item in payload["expectations"]
    )
    assert any(
        item.startswith("Codex subagents remain optional specialist lanes")
        for item in payload["expectations"]
    )


def test_quality_gate_lists_surfaces_json():
    result = runner.invoke(app, ["quality-gate", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["count"] >= 1
    assert any(item["surface"] == "builder-cli" for item in payload["surfaces"])
    assert any(item["surface"] == "claude-md" for item in payload["surfaces"])
    assert any(item["surface"] == "claude-agent-sdk" for item in payload["surfaces"])
    assert any(item["surface"] == "architecture-boundary" for item in payload["surfaces"])
    assert not any(item["surface"] == "nonexistent" for item in payload["surfaces"])


def test_quality_gate_architecture_boundary_surface_json():
    result = runner.invoke(app, ["quality-gate", "architecture-boundary", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["title"] == "Architecture boundary quality gate"
    assert any(
        item.startswith("runtime-boundary changes preserve the ownership split already documented")
        for item in payload["expectations"]
    )


def test_quality_gate_claude_md_surface_json():
    result = runner.invoke(app, ["quality-gate", "claude-md", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "claude-md"
    assert payload["title"] == "CLAUDE.md quality gate"
    assert "workflow --docs-dir=docs read quality-gate/claude-md" in payload["commands"]
    assert any(
        item.startswith("CLAUDE.md stays a runtime contract for this repo")
        for item in payload["expectations"]
    )


def test_quality_gate_surface_json():
    result = runner.invoke(app, ["quality-gate", "builder-cli", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "builder-cli"
    assert any(
        item.startswith("the knowledge lane still provides one coherent command family")
        for item in payload["expectations"]
    )


def test_quality_gate_claude_agent_sdk_surface_json():
    result = runner.invoke(app, ["quality-gate", "claude-agent-sdk", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["surface"] == "claude-agent-sdk"
    assert any(
        item.startswith("routing, blocked states, retries, and human checkpoints are not reassigned")
        for item in payload["expectations"]
    )


def test_gate_command_removed():
    result = runner.invoke(app, ["gate", "contract", "builder-cli", "--json"])

    assert result.exit_code != 0
    assert "No such command 'gate'" in result.stdout


def test_kb_contract_defaults_to_system_docs():
    result = runner.invoke(app, ["knowledge", "contract", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["doc_type"] == "system-docs"
    assert payload["required_sections"] == [
        "# Title",
        "## Overview",
        "## Boundaries",
        "## Invariants",
        "## Evidence",
        "## Change guidance",
    ]


def test_context_json():
    result = runner.invoke(app, ["context", "verification", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["task"] == "verification"
    assert "builder quality-gate quality-gates" in payload["commands"]


def test_quality_gate_malformed_frontmatter_errors(monkeypatch, tmp_path):
    gate_dir = tmp_path / "quality-gate"
    gate_dir.mkdir()
    (gate_dir / "broken.md").write_text(
        "---\n"
        "title: Broken Gate\n"
        "surface: broken\n"
        "summary: bad\n"
        "commands: nope\n"
        "---\n\n"
        "# Broken\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(quality_gate_registry, "QUALITY_GATE_DIR", gate_dir)

    result = runner.invoke(app, ["quality-gate", "--json"])

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "invalid_quality_gate_doc"
    assert "frontmatter" in payload["error"]["detail"]


def test_root_help_hides_gate_surface():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "│ gate" not in result.stdout


def test_map_json(tmp_path, monkeypatch):
    project_root = tmp_path
    kb_dir = project_root / ".agent-builder" / "knowledge" / "system-docs"
    kb_dir.mkdir(parents=True)
    (kb_dir / "project-overview.md").write_text("# Project Overview\n", encoding="utf-8")

    memory_dir = project_root / ".memory"
    memory_dir.mkdir()
    (memory_dir / "routing.json").write_text(
        json.dumps(
            {
                "memories": [
                    {"slug": "one", "type": "decision", "status": "active"},
                    {"slug": "two", "type": "correction", "status": "flagged"},
                ]
            }
        ),
        encoding="utf-8",
    )

    feature_list_dir = project_root / ".claude" / "progress"
    feature_list_dir.mkdir(parents=True)
    (feature_list_dir / "feature-list.json").write_text(
        json.dumps(
            {
                "features": [
                    {"status": "done"},
                    {"status": "pending"},
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AAB_PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("AAB_LOCAL_KB_ROOT", str(project_root / ".agent-builder" / "knowledge"))
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_dir))
    monkeypatch.setattr(
        map_module,
        "_server_snapshot",
        lambda: {
            "reachable": True,
            "base_url": "http://localhost:8000",
            "projects": {"count": 1},
            "board": {"active": 2, "review": 1},
            "metrics": {"total_runs": 3, "total_cost": 1.25, "gate_pass_rate": 50.0},
        },
    )

    result = runner.invoke(app, ["map", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["knowledge_base"]["documents"] == 1
    assert payload["memory"]["flagged"] == 1
    assert payload["server"]["projects"]["count"] == 1


def test_agent_surfaces_expose_official_learning_mutation_tools():
    assert "builder_kb_extract" in CLI_TOOLS
    assert "builder_kb_add" in CLI_TOOLS
    assert "builder_kb_update" in CLI_TOOLS
    assert "builder_memory_add" in CLI_TOOLS
    assert "builder_task_list" in CLI_TOOLS
    assert "mcp__builder__kb_extract" in _SDK_BUILTINS
    assert "mcp__builder__kb_add" in _SDK_BUILTINS
    assert "mcp__builder__kb_update" in _SDK_BUILTINS
    assert "mcp__builder__memory_add" in _SDK_BUILTINS


def test_root_doctor_supports_global_json(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "_doctor_payload",
        lambda: {
            "ok": True,
            "status": "ok",
            "exit_code": 0,
            "passed": True,
            "schema_version": "1",
            "tool": "builder",
            "checks": {
                "project": {
                    "initialized": True,
                    "cwd": "/tmp/project",
                    "project_root": "/tmp/project",
                    "agent_builder_dir": "/tmp/project/.agent-builder",
                    "hint": "",
                },
                "config": {
                    "api_base_url": "http://127.0.0.1:9876",
                    "api_base_url_source": "repo-port",
                    "auth_required": False,
                    "auth_source": "not_required",
                },
                "server": {
                    "reachable": True,
                    "healthy": True,
                    "status_code": 200,
                    "contract_ok": True,
                    "payload": {"status": "ok"},
                },
            },
            "next": "builder map",
            "next_step": "builder map",
        },
    )

    result = runner.invoke(app, ["--json", "doctor"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["exit_code"] == 0
    assert payload["tool"] == "builder"
    assert payload["next"] == "builder map"
    assert payload["checks"]["server"]["healthy"] is True


def test_root_invalid_command_emits_hint():
    result = runner.invoke(app, ["does-not-exist"])

    assert result.exit_code == 2
    assert "Error: No such command 'does-not-exist'." in result.output
    assert "Hint:" in result.output
    assert "builder --help" in result.output


def test_root_invalid_command_supports_global_json():
    result = runner.invoke(app, ["--json", "does-not-exist"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] == 2
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "invalid_usage"
    assert payload["error"]["message"] == "No such command 'does-not-exist'."
    assert payload["next"] == "builder --help"
    assert payload["error"]["hint"] == "builder --help"


def test_root_invalid_option_supports_global_json():
    result = runner.invoke(app, ["--json", "--badflag"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] == 2
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "invalid_usage"
    assert payload["error"]["message"] == "No such option: --badflag"
    assert payload["next"] == "builder --help"


def test_logs_command_reads_error_events_from_local_db(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-1", "2026-04-22 10:00:00", "2026-04-22 10:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-1",
            "sess-1",
            "tool_error",
            json.dumps(
                {
                    "tool_name": "mcp__builder__kb_add",
                    "content": "Missing required sections for feature: Current behavior",
                }
            ),
            "completed",
            "2026-04-22 10:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "--error", "--json", "--no-follow"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["results"][0]["event_type"] == "tool_error"
    assert payload["results"][0]["tool_name"] == "mcp__builder__kb_add"


def test_logs_ndjson_emits_line_delimited_compact_events(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-ndjson", "2026-04-22 10:00:00", "2026-04-22 10:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-ndjson",
            "sess-ndjson",
            "tool_error",
            json.dumps(
                {
                    "tool_name": "mcp__builder__kb_add",
                    "content": "Missing required sections for feature: Current behavior",
                }
            ),
            "completed",
            "2026-04-22 10:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "--session", "sess-ndjson", "--error", "--compact", "--ndjson", "--no-follow"])

    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event_type"] == "tool_error"
    assert payload["tool_name"] == "mcp__builder__kb_add"
    assert payload["outcome"] == "error"
    assert payload["error_message"] == "Missing required sections for feature: Current behavior"


def test_logs_rejects_json_and_ndjson_together():
    result = runner.invoke(app, ["logs", "--json", "--ndjson"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_usage"


def test_logs_command_supports_info_compact(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-2", "2026-04-22 11:00:00", "2026-04-22 11:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-2",
            "sess-2",
            "tool_result",
            json.dumps(
                {
                    "tool_name": "mcp__builder__kb_add",
                    "tool_input": {"doc_type": "feature"},
                    "content": "{\"status\":\"ok\",\"id\":\"feature/doc.md\"}",
                }
            ),
            "completed",
            "2026-04-22 11:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "--info", "--compact", "--json", "--no-follow"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["next_step"] == "builder logs --session <id> --compact --json"
    event = payload["results"][0]
    assert event["event_type"] == "tool_result"
    assert event["tool_name"] == "mcp__builder__kb_add"
    assert event["outcome"] == "ok"
    assert event["input_focus"] == "doc_type=feature"
    assert event["summary"] == "mcp__builder__kb_add: feature/doc.md"
    assert "error_message" not in event
    assert event["next_action"] == "Expand raw output only if the compact digest is insufficient."


def test_logs_run_status_json_compacts_sdk_telemetry(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-run", "2026-04-22 11:00:00", "2026-04-22 11:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-run",
            "sess-run",
            "run_status",
            json.dumps(
                {
                    "running": False,
                    "current_turn": 2,
                    "max_turns": 15,
                    "tokens_used": 42,
                    "cost_usd": 0.03,
                    "duration_ms": 1234,
                    "stop_reason": "end_turn",
                    "sdk_session_id": "sdk-sess-run",
                }
            ),
            "completed",
            "2026-04-22 11:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        ["logs", "--session", "sess-run", "--type", "run_status", "--compact", "--json", "--no-follow"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    event = payload["results"][0]
    assert event["event_type"] == "run_status"
    assert event["tool_name"] == "Agent"
    assert event["outcome"] == "completed"
    assert event["summary"] == "Agent run completed"
    assert "duration_ms=1234" in event["input_focus"]
    assert "stop_reason=end_turn" in event["input_focus"]
    assert "sdk_session_id=sdk-sess-run" in event["input_focus"]


def test_logs_error_json_auto_compacts_filtered_lane(monkeypatch, tmp_path):
    agent_builder_dir = tmp_path / ".agent-builder"
    agent_builder_dir.mkdir(parents=True)
    db_path = agent_builder_dir / "agent_builder.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        create table chat_sessions (
            id varchar(36) primary key,
            created_at datetime default current_timestamp,
            updated_at datetime default current_timestamp
        );
        create table chat_events (
            id varchar(36) primary key,
            session_id varchar(36) not null,
            event_type varchar(50) not null,
            payload_json json not null,
            status varchar(20) not null,
            tool_use_id varchar(255),
            response_to_event_id varchar(36),
            created_at datetime default current_timestamp
        );
        """
    )
    conn.execute(
        "insert into chat_sessions (id, created_at, updated_at) values (?, ?, ?)",
        ("sess-3", "2026-04-22 12:00:00", "2026-04-22 12:00:00"),
    )
    conn.execute(
        "insert into chat_events (id, session_id, event_type, payload_json, status, created_at) values (?, ?, ?, ?, ?, ?)",
        (
            "evt-3",
            "sess-3",
            "tool_error",
            json.dumps(
                {
                    "tool_name": "mcp__builder__kb_add",
                    "content": "Missing required sections for feature: Current behavior",
                }
            ),
            "completed",
            "2026-04-22 12:00:01",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["logs", "--error", "--json", "--no-follow"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["count"] == 1
    event = payload["results"][0]
    assert event["event_type"] == "tool_error"
    assert event["tool_name"] == "mcp__builder__kb_add"
    assert event["outcome"] == "error"
    assert event["error_message"] == "Missing required sections for feature: Current behavior"


def test_kb_summary_json_stays_triage_sized(monkeypatch, tmp_path):
    kb_root = _configure_local_kb(monkeypatch, tmp_path)
    _write_local_kb_doc(
        kb_root,
        "system-docs/builder-cli-surface.md",
        (
            "---\n"
            "title: Builder CLI Surface\n"
            "tags: [feature, cli, builder, commands, operator]\n"
            "version: 7\n"
            "card_summary: The builder CLI is the repo-local operator and agent interface.\n"
            "detail_summary: Start with doctor and map, then use page-aligned commands for targeted retrieval.\n"
            "---\n\n"
            "# Builder CLI Surface\n\n"
            "## Change guidance\n\n"
            "Keep JSON compact by default and expand only behind explicit full reads.\n"
        ),
    )

    result = runner.invoke(app, ["knowledge", "summary", "builder", "cli", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == "system-docs/builder-cli-surface.md"
    assert payload["preview"] == "The builder CLI is the repo-local operator and agent interface."
    assert payload["detail"] == "Start with doctor and map, then use page-aligned commands for targeted retrieval."
    assert payload["change_guidance"] == "Keep JSON compact by default and expand only behind explicit full reads."
    assert payload["next_step"] == "builder knowledge show system-docs/builder-cli-surface.md --section 'Change guidance' --json"


def test_root_help_exposes_page_aligned_surfaces():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "agent" in result.output
    assert "board" in result.output
    assert "backlog" in result.output
    assert "knowledge" in result.output
    assert "memory" in result.output
    assert "metrics" in result.output
    assert "│ project" not in result.output
    assert "│ feature" not in result.output
    assert "│ approval" not in result.output
    assert "run           " not in result.output
    assert "kb            " not in result.output


def test_legacy_top_level_commands_are_removed():
    for command in ("project", "feature", "task", "approval", "run", "kb"):
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 2
        assert f"No such command '{command}'." in result.output


def test_backlog_and_knowledge_surfaces_are_registered():
    backlog_result = runner.invoke(app, ["backlog", "--help"])
    knowledge_result = runner.invoke(app, ["knowledge", "--help"])
    agent_result = runner.invoke(app, ["agent", "--help"])
    board_result = runner.invoke(app, ["board", "--help"])
    metrics_result = runner.invoke(app, ["metrics", "--help"])
    map_result = runner.invoke(app, ["map", "--help"])
    context_result = runner.invoke(app, ["context", "--help"])
    feature_result = runner.invoke(app, ["backlog", "feature", "--help"])

    assert backlog_result.exit_code == 0
    assert "Backlog planning and execution surfaces." in backlog_result.output
    assert "project" in backlog_result.output
    assert "feature" in backlog_result.output
    assert "task" in backlog_result.output
    assert "approval" in backlog_result.output
    assert "run" in backlog_result.output

    assert knowledge_result.exit_code == 0
    assert "search" in knowledge_result.output
    assert "extract" in knowledge_result.output

    assert agent_result.exit_code == 0
    assert "Agent chat sessions and runtime metadata." in agent_result.output
    assert "sessions" in agent_result.output
    assert "history" in agent_result.output
    assert "meta" in agent_result.output

    assert board_result.exit_code == 0
    assert "active-work routing" in board_result.output
    assert "show" in board_result.output

    assert metrics_result.exit_code == 0
    assert "Cost and verification metrics." in metrics_result.output
    assert "show" in metrics_result.output

    assert map_result.exit_code == 0
    assert "startup orientation" in map_result.output

    assert context_result.exit_code == 0
    assert "named profiles" in context_result.output

    assert feature_result.exit_code == 0
    assert "Feature backlog and delivery slices." in feature_result.output


def test_project_summary_resolves_natural_query(monkeypatch):
    client = _PathClient(
        {
            "/projects/": [
                {
                    "id": "proj-1",
                    "name": "Builder",
                    "description": "Autonomous agent builder project",
                    "repo_url": "https://example.com/repo",
                    "language": "python",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ],
            "/projects/proj-1": {
                "id": "proj-1",
                "name": "Builder",
                "description": "Autonomous agent builder project",
                "repo_url": "https://example.com/repo",
                "language": "python",
                "created_at": "2026-01-01T00:00:00Z",
            },
        }
    )
    monkeypatch.setattr(project_module, "get_client", lambda **_: client)

    result = runner.invoke(app, ["backlog", "project", "summary", "builder", "project", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["matched_on"] in {"search", "name", "prefix"}
    assert payload["id"] == "proj-1"
    assert payload["next_step"] == "builder backlog project show proj-1 --json"


def test_task_search_json_is_compact(monkeypatch):
    client = _PathClient(
        {
            "/tasks": [
                {
                    "id": "task-1",
                    "feature_id": "feat-1",
                    "title": "Implement retrieval hints",
                    "description": "Add fuzzy retrieval support.",
                    "status": "planning",
                    "complexity": 2,
                    "retry_count": 0,
                    "blocked_reason": "",
                    "capability_limit_reason": "",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        }
    )
    monkeypatch.setattr(task_module, "get_client", lambda **_: client)

    result = runner.invoke(app, ["backlog", "task", "search", "retrieval", "hints", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "task-1"
    assert "description" not in payload["results"][0]


def test_task_show_full_includes_gate_results(monkeypatch):
    task = {
        "id": "task-1",
        "title": "Implement verification surface",
        "description": "Expose task-scoped verification evidence.",
        "status": "quality_gates",
    }
    gates = [
        {
            "id": "gate-1",
            "task_id": "task-1",
            "gate_name": "quality-gates",
            "status": "pass",
        }
    ]
    runs = [
        {
            "id": "run-1",
            "task_id": "task-1",
            "agent_name": "designer",
            "status": "success",
        }
    ]
    client = _PathClient(
        {
            "/tasks": [task],
            "/tasks/task-1": dict(task),
            "/tasks/task-1/gates": gates,
            "/tasks/task-1/runs": runs,
        }
    )
    monkeypatch.setattr(task_module, "get_client", lambda **_: client)

    result = runner.invoke(app, ["backlog", "task", "show", "verification", "surface", "--full", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == "task-1"
    assert payload["matched_on"] in {"search", "name", "prefix"}
    assert payload["gate_results"] == gates
    assert payload["agent_runs"] == runs


def test_run_summary_resolves_natural_query(monkeypatch):
    run = {
        "id": "run-1",
        "task_id": "task-1",
        "agent_name": "designer",
        "session_id": "sess-1",
        "cost_usd": 0.42,
        "tokens_input": 100,
        "tokens_output": 50,
        "tokens_cached": 0,
        "num_turns": 3,
        "duration_ms": 1500,
        "stop_reason": "completed",
        "status": "success",
        "error": "",
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:00:01Z",
    }
    client = _PathClient({"/runs": [run], "/runs/run-1": run})
    monkeypatch.setattr(run_module, "get_client", lambda **_: client)

    result = runner.invoke(app, ["backlog", "run", "summary", "designer", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == "run-1"
    assert payload["matched_on"] in {"search", "name", "prefix"}


def test_approval_search_json_is_compact(monkeypatch):
    gate = {
        "id": "approval-1",
        "task_id": "task-1",
        "gate_type": "design",
        "status": "pending",
        "created_at": "2026-01-01T00:00:00Z",
    }
    client = _PathClient({"/approval-gates": [gate]})
    monkeypatch.setattr(approval_module, "get_client", lambda **_: client)

    result = runner.invoke(app, ["backlog", "approval", "search", "design", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "approval-1"
    assert "created_at" not in payload["results"][0]


def test_memory_summary_resolves_natural_query(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    decisions = memory_root / "decisions"
    decisions.mkdir(parents=True)
    body = "## Summary\n\nUse the builder retrieval surface.\n"
    payload = {
        "slug": "decision-builder-cli",
        "title": "Builder CLI retrieval precedent",
        "type": "decision",
        "date": "2026-01-01",
        "phase": "implementation",
        "entity": "builder-cli",
        "tags": ["cli", "retrieval"],
        "status": "active",
    }
    decisions.joinpath("decision-builder-cli.md").write_text(
        memory_module._build_memory_markdown(payload, body),
        encoding="utf-8",
    )
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    result = runner.invoke(app, ["memory", "summary", "builder", "retrieval", "--json"])

    assert result.exit_code == 0
    response = json.loads(result.stdout)
    assert response["id"] == "decision-builder-cli"
    assert response["matched_on"] in {"search", "name", "prefix"}


def test_agent_sessions_json_is_agent_friendly(monkeypatch):
    class _DummyClient:
        def close(self):
            return None

    monkeypatch.setattr(agent_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        agent_module,
        "request_json",
        lambda *args, **kwargs: {
            "sessions": [
                {
                    "id": "sess-1",
                    "sdk_session_id": "sdk-sess-1",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "message_count": 3,
                    "preview": "Latest agent turn",
                }
            ]
        },
    )

    result = runner.invoke(app, ["agent", "sessions", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["count"] == 1
    assert payload["results"][0]["id"] == "sess-1"
    assert payload["results"][0]["sdk_session_id"] == "sdk-sess-1"
    assert payload["next_step"] == "builder agent history --session <id> --json"


def test_agent_history_json_exposes_sdk_result_telemetry(monkeypatch):
    class _DummyClient:
        def close(self):
            return None

    monkeypatch.setattr(agent_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        agent_module,
        "request_json",
        lambda *args, **kwargs: {
            "session_id": "sess-1",
            "sdk_session_id": "sdk-sess-1",
            "model": "haiku",
            "repo_identity": "/repo",
            "workspace_cwd": "/repo",
            "messages": [{"role": "assistant", "content": "done"}],
            "status": {
                "running": False,
                "current_turn": 2,
                "max_turns": 15,
                "tokens_used": 42,
                "cost_usd": 0.03,
                "duration_ms": 1234,
                "stop_reason": "end_turn",
                "sdk_session_id": "sdk-sess-1",
            },
        },
    )

    result = runner.invoke(app, ["agent", "history", "--session", "sess-1", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["session_id"] == "sess-1"
    assert payload["sdk_session_id"] == "sdk-sess-1"
    assert payload["status"]["duration_ms"] == 1234
    assert payload["status"]["stop_reason"] == "end_turn"
    assert payload["status"]["sdk_session_id"] == "sdk-sess-1"


def test_agent_sessions_falls_back_to_local_data_on_connectivity_error(monkeypatch):
    class _DummyClient:
        base_url = "http://127.0.0.1:9876"

        def close(self):
            return None

    monkeypatch.setattr(agent_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        agent_module,
        "request_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(BuilderConnectivityError("http://127.0.0.1:9876")),
    )
    monkeypatch.setattr(
        agent_module,
        "load_local_agent_sessions",
        lambda limit: {
            "status": "ok",
            "count": 1,
            "results": [{"id": "sess-local", "updated_at": "2026-01-01T00:00:00Z", "message_count": 2, "preview": "Local session"}],
            "schema_version": "1",
            "degraded": True,
            "source": "local_db_fallback",
            "next_step": "builder agent history --session <id> --json",
        },
    )

    result = runner.invoke(app, ["agent", "sessions", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["degraded"] is True
    assert payload["source"] == "local_db_fallback"
    assert payload["results"][0]["id"] == "sess-local"


def test_board_show_json_includes_counts_and_next_step(monkeypatch):
    class _DummyClient:
        def close(self):
            return None

    monkeypatch.setattr(board_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        board_module,
        "request_json",
        lambda *args, **kwargs: {
            "pending": [{"id": "task-1", "title": "Plan task", "status": "pending"}],
            "active": [{"id": "task-2", "title": "Build task", "status": "active"}],
            "review": [],
            "done": [],
            "blocked": [],
        },
    )

    result = runner.invoke(app, ["board", "show", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["counts"]["pending"] == 1
    assert payload["counts"]["active"] == 1
    assert payload["next_step"] == "builder backlog task status <task-id> --json"


def test_board_show_falls_back_to_local_data_on_connectivity_error(monkeypatch):
    class _DummyClient:
        base_url = "http://127.0.0.1:9876"

        def close(self):
            return None

    monkeypatch.setattr(board_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        board_module,
        "request_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(BuilderConnectivityError("http://127.0.0.1:9876")),
    )
    monkeypatch.setattr(
        board_module,
        "load_local_board",
        lambda limit: {
            "pending": [{"id": "task-local", "title": "Plan task", "status": "pending"}],
            "active": [],
            "review": [],
            "done": [],
            "blocked": [],
            "counts": {"pending": 1, "active": 0, "review": 0, "done": 0, "blocked": 0},
            "degraded": True,
            "source": "local_db_fallback",
            "next_step": "builder backlog task status <task-id> --json",
        },
    )

    result = runner.invoke(app, ["board", "show", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["degraded"] is True
    assert payload["source"] == "local_db_fallback"
    assert payload["counts"]["pending"] == 1


def test_task_show_points_failed_tasks_to_recover(monkeypatch):
    monkeypatch.setattr(
        task_module,
        "get_client",
        lambda **_: _PathClient(
            {
                "/tasks": [
                    {
                        "id": "task-123",
                        "title": "Recover planner failure",
                        "description": "Planner crashed",
                        "status": "failed",
                        "complexity": 2,
                        "retry_count": 0,
                        "blocked_reason": "planner failed",
                    }
                ],
                "/tasks/task-123": {
                    "id": "task-123",
                    "title": "Recover planner failure",
                    "description": "Planner crashed",
                    "status": "failed",
                    "complexity": 2,
                    "retry_count": 0,
                    "blocked_reason": "planner failed",
                },
            }
        ),
    )

    result = runner.invoke(app, ["backlog", "task", "show", "task-123", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["next_step"] == "builder backlog task recover task-123 --yes --json"


def test_task_recover_posts_recovery_request(monkeypatch):
    recorded: list[tuple[str, object]] = []

    class _RecoverClient:
        def post(self, path: str, data=None):
            recorded.append((path, data))
            return {
                "status": "ok",
                "task_id": "task-123",
                "previous_status": "failed",
                "current_status": "pending",
                "next_step": "builder backlog task dispatch task-123 --yes --json",
            }

        def close(self):
            return None

    monkeypatch.setattr(task_module, "get_client", lambda **_: _RecoverClient())

    result = runner.invoke(app, ["backlog", "task", "recover", "task-123", "--yes", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert recorded == [("/tasks/task-123/recover", None)]
    assert payload["current_status"] == "pending"
    assert payload["next_step"] == "builder backlog task dispatch task-123 --yes --json"


def test_metrics_show_json_includes_summary_and_next_step(monkeypatch):
    class _DummyClient:
        def close(self):
            return None

    monkeypatch.setattr(metrics_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        metrics_module,
        "request_json",
        lambda *args, **kwargs: {
            "total_cost": 1.25,
            "total_tokens": 500,
            "total_runs": 4,
            "gate_pass_rate": 0.75,
                "runs": [
                    {
                        "agent_name": "planner",
                        "cost_usd": 0.25,
                        "tokens_input": 100,
                        "tokens_output": 50,
                        "duration_ms": 123,
                        "status": "completed",
                    }
                ],
            },
    )

    result = runner.invoke(app, ["metrics", "show", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["total_cost"] == 1.25
    assert payload["summary"]["total_runs"] == 4
    assert "runs" not in payload
    assert payload["run_count"] == 1
    assert payload["recent_runs"][0]["agent_name"] == "planner"
    assert payload["next_step"] == "builder backlog run summary <query> --json"

    full_result = runner.invoke(app, ["metrics", "show", "--json", "--full"])
    assert full_result.exit_code == 0
    full_payload = json.loads(full_result.stdout)
    assert "runs" in full_payload
    assert full_payload["runs"][0]["agent_name"] == "planner"


def test_metrics_show_falls_back_to_local_data_on_connectivity_error(monkeypatch):
    class _DummyClient:
        base_url = "http://127.0.0.1:9876"

        def close(self):
            return None

    monkeypatch.setattr(metrics_module, "get_client", lambda **_: _DummyClient())
    monkeypatch.setattr(
        metrics_module,
        "request_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(BuilderConnectivityError("http://127.0.0.1:9876")),
    )
    monkeypatch.setattr(
        metrics_module,
        "load_local_metrics",
        lambda: {
            "total_cost": 0.5,
            "total_tokens": 200,
            "total_runs": 2,
            "gate_pass_rate": 50.0,
            "runs": [],
            "summary": {"total_cost": 0.5, "total_tokens": 200, "total_runs": 2, "gate_pass_rate": 50.0},
            "degraded": True,
            "source": "local_db_fallback",
            "next_step": "builder backlog run summary <query> --json",
        },
    )

    result = runner.invoke(app, ["metrics", "show", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["degraded"] is True
    assert payload["source"] == "local_db_fallback"
    assert payload["summary"]["total_runs"] == 2


def test_map_json_includes_next_step(monkeypatch, tmp_path):
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(map_module, "_server_snapshot", lambda: {"reachable": False, "base_url": "http://127.0.0.1:9876"})

    result = runner.invoke(app, ["map", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["next_step"] == "builder --json doctor"


def test_context_json_includes_next_step():
    result = runner.invoke(app, ["context", "verification", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["next_step"] == "builder quality-gate quality-gates"


def test_context_unknown_profile_json_returns_deterministic_guidance():
    result = runner.invoke(app, ["context", "unknown", "--json"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_context_profile"
    assert payload["next"] == "builder context --help"
    assert "verification" in payload["error"]["detail"]["valid_profiles"]


def test_invalid_builder_command_json_uses_contract_without_raw_leak():
    result = runner.invoke(app, ["--json", "does-not-exist"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    _assert_agent_json_contract(payload, ok=False)
    assert payload["code"] == "invalid_usage"
    assert payload["error"]["code"] == "invalid_usage"
    assert payload["next"] in {"builder --help", "builder doctor --json"}
    assert "Traceback" not in result.stdout
    assert "<html" not in result.stdout.lower()


def test_core_builder_json_commands_have_agent_contract(monkeypatch, tmp_path):
    kb_root = _configure_local_kb(monkeypatch, tmp_path)
    _write_local_kb_doc(
        kb_root,
        "system-docs/project-overview.md",
        (
            "---\n"
            "title: Project Overview\n"
            "tags: [builder, system-docs, seed]\n"
            "card_summary: Local builder project overview.\n"
            "---\n\n"
            "# Project Overview\n\n"
            "Builder local context.\n"
        ),
    )
    monkeypatch.setattr(map_module, "_server_snapshot", lambda: {"reachable": False, "base_url": "http://127.0.0.1:9876"})

    commands = [
        ["context", "verification", "--json"],
        ["map", "--json"],
        ["knowledge", "list", "--json"],
        ["knowledge", "search", "overview", "--json"],
    ]

    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.stdout
        _assert_agent_json_contract(json.loads(result.stdout), ok=True)


def test_memory_summary_resolves_body_text(tmp_path, monkeypatch):
    memory_root = tmp_path / ".memory"
    decisions = memory_root / "decisions"
    decisions.mkdir(parents=True)
    body = (
        "## Summary\n\n"
        "Use builder and workflow CLIs for memory and knowledge operations.\n"
    )
    payload = {
        "slug": "workflow-and-memory-creation-only-via-clis",
        "title": "Workflow and memory creation ONLY via CLIs",
        "type": "decision",
        "date": "2026-01-01",
        "phase": "implementation",
        "entity": "builder-cli",
        "tags": ["cli", "knowledge"],
        "status": "active",
    }
    decisions.joinpath("workflow-and-memory-creation-only-via-clis.md").write_text(
        memory_module._build_memory_markdown(payload, body),
        encoding="utf-8",
    )
    monkeypatch.setenv("AAB_MEMORY_ROOT", str(memory_root))

    result = runner.invoke(app, ["memory", "summary", "workflow", "knowledge", "operations", "--json"])

    assert result.exit_code == 0
    response = json.loads(result.stdout)
    assert response["id"] == "workflow-and-memory-creation-only-via-clis"
    assert response["matched_on"] in {"search", "prefix", "name"}


def test_extract_pipeline_continues_when_agent_advisory_falls_back(tmp_path, monkeypatch):
    workspace_path = tmp_path
    kb_path = workspace_path / ".agent-builder" / "knowledge" / "system-docs"
    kb_path.mkdir(parents=True)

    class _FakeExtractor:
        def __init__(self, workspace_path: Path, output_path: Path, *, doc_slugs=None):
            self.workspace_path = workspace_path
            self.output_path = output_path
            self.doc_slugs = doc_slugs

        def extract(self, scope: str = "full"):
            return {
                "documents": [
                    {
                        "type": "system-docs",
                        "title": "Project Overview",
                        "filename": "project-overview.md",
                    }
                ],
                "errors": [],
            }

    class _FakeDeterministicGate:
        def __init__(self, kb_path: Path, workspace_path: Path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self):
            return QualityGateResult(
                passed=True,
                score=1.0,
                checks=[QualityCheck("specificity", True, 1.0, "passed")],
                summary="Quality Gate: PASSED (9/9 checks passed, score: 100.0%)",
            )

    class _FakeAgentGate:
        def __init__(self, kb_path: Path, workspace_path: Path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self):
            return AgentQualityGateResult(
                passed=True,
                score=1.0,
                summary="fallback",
                evaluation={
                    "fallback": "rule-based",
                    "fallback_reason": "Not logged in · Please run /login",
                },
                recommendations=["Run `/login` in Claude Code to restore agent-based evaluation."],
                agent_reasoning="deterministic fallback",
            )

    import autonomous_agent_builder.knowledge as knowledge_module
    import autonomous_agent_builder.knowledge.agent_quality_gate as agent_quality_gate_module
    import autonomous_agent_builder.knowledge.document_spec as document_spec_module
    import autonomous_agent_builder.knowledge.quality_gate as quality_gate_module

    monkeypatch.setattr(knowledge_module, "KnowledgeExtractor", _FakeExtractor)
    monkeypatch.setattr(document_spec_module, "lint_directory", lambda *_, **__: (12, 0, 12))
    monkeypatch.setattr(quality_gate_module, "KnowledgeQualityGate", _FakeDeterministicGate)
    monkeypatch.setattr(agent_quality_gate_module, "AgentKnowledgeQualityGate", _FakeAgentGate)

    payload = kb_module._run_extract_pipeline(
        workspace_path=workspace_path,
        kb_path=kb_path,
        scope="full",
        run_validation=True,
    )

    assert payload["passed"] is True
    assert payload["validation"]["deterministic"]["passed"] is True
    assert payload["validation"]["agent_advisory"]["available"] is False
    assert payload["validation"]["agent_advisory"]["summary"] == ""
    assert payload["next_step"]["action"] == "continue"
    assert payload["next_step"]["target_phase"] == "kb_ready"


def test_extract_pipeline_continues_when_agent_advisory_is_unavailable(tmp_path, monkeypatch):
    workspace_path = tmp_path
    kb_path = workspace_path / ".agent-builder" / "knowledge" / "system-docs"
    kb_path.mkdir(parents=True)

    class _FakeExtractor:
        def __init__(self, workspace_path: Path, output_path: Path, *, doc_slugs=None):
            self.workspace_path = workspace_path
            self.output_path = output_path
            self.doc_slugs = doc_slugs

        def extract(self, scope: str = "full"):
            return {
                "documents": [
                    {
                        "type": "system-docs",
                        "title": "System Architecture",
                        "filename": "system-architecture.md",
                    }
                ],
                "errors": [],
            }

    class _FakeDeterministicGate:
        def __init__(self, kb_path: Path, workspace_path: Path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self):
            return QualityGateResult(
                passed=True,
                score=1.0,
                checks=[QualityCheck("specificity", True, 1.0, "passed")],
                summary="Quality Gate: PASSED (10/10 checks passed, score: 100.0%)",
            )

    class _FakeAgentGate:
        def __init__(self, kb_path: Path, workspace_path: Path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self):
            return AgentQualityGateResult(
                passed=True,
                score=1.0,
                summary="fallback",
                evaluation={
                    "fallback": "rule-based",
                    "fallback_reason": "Not logged in · Please run /login",
                },
                recommendations=["Run `/login` in Claude Code to restore agent-based evaluation."],
                agent_reasoning="deterministic fallback",
            )

    import autonomous_agent_builder.knowledge as knowledge_module
    import autonomous_agent_builder.knowledge.agent_quality_gate as agent_quality_gate_module
    import autonomous_agent_builder.knowledge.document_spec as document_spec_module
    import autonomous_agent_builder.knowledge.quality_gate as quality_gate_module

    monkeypatch.setattr(knowledge_module, "KnowledgeExtractor", _FakeExtractor)
    monkeypatch.setattr(document_spec_module, "lint_directory", lambda *_, **__: (12, 0, 12))
    monkeypatch.setattr(quality_gate_module, "KnowledgeQualityGate", _FakeDeterministicGate)
    monkeypatch.setattr(agent_quality_gate_module, "AgentKnowledgeQualityGate", _FakeAgentGate)

    payload = kb_module._run_extract_pipeline(
        workspace_path=workspace_path,
        kb_path=kb_path,
        scope="full",
        run_validation=True,
    )

    assert payload["passed"] is True
    assert payload["validation"]["deterministic"]["passed"] is True
    assert payload["validation"]["agent_advisory"]["available"] is False
    assert payload["validation"]["agent_advisory"]["summary"] == ""
    assert payload["next_step"]["action"] == "continue"
    assert payload["next_step"]["reason"] == "deterministic_validation_passed"
    assert payload["next_step"]["target_phase"] == "kb_ready"


def test_extract_command_passes_doc_slug_to_pipeline(monkeypatch):
    captured: dict[str, object] = {}

    def fake_pipeline(**kwargs):
        captured.update(kwargs)
        return {
            "documents": [
                {
                    "type": "system-docs",
                    "title": "System Architecture",
                    "filename": "system-architecture.md",
                }
            ],
            "errors": [],
            "passed": True,
            "validation": {},
            "next_step": {"action": "continue"},
        }

    monkeypatch.setattr(kb_module, "_run_extract_pipeline", fake_pipeline)

    with runner.isolated_filesystem():
        Path(".agent-builder").mkdir()
        result = runner.invoke(app, ["knowledge", "extract", "--doc", "system-architecture", "--json"])

    assert result.exit_code == 0
    assert captured["doc_slug"] == "system-architecture"


def test_extract_pipeline_ignores_non_blocking_generator_errors(tmp_path, monkeypatch):
    workspace_path = tmp_path
    kb_path = workspace_path / ".agent-builder" / "knowledge" / "system-docs"
    kb_path.mkdir(parents=True)

    class _FakeExtractor:
        def __init__(self, workspace_path: Path, output_path: Path, *, doc_slugs=None):
            self.workspace_path = workspace_path
            self.output_path = output_path
            self.doc_slugs = doc_slugs

        def extract(self, scope: str = "full"):
            return {
                "documents": [
                    {
                        "type": "system-docs",
                        "title": "System Architecture",
                        "filename": "system-architecture.md",
                    }
                ],
                "errors": [
                    {
                        "generator": "ProjectOverviewGenerator",
                        "slug": "project-overview",
                        "error": "non-authoritative doc failed",
                    }
                ],
            }

    class _FakeDeterministicGate:
        def __init__(self, kb_path: Path, workspace_path: Path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self):
            return QualityGateResult(
                passed=True,
                score=1.0,
                checks=[QualityCheck("claim_validation", True, 1.0, "passed")],
                summary="Deterministic KB validation passed.",
                blocking_docs=["system-architecture"],
            )

    import autonomous_agent_builder.knowledge as knowledge_module
    import autonomous_agent_builder.knowledge.document_spec as document_spec_module
    import autonomous_agent_builder.knowledge.quality_gate as quality_gate_module

    monkeypatch.setattr(knowledge_module, "KnowledgeExtractor", _FakeExtractor)
    monkeypatch.setattr(document_spec_module, "lint_directory", lambda *_, **__: (1, 0, 1))
    monkeypatch.setattr(quality_gate_module, "KnowledgeQualityGate", _FakeDeterministicGate)

    payload = kb_module._run_extract_pipeline(
        workspace_path=workspace_path,
        kb_path=kb_path,
        scope="full",
        run_validation=True,
    )

    assert payload["passed"] is True
    assert payload["errors"][0]["slug"] == "project-overview"
    assert payload["next_step"]["reason"] == "deterministic_validation_passed_with_non_blocking_errors"


def test_validate_defaults_to_deterministic_only(tmp_path, monkeypatch):
    project_root = tmp_path
    kb_path = project_root / ".agent-builder" / "knowledge" / "system-docs"
    kb_path.mkdir(parents=True)
    monkeypatch.chdir(project_root)

    class _FakeDeterministicGate:
        def __init__(self, kb_path: Path, workspace_path: Path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self):
            return QualityGateResult(
                passed=True,
                score=1.0,
                checks=[QualityCheck("claim_validation", True, 1.0, "passed")],
                summary="Deterministic KB validation passed.",
                blocking_docs=["system-architecture"],
                non_blocking_docs=["project-overview"],
            )

    class _UnexpectedAgentGate:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("agent gate should not run by default")

    monkeypatch.setattr(
        "autonomous_agent_builder.knowledge.quality_gate.KnowledgeQualityGate",
        _FakeDeterministicGate,
    )
    monkeypatch.setattr(
        "autonomous_agent_builder.knowledge.agent_quality_gate.AgentKnowledgeQualityGate",
        _UnexpectedAgentGate,
    )

    result = runner.invoke(app, ["knowledge", "validate", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["blocking_docs"] == ["system-architecture"]
    assert payload["agent_advisory"]["available"] is False


def test_validate_use_agent_keeps_deterministic_result_authoritative(tmp_path, monkeypatch):
    project_root = tmp_path
    kb_path = project_root / ".agent-builder" / "knowledge" / "system-docs"
    kb_path.mkdir(parents=True)
    monkeypatch.chdir(project_root)

    class _FakeDeterministicGate:
        def __init__(self, kb_path: Path, workspace_path: Path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self):
            return QualityGateResult(
                passed=False,
                score=0.4,
                checks=[QualityCheck("claim_validation", False, 0.4, "failed")],
                summary="Deterministic KB validation failed.",
                blocking_docs=["system-architecture"],
                claim_failures=[
                    {
                        "doc": "system-architecture",
                        "section": "Manifest",
                        "claim": "Blocking doc leaked template text.",
                        "reason": "template_leakage",
                        "citations": [],
                    }
                ],
            )

    class _FakeAgentGate:
        def __init__(self, kb_path: Path, workspace_path: Path):
            self.kb_path = kb_path
            self.workspace_path = workspace_path

        def validate(self, model=None):
            return AgentQualityGateResult(
                passed=True,
                score=0.9,
                summary="Agent advisory would accept this.",
                evaluation={"criteria_scores": {"usefulness": 90}},
                recommendations=["No changes requested."],
                agent_reasoning="advisory only",
            )

    monkeypatch.setattr(
        "autonomous_agent_builder.knowledge.quality_gate.KnowledgeQualityGate",
        _FakeDeterministicGate,
    )
    monkeypatch.setattr(
        "autonomous_agent_builder.knowledge.agent_quality_gate.AgentKnowledgeQualityGate",
        _FakeAgentGate,
    )

    result = runner.invoke(app, ["knowledge", "validate", "--json", "--use-agent"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert payload["agent_advisory"]["available"] is True
    assert payload["agent_advisory"]["passed"] is True


def test_extract_command_rejects_noncanonical_output_dir():
    with runner.isolated_filesystem():
        Path(".agent-builder").mkdir()
        result = runner.invoke(app, ["knowledge", "extract", "--output-dir", "scratch", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert payload["errors"] == [{"stage": "preflight", "error": "noncanonical_output_dir"}]
    assert payload["next_step"]["reason"] == "noncanonical_output_dir"
