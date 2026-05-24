#!/usr/bin/env python3
"""Extract structured escalation from a baseline.py evidence-root.

Closes the loop on SKILL.md Hard Rule 14: after baseline.py exits (success or
abort), the calling agent MUST check for a structured escalation. If one
exists, the agent MUST immediately invoke `AskUserQuestion` with the
`proposed_questions` — NOT write a chat reply summarizing the situation.

This script makes that check deterministic and parseable:

  python3 extract_escalation.py /path/to/evidence-root

Exit codes:
  0 — no escalation present (baseline completed cleanly or never started)
  1 — escalation present; AskUserQuestion args printed to stdout as JSON
  2 — escalation file present but malformed (treat as "needs operator")

When exit=1, stdout is a JSON object with shape:
  {
    "askUserQuestion_args": {
      "questions": [ {question, header, multiSelect, options:[{label,description}]} ]
    },
    "context_summary": "one-line synthesis the agent should include in its
                       text response alongside the AskUserQuestion call",
    "raw_escalation": { ...full escalation record for forensics... }
  }

The calling agent's loop is then:
  1. baseline.py exits
  2. Run extract_escalation.py against the evidence-root
  3. If exit=1: immediately invoke AskUserQuestion with askUserQuestion_args.
     Surface context_summary as the leading text. Do not write a generic
     "baseline aborted" reply — the structured question IS the reply.
  4. If exit=0: proceed with normal baseline-complete handling (TSV append,
     PROGRESS.md entry, etc.)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ESCALATION_FILE = "SELF_HEAL_ESCALATION.json"


def _summarize(esc: dict) -> str:
    """Produce a one-line context summary the agent prepends to its
    AskUserQuestion. Keeps the operator oriented without forcing them to
    read raw JSON."""
    fixture = esc.get("fixture", "?")
    iter_n = esc.get("iter", "?")
    pattern = (esc.get("top_match") or {}).get("pattern_id") or esc.get("pattern") or "none"
    category = esc.get("category") or (esc.get("top_match") or {}).get("category") or "?"
    elapsed = esc.get("elapsed_seconds")
    reason = esc.get("reason", "")
    parts = [f"Fixture {fixture} iter {iter_n} aborted"]
    if pattern and pattern != "none":
        parts.append(f"pattern={pattern}")
    parts.append(f"category={category}")
    if elapsed:
        parts.append(f"elapsed={elapsed}s")
    if reason:
        parts.append(f"reason={reason}")
    return " | ".join(parts)


def _convert_proposed_questions(pqs: list[dict]) -> dict:
    """Convert the escalation's proposed_questions into the exact shape
    AskUserQuestion expects: {questions: [{question, header, multiSelect,
    options: [{label, description}]}]}. The escalation may have options as
    dicts already; pass through. Truncate at 4 questions / 4 options per
    AskUserQuestion's limits."""
    questions = []
    for q in pqs[:4]:
        options = q.get("options", [])[:4]
        # Normalize options to the {label, description} shape
        norm_opts = []
        for o in options:
            if isinstance(o, dict) and "label" in o:
                norm_opts.append({
                    "label": o["label"],
                    "description": o.get("description", ""),
                })
            elif isinstance(o, str):
                norm_opts.append({"label": o, "description": ""})
        # AskUserQuestion needs ≥2 options per question; pad with an abort
        # option if the escalation declared too few.
        if len(norm_opts) < 2:
            norm_opts.append({
                "label": "Abort and investigate manually",
                "description": "Skip auto-recovery; operator inspects "
                               "evidence_dir + Builder logs.",
            })
        questions.append({
            "question": q.get("question", "How should the skill recover?"),
            "header": q.get("header", "Recovery")[:12],  # AskUQ header limit
            "multiSelect": bool(q.get("multiSelect", False)),
            "options": norm_opts,
        })
    return {"questions": questions}


def extract(evidence_root: pathlib.Path) -> tuple[int, dict | None]:
    """Returns (exit_code, payload). See module docstring for shape."""
    if not evidence_root.exists():
        return 0, None
    file = evidence_root / ESCALATION_FILE
    if not file.exists():
        return 0, None
    try:
        esc = json.loads(file.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return 2, {"error": f"escalation file malformed: {exc}",
                   "file": str(file)}
    pqs = esc.get("proposed_questions", [])
    if not pqs:
        return 2, {"error": "escalation file has no proposed_questions",
                   "file": str(file), "raw_escalation": esc}
    return 1, {
        "askUserQuestion_args": _convert_proposed_questions(pqs),
        "context_summary": _summarize(esc),
        "raw_escalation": esc,
        "evidence_root": str(evidence_root),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("evidence_root", type=pathlib.Path,
                    help="baseline.py --evidence-root path")
    ap.add_argument("--json", action="store_true",
                    help="emit JSON output (default). Reserved for future "
                         "human-readable mode.")
    args = ap.parse_args()
    code, payload = extract(args.evidence_root)
    if payload is not None:
        print(json.dumps(payload, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
