#!/usr/bin/env python3
"""Regenerate the live numbers in docs/goal/goal-overview.html from the canonical
docs/goal/*.md (ROADMAP.md + STATUS.md). Deterministic, idempotent, fail-loud.

Patches three kinds of region, never the hand-authored narrative prose:
  1. the <script type="application/json" id="artifact-data"> block (derivable keys only;
     non-derivable keys like `tiers`/`source` are preserved from the existing block).
  2. <!-- gen:NAME -->…<!-- /gen:NAME --> marker regions: snapshot_date, roadmap_totals,
     epoch, milestone.
  3. per-milestone meters: each `.ms` block keyed by <span class="id">MX.Y</span> gets its
     <small>D / T</small> and bar width:NN% recomputed.

Usage:
  build_goal_overview.py [--root DIR] [--check]
    --check : exit 1 if the file WOULD change (no write) — used by the idempotency eval.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import NoReturn

MS_HEADING = re.compile(r"^###\s+(M\d+\.\d+)\b(.*)$")
CLOSED = re.compile(r"\[x\]", re.IGNORECASE)
OPEN = re.compile(r"\[ \]")


def die(msg: str) -> NoReturn:
    print(f"build_goal_overview: ERROR — {msg}", file=sys.stderr)
    raise SystemExit(2)


def parse_roadmap(text: str) -> tuple[list[dict], int, int]:
    """Return (per-milestone [{id,done,open}], total_closed, total_open).

    Splits by `### M<x.y>` headings; counts [x]/[ ] checkboxes at any indent per section.
    """
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    cur_id: str | None = None
    buf: list[str] = []
    for line in lines:
        m = MS_HEADING.match(line)
        if m:
            if cur_id is not None:
                sections.append((cur_id, buf))
            cur_id, buf = m.group(1), []
        elif cur_id is not None:
            buf.append(line)
    if cur_id is not None:
        sections.append((cur_id, buf))
    if not sections:
        die("no '### M<x.y>' milestone headings found in ROADMAP.md")

    milestones, tot_done, tot_open = [], 0, 0
    for mid, body in sections:
        blob = "\n".join(body)
        done = len(CLOSED.findall(blob))
        opn = len(OPEN.findall(blob))
        milestones.append({"id": mid, "done": done, "open": opn})
        tot_done += done
        tot_open += opn
    return milestones, tot_done, tot_open


def parse_status(text: str) -> dict:
    """Pull Epoch, Milestone, Last-Update date from the `## Current Position` table."""
    def cell(label: str) -> str:
        m = re.search(rf"\|\s*{re.escape(label)}\s*\|\s*(.+?)\s*\|", text)
        if not m:
            die(f"STATUS.md Current Position: row '{label}' not found")
        return m.group(1).strip()

    epoch = cell("Current Epoch").replace("**", "").strip()
    milestone_raw = cell("Current Milestone").strip()
    last_update = cell("Last Update")
    date_m = re.match(r"(\d{4}-\d{2}-\d{2})", last_update)
    if not date_m:
        die("STATUS.md Last Update does not start with a YYYY-MM-DD date")
    return {"epoch": epoch, "milestone_raw": milestone_raw, "date": date_m.group(1)}


def milestone_html(raw: str) -> str:
    """`**M3.5 — Optimization loop activation** (autoresearch Track B)` -> bolded-id HTML."""
    inner = re.sub(r"\*\*(.+?)\*\*", r"\1", raw)  # strip bold markers
    m = re.match(r"(M\d+\.\d+)\s*[—-]\s*(.*)", inner)
    if m:
        return f"<b>{m.group(1)}</b> — {m.group(2)}".rstrip()
    return inner


def replace_marker(html: str, name: str, value: str) -> tuple[str, bool]:
    pat = re.compile(rf"(<!-- gen:{name} -->)(.*?)(<!-- /gen:{name} -->)", re.DOTALL)
    if not pat.search(html):
        die(f"marker <!-- gen:{name} --> missing in goal-overview.html (run setup)")
    new, _ = pat.subn(lambda m: m.group(1) + value + m.group(3), html)
    return new, new != html


def replace_artifact_data(html: str, payload: dict) -> tuple[str, bool]:
    pat = re.compile(
        r'(<script type="application/json" id="artifact-data">\s*)(\{.*?\})(\s*</script>)',
        re.DOTALL,
    )
    m = pat.search(html)
    if not m:
        die('artifact-data <script id="artifact-data"> block not found')
    try:
        existing = json.loads(m.group(2))
    except json.JSONDecodeError:
        existing = {}
    merged = dict(existing)
    merged.update(payload)  # derivable keys overwrite; non-derivable (tiers/source) preserved
    new_json = json.dumps(merged, indent=2)
    new = html[: m.start()] + m.group(1) + new_json + m.group(3) + html[m.end():]
    return new, new != html


def update_meters(html: str, milestones: list[dict]) -> tuple[str, list[str]]:
    """Update <small>D / T</small> + bar width for each milestone meter present."""
    changed: list[str] = []
    ids = [m["id"] for m in milestones]
    by_id = {m["id"]: m for m in milestones}
    for mid in ids:
        anchor = re.search(rf'<span class="id">{re.escape(mid)}</span>', html)
        if not anchor:
            continue
        nxt = re.search(r'<span class="id">M\d+\.\d+</span>', html[anchor.end():])
        seg_end = anchor.end() + (nxt.start() if nxt else len(html) - anchor.end())
        seg = html[anchor.end():seg_end]
        done, opn = by_id[mid]["done"], by_id[mid]["open"]
        total = done + opn
        if total == 0 or "<small>" not in seg:
            continue
        pct = round(100 * done / total)
        new_seg = re.sub(r"width:\d+%", f"width:{pct}%", seg, count=1)
        new_seg = re.sub(r"<small>\s*\d+\s*/\s*\d+\s*</small>",
                         f"<small>{done} / {total}</small>", new_seg, count=1)
        if new_seg != seg:
            changed.append(mid)
            html = html[:anchor.end()] + new_seg + html[seg_end:]
    return html, changed


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate goal-overview.html live numbers.")
    ap.add_argument("--root", default=".", help="repo root (default: cwd)")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the file would change; do not write")
    args = ap.parse_args()

    goal = Path(args.root) / "docs" / "goal"
    html_path = goal / "goal-overview.html"
    for p in (html_path, goal / "ROADMAP.md", goal / "STATUS.md"):
        if not p.exists():
            die(f"missing {p}")

    milestones, closed, opn = parse_roadmap((goal / "ROADMAP.md").read_text(encoding="utf-8"))
    status = parse_status((goal / "STATUS.md").read_text(encoding="utf-8"))
    html = original = html_path.read_text(encoding="utf-8")

    summary: list[str] = []
    payload = {
        "snapshot_date": status["date"],
        "epoch": status["epoch"],
        "milestone": re.sub(r"\*\*", "", status["milestone_raw"]),
        "roadmap_totals": {"closed": closed, "open": opn},
        "milestones": milestones,
    }
    html, ch = replace_artifact_data(html, payload)
    if ch:
        summary.append("artifact-data JSON")
    for name, value in (
        ("snapshot_date", status["date"]),
        ("epoch", status["epoch"]),
        ("milestone", milestone_html(status["milestone_raw"])),
        ("roadmap_totals", f"{closed} items closed, {opn} open"),
    ):
        html, ch = replace_marker(html, name, value)
        if ch:
            summary.append(f"gen:{name}")
    html, meters = update_meters(html, milestones)
    if meters:
        summary.append(f"meters[{','.join(meters)}]")

    would_change = html != original
    if args.check:
        if would_change:
            print("build_goal_overview: --check FAILED — file is stale, run without --check:")
            print("  changed: " + (", ".join(summary) or "(formatting)"))
            return 1
        print("build_goal_overview: --check OK — goal-overview.html is in sync")
        return 0

    if would_change:
        html_path.write_text(html, encoding="utf-8")
        print(f"build_goal_overview: updated {html_path}")
        print(f"  totals: {closed} closed / {opn} open · epoch={status['epoch']} · date={status['date']}")
        print("  changed: " + (", ".join(summary) or "(formatting)"))
    else:
        print("build_goal_overview: no change — already in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
