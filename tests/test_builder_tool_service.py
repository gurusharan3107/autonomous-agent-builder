from __future__ import annotations

import json
import importlib
import sys
from types import ModuleType

import pytest

from autonomous_agent_builder.agents.tools import cli_tools
from autonomous_agent_builder.cli.commands import kb as kb_cli
from autonomous_agent_builder.knowledge.document_spec import build_document_markdown, contract_payload
from autonomous_agent_builder.services import builder_tool_service


def _decode_tool_payload(result: dict) -> dict:
    assert result["metadata"]["exit_code"] == 0
    return json.loads(result["content"][0]["text"])


@pytest.mark.asyncio
async def test_builder_tool_service_memory_add_and_search_preserve_json_contract(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))

    created = await builder_tool_service.builder_memory_add(
        "decision",
        "implementation",
        "sdk-mcp",
        "boundary,sdk",
        "Use shared builder services",
        "Record the direct service-backed integration boundary.",
        project_root=str(tmp_path),
    )
    created_payload = _decode_tool_payload(created)
    assert created_payload["slug"] == "use-shared-builder-services"
    assert created_payload["type"] == "decision"

    searched = await builder_tool_service.builder_memory_search(
        "service-backed integration",
        project_root=str(tmp_path),
    )
    search_payload = _decode_tool_payload(searched)
    assert search_payload["status"] == "ok"
    assert search_payload["count"] == 1
    assert search_payload["results"][0]["id"] == "use-shared-builder-services"
    assert search_payload["next_step"] == "builder memory summary <query> --json"


@pytest.mark.asyncio
async def test_builder_tool_service_kb_add_and_show_preserve_json_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))

    created = await builder_tool_service.builder_kb_add(
        "context",
        "SDK Builder Boundary",
        (
            "# SDK Builder Boundary\n\n"
            "## Overview\n\n"
            "Shared builder services now back the SDK-facing MCP tools in this repo. "
            "That means the Claude Agent SDK reaches builder-owned product data through "
            "direct application services instead of spawning the builder CLI as an "
            "internal transport layer.\n\n"
            "## Key points\n\n"
            "- The SDK path no longer shells out to builder.\n"
            "- The builder JSON contract stays stable for agent callers.\n"
            "- Task, board, KB, and memory payloads remain builder-shaped.\n"
            "- The CLI continues to exist as a user-facing and automation-facing adapter.\n\n"
            "## Constraints or caveats\n\n"
            "This service still needs a reachable builder API for task and board reads, "
            "and the KB and memory lanes still depend on the repo-local filesystem owner "
            "surfaces staying intact.\n\n"
            "## Operational next step\n\n"
            "Use the service-backed path for repo-local SDK integrations, and update the "
            "boundary docs whenever the ownership split or service entrypoints change.\n"
        ),
        tags=["sdk", "feature"],
        family="feature",
        linked_feature="onboarding",
        feature_id="feature-onboarding",
        documented_against_commit="abc123",
        documented_against_ref="main",
        owned_paths=["src/autonomous_agent_builder/agents", "src/autonomous_agent_builder/services"],
        project_root=str(tmp_path),
    )
    created_payload = _decode_tool_payload(created)
    assert created_payload["title"] == "SDK Builder Boundary"
    assert created_payload["doc_type"] == "context"
    assert created_payload["doc_family"] == "feature"
    assert created_payload["tags"] == ["context", "feature", "sdk"]
    assert created_payload["documented_against_commit"] == "abc123"
    assert created_payload["documented_against_ref"] == "main"
    assert created_payload["owned_paths"] == [
        "src/autonomous_agent_builder/agents",
        "src/autonomous_agent_builder/services",
    ]

    shown = await builder_tool_service.builder_kb_show(
        created_payload["id"],
        project_root=str(tmp_path),
    )
    show_payload = _decode_tool_payload(shown)
    assert show_payload["id"] == created_payload["id"]
    assert show_payload["matched_on"] == "id"
    assert show_payload["next_step"] == "builder knowledge summary <query> --json"
    assert "SDK Builder Boundary" in show_payload["content"]
    assert show_payload["documented_against_commit"] == "abc123"
    assert show_payload["documented_against_ref"] == "main"
    assert show_payload["owned_paths"] == [
        "src/autonomous_agent_builder/agents",
        "src/autonomous_agent_builder/services",
    ]

    updated = await builder_tool_service.builder_kb_update(
        created_payload["id"],
        tags=["testing", "browser"],
        family="testing",
        verified_with="browser",
        last_verified_at="2026-04-22T18:00:00",
        project_root=str(tmp_path),
    )
    updated_payload = _decode_tool_payload(updated)
    assert updated_payload["doc_family"] == "testing"
    assert updated_payload["tags"] == ["context", "testing", "browser"]

    searched = await builder_tool_service.builder_kb_search(
        "builder boundary",
        tags=["testing"],
        project_root=str(tmp_path),
    )
    search_payload = _decode_tool_payload(searched)
    assert search_payload["count"] == 1
    assert search_payload["results"][0]["id"] == created_payload["id"]


