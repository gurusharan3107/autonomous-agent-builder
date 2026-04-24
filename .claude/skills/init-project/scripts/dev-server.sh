#!/usr/bin/env bash
# Start the dev environment — install deps + launch server.
#
# CUSTOMIZE per project: replace commands below during /init-project or /implementation.
set -e

echo "=== Installing dependencies ==="
# CUSTOMIZE: install command
pip install -e ".[dev]"

echo ""
echo "=== Starting server ==="
# CUSTOMIZE: server start command
python -m autonomous_agent_builder
