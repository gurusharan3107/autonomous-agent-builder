#!/usr/bin/env python3
"""
update_t_token.py — upgrade a T:lane token on a ROADMAP.md line.

Usage:
  python3 update_t_token.py --raw-line <exact_line> --lane backend|browser \
      --result passed|pending|na [--note <short failure note>]

  --raw-line   Exact original line (from pending_test_items.py json.raw_line).
  --lane       "backend" or "browser"
  --result     "passed" → bare token; "pending" → :pending; "na" → :na
  --note       Optional note appended to line when result=pending (failure reason).

Idempotent: if the token already matches the target state, exits 0 without writing.
Exit 0: updated (or already correct).
Exit 1: raw_line not found.
Exit 2: usage error.
"""

import argparse
import re
import sys
from pathlib import Path

ROADMAP = Path("docs/goal/ROADMAP.md")


def token_for(lane: str, result: str) -> str:
    if result == "passed":
        return f"`T:{lane}`"
    elif result == "na":
        return f"`T:{lane}:na`"
    else:
        return f"`T:{lane}:pending`"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw-line", required=True)
    p.add_argument("--lane", required=True, choices=["backend", "browser"])
    p.add_argument("--result", required=True, choices=["passed", "pending", "na"])
    p.add_argument("--note", default="")
    args = p.parse_args()

    if not ROADMAP.exists():
        print(f"ERROR: {ROADMAP} not found", file=sys.stderr)
        sys.exit(2)

    text = ROADMAP.read_text()
    lines = text.splitlines(keepends=True)
    target = args.raw_line
    new_token = token_for(args.lane, args.result)

    for i, line in enumerate(lines):
        if line.rstrip("\n") != target:
            continue

        pattern = rf"`T:{args.lane}(:[^`]+)?`"
        existing = re.search(pattern, line)

        if existing and existing.group(0) == new_token:
            print(f"OK: already {new_token} — no change")
            sys.exit(0)

        if existing:
            new_line = line[:existing.start()] + new_token + line[existing.end():]
        else:
            new_line = line.rstrip("\n") + f" {new_token}\n"

        if args.result == "pending" and args.note:
            note_tag = f"<!-- test-note: {args.note} -->"
            if note_tag not in new_line:
                new_line = new_line.rstrip("\n") + f" {note_tag}\n"

        lines[i] = new_line
        ROADMAP.write_text("".join(lines))
        print(f"OK: updated T:{args.lane} → {new_token}")
        sys.exit(0)

    print(f"ERROR: raw_line not found in {ROADMAP}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
