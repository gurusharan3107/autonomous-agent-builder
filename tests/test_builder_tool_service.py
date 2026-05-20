from __future__ import annotations

import importlib
import json
import sys
from types import ModuleType

import pytest

from autonomous_agent_builder.agents.tools import cli_tools
from autonomous_agent_builder.cli.commands import kb as kb_cli
from autonomous_agent_builder.knowledge.document_spec import (
    build_document_markdown,
    contract_payload,
)
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
        (
            "## Decision\n\n"
            "Record the direct service-backed integration boundary.\n\n"
            "## Agent Retrieval Summary\n\n"
            "Use this when checking SDK MCP tool ownership.\n\n"
            "## User-Facing Summary\n\n"
            "SDK MCP tools should use shared builder services.\n\n"
            "## Reusable Guidance\n\n"
            "- Keep SDK tools on builder-owned service contracts.\n\n"
            "## When To Apply\n\n"
            "Apply during SDK MCP integration changes.\n\n"
            "## Retrieval Queries\n\n"
            "- sdk mcp shared builder services\n"
        ),
        project_root=str(tmp_path),
    )
    created_payload = _decode_tool_payload(created)
    assert created_payload["slug"] == "use-shared-builder-services"
    assert created_payload["type"] == "decision"
    assert created_payload["post_mutation"]["reindexed"] is True
    assert created_payload["post_mutation"]["lint_passed"] is True
    assert created_payload["post_mutation"]["retrieval_passed"] is True

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
    assert created_payload["mutation"] == "created"
    assert "content" not in created_payload
    assert "content_preview" in created_payload

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
    assert updated_payload["mutation"] == "updated"
    assert "content" not in updated_payload

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
async def test_builder_tool_service_board_returns_compact_summary(monkeypatch):
    long_description = " ".join(["large detail"] * 200)

    async def fake_api_request(method: str, path: str, **_: object) -> dict:
        assert method == "GET"
        assert path == "/dashboard/board"
        return {
            "pending": [
                {
                    "id": f"task-{index}",
                    "title": f"Task {index}",
                    "status": "pending",
                    "phase": "planning",
                    "feature_id": "feature-1",
                    "feature_title": "Filters",
                    "description": long_description,
                    "sprint_execution": {"implementation_brief": long_description},
                    "verification_evidence": {"full": long_description},
                }
                for index in range(12)
            ],
            "active": [],
            "review": [],
            "done": [],
            "blocked": [],
            "sprints_summary": {
                "latest": [
                    {
                        "label": "Sprint 2",
                        "task_counts": {"done": 3},
                        "verification_status": "shipped",
                    }
                ]
            },
        }

    monkeypatch.setattr(builder_tool_service, "_api_request", fake_api_request)

    result = await builder_tool_service.builder_board(project_root="/tmp/demo")
    payload = _decode_tool_payload(result)

    assert payload["doc_type"] == "board_summary"
    assert "must not be added again" in payload["count_semantics"]
    assert payload["counts"]["pending"] == 12
    assert payload["sprints_summary"]["latest"][0]["task_counts"]["done"] == 3
    assert payload["sections"]["pending"]["count"] == 12
    assert payload["sections"]["pending"]["returned"] == 10
    assert len(payload["sections"]["pending"]["items"]) == 10
    assert payload["sections"]["pending"]["omitted"] == 2
    assert set(payload["sections"]["pending"]["items"][0]) == {
        "id",
        "title",
        "doc_type",
        "status",
        "phase",
        "feature_id",
        "feature_title",
        "preview",
    }
    assert len(json.dumps(payload)) < 5000
    assert "implementation_brief" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_builder_tool_service_metrics_is_compact_by_default(monkeypatch):
    async def fake_api_request(method: str, path: str, **_: object) -> dict:
        assert method == "GET"
        assert path == "/dashboard/metrics"
        return {
            "total_runs": 2,
            "total_tokens": 3000,
            "optimization_summary": {
                "raw_token_total": 3000,
                "cache_ratio": 2.5,
                "avoidable_token_estimate": 400,
                "avoidable_cost_flags": [{"flag": "redundant_scan", "count": 1}],
                "top_cost_drivers": [
                    {"agent_name": "code-gen", "raw_tokens": 2000},
                    {"agent_name": "pr-creator", "raw_tokens": 1000},
                ],
                "recommended_next_change": "tighten_task_briefs",
            },
            "runs": [
                {
                    "id": "run-1",
                    "task_id": "task-1",
                    "agent_name": "code-gen",
                    "status": "completed",
                    "runtime_sdk": "claude",
                    "model": "sonnet",
                    "effort": "medium",
                    "tokens_input": 1200,
                    "tokens_output": 300,
                    "tokens_cached": 900,
                    "duration_ms": 1000,
                    "stop_reason": "end_turn",
                    "observability": {"large": "raw payload should be omitted"},
                }
            ],
            "voice_ledger": {
                "tool_outputs": [
                    {
                        "event_id": "evt-1",
                        "tool_name": "delegate_to_builder_agent",
                        "tool_call_id": "call-1",
                        "ok": False,
                        "error": "message is required",
                        "raw": "large raw output should be omitted",
                    }
                ],
                "usage": [{"voice_call_id": "rtc-1", "total_tokens": 100}],
                "totals": {
                    "responses": 1,
                    "total_tokens": 100,
                    "failed_tool_outputs": 1,
                    "delegation_ratio": 1.0,
                },
            },
        }

    monkeypatch.setattr(builder_tool_service, "_api_request", fake_api_request)

    result = await builder_tool_service.builder_metrics(project_root="/tmp/demo")
    payload = _decode_tool_payload(result)

    assert "runs" not in payload
    assert payload["run_count"] == 1
    assert payload["recent_runs"][0]["agent_name"] == "code-gen"
    assert "observability" not in payload["recent_runs"][0]
    assert payload["optimization_preflight"]["avoidable_token_estimate"] == 400
    assert payload["optimization_preflight"]["top_cost_drivers"][0]["agent_name"] == "code-gen"
    assert payload["voice_ledger"]["totals"]["failed_tool_outputs"] == 1
    assert payload["voice_ledger"]["recent_failures"] == [
        {
            "tool_name": "delegate_to_builder_agent",
            "tool_call_id": "call-1",
            "error": "message is required",
            "event_id": "evt-1",
        }
    ]
    assert "tool_outputs" not in payload["voice_ledger"]
    assert "usage" not in payload["voice_ledger"]
    assert payload["raw_evidence"]["full_payload_command"] == "builder metrics show --json --full"


