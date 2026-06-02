#!/usr/bin/env python3
"""
close_build_item.py — mark a ROADMAP.md item [x] after successful build.

Usage:
  python3 close_build_item.py --raw-line <exact_raw_line> --evidence <pointer> \
      [--note <short outcome note>] [--backend-result passed|na] [--browser-result passed|na]

  --raw-line        Exact line from ROADMAP.md (from next_build_item.py json.raw_line).
                    Used as the unique key to find and replace the line.
  --evidence        One evidence pointer: commit hash, file path, or test name.
  --note            Optional one-line outcome. Defaults to "implemented".
  --backend-result  "passed" or "na" (default: "na" — set to "passed" if tests ran)
  --browser-result  "passed" or "na" (default: "na" — set to "passed" if browser-verified)

Exit 0: line replaced.
Exit 1: line not found (already closed? wrong raw_line?).
Exit 2: usage error.
"""

import argparse
import re
import sys
from pathlib import Path

ROADMAP = Path("docs/goal/ROADMAP.md")
CLOSED_BUDGET = 160


def t_token(lane: str, result: str) -> str:
    if result == "passed":
        return f"`T:{lane}`"
    return f"`T:{lane}:na`"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw-line", required=True)
    p.add_argument("--evidence", required=True)
    p.add_argument("--note", default="implemented")
    p.add_argument("--backend-result", default="na", choices=["passed", "na"])
    p.add_argument("--browser-result", default="na", choices=["passed", "na"])
    args = p.parse_args()

    if not ROADMAP.exists():
        print(f"ERROR: {ROADMAP} not found", file=sys.stderr)
        sys.exit(2)

    text = ROADMAP.read_text()
    lines = text.splitlines(keepends=True)
    target = args.raw_line
    found = False

    for i, line in enumerate(lines):
        if line.rstrip("\n") != target:
            continue

        bold = re.search(r"\*\*([^*]+)\*\*", target)
        item_id = bold.group(1) if bold else target[6:40]

        pri = re.search(r"`P[0-3]`", target)
        pri_tok = f" {pri.group(0)}" if pri else ""

        outcome = args.note
        evidence = args.evidence
        be = t_token("backend", args.backend_result)
        br = t_token("browser", args.browser_result)

        closed = f"- [x]{pri_tok} **{item_id}** — {outcome}. `{evidence}`. {be} {br}\n"

        # Trim if over budget
        text_part = re.sub(r"`[^`]+`", "", closed).strip()
        if len(text_part) > CLOSED_BUDGET:
            outcome = outcome[:60] + "…"
            closed = f"- [x]{pri_tok} **{item_id}** — {outcome}. `{evidence}`. {be} {br}\n"

        lines[i] = closed
        found = True
        break

    if not found:
        print(f"ERROR: raw_line not found in {ROADMAP}", file=sys.stderr)
        print(f"  Looking for: {target!r}", file=sys.stderr)
        sys.exit(1)

    ROADMAP.write_text("".join(lines))
    print(f"OK: closed item in {ROADMAP}")
    sys.exit(0)


if __name__ == "__main__":
    main()
