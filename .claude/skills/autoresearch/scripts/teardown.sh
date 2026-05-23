#!/usr/bin/env bash
# Autoresearch loop teardown — bundled with the autoresearch skill.
#
# Shuts down ephemeral session state after a loop run:
#   - Stops + removes the Jaeger container (if running)
#   - Cleans up /tmp/devpulse-* workspaces (run.py leftovers if it crashed mid-run)
#   - Optionally clears /tmp/autoresearch/* evidence (--with-evidence)
#
# DOES NOT touch:
#   - .seed/devpulse  (immutable; never delete via teardown)
#   - docs/autoresearch/*.tsv  (durable evidence rows)
#   - docs/autoresearch/baseline_runs_summary.json  (σ floor — reused across iterations)
#   - git state  (operator owns branches)
#
# Usage:
#   bash .claude/skills/autoresearch/scripts/teardown.sh                  # stop Jaeger, clean /tmp/devpulse-*, restore stopped builders
#   bash .claude/skills/autoresearch/scripts/teardown.sh --with-evidence  # also clear /tmp/autoresearch/
#   bash .claude/skills/autoresearch/scripts/teardown.sh --keep-jaeger    # leave Jaeger running
#   bash .claude/skills/autoresearch/scripts/teardown.sh --no-restore     # don't restart builders bootstrap stopped
#   bash .claude/skills/autoresearch/scripts/teardown.sh --dry-run

set -euo pipefail

WITH_EVIDENCE=0
KEEP_JAEGER=0
DRY_RUN=0
NO_RESTORE=0
for arg in "$@"; do
  case "$arg" in
    --with-evidence) WITH_EVIDENCE=1 ;;
    --keep-jaeger)   KEEP_JAEGER=1 ;;
    --no-restore)    NO_RESTORE=1 ;;
    --dry-run)       DRY_RUN=1 ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "  [dry-run] would run: $*"
  else
    "$@"
  fi
}

echo "═══════════════════════════════════════════════════════════════════════"
echo "Autoresearch teardown"
echo "  Mode: $([[ $DRY_RUN -eq 1 ]] && echo dry-run || echo execute)"
echo "═══════════════════════════════════════════════════════════════════════"

# ----- Jaeger -----
echo ""
echo "▸ Jaeger container..."
if [[ $KEEP_JAEGER -eq 1 ]]; then
  echo "  Skipped (--keep-jaeger)"
elif ! command -v docker >/dev/null 2>&1; then
  echo "  ✓ docker not installed — nothing to stop"
else
  COMPOSE="$REPO/scripts/autoresearch/docker-compose.yml"
  RUNNING=$(docker ps --filter "name=autoresearch-jaeger" --format "{{.Names}}" 2>/dev/null || true)
  if [[ -z "$RUNNING" ]]; then
    EXISTS=$(docker ps -a --filter "name=autoresearch-jaeger" --format "{{.Names}}" 2>/dev/null || true)
    if [[ -z "$EXISTS" ]]; then
      echo "  ✓ No Jaeger container present"
    else
      echo "  Removing stopped Jaeger container..."
      run docker rm autoresearch-jaeger
    fi
  elif [[ -f "$COMPOSE" ]]; then
    echo "  Stopping Jaeger via docker compose..."
    run docker compose -f "$COMPOSE" down
  else
    echo "  Stopping container directly (docker-compose.yml missing)..."
    run docker stop autoresearch-jaeger
    run docker rm autoresearch-jaeger
  fi
fi

# ----- /tmp/devpulse-<uuid> workspaces -----
# Only UUID-suffixed dirs that match run.py's naming convention. This avoids
# deleting unrelated /tmp/devpulse-* paths (e.g., /tmp/devpulse-venv).
echo ""
echo "▸ Ephemeral workspace cleanup..."
UUID_RE='^/tmp/devpulse-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
shopt -s nullglob
ALL_CANDIDATES=(/tmp/devpulse-*)
shopt -u nullglob
WORKSPACES=()
for c in "${ALL_CANDIDATES[@]}"; do
  if [[ -d "$c" && "$c" =~ $UUID_RE ]]; then
    WORKSPACES+=("$c")
  fi
