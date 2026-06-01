#!/usr/bin/env bash
# IMP-030 — repeatable dashboard build→embedded-sync pipeline.
#
# vite builds the dashboard SPA into frontend/dist; the embedded server serves
# from src/autonomous_agent_builder/embedded/dashboard (app.py:211-234). Without
# this step the served bundle drifts behind the frontend source (it had fallen
# back to a 2026-05-20 build, predating IMP-017's cancel control). Run this after
# any frontend change, then restart the running `builder start` to serve it.
#
# Usage: scripts/build_dashboard.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FE="$ROOT/frontend"
DEST="$ROOT/src/autonomous_agent_builder/embedded/dashboard"

echo "[build_dashboard] building frontend (tsc -b && vite build)…"
( cd "$FE" && npm run build )

if [ ! -f "$FE/dist/index.html" ]; then
  echo "[build_dashboard] ERROR: $FE/dist/index.html missing after build" >&2
  exit 1
fi

echo "[build_dashboard] syncing $FE/dist/ → $DEST/"
rsync -a --delete "$FE/dist/" "$DEST/"

echo "[build_dashboard] synced. Served bundle is now:"
grep -oE 'index-[A-Za-z0-9_]+\.(js|css)' "$DEST/index.html" | sed 's/^/    /'

cat <<'EOF'
[build_dashboard] NOTE: the running server caches nothing per-request but holds
the process — restart it to serve the new bundle:
    pkill -f 'builder start' ; (cd <app-workspace> && builder start --port 9876 --force &)
Then hard-reload the dashboard tab.
EOF
