#!/usr/bin/env python3
"""Karpathy-style autoresearch loop (human-in-the-loop v1).

Per docs/autoresearch/HARNESS.md, this script picks the top unattempted idea
from docs/autoresearch/OPTIMIZE_IDEAS.md, creates a branch, prompts the
operator to make the edit (v1 is human-in-the-loop), then runs run.py and
compare.py and either keeps or discards the branch.

Stops on iteration cap, cost budget exhaustion, or operator interrupt.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import signal
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
IDEAS_PATH = ROOT / "docs" / "autoresearch" / "OPTIMIZE_IDEAS.md"

_STOP = False


def _stop_handler(*_: object) -> None:
    global _STOP
    _STOP = True
    print("\n[loop] Stop signal received. Finishing current iteration cleanly.", file=sys.stderr)


signal.signal(signal.SIGINT, _stop_handler)


def parse_ideas(ideas_md: pathlib.Path) -> list[dict]:
    """Parse OPTIMIZE_IDEAS.md for the top numbered list of ideas.

    Heuristic parse: looks for lines like `1. **idea-ref** — description`
    or `## 1. Title (idea-ref)` and a following allowlist block.
    """
    if not ideas_md.exists():
        return []
    text = ideas_md.read_text()
    ideas: list[dict] = []
    for m in re.finditer(r"^\s*(\d+)\.\s+\*\*([\w\-]+)\*\*\s*[—-]?\s*(.*?)(?=\n\s*\d+\.|$)",
                         text, flags=re.DOTALL | re.MULTILINE):
        idx, ref, body = m.group(1), m.group(2), m.group(3).strip()
        # Files: look for "files: <list>" or "Files: ..." block inside body
        files: list[str] = []
        files_match = re.search(r"(?im)^\s*files?:\s*(.+)$", body)
        if files_match:
            files = [f.strip() for f in re.split(r"[,;]", files_match.group(1)) if f.strip()]
        attempted = bool(re.search(r"(?im)^\s*attempted:\s*(yes|true|done|kept|discarded)", body))
        ideas.append({
            "index": int(idx),
            "ref": ref,
            "description": body.split("\n", 1)[0],
            "files": files,
            "attempted": attempted,
        })
    return ideas


def pick_next_idea() -> dict | None:
    ideas = parse_ideas(IDEAS_PATH)
    for idea in ideas:
        if not idea["attempted"]:
            return idea
    return None


def has_diff() -> bool:
    out = subprocess.check_output(["git", "status", "--porcelain"], cwd=str(ROOT)).decode()
    return bool(out.strip())


def has_committed_diff(base_branch: str) -> bool:
    out = subprocess.check_output(
        ["git", "rev-list", f"{base_branch}..HEAD"], cwd=str(ROOT)
    ).decode()
    return bool(out.strip())


def prompt_for_edit(idea: dict, branch: str) -> str:
    print()
    print("=" * 78)
    print(f"[loop] Iteration idea: {idea['ref']}")
    print(f"  Description: {idea['description']}")
    if idea["files"]:
        print(f"  Allowlist:   {', '.join(idea['files'])}")
    else:
        print("  Allowlist:   (no explicit files field; edit per idea description)")
    print(f"  Branch:      {branch}")
    print("=" * 78)
    print()
    print("Make the edit per the idea + allowlist, then `git add` + `git commit` on this branch.")
    print("Press ENTER when committed, or 'q' + ENTER to skip this idea.")
    try:
        line = input("> ").strip().lower()
    except EOFError:
        return "skip"
    return "skip" if line == "q" else "continue"


def mark_idea_attempted(idea: dict, decision: str, reason: str) -> None:
    """Append a one-line attempt log under the idea's section."""
    if not IDEAS_PATH.exists():
        return
    text = IDEAS_PATH.read_text()
    marker = f"\n\n> attempted: {decision} ({reason}, {time.strftime('%Y-%m-%d')})"
    pattern = rf"(\*\*{re.escape(idea['ref'])}\*\*.*?)(?=\n\s*\d+\.|$)"
    new_text, count = re.subn(pattern, lambda m: m.group(1).rstrip() + marker,
                              text, count=1, flags=re.DOTALL)
    if count:
        IDEAS_PATH.write_text(new_text)


