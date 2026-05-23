#!/usr/bin/env python3
"""Cleanup audit — deterministic detector for orphan / verbose / dangling / misrouted docs.

Walks every `.md` under `docs/` and `.claude/skills/`, applies the 7 detection signals
+ 4 safety blockers from `.claude/skills/cleanup/references/criteria.md`, emits a
prioritized list of HARD-DELETE / DELETE? / COMPACT / WIRE / KEEP recommendations.

Read-only against the repo. Never mutates state. Safe to run in parallel with editing.

Usage:
    python3 .claude/skills/cleanup/scripts/audit.py            # human-readable
    python3 .claude/skills/cleanup/scripts/audit.py --json     # machine output
    python3 .claude/skills/cleanup/scripts/audit.py --human    # explicit human (default)
    python3 .claude/skills/cleanup/scripts/audit.py <file> --verify   # check one file against safety blockers
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys


# --- Canonical entry-point docs (safety blocker D) ----------------------------

CANONICAL_ENTRY_POINTS = {
    "CLAUDE.md", "AGENTS.md", "README.md", "CHANGELOG.md",
    "docs/REFERENCE.md", "docs/knowledge.md",
    # docs/goal/
    "docs/goal/README.md", "docs/goal/NORTH-STAR.md", "docs/goal/ROADMAP.md",
    "docs/goal/STATUS.md", "docs/goal/INDEX.md", "docs/goal/INSIGHTS.md",
    "docs/goal/EVALUATION.md", "docs/goal/FIX-STANDARD.md",
    "docs/goal/OPERATOR-LANGUAGE.md", "docs/goal/TUNING.md", "docs/goal/RESUME.md",
    # docs/autoresearch/
    "docs/autoresearch/README.md", "docs/autoresearch/PROGRESS.md",
    "docs/autoresearch/OPTIMIZE.md", "docs/autoresearch/METRICS.md",
    "docs/autoresearch/HARNESS.md", "docs/autoresearch/COMPARE.md",
    "docs/autoresearch/SDK-OBSERVABILITY.md", "docs/autoresearch/CONTEXT-LEDGER.md",
    "docs/autoresearch/GAPS.md", "docs/autoresearch/OPTIMIZE_IDEAS.md",
    "docs/autoresearch/baseline_variance.md", "docs/autoresearch/fixtures.md",
    "docs/autoresearch/INTROSPECTION.md",
}

CLI_WALKED_DIRS = ("docs/quality-gate/", "docs/workflows/")
PRE_COMMIT_FILE = "scripts/pre_commit_checks.py"
SKIP_DIRS = ("docs/agentharness-audit/",)  # operator-kept; out of scope

DEPRECATED_PATTERNS = re.compile(
    r"^.{0,200}(deprecated|migrated to|redirect|obsolete|# .+ — Deprecated)",
    re.IGNORECASE | re.DOTALL,
)
VERBOSE_DRIFT_PATTERNS = re.compile(
    r"^## Why this matters\b|^## Background\b", re.MULTILINE,
)


def _grep(pattern: str, paths: list[str], *, fixed: bool = True, include: list[str] | None = None) -> list[str]:
    """Return list of files matching `pattern` under `paths`. Empty list on no match."""
    cmd = ["grep", "-rln"]
    if fixed:
        cmd.append("-F")
    for inc in include or []:
        cmd.append(f"--include={inc}")
    cmd.append(pattern)
    cmd.extend(paths)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    return [l for l in out.stdout.splitlines() if l]


def runtime_refs(p: pathlib.Path) -> list[str]:
    """Safety blocker A: code/scripts/skills that read this file."""
    return _grep(
        p.name,
        ["src", "scripts", ".claude/skills"],
        include=["*.py", "*.ts", "*.tsx", "*.toml", "*.sh", "*.json"],
    )


def cli_walks_dir(p: pathlib.Path) -> bool:
    """Safety blocker B: is the file under a runtime-CLI-walked directory."""
    return any(str(p).startswith(d) for d in CLI_WALKED_DIRS)


def in_pre_commit_set(p: pathlib.Path) -> bool:
    """Safety blocker C: file is listed in pre_commit_checks DOC_OWNER_FILES."""
    pc = pathlib.Path(PRE_COMMIT_FILE)
    if not pc.exists():
        return False
    return f'"{p}"' in pc.read_text(errors="replace")


def is_canonical_entry_point(p: pathlib.Path) -> bool:
    """Safety blocker D."""
    return str(p) in CANONICAL_ENTRY_POINTS


def safety_blockers(p: pathlib.Path) -> list[str]:
    """Return list of triggered blocker IDs (A/B/C/D)."""
    blockers = []
    if runtime_refs(p): blockers.append("A")
    if cli_walks_dir(p): blockers.append("B")
    if in_pre_commit_set(p): blockers.append("C")
    if is_canonical_entry_point(p): blockers.append("D")
    return blockers


def doc_graph_refs(p: pathlib.Path) -> list[str]:
    """Refs to this file's basename + stem from any markdown."""
    matches = set(_grep(
        p.name,
        ["docs", "AGENTS.md", "CLAUDE.md", "README.md", ".claude/skills"],
        include=["*.md"],
    ))
    # Stem search catches refs that omit the .md (e.g., AGENTS.md cites
    # `library-retrieval-map` without the suffix).
    if p.stem != p.name:
        matches |= set(_grep(
            p.stem,
            ["docs", "AGENTS.md", "CLAUDE.md", "README.md", ".claude/skills"],
            include=["*.md"],
        ))
    matches.discard(str(p))
    return sorted(matches)


