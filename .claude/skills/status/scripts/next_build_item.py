#!/usr/bin/env python3
"""
next_build_item.py — find the next unchecked ROADMAP item for /status build.

Exit 0: prints JSON with the next item.
Exit 1: no remaining items (all done or milestone complete).
Exit 2: usage/parse error.

JSON fields:
  milestone         str   e.g. "M1.1"
  id                str   normalised id slug (first bold token or first 6 words)
  raw_line          str   full original checkbox line
  body              str   item text without checkbox/priority/test tokens
  priority          str   "P0"–"P3" or ""
  dashboard_gated   bool  requires live builder dashboard / running app to implement
  dashboard_reason  str   if dashboard_gated, why
  if_flag           bool  item already marked `IF` (in-flight)
"""

import json
import re
import sys
from pathlib import Path

ROADMAP = Path("docs/goal/ROADMAP.md")

# Signals → dashboard_gated (need a live running builder + operator session to implement)
DASHBOARD_GATED_SIGNALS = [
    ("ship one feature on devpulse", "requires live devpulse workspace + builder run"),
    ("forward-engineering on fresh workspace", "requires live workspace + builder dispatch"),
    ("reverse-engineering on existing workspace", "requires live workspace + builder dispatch"),
    ("both lanes ship", "requires live devpulse + codex runtime"),
    ("operator drives", "requires live operator session"),
    ("run one sprint", "requires live builder dispatch"),
]

# Signals that the item is code-only (safe to implement on Linux without dashboard)
CODE_SIGNALS = [
    "fix",
    "bug",
    "schema",
    "pytest",
    "cache_ratio",
    "ratio",
    "token",
    "frontend",
    "backend",
    "dashboard",
    "render",
    "api",
    "mcp",
    "tool",
    "observability",
    "metrics",
    "logs",
    "board",
    "backlog",
    "sprint",
    "docs",
    "adr",
    "decision",
    "test",
    "src/",
    "services/",
    "scripts/",
]


def classify(body_lower: str) -> tuple[bool, str]:
    """Return (dashboard_gated, dashboard_reason)."""
    for signal, reason in DASHBOARD_GATED_SIGNALS:
        if signal in body_lower:
            return True, reason
    return False, ""


def parse_roadmap() -> list[dict]:
    if not ROADMAP.exists():
        print(f"ERROR: {ROADMAP} not found", file=sys.stderr)
        sys.exit(2)

    text = ROADMAP.read_text()
    items = []
    current_milestone = ""

    for line in text.splitlines():
        ms_match = re.match(r"^### (M[\d.]+)", line)
        if ms_match:
            current_milestone = ms_match.group(1)
            continue

        # Open checkbox only
        if not re.match(r"^- \[ \]", line):
            continue

        # Extract priority
        pri_match = re.search(r"`(P[0-3])`", line)
        priority = pri_match.group(1) if pri_match else ""

        # In-flight flag
        if_flag = "`IF`" in line

        # Strip tokens to get readable body
        body = line
        body = re.sub(r"^- \[ \]\s*", "", body)
        body = re.sub(r"`P[0-3]`\s*", "", body)
        body = re.sub(r"`IF`\s*", "", body)
        body = re.sub(r"`T:[^`]+`", "", body)
        body = body.strip()

        # Derive id: first **bold** token, else first 5 words
        bold = re.search(r"\*\*([^*]+)\*\*", body)
        if bold:
            item_id = re.sub(r"[^a-z0-9]+", "-", bold.group(1).lower()).strip("-")
        else:
            item_id = "-".join(body.lower().split()[:5])
            item_id = re.sub(r"[^a-z0-9-]+", "", item_id)

        body_lower = body.lower()
        dashboard_gated, dashboard_reason = classify(body_lower)

        items.append(
            {
                "milestone": current_milestone,
                "id": item_id,
                "raw_line": line,
                "body": body,
                "priority": priority,
                "dashboard_gated": dashboard_gated,
                "dashboard_reason": dashboard_reason,
                "if_flag": if_flag,
            }
        )

    return items


def main():
    args = sys.argv[1:]
    skip_gated = "--skip-gated" in args
    args = [a for a in args if a != "--skip-gated"]
    milestone_filter = args[0] if args else None

    items = parse_roadmap()

    if milestone_filter:
        items = [i for i in items if i["milestone"] == milestone_filter]

    if not items:
        print(json.dumps({"done": True, "message": "No remaining open items."}))
        sys.exit(1)

    if skip_gated:
        gated = [i for i in items if i["dashboard_gated"]]
        buildable = [i for i in items if not i["dashboard_gated"]]
        for sk in gated:
            if buildable and items.index(sk) < items.index(buildable[0]):
                print(
                    json.dumps(
                        {
                            "skipped": True,
                            "id": sk["id"],
                            "dashboard_reason": sk["dashboard_reason"],
                        }
                    ),
                    file=sys.stderr,
                )
        if not buildable:
            print(
                json.dumps(
                    {
                        "done": True,
                        "message": "All remaining items are dashboard-gated.",
                        "gated": [i["id"] for i in gated],
                    }
                )
            )
            sys.exit(1)
        next_item = buildable[0]
    else:
        next_item = items[0]

    print(json.dumps(next_item, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