def run_fixture(fixture: str, branch: str, port: int) -> dict:
    cmd = [
        sys.executable, str(ROOT / "scripts" / "autoresearch" / "run.py"),
        "--fixture", fixture,
        "--branch", branch,
        "--port", str(port),
    ]
    out = subprocess.check_output(cmd, cwd=str(ROOT))
    return json.loads(out.decode().strip().splitlines()[-1])


def compare_run(fixture: str, candidate_run_id: str) -> dict:
    cmd = [
        sys.executable, str(ROOT / "scripts" / "autoresearch" / "compare.py"),
        "--fixture", fixture,
        "--candidate-run", candidate_run_id,
    ]
    out = subprocess.check_output(cmd, cwd=str(ROOT))
    return json.loads(out.decode())


def discard_branch(branch: str, base: str) -> None:
    subprocess.run(["git", "checkout", base], cwd=str(ROOT), check=True)
    subprocess.run(["git", "branch", "-D", branch], cwd=str(ROOT), check=False)


def main() -> int:
    args = parse_args()
    iteration = 0
    cumulative_cost = 0.0
    base = args.base_branch

    while not _STOP and iteration < args.max_iterations and cumulative_cost < args.cost_budget_usd:
        idea = pick_next_idea()
        if idea is None:
            print("[loop] No unattempted ideas remain. Stopping.")
            break

        branch = f"autoresearch/iter-{iteration+1}-{idea['ref']}"
        subprocess.run(["git", "checkout", "-b", branch, base], cwd=str(ROOT), check=True)
        choice = prompt_for_edit(idea, branch)
        if choice == "skip":
            discard_branch(branch, base)
            mark_idea_attempted(idea, "skipped", "operator_skipped")
            iteration += 1
            continue
        if not has_committed_diff(base):
            print("[loop] No commits on branch — nothing to evaluate. Marking attempted.")
            discard_branch(branch, base)
            mark_idea_attempted(idea, "no_diff", "no_commits_on_branch")
            iteration += 1
            continue

        # Run candidate on Fixture A (fast proxy)
        try:
            cand = run_fixture("A", branch, args.port_base)
        except subprocess.CalledProcessError as exc:
            print(f"[loop] run.py crashed: {exc}")
            discard_branch(branch, base)
            mark_idea_attempted(idea, "crash", "run.py_failed")
            iteration += 1
            continue
        cumulative_cost += float(cand.get("cost_usd") or 0)

        verdict = compare_run("A", cand["run_id"])
        if verdict["decision"] != "keep":
            discard_branch(branch, base)
            mark_idea_attempted(idea, "discard", verdict["reason"])
            iteration += 1
            continue

        # Promotion to fixtures B–E
        promoted = True
        for fixture in ["B", "C", "D", "E"]:
            try:
                cand2 = run_fixture(fixture, branch, args.port_base + ord(fixture) - ord("A"))
            except subprocess.CalledProcessError as exc:
                print(f"[loop] promotion crash on {fixture}: {exc}")
                promoted = False
                break
            cumulative_cost += float(cand2.get("cost_usd") or 0)
            v2 = compare_run(fixture, cand2["run_id"])
            if v2["decision"] != "keep":
                print(f"[loop] regressed on fixture {fixture}: {v2['reason']}")
                promoted = False
                break

        if promoted:
            print(f"[loop] KEEP — idea {idea['ref']} promoted A→E. Leaving branch {branch} for review.")
            mark_idea_attempted(idea, "kept", "promoted_all_fixtures")
        else:
            discard_branch(branch, base)
            mark_idea_attempted(idea, "discard", "regressed_during_promotion")

        iteration += 1

    print(f"[loop] Done. iterations={iteration} cumulative_cost_usd={cumulative_cost:.2f}")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Autoresearch Karpathy loop (human-in-loop v1).")
    p.add_argument("--max-iterations", type=int, default=10)
    p.add_argument("--cost-budget-usd", type=float, default=10.0)
    p.add_argument("--base-branch", default="main")
    p.add_argument("--port-base", type=int, default=9876)
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())