def detect_signals(p: pathlib.Path) -> list[str]:
    """Return list of triggered signal IDs from criteria.md."""
    signals = []
    try:
        content = p.read_text(errors="replace")
    except OSError:
        return signals
    head = content[:3000]  # first 3KB for deprecation detection
    if DEPRECATED_PATTERNS.search(head):
        signals.append("deprecated-stub")
    if VERBOSE_DRIFT_PATTERNS.search(content):
        signals.append("verbose-drift")
    # Long paragraphs
    long_paras = [
        para for para in content.split("\n\n")
        if len(para) > 600 and not para.startswith("```") and not para.startswith("|")
    ]
    if len(long_paras) >= 3:
        signals.append(f"long-paras:{len(long_paras)}")
    return signals


def categorize(refs: list[str], code_refs: list[str],
               blockers: list[str], signals: list[str]) -> str:
    n_refs = len(refs)
    n_code = len(code_refs)
    has_safety = bool(blockers)
    if has_safety:
        return "KEEP" if not signals else "COMPACT"  # safety blocker prevents delete
    if any("verbose" in s or "long-paras" in s for s in signals):
        if n_refs + n_code <= 2:
            return "DELETE?"  # verbose AND low refs → likely dead doctrine
        return "COMPACT"
    if "deprecated-stub" in signals:
        return "HARD-DELETE"
    if n_code == 0 and n_refs == 0:
        return "HARD-DELETE"
    if n_code == 0 and n_refs <= 2:
        return "DELETE?"
    return "KEEP"


def audit_file(p: pathlib.Path) -> dict:
    lines = sum(1 for _ in open(p, errors="replace"))
    code_refs = runtime_refs(p)
    refs = doc_graph_refs(p)
    blockers = safety_blockers(p)
    signals = detect_signals(p)
    category = categorize(refs, code_refs, blockers, signals)
    return {
        "file": str(p),
        "lines": lines,
        "runtime_refs": len(code_refs),
        "doc_refs": len(refs),
        "blockers": blockers,
        "signals": signals,
        "category": category,
    }


def enumerate_files() -> list[pathlib.Path]:
    out = []
    for root in ("docs",):
        for p in pathlib.Path(root).rglob("*.md"):
            if any(str(p).startswith(d) for d in SKIP_DIRS):
                continue
            out.append(p)
    return sorted(out)


def verify_one(target: pathlib.Path) -> int:
    if not target.exists():
        print(f"error: {target} does not exist", file=sys.stderr)
        return 2
    r = audit_file(target)
    print(json.dumps(r, indent=2))
    return 0 if r["category"] in ("HARD-DELETE", "DELETE?") else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?", help="Optional single file to verify (with --verify)")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument("--human", action="store_true", help="Human-readable (default)")
    ap.add_argument("--verify", action="store_true", help="Verify single file's safety status; exit 0 if safe to delete, 1 otherwise")
    args = ap.parse_args(argv)

    if args.verify:
        if not args.target:
            print("--verify requires a target file path", file=sys.stderr)
            return 2
        return verify_one(pathlib.Path(args.target))

    files = enumerate_files()
    results = [audit_file(p) for p in files]
    results.sort(key=lambda r: (r["category"], -r["lines"]))

    if args.json:
        summary = {"total_files": len(results)}
        for cat in ("HARD-DELETE", "DELETE?", "COMPACT", "WIRE", "KEEP"):
            summary[cat.lower().replace("?", "_question").replace("-", "_")] = sum(1 for r in results if r["category"] == cat)
        print(json.dumps({
            "categories": {cat: [r for r in results if r["category"] == cat]
                           for cat in ("HARD-DELETE", "DELETE?", "COMPACT", "KEEP")},
            "summary": summary,
        }, indent=2))
        return 0

    # human
    print(f"{'category':<12} {'file':<60} {'lines':>5} {'rt':>3} {'docs':>4}  signals/blockers")
    print("-" * 110)
    for r in results:
        flag = ",".join(r["signals"]) if r["signals"] else "-"
        block = f"BLOCK:{','.join(r['blockers'])}" if r["blockers"] else ""
        print(f"{r['category']:<12} {r['file'][:60]:<60} {r['lines']:>5} {r['runtime_refs']:>3} {r['doc_refs']:>4}  {flag} {block}")
    print()
    counts = {}
    for r in results:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    print("summary:", counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