@pytest.mark.asyncio
async def test_builder_tool_service_kb_validate_returns_deterministic_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    kb_root = tmp_path / ".agent-builder" / "knowledge" / "system-docs"
    kb_root.mkdir(parents=True, exist_ok=True)
    (kb_root / "extraction-metadata.md").write_text(
        "---\n"
        "title: Extraction Metadata\n"
        "doc_type: metadata\n"
        "created: 2026-04-22\n"
        "---\n\n"
        "# Extraction Metadata\n\n"
        "## Summary\n\n"
        "Metadata stub.\n\n"
        "## Generated artifacts\n\n"
        "- none\n\n"
        "## Usage\n\n"
        "Used for validation tests.\n",
        encoding="utf-8",
    )

    result = await builder_tool_service.builder_kb_validate(project_root=str(tmp_path))
    payload = json.loads(result["content"][0]["text"])

    assert "passed" in payload
    assert "summary" in payload
    assert "checks" in payload


@pytest.mark.asyncio
async def test_builder_tool_service_kb_validate_rejects_paths_outside_repo_local_kb(tmp_path, monkeypatch):
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))

    result = await builder_tool_service.builder_kb_validate("../outside", project_root=str(tmp_path))
    payload = json.loads(result["content"][0]["text"])

    assert payload["status"] == "error"
    assert payload["error"]["code"] == "error"
    assert payload["error"]["message"] == (
        "KB validation is limited to repo-local directories under .agent-builder/knowledge."
    )
    assert "Retry with `kb_dir: \"system-docs\"`" in payload["error"]["hint"]
    assert payload["error"]["detail"]["safe_lane"] == ".agent-builder/knowledge/<kb_dir>"


@pytest.mark.asyncio
async def test_builder_tool_service_kb_contract_matches_cli_contract_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))

    result = await builder_tool_service.builder_kb_contract(
        doc_type="testing",
        sample_title="Testing Contract Doc",
        project_root=str(tmp_path),
    )
    payload = _decode_tool_payload(result)
    expected = contract_payload(doc_type="testing", sample_title="Testing Contract Doc")

    assert payload["doc_type"] == expected["doc_type"]
    assert payload["required_sections"] == expected["required_sections"]
    assert payload["required_frontmatter"] == expected["required_frontmatter"]
    assert "# Testing Contract Doc" in payload["sample_markdown"]
    assert "## Evidence and follow-up" in payload["sample_markdown"]
    assert "doc_type: testing" in payload["sample_markdown"]
    assert payload["next_step"] == "builder knowledge contract --type testing --json"