done
if [[ ${#WORKSPACES[@]} -eq 0 ]]; then
  echo "  ✓ No /tmp/devpulse-<uuid> workspaces to clean"
  # If there are non-UUID matches, surface them but do NOT delete.
  skipped=()
  for c in "${ALL_CANDIDATES[@]}"; do
    if [[ -d "$c" && ! "$c" =~ $UUID_RE ]]; then skipped+=("$c"); fi
  done
  if [[ ${#skipped[@]} -gt 0 ]]; then
    echo "  (skipped non-UUID paths that look unrelated: ${skipped[*]})"
  fi
else
  echo "  Found ${#WORKSPACES[@]} workspace(s) to remove:"
  for ws in "${WORKSPACES[@]}"; do
    echo "    - $ws"
    run rm -rf "$ws"
  done
fi

# ----- /tmp/autoresearch/* evidence (opt-in) -----
echo ""
echo "▸ Evidence cleanup..."
if [[ $WITH_EVIDENCE -eq 0 ]]; then
  echo "  Skipped (pass --with-evidence to also clear /tmp/autoresearch/)"
  if [[ -d /tmp/autoresearch ]]; then
    size=$(du -sh /tmp/autoresearch 2>/dev/null | awk '{print $1}')
    echo "    /tmp/autoresearch/ currently: ${size:-unknown}"
  fi
else
  if [[ -d /tmp/autoresearch ]]; then
    echo "  Clearing /tmp/autoresearch/..."
    run rm -rf /tmp/autoresearch
  else
    echo "  ✓ /tmp/autoresearch/ already absent"
  fi
fi

# ----- Restore builders bootstrap.sh stopped -----
echo ""
echo "▸ Restore stopped builders..."
STATE_FILE="$REPO/.autoresearch-bootstrap-state"
if [[ $NO_RESTORE -eq 1 ]]; then
  echo "  Skipped (--no-restore). State file (if any) preserved at $STATE_FILE."
elif [[ ! -s "$STATE_FILE" ]]; then
  echo "  ✓ No state file — nothing to restore"
else
  echo "  Restoring builders from $STATE_FILE:"
  declare -a restored=()
  while IFS='|' read -r port cwd started; do
    [[ -z "$port" || -z "$cwd" ]] && continue
    if [[ ! -d "$cwd" ]]; then
      echo "    ⚠ port=$port cwd=$cwd no longer exists — skipping"
      continue
    fi
    # Skip if a builder is already on that port
    if ss -tlnp 2>/dev/null | grep -q ":$port "; then
      echo "    ✓ port=$port already has a listener — skipping restart"
      restored+=("$port")
      continue
    fi
    echo "    Starting builder on port $port (cwd=$cwd)..."
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "      [dry-run] would run: (cd $cwd && nohup builder start --port $port > /tmp/builder-restored-$port.log 2>&1 &)"
    else
      (cd "$cwd" && nohup builder start --port "$port" > "/tmp/builder-restored-$port.log" 2>&1 &)
      restored+=("$port")
    fi
  done < "$STATE_FILE"
  if [[ ${#restored[@]} -gt 0 && $DRY_RUN -eq 0 ]]; then
    sleep 5
    echo "  Waiting for restored builders to come up..."
    for port in "${restored[@]}"; do
      if curl -sS -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:$port/api/dashboard/board" | grep -qE "^(200|301|302)"; then
        echo "    ✓ port=$port reachable"
      else
        echo "    ⚠ port=$port not yet responding — check /tmp/builder-restored-$port.log"
      fi
    done
    rm -f "$STATE_FILE"
    echo "  Cleared $STATE_FILE"
  fi
fi

echo ""
echo "Done. Next session: run preflight before starting."
echo "  python3 .claude/skills/autoresearch/scripts/preflight.py --recipe 1"
