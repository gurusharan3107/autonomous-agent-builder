"""Deterministic, bridge-independent health checks for the Hermes Chrome Bridge.

Single source of truth for `diagnose`. Catches the recurring browser-control
setup regressions *before* the agent starts clicking — when the live bridge is
down, this still runs (it inspects the filesystem + native manifest, not the
socket round-trip alone).

Each check carries `severity` ("blocking" | "warning"), the `surface` that owns
the root cause, and a concrete `fix`, so the output routes the agent to the
right layer instead of trial-and-error guessing. Consumed by `scripts/diagnose.py`
(skill preflight) and `tools.py` (`_diagnostics`).

Stdlib only. Supports WSL2 and macOS, matching the rest of the bridge.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import platform
import socket
import stat
from pathlib import Path
from typing import Any

PLUGIN_DIR = Path(__file__).resolve().parent
HOST_NAME = "com.hermes.chrome_bridge"

# Files whose source↔deployed drift means Chrome is running stale code.
_DRIFT_FILES = [
    "manifest.json",
    "service_worker.js",
    "content-scripts/cursor-agent.js",
]
_PLACEHOLDER_ID = "__REPLACE_WITH_EXTENSION_ID__"


# ── Platform + path resolution ────────────────────────────────────────────────

def _is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def _socket_path() -> Path:
    return Path(os.environ.get("HERMES_CHROME_BRIDGE_SOCKET",
        str(Path.home() / ".hermes" / "run" / "chrome-bridge.sock")))


def _native_host_deployed() -> Path:
    # Native host always runs in WSL2/macOS at this path (see sync.sh).
    return Path.home() / ".hermes" / "chrome-bridge" / "native" / "native_host.py"


def _win_claude_dir() -> Path | None:
    """Windows .claude dir, reachable from WSL2 as /mnt/c/Users/<user>/.claude."""
    override = os.environ.get("HERMES_WIN_CLAUDE_DIR")
    if override:
        return Path(override)
    # Prefer the dir that actually holds the native manifest; else first match.
    candidates = sorted(glob.glob("/mnt/*/Users/*/.claude"))
    for cand in candidates:
        if (Path(cand) / f"{HOST_NAME}.json").exists():
            return Path(cand)
    return Path(candidates[0]) if candidates else None


def _deployed_extension_dir() -> Path | None:
    if _is_macos():
        return Path.home() / ".hermes" / "chrome-bridge" / "extension"
    win = _win_claude_dir()
    return (win / "extension") if win else None


def _native_manifest_path() -> Path | None:
    if _is_macos():
        return (Path.home() / "Library" / "Application Support" / "Google"
                / "Chrome" / "NativeMessagingHosts" / f"{HOST_NAME}.json")
    win = _win_claude_dir()
    return (win / f"{HOST_NAME}.json") if win else None


def _resolve_manifest_target(raw_path: str) -> Path | None:
    """Map a manifest `path` (possibly a Windows path) to a WSL-readable Path."""
    if not raw_path:
        return None
    p = raw_path.strip()
    if len(p) >= 2 and p[1] == ":":  # C:\Users\...\x.bat
        drive = p[0].lower()
        return Path(f"/mnt/{drive}/" + p[3:].replace("\\", "/"))
    return Path(p)


# ── Check primitive ───────────────────────────────────────────────────────────

def _check(name: str, ok: bool | None, *, severity: str, detail: str,
           surface: str, fix: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "severity": severity, "detail": detail,
            "surface": surface, "fix": fix}


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return None


# ── Individual checks ──────────────────────────────────────────────────────────

def _check_socket() -> dict[str, Any]:
    sock = _socket_path()
    if not sock.exists():
        return _check("bridge_socket_reachable", False, severity="blocking",
            detail=f"socket {sock} does not exist",
            surface="chrome+extension (operator)",
            fix="Open Chrome with a visible window and load/reload the Hermes "
                "Chrome Bridge extension in chrome://extensions; the native host "
                "creates the socket on connect.")
    try:
        is_sock = stat.S_ISSOCK(sock.stat().st_mode)
    except Exception:
        is_sock = False
    if not is_sock:
        return _check("bridge_socket_reachable", False, severity="blocking",
            detail=f"{sock} exists but is not a socket (stale file)",
            surface="native host lifecycle",
            fix=f"rm {sock} then reload the extension to restart the native host.")
    try:
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c.settimeout(2.0)
        c.connect(str(sock))
        c.close()
        return _check("bridge_socket_reachable", True, severity="blocking",
            detail="socket present and accepting connections", surface="-", fix="-")
    except OSError as exc:
        return _check("bridge_socket_reachable", False, severity="blocking",
            detail=f"socket present but connect failed: {exc} (host dead/stale)",
            surface="native host lifecycle",
            fix="Reload the extension in chrome://extensions to restart the "
                "native host; if it persists, rm the socket and reload.")


def _check_native_host() -> dict[str, Any]:
    host = _native_host_deployed()
    if not host.exists():
        return _check("native_host_deployed", False, severity="blocking",
            detail=f"{host} missing",
            surface="sync / install",
            fix="Run scripts/sync.sh (or install_hermes_chrome_bridge.py "
                "--install-runtime) to deploy the native host.")
    return _check("native_host_deployed", True, severity="blocking",
        detail=f"present at {host}", surface="-", fix="-")


def _check_extension_deployed() -> dict[str, Any]:
    ext = _deployed_extension_dir()
    if ext is None:
        return _check("extension_deployed", None, severity="blocking",
            detail="could not resolve deployed extension dir",
            surface="diagnostics",
            fix="Set HERMES_WIN_CLAUDE_DIR to the Windows .claude dir.")
    required = ["manifest.json", "service_worker.js",
                "content-scripts/cursor-agent.js"]
    missing = [f for f in required if not (ext / f).exists()]
    if missing:
        return _check("extension_deployed", False, severity="blocking",
            detail=f"deployed extension at {ext} missing: {', '.join(missing)}",
            surface="sync",
            fix="Run scripts/sync.sh to deploy the extension Chrome loads from.")
    return _check("extension_deployed", True, severity="blocking",
        detail=f"core files present at {ext}", surface="-", fix="-")


def _check_cursor_assets() -> dict[str, Any]:
    ext = _deployed_extension_dir()
    if ext is None or not ext.exists():
        return _check("cursor_assets_present", None, severity="blocking",
            detail="deployed extension dir unresolved", surface="diagnostics",
            fix="Resolve the deployed extension dir first (extension_deployed).")
    # Derive the asset list from the deployed manifest's web_accessible_resources.
    assets: list[str] = []
    try:
        mani = json.loads((ext / "manifest.json").read_text())
        for entry in mani.get("web_accessible_resources", []):
            assets.extend(entry.get("resources", []))
    except Exception:
        pass
    assets = [a for a in assets if a.startswith("images/")] or [
        "images/cursor-agent.png", "images/ocean-glow-pointer.svg",
        "images/pointer-shape-animated.svg"]
    missing = [a for a in assets if not (ext / a).exists()]
    if missing:
        return _check("cursor_assets_present", False, severity="blocking",
            detail=f"missing cursor assets: {', '.join(missing)} — clicks animate "
                   "via these; absence makes the cursor invisible or throws",
            surface="extension assets + sync",
            fix="Run scripts/sync.sh; confirm the assets exist in "
                "plugin/extension/images/.")
    return _check("cursor_assets_present", True, severity="blocking",
        detail=f"{len(assets)} cursor assets present", surface="-", fix="-")


def _check_drift() -> dict[str, Any]:
    ext = _deployed_extension_dir()
    src = PLUGIN_DIR / "extension"
    if ext is None or not ext.exists() or not src.exists():
        return _check("deployed_matches_source", None, severity="warning",
            detail="cannot compare (source or deployed dir unresolved)",
            surface="diagnostics", fix="-")
    drifted = [f for f in _DRIFT_FILES if _sha(src / f) != _sha(ext / f)]
    if drifted:
        return _check("deployed_matches_source", False, severity="warning",
            detail=f"source ≠ deployed for: {', '.join(drifted)} — Chrome is "
                   "running stale code; edits are not live until synced",
            surface="sync discipline",
            fix="Run scripts/sync.sh, then reload the extension.")
    return _check("deployed_matches_source", True, severity="warning",
        detail="deployed extension matches source", surface="-", fix="-")


def _check_native_manifest() -> dict[str, Any]:
    mani_path = _native_manifest_path()
    if mani_path is None:
        return _check("native_manifest_valid", None, severity="blocking",
            detail="could not resolve native manifest path",
            surface="diagnostics", fix="Set HERMES_WIN_CLAUDE_DIR.")
    if not mani_path.exists():
        return _check("native_manifest_valid", False, severity="blocking",
            detail=f"native manifest {mani_path} missing",
            surface="install script",
            fix="Run install_hermes_chrome_bridge.py --extension-id <id from "
                "chrome://extensions>.")
    try:
        mani = json.loads(mani_path.read_text())
    except Exception as exc:
        return _check("native_manifest_valid", False, severity="blocking",
            detail=f"native manifest unparseable: {exc}",
            surface="install script",
            fix="Re-run install_hermes_chrome_bridge.py --extension-id <id>.")
    origins = mani.get("allowed_origins", [])
    if not origins or _PLACEHOLDER_ID in json.dumps(origins):
        return _check("native_manifest_valid", False, severity="blocking",
            detail=f"allowed_origins not bound to a real extension id: {origins}",
            surface="install script",
            fix="Run install_hermes_chrome_bridge.py --extension-id <id from "
                "chrome://extensions> after loading the unpacked extension.")
    target = _resolve_manifest_target(str(mani.get("path", "")))
    if target is None or not target.exists():
        return _check("native_manifest_valid", False, severity="blocking",
            detail=f"manifest `path` → {mani.get('path')!r} does not exist",
            surface="install script",
            fix="Run install_hermes_chrome_bridge.py --install-runtime to "
                "(re)create the launcher the manifest points to.")
    return _check("native_manifest_valid", True, severity="blocking",
        detail=f"bound to {origins[0]}, launcher present", surface="-", fix="-")


def _check_launcher() -> dict[str, Any]:
    """WSL only: the .bat must launch the WSL native host, not a missing
    Windows-python copy. This is the interpreter-mismatch regression."""
    win = _win_claude_dir()
    if win is None:
        return _check("launcher_consistent", None, severity="warning",
            detail="Windows .claude dir unresolved", surface="diagnostics", fix="-")
    bat = win / "hermes_chrome_bridge.bat"
    if not bat.exists():
        return _check("launcher_consistent", False, severity="blocking",
            detail=f"{bat} missing",
            surface="install script",
            fix="Run install_hermes_chrome_bridge.py --install-runtime.")
    body = bat.read_text(errors="replace")
    host = _native_host_deployed()
    if "wsl" in body.lower() and "python3" in body.lower():
        if str(host) in body:
            return _check("launcher_consistent", True, severity="blocking",
                detail="launcher runs the deployed WSL native host", surface="-",
                fix="-")
        return _check("launcher_consistent", False, severity="warning",
            detail=f"launcher uses wsl python3 but not the deployed host {host}",
            surface="install script",
            fix="Re-run install_hermes_chrome_bridge.py --install-runtime to "
                "point the launcher at the deployed WSL native host.")
    return _check("launcher_consistent", False, severity="blocking",
        detail="launcher does not use `wsl python3` — the AF_UNIX socket only "
               "works when the native host runs inside WSL2",
        surface="install script",
        fix="Re-run install_hermes_chrome_bridge.py --install-runtime to "
            "regenerate the launcher as `wsl python3 <wsl native host>`.")


# ── Aggregate ──────────────────────────────────────────────────────────────────

def run_diagnostics() -> dict[str, Any]:
    if _is_macos():
        plat = "macos"
    elif _is_wsl():
        plat = "wsl"
    else:
        plat = "unsupported"

    checks = [
        _check_socket(),
        _check_native_host(),
        _check_extension_deployed(),
        _check_cursor_assets(),
        _check_drift(),
        _check_native_manifest(),
    ]
    if plat == "wsl":
        checks.append(_check_launcher())

    blocking = [c["name"] for c in checks
                if c["ok"] is False and c["severity"] == "blocking"]
    warnings = [c["name"] for c in checks
                if c["ok"] is False and c["severity"] == "warning"]
    unknown = [c["name"] for c in checks if c["ok"] is None]

    return {
        "success": True,
        "platform": plat,
        "preflight_ok": not blocking,
        "blocking_checks": blocking,
        "warnings": warnings,
        "unknown_checks": unknown,
        "checks": checks,
        "socket": str(_socket_path()),
    }