@pytest.mark.asyncio
async def test_builder_tool_service_kb_lint_returns_structured_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))

    invalid_content = (
        "---\n"
        "title: Bad Testing Doc\n"
        "tags:\n"
        "- testing\n"
        "doc_type: testing\n"
        "created: 2026-04-23\n"
        "---\n\n"
        "# Bad Testing Doc\n\n"
        "Short intro.\n\n"
        "## Purpose\n\n"
        "Tiny purpose.\n\n"
        "# Another H1\n"
    )

    result = await builder_tool_service.builder_kb_lint(
        doc_type="testing",
        content=invalid_content,
        project_root=str(tmp_path),
    )
    payload = json.loads(result["content"][0]["text"])

    assert payload["status"] == "error"
    assert payload["passed"] is False
    assert any("Missing required field 'auto_generated'" in error for error in payload["errors"])
    assert any(
        "Missing required sections for testing: Coverage, Preconditions, Procedure, Evidence and follow-up"
        in error
        for error in payload["errors"]
    )
    assert any("Multiple H1 headings found" in warning for warning in payload["warnings"])
    assert payload["next_step"] == "Fix the listed contract issues, then retry the KB mutation."


@pytest.mark.asyncio
async def test_builder_tool_service_kb_lint_passes_valid_testing_doc(tmp_path, monkeypatch):
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))

    valid_content = build_document_markdown(
        title="Testing Contract Doc",
        tags=["testing", "example"],
        doc_type="testing",
        created="2026-04-23T00:00:00Z",
        updated="2026-04-23T00:05:00Z",
        extra_fields={
            "doc_family": "testing",
            "linked_feature": "onboarding",
            "feature_id": "feature-onboarding",
            "refresh_required": True,
            "documented_against_commit": "abc123",
            "documented_against_ref": "main",
            "owned_paths": ["tests/test_builder_tool_service.py"],
            "last_verified_at": "2026-04-23T00:00:00Z",
        },
        body=(
            "# Testing Contract Doc\n\n"
            "This document explains the end to end testing coverage for the autonomous "
            "builder onboarding and delivery flows in concrete operator terms.\n\n"
            "## Purpose\n\n"
            "This testing document explains why the suite exists, which product journey it "
            "protects, and which regressions should be treated as release blocking for "
            "maintainers and agents.\n\n"
            "## Coverage\n\n"
            "Coverage includes onboarding, repo mapping, task execution, documentation "
            "refresh, approval handling, and final verification so maintainers know which "
            "major product transitions are exercised before release.\n\n"
            "## Preconditions\n\n"
            "Start from a clean repo-local workspace, a reachable builder runtime, stable "
            "test fixtures, and a task state that makes the expected routes, logs, and KB "
            "surfaces available for inspection.\n\n"
            "## Procedure\n\n"
            "Run the documented onboarding flow, create the required project state, execute "
            "the embedded agent path, verify builder logs, inspect the maintained KB "
            "retrieval path, and confirm the final quality gates report the expected "
            "evidence without manual file edits.\n\n"
            "## Evidence and follow-up\n\n"
            "Capture the exact commands, visible route outcomes, and any remaining gap that "
            "would make the document stale, then record the next owner action required "
            "before treating the workflow as healthy again.\n"
        ),
    )

    result = await builder_tool_service.builder_kb_lint(
        doc_type="testing",
        content=valid_content,
        project_root=str(tmp_path),
    )
    payload = json.loads(result["content"][0]["text"])

    assert payload["status"] == "ok"
    assert payload["passed"] is True
    assert payload["errors"] == []
    assert payload["warnings"] == []
    assert payload["summary"] == "KB contract checks passed."


