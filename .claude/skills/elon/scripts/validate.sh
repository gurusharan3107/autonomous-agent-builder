#!/usr/bin/env bash
# Self-validate this skill against agentskills.io spec + project local style.
# Single source of truth: .claude/skills/create-skill/scripts/audit.py.
# This wrapper is identical across every skill — do not customize per-skill.
#
# Usage:
#   ./scripts/validate.sh              # default audit
#   ./scripts/validate.sh --strict     # cross-runtime portability gate
#   ./scripts/validate.sh --json       # machine-readable
#
# Exit codes match audit.py: 0 clean (or soft-only), 1 hard findings, 2 IO error.

set -eu

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SKILL_NAME="$(basename "$SKILL_DIR")"

# Walk up looking for the repo root — the directory containing `.claude/`.
REPO_ROOT="$SKILL_DIR"
while [ "$REPO_ROOT" != "/" ] && [ ! -d "$REPO_ROOT/.claude" ]; do
    REPO_ROOT="$(dirname "$REPO_ROOT")"
done
# Prefer the repo-local create-skill; fall back to the global install
# (~/.claude/skills/create-skill) since create-skill migrated to global.
AUDIT="$REPO_ROOT/.claude/skills/create-skill/scripts/audit.py"
if [ ! -f "$AUDIT" ]; then
    AUDIT="$HOME/.claude/skills/create-skill/scripts/audit.py"
fi
if [ ! -f "$AUDIT" ]; then
    echo "validate.sh: could not locate create-skill audit.py" >&2
    echo "  Tried: $REPO_ROOT/.claude/skills/create-skill/ and $HOME/.claude/skills/create-skill/" >&2
    exit 2
fi

set +e
python3 "$AUDIT" "$SKILL_DIR" "$@"
EXIT=$?
set -e

if [ "$EXIT" -ne 0 ]; then
    cat >&2 <<EOF

────────────────────────────────────────────────────────────────────
Hard findings detected in skill: $SKILL_NAME

Most skill findings need editorial judgment — they are not safely
auto-fixable. To resolve them, hand this skill to the create-skill
Optimize lane:

  1. Run /create-skill and pick "Optimize" (or type "optimize $SKILL_NAME")
  2. The Optimize lane reads this audit output as input and walks you
     through the per-finding fix using:
       .claude/skills/create-skill/references/optimize.md

For per-check rationale and fix recipes:
  cat $REPO_ROOT/.claude/skills/create-skill/references/checklist.md
────────────────────────────────────────────────────────────────────
EOF
fi

exit "$EXIT"
