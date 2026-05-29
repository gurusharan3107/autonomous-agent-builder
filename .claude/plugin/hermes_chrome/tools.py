"""Hermes-owned Chrome browser-control tool."""

from __future__ import annotations

import json
import os
import socket
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


def _coerce_positive_int(raw: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _normalise_action(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    action_type = str(raw.get("type") or "").strip()
    if not action_type:
        return None
    action = dict(raw)
    action["type"] = action_type
    return action


def _normalise_actions(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("actions must be a list")
    actions: list[dict[str, Any]] = []
    for item in raw[:MAX_ACTIONS]:
        action = _normalise_action(item)
        if action is not None:
            actions.append(action)
    return actions


def _install_info() -> dict[str, Any]:
    return {
        "success": True,
        "socket": str(_SOCKET_PATH),
        "steps": [
            "Load unpacked extension from C:\\Users\\<you>\\.claude\\extension\\ in chrome://extensions.",
            "Copy the extension id shown in chrome://extensions.",
            "Run: python .claude/plugin/hermes_chrome/scripts/install_hermes_chrome_bridge.py --extension-id <id>",
            "Run: .claude/plugin/hermes_chrome/scripts/sync.sh",
            "Call hermes_chrome_browser with action=status to confirm.",
        ],
    }


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


def _diagnostics() -> dict[str, Any]:
    # Delegate to the shared deterministic checker (single source of truth,
    # also used by scripts/diagnose.py in the skill preflight). It runs even
    # when the live bridge is down: filesystem + native-manifest inspection.
    try:
        import sys
        sys.path.insert(0, str(PLUGIN_DIR))
        from diagnostics import run_diagnostics  # type: ignore[import]
        return run_diagnostics()
    except Exception as exc:
        reachable = _socket_reachable()
        return {
            "success": True,
            "preflight_ok": reachable,
            "blocking_checks": [] if reachable else ["bridge_socket_reachable"],
            "checks": [{"name": "bridge_socket_reachable", "ok": reachable}],
            "socket": str(_SOCKET_PATH),
            "diagnostics_degraded": f"shared checker unavailable: {exc}",
        }


def _preflight() -> dict[str, Any]:
    diagnostics = _diagnostics()
    return {
        "success": True,
        "socket": str(_SOCKET_PATH),
        "socket_exists": _SOCKET_PATH.exists(),
        "diagnostics": diagnostics,
        "preflight_ok": diagnostics["preflight_ok"],
        "blocking_checks": diagnostics["blocking_checks"],
    }


def _build_bridge_request(args: dict[str, Any], *, task_id: str | None) -> dict[str, Any]:
    action = str(args.get("action") or "run").strip().lower()
    if action not in {"install_info", "preflight", "diagnose", "health", "status", "run"}:
        raise ValueError("action must be one of: install_info, preflight, diagnose, health, status, run")

    request: dict[str, Any] = {
        "action": action,
        "sessionName": str(args.get("session_name") or "Hermes Chrome"),
        "taskId": task_id or "",
        "maxTextChars": _coerce_positive_int(
            args.get("max_text_chars"),
            default=20_000,
            minimum=1_000,
            maximum=MAX_TEXT_CHARS,
        ),
    }
    if action == "run":
        actions = _normalise_actions(args.get("actions"))
        url = str(args.get("url") or "").strip()
        if url:
            actions.insert(0, {"type": "goto", "url": url})
        if not actions:
            actions = [{"type": "snapshot"}]
        request["actions"] = actions
        request["useSelectedTab"] = bool(args.get("use_selected_tab", False))
    return request


def _build_extension_request(request: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    if request["action"] == "status":
        return {"type": "status", "timeoutSeconds": timeout_seconds}
    return {
        "type": "run",
        "actions": request.get("actions", []),
        "timeoutSeconds": timeout_seconds,
        "sessionName": request.get("sessionName"),
        "taskId": request.get("taskId"),
        "useSelectedTab": request.get("useSelectedTab", False),
        "maxTextChars": request.get("maxTextChars", 20_000),
    }


def _run_extension_bridge(request: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    if not _SOCKET_PATH.exists():
        return {
            "success": False,
            "error": "Hermes Chrome Bridge socket not found. Ensure Chrome is open with the extension loaded.",
            "socket": str(_SOCKET_PATH),
        }
    payload = _build_extension_request(request, timeout_seconds=timeout_seconds)
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(timeout_seconds)
        with client:
            client.connect(str(_SOCKET_PATH))
            client.sendall(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            chunks: list[bytes] = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        raw = b"".join(chunks).decode("utf-8")
        return json.loads(raw) if raw else {"success": False, "error": "Hermes extension bridge returned no output"}
    except Exception as exc:
        return {"success": False, "error": f"Hermes extension bridge failed: {exc}", "socket": str(_SOCKET_PATH)}


def _health_check(*, timeout_seconds: int) -> dict[str, Any]:
    reachable = _socket_reachable()
    result: dict[str, Any] = {
        "success": True,
        "socket": str(_SOCKET_PATH),
        "preflight_ok": reachable,
        "blocking_checks": [] if reachable else ["bridge_socket_reachable"],
        "bridge_status": None,
        "selected_tab_ready": False,
        "ready": False,
    }
    if not reachable:
        return result
    bridge_status = _run_extension_bridge({"action": "status"}, timeout_seconds=timeout_seconds)
    result["bridge_status"] = bridge_status
    result["ready"] = bool(bridge_status.get("success"))
    result["selected_tab_ready"] = bool(bridge_status.get("content_script", {}).get("injected"))
    if not bridge_status.get("success"):
        result["bridge_error"] = bridge_status.get("error") or "Hermes Chrome bridge status failed"
    return result


HERMES_CHROME_BROWSER_SCHEMA = {
    "name": "hermes_chrome_browser",
    "description": (
        "Control the user's signed-in Chrome profile through the Hermes Chrome "
        "extension and native messaging host. Use for browser testing or authenticated "
        "browser tasks when the user explicitly wants Chrome state."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["install_info", "preflight", "diagnose", "health", "status", "run"],
                "description": (
                    "Use install_info for setup instructions, preflight for local checks, "
                    "diagnose for detailed deterministic runtime checks, status to check "
                    "live bridge availability, health for combined diagnostics plus live "
                    "status, and run to execute browser actions."
                ),
                "default": "run",
            },
            "url": {
                "type": "string",
                "description": "Optional URL to open before executing actions.",
            },
            "session_name": {
                "type": "string",
                "description": "Short Chrome session name for this task.",
            },
            "use_selected_tab": {
                "type": "boolean",
                "description": "Reuse Chrome's selected tab instead of creating a managed tab.",
                "default": False,
            },
            "actions": {
                "type": "array",
                "description": (
                    "Ordered browser actions. Supported types: goto, wait, snapshot, text, "
                    "screenshot, click_text, fill_selector, click_selector, cursor_move, "
                    "cursor_click, cursor_right_click, cursor_double_click, cursor_triple_click, "
                    "cursor_type, cursor_key, cursor_drag, cursor_scroll, cursor_status, "
                    "cursor_hide, evaluate, close_tab. High-level click/fill actions animate "
                    "the visible Hermes cursor before interacting."
                ),
                "items": {"type": "object"},
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Maximum wall time for the bridge request.",
                "default": DEFAULT_TIMEOUT_SECONDS,
            },
            "max_text_chars": {
                "type": "integer",
                "description": "Maximum text or DOM snapshot characters returned per action.",
                "default": 20000,
            },
        },
        "additionalProperties": False,
    },
}


def _handle_hermes_chrome_browser(args: dict, task_id: str | None = None, **_: Any) -> str:
    try:
        args = args or {}
        request = _build_bridge_request(args, task_id=task_id)
        timeout_seconds = _coerce_positive_int(
            args.get("timeout_seconds"),
            default=DEFAULT_TIMEOUT_SECONDS,
            minimum=5,
            maximum=180,
        )
    except Exception as exc:
        return tool_error(str(exc), success=False)

    if request["action"] == "install_info":
        return tool_result(_install_info())
    if request["action"] == "preflight":
        return tool_result(_preflight())
    if request["action"] == "diagnose":
        return tool_result(_diagnostics())
    if request["action"] == "health":
        return tool_result(_health_check(timeout_seconds=timeout_seconds))

    result = _run_extension_bridge(request, timeout_seconds=timeout_seconds)
    if not result.get("success"):
        return tool_error(result.get("error") or "Hermes Chrome bridge failed", success=False, details=result)
    return tool_result(result)
