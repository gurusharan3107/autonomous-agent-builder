#!/usr/bin/env bash
# Capture an immutable .seed/devpulse snapshot for the autoresearch loop.
#
# Per docs/autoresearch/README.md: the seed is the canonical starting state
# for every fixture run. baseline.py and run.py copy this snapshot into a
# fresh workspace per run; the seed itself is never mutated.
#
# Run this script ONCE before the first baseline. Re-run only when the
# devpulse template evolves (e.g., a new app version that future runs
# should baseline against).
#
# Usage:
#   bash scripts/autoresearch/setup_seed.sh
#   bash scripts/autoresearch/setup_seed.sh --src /custom/devpulse --dst /custom/.seed/devpulse
#
# Outputs:
#   ${SEED_DST}/                       immutable snapshot tree (chmod -R a-w)
#   ${SEED_DST}.sha256                 hash of snapshot tree for compare.py drift detection

set -euo pipefail

SRC="${1:-/home/gurusharangupta/Builder-Workspace/devpulse}"
DST="${2:-/home/gurusharangupta/.seed/devpulse}"

if [[ ! -d "$SRC" ]]; then
  echo "ERROR: source devpulse not found at $SRC" >&2
  exit 1
fi

if [[ -e "$DST" ]]; then
  echo "ERROR: destination $DST already exists. Remove it first if you intend to re-snapshot." >&2
  echo "  rm -rf '$DST' '${DST}.sha256'" >&2
  exit 1
fi

echo "Snapshotting $SRC → $DST"
mkdir -p "$(dirname "$DST")"
cp -r --reflink=auto "$SRC" "$DST"

# Strip Python bytecode caches. These churn on every pytest run and create
# false "tracked file divergence" signals in seed_verify. Source files are
# what matter for substrate identity; .pyc regenerates per Python invocation.
echo "Stripping __pycache__/ directories"
find "$DST" -type d -name __pycache__ -not -path "*/.venv/*" -exec rm -rf {} + 2>/dev/null || true

# Clear builder runtime state so each baseline run starts with an empty board.
# The .agent-builder/ layout (observed 2026-05-24): agent_builder.db (+ -shm/-wal
# sidecars), dashboard/, archive/, runtime/, scripts/, knowledge/, migrations/,
# config.yaml, onboarding-state.json, readiness.json. Clear execution state
# (db file + sidecars, logs, sessions, runtime, dashboard cache) but keep
# config, migrations, and the .agent-builder/ skeleton intact. Builder
# re-creates the empty DB schema from migrations on next start.
if [[ -d "$DST/.agent-builder" ]]; then
  echo "Clearing .agent-builder execution state; preserving config/migrations"
  rm -f "$DST/.agent-builder/agent_builder.db" \
        "$DST/.agent-builder/agent_builder.db-shm" \
        "$DST/.agent-builder/agent_builder.db-wal" 2>/dev/null || true
  rm -rf "$DST/.agent-builder/db" \
         "$DST/.agent-builder/logs" \
         "$DST/.agent-builder/sessions" \
         "$DST/.agent-builder/runtime" \
         "$DST/.agent-builder/dashboard" 2>/dev/null || true
fi

# Compute snapshot hash (excluding .git internals which churn even for read-only state).
echo "Computing sha256 of snapshot tree"
(cd "$DST" && find . -type f ! -path './.git/objects/pack/*' -print0 | sort -z | xargs -0 sha256sum) \
  | sha256sum | awk '{print $1}' > "${DST}.sha256"
echo "  → $(cat "${DST}.sha256")"

# Make the snapshot read-only so accidental writes during baseline runs fail loudly.
echo "Setting chmod -R a-w on $DST"
chmod -R a-w "$DST"

echo "Done. Seed snapshot ready at $DST"
echo "  Hash:    $(cat "${DST}.sha256")"
echo "  Verify:  ls -la $DST"
