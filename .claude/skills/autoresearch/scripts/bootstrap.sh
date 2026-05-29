#!/usr/bin/env bash
# Autoresearch loop bootstrap — bundled with the autoresearch skill.
#
# One-shot setup: reads preflight.py output and attempts to fix every
# auto-fixable failure. Items requiring root / docker install / port frees
# are surfaced as manual steps with the exact command to run.
#
# Idempotent — safe to re-run. Won't overwrite an existing seed snapshot
# (use setup_seed.sh directly to re-capture).
#
# Usage:
#   bash .claude/skills/autoresearch/scripts/bootstrap.sh                 # auto-fix everything possible
#   bash .claude/skills/autoresearch/scripts/bootstrap.sh --skip-seed     # don't capture .seed/devpulse
#   bash .claude/skills/autoresearch/scripts/bootstrap.sh --auto-free-ports # stop conflicting builders without prompting
#   bash .claude/skills/autoresearch/scripts/bootstrap.sh --dry-run       # report what would happen

set -euo pipefail

SKIP_SEED=0
DRY_RUN=0
AUTO_FREE_PORTS=0
for arg in "$@"; do
  case "$arg" in
    --skip-seed)        SKIP_SEED=1 ;;
    --auto-free-ports)  AUTO_FREE_PORTS=1 ;;
    --dry-run)          DRY_RUN=1 ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

BUILDER_PORTS=(9876 9877 9878 9879 9880)

# Derive repo root from this script's location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
PREFLIGHT="$SCRIPT_DIR/preflight.py"

if [[ ! -f "$PREFLIGHT" ]]; then
  echo "ERROR: preflight.py not found at $PREFLIGHT" >&2
  exit 1
fi

run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "  [dry-run] would run: $*"
  else
    "$@"
  fi
}

echo "═══════════════════════════════════════════════════════════════════════"
echo "Autoresearch bootstrap"
echo "  Repo:    $REPO"
echo "  Mode:    $([[ $DRY_RUN -eq 1 ]] && echo dry-run || echo execute)"
echo "═══════════════════════════════════════════════════════════════════════"

# ----- Step 1: read current preflight state -----
echo ""
echo "▸ Step 1/5 — Reading preflight state..."
PREFLIGHT_JSON="$(python3 "$PREFLIGHT" --json || true)"
if ! echo "$PREFLIGHT_JSON" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
  echo "ERROR: preflight.py did not emit valid JSON" >&2
  echo "$PREFLIGHT_JSON" >&2
  exit 1
fi

failed_hard=$(echo "$PREFLIGHT_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for c in d['hard']:
    if c['status'] == 'fail':
        print(c['name'])
")
if [[ -n "$failed_hard" ]]; then
  echo "  Hard failures detected:"
  echo "$failed_hard" | sed 's/^/    - /'
fi

# ----- Step 2: install Python deps if missing -----
echo ""
echo "▸ Step 2/5 — Python dependencies..."
need_requests=$(echo "$PREFLIGHT_JSON" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for c in d['hard'] + d['soft']:
    if c['name'].startswith(('requests', 'tiktoken', 'py-spy')) and c['status'] != 'pass':
        print(c['name'].split()[0])
")
if [[ -n "$need_requests" ]]; then
  # On Ubuntu 24.04+ / Debian 12+, system Python is PEP 668 externally-managed.
  # Try plain --user first; on failure fall back to --break-system-packages
  # (safe for --user site-packages; doesn't touch system-managed paths).
  for pkg in $need_requests; do
    echo "  Installing $pkg..."
    if [[ $DRY_RUN -eq 1 ]]; then
      echo "  [dry-run] would run: python3 -m pip install --user $pkg (with PEP668 fallback)"
    else
      if ! python3 -m pip install --user "$pkg" 2>/tmp/pip-install.err; then
        if grep -q "externally-managed-environment" /tmp/pip-install.err; then
          echo "  PEP 668 detected — retrying with --break-system-packages"
          python3 -m pip install --user --break-system-packages "$pkg" || {
            echo "  ⚠ pip install failed for $pkg"
            cat /tmp/pip-install.err
          }
        else
          echo "  ⚠ pip install failed for $pkg"
          cat /tmp/pip-install.err
        fi
      fi
      rm -f /tmp/pip-install.err
    fi
  done
else
  echo "  ✓ requests + tiktoken + py-spy already installed"
fi

# ----- Step 3: seed snapshot -----
echo ""
echo "▸ Step 3/5 — Seed snapshot..."
SEED_DST="/home/gurusharangupta/.seed/devpulse"
if [[ $SKIP_SEED -eq 1 ]]; then
  echo "  Skipped (--skip-seed)"
elif [[ -d "$SEED_DST" ]]; then
  echo "  ✓ Seed already exists at $SEED_DST (re-snapshot via scripts/autoresearch/setup_seed.sh)"
else
  if [[ ! -x "$REPO/scripts/autoresearch/setup_seed.sh" ]]; then
    echo "  ✗ setup_seed.sh not executable at $REPO/scripts/autoresearch/setup_seed.sh"
  else
    echo "  Capturing seed via scripts/autoresearch/setup_seed.sh..."
    run bash "$REPO/scripts/autoresearch/setup_seed.sh"
  fi
fi

# ----- Step 5: re-run preflight and report -----
echo ""
echo "▸ Step 4/4 — Re-running preflight to verify..."
if [[ $DRY_RUN -eq 1 ]]; then
  echo "  [dry-run] skipping final preflight"
else
  python3 "$PREFLIGHT"
fi

# ----- Manual steps that bootstrap can't handle -----
echo ""
echo "═══════════════════════════════════════════════════════════════════════"
echo "Manual steps (bootstrap can't auto-fix these):"
echo "═══════════════════════════════════════════════════════════════════════"

if [[ $DRY_RUN -eq 0 ]]; then
  POST="$(python3 "$PREFLIGHT" --json || true)"
  remaining=$(echo "$POST" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for c in d['hard'] + d['soft']:
    if c['status'] in ('fail', 'warn') and c['fix']:
        print(f\"  [{c['status']}] {c['name']}: {c['fix']}\")
" || true)
  if [[ -n "$remaining" ]]; then
    echo "$remaining"
  else
    echo "  (none — fully bootstrapped)"
  fi
fi

echo ""
echo "Next step: run a recipe per SKILL.md, e.g.:"
echo "  python3 .claude/skills/autoresearch/scripts/preflight.py --recipe 1 --json"
echo "  python3 scripts/autoresearch/baseline.py --fixtures A,B,C,D,E --n 5 \\"
echo "      --evidence-root /tmp/autoresearch/baseline-\$(date +%Y-%m-%d)"