@pytest.mark.asyncio
async def test_builder_tool_service_kb_extract_uses_canonical_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("AAB_PROJECT_ROOT", str(tmp_path))
    (tmp_path / ".agent-builder").mkdir()
    captured: dict[str, object] = {}

    def fake_run_extract_pipeline(
        *,
        workspace_path,
        kb_path,
        scope,
        run_validation,
        doc_slug=None,
    ):
        captured["workspace_path"] = workspace_path
        captured["kb_path"] = kb_path
        captured["scope"] = scope
        captured["run_validation"] = run_validation
        captured["doc_slug"] = doc_slug
        return {
            "passed": True,
            "documents": [{"filename": "project-overview.md"}],
            "errors": [],
            "operator_message": "ok",
            "next_step": {"action": "done", "reason": "", "recommended_command": ""},
            "validation": {"deterministic": {"passed": True}, "agent_advisory": {}},
            "lint": {"passed": True, "counts": {"passed": 1, "failed": 0, "total": 1}},
            "graph": {},
            "phase": "knowledge_extract",
            "engine": "deterministic",
            "output_path": str(tmp_path / ".agent-builder" / "knowledge" / "system-docs"),
        }

    monkeypatch.setattr(kb_cli, "_run_extract_pipeline", fake_run_extract_pipeline)

    result = await builder_tool_service.builder_kb_extract(
        scope="feature:feat-1",
        doc_slug="system-architecture",
        force=True,
        project_root=str(tmp_path),
    )
    payload = _decode_tool_payload(result)

    assert payload["passed"] is True
    assert captured == {
        "workspace_path": tmp_path,
        "kb_path": tmp_path / ".agent-builder" / "knowledge" / "system-docs",
        "scope": "feature:feat-1",
        "run_validation": True,
        "doc_slug": "system-architecture",
    }


@pytest.mark.asyncio
async def test_builder_tool_service_task_status_uses_direct_api_payload(monkeypatch):
    async def fake_api_request(method: str, path: str, **_: object) -> dict:
        assert method == "GET"
        assert path == "/tasks/task-123"
        return {
            "id": "task-123",
            "status": "implementation",
            "retry_count": 2,
            "blocked_reason": "",
            "capability_limit_reason": "",
        }

    monkeypatch.setattr(builder_tool_service, "_api_request", fake_api_request)

    result = await builder_tool_service.builder_task_status("task-123", project_root="/tmp/demo")
    payload = _decode_tool_payload(result)
    assert payload == {
        "id": "task-123",
        "status": "implementation",
        "retry_count": 2,
        "blocked_reason": "",
        "capability_limit_reason": "",
        "next_step": "builder backlog task show task-123 --json",
    }


