#!/usr/bin/env python3
"""Cross-platform installer for the Hermes Chrome Bridge.

Supports macOS and WSL2 (Windows). Detects the platform automatically
and installs the native host, native manifest, and (on WSL2) the Windows
registry key and batch wrapper.

Usage:
  # Step 1 — install runtime files (no extension ID needed yet):
  python3 install_hermes_chrome_bridge.py --install-runtime

  # Step 2 — after loading the extension in Chrome and getting its ID:
  python3 install_hermes_chrome_bridge.py --extension-id <id>
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HOST_NAME = "com.hermes.chrome_bridge"
REPO_ROOT = Path(__file__).resolve().parents[1]


# ── Platform detection ────────────────────────────────────────────────────────

def is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False


def is_macos() -> bool:
    return platform.system() == "Darwin"


def detect_platform() -> str:
    if is_wsl():
        return "wsl"
    if is_macos():
        return "macos"
    return "unsupported"


# ── Path helpers ──────────────────────────────────────────────────────────────

def win_user_home() -> Path:
    """Windows user home directory, accessible from WSL2 as /mnt/c/Users/<user>."""
    try:
        result = subprocess.run(
            ["powershell.exe", "-Command", "[Environment]::GetFolderPath('UserProfile')"],
            capture_output=True, text=True, timeout=5,
        )
        win_path = result.stdout.strip()  # e.g. C:\Users\gurusharan.gupta
        if win_path and len(win_path) >= 2 and win_path[1] == ":":
            drive = win_path[0].lower()
            rest = win_path[3:].replace("\\", "/")
            return Path(f"/mnt/{drive}/{rest}")
    except Exception:
        pass
    raise SystemExit("Could not determine Windows user home directory.")


def win_claude_dir() -> Path:
    return win_user_home() / ".claude"


def macos_extension_dir() -> Path:
    return Path.home() / ".hermes" / "chrome-bridge" / "extension"


def macos_native_host_path() -> Path:
    return Path.home() / ".hermes" / "chrome-bridge" / "native" / "native_host.py"


def macos_manifest_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "NativeMessagingHosts"


# ── Runtime installation ──────────────────────────────────────────────────────

def install_runtime_wsl() -> dict:
    claude = win_claude_dir()
    ext_dst = claude / "extension"
    bat_dst = claude / "hermes_chrome_bridge.bat"

    # The native host runs INSIDE WSL2 — it serves an AF_UNIX socket at a WSL
    # path that the bridge client (also WSL2) connects to. A Windows-Python copy
    # cannot serve that socket. So deploy the host to the WSL location sync.sh
    # owns, and make the Windows launcher shell into WSL to run it.
    native_dst = Path.home() / ".hermes" / "chrome-bridge" / "native" / "native_host.py"
    native_dst.parent.mkdir(parents=True, exist_ok=True)

    ext_dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(REPO_ROOT / "extension"), str(ext_dst), dirs_exist_ok=True)

    shutil.copy2(str(REPO_ROOT / "native" / "native_host.py"), str(native_dst))
    native_dst.chmod(native_dst.stat().st_mode | 0o111)

    bat_dst.write_text(f"@echo off\nwsl python3 {native_dst}\n", encoding="utf-8")

    return {
        "platform": "wsl",
        "extension_dir": f"C:\\Users\\...\\{ext_dst.relative_to(ext_dst.parents[1])}",
        "extension_dir_wsl": str(ext_dst),
        "native_host_wsl": str(native_dst),
        "batch_wrapper_wsl": str(bat_dst),
        "launcher_command": f"wsl python3 {native_dst}",
        "next_step": (
            f"Open chrome://extensions → Load unpacked → select: "
            f"{str(ext_dst).replace('/mnt/c/', 'C:\\\\').replace('/', '\\\\')}"
        ),
    }


def install_runtime_macos() -> dict:
    ext_dst = macos_extension_dir()
    native_dst = macos_native_host_path()

    ext_dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(REPO_ROOT / "extension"), str(ext_dst), dirs_exist_ok=True)

    native_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(REPO_ROOT / "native" / "native_host.py"), str(native_dst))
    native_dst.chmod(native_dst.stat().st_mode | 0o111)

    return {
        "platform": "macos",
        "extension_dir": str(ext_dst),
        "native_host": str(native_dst),
        "next_step": (
            f"Open chrome://extensions → Load unpacked → select: {ext_dst}"
        ),
    }


# ── Manifest installation ─────────────────────────────────────────────────────

def install_manifest_wsl(extension_id: str, native_host_override: str | None = None) -> dict:
    claude = win_claude_dir()
    native_host_win = native_host_override or f"C:\\Users\\{win_user_home().name}\\.claude\\hermes_chrome_bridge.bat"

    manifest = {
        "name": HOST_NAME,
        "description": "Hermes Chrome Bridge native messaging host",
        "path": native_host_win,
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    manifest_path = claude / "com.hermes.chrome_bridge.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    # Register in Windows registry
    reg_key = r"HKCU\SOFTWARE\Google\Chrome\NativeMessagingHosts\com.hermes.chrome_bridge"
    manifest_win = f"C:\\Users\\{win_user_home().name}\\.claude\\com.hermes.chrome_bridge.json"
    subprocess.run(
        ["powershell.exe", "-Command",
         f"New-Item -Path 'HKCU:\\SOFTWARE\\Google\\Chrome\\NativeMessagingHosts\\{HOST_NAME}' -Force | Out-Null; "
         f"Set-ItemProperty -Path 'HKCU:\\SOFTWARE\\Google\\Chrome\\NativeMessagingHosts\\{HOST_NAME}' "
         f"-Name '(Default)' -Value '{manifest_win}'"],
        check=True,
    )

    return {
        "platform": "wsl",
        "manifest_path_wsl": str(manifest_path),
        "manifest_path_win": manifest_win,
        "registry_key": reg_key,
        "extension_id": extension_id,
        "next_step": "Reload the Hermes Chrome Bridge extension in chrome://extensions.",
    }


def install_manifest_macos(extension_id: str, native_host_override: str | None = None) -> dict:
    native_host = native_host_override or str(macos_native_host_path())
    manifest_dir = macos_manifest_dir()
    manifest_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": HOST_NAME,
        "description": "Hermes Chrome Bridge native messaging host",
        "path": native_host,
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    manifest_path = manifest_dir / f"{HOST_NAME}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return {
        "platform": "macos",
        "manifest_path": str(manifest_path),
        "extension_id": extension_id,
        "next_step": "Reload the Hermes Chrome Bridge extension in chrome://extensions.",
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--install-runtime", action="store_true",
                        help="Copy extension + native host to the platform install location.")
    parser.add_argument("--extension-id",
                        help="Chrome extension ID (shown in chrome://extensions after loading unpacked).")
    parser.add_argument("--native-host", default=None,
                        help="Override native host path written into the manifest.")
    parser.add_argument("--platform", choices=["wsl", "macos"], default=None,
                        help="Force platform (default: auto-detect).")
    args = parser.parse_args()

    plat = args.platform or detect_platform()
    if plat == "unsupported":
        raise SystemExit(f"Unsupported platform: {platform.system()}. Use --platform wsl or macos.")

    if not args.install_runtime and not args.extension_id:
        raise SystemExit("Provide --install-runtime, --extension-id <id>, or both.")

    result: dict = {"platform": plat}

    if args.install_runtime:
        if plat == "wsl":
            result.update(install_runtime_wsl())
        else:
            result.update(install_runtime_macos())

    if args.extension_id:
        if plat == "wsl":
            result.update(install_manifest_wsl(args.extension_id, args.native_host))
        else:
            result.update(install_manifest_macos(args.extension_id, args.native_host))

    result["success"] = True
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
