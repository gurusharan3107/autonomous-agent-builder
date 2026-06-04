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
async def test_navigate_opens_dedicated_visible_tab_with_forced_reload(monkeypatch) -> None:
    """IMP-019 operator-visibility: navigate must open a dedicated NEW tab
    (``useSelectedTab=False`` -> bridge ``chrome.tabs.create``) so the operator
    can watch the verification, and force a real navigation (``reload=True``) so
    a tab parked on the same URL doesn't serve a stale render. The prior
    behavior hijacked the operator's active tab in place and could no-op on a
    same-URL goto."""
    capture: dict = {}
    reply = {
        "success": True,
        "results": [{"type": "page_context", "url": "http://localhost:5173/", "title": "App"}],
    }
    _patch_bridge(monkeypatch, reply, capture)
    await browser_tools.browser_navigate("http://localhost:5173/")
    sent = json.loads(capture["writer"].sent.decode())
    assert sent["useSelectedTab"] is False  # dedicated visible tab, not the active one
    goto = next(a for a in sent["actions"] if a["type"] == "goto")
    assert goto.get("reload") is True  # never read a stale same-URL render


@pytest.mark.asyncio
async def test_followup_reads_reuse_the_navigated_tab(monkeypatch) -> None:
    """Reads/clicks after navigate default to ``useSelectedTab=True`` so they
    continue in the tab navigate just created+activated (not a second new tab)."""
    browser_tools._session_tabs.clear()
    capture: dict = {}
    reply = {"success": True, "results": [{"type": "text", "text": "hello"}]}
    _patch_bridge(monkeypatch, reply, capture)
    await browser_tools.browser_read_text()
    sent = json.loads(capture["writer"].sent.decode())
    assert sent["useSelectedTab"] is True


@pytest.mark.asyncio
async def test_session_reuses_one_tab_instead_of_spawning_new_ones(monkeypatch) -> None:
    """IMP-019: the bridge has no cross-call tab memory, so a naive navigate
    opens a new tab every call (operator saw two tabs). browser_tools pins the
    tab id returned by the first navigate and stamps it onto subsequent actions
    so the whole verification session stays in ONE tab."""
    browser_tools._session_tabs.clear()
    capture: dict = {}
    # First navigate: bridge creates tab 4242 and returns it in the goto result.
    _patch_bridge(
        monkeypatch,
        {
            "success": True,
            "results": [
                {"type": "goto", "tabId": 4242, "url": "http://localhost:5173/"},
                {"type": "page_context", "url": "http://localhost:5173/", "title": "App"},
            ],
        },
        capture,
    )
    await browser_tools.browser_navigate("http://localhost:5173/")
    assert browser_tools._session_tabs["builder-verify"] == 4242
    first = json.loads(capture["writer"].sent.decode())
    assert "tabId" not in first["actions"][0]  # nothing to pin yet on the opener

    # Second navigate: must REUSE tab 4242 (pinned onto the goto action), not create.
    _patch_bridge(
        monkeypatch,
        {
            "success": True,
            "results": [
                {"type": "goto", "tabId": 4242, "url": "http://localhost:5173/x"},
            ],
        },
        capture,
    )
    await browser_tools.browser_navigate("http://localhost:5173/x")
    second = json.loads(capture["writer"].sent.decode())
    assert second["actions"][0]["tabId"] == 4242


@pytest.mark.asyncio
async def test_browser_close_tears_down_the_session_tab(monkeypatch) -> None:
    """Teardown closes the opened tab (close_tab on the pinned id) and forgets it
    so the run leaves no orphan tab (hermes-chrome closeout step 4)."""
    browser_tools._session_tabs.clear()
    browser_tools._session_tabs["builder-verify"] = 4242
    capture: dict = {}
    _patch_bridge(
        monkeypatch, {"success": True, "results": [{"type": "close_tab", "tabId": 4242}]}, capture
    )
    result = await browser_tools.browser_close()
    assert result["closed"] is True
    sent = json.loads(capture["writer"].sent.decode())
    assert sent["actions"][0] == {"type": "close_tab", "tabId": 4242}
    assert "builder-verify" not in browser_tools._session_tabs  # forgotten
    # No tab open -> no-op, no bridge call needed.
    assert (await browser_tools.browser_close())["closed"] is False


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
    # IMP-019: queryable field must be present and equal to tier.
    assert real["browser_evidence_tier"] == "real_browser"

    # No browser evidence + bridge down (non-UI) → acceptable weaker tier (does not block CI).
    fallback = browser_evidence_tier(
        json.dumps({"status": "pass", "browser_evidence": []}), bridge_available=False
    )
    assert fallback["tier"] == "jsdom_fallback" and fallback["advisory"]
    assert fallback["browser_evidence_tier"] == "jsdom_fallback"

    # No browser evidence but bridge available → the IMP-019 gap, advisory raised.
    gap = browser_evidence_tier(
        json.dumps({"status": "pass", "browser_evidence": []}), bridge_available=True
    )
    assert gap["tier"] == "no_browser_proof" and gap["advisory"]
    assert gap["browser_evidence_tier"] == "no_browser_proof"


def test_browser_tools_registered_in_tool_registry() -> None:
    # P19 contract: tools in an agent's allowed_tools that lack a tool_registry
    # schema are silently dropped (tool_not_found_in_registry). A live
    # feature-verifier run (recall-loop 2026-05-30) showed every mcp__browser__*
    # tool dropped because the schemas were missing here. Guard it.
    from autonomous_agent_builder.agents import tool_registry as tr
    from autonomous_agent_builder.agents.definitions import BROWSER_TOOLS

    missing = [t for t in BROWSER_TOOLS if t not in tr._SDK_BUILTINS]
    assert not missing, f"browser tools missing tool_registry schemas: {missing}"


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