@pytest.mark.asyncio
async def test_builder_tool_service_task_show_is_compact_by_default(monkeypatch):
    async def fake_api_request(method: str, path: str, **_: object):
        assert method == "GET"
        if path == "/tasks/task-123":
            return {
                "id": "task-123",
                "feature_id": "feature-05",
                "title": "Verify Deterministic tests and build script for shipping",
                "description": "Run final checks and browser-visible proof that the feature is shippable.",
                "status": "capability_limit",
                "phase": "implementation",
                "complexity": 1,
                "retry_count": 1,
                "blocked_reason": "provider limit blocked",
                "capability_limit_reason": "SDK limit: provider_limit",
                "depends_on": {
                    "sprint_execution": {
                        "sprint_id": "sprint-1",
                        "feature_id": "feature-05",
                        "task_key": "browser-verification",
                        "batch_id": "batch-015",
                        "recommended_model": "sonnet",
                        "large_unused_field": "x" * 5000,
                    },
                    "materialized_checkout_verification": {
                        "status": "failed",
                        "command": "builder script run build_verify --json",
                        "output": "npm install PASS\nnpm run lint PASS\nnpm run build FAIL\nnpm test PASS",
                        "raw": "x" * 5000,
                    },
                    "feature_acceptance_run_ids": [f"run-{index}" for index in range(8)],
                },
            }
        if path == "/tasks/task-123/gates":
            return [
                {
                    "id": "gate-1",
                    "gate_name": "build_verify",
                    "status": "failed",
                    "output": "npm run build FAIL\n" + ("raw output " * 200),
                    "raw": "large raw gate payload",
                }
            ]
        if path == "/tasks/task-123/runs":
            return [
                {
                    "id": "run-1",
                    "agent_name": "build-verifier",
                    "status": "failed",
                    "runtime_sdk": "claude",
                    "model": "sonnet",
                    "tokens_input": 1000,
                    "tokens_output": 250,
                    "observability": {"raw": "large payload"},
                    "output_text": "Verifier failed because npm run build failed. " * 40,
                }
            ]
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(builder_tool_service, "_api_request", fake_api_request)

    result = await builder_tool_service.builder_task_show(
        "task-123",
        project_root="/tmp/demo",
    )
    payload = _decode_tool_payload(result)
    payload_text = json.dumps(payload)

    assert payload["doc_type"] == "task_detail"
    assert payload["depends_on"]["materialized_checkout_verification"]["command"] == (
        "builder script run build_verify --json"
    )
    assert "npm run build FAIL" in payload["depends_on"]["materialized_checkout_verification"]["output"]
    assert payload["depends_on"]["feature_acceptance_run_ids"] == {
        "count": 8,
        "sample": ["run-0", "run-1", "run-2", "run-3", "run-4"],
    }
    assert payload["gate_results"]["items"][0]["output_preview"].startswith("npm run build FAIL")
    assert payload["agent_runs"]["recent"][0]["tokens"] == 1250
    assert "observability" not in payload_text
    assert "large_unused_field" not in payload_text
    assert "large raw gate payload" not in payload_text
    assert payload["raw_evidence"]["full_payload_command"] == (
        "builder backlog task show task-123 --full --json"
    )


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
async def test_builder_tool_service_task_recover_uses_recovery_api(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_api_request(method: str, path: str, **kwargs: object) -> dict:
        captured["method"] = method
        captured["path"] = path
        captured["project_root"] = kwargs.get("project_root")
        return {
            "status": "ok",
            "task_id": "task-123",
            "previous_status": "failed",
            "current_status": "build_verify",
        }

    monkeypatch.setattr(builder_tool_service, "_api_request", fake_api_request)

    result = await builder_tool_service.builder_task_recover("task-123", project_root="/tmp/demo")
    payload = _decode_tool_payload(result)

    assert captured == {
        "method": "POST",
        "path": "/tasks/task-123/recover",
        "project_root": "/tmp/demo",
    }
    assert payload == {
        "status": "ok",
        "task_id": "task-123",
        "previous_status": "failed",
        "current_status": "build_verify",
    }


@pytest.mark.asyncio
async def test_builder_tool_service_backlog_item_list_defaults_to_repo_project(monkeypatch):
    async def fake_api_request(method: str, path: str, **kwargs: object) -> object:
        assert method == "GET"
        if path == "/projects/":
            return [{"id": "proj-123", "name": "autonomous-agent-builder"}]
        assert path == "/projects/proj-123/backlog/items"
        assert kwargs["params"] == {"type": "optimization"}
        return [
            {
                "id": "item-1",
                "project_id": "proj-123",
                "type": "optimization",
                "title": "Reduce prompt bloat",
                "status": "pending",
                "priority": 3,
                "severity": None,
                "source": "validation",
                "tags": ["agent-experience"],
                "created_at": "2026-04-25T00:00:00Z",
            }
        ]

    monkeypatch.setattr(builder_tool_service, "_api_request", fake_api_request)

    result = await builder_tool_service.builder_backlog_item_list(
        item_type="optimization",
        project_root="/tmp/demo",
    )
    payload = _decode_tool_payload(result)

    assert payload["project_id"] == "proj-123"
    assert payload["count"] == 1
    assert payload["counts_by_type"] == {"optimization": 1}
    assert payload["results"][0]["type"] == "optimization"


@pytest.mark.asyncio
async def test_builder_tool_service_backlog_item_show_returns_compact_payload(monkeypatch):
    async def fake_api_request(method: str, path: str, **_: object) -> dict[str, object]:
        assert method == "GET"
        assert path == "/backlog/items/item-1"
        return {
            "id": "item-1",
            "project_id": "proj-123",
            "type": "incident",
            "title": "Agent used board instead of backlog",
            "description": "Long description " * 200,
            "status": "pending",
            "evidence": "Verbose evidence " * 200,
            "acceptance_criteria": [f"criterion-{index}" for index in range(12)],
            "dependencies": [f"dep-{index}" for index in range(10)],
            "large_unused_field": "large raw backlog payload " * 100,
        }

    monkeypatch.setattr(builder_tool_service, "_api_request", fake_api_request)

    result = await builder_tool_service.builder_backlog_item_show("item-1", project_root="/tmp/demo")
    payload = _decode_tool_payload(result)

    assert payload["id"] == "item-1"
    assert payload["doc_type"] == "backlog_item_detail"
    assert payload["matched_on"] == "id"
    assert payload["next_step"] == "builder backlog item show item-1 --json"
    assert payload["acceptance_criteria"]["count"] == 12
    assert payload["acceptance_criteria"]["omitted"] == 4
    assert payload["dependencies"]["count"] == 10
    assert payload["dependencies"]["omitted"] == 2
    assert "large_unused_field" not in json.dumps(payload)


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

    assert "recommendation_create" in builder_tools
    result = await builder_tools["board"]({})

    assert json.loads(result["content"][0]["text"]) == {"status": "ok"}
    assert captured["project_root"] == "/tmp/project-root"


@pytest.mark.asyncio
async def test_sdk_mcp_task_recover_delegates_to_shared_service(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_task_recover(task_id: str, *, project_root: str | None = None) -> dict:
        captured["task_id"] = task_id
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
    monkeypatch.setattr(builder_tool_service, "builder_task_recover", fake_task_recover)

    from autonomous_agent_builder.agents.tools import sdk_mcp

    importlib.reload(sdk_mcp)

    servers = sdk_mcp.build_default_mcp_servers(
        workspace_path=".",
        project_root="/tmp/project-root",
        allowed_tool_names={"mcp__builder__task_recover"},
    )
    builder_tools = {tool._sdk_tool_name: tool for tool in servers["builder"]["tools"]}

    result = await builder_tools["task_recover"]({"task_id": "task-123"})

    assert json.loads(result["content"][0]["text"]) == {"status": "ok"}
    assert captured == {"task_id": "task-123", "project_root": "/tmp/project-root"}


async def test_sdk_mcp_workspace_scaffold_delegates_to_shared_service(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_workspace_scaffold(
        task_id: str, *, project_root: str | None = None
    ) -> dict:
        captured["task_id"] = task_id
        captured["project_root"] = project_root
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {"status": "ok", "action": "scaffold_ready", "language": "python"}
                    ),
                }
            ],
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
    monkeypatch.setattr(
        builder_tool_service, "builder_workspace_scaffold", fake_workspace_scaffold
    )

    from autonomous_agent_builder.agents.tools import sdk_mcp

    importlib.reload(sdk_mcp)

    servers = sdk_mcp.build_default_mcp_servers(
        workspace_path=".",
        project_root="/tmp/project-root",
        allowed_tool_names={"mcp__builder__workspace_scaffold"},
    )
    builder_tools = {tool._sdk_tool_name: tool for tool in servers["builder"]["tools"]}

    assert "workspace_scaffold" in builder_tools
    result = await builder_tools["workspace_scaffold"]({"task_id": "task-abc"})

    payload = json.loads(result["content"][0]["text"])
    assert payload == {"status": "ok", "action": "scaffold_ready", "language": "python"}
    assert captured == {"task_id": "task-abc", "project_root": "/tmp/project-root"}


def test_sdk_mcp_servers_filter_tools_to_agent_allowlist(monkeypatch):
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

    from autonomous_agent_builder.agents.tools import sdk_mcp

    importlib.reload(sdk_mcp)

    servers = sdk_mcp.build_default_mcp_servers(
        workspace_path=".",
        project_root="/tmp/project-root",
        allowed_tool_names={
            "mcp__builder__task_show",
            "mcp__workspace__run_command",
        },
    )

    assert [tool._sdk_tool_name for tool in servers["builder"]["tools"]] == ["task_show"]
    assert [tool._sdk_tool_name for tool in servers["workspace"]["tools"]] == [
        "run_command"
    ]


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
