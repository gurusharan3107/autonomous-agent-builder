#!/usr/bin/env bash
# Verification checks for autonomous-agent-builder (Python/FastAPI).
# Runs in order, stops at first failure. Exit 0 = all pass.
set -e

echo "=== Lint ==="
ruff check .

echo ""
echo "=== Format Check ==="
ruff format --check .

echo ""
echo "=== Tests ==="
pytest

echo ""
echo "All checks passed."
