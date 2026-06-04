"""Hermes-owned Chrome browser-control tool.

Extension bridge only: Windows Chrome + Hermes extension + native messaging Unix socket.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

try:
    from hermes_constants import get_hermes_home as _get_hermes_home  # noqa: F401
    from tools.registry import tool_error, tool_result
except ImportError:
    def tool_result(data: Any) -> str:  # type: ignore[misc]
        return json.dumps({"success": True, **data} if isinstance(data, dict) else {"result": data})

    def tool_error(msg: str, *, success: bool = False, **_: Any) -> str:  # type: ignore[misc]
        return json.dumps({"success": success, "error": msg})

PLUGIN_DIR = Path(__file__).resolve().parent
DEFAULT_TIMEOUT_SECONDS = 45
MAX_ACTIONS = 20
MAX_TEXT_CHARS = 120_000

_SOCKET_PATH = Path(os.environ.get("HERMES_CHROME_BRIDGE_SOCKET",
    str(Path.home() / ".hermes" / "run" / "chrome-bridge.sock")))


# ── Shared helpers ────────────────────────────────────────────────────────────

def _coerce_positive_int(raw: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _normalise_action(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    t = str(raw.get("type") or "").strip()
    if not t:
        return None
    action = dict(raw)
    action["type"] = t
    return action


def _normalise_actions(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("actions must be a list")
    return [a for item in raw[:MAX_ACTIONS] if (a := _normalise_action(item)) is not None]


# ── Extension socket path (Windows Chrome + native messaging) ─────────────────

def _socket_reachable(*, timeout: float = 2.0) -> bool:
    if not _SOCKET_PATH.exists():
        return False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(str(_SOCKET_PATH))
        s.close()
        return True
    except OSError:
        return False


def _wake_chrome_extension() -> None:
    """Wake Chrome's MV3 service worker (goes idle after ~30s)."""
    import subprocess, platform, time
    try:
        if platform.system() == "Darwin":
            subprocess.run(["open", "-a", "Google Chrome", "about:newtab"],
                           capture_output=True, timeout=5)
        else:
            subprocess.run(
                ["powershell.exe", "-Command",
                 "& { Start-Process 'cmd.exe' '/c start chrome about:newtab' }"],
                capture_output=True, timeout=5,
            )
    except Exception:
        pass
    time.sleep(3)


def _call_socket(payload: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    """Raw socket call — no retry logic."""
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout_seconds)
    with client:
        client.connect(str(_SOCKET_PATH))
        client.sendall(json.dumps(payload, ensure_ascii=False).encode())
        chunks: list[bytes] = []
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    raw = b"".join(chunks).decode()
    return json.loads(raw) if raw else {
        "success": False, "error_code": "EMPTY_RESPONSE",
        "error": "Extension bridge returned no output",
    }


