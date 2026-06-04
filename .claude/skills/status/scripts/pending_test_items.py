#!/usr/bin/env python3
"""
pending_test_items.py — find closed [x] ROADMAP items with pending T: tokens.

Prints a JSON array of items that still need testing. Each item includes:
  milestone        str
  id               str
  raw_line         str   (unique key for update_t_token.py)
  body             str
  backend          str   "pending" | "na" | "passed"
  browser          str   "pending" | "na" | "passed"
  linux_backend    str   "testable" | "dashboard_gated" | "na"
  linux_browser    str   "browser_testable" | "dashboard_gated" | "na"
  backend_cmd      str   command to run (empty if not testable)
  browser_cmd      str   "hermes-chrome" if browser_testable, else ""

Exit 0 + JSON array: items found.
Exit 1: no pending test items.
Exit 2: usage/parse error.

Testability rules (autonomous-agent-builder, Linux/WSL2):
  backend:
    - pytest-coverable items → testable via pytest (most src/ changes)
    - builder CLI items → testable via builder CLI
    - pure frontend/CSS/HTML → na (no backend test surface)
    - live-dispatch/operator-session required → dashboard_gated
  browser:
    - UI / dashboard / board / backlog / widget items → browser_testable (hermes-chrome)
    - pure backend/CLI/docs → na
    - live app workspace required → dashboard_gated
"""

import json
import re
import sys
from pathlib import Path

ROADMAP = Path("docs/goal/ROADMAP.md")

# Signals → backend test is not directly runnable (needs live app)
DASHBOARD_GATED_BACKEND = [
    "ship one feature",
    "run one sprint",
    "operator drives",
    "forward-engineering on fresh workspace",
    "reverse-engineering",
    "both lanes ship",
    "devpulse e2e",
]

# Signals → item has pytest coverage (can run pytest directly)
PYTEST_SIGNALS = [
    "test_",
    "pytest",
    "fix",
    "cache_ratio",
    "schema",
    "mcp tool",
    "tool-call",
    "retain",
    "resolution",
    "classify",
    "intent",
    "phase planner",
    "task count",
    "proposed_tasks",
    "cost",
    "token",
    "cache",
    "ratio",
    "permission_mode",
    "can_use_tool",
]

# Signals → browser-testable via hermes-chrome
BROWSER_SIGNALS = [
    "dashboard",
    "board",
    "backlog",
    "frontend",
    "ui",
    "widget",
    "overlay",
    "tasklist",
    "sprint",
    "render",
    "react",
    "tsx",
    "sidebar",
    "trace",
    "clickable",
    "visible",
    "button",
]

# Signals → browser test needs live running app (beyond what hermes-chrome alone can do)
DASHBOARD_GATED_BROWSER = [
    "live run",
    "live dispatch",
    "operator session",
    "real sprint",
    "actual feature",
    "e2e feature",
    "devpulse sprint",
]


def parse_t_token(line: str, lane: str) -> str:
    m = re.search(rf"`T:{lane}(:([^`]+))?`", line)
    if not m:
        return "unknown"
    suffix = m.group(2)
    if suffix == "pending":
        return "pending"
    if suffix == "na":
        return "na"
    return "passed"


def classify_backend(body_lower: str) -> tuple[str, str]:
    if any(s in body_lower for s in DASHBOARD_GATED_BACKEND):
        return "dashboard_gated", ""
    # Check for pytest-coverable patterns
    if any(s in body_lower for s in PYTEST_SIGNALS):
        return "testable", "python3 -m pytest tests/ -x -q 2>&1 | tail -20"
    # Default: try pytest anyway (most items have backend coverage)
    return "testable", "python3 -m pytest tests/ -x -q 2>&1 | tail -20"


def classify_browser(body_lower: str) -> tuple[str, str]:
    if any(s in body_lower for s in DASHBOARD_GATED_BROWSER):
        return "dashboard_gated", ""
    if any(s in body_lower for s in BROWSER_SIGNALS):
        return "browser_testable", "hermes-chrome"
    return "na", ""


def main():
    milestone_filter = sys.argv[1] if len(sys.argv) > 1 else None

    if not ROADMAP.exists():
        print(f"ERROR: {ROADMAP} not found", file=sys.stderr)
        sys.exit(2)

    text = ROADMAP.read_text()
    results = []
    current_milestone = ""

    for line in text.splitlines():
        ms_match = re.match(r"^### (M[\d.]+)", line)
        if ms_match:
            current_milestone = ms_match.group(1)
            continue

        # Closed items only
        if not re.match(r"^- \[x\]", line):
            continue

        if milestone_filter and current_milestone != milestone_filter:
            continue

        backend = parse_t_token(line, "backend")
        browser = parse_t_token(line, "browser")

        if backend not in ("pending",) and browser not in ("pending",):
            continue

        body = re.sub(r"^- \[x\]\s*", "", line)
        body = re.sub(r"`P[0-3]`\s*", "", body)
        body = re.sub(r"`T:[^`]+`", "", body)
        body = body.strip()

        bold = re.search(r"\*\*([^*]+)\*\*", body)
        item_id = (
            re.sub(r"[^a-z0-9]+", "-", bold.group(1).lower()).strip("-") if bold else body[:30]
        )

        body_lower = body.lower()
        linux_backend, backend_cmd = classify_backend(body_lower)
        linux_browser, browser_cmd = classify_browser(body_lower)

        results.append(
            {
                "milestone": current_milestone,
                "id": item_id,
                "raw_line": line,
                "body": body,
                "backend": backend,
                "browser": browser,
                "linux_backend": linux_backend,
                "linux_browser": linux_browser,
                "backend_cmd": backend_cmd if backend == "pending" else "",
                "browser_cmd": browser_cmd if browser == "pending" else "",
            }
        )

    if not results:
        print(json.dumps([]))
        sys.exit(1)

    print(json.dumps(results, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
