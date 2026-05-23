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
#   bash .claude/skills/autoresearch/scripts/bootstrap.sh --skip-jaeger   # don't try to start Jaeger
#   bash .claude/skills/autoresearch/scripts/bootstrap.sh --auto-free-ports # stop conflicting builders without prompting
#   bash .claude/skills/autoresearch/scripts/bootstrap.sh --dry-run       # report what would happen

set -euo pipefail

SKIP_SEED=0
SKIP_JAEGER=0
DRY_RUN=0
AUTO_FREE_PORTS=0
for arg in "$@"; do
  case "$arg" in
    --skip-seed)        SKIP_SEED=1 ;;
    --skip-jaeger)      SKIP_JAEGER=1 ;;
    --auto-free-ports)  AUTO_FREE_PORTS=1 ;;
    --dry-run)          DRY_RUN=1 ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# Ports the autoresearch loop needs free at start. :4317/:4318 are OTLP
# (Jaeger receivers); :16686 is Jaeger UI. :9876-9880 are reserved for the
# baseline.py port range. Any running `builder` instance bound to these is
# preserved by default and offered for shutdown; --auto-free-ports stops
# them without prompting.
OTEL_PORTS=(4317 4318 16686)
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
    if c['name'].startswith(('requests', 'tiktoken')) and c['status'] != 'pass':
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
  echo "  ✓ requests + tiktoken already installed"
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

# ----- Step 4a: resolve OTEL port conflicts -----
echo ""
echo "▸ Step 4a — OTEL port conflict check (4317/4318/16686 + builder range)..."
# Discover any process holding the ports we need. `ss -tlnp` shows PID + cmd.
# We're specifically looking for `builder` processes — those use the same OTEL
# port (4318) as Jaeger, so they collide. External listeners (e.g., a vendor
# observability agent) are surfaced but not touched.
declare -a HELD_PORTS=()
declare -A HELD_PID_BY_PORT=()
declare -A HELD_CMD_BY_PORT=()
for port in "${OTEL_PORTS[@]}"; do
  line=$(ss -tlnp 2>/dev/null | awk -v p=":$port" '$0 ~ p {print; exit}')
  if [[ -z "$line" ]]; then continue; fi
  # ss output ends with users:(("name",pid=N,fd=K))
  pid=$(echo "$line" | grep -oP 'pid=\K[0-9]+' | head -1)
  cmd=$(echo "$line" | grep -oP 'users:\(\("\K[^"]+' | head -1)
  HELD_PORTS+=("$port")
  HELD_PID_BY_PORT[$port]=$pid
  HELD_CMD_BY_PORT[$port]=$cmd
done

