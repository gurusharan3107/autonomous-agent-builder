#!/usr/bin/env python3
"""Regenerate the live numbers in docs/goal/goal-overview.html from the canonical
docs/goal/*.md (ROADMAP.md + STATUS.md). Deterministic, idempotent, fail-loud.

Patches three kinds of region, never the hand-authored narrative prose:
  1. the <script type="application/json" id="artifact-data"> block (derivable keys only;
     non-derivable keys like `tiers`/`source` are preserved from the existing block).
  2. <!-- gen:NAME -->…<!-- /gen:NAME --> marker regions: snapshot_date, roadmap_totals,
     epoch, milestone, priorities, tasks.
  3. per-milestone meters: each `.ms` block keyed by <span class="id">MX.Y</span> gets its
     <small>D / T</small> and bar width:NN% recomputed.

Priority convention (source of truth = ROADMAP.md): an OPEN item may carry an inline
backtick-wrapped priority token immediately after its checkbox, e.g.
  - [ ] `P0` **can_use_tool enforces subagent phase boundaries** …
Tagged open items (P0–P3) are collected and rendered into the `priorities` marker,
sorted P0→P3 then file order. Untagged items are ignored by the priorities view but
still counted in the milestone meters.

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
# A checkbox item line: capture indent, state ( |x), optional inline `Pn`, then the rest.
ITEM_LINE = re.compile(r"^\s*-\s*\[( |x)\]\s*(?:`(P[0-3])`\s*)?(.*)$")
# An open item line, capturing an optional inline `Pn` priority token + the rest.
OPEN_ITEM = re.compile(r"^\s*-\s*\[ \]\s*(?:`(P[0-3])`\s*)?(.*)$")
PRI_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
# Curated Open-priorities view: at most this many rows per level (full prioritized
# backlog lives in the Tasks matrix). P3 capped to 1.
PRI_CAP = {"P0": 3, "P1": 3, "P2": 3, "P3": 1}
# Manual metadata tokens (backtick-wrapped) parsed off a roadmap line. Not prose.
IF_TOKEN = re.compile(r"`IF`")
T_TOKEN = re.compile(r"`T:(backend|browser)(?::(pending|na))?`")
# Heading name: `### M1.5 — Realtime Voice (Samantha) parity …` -> the part after the id.
MS_NAME = re.compile(r"^\s*[—-]\s*(.*)$")
# TESTING.md (browser-testing roadmap) parsing.
#   `## S1 — Bootstrap & readiness`  (surface group heading)
SC_HEADING = re.compile(r"^##\s+(S\d+)\s+[—-]\s+(.*)$")
#   ``- `SC-01` **Title** — desc. `S:inflight` `` (scenario line; state is source of truth)
SC_LINE = re.compile(
    r"^\s*-\s*`(SC-\d+)`\s*\*\*(.+?)\*\*\s*[—-]\s*(.*?)\s*`S:(pending|inflight|pass|fail|blocked)`\s*$"
)
SC_STATES = ("pass", "inflight", "fail", "blocked", "pending")


def die(msg: str) -> NoReturn:
    print(f"build_goal_overview: ERROR — {msg}", file=sys.stderr)
    raise SystemExit(2)


def item_label(rest: str, cap: int = 90) -> str:
    """Strip markdown emphasis/code/links from an item line and shorten to one phrase."""
    s = rest
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)  # [text](url) -> text
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)          # **bold**
    s = re.sub(r"`([^`]*)`", r"\1", s)              # `code`
    s = re.sub(r"\*(.+?)\*", r"\1", s)              # *italic*
    s = re.sub(r"\s+", " ", s).strip()
    dot = s.find(". ")
    if 0 <= dot < cap:                              # cut at first sentence end if early
        s = s[:dot]
    elif len(s) > cap:
        s = s[:cap].rstrip() + "…"
    return s


def strip_meta_tokens(rest: str) -> str:
    """Remove the manual `IF`/`T:*` metadata tokens from an item line before display."""
    s = IF_TOKEN.sub("", rest)
    s = T_TOKEN.sub("", s)
    return s


def parse_roadmap(text: str) -> tuple[list[dict], int, int, list[dict], list[dict]]:
    """Return (per-milestone [{id,done,open}], total_closed, total_open, priorities, tasks).

    Splits by `### M<x.y>` headings; counts [x]/[ ] checkboxes at any indent per section.
    `priorities` = open items carrying an inline `Pn` token, sorted P0→P3 then file order:
    [{"pri","milestone","label"}].
    `tasks` = every checkbox item with its tick state, bucketed completed→in-flight→pending
    (file order within a bucket): [{"ms","ms_name","pri","label","done","inflight",
    "backend","browser"}] where backend/browser ∈ {"none","pending","pass"}.
    """
    lines = text.splitlines()
    sections: list[tuple[str, str, list[str]]] = []  # (id, name, body lines)
    cur_id: str | None = None
    cur_name = ""
    buf: list[str] = []
    for line in lines:
        m = MS_HEADING.match(line)
        if m:
            if cur_id is not None:
                sections.append((cur_id, cur_name, buf))
            cur_id = m.group(1)
            nm = MS_NAME.match(m.group(2))
            cur_name = nm.group(1).strip() if nm else m.group(2).strip()
            buf = []
        elif cur_id is not None:
            buf.append(line)
    if cur_id is not None:
        sections.append((cur_id, cur_name, buf))
    if not sections:
        die("no '### M<x.y>' milestone headings found in ROADMAP.md")

    milestones, tot_done, tot_open = [], 0, 0
    priorities: list[dict] = []
    tasks: list[dict] = []
    order = 0
    for mid, mname, body in sections:
        blob = "\n".join(body)
        done = len(CLOSED.findall(blob))
        opn = len(OPEN.findall(blob))
        milestones.append({"id": mid, "done": done, "open": opn})
        tot_done += done
        tot_open += opn
        for line in body:
            im = OPEN_ITEM.match(line)
            if im and im.group(1):
                priorities.append({
                    "pri": im.group(1),
                    "milestone": mid,
                    "label": item_label(strip_meta_tokens(im.group(2))),
                    "_order": order,
                })
            tm = ITEM_LINE.match(line)
            if tm:
                state, pri, rest = tm.group(1), tm.group(2), tm.group(3)
                is_done = state == "x"
                inflight = (not is_done) and bool(IF_TOKEN.search(rest))

                def _test_state(kind: str, rest: str = rest) -> str:
                    st = "none"
                    for tk in T_TOKEN.finditer(rest):
                        if tk.group(1) == kind:
                            st = tk.group(2) or "pass"  # "pending" | "na" | "pass"
                    return st

                tasks.append({
                    "ms": mid,
                    "ms_name": mname,
                    "pri": pri or "",
                    "label": item_label(strip_meta_tokens(rest)),
                    "done": is_done,
                    "inflight": inflight,
                    "backend": _test_state("backend"),
                    "browser": _test_state("browser"),
                    "_order": order,
                })
            order += 1
    priorities.sort(key=lambda p: (PRI_RANK[p["pri"]], p["_order"]))
    for p in priorities:
        p.pop("_order", None)

    def _bucket(t: dict) -> int:
        if t["done"]:
            return 0          # completed
        if t["inflight"]:
            return 1          # in-flight
        return 2              # pending

    tasks.sort(key=lambda t: (_bucket(t), t["_order"]))
    for t in tasks:
        t.pop("_order", None)
    return milestones, tot_done, tot_open, priorities, tasks


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def cap_priorities(priorities: list[dict]) -> list[dict]:
    """Trim the sorted priorities list to PRI_CAP[level] rows per level (curated view)."""
    seen: dict[str, int] = {}
    out: list[dict] = []
    for p in priorities:  # already sorted P0->P3 then file order
        n = seen.get(p["pri"], 0)
        if n >= PRI_CAP.get(p["pri"], 0):
            continue
        seen[p["pri"]] = n + 1
        out.append(p)
    return out


def priorities_html(priorities: list[dict]) -> str:
    """Render tagged open items as priority rows (P0→P3), each with a colored badge."""
    if not priorities:
        return ('<div class="empty">No prioritized items — tag a ROADMAP item with '
                "<code>`P0`</code>/<code>`P1`</code>/<code>`P2`</code> after its "
                "checkbox.</div>")
    rows = []
    for p in priorities:
        cls = p["pri"].lower()
        rows.append(
            f'<div class="prow"><span class="badge {cls}">{p["pri"]}</span>'
            f'<span class="plabel">{_esc(p["label"])}</span>'
            f'<span class="pms">{p["milestone"]}</span></div>'
        )
    return "".join(rows)


_TICK = {"pass": "✓", "pending": "⏳", "na": "✗", "none": "—"}
_TICK_CLS = {"pass": "tk pass", "pending": "tk pend", "na": "tk cross", "none": "tk na"}


def tasks_html(tasks: list[dict]) -> str:
    """Render every roadmap item as a task row, bucketed completed→in-flight→pending.

    Each row: milestone id+name · Pn badge (blank if none) · label · three status cells
    (Done / Browser / Backend) rendered ✓ pass / ⏳ pending / ✗ not-applicable / —
    untagged. Bucket headers separate the groups.
    """
    if not tasks:
        return '<div class="empty">No roadmap items found.</div>'
    buckets = [
        ("done", "Completed", lambda t: t["done"]),
        ("inflight", "In flight", lambda t: (not t["done"]) and t["inflight"]),
        ("pending", "Pending", lambda t: (not t["done"]) and (not t["inflight"])),
    ]
    parts: list[str] = []
    for cls, title, pred in buckets:
        group = [t for t in tasks if pred(t)]
        if not group:
            continue
        parts.append(f'<div class="tbucket {cls}"><span class="tbhead">{title}</span>'
                     f'<span class="tbn">{len(group)}</span></div>')
        for t in group:
            done_tick = "pass" if t["done"] else "none"
            pri = t["pri"]
            badge = (f'<span class="badge {pri.lower()}">{pri}</span>' if pri
                     else '<span class="badge blank"></span>')
            parts.append(
                '<div class="trow">'
                f'<span class="tms" title="{_esc(t["ms_name"])}">{t["ms"]}</span>'
                f'{badge}'
                f'<span class="tlabel">{_esc(t["label"])}</span>'
                f'<span class="{_TICK_CLS[done_tick]}" title="Done">{_TICK[done_tick]}</span>'
                f'<span class="{_TICK_CLS[t["browser"]]}" title="Browser-tested">{_TICK[t["browser"]]}</span>'
                f'<span class="{_TICK_CLS[t["backend"]]}" title="Backend-tested">{_TICK[t["backend"]]}</span>'
                '</div>'
            )
    return "".join(parts)


# ---- TESTING.md (browser-testing roadmap) -------------------------------------------

# state -> (badge css suffix, glyph, label)
_SC_BADGE = {
    "pass": ("s-pass", "✓", "passed"),
    "inflight": ("s-inflight", "🔄", "in flight"),
    "pending": ("s-pending", "⬜", "pending"),
    "fail": ("s-fail", "✗", "bug found"),
    "blocked": ("s-blocked", "⛔", "blocked"),
}


def parse_testing(text: str) -> tuple[list[dict], dict, int]:
    """Parse TESTING.md → (groups, counts, total).

    groups = [{"sid","sname","scenarios":[{"id","title","desc","state"}]}] in file order;
    counts = {state: n} over SC_STATES; total = sum(counts). State token is the only
    source of truth for the rendered status (checkbox-free format).
    """
    groups: list[dict] = []
    counts = {s: 0 for s in SC_STATES}
    cur: dict | None = None
    for line in text.splitlines():
        h = SC_HEADING.match(line)
        if h:
            cur = {"sid": h.group(1), "sname": h.group(2).strip(), "scenarios": []}
            groups.append(cur)
            continue
        m = SC_LINE.match(line)
        if m and cur is not None:
            state = m.group(4)
            cur["scenarios"].append({
                "id": m.group(1),
                "title": m.group(2).strip(),
                "desc": item_label(m.group(3), cap=160),
                "state": state,
            })
            counts[state] += 1
    groups = [g for g in groups if g["scenarios"]]
    return groups, counts, sum(counts.values())


def testing_summary_html(counts: dict, total: int) -> str:
    """One-line tally; `in flight` is the current testing effort."""
    if not total:
        return "No scenarios yet — add them to <a href=\"TESTING.md\">TESTING.md</a>."
    return (
        f'<b>{total}</b> scenarios &middot; '
        f'<b style="color:var(--clay)">{counts["inflight"]}</b> in flight (current effort) &middot; '
        f'<span style="color:var(--olive)">{counts["pass"]} passed</span> &middot; '
        f'{counts["fail"]} bugs &middot; {counts["blocked"]} blocked &middot; '
        f'{counts["pending"]} pending'
    )


def testing_html(groups: list[dict], total: int) -> str:
    """Render TESTING.md scenarios, grouped by surface, each with a status badge."""
    if not total:
        return ('<div class="empty">No scenarios — add them to '
                "<a href=\"TESTING.md\">TESTING.md</a>.</div>")
    parts: list[str] = []
    for g in groups:
        parts.append(
            f'<div class="tbucket"><span class="tbhead">{_esc(g["sid"])} · '
            f'{_esc(g["sname"])}</span><span class="tbn">{len(g["scenarios"])}</span></div>'
        )
        for s in g["scenarios"]:
            cls, glyph, lbl = _SC_BADGE[s["state"]]
            parts.append(
                '<div class="screw">'
                f'<span class="scid">{_esc(s["id"])}</span>'
                f'<span class="badge {cls}" title="{lbl}">{glyph} {_esc(lbl)}</span>'
                f'<span class="sclabel" title="{_esc(s["desc"])}">{_esc(s["title"])}</span>'
                '</div>'
            )
    return "".join(parts)


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

    milestones, closed, opn, priorities, tasks = parse_roadmap(
        (goal / "ROADMAP.md").read_text(encoding="utf-8"))
    status = parse_status((goal / "STATUS.md").read_text(encoding="utf-8"))
    priorities_view = cap_priorities(priorities)
    # TESTING.md is optional; when present it drives the Browser Testing section.
    testing_path = goal / "TESTING.md"
    if testing_path.exists():
        tgroups, tcounts, ttotal = parse_testing(testing_path.read_text(encoding="utf-8"))
    else:
        tgroups, tcounts, ttotal = [], {s: 0 for s in SC_STATES}, 0
    html = original = html_path.read_text(encoding="utf-8")

    summary: list[str] = []
    payload = {
        "snapshot_date": status["date"],
        "epoch": status["epoch"],
        "milestone": re.sub(r"\*\*", "", status["milestone_raw"]),
        "roadmap_totals": {"closed": closed, "open": opn},
        "milestones": milestones,
        "priorities": priorities_view,
        "tasks": tasks,
        "testing": {"total": ttotal, "counts": tcounts, "groups": tgroups},
    }
    html, ch = replace_artifact_data(html, payload)
    if ch:
        summary.append("artifact-data JSON")
    for name, value in (
        ("snapshot_date", status["date"]),
        ("epoch", status["epoch"]),
        ("milestone", milestone_html(status["milestone_raw"])),
        ("roadmap_totals", f"{closed} items closed, {opn} open"),
        ("priorities", priorities_html(priorities_view)),
        ("tasks", tasks_html(tasks)),
    ):
        html, ch = replace_marker(html, name, value)
        if ch:
            summary.append(f"gen:{name}")
    # Browser-testing markers are optional (soft-skip if the section isn't in the HTML).
    for name, value in (
        ("testing_summary", testing_summary_html(tcounts, ttotal)),
        ("testing", testing_html(tgroups, ttotal)),
    ):
        pat = re.compile(rf"(<!-- gen:{name} -->)(.*?)(<!-- /gen:{name} -->)", re.DOTALL)
        if not pat.search(html):
            continue
        before = html
        html = pat.sub(lambda m: m.group(1) + value + m.group(3), html)
        if html != before:
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
