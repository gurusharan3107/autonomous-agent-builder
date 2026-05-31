#!/usr/bin/env python3
"""Deterministic evidence gatherer for the elon (Musk-hat) skill.

No model judgment — pure git/filesystem metrics that answer the phase questions:
  - deletion ratio (phase 2)      : how much the codebase prunes vs grows
  - LOC + largest files (phase 2/3): where the mass is
  - dead-import candidates (phase 2): modules with no importer outside themselves + tests

Classification of a candidate as actually-deletable is a JUDGMENT call and is
intentionally NOT done here — see references/operate.md phase 2 (import-trace).
This script only surfaces candidates to investigate.

Usage:
  python3 evidence.py [--src DIR] [--ext .py] [--days 90] [--top 20] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def sh(*args: str) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, check=False).stdout
    except Exception:  # noqa: BLE001 - deterministic best-effort
        return ""


def repo_root() -> Path:
    out = sh("git", "rev-parse", "--show-toplevel").strip()
    return Path(out) if out else Path.cwd()


def deletion_ratio(root: Path, ext: str, days: int) -> dict:
    out = sh(
        "git", "-C", str(root), "log", f"--since={days} days ago",
        "--numstat", "--pretty=tformat:", "--", f"*{ext}",
    )
    added = removed = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            added += int(parts[0])
            removed += int(parts[1])
    ratio = round(removed / added, 3) if added else None
    band = (
        "grows-only (cardinal sin)" if ratio is not None and ratio < 0.15
        else "alive but grows faster than it prunes" if ratio is not None and ratio < 0.30
        else "healthy pruning" if ratio is not None
        else "no history"
    )
    return {"days": days, "added": added, "removed": removed, "ratio": ratio, "band": band}


def loc_and_largest(src: Path, ext: str, top: int) -> dict:
    files = sorted(src.rglob(f"*{ext}"))
    sizes = []
    total = 0
    for f in files:
        try:
            n = sum(1 for _ in f.open("rb"))
        except OSError:
            continue
        total += n
        sizes.append((n, str(f)))
    sizes.sort(reverse=True)
    return {
        "total_loc": total,
        "file_count": len(sizes),
        "largest": [{"loc": n, "file": p} for n, p in sizes[:top]],
        "over_1000": [{"loc": n, "file": p} for n, p in sizes if n >= 1000],
    }


def dead_import_candidates(src: Path, ext: str, top: int) -> list[dict]:
    """Modules whose stem appears in no other source file (outside tests).

    Heuristic only — surfaces candidates for the import-trace step, never a verdict.
    Skips __init__/__main__ and dunder files.
    """
    if ext != ".py":
        return []  # heuristic is python-import shaped; other langs: trace manually
    files = [f for f in src.rglob("*.py") if not f.name.startswith("__")]
    # Build one corpus of all source text (excluding tests dirs) for cheap membership tests.
    corpus_parts = []
    for f in src.rglob("*.py"):
        if "test" in f.parts or f.name.startswith("test_"):
            continue
        try:
            corpus_parts.append(f"\n# FILE {f}\n" + f.read_text(errors="ignore"))
        except OSError:
            continue
    corpus = "".join(corpus_parts)
    out = []
    for f in files:
        stem = f.stem
        # count references to this module name as an import target, excluding its own file
        # Excise the WHOLE own-file segment (marker + body up to the next marker),
        # not just the marker line — otherwise the file's own body remains in the
        # corpus and any self-reference (e.g. a path string naming the module)
        # counts as an external ref, hiding a genuine orphan from this heuristic.
        own = f"\n# FILE {f}\n"
        start = corpus.find(own)
        if start >= 0:
            nxt = corpus.find("\n# FILE ", start + len(own))
            end = nxt if nxt >= 0 else len(corpus)
            body_removed = corpus[:start] + corpus[end:]
        else:
            body_removed = corpus
        # any word-boundary occurrence of the module name elsewhere — counts dotted
        # imports (`from pkg.stem import X`) and attribute refs (`pkg.stem`). A bare
        # word-boundary match is deliberately generous: false-negatives (calling a used
        # module dead) are far worse here than false-positives.
        refs = len(re.findall(rf"\b{re.escape(stem)}\b", body_removed))
        if refs == 0:
            try:
                loc = sum(1 for _ in f.open("rb"))
            except OSError:
                loc = 0
            out.append({"module": stem, "file": str(f), "loc": loc, "nonself_refs": 0})
    out.sort(key=lambda d: d["loc"], reverse=True)
    return out[:top]


def main() -> int:
    ap = argparse.ArgumentParser(description="Musk-hat evidence gatherer (deterministic).")
    ap.add_argument("--src", default="src", help="source dir to measure (default: src)")
    ap.add_argument("--ext", default=".py", help="file extension (default: .py)")
    ap.add_argument("--days", type=int, default=90, help="deletion-ratio window (default: 90)")
    ap.add_argument("--top", type=int, default=20, help="how many largest/candidates to list")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    root = repo_root()
    src = (root / args.src) if not Path(args.src).is_absolute() else Path(args.src)
    if not src.exists():
        src = root  # fall back to whole repo

    data = {
        "root": str(root),
        "src": str(src),
        "ext": args.ext,
        "deletion_ratio_90d": deletion_ratio(root, args.ext, args.days),
        "mass": loc_and_largest(src, args.ext, args.top),
        "dead_import_candidates": dead_import_candidates(src, args.ext, args.top),
        "note": "candidates are heuristic — import-trace each (operate.md phase 2) before calling it deletable",
    }

    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    dr = data["deletion_ratio_90d"]
    print(f"# Musk-hat evidence — {src}")
    print(f"\n## Phase 2 · Deletion ratio ({dr['days']}d)")
    print(f"  added={dr['added']}  removed={dr['removed']}  ratio={dr['ratio']}  → {dr['band']}")
    m = data["mass"]
    print(f"\n## Mass: {m['total_loc']} LOC across {m['file_count']} files")
    print(f"  files ≥1000 LOC: {len(m['over_1000'])}")
    for row in m["largest"][:10]:
        print(f"    {row['loc']:>6}  {row['file']}")
    dc = data["dead_import_candidates"]
    print(f"\n## Dead-import CANDIDATES (heuristic — verify by import-trace): {len(dc)}")
    for row in dc[:15]:
        print(f"    {row['loc']:>6}  {row['module']}  ({row['file']})")
    print("\n  -> import-trace each before the word 'delete' (operate.md phase 2)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