def _run_extension_bridge(request: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    payload: dict[str, Any]
    if request.get("action") == "status":
        payload = {"type": "status", "timeoutSeconds": timeout_seconds}
    else:
        payload = {
            "type": "run",
            "actions": request.get("actions", []),
            "timeoutSeconds": timeout_seconds,
            "sessionName": request.get("sessionName"),
            "taskId": request.get("taskId"),
            "useSelectedTab": request.get("useSelectedTab", False),
            "maxTextChars": request.get("maxTextChars", 20_000),
        }

    # First attempt
    if _SOCKET_PATH.exists():
        try:
            return _call_socket(payload, timeout_seconds=timeout_seconds)
        except Exception:
            pass  # fall through to recovery

    # Socket missing or dead — MV3 service worker went idle. Remove stale socket,
    # wake Chrome, then wait for the native host to rebind.
    try:
        if _SOCKET_PATH.exists():
            _SOCKET_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    _wake_chrome_extension()
    import time
    for _ in range(10):
        if _SOCKET_PATH.exists():
            try:
                return _call_socket(payload, timeout_seconds=timeout_seconds)
            except Exception:
                time.sleep(1)
        else:
            time.sleep(1)

    return {
        "success": False,
        "error_code": "SOCKET_DOWN",
        "error": (
            "Extension bridge socket not found after Chrome wake attempt. "
            "Open Chrome, ensure the Hermes extension is enabled, and navigate to any HTTPS page."
        ),
        "socket": str(_SOCKET_PATH),
    }


def _extension_health(*, timeout_seconds: int) -> dict[str, Any]:
    reachable = _socket_reachable()
    result: dict[str, Any] = {
        "success": True,
        "bridge": "extension",
        "socket": str(_SOCKET_PATH),
        "preflight_ok": reachable,
        "ready": False,
    }
    if not reachable:
        result["error_code"] = "SOCKET_DOWN"
        return result
    status = _run_extension_bridge({"action": "status"}, timeout_seconds=timeout_seconds)
    result["ready"] = bool(status.get("success"))
    result["active_tab"] = status.get("active_tab", {})
    if not status.get("success"):
        result["error_code"] = status.get("error_code", "BRIDGE_ERROR")
        result["error"] = status.get("error", "Bridge status failed")
    return result


# ── Diagnostics (filesystem/manifest checks, bridge-independent) ──────────────

def _diagnostics() -> dict[str, Any]:
    try:
        sys.path.insert(0, str(PLUGIN_DIR))
        from diagnostics import run_diagnostics  # type: ignore[import]
        return run_diagnostics()
    except Exception as exc:
        reachable = _socket_reachable()
        return {
            "success": True,
            "preflight_ok": reachable,
            "blocking_checks": [] if reachable else ["bridge_socket_reachable"],
            "diagnostics_degraded": str(exc),
        }


def _install_info() -> dict[str, Any]:
    return {
        "success": True,
        "bridge": "extension",
        "socket": str(_SOCKET_PATH),
        "steps": [
            "1. Load unpacked extension from C:\\Users\\<you>\\.claude\\extension\\ in chrome://extensions.",
            "2. Run: python .claude/plugin/hermes_chrome/scripts/install_hermes_chrome_bridge.py --extension-id <id>",
            "3. Run: bash .claude/plugin/hermes_chrome/scripts/sync.sh",
            "4. Call hermes_chrome_browser with action=status to confirm.",
        ],
    }


# ── Tool schema ───────────────────────────────────────────────────────────────

HERMES_CHROME_BROWSER_SCHEMA = {
    "name": "hermes_chrome_browser",
    "description": (
        "Control the user's Windows Chrome browser via the Hermes extension bridge. "
        "Requires the Hermes extension installed in Windows Chrome and the native messaging host deployed. "
        "Use for browser testing, authenticated tasks, screenshots, and UI verification. "
        "Always run action=status first to confirm the bridge is ready."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["install_info", "preflight", "diagnose", "health", "status", "run"],
                "description": (
                    "status/health: check if extension bridge is reachable. "
                    "preflight/diagnose: detailed health check including manifest/socket validation. "
                    "install_info: setup instructions. "
                    "run: execute browser actions."
                ),
                "default": "run",
            },
            "url": {
                "type": "string",
                "description": "Navigate to this URL before executing actions.",
            },
            "tab_id": {
                "type": "string",
                "description": "Extension tab ID to target. Omit to use the active tab.",
            },
            "actions": {
                "type": "array",
                "description": (
                    "Ordered browser actions. Batch everything into one call. "
                    "Supported types: "
                    "page_context (compact overview ~1KB), "
                    "snapshot (interactive elements with selectors), "
                    "text (full visible text), "
                    "screenshot, "
                    "zoom {x0, y0, x1, y1, quality?} (region-specific JPEG — use instead of full screenshot when you only care about part of the page), "
                    "goto {url, waitMs?, reload?}, "
                    "wait {ms}, "
                    "wait_for_selector {selector, timeout?} (poll until element present — use after goto instead of fixed wait), "
                    "wait_for_url_change {from_url?, timeout?} (poll until URL changes — use after form submit / login redirect), "
                    "click_text {text}, "
                    "click_selector {selector}, "
                    "fill_selector {selector, value, append?}, "
                    "evaluate {expression}, "
                    "cursor_move {x,y}, cursor_type {text}, cursor_key {key, modifiers?}, "
                    "cursor_scroll {deltaX?, deltaY?}, cursor_drag {x,y,duration?}, "
                    "cursor_click, cursor_double_click, cursor_right_click, cursor_hide, "
                    "close_tab."
                ),
                "items": {"type": "object"},
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Max wall time per bridge call.",
                "default": DEFAULT_TIMEOUT_SECONDS,
            },
            "max_text_chars": {
                "type": "integer",
                "description": "Max characters for text/snapshot actions.",
                "default": 20000,
            },
            "session_name": {
                "type": "string",
                "description": (
                    "Name for this task's Chrome tab group. All tabs opened during this call "
                    "are grouped under this name in Chrome's tab strip. Use a stable task "
                    "identifier (e.g. task ID or feature name) so related tabs stay together "
                    "and separate from other concurrent tasks. Defaults to 'Hermes Chrome'."
                ),
                "default": "Hermes Chrome",
            },
        },
        "additionalProperties": False,
    },
}


# ── Handler ───────────────────────────────────────────────────────────────────

def _handle_hermes_chrome_browser(args: dict, task_id: str | None = None, **_: Any) -> str:
    args = args or {}
    action = str(args.get("action") or "run").strip().lower()
    timeout_seconds = _coerce_positive_int(
        args.get("timeout_seconds"),
        default=DEFAULT_TIMEOUT_SECONDS, minimum=5, maximum=180,
    )

    # ── Static actions (no bridge needed) ─────────────────────────────────────
    if action == "install_info":
        return tool_result(_install_info())

    if action in ("preflight", "diagnose"):
        diag = _diagnostics()
        ext = _extension_health(timeout_seconds=timeout_seconds)
        return tool_result({
            "extension": ext,
            "diagnostics": diag,
            "ready": ext.get("ready", False),
        })

    # ── Health / status ────────────────────────────────────────────────────────
    if action in ("health", "status"):
        return tool_result(_extension_health(timeout_seconds=timeout_seconds))

    # ── Run ────────────────────────────────────────────────────────────────────
    if action != "run":
        return tool_error(f"Unknown action: {action!r}", success=False)

    try:
        actions = _normalise_actions(args.get("actions"))
    except ValueError as e:
        return tool_error(str(e), success=False)
    if not actions:
        actions = [{"type": "page_context"}]

    url = str(args.get("url") or "").strip()
    if url:
        actions.insert(0, {"type": "goto", "url": url})
    request: dict[str, Any] = {
        "action": "run",
        "actions": actions,
        "sessionName": str(args.get("session_name") or "Hermes Chrome"),
        "taskId": task_id or "",
        "maxTextChars": _coerce_positive_int(
            args.get("max_text_chars"), default=20_000, minimum=1_000, maximum=MAX_TEXT_CHARS,
        ),
        "useSelectedTab": bool(args.get("use_selected_tab", True)),
    }
    result = _run_extension_bridge(request, timeout_seconds=timeout_seconds)

    if not result.get("success"):
        return tool_error(
            result.get("error") or "Bridge call failed",
            success=False,
            error_code=result.get("error_code", "BRIDGE_ERROR"),
        )
    return tool_result(result)
