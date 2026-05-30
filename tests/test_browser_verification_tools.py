"""IMP-019: real-browser verification tools (Hermes Chrome bridge).

Guards: the browser MCP tools talk the bridge socket protocol correctly, degrade
gracefully when the bridge is absent, and are wired into the verification agents
so the `browser` MCP server is actually built.
"""

from __future__ import annotations

import json

import pytest

from autonomous_agent_builder.agents.tools import browser_tools


class _FakeWriter:
    def __init__(self) -> None:
        self.sent = b""

    def write(self, data: bytes) -> None:
        self.sent += data

    async def drain(self) -> None:
        return None

    def write_eof(self) -> None:
        return None

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


class _FakeReader:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def read(self, _n: int = -1) -> bytes:
        return self._payload


def _patch_bridge(monkeypatch, reply: dict, capture: dict) -> None:
    monkeypatch.setattr(browser_tools, "bridge_available", lambda: True)

    async def fake_open(_path):  # noqa: ANN001
        writer = _FakeWriter()
        capture["writer"] = writer
        return _FakeReader(json.dumps(reply).encode()), writer

    monkeypatch.setattr(browser_tools.asyncio, "open_unix_connection", fake_open)


@pytest.mark.asyncio
async def test_browser_navigate_parses_page_context(monkeypatch) -> None:
    capture: dict = {}
    reply = {
        "success": True,
        "final_url": "http://localhost:5173/",
        "results": [
            {"type": "goto", "url": "http://localhost:5173/"},
            {"type": "wait_for_selector", "selector": "body"},
            {
                "type": "page_context",
                "url": "http://localhost:5173/",
                "title": "Recall Loop",
                "headings": [{"tag": "H1", "text": "Recall Loop"}],
                "nav": [],
                "buttons": ["Study"],
                "inputs": [],
            },
        ],
    }
    _patch_bridge(monkeypatch, reply, capture)
    result = await browser_tools.browser_navigate("http://localhost:5173/")
    assert result["ok"] is True
    assert result["title"] == "Recall Loop"
    assert result["buttons"] == ["Study"]
    # The bridge received a goto + page_context run payload.
    sent = json.loads(capture["writer"].sent.decode())
    assert sent["type"] == "run"
    assert any(a["type"] == "goto" for a in sent["actions"])


@pytest.mark.asyncio
async def test_browser_tools_degrade_when_bridge_absent(monkeypatch) -> None:
    monkeypatch.setattr(browser_tools, "bridge_available", lambda: False)
    result = await browser_tools.browser_navigate("http://localhost:5173/")
    # Must not hang or raise — returns a structured, recognizable failure so the
    # verifier can fall back to deterministic evidence.
    assert result["ok"] is False
    assert result["error"] in {"bridge_unavailable", "navigate_failed"}


@pytest.mark.asyncio
async def test_browser_screenshot_returns_path_not_bytes(monkeypatch) -> None:
    capture: dict = {}
    reply = {
        "success": True,
        "results": [{"type": "screenshot", "screenshot_path": "/tmp/x.jpeg", "format": "jpeg"}],
    }
    _patch_bridge(monkeypatch, reply, capture)
    result = await browser_tools.browser_screenshot()
    assert result["ok"] is True
    assert result["screenshot_path"] == "/tmp/x.jpeg"
    assert "base64" not in result  # token discipline: never inline image bytes


def test_mcp_content_envelope_applied_to_plain_results() -> None:
    # F1 (agent-sdk-verifier audit): the SDK call_tool handler returns an empty
    # CallToolResult unless the handler result carries a "content" key. Browser
    # tools return plain dicts, so sdk_mcp must wrap them.
    import json as _json

    from autonomous_agent_builder.agents.tools.sdk_mcp import _to_mcp

    wrapped = _to_mcp({"ok": True, "url": "http://localhost:5173/"})
    assert "content" in wrapped
    assert wrapped["content"][0]["type"] == "text"
    assert "http://localhost:5173/" in wrapped["content"][0]["text"]
    assert _json.loads(wrapped["content"][0]["text"])["ok"] is True
    # Already-enveloped results (builder_tool_service) pass through unchanged.
    enveloped = {"content": [{"type": "text", "text": "x"}], "metadata": {}}
    assert _to_mcp(enveloped) is enveloped


def test_resolve_dev_server_reads_package_json_port(tmp_path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"dev": "npx serve . -l 5173"}}), encoding="utf-8"
    )
    r = browser_tools.resolve_dev_server(tmp_path)
    assert r["ok"] is True
    assert r["command"] == "npm run dev"
    assert r["url"] == "http://localhost:5173/"
    assert r["port"] == 5173


def test_resolve_dev_server_vite_default_port(tmp_path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"dev": "vite"}}), encoding="utf-8"
    )
    r = browser_tools.resolve_dev_server(tmp_path)
    assert r["ok"] is True and r["port"] == 5173


def test_resolve_dev_server_static_index_fallback(tmp_path) -> None:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    r = browser_tools.resolve_dev_server(tmp_path)
    assert r["ok"] is True
    assert r["source"] == "static index.html"


def test_resolve_dev_server_no_web_entrypoint(tmp_path) -> None:
    r = browser_tools.resolve_dev_server(tmp_path)
    assert r["ok"] is False
    assert r["error"] == "no_web_entrypoint"


def test_browser_mcp_server_built_only_when_tools_allowed() -> None:
    from autonomous_agent_builder.agents.tools.sdk_mcp import build_default_mcp_servers

    with_browser = build_default_mcp_servers(
        workspace_path="/tmp", allowed_tool_names=["mcp__browser__navigate", "Read"]
    )
    without_browser = build_default_mcp_servers(
        workspace_path="/tmp", allowed_tool_names=["Read", "mcp__builder__board"]
    )
    assert "browser" in with_browser
    assert "browser" not in without_browser


def test_browser_evidence_tier_classifies_proof() -> None:
    from autonomous_agent_builder.orchestrator.build_verification import browser_evidence_tier

    real = browser_evidence_tier(
        json.dumps({"status": "pass", "browser_evidence": ["screenshot:/tmp/x.jpeg", "url:/#/"]}),
        bridge_available=True,
    )
    assert real["tier"] == "real_browser" and real["advisory"] is None

    # No browser evidence + bridge down → acceptable weaker tier (does not block CI).
    fallback = browser_evidence_tier(
        json.dumps({"status": "pass", "browser_evidence": []}), bridge_available=False
    )
    assert fallback["tier"] == "jsdom_fallback" and fallback["advisory"]

    # No browser evidence but bridge available → the IMP-019 gap, advisory raised.
    gap = browser_evidence_tier(
        json.dumps({"status": "pass", "browser_evidence": []}), bridge_available=True
    )
    assert gap["tier"] == "no_browser_proof" and gap["advisory"]


def test_verification_agents_carry_browser_tools() -> None:
    from autonomous_agent_builder.agents.definitions import (
        BROWSER_TOOLS,
        get_agent_definition,
        get_subagent_definition,
    )

    for name in ("feature-verifier", "build-verifier"):
        tools = get_agent_definition(name).tools
        assert all(t in tools for t in BROWSER_TOOLS), name
    sub = get_subagent_definition("browser-verifier")
    assert all(t in sub.tools for t in BROWSER_TOOLS)
