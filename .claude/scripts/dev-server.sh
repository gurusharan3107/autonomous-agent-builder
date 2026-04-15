#!/usr/bin/env bash
# Start dev environment for autonomous-agent-builder.
# Backend: FastAPI on port 8000. Frontend: Vite on port 5173.
set -e

echo "=== Installing Python dependencies ==="
pip install -e ".[dev]"

echo ""
echo "=== Starting backend (port 8000) ==="
python -m autonomous_agent_builder
