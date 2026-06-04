#!/usr/bin/env python3
"""
cluster.py — deterministic theme clustering for self-optimize skill.

Reads the JSON output of analyze-sessions.mjs from a file path argument,
applies keyword clustering to recent_prompts to surface correction/pushback
signals, and also parses git log for fix-commit patterns.

Output: JSON with ranked themes (occurrences + weighted git_fix_commits).

Usage:
  python3 cluster.py /tmp/self-optimize-session.json
  python3 cluster.py /tmp/self-optimize-session.json --since 14d
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Theme definitions — keyword clusters that signal operator corrections
# ---------------------------------------------------------------------------
THEMES: list[dict] = [
    {
        "name": "autonomous_recovery",
        "label": "Autonomous recovery — agent needs operator to trigger a fix",
        "keywords": [
            "without me prompting",
            "without operator",
            "dynamically",
            "autonomous",
            "self",
            "you should know",
            "you have workflow",
            "you have builder",
            "without intervention",
            "should be able to",
            "on your own",
        ],
        "git_patterns": [],
    },
    {
        "name": "progress_routing",
        "label": "Progress routing — writing to ROADMAP/CHANGELOG instead of PROGRESS.md",
        "keywords": [
            "progress.md",
            "roadmap",
            "changelog",
            "autoresearch related",
            "not supposed to update roadmap",
            "wrong file",
        ],
        "git_patterns": ["fix.*progress", "fix.*roadmap", "fix.*routing"],
    },
    {
        "name": "test_failures",
        "label": "Test failures — committing behavioral changes without updating tests",
        "keywords": [
            "test",
            "failing",
            "failures",
            "fix rest",
            "commit this and fix",
            "broken test",
            "pytest",
            "test suite",
        ],
        "git_patterns": [r"fix\(tests\)", "align test", "test.*failure", "fix.*test"],
    },
    {
        "name": "commit_discipline",
        "label": "Commit discipline — intermediate commits, partial skill commits",
        "keywords": [
            "dont commit",
            "don't commit",
            "only added when",
            "changes are only",
            "intermediate",
            "partial commit",
            "only skill.md",
            "rest of the files",
            "not committed",
            "commit this",
        ],
        "git_patterns": [],
    },
    {
        "name": "verbose_docs",
        "label": "Verbose docs — operator-friendly writing when agent-audience is default",
        "keywords": [
            "concise",
            "verbose",
            "explanative",
            "too much",
            "without losing",
            "compact",
            "big file",
            "agent friendly",
            "shorter",
            "less text",
        ],
        "git_patterns": [],
    },
    {
        "name": "managed_app_boundary",
        "label": "Managed app boundary — direct edits to managed app instead of dispatching",
        "keywords": [
            "managed app",
            "never touch",
            "builder dashboard",
            "autonomous builder is supposed",
            "not supposed to fix",
            "dispatch",
            "ship through builder",
        ],
        "git_patterns": [],
    },
    {
        "name": "evidence_before_fix",
        "label": "Evidence before fix — acting on recommendation without validating first",
        "keywords": [
            "concrete evidence",
            "validate first",
            "dont blindly",
            "don't blindly",
            "first validate",
            "ship feature and validate",
            "is it still valid",
        ],
        "git_patterns": [],
    },
    {
        "name": "skill_patching",
        "label": "Skill patching — adding bug notes to skill instead of fixing root cause",
        "keywords": [
            "patching",
            "symptom",
            "surgical fix",
            "root cause",
            "not in the skill",
            "fix the skill",
            "dont add to skill",
            "don't add to skill",
        ],
        "git_patterns": [],
    },
    {
        "name": "routing_wrong_surface",
        "label": "Routing wrong surface — checking global skill instead of project-local",
        "keywords": [
            "dont check global",
            "check project local",
            "local not global",
            "project local",
            "wrong version",
            "global version",
        ],
        "git_patterns": [],
    },
    {
        "name": "operator_question_tool",
        "label": "Operator question tool — asking questions as plain text instead of AskUserQuestion",
        "keywords": [
            "askuserquestion",
            "ask user question",
            "question using",
            "ask in form",
            "use the tool",
            "structured question",
            "plain text question",
        ],
        "git_patterns": [],
    },
]

# Corrections are signals of operator pushback — weight heavier
CORRECTION_SIGNALS = [
    "no i meant",
    "dont",
    "don't",
    "instead",
    "wrong",
    "not that",
    "you should",
    "never",
    "always",
    "again",
    "mistake",
    "issue",
    "problem",
    "incorrect",
    "you are",
    "you were",
    "i said",
    "remember",
    "told you",
    "why did",
    "should have",
    "not supposed to",
    "supposed to",
]


def is_correction(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in CORRECTION_SIGNALS)


# Builder-orchestrated sub-agent system prompts (feature-verifier, gate-remediator,
# scaffold, code-gen, build-verifier, ...) are captured in this repo's transcript
# stream and open with "You are the <role> agent" — which matches the "you are"
# CORRECTION_SIGNAL and floods the clustering with false "corrections". Exclude them.
BUILDER_AGENT_SIGNATURES = (
    "you are the feature verifier",
    "you are the gate-remediator",
    "you are the gate remediator",
    "you are the scaffold agent",
    "you are the code-gen",
    "you are the build verifier",
    "you are the build-verifier",
    "you are the evidence",
    "you are the pr-creator",
    "you are the pr creator",
    "you are the repo-researcher",
    "you are the security review",
    "you are the documentation agent",
    "you are the browser-verifier",
    "you are the optimization agent",
)


def is_builder_agent_prompt(text: str) -> bool:
    """True for builder sub-agent system prompts (not operator input)."""
    t = text.strip().lower()
    if any(t.startswith(sig) for sig in BUILDER_AGENT_SIGNATURES):
        return True
    head = t[:80]
    return t.startswith("you are the ") and (
        "agent" in head or "verifier" in head or "remediator" in head
    )


def collect_git_fixes(since: str = "30d") -> list[str]:
    """Return git log subjects for fix/correction commits."""
    try:
        days = int(since.rstrip("d")) if since.endswith("d") else 30
        result = subprocess.run(
            ["git", "log", f"--since={days} days ago", "--format=%s"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def match_git_patterns(subjects: list[str], patterns: list[str]) -> int:
    import re

    count = 0
    for subj in subjects:
        for pat in patterns:
            if re.search(pat, subj, re.IGNORECASE):
                count += 1
                break
    return count


def cluster(session_json: dict, since: str = "30d") -> dict:
    prompts = session_json.get("recent_prompts", [])
    git_subjects = collect_git_fixes(since)

    theme_hits: dict[str, list[str]] = defaultdict(list)

    for p in prompts:
        text = p.get("text", "")
        ts = (p.get("ts") or "")[:10]
        api = p.get("api_calls", 0)
        # Only count prompts that actually triggered API calls (real interactions)
        if api == 0:
            continue
        # Skip builder sub-agent system prompts — they are not operator corrections.
        if is_builder_agent_prompt(text):
            continue
        t = text.lower()
        for theme in THEMES:
            if any(k in t for k in theme["keywords"]):
                theme_hits[theme["name"]].append(f"[{ts}] {text[:120]}")

    results = []
    for theme in THEMES:
        hits = theme_hits[theme["name"]]
        git_count = match_git_patterns(git_subjects, theme["git_patterns"])
        if hits or git_count:
            results.append(
                {
                    "name": theme["name"],
                    "label": theme["label"],
                    "occurrences": len(hits),
                    "git_fix_commits": git_count,
                    "score": len(hits) + (git_count * 2),
                    "example_prompts": hits[:4],
                    "keywords_matched": [
                        k
                        for k in theme["keywords"]
                        if any(k in p.get("text", "").lower() for p in prompts)
                    ][:5],
                }
            )

    results.sort(key=lambda x: -x["score"])

    return {
        "window": since,
        "total_prompts": len(prompts),
        "correction_prompts": sum(
            1
            for p in prompts
            if is_correction(p.get("text", "")) and not is_builder_agent_prompt(p.get("text", ""))
        ),
        "git_subjects_analyzed": len(git_subjects),
        "themes": results,
    }


def load_last_run(skill_dir: Path) -> dict:
    """Load last-run.json from the skill directory if it exists."""
    last_run_path = skill_dir / "last-run.json"
    if last_run_path.exists():
        try:
            with last_run_path.open() as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def annotate_recurrence(themes: list[dict], last_run: dict) -> list[dict]:
    """
    Mark themes that recurred since the last run where an edit was applied.
    recurred=True means: fix was applied last run but pattern is still appearing.
    This signals the fix was insufficient — needs a stronger mechanical gate.
    """
    last_edits = {t["name"] for t in last_run.get("themes", []) if t.get("edit_applied")}
    for theme in themes:
        theme["recurred"] = theme["name"] in last_edits
        if theme["recurred"]:
            # Weight recurred themes higher — they've survived a fix attempt
            theme["score"] += 5
    # Re-sort after recurrence weighting
    themes.sort(key=lambda x: -x["score"])
    return themes


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: cluster.py <session.json> [--since 30d] [--skill-dir <path>]", file=sys.stderr
        )
        sys.exit(1)

    path = Path(sys.argv[1])
    since = "30d"
    skill_dir = Path(__file__).parent.parent  # default: self-optimize root

    if "--since" in sys.argv:
        idx = sys.argv.index("--since")
        if idx + 1 < len(sys.argv):
            since = sys.argv[idx + 1]

    if "--skill-dir" in sys.argv:
        idx = sys.argv.index("--skill-dir")
        if idx + 1 < len(sys.argv):
            skill_dir = Path(sys.argv[idx + 1])

    with path.open() as f:
        session_json = json.load(f)

    last_run = load_last_run(skill_dir)
    result = cluster(session_json, since)

    # Annotate recurrence and add last-run metadata to output
    result["themes"] = annotate_recurrence(result["themes"], last_run)
    result["last_run"] = {
        "date": last_run.get("date", None),
        "themes_with_edits": [
            t["name"] for t in last_run.get("themes", []) if t.get("edit_applied")
        ],
    }
    result["recurred_count"] = sum(1 for t in result["themes"] if t.get("recurred"))

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
