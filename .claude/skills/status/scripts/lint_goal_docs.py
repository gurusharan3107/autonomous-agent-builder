#!/usr/bin/env python3
"""Lint docs/goal/ROADMAP.md + STATUS.md against the goal-docs maintenance contract,
and verify goal-overview.html is in sync. Deterministic, fail-loud, agent-readable.

CONTRACT (enforced here so the prose can't drift — see status/SKILL.md):
  ROADMAP.md is the forward spine: ONE checkbox line per item.
    · OPEN  `- [ ] `Pn` <intent + acceptance>`  — carries a priority, states what
      "done" looks like; NOT a work-log.
    · CLOSED `- [x] <outcome>. <evidence pointer>` — one line: result + a pointer
      (commit hash, test name, file, or .memory slug). The full story lives in
      git / CHANGELOG.md / .memory — never re-narrated inline.
  Multi-step working detail (Delivered/Remaining/PROVEN/CORRECTION chains) belongs in
  STATUS.md (Current Item In Flight) or a working doc, never inside a ROADMAP item.
  goal-overview.html is generated read-only: meters + open-priorities + status snapshot.

SEVERITIES: ERROR (structural — blocks) / WARN (over-budget — advisory).
EXIT: 2 if any ERROR; 1 if any WARN and --strict; else 0.

Usage:
  lint_goal_docs.py [--root DIR] [--strict]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# --- budgets (chars of item text, after stripping checkbox + Pn token) -------------
# Ceilings, not targets. Write compact: open = one line; closed = outcome + pointer.
OPEN_MAX = 240
CLOSED_MAX = 160
# A closed item should point at durable evidence somewhere in its block.
EVIDENCE = re.compile(
    r"\b[0-9a-f]{7,40}\b"          # commit hash
    r"|test_\w+"                    # regression test name
    r"|\.memory|\bmemory\b"         # memory slug ref
    r"|\.(py|ts|tsx|md|json|html)\b"  # a file pointer
    r"|\d{4}-\d{2}-\d{2}"           # a dated evidence stamp
)
# Work-log keywords that should live in STATUS/CHANGELOG, not in a ROADMAP item.
WORKLOG = re.compile(
    r"\b(Delivered|PROVEN|Remaining|Verified|CORRECTION|PARTIAL DELIVERY|FIX [AB]\b"
    r"|Live[- ]?verified|Increment delivered|root cause found)\b"
)
MS_HEADING = re.compile(r"^###\s+(M\d+\.\d+)\b")
ITEM = re.compile(r"^(\s*)-\s*\[( |x)\]\s*(.*)$")
PRI = re.compile(r"^`(P[0-3])`\s*")
# Manual metadata tokens (in-flight + test status) — excluded from the char budget.
IF_TOKEN = re.compile(r"`IF`")
T_TOKEN = re.compile(r"`T:(\w+)(?::(\w+))?`")
T_KINDS = {"backend", "browser"}
T_STATES = {"pending"}
# Recognized split sub-item (IMP-027a/b/c style) or labelled task — an allowed child.
SPLIT_CHILD = re.compile(r"^\s*-\s+\*\*(IMP-\d+[a-z]|[A-Z][^*]*—)")
# The DEFINING id of an item = the bold token right after the checkbox (+ optional Pn).
DEF_ID = re.compile(r"^(?:`P[0-3]`\s*)?\*\*(IMP-\d+|G\d+)\b")


def strip_md(s: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`([^`]*)`", r"\1", s)
    return s.strip()


def lint_roadmap(text: str) -> list[tuple[str, int, str]]:
    """Return [(severity, lineno, message)]."""
    out: list[tuple[str, int, str]] = []
    lines = text.splitlines()
    in_ms = False
    cur_item: tuple[int, str, str] | None = None  # (lineno, state, text)
    worklog_hits = 0
    id_lines: dict[str, list[int]] = {}
    untagged_open: list[int] = []

    def flush(item, worklog_hits):
        if item is None:
            return
        lineno, state, raw = item
        # Warn on unknown `T:` token grammar before stripping (metadata, not prose).
        for tk in T_TOKEN.finditer(raw):
            kind, st = tk.group(1), tk.group(2)
            if kind not in T_KINDS or (st is not None and st not in T_STATES):
                out.append(("WARN", lineno, f"unknown test token `T:{kind}"
                            f"{':' + st if st else ''}` — expected "
                            "`T:backend`/`T:browser` (optionally `:pending`)"))
        # `IF`/`T:*` are metadata, not prose — exclude from the char budget.
        stripped = T_TOKEN.sub("", IF_TOKEN.sub("", raw))
        body = strip_md(PRI.sub("", stripped))
        if state == " ":
            if not PRI.match(raw):
                untagged_open.append(lineno)
            if len(body) > OPEN_MAX:
                out.append(("WARN", lineno, f"open item {len(body)}c > {OPEN_MAX} — cut to "
                            "one line (intent + acceptance); work-log → STATUS.md"))
        else:  # closed
            if len(body) > CLOSED_MAX:
                out.append(("WARN", lineno, f"closed item {len(body)}c > {CLOSED_MAX} — cut "
                            "to outcome + pointer; detail → git/CHANGELOG/.memory"))
            if not EVIDENCE.search(raw):
                out.append(("WARN", lineno, "closed item has no evidence pointer "
                            "(commit / test_ name / file / .memory / date)"))
        if worklog_hits:
            out.append(("WARN", lineno, f"item block has {worklog_hits} work-log line(s) "
                        "(Delivered/Remaining/PROVEN/…) — move the running log to "
                        "STATUS.md 'Current Item In Flight'"))

    for i, line in enumerate(lines, 1):
        if MS_HEADING.match(line):
            flush(cur_item, worklog_hits)
            cur_item, worklog_hits = None, 0
            in_ms = True
            continue
        if not in_ms:
            continue
        m = ITEM.match(line)
        if m:
            flush(cur_item, worklog_hits)
            worklog_hits = 0
            state, txt = m.group(2), m.group(3)
            cur_item = (i, state, txt)
            dm = DEF_ID.match(txt)
            if dm:
                id_lines.setdefault(dm.group(1), []).append(i)
        elif cur_item is not None and line.strip():
            # continuation line under the current item
            if not SPLIT_CHILD.match(line) and WORKLOG.search(line):
                worklog_hits += 1
    flush(cur_item, worklog_hits)

    for mid, where in sorted(id_lines.items()):
        if len(where) > 1:
            out.append(("WARN", where[0], f"item id {mid} defined {len(where)}× "
                        f"(lines {', '.join(map(str, where))}) — keep one canonical "
                        "entry; fold the re-opens into it"))
    if untagged_open:
        head = ", ".join(map(str, untagged_open[:10]))
        more = f" (+{len(untagged_open) - 10} more)" if len(untagged_open) > 10 else ""
        out.append(("WARN", untagged_open[0], f"{len(untagged_open)} open items have no "
                    f"`Pn` priority and won't show in the overview — lines {head}{more}"))
    return out


def lint_status(text: str) -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for label in ("Current Epoch", "Current Milestone", "Last Update"):
        if not re.search(rf"\|\s*{re.escape(label)}\s*\|", text):
            out.append(("ERROR", 0, f"STATUS.md Current Position: row '{label}' missing "
                        "— the generator parses it; goal-overview will fail to build"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint docs/goal ROADMAP/STATUS + HTML sync.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--strict", action="store_true", help="exit 1 on WARN too")
    args = ap.parse_args()

    goal = Path(args.root) / "docs" / "goal"
    findings: list[tuple[str, str, int, str]] = []  # (file, sev, line, msg)
    for fname, fn in (("ROADMAP.md", lint_roadmap), ("STATUS.md", lint_status)):
        p = goal / fname
        if not p.exists():
            findings.append((fname, "ERROR", 0, "file missing"))
            continue
        for sev, ln, msg in fn(p.read_text(encoding="utf-8")):
            findings.append((fname, sev, ln, msg))

    # HTML sync (reuse the generator's --check).
    gen = Path(args.root) / ".claude/skills/status/scripts/build_goal_overview.py"
    if gen.exists():
        r = subprocess.run([sys.executable, str(gen), "--root", args.root, "--check"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            findings.append(("goal-overview.html", "ERROR", 0,
                             "out of sync with markdown — run `/status update`"))

    errors = [f for f in findings if f[1] == "ERROR"]
    warns = [f for f in findings if f[1] == "WARN"]
    if not findings:
        print("lint_goal_docs: OK — goal docs satisfy the maintenance contract")
        return 0

    for fname, sev, ln, msg in findings:
        loc = f"{fname}:{ln}" if ln else fname
        print(f"  [{sev}] {loc} — {msg}")
    print(f"lint_goal_docs: {len(errors)} error(s), {len(warns)} warning(s)")
    if errors:
        return 2
    if warns and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
