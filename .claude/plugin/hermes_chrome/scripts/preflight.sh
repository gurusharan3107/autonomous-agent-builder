#!/usr/bin/env bash
# hermes-chrome preflight — bring extension bridge to steady state before any browser action.
#
# Extension bridge only: Windows Chrome + Hermes extension + native messaging Unix socket.
#
# Auto-fixes applied in order:
#   1. File deployment drift → sync.sh
#   2. Stale socket → remove + Chrome wake via PowerShell
#   3. Socket missing (service worker idle) → PowerShell Chrome wake, wait 15s
#
# Exit 0: bridge is healthy. Prints active tab URL.
# Exit 1: unrecoverable — prints exact manual step.
set -euo pipefail

PLUGIN="${HOME}/.claude/plugin/hermes_chrome"
FIXED=()

# ── Extension socket preflight ────────────────────────────────────────────────
_socket_alive() {
  python3 - <<'PYEOF' 2>/dev/null
import socket, json, os, sys
SOCK = os.environ.get("HERMES_CHROME_BRIDGE_SOCKET",
    os.path.expanduser("~/.hermes/run/chrome-bridge.sock"))
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(3)
try:
    s.connect(SOCK)
    s.sendall(json.dumps({"type": "status", "timeoutSeconds": 3}).encode())
    data = b""
    while True:
        c = s.recv(4096)
        if not c: break
        data += c
    r = json.loads(data)
    sys.exit(0 if r.get("success") else 1)
except:
    sys.exit(1)
finally:
    try: s.close()
    except: pass
PYEOF
}

