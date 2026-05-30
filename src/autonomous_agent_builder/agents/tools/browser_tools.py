"""Real-browser verification tools backed by the Hermes Chrome bridge.

IMP-019: the ``browser-verifier`` subagent previously had no live-browser tool,
so for vanilla web apps the builder "verified" against jsdom only — never a real
browser. These tools let the builder drive the same Hermes Chrome bridge the
operator uses (``~/.hermes/run/chrome-bridge.sock``) to navigate the running
app, read rendered content, click/fill, and capture screenshots, returning
compact structured evidence.

Design notes (Claude-Agent-SDK-native):
- These are plain async functions returning JSON-serializable dicts. ``sdk_mcp``
  wraps them with ``@tool`` and exposes them as ``mcp__browser__*`` so they flow
  through the same allowed_tools / can_use_tool permission path as every other
  builder tool.
- Token discipline: ``read_text`` / ``page_context`` return text, never base64.
  ``screenshot`` returns the on-disk path the bridge wrote, never inline image
  bytes, so verifier context stays small.
- The bridge is optional infrastructure. When the socket is absent the tools
  return ``{"ok": False, "error": "bridge_unavailable", ...}`` so the verifier
  can fall back to deterministic (jsdom/test) evidence instead of hanging.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

# Conventional default ports per dev-server family, used when a serve script
# does not state an explicit port.
_DEFAULT_PORTS = {"vite": 5173, "serve": 3000, "next": 3000, "http-server": 8080}
_SERVE_SCRIPT_PRIORITY = ("dev", "preview", "serve", "start")

_DEFAULT_SOCKET = os.path.expanduser("~/.hermes/run/chrome-bridge.sock")
_BRIDGE_TIMEOUT_S = 60.0


def _socket_path() -> str:
    return os.environ.get("HERMES_CHROME_BRIDGE_SOCKET", _DEFAULT_SOCKET)


def bridge_available() -> bool:
    """True when the Hermes Chrome bridge socket exists."""
    path = _socket_path()
    try:
        import stat

        return stat.S_ISSOCK(os.stat(path).st_mode)
    except OSError:
        return False


async def hermes_bridge(payload: dict[str, Any], *, timeout: float = _BRIDGE_TIMEOUT_S) -> dict[str, Any]:
    """Send one JSON payload to the Hermes bridge socket and return the parsed reply.

    Never raises on connection/timeout — returns a structured error dict so the
    verifier can degrade gracefully rather than hang the run.
    """
    path = _socket_path()
    if not bridge_available():
        return {"ok": False, "error": "bridge_unavailable", "detail": f"no socket at {path}"}
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(path), timeout=10.0
        )
    except (OSError, asyncio.TimeoutError) as exc:
        return {"ok": False, "error": "bridge_connect_failed", "detail": str(exc)}
    try:
        writer.write(json.dumps(payload).encode())
        await writer.drain()
        try:
            writer.write_eof()
        except OSError:
            pass
        raw = await asyncio.wait_for(reader.read(), timeout=timeout)
    except (OSError, asyncio.TimeoutError) as exc:
        return {"ok": False, "error": "bridge_io_failed", "detail": str(exc)}
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass
    try:
        return json.loads(raw.decode(errors="replace"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": "bridge_bad_response", "detail": str(exc)}


def _first_result(reply: dict[str, Any], result_type: str) -> dict[str, Any]:
    for item in reply.get("results", []) or []:
        if item.get("type") == result_type:
            return item
    return {}


async def _run(actions: list[dict[str, Any]], *, session_name: str) -> dict[str, Any]:
    return await hermes_bridge(
        {"type": "run", "sessionName": session_name, "useSelectedTab": True, "actions": actions}
    )


def _extract_port(command: str) -> int | None:
    """Pull an explicit port from a serve command (`-l 5173`, `--port 3000`,
    `-p 8080`, or a bare `:5173`)."""
    m = re.search(r"(?:--port|-l|-p)[ =]+(\d{2,5})", command)
    if m:
        return int(m.group(1))
    m = re.search(r":(\d{2,5})\b", command)
    return int(m.group(1)) if m else None


def resolve_dev_server(project_root: str | os.PathLike[str]) -> dict[str, Any]:
    """Deterministically resolve how to serve a generated web app and the URL to
    open — so a verifier can start the app and point the browser at it without
    guessing. Pure filesystem read; no network, no process launch.

    Returns ``{ok, command, url, port, source}``. ``ok`` is False (with a
    ``hint``) when no servable web entrypoint is detected.
    """
    root = Path(project_root)
    pkg_path = root / "package.json"
    if pkg_path.is_file():
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": "package_json_unreadable", "detail": str(exc)}
        scripts = pkg.get("scripts") if isinstance(pkg.get("scripts"), dict) else {}
        for name in _SERVE_SCRIPT_PRIORITY:
            script = scripts.get(name)
            if isinstance(script, str) and script.strip():
                port = _extract_port(script)
                if port is None:
                    for family, default in _DEFAULT_PORTS.items():
                        if family in script:
                            port = default
                            break
                port = port or 5173
                return {
                    "ok": True,
                    "command": f"npm run {name}",
                    "url": f"http://localhost:{port}/",
                    "port": port,
                    "source": f"package.json scripts.{name}",
                }
    # No package.json serve script — a static index.html can be served directly.
    if (root / "index.html").is_file():
        return {
            "ok": True,
            "command": "npx serve . -l 5173",
            "url": "http://localhost:5173/",
            "port": 5173,
            "source": "static index.html",
        }
    return {
        "ok": False,
        "error": "no_web_entrypoint",
        "hint": "No package.json serve script or index.html found; this may not be a servable web app.",
    }


async def browser_navigate(url: str, *, session_name: str = "builder-verify") -> dict[str, Any]:
    """Navigate the bridge-controlled browser to ``url`` and return the landed
    URL/title plus compact page context (headings, nav, buttons, inputs)."""
    reply = await _run(
        [
            {"type": "goto", "url": url},
            {"type": "wait_for_selector", "selector": "body", "timeout": 8000},
            {"type": "page_context"},
        ],
        session_name=session_name,
    )
    if not reply.get("success", reply.get("ok", False)):
        return {"ok": False, "error": reply.get("error", "navigate_failed"), "detail": reply}
    ctx = _first_result(reply, "page_context")
    return {"ok": True, "url": ctx.get("url", reply.get("final_url", url)), "title": ctx.get("title", ""),
            "headings": ctx.get("headings", []), "nav": ctx.get("nav", []),
            "buttons": ctx.get("buttons", []), "inputs": ctx.get("inputs", [])}


async def browser_page_context(*, session_name: str = "builder-verify") -> dict[str, Any]:
    """Return compact page context for the current tab (URL, title, headings,
    nav, buttons, inputs) — ~1 KB, the cheapest way to verify rendered state."""
    reply = await _run([{"type": "page_context"}], session_name=session_name)
    if not reply.get("success", reply.get("ok", False)):
        return {"ok": False, "error": reply.get("error", "page_context_failed"), "detail": reply}
    ctx = _first_result(reply, "page_context")
    return {"ok": True, **{k: ctx.get(k) for k in ("url", "title", "headings", "nav", "buttons", "inputs")}}


async def browser_read_text(*, session_name: str = "builder-verify") -> dict[str, Any]:
    """Return the visible rendered text of the current page (to assert real
    content/values), never base64."""
    reply = await _run([{"type": "text"}], session_name=session_name)
    if not reply.get("success", reply.get("ok", False)):
        return {"ok": False, "error": reply.get("error", "read_text_failed"), "detail": reply}
    res = _first_result(reply, "text")
    return {"ok": True, "url": res.get("url"), "title": res.get("title"), "text": res.get("text", "")}


async def browser_click_text(text: str, *, session_name: str = "builder-verify") -> dict[str, Any]:
    """Click the first element whose visible text matches ``text`` (cursor-driven),
    then return the resulting page context."""
    reply = await _run(
        [
            {"type": "click_text", "text": text},
            {"type": "wait", "ms": 600},
            {"type": "page_context"},
        ],
        session_name=session_name,
    )
    if not reply.get("success", reply.get("ok", False)):
        return {"ok": False, "error": reply.get("error", "click_failed"), "detail": reply}
    ctx = _first_result(reply, "page_context")
    return {"ok": True, "clicked": text, "url": ctx.get("url"), "title": ctx.get("title"),
            "buttons": ctx.get("buttons", []), "inputs": ctx.get("inputs", [])}


async def browser_fill(selector: str, value: str, *, session_name: str = "builder-verify") -> dict[str, Any]:
    """Fill the form field matched by CSS ``selector`` with ``value`` and return
    the resulting page context."""
    reply = await _run(
        [
            {"type": "fill_selector", "selector": selector, "value": value},
            {"type": "page_context"},
        ],
        session_name=session_name,
    )
    if not reply.get("success", reply.get("ok", False)):
        return {"ok": False, "error": reply.get("error", "fill_failed"), "detail": reply}
    ctx = _first_result(reply, "page_context")
    return {"ok": True, "selector": selector, "url": ctx.get("url"), "inputs": ctx.get("inputs", [])}


async def browser_screenshot(*, session_name: str = "builder-verify") -> dict[str, Any]:
    """Capture a viewport screenshot as visual proof; return the on-disk path the
    bridge wrote (never inline bytes, to keep verifier context small)."""
    reply = await _run([{"type": "screenshot"}], session_name=session_name)
    if not reply.get("success", reply.get("ok", False)):
        return {"ok": False, "error": reply.get("error", "screenshot_failed"), "detail": reply}
    res = _first_result(reply, "screenshot")
    return {"ok": True, "screenshot_path": res.get("screenshot_path", "")}
