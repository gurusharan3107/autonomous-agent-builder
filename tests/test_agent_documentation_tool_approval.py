"""Agent documentation-specialist KB tool approval regressions."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from autonomous_agent_builder.agents.runner import RunResult
from autonomous_agent_builder.embedded.server.app import create_app
from tests.agent_route_test_support import (
    wait_for_history_item as _wait_for_history_item,
)


@pytest.mark.asyncio
async def test_documentation_routed_kb_validate_is_auto_allowed_without_manual_approval(
    monkeypatch, test_db, tmp_path
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )

    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured["subagents"] = kwargs.get("subagents")
        permission = await kwargs["can_use_tool"](
            "mcp__builder__kb_validate",
            {"kb_dir": "system-docs"},
            {},
        )
        assert getattr(permission, "behavior", "") == "allow"
        return RunResult(
            session_id="sdk-session-kb-allow",
            cost_usd=0.01,
            tokens_input=4,
            tokens_output=4,
            num_turns=1,
            output_text="KB validation allowed.",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "Check whether the knowledge base is current for this repo."},
        )
        session_id = response.json()["session_id"]
        history_payload, assistant_item = await _wait_for_history_item(
            client, session_id, "assistant_message"
        )

    assert captured["subagents"] == ("documentation-agent",)
    assert assistant_item["payload"]["content"] == "KB validation allowed."
    assert all(item["type"] != "tool_approval_request" for item in history_payload["items"])


@pytest.mark.asyncio
async def test_documentation_routed_kb_validate_surfaces_exact_deny_reason_for_unsafe_path(
    monkeypatch, test_db, tmp_path
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )

    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured["subagents"] = kwargs.get("subagents")
        permission = await kwargs["can_use_tool"](
            "mcp__builder__kb_validate",
            {"kb_dir": "../outside"},
            {},
        )
        assert "must stay under `.agent-builder/knowledge/`" in getattr(permission, "message", "")
        return RunResult(
            session_id="sdk-session-kb-deny",
            cost_usd=0.01,
            tokens_input=4,
            tokens_output=4,
            num_turns=1,
            output_text="KB validation was denied.",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "Check whether the knowledge base is current for this repo."},
        )
        session_id = response.json()["session_id"]
        history_payload, tool_item = await _wait_for_history_item(
            client,
            session_id,
            "tool_error",
            predicate=lambda item: item["payload"].get("tool_name") == "mcp__builder__kb_validate",
        )

    assert captured["subagents"] == ("documentation-agent",)
    assert tool_item["payload"]["diagnostic"]["summary"] == "mcp__builder__kb_validate denied"
    assert (
        "must stay under `.agent-builder/knowledge/`"
        in tool_item["payload"]["diagnostic"]["error_message"]
    )
    assert (
        'Retry with `{"kb_dir":"system-docs"}`' in tool_item["payload"]["diagnostic"]["next_action"]
    )
    assert all(item["type"] != "tool_approval_request" for item in history_payload["items"])


@pytest.mark.asyncio
async def test_documentation_routed_kb_tools_skip_interactive_approval(
    monkeypatch, test_db, tmp_path
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )

    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured["subagents"] = kwargs.get("subagents")
        permission = await kwargs["can_use_tool"](
            "mcp__builder__kb_show",
            {"doc_id": "system-docs/system-architecture.md"},
            {},
        )
        updated_input = getattr(permission, "updated_input", None) or getattr(
            permission, "updatedInput", None
        )
        assert updated_input == {"doc_id": "system-docs/system-architecture.md"}
        return RunResult(
            session_id="sdk-session-docs-auto-approve",
            cost_usd=0.02,
            tokens_input=8,
            tokens_output=6,
            num_turns=1,
            output_text="Docs checked without approval.",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "Check whether the knowledge base is current for this repo."},
        )
        session_id = response.json()["session_id"]
        history_payload, assistant_item = await _wait_for_history_item(
            client, session_id, "assistant_message"
        )

    assert captured["subagents"] == ("documentation-agent",)
    assert all(item["type"] != "tool_approval_request" for item in history_payload["items"])
    assert assistant_item["payload"]["content"] == "Docs checked without approval."


@pytest.mark.asyncio
async def test_documentation_follow_up_continuation_keeps_kb_tools_auto_approved(
    monkeypatch, test_db, tmp_path
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )

    captured_prompts: list[str] = []

    async def fake_run_phase(self, **kwargs):
        captured_prompts.append(kwargs["prompt"])
        if len(captured_prompts) == 1:
            return RunResult(
                session_id="sdk-session-docs-initial",
                cost_usd=0.02,
                tokens_input=8,
                tokens_output=6,
                num_turns=1,
                output_text="Docs are stale.",
            )
        permission = await kwargs["can_use_tool"](
            "mcp__builder__kb_show",
            {"doc_id": "system-docs/system-architecture.md"},
            {},
        )
        updated_input = getattr(permission, "updated_input", None) or getattr(
            permission, "updatedInput", None
        )
        assert updated_input == {"doc_id": "system-docs/system-architecture.md"}
        return RunResult(
            session_id="sdk-session-docs-follow-up",
            cost_usd=0.02,
            tokens_input=8,
            tokens_output=6,
            num_turns=1,
            output_text="updated and verified",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/agent/chat",
            json={"message": "Check whether the knowledge base is current for this repo."},
        )
        session_id = first.json()["session_id"]
        await _wait_for_history_item(client, session_id, "assistant_message")

        second = await client.post(
            "/api/agent/chat",
            json={"message": "please update", "session_id": session_id},
        )
        assert second.status_code == 200
        history_payload, assistant_item = await _wait_for_history_item(
            client,
            session_id,
            "assistant_message",
            predicate=lambda item: item["payload"]["content"] == "updated and verified",
        )

    continuation_status = [
        item
        for item in history_payload["items"]
        if item["type"] == "specialist_status"
        and item["payload"].get("route_reason") == "specialist_continuation:documentation-agent"
    ]
    assert continuation_status
    assert all(item["type"] != "tool_approval_request" for item in history_payload["items"])
    assert "specialist_continuation:documentation-agent" in captured_prompts[1]
    assert assistant_item["payload"]["content"] == "updated and verified"


@pytest.mark.asyncio
async def test_documentation_routed_kb_contract_and_lint_skip_interactive_approval(
    monkeypatch, test_db, tmp_path
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )

    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured["subagents"] = kwargs.get("subagents")
        captured["prompt"] = kwargs["prompt"]
        contract_permission = await kwargs["can_use_tool"](
            "mcp__builder__kb_contract",
            {"doc_type": "testing", "sample_title": "Testing Required"},
            {},
        )
        lint_permission = await kwargs["can_use_tool"](
            "mcp__builder__kb_lint",
            {"doc_type": "testing", "content": "# draft"},
            {},
        )
        assert getattr(contract_permission, "behavior", "") == "allow"
        assert getattr(lint_permission, "behavior", "") == "allow"
        return RunResult(
            session_id="sdk-session-docs-contract-lint",
            cost_usd=0.02,
            tokens_input=8,
            tokens_output=6,
            num_turns=1,
            output_text="Contract and lint ran without approval.",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "Can documentation also be generated on testing required?"},
        )
        session_id = response.json()["session_id"]
        history_payload, assistant_item = await _wait_for_history_item(
            client, session_id, "assistant_message"
        )

    assert captured["subagents"] == ("documentation-agent",)
    # Doc context is serialized compact (json.dumps separators=(",",":")) — match it.
    assert '"resolved_action":"add"' in captured["prompt"]
    assert '"target_doc_type":"testing"' in captured["prompt"]
    assert '"testing_scope":"testing_required"' in captured["prompt"]
    assert all(item["type"] != "tool_approval_request" for item in history_payload["items"])
    assert assistant_item["payload"]["content"] == "Contract and lint ran without approval."


@pytest.mark.asyncio
async def test_documentation_routed_turn_still_prompts_for_unrelated_tools(
    monkeypatch, test_db, tmp_path
):
    dashboard_root = tmp_path / "dashboard"
    dashboard_root.mkdir()
    (dashboard_root / "index.html").write_text(
        "<html><body>embedded</body></html>", encoding="utf-8"
    )

    captured: dict[str, object] = {}

    async def fake_run_phase(self, **kwargs):
        captured["subagents"] = kwargs.get("subagents")
        # IMP-020: the chat lane now denies ungranted mutating built-ins (Bash/Edit/
        # Write/...) outright and routes them to dispatch — they no longer surface an
        # approval card. Use a confirmable non-builtin mutating tool, which IMP-020
        # explicitly keeps promptable, to exercise the "still prompts" path.
        permission = await kwargs["can_use_tool"](
            "mcp__workspace__run_command",
            {"command": "npm publish", "description": "Publish the package"},
            {},
        )
        assert "wait" in getattr(permission, "message", "")
        return RunResult(
            session_id="sdk-session-docs-run-command-approval",
            cost_usd=0.02,
            tokens_input=8,
            tokens_output=6,
            num_turns=1,
            output_text="Blocked on manual approval.",
        )

    monkeypatch.setattr(
        "autonomous_agent_builder.embedded.server.routes.agent.AgentRunner.run_phase",
        fake_run_phase,
    )

    app = create_app(
        db_path=tmp_path / ".agent-builder" / "agent_builder.db",
        dashboard_path=dashboard_root,
        project_root=tmp_path,
    )
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"message": "Check whether the knowledge base is current for this repo."},
        )
        session_id = response.json()["session_id"]
        _, approval_item = await _wait_for_history_item(client, session_id, "tool_approval_request")

    assert captured["subagents"] == ("documentation-agent",)
    assert approval_item["payload"]["tool_name"] == "mcp__workspace__run_command"
