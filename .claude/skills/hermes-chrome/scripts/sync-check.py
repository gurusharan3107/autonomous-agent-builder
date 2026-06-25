#!/usr/bin/env python3
"""
sync-check.py — hermes-chrome SKILL.md ↔ hermes-chrome-guide.html sync validator.

Usage (from skill directory):
    python3 scripts/sync-check.py

Exit codes:
    0 — all checks pass (files in sync)
    1 — one or more checks fail (files diverged)
"""

import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent


def _normalize(text: str) -> str:
    """Normalize a rule title for loose comparison: lowercase, strip backticks, trailing punct."""
    text = text.strip()
    text = text.replace("`", "")
    text = text.rstrip(".,:;")
    return text.lower()


def extract_skill_hard_rules(skill_md: str) -> list[str]:
    """Extract bold titles from ## Hard rules section (lines matching ^N. **<title>**).

    Returns normalized titles (lowercase, no backticks, no trailing punctuation)
    suitable for substring matching against artifact-data hard_rules entries.
    """
    # Find the ## Hard rules section
    section_match = re.search(r"^## Hard rules\s*$(.*?)^##", skill_md, re.MULTILINE | re.DOTALL)
    if not section_match:
        # Try to get to end of file if last section
        section_match = re.search(r"^## Hard rules\s*$(.*)", skill_md, re.MULTILINE | re.DOTALL)
    if not section_match:
        return []
    section = section_match.group(1)
    # Match numbered rule lines: ^N. **Title**
    raw_titles = re.findall(r"^\d+\.\s+\*\*([^*]+)\*\*", section, re.MULTILINE)
    return [_normalize(t) for t in raw_titles]


def extract_operate_dead_ends(operate_md: str) -> list[str]:
    """Extract dead-end entries from the ## bridge() section's Dead ends list.

    Parses all bullet lines (^- ) between the 'Dead ends' bold label and the
    next horizontal rule or section heading, capturing the first backtick-quoted
    command on each line as the key.
    """
    # Find the Dead ends block inside ## bridge() — inline helper
    dead_block_match = re.search(
        r"\*\*Dead ends[^*]*\*\*.*?\n((?:^- .*\n?)+)",
        operate_md,
        re.MULTILINE,
    )
    if not dead_block_match:
        return []
    block = dead_block_match.group(1)
    entries = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        # Extract the first backtick-quoted value as the key
        cmd_match = re.search(r"`([^`]+)`", line)
        if cmd_match:
            # Use the last path component for file paths, or the full command
            cmd = cmd_match.group(1)
            # Normalise: strip leading 'python3 .../' path to get the filename
            cmd = re.sub(r"^python3\s+\S*/(\S+\.(?:py|js))\s*.*$", r"\1", cmd)
            entries.append(cmd)
        else:
            # No backtick — use the whole content after '- '
            entries.append(line[2:].split(" — ")[0].strip())
    return entries


def extract_artifact_data(html: str) -> dict:
    """Parse the #artifact-data JSON script block from the HTML."""
    match = re.search(
        r'<script[^>]+id=["\']artifact-data["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        return {}
    return json.loads(match.group(1))


def count_dead_rows(html: str) -> int:
    """Count <div class="dead-row"> occurrences in the HTML."""
    return len(re.findall(r'<div\s+class=["\']dead-row["\']', html))


def count_hard_rule_qr_items(html: str) -> int:
    """Count qr-item entries inside the Hard rules sidebar card only."""
    # Find the Hard rules sidebar card
    card_match = re.search(
        r"<h3>Hard rules</h3>(.*?)</div>\s*\n\s*</div>",
        html,
        re.DOTALL,
    )
    if not card_match:
        # Fallback: find between <h3>Hard rules</h3> and the closing </div> of the card
        card_match = re.search(
            r"<h3>Hard rules</h3>(.*?)\n  </div>",
            html,
            re.DOTALL,
        )
    if not card_match:
        return 0
    card_body = card_match.group(1)
    return len(re.findall(r'<div\s+class=["\']qr-item', card_body))


def main() -> int:
    skill_md_path = SKILL_DIR / "SKILL.md"
    operate_md_path = SKILL_DIR / "references" / "operate.md"
    html_path = SKILL_DIR / "references" / "hermes-chrome-guide.html"

    # Read files
    try:
        skill_md = skill_md_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"ERROR: cannot read {skill_md_path}: {e}", file=sys.stderr)
        return 1

    try:
        operate_md = operate_md_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"ERROR: cannot read {operate_md_path}: {e}", file=sys.stderr)
        return 1

    try:
        html = html_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"ERROR: cannot read {html_path}: {e}", file=sys.stderr)
        return 1

    # Extract data
    skill_hard_rules = extract_skill_hard_rules(skill_md)
    operate_dead_ends = extract_operate_dead_ends(operate_md)
    artifact = extract_artifact_data(html)
    artifact_hard_rules = artifact.get("hard_rules", [])
    artifact_dead_ends = artifact.get("dead_ends", [])
    dead_row_count = count_dead_rows(html)
    qr_item_count = count_hard_rule_qr_items(html)

    n_skill = len(skill_hard_rules)
    n_artifact_hr = len(artifact_hard_rules)
    n_artifact_de = len(artifact_dead_ends)
    n_operate_de = len(operate_dead_ends)

    print("SYNC CHECK: hermes-chrome SKILL.md ↔ hermes-chrome-guide.html")

    # ── hard_rules check ──────────────────────────────────────────────────────
    hr_counts_match = n_skill == n_artifact_hr == qr_item_count
    artifact_hr_normalized = [_normalize(e) for e in artifact_hard_rules]
    hr_missing = [
        title
        for title in skill_hard_rules
        if not any(title in entry or entry in title for entry in artifact_hr_normalized)
    ]
    hr_pass = hr_counts_match and not hr_missing
    hr_status = "PASS" if hr_pass else "FAIL"
    print(
        f"hard_rules:  SKILL.md={n_skill}  artifact-data={n_artifact_hr}"
        f"  HTML-sidebar={qr_item_count}  → {hr_status}"
    )
    if not hr_counts_match:
        if n_artifact_hr != n_skill:
            print(f"  Count mismatch: SKILL.md={n_skill} vs artifact-data={n_artifact_hr}")
        if qr_item_count != n_skill:
            print(f"  Count mismatch: SKILL.md={n_skill} vs HTML-sidebar={qr_item_count}")
    for title in hr_missing:
        print(f'  Missing in artifact-data: "{title}"')

    # ── dead_ends check ───────────────────────────────────────────────────────
    de_counts_match = n_operate_de == n_artifact_de == dead_row_count
    de_pass = de_counts_match
    de_status = "PASS" if de_pass else "FAIL"
    print(
        f"dead_ends:   operate.md={n_operate_de}  artifact-data={n_artifact_de}"
        f"   HTML-rows={dead_row_count}      → {de_status}"
    )
    if not de_counts_match:
        if n_artifact_de != n_operate_de:
            print(f"  Count mismatch: operate.md={n_operate_de} vs artifact-data={n_artifact_de}")
        if dead_row_count != n_operate_de:
            print(f"  Count mismatch: operate.md={n_operate_de} vs HTML-rows={dead_row_count}")

    # ── result ────────────────────────────────────────────────────────────────
    overall_pass = hr_pass and de_pass
    print("---")
    if overall_pass:
        print("RESULT: PASS — files are in sync")
        return 0
    else:
        print("RESULT: FAIL — update hermes-chrome-guide.html to match SKILL.md")
        return 1


if __name__ == "__main__":
    sys.exit(main())
