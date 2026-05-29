#!/usr/bin/env bash
# Sync repo → install location, then hot-reload Chrome.
# Works on macOS and WSL2. Auto-detects platform.
# Usage: ./sync.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOCKET="${HERMES_CHROME_BRIDGE_SOCKET:-$HOME/.hermes/run/chrome-bridge.sock}"

# ── Platform detection ────────────────────────────────────────────────────────
if grep -qi microsoft /proc/version 2>/dev/null; then
  PLATFORM="wsl"
elif [[ "$(uname)" == "Darwin" ]]; then
  PLATFORM="macos"
else
  echo "Unsupported platform"; exit 1
fi

# ── Resolve install directories ───────────────────────────────────────────────
# Global plugin: ~/.claude/plugin/hermes_chrome/ — available in all sessions.
GLOBAL_PLUGIN="$HOME/.claude/plugin/hermes_chrome"

if [[ "$PLATFORM" == "wsl" ]]; then
  WIN_HOME="$(powershell.exe -Command '[Environment]::GetFolderPath("UserProfile")' 2>/dev/null | tr -d '\r')"
  DRIVE="${WIN_HOME:0:1}"; DRIVE="${DRIVE,,}"
  WIN_HOME_WSL="/mnt/${DRIVE}/${WIN_HOME:3}"
  WIN_HOME_WSL="${WIN_HOME_WSL//\\//}"
  INSTALL_EXT="$WIN_HOME_WSL/.claude/extension"
else
  INSTALL_EXT="$HOME/.hermes/chrome-bridge/extension"
fi
# Native host always runs in WSL2 (called by the batch file via `wsl python3 ...`)
INSTALL_NATIVE="$HOME/.hermes/chrome-bridge/native/native_host.py"

# ── Sync files ────────────────────────────────────────────────────────────────

# 1. Global plugin install (makes hermes_chrome_browser tool available everywhere)
echo "→ Syncing plugin → $GLOBAL_PLUGIN"
mkdir -p "$GLOBAL_PLUGIN"
rsync -a --exclude='*.Zone.Identifier' --exclude='scripts/' \
  "$REPO_ROOT/" "$GLOBAL_PLUGIN/"

# 1b. Install diagnose.py to global plugin scripts/ so preflight works from any cwd.
#     sync.sh itself is intentionally excluded (repo-specific); diagnose.py is not.
mkdir -p "$GLOBAL_PLUGIN/scripts"
cp "$REPO_ROOT/scripts/diagnose.py"  "$GLOBAL_PLUGIN/scripts/diagnose.py"
cp "$REPO_ROOT/scripts/preflight.sh" "$GLOBAL_PLUGIN/scripts/preflight.sh"
chmod +x "$GLOBAL_PLUGIN/scripts/preflight.sh"
echo "→ Installed scripts → $GLOBAL_PLUGIN/scripts/ (diagnose.py, preflight.sh)"

# 2. Chrome extension (platform-specific Windows/macOS path Chrome loads from)
echo "→ [$PLATFORM] Syncing extension → $INSTALL_EXT"
mkdir -p "$INSTALL_EXT"
rsync -a --exclude='*.Zone.Identifier' "$REPO_ROOT/extension/" "$INSTALL_EXT/"

# 3. Native host (called by Chrome via native messaging)
echo "→ [$PLATFORM] Syncing native_host.py → $INSTALL_NATIVE"
cp "$REPO_ROOT/native/native_host.py" "$INSTALL_NATIVE"
[[ "$PLATFORM" == "macos" ]] && chmod +x "$INSTALL_NATIVE"

# ── Hot-reload via Unix socket bridge ────────────────────────────────────────
echo "→ Sending reload via bridge ($SOCKET)..."
python3 - <<PYEOF
import socket, json, os, time

sock_path = os.environ.get("HERMES_CHROME_BRIDGE_SOCKET",
    os.path.expanduser("~/.hermes/run/chrome-bridge.sock"))

def call(payload, timeout=5):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(sock_path)
        s.sendall(json.dumps(payload).encode())
        chunks = []
        while True:
            chunk = s.recv(4096)
            if not chunk: break
            chunks.append(chunk)
        return json.loads(b"".join(chunks)) if chunks else {}
    except Exception as e:
        return {"error": str(e)}
    finally:
        s.close()

r = call({"type": "reload", "timeoutSeconds": 5})
if r.get("success") or "reloading" in str(r.get("message", "")):
    print("   Reload sent — waiting for bridge...")
elif "error" in r:
    print(f"   Warning: {r['error']}")

for _ in range(10):
    time.sleep(1.5)
    r = call({"type": "status", "timeoutSeconds": 3})
    if r.get("success"):
        print(f"   Bridge ready — {r.get('active_tab', {}).get('url', 'unknown')}")
        break
else:
    print("   Bridge did not reconnect within 15s — check chrome://extensions")
PYEOF

echo "✓ Done."