if [[ ${#HELD_PORTS[@]} -eq 0 ]]; then
  echo "  ✓ All OTEL ports free"
else
  echo "  ${#HELD_PORTS[@]} OTEL port(s) held:"
  for port in "${HELD_PORTS[@]}"; do
    echo "    :$port → pid=${HELD_PID_BY_PORT[$port]} cmd=${HELD_CMD_BY_PORT[$port]}"
  done
  # Distinguish builder processes (safe to stop via builder server stop) from
  # other listeners (require operator decision).
  builder_pids_to_stop=()
  external_listeners=()
  for port in "${HELD_PORTS[@]}"; do
    cmd="${HELD_CMD_BY_PORT[$port]}"
    pid="${HELD_PID_BY_PORT[$port]}"
    if [[ "$cmd" == "builder" ]]; then
      # Find the --port flag from the process's cmdline to call builder server stop
      builder_port=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | grep -oP -- '--port \K[0-9]+' | head -1)
      if [[ -n "$builder_port" ]]; then
        builder_pids_to_stop+=("$builder_port:$pid")
      else
        builder_pids_to_stop+=("?:$pid")
      fi
    else
      external_listeners+=(":$port (pid=$pid cmd=$cmd)")
    fi
  done

  # External listeners — surface only, never stop.
  if [[ ${#external_listeners[@]} -gt 0 ]]; then
    echo "  ⚠ External listeners detected (NOT auto-stopped):"
    for x in "${external_listeners[@]}"; do echo "      $x"; done
    echo "    Stop them manually before running the loop, or skip Jaeger with --skip-jaeger."
  fi

  # Builder listeners — stop them (with prompt unless --auto-free-ports).
  if [[ ${#builder_pids_to_stop[@]} -gt 0 ]]; then
    echo "  Builder process(es) holding OTEL ports:"
    declare -A seen_pid=()
    for entry in "${builder_pids_to_stop[@]}"; do
      port="${entry%%:*}"
      pid="${entry##*:}"
      if [[ -n "${seen_pid[$pid]:-}" ]]; then continue; fi
      seen_pid[$pid]=1
      echo "      port=$port pid=$pid"
    done
    if [[ $AUTO_FREE_PORTS -eq 1 ]]; then
      proceed="y"
    elif [[ $DRY_RUN -eq 1 ]]; then
      proceed="n"
      echo "    [dry-run] would prompt to stop them"
    else
      echo -n "  Stop these builder(s) so Jaeger can bind :4318? [y/N] "
      read -r proceed
    fi
    if [[ "${proceed,,}" == "y" || "${proceed,,}" == "yes" ]]; then
      declare -A seen_stopped=()
      # Record what we stopped so teardown.sh can offer to restart them later.
      # State file format: one line per stopped builder, "port|cwd|started_at".
      STATE_FILE="$REPO/.autoresearch-bootstrap-state"
      [[ $DRY_RUN -eq 0 ]] && : > "$STATE_FILE"
      for entry in "${builder_pids_to_stop[@]}"; do
        port="${entry%%:*}"
        pid="${entry##*:}"
        if [[ -n "${seen_stopped[$pid]:-}" ]]; then continue; fi
        seen_stopped[$pid]=1
        if [[ "$port" != "?" ]]; then
          # Capture cwd before stopping so teardown can `cd` back into it
          cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null || echo "")
          started=$(stat -c %Y "/proc/$pid" 2>/dev/null || date +%s)
          echo "    Stopping builder on port $port (pid $pid, cwd=$cwd)..."
          run bash -c "builder server stop --port $port --json 2>&1 | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"      stopped:\", d.get(\"stopped_pids\", d.get(\"status\")))'" || true
          [[ $DRY_RUN -eq 0 && -n "$cwd" ]] && echo "$port|$cwd|$started" >> "$STATE_FILE"
        else
          echo "    ⚠ Could not determine --port for pid=$pid; sending TERM directly"
          run kill -TERM "$pid" || true
        fi
      done
      run sleep 3
      [[ $DRY_RUN -eq 0 && -s "$STATE_FILE" ]] && echo "    Recorded stopped builders to $STATE_FILE for teardown restore"
    else
      echo "  Skipping port-free step. Jaeger will fail to bind :4318 — pass --skip-jaeger or use --auto-free-ports next time."
    fi
  fi
fi

# ----- Step 4b: Jaeger (optional) -----
echo ""
echo "▸ Step 4b — Jaeger OTEL collector (optional)..."
if [[ $SKIP_JAEGER -eq 1 ]]; then
  echo "  Skipped (--skip-jaeger). Path A file-OTEL still works."
elif ! command -v docker >/dev/null 2>&1; then
  echo "  ⚠ docker not on PATH — skipping Jaeger. Path A file-OTEL still works."
  echo "    To install docker on WSL2 Ubuntu (one-time, requires sudo):"
  echo "      curl -fsSL https://get.docker.com | sh"
  echo "      sudo usermod -aG docker \$USER"
  echo "      sudo service docker start    # or: systemctl --user start docker"
  echo "      newgrp docker                # re-login or new shell to pick up group"
  echo "    Then re-run this bootstrap."
elif ! docker info >/dev/null 2>&1; then
  echo "  ⚠ docker binary present but daemon unreachable."
  # Distinguish "daemon stopped" from "no group access" — different remedies.
  if docker info 2>&1 | grep -qiE "permission denied|cannot connect.*socket"; then
    echo "    Looks like socket permission denied. Fix once:"
    echo "      sudo usermod -aG docker \$USER && sudo chmod 666 /var/run/docker.sock"
    echo "    Then restart this shell or re-run bootstrap."
  else
    echo "    Daemon appears stopped. Try one of:"
    echo "      sudo service docker start      # SysV / WSL2"
    echo "      sudo systemctl start docker    # systemd"
  fi
  echo "    Path A file-OTEL still works without Jaeger if you want to skip."
else
  COMPOSE="$REPO/scripts/autoresearch/docker-compose.yml"
  RUNNING=$(docker ps --filter "name=autoresearch-jaeger" --format "{{.Names}}" 2>/dev/null || true)
  if [[ -n "$RUNNING" ]]; then
    echo "  ✓ Jaeger container already running"
  elif [[ ! -f "$COMPOSE" ]]; then
    echo "  ✗ docker-compose.yml not found at $COMPOSE"
  else
    # Pre-pull the image with explicit error reporting. The compose file pins a
    # specific tag — if Docker Hub returns 404, fail loudly with a clear
    # message instead of letting docker compose up exit with a generic error.
    IMAGE=$(grep -E "^\s*image:" "$COMPOSE" | head -1 | awk '{print $2}' | tr -d '"')
    if [[ -n "$IMAGE" ]]; then
      echo "  Pulling $IMAGE..."
      if [[ $DRY_RUN -eq 1 ]]; then
        echo "    [dry-run] would run: docker pull $IMAGE"
      elif ! docker pull "$IMAGE" 2>&1 | tail -3; then
        echo "  ✗ Image pull failed for $IMAGE"
        echo "    The tag may have been removed from Docker Hub. Check:"
        echo "      curl -s 'https://hub.docker.com/v2/repositories/jaegertracing/all-in-one/tags?page_size=5' | python3 -m json.tool"
        echo "    Update the image: tag in $COMPOSE and re-run bootstrap."
        echo "    Continuing without Jaeger — Path A file-OTEL still works."
        JAEGER_FAILED=1
      fi
    fi

    if [[ -z "${JAEGER_FAILED:-}" ]]; then
      EXISTS=$(docker ps -a --filter "name=autoresearch-jaeger" --format "{{.Names}}" 2>/dev/null || true)
      if [[ -n "$EXISTS" ]]; then
        echo "  Container exists but stopped — restarting..."
        run docker start autoresearch-jaeger
      else
        echo "  Starting Jaeger via docker compose..."
        if [[ $DRY_RUN -eq 1 ]]; then
          echo "    [dry-run] would run: docker compose -f $COMPOSE up -d"
        elif ! docker compose -f "$COMPOSE" up -d 2>&1 | tail -3; then
          echo "  ✗ docker compose up failed. Common causes on WSL2:"
          echo "    - Bridge networking issues — the compose file uses network_mode: host"
          echo "    - Port collision (something else on :16686 / :4318 / :4317)"
          echo "    Check: ss -tlnp | grep -E ':16686|:4318|:4317'"
          JAEGER_FAILED=1
        fi
      fi
    fi
  fi

  # Health check — Jaeger UI on :16686, OTLP HTTP on :4318
  if [[ $DRY_RUN -eq 0 ]]; then
    echo "  Waiting up to 30s for Jaeger to become reachable..."
    deadline=$((SECONDS + 30))
    while (( SECONDS < deadline )); do
      if curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:16686 2>/dev/null | grep -qE "^(200|302)$"; then
        echo "  ✓ Jaeger UI reachable at http://127.0.0.1:16686"
        # Also confirm OTLP HTTP receiver
        if curl -sS -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:4318/v1/traces 2>/dev/null | grep -qE "^(200|400|415)$"; then
          echo "  ✓ OTLP HTTP receiver reachable at http://127.0.0.1:4318"
        else
          echo "  ⚠ OTLP HTTP receiver not responding — telemetry won't reach Jaeger"
        fi
        break
      fi
      sleep 2
    done
    if (( SECONDS >= deadline )); then
      echo "  ⚠ Jaeger did not respond within 30s"
      echo "    Check container logs: docker logs autoresearch-jaeger"
    fi
  fi
fi

# ----- Step 5: re-run preflight and report -----
echo ""
echo "▸ Step 5/5 — Re-running preflight to verify..."
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
