#!/usr/bin/env python3
"""Drift check for docs/goal/STATUS.md vs reality.

Read-only. Emits JSON findings; consumed by .claude/skills/start/ Step 2.

Each finding: {severity: 'hard' | 'soft', field: str, claim: str, evidence: str}

Exit 0 if no hard findings (clean or soft-only); 1 if any hard finding.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
STATUS = REPO_ROOT / "docs" / "goal" / "STATUS.md"
INSIGHTS = REPO_ROOT / "docs" / "goal" / "INSIGHTS.md"


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def parse_current_position(status_text: str) -> dict:
    """Extract Current Position table fields from STATUS.md."""
    out: dict[str, str] = {}
    section = re.search(r"## Current Position(.*?)(?=^## )", status_text, flags=re.S | re.M)
    if not section:
        return out
    for row in re.findall(r"^\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|$", section.group(1), flags=re.M):
        key, value = row[0].strip(), row[1].strip()
        if key == "Current Milestone":
            out["milestone"] = value
        elif key == "Current Item In Flight":
            out["item_in_flight"] = value
        elif key == "Active Workspace":
            out["active_workspace"] = value.strip("` ")
        elif key == "Last Update":
            out["last_update"] = value
    return out


def parse_last_insight_verdict(insights_text: str) -> str | None:
    """Find the most-recent Run entry's alignment verdict."""
    headers = re.findall(r"^## (\d{4}-\d{2}-\d{2}) — Run", insights_text, flags=re.M)
    if not headers:
        return None
    # The first occurrence is the topmost entry; INSIGHTS has newest-first in current convention,
    # but historic compression puts the table at the top. Find the first ## Run header AFTER ## Entries.
    # Heuristic: take the section starting with the first matched header.
    first_date = headers[0]
    pattern = rf"## {re.escape(first_date)} — Run.*?(?=\n## |\Z)"
    section_match = re.search(pattern, insights_text, flags=re.S)
    if not section_match:
        return None
    verdict = re.search(r"\*\*Alignment verdict:\*\*\s*([A-Za-z]+)", section_match.group(0))
    return verdict.group(1) if verdict else None


def git_log_recent(days: int) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"--since={days} days ago", "-30"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return [line for line in result.stdout.splitlines() if line.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Drift check for STATUS.md vs reality.")
    parser.add_argument("--json", action="store_true", help="emit JSON findings")
    args = parser.parse_args()

    findings: list[dict[str, str]] = []

    status_text = read(STATUS)
    if not status_text:
        findings.append({
            "severity": "hard",
            "field": "STATUS.md",
            "claim": "exists",
            "evidence": f"file not found at {STATUS}",
        })
        emit(findings, args.json)
        return 1

    cp = parse_current_position(status_text)
    item = cp.get("item_in_flight", "")
    last_update = cp.get("last_update", "")
    workspace = cp.get("active_workspace", "")

    # Check 1 — Active Workspace path exists on disk
    if workspace and not Path(workspace).exists():
        findings.append({
            "severity": "soft",
            "field": "Active Workspace",
            "claim": workspace,
            "evidence": "path does not exist on disk",
        })

    # Check 2 — Last Update date is no more than 7 days old
    today = datetime.now(timezone.utc).date()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", last_update)
    if m:
        try:
            d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            age = (today - d).days
            if age > 7:
                findings.append({
                    "severity": "soft",
                    "field": "Last Update",
                    "claim": last_update[:60],
                    "evidence": f"{age} days old — STATUS may not reflect recent commits",
                })
        except ValueError:
            pass

    # Check 3 — Current Item In Flight names a milestone (e.g. "M1.4"); is it referenced in recent commits?
    milestone_match = re.search(r"M\d+(?:\.\d+)?", item)
    if milestone_match:
        ms = milestone_match.group(0)
        commits = git_log_recent(7)
        if commits and not any(ms in c for c in commits):
            findings.append({
                "severity": "soft",
                "field": "Current Item In Flight",
                "claim": item[:80],
                "evidence": f"no commit mentions {ms} in last 7d (commits exist but reference other work)",
            })

    # Check 4 — Most-recent INSIGHTS verdict is not 'drifting' / 'ambiguous'
    insights_text = read(INSIGHTS)
    verdict = parse_last_insight_verdict(insights_text)
    if verdict:
        normalized = verdict.lower()
        if normalized == "drifting":
            findings.append({
                "severity": "hard",
                "field": "INSIGHTS alignment verdict",
                "claim": verdict,
                "evidence": "most-recent goal-audit run reports STATUS-vs-intent drift",
            })
        elif normalized == "ambiguous":
            findings.append({
                "severity": "soft",
                "field": "INSIGHTS alignment verdict",
                "claim": verdict,
                "evidence": "most-recent goal-audit run could not resolve alignment",
            })

    emit(findings, args.json)
    return 1 if any(f["severity"] == "hard" for f in findings) else 0


def emit(findings: list[dict[str, str]], as_json: bool) -> None:
    if as_json:
        print(json.dumps({"findings": findings}, indent=2))
        return
    if not findings:
        print("No drift detected.")
        return
    for f in findings:
        print(f"[{f['severity']}] {f['field']}: {f['claim']} — {f['evidence']}")


if __name__ == "__main__":
    sys.exit(main())
