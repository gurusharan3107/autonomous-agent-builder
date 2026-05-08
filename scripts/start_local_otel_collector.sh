#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${AAB_OTEL_COLLECTOR_CONFIG:-$ROOT_DIR/docker/otel-collector-local.yaml}"
CONFIG_DIR="$(cd "$(dirname "$CONFIG_PATH")" && pwd)"
CONFIG_FILE="$(basename "$CONFIG_PATH")"
NAME="${AAB_OTEL_COLLECTOR_NAME:-aab-otel-collector}"
IMAGE="${AAB_OTEL_COLLECTOR_IMAGE:-ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector:0.150.1}"
MEMORY="${AAB_OTEL_COLLECTOR_MEMORY:-128M}"
CPUS="${AAB_OTEL_COLLECTOR_CPUS:-1}"
PORT="${AAB_OTEL_COLLECTOR_PORT:-4318}"
HOST_IP="${AAB_OTEL_COLLECTOR_HOST_IP:-127.0.0.1}"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "missing config: $CONFIG_PATH" >&2
  exit 1
fi

runtime=""
if command -v container >/dev/null 2>&1 && container system status >/dev/null 2>&1; then
  runtime="container"
elif command -v docker >/dev/null 2>&1; then
  runtime="docker"
elif command -v podman >/dev/null 2>&1; then
  runtime="podman"
else
  echo "missing container runtime: install Apple container, Docker, or Podman" >&2
  exit 1
fi

case "$runtime" in
  container)
    container stop "$NAME" >/dev/null 2>&1 || true
    container delete --force "$NAME" >/dev/null 2>&1 || true
    container run \
      --name "$NAME" \
      --detach \
      --memory "$MEMORY" \
      --cpus "$CPUS" \
      --publish "$HOST_IP:$PORT:4318" \
      --mount "type=bind,source=$CONFIG_DIR,target=/etc/otelcol,readonly" \
      "$IMAGE" \
      --config="/etc/otelcol/$CONFIG_FILE"
    ;;
  docker|podman)
    "$runtime" rm -f "$NAME" >/dev/null 2>&1 || true
    "$runtime" run \
      --name "$NAME" \
      --detach \
      --memory "$MEMORY" \
      --cpus "$CPUS" \
      --publish "$HOST_IP:$PORT:4318" \
      --volume "$CONFIG_PATH:/etc/otelcol/config.yaml:ro" \
      "$IMAGE" \
      --config=/etc/otelcol/config.yaml
    ;;
esac

for _ in {1..30}; do
  if nc -z "$HOST_IP" "$PORT" >/dev/null 2>&1; then
    echo "ok runtime=$runtime name=$NAME endpoint=http://$HOST_IP:$PORT memory=$MEMORY cpus=$CPUS"
    exit 0
  fi
  sleep 1
done

echo "collector started with $runtime, but http://$HOST_IP:$PORT did not become reachable within 30s" >&2
exit 2
