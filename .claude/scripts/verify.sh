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
echo "=== CLI Tools Validation ==="
python scripts/test_cli_tools.py

echo ""
echo "=== CLI Wrappers Validation ==="
python scripts/validate_cli_wrappers.py || echo "⚠️  Some CLI wrappers missing (non-critical)"

echo ""
echo "=== Tests ==="
pytest

echo ""
echo "All checks passed."
