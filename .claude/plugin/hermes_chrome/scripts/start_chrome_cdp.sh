#!/usr/bin/env bash
# Start a dedicated testing Chrome instance with CDP enabled.
#
# What this does:
#   1. CDP already up on port → nothing to do.
#   2. Chrome running with the test profile (still starting) → wait for it.
#   3. No Chrome on the test profile → start one fresh.
#
# Uses a SEPARATE testing profile (google-chrome-test) so it never interferes
# with the main Chrome instance (builder dashboard, personal browsing, etc.).
#
# Chrome opens a VISIBLE window via WSLg (DISPLAY=:0) — not headless.
# Login state in the test profile persists across sessions.
#
# On first use: Chrome opens. Log in to any sites you want the agent to test.
# Those cookies persist and are reused automatically on every subsequent run.
#
# Usage:
#   bash ~/.claude/plugin/hermes_chrome/scripts/start_chrome_cdp.sh
#   HERMES_CDP_PORT=9223 bash start_chrome_cdp.sh
set -euo pipefail

PORT="${HERMES_CDP_PORT:-9222}"
PROFILE="${HERMES_CHROME_TEST_PROFILE:-$HOME/.config/google-chrome-test}"
LOG_DIR="$HOME/.hermes/logs"
LOG="$LOG_DIR/chrome-cdp.log"
CHROME_BIN="${HERMES_CHROME_BIN:-$(which google-chrome 2>/dev/null || echo '')}"

if [[ -z "$CHROME_BIN" ]]; then
  echo "✗ google-chrome not found in PATH."
  echo "  Install: sudo apt-get install -y google-chrome-stable"
  exit 1
fi
mkdir -p "$LOG_DIR"

# ── Fast path: CDP already up ──────────────────────────────────────────────────
_cdp_up() {
  curl -sf --max-time 2 "http://localhost:${PORT}/json/version" > /dev/null 2>&1
}

_cdp_ver() {
  curl -sf --max-time 2 "http://localhost:${PORT}/json/version" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('Browser','?'))" 2>/dev/null || echo "?"
}

if _cdp_up; then
  ver=$(_cdp_ver)
  echo "✓ Testing Chrome already running on port ${PORT}: ${ver}"
  exit 0
fi

# ── Wait path: Chrome is starting but CDP not bound yet ────────────────────────
# If Chrome is already running with --remote-debugging-port=PORT, just wait.
if pgrep -f "remote-debugging-port=${PORT}" > /dev/null 2>&1; then
  echo "→ Chrome is starting with CDP on port ${PORT} — waiting..."
  for i in $(seq 1 45); do
    sleep 1
    echo -n "."
    if _cdp_up; then
      echo ""
      echo "✓ Chrome CDP ready: $(_cdp_ver) (port ${PORT})"
      exit 0
    fi
  done
  echo ""
  echo "→ Chrome did not bind CDP after 45s — killing stale instance and restarting..."
  pkill -f "remote-debugging-port=${PORT}" 2>/dev/null || true
  sleep 1
fi

# ── Start path: launch Chrome fresh ──────────────────────────────────────────
# Remove stale singleton lock left by crashed instances
[[ -e "$PROFILE/SingletonLock" ]] && rm -f "$PROFILE/SingletonLock"
[[ -e "$PROFILE/Default/SingletonLock" ]] && rm -f "$PROFILE/Default/SingletonLock"
[[ -e "$PROFILE/SingletonCookie" ]] && rm -f "$PROFILE/SingletonCookie"

if [[ ! -d "$PROFILE/Default" ]]; then
  echo "→ First use: creating testing Chrome profile at ${PROFILE}"
  echo "  Chrome will open. Log in to any sites you want the agent to test."
  echo "  Cookies persist across sessions — one-time setup."
  mkdir -p "$PROFILE/Default"
fi

# Ensure WSLg display is available (Chrome opens a VISIBLE window, not headless)
export DISPLAY="${DISPLAY:-:0}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-/dev/null}"

echo "→ Starting testing Chrome (visible window, port ${PORT})..."
echo "  Profile: ${PROFILE}"

"$CHROME_BIN" \
  --remote-debugging-port="${PORT}" \
  --user-data-dir="${PROFILE}" \
  --profile-directory=Default \
  --no-first-run \
  --no-default-browser-check \
  --restore-last-session \
  --window-size=1280,900 \
  --start-maximized \
  --disable-features=MediaRouter \
  --suppress-message-center-popups \
  > "$LOG" 2>&1 &

CHROME_PID=$!
disown "$CHROME_PID" 2>/dev/null || true
echo "→ Chrome PID: ${CHROME_PID}"

# ── Wait up to 90s for CDP to bind ────────────────────────────────────────────
echo -n "→ Waiting for CDP"
for i in $(seq 1 90); do
  sleep 1
  echo -n "."
  if _cdp_up; then
    echo ""
    tab=$(curl -sf --max-time 2 "http://localhost:${PORT}/json/list" 2>/dev/null \
      | python3 -c "import sys,json; pages=[t for t in json.load(sys.stdin) if t.get('type')=='page']; print(pages[0].get('url','(no tabs yet)') if pages else '(no tabs yet)')" 2>/dev/null || echo "?")
    echo "✓ Testing Chrome ready: $(_cdp_ver)"
    echo "  Port: ${PORT}  |  Profile: ${PROFILE}"
    echo "  Tab: ${tab}"
    echo ""
    echo "  Preflight: bash ~/.claude/plugin/hermes_chrome/scripts/preflight.sh"
    exit 0
  fi
done
echo ""
echo "✗ Chrome CDP did not bind within 90s."
echo "  Log tail:"
tail -5 "$LOG" 2>/dev/null | sed 's/^/  /'
echo ""
echo "  Try manually: $CHROME_BIN --remote-debugging-port=${PORT} --user-data-dir=${PROFILE}"
exit 1
