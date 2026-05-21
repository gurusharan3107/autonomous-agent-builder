#!/usr/bin/env bash
# Run all verification checks in order. Stops at first failure.
# Exit 0 = all pass. Non-zero = failure.
#
# CUSTOMIZE per project: replace commands below during /init-project or /implementation.
set -e

echo "=== Lint ==="
# CUSTOMIZE: lint command
ruff check .

echo ""
echo "=== Tests ==="
# CUSTOMIZE: test command
pytest

echo ""
echo "=== Build ==="
# CUSTOMIZE: build command (comment out if not applicable)
# python -m build

echo ""
echo "All checks passed."