_run_extension_preflight() {
  DIAGNOSE="python3 ${PLUGIN}/scripts/diagnose.py"
  SOCK="${HERMES_CHROME_BRIDGE_SOCKET:-$HOME/.hermes/run/chrome-bridge.sock}"

  echo "→ [preflight/extension] Running diagnostics..."
  diag=$($DIAGNOSE --json 2>&1) || {
    echo "✗ [preflight/extension] diagnose.py failed — run sync.sh first."
    exit 1
  }

  preflight_ok=$(echo "$diag" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('preflight_ok',False))" 2>/dev/null)
  blocking=$(echo "$diag" | python3 -c "import sys,json; d=json.load(sys.stdin); print(','.join(d.get('blocking_checks',[])))" 2>/dev/null)
  warnings=$(echo "$diag" | python3 -c "import sys,json; d=json.load(sys.stdin); print(','.join(d.get('warnings',[])))" 2>/dev/null)

  # Auto-fix file deployment
  needs_sync=false
  [[ -n "$warnings" ]] && needs_sync=true
  for chk in native_host_deployed extension_deployed cursor_assets_present; do
    echo "$blocking" | grep -q "$chk" && needs_sync=true && break
  done

  if $needs_sync; then
    sync_sh=""
    [[ -f ".claude/plugin/hermes_chrome/scripts/sync.sh" ]] && sync_sh=".claude/plugin/hermes_chrome/scripts/sync.sh"
    [[ -z "$sync_sh" && -f "${PLUGIN}/scripts/sync.sh" ]] && sync_sh="${PLUGIN}/scripts/sync.sh"
    if [[ -z "$sync_sh" ]]; then
      echo "✗ [preflight/extension] File deployment issue but sync.sh not found."
      exit 1
    fi
    echo "→ [preflight/extension] Running sync.sh..."
    bash "$sync_sh" 2>&1 | grep -E '^[→✓✗]' || true
    FIXED+=("sync")
    diag=$($DIAGNOSE --json 2>&1) || true
    preflight_ok=$(echo "$diag" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('preflight_ok',False))" 2>/dev/null)
    blocking=$(echo "$diag" | python3 -c "import sys,json; d=json.load(sys.stdin); print(','.join(d.get('blocking_checks',[])))" 2>/dev/null)
  fi

  # Non-automatable manifest issues
  for chk in native_manifest_valid launcher_consistent; do
    if echo "$blocking" | grep -q "$chk"; then
      fix=$(echo "$diag" | python3 -c "
import sys,json; d=json.load(sys.stdin)
checks={c['name']:c for c in d.get('checks',[])}
print(checks.get('$chk',{}).get('fix','Re-run install_hermes_chrome_bridge.py'))
" 2>/dev/null || echo "Re-run install_hermes_chrome_bridge.py")
      echo "✗ [preflight/extension] ${chk} failed — not auto-fixable."
      echo "  Fix: ${fix}"
      exit 1
    fi
  done

  # Socket recovery
  if echo "$blocking" | grep -q "bridge_socket_reachable"; then
    [[ -S "$SOCK" ]] && { echo "→ Stale socket — removing..."; rm -f "$SOCK"; FIXED+=("stale-socket"); }
    echo "→ [preflight/extension] Waking Chrome extension..."
    if grep -qi microsoft /proc/version 2>/dev/null; then
      powershell.exe -Command "& { Start-Process 'cmd.exe' '/c start chrome about:newtab' }" 2>/dev/null || true
    elif [[ "$(uname)" == "Darwin" ]]; then
      open -a "Google Chrome" about:newtab 2>/dev/null || true
    fi
    FIXED+=("chrome-wake")
    echo -n "→ Waiting for bridge"
    connected=false
    for i in $(seq 1 15); do sleep 1; echo -n "."; _socket_alive && connected=true && break; done
    echo ""
    if ! $connected; then
      echo "✗ [preflight/extension] Bridge socket did not come up within 15s."
      echo "  Open Chrome → navigate to any HTTPS page → re-run preflight."
      exit 1
    fi
    FIXED+=("socket")
    diag=$($DIAGNOSE --json 2>&1) || true
    preflight_ok=$(echo "$diag" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('preflight_ok',False))" 2>/dev/null)
    blocking=$(echo "$diag" | python3 -c "import sys,json; d=json.load(sys.stdin); print(','.join(d.get('blocking_checks',[])))" 2>/dev/null)
  fi

  [[ "$preflight_ok" != "True" ]] && {
    echo "✗ [preflight/extension] Unresolved: ${blocking}"
    exit 1
  }

  # Live bridge verify — confirms socket is live AND active tab is controllable
  bridge_out=$(python3 - <<'PYEOF' 2>/dev/null
import socket, json, os, sys
SOCK = os.environ.get("HERMES_CHROME_BRIDGE_SOCKET",
    os.path.expanduser("~/.hermes/run/chrome-bridge.sock"))
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect(SOCK)
    s.sendall(json.dumps({"type":"status","timeoutSeconds":5}).encode())
    chunks = []
    while True:
        c = s.recv(4096)
        if not c: break
        chunks.append(c)
    r = json.loads(b"".join(chunks))
    tab = r.get("active_tab") or {}
    cs = r.get("content_script") or {}
    blocked = cs.get("blocked", False)
    url = tab.get("url", "?")
    title = tab.get("title", "")
    if not r.get("success"):
        print(f"fail|{r.get('error','?')}")
    elif blocked:
        reason = cs.get("reason", "unknown")
        print(f"blocked|{url}|{title}|{reason}")
    else:
        print(f"ok|{url}|{title}")
except Exception as e:
    print(f"error|{e}")
finally:
    try: s.close()
    except: pass
PYEOF
  ) || bridge_out="error|python call failed"

  status_key="${bridge_out%%|*}"
  if [[ "$status_key" == "fail" || "$status_key" == "error" ]]; then
    echo "✗ [preflight/extension] Live bridge failed: ${bridge_out#*|}"
    exit 1
  fi

  rest="${bridge_out#*|}"
  active_url="${rest%%|*}"
  rest="${rest#*|}"
  active_title="${rest%%|*}"

  fixed_note=""
  [[ ${#FIXED[@]} -gt 0 ]] && fixed_note=" (auto-fixed: $(IFS=', '; echo "${FIXED[*]}"))"
  if grep -qi microsoft /proc/version 2>/dev/null; then
    platform_label="Windows Chrome"
  elif [[ "$(uname)" == "Darwin" ]]; then
    platform_label="macOS Chrome"
  else
    platform_label="Chrome"
  fi
  echo "✓ [preflight] System ready${fixed_note}"
  echo "  Bridge: extension (${platform_label} + native messaging)"
  echo "  URL: ${active_url}"
  echo "  Title: ${active_title}"

  if [[ "$status_key" == "blocked" ]]; then
    block_reason="${bridge_out##*|}"
    echo "  ⚠ Content script blocked on active tab: ${block_reason}"
    echo "    Navigate Chrome to an https:// page before running browser actions."
  fi
}

# ── Entry ─────────────────────────────────────────────────────────────────────
_run_extension_preflight