@pytest.mark.asyncio
async def test_cli_tools_kb_update_preserves_freshness_metadata(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_kb_update(
        doc_id: str,
        title: str = "",
        content: str = "",
        tags: list[str] | None = None,
        family: str = "",
        linked_feature: str = "",
        feature_id: str = "",
        refresh_required: bool | None = None,
        documented_against_commit: str = "",
        documented_against_ref: str = "",
        owned_paths: list[str] | None = None,
        verified_with: str = "",
        last_verified_at: str = "",
        lifecycle_status: str = "",
        superseded_by: str = "",
        source_url: str = "",
        source_title: str = "",
        source_author: str = "",
        date_published: str = "",
        *,
        project_root: str | None = None,
    ) -> dict:
        captured.update(
            {
                "doc_id": doc_id,
                "documented_against_commit": documented_against_commit,
                "documented_against_ref": documented_against_ref,
                "owned_paths": owned_paths,
                "verified_with": verified_with,
                "last_verified_at": last_verified_at,
                "project_root": project_root,
            }
        )
        return {
            "content": [{"type": "text", "text": json.dumps({"status": "ok"})}],
            "metadata": {"exit_code": 0},
        }

    monkeypatch.setattr(builder_tool_service, "builder_kb_update", fake_kb_update)

    result = await cli_tools.builder_kb_update(
        "system-docs/example.md",
        documented_against_commit="abc123",
        documented_against_ref="main",
        owned_paths=["src/example.py"],
        verified_with="builder logs",
        last_verified_at="2026-04-23",
        project_root="/tmp/project-root",
    )

    assert json.loads(result["content"][0]["text"]) == {"status": "ok"}
    assert captured == {
        "doc_id": "system-docs/example.md",
        "documented_against_commit": "abc123",
        "documented_against_ref": "main",
        "owned_paths": ["src/example.py"],
        "verified_with": "builder logs",
        "last_verified_at": "2026-04-23",
        "project_root": "/tmp/project-root",
    }


@pytest.mark.asyncio
async def test_sdk_mcp_builder_tools_delegate_to_shared_service(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_board(*, project_root: str | None = None) -> dict:
        captured["project_root"] = project_root
        return {
            "content": [{"type": "text", "text": json.dumps({"status": "ok"})}],
            "metadata": {"exit_code": 0},
        }

    def fake_tool(name, description, input_schema, annotations=None):
        def decorator(func):
            func._sdk_tool_name = name
            return func

        return decorator

    def fake_create_sdk_mcp_server(name, version="1.0.0", tools=None):
        return {"name": name, "tools": tools or []}

    fake_sdk = ModuleType("claude_agent_sdk")
    fake_sdk.create_sdk_mcp_server = fake_create_sdk_mcp_server
    fake_sdk.tool = fake_tool
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)
    monkeypatch.setattr(builder_tool_service, "builder_board", fake_board)

    from autonomous_agent_builder.agents.tools import sdk_mcp

    importlib.reload(sdk_mcp)

    servers = sdk_mcp.build_default_mcp_servers(workspace_path=".", project_root="/tmp/project-root")
    builder_tools = {tool._sdk_tool_name: tool for tool in servers["builder"]["tools"]}

    result = await builder_tools["board"]({})

    assert json.loads(result["content"][0]["text"]) == {"status": "ok"}
    assert captured["project_root"] == "/tmp/project-root"


@pytest.mark.asyncio
async def test_sdk_mcp_kb_validate_delegates_to_shared_service(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_kb_validate(kb_dir: str = "system-docs", *, project_root: str | None = None) -> dict:
        captured["kb_dir"] = kb_dir
        captured["project_root"] = project_root
        return {
            "content": [{"type": "text", "text": json.dumps({"passed": True})}],
            "metadata": {"exit_code": 0},
        }

    def fake_tool(name, description, input_schema, annotations=None):
        def decorator(func):
            func._sdk_tool_name = name
            return func

        return decorator

    def fake_create_sdk_mcp_server(name, version="1.0.0", tools=None):
        return {"name": name, "tools": tools or []}

    fake_sdk = ModuleType("claude_agent_sdk")
    fake_sdk.create_sdk_mcp_server = fake_create_sdk_mcp_server
    fake_sdk.tool = fake_tool
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)
    monkeypatch.setattr(builder_tool_service, "builder_kb_validate", fake_kb_validate)

    from autonomous_agent_builder.agents.tools.sdk_mcp import build_default_mcp_servers

    servers = build_default_mcp_servers(workspace_path=".", project_root="/tmp/project-root")
    builder_tools = {tool._sdk_tool_name: tool for tool in servers["builder"]["tools"]}

    result = await builder_tools["kb_validate"]({"kb_dir": "system-docs"})

    assert json.loads(result["content"][0]["text"]) == {"passed": True}
    assert captured == {"kb_dir": "system-docs", "project_root": "/tmp/project-root"}


@pytest.mark.asyncio
async def test_sdk_mcp_kb_extract_delegates_to_shared_service(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_kb_extract(
        kb_dir: str = "system-docs",
        scope: str = "full",
        doc_slug: str = "",
        force: bool = False,
        run_validation: bool = True,
        *,
        project_root: str | None = None,
    ) -> dict:
        captured["kb_dir"] = kb_dir
        captured["scope"] = scope
        captured["doc_slug"] = doc_slug
        captured["force"] = force
        captured["run_validation"] = run_validation
        captured["project_root"] = project_root
        return {
            "content": [{"type": "text", "text": json.dumps({"passed": True})}],
            "metadata": {"exit_code": 0},
        }

    def fake_tool(name, description, input_schema, annotations=None):
        def decorator(func):
            func._sdk_tool_name = name
            return func

        return decorator

    def fake_create_sdk_mcp_server(name, version="1.0.0", tools=None):
        return {"name": name, "tools": tools or []}

    fake_sdk = ModuleType("claude_agent_sdk")
    fake_sdk.create_sdk_mcp_server = fake_create_sdk_mcp_server
    fake_sdk.tool = fake_tool
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)
    monkeypatch.setattr(builder_tool_service, "builder_kb_extract", fake_kb_extract)

    from autonomous_agent_builder.agents.tools.sdk_mcp import build_default_mcp_servers

    servers = build_default_mcp_servers(workspace_path=".", project_root="/tmp/project-root")
    builder_tools = {tool._sdk_tool_name: tool for tool in servers["builder"]["tools"]}

    result = await builder_tools["kb_extract"](
        {
            "kb_dir": "system-docs",
            "scope": "feature:feat-1",
            "doc_slug": "system-architecture",
            "force": True,
            "run_validation": False,
        }
    )

    assert json.loads(result["content"][0]["text"]) == {"passed": True}
    assert captured == {
        "kb_dir": "system-docs",
        "scope": "feature:feat-1",
        "doc_slug": "system-architecture",
        "force": True,
        "run_validation": False,
        "project_root": "/tmp/project-root",
    }


@pytest.mark.asyncio
async def test_sdk_mcp_kb_update_preserves_freshness_metadata(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_kb_update(
        doc_id: str,
        title: str = "",
        content: str = "",
        tags: list[str] | None = None,
        family: str = "",
        linked_feature: str = "",
        feature_id: str = "",
        refresh_required: bool | None = None,
        documented_against_commit: str = "",
        documented_against_ref: str = "",
        owned_paths: list[str] | None = None,
        verified_with: str = "",
        last_verified_at: str = "",
        lifecycle_status: str = "",
        superseded_by: str = "",
        source_url: str = "",
        source_title: str = "",
        source_author: str = "",
        date_published: str = "",
        *,
        project_root: str | None = None,
    ) -> dict:
        captured.update(
            {
                "doc_id": doc_id,
                "documented_against_commit": documented_against_commit,
                "documented_against_ref": documented_against_ref,
                "owned_paths": owned_paths,
                "verified_with": verified_with,
                "last_verified_at": last_verified_at,
                "project_root": project_root,
            }
        )
        return {
            "content": [{"type": "text", "text": json.dumps({"status": "ok"})}],
            "metadata": {"exit_code": 0},
        }

    def fake_tool(name, description, input_schema, annotations=None):
        def decorator(func):
            func._sdk_tool_name = name
            return func

        return decorator

    def fake_create_sdk_mcp_server(name, version="1.0.0", tools=None):
        return {"name": name, "tools": tools or []}

    fake_sdk = ModuleType("claude_agent_sdk")
    fake_sdk.create_sdk_mcp_server = fake_create_sdk_mcp_server
    fake_sdk.tool = fake_tool
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", fake_sdk)
    monkeypatch.setattr(builder_tool_service, "builder_kb_update", fake_kb_update)

    from autonomous_agent_builder.agents.tools.sdk_mcp import build_default_mcp_servers

    servers = build_default_mcp_servers(workspace_path=".", project_root="/tmp/project-root")
    builder_tools = {tool._sdk_tool_name: tool for tool in servers["builder"]["tools"]}

    result = await builder_tools["kb_update"](
        {
            "doc_id": "system-docs/example.md",
            "documented_against_commit": "abc123",
            "documented_against_ref": "main",
            "owned_paths": ["src/example.py"],
            "verified_with": "builder logs",
            "last_verified_at": "2026-04-23",
        }
    )

    assert json.loads(result["content"][0]["text"]) == {"status": "ok"}
    assert captured == {
        "doc_id": "system-docs/example.md",
        "documented_against_commit": "abc123",
        "documented_against_ref": "main",
        "owned_paths": ["src/example.py"],
        "verified_with": "builder logs",
        "last_verified_at": "2026-04-23",
        "project_root": "/tmp/project-root",
    }
