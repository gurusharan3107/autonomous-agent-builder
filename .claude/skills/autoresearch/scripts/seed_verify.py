#!/usr/bin/env python3
"""Seed manifest verifier — checks SEED_DST against seed_manifest.json.

Single source of truth: `.claude/skills/autoresearch/seed_manifest.json`.
This script verifies; `self_heal.py` remediates. Both read the same manifest.

Returns JSON. Exit 0 on conformance, 1 on any violation.

Usage:
  python3 .claude/skills/autoresearch/scripts/seed_verify.py
  python3 .claude/skills/autoresearch/scripts/seed_verify.py --seed-dir ~/.seed/devpulse --json
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys

SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = SKILL_DIR / "seed_manifest.json"


def _expand(p: str) -> pathlib.Path:
    return pathlib.Path(os.path.expanduser(p))


def _load_manifest(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def _safe_git(seed_dir: pathlib.Path, args: list[str], timeout: int = 30
              ) -> tuple[bool, str]:
    """Run a git command against seed_dir with timeout. Returns (ok, stdout).
    On timeout/error, returns (False, error_message). Never raises."""
    try:
        r = subprocess.run(
            ["git", "-C", str(seed_dir), *args],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode != 0:
            return False, f"git exit {r.returncode}: {(r.stderr or '')[:200]}"
        return True, r.stdout
    except subprocess.TimeoutExpired:
        return False, f"git timed out after {timeout}s (seed may be under heavy I/O)"
    except (FileNotFoundError, OSError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


def verify_git(seed_dir: pathlib.Path, rules: dict) -> list[dict]:
    """Check git working-tree + commit-subject invariants.

    Each clause is independently isolated — a timeout on one does not skip the
    others. Slow seed git (Builder concurrent I/O) still produces a partial
    report with `warn` on the blocked clause(s) rather than no output at all.
    """
    out: list[dict] = []
    if not (seed_dir / ".git").exists():
        return [{"clause": "git", "status": "skip", "detail": "seed is not a git repo"}]
    # Working-tree clean — slow when seed has many untracked .venv files; use 30s
    if rules.get("working_tree_must_be_clean"):
        ok, stdout = _safe_git(seed_dir, ["status", "--porcelain"], timeout=30)
        if not ok:
            out.append({"clause": "git.working_tree_must_be_clean",
                        "status": "warn", "detail": stdout,
                        "remediation_hint": "retry when seed I/O is quiet"})
        else:
            # Exclude noise that churns independently of substrate identity:
            # .venv (Python virtualenv files), .claude (skill workspace), and
            # any __pycache__/*.pyc (Python bytecode regenerates per pytest run).
            dirty = [ln for ln in stdout.splitlines()
                     if ln
                     and not ln[3:].startswith(".venv/")
                     and not ln[3:].startswith(".claude/")
                     and "__pycache__/" not in ln[3:]
                     and not ln[3:].endswith(".pyc")]
            if dirty:
                out.append({
                    "clause": "git.working_tree_must_be_clean",
                    "status": "fail",
                    "detail": f"{len(dirty)} tracked file(s) diverge from HEAD",
                    "evidence": dirty[:5],
                    "remediation_hint": "self_heal pattern: seed-uncommitted",
                })
            else:
                out.append({"clause": "git.working_tree_must_be_clean", "status": "pass"})
    # Forbidden commit-subject patterns. Check HEAD-reachable history only,
    # not `--all`. The seed's substrate identity is defined by what's currently
    # checked out, not by what exists in stale branch refs / reflog. Stale
    # branches are independently a concern (max_total_commits caps unbounded
    # growth) but they don't invalidate the substrate at HEAD.
    forbidden = rules.get("forbidden_commit_subject_patterns", [])
    if forbidden:
        ok, stdout = _safe_git(seed_dir, ["log", "--format=%s", "HEAD"], timeout=15)
        if not ok:
            out.append({"clause": "git.forbidden_commit_subject_patterns",
                        "status": "warn", "detail": stdout,
                        "remediation_hint": "retry when seed I/O is quiet"})
        else:
            subjects = stdout.splitlines()
            matches: list[tuple[str, str]] = []  # (pattern, subject)
            for pat in forbidden:
                try:
                    rx = re.compile(pat)
                except re.error:
                    continue
                for s in subjects:
                    if rx.search(s):
                        matches.append((pat, s))
            if matches:
                out.append({
                    "clause": "git.forbidden_commit_subject_patterns",
                    "status": "fail",
                    "detail": f"{len(matches)} past-agent commit(s) in seed git log",
                    "evidence": [{"pattern": p, "subject": s} for p, s in matches[:8]],
                    "remediation_hint": "self_heal pattern: seed-history-pollution (escalates — needs re-snapshot)",
                })
            else:
                out.append({
                    "clause": "git.forbidden_commit_subject_patterns",
                    "status": "pass",
                    "detail": f"none of {len(forbidden)} forbidden pattern(s) matched any of {len(subjects)} commit subjects",
                })
    # Max commit count (defense against unbounded history accumulation).
    # Use HEAD-reachable count, matching the forbidden-pattern scope.
    max_commits = rules.get("max_total_commits")
    if max_commits is not None:
        ok, stdout = _safe_git(seed_dir, ["rev-list", "--count", "HEAD"], timeout=15)
        if not ok:
            out.append({"clause": "git.max_total_commits",
                        "status": "warn", "detail": stdout})
        else:
            try:
                count = int(stdout.strip())
            except ValueError:
                count = -1
            if count > max_commits:
                out.append({
                    "clause": "git.max_total_commits",
                    "status": "fail",
                    "detail": f"seed has {count} commits; manifest caps at {max_commits}",
                    "remediation_hint": "re-snapshot from upstream or hard-reset to pristine sha",
                })
            else:
                out.append({"clause": "git.max_total_commits", "status": "pass",
                            "detail": f"{count} commits (cap {max_commits})"})
    return out


def verify_deps(seed_dir: pathlib.Path, rules: dict) -> list[dict]:
    """Check seed .venv has required modules importable + pytest collects."""
    out: list[dict] = []
    venv_py = seed_dir / ".venv" / "bin" / "python"
    if not venv_py.exists():
        return [{"clause": "deps", "status": "skip", "detail": f"no .venv at {venv_py}"}]
    required = rules.get("venv_required_modules", [])
    missing: list[str] = []
    for mod in required:
        r = subprocess.run(
            [str(venv_py), "-c", f"import {mod}"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            missing.append(mod)
    if missing:
        out.append({
            "clause": "deps.venv_required_modules",
            "status": "fail",
            "detail": f"{len(missing)} module(s) not importable: {missing}",
            "evidence": missing,
            "remediation_hint": "self_heal pattern: missing-python-module (auto-pip-install)",
        })
    else:
        out.append({
            "clause": "deps.venv_required_modules",
            "status": "pass",
            "detail": f"all {len(required)} required modules importable",
        })
    if rules.get("pytest_must_collect"):
        tests_dir = seed_dir / "tests"
        if not tests_dir.exists():
            out.append({"clause": "deps.pytest_must_collect", "status": "skip",
                        "detail": "no tests/ dir"})
        else:
            r = subprocess.run(
                [str(venv_py), "-m", "pytest", str(tests_dir), "--collect-only", "-q",
                 "--ignore-glob=*playwright*", "--ignore-glob=*test_github*"],
                capture_output=True, text=True, timeout=60, cwd=str(seed_dir),
            )
            if r.returncode != 0:
                tail = ((r.stderr or "") + (r.stdout or "")).strip().splitlines()
                sig = next((ln for ln in tail
                            if "ModuleNotFoundError" in ln or "ImportError" in ln
                            or ln.startswith("ERROR")), tail[-1] if tail else "unknown")
                out.append({
                    "clause": "deps.pytest_must_collect",
                    "status": "fail",
                    "detail": f"pytest --collect-only failed: {sig[:200]}",
                    "remediation_hint": "self_heal will parse signature and pip-install missing module/plugin",
                })
            else:
                out.append({"clause": "deps.pytest_must_collect", "status": "pass"})
    return out


def verify_db(seed_dir: pathlib.Path, rules: dict) -> list[dict]:
    """Check Builder DB tables that must be empty in pristine state."""
    db_path = seed_dir / rules.get("relative_path", ".agent-builder/agent_builder.db")
    if not db_path.exists():
        return [{"clause": "db", "status": "skip", "detail": f"no DB at {db_path}"}]
    tables = rules.get("must_be_empty_tables", [])
    non_empty: list[dict] = []
    try:
        # Open read-only via URI mode to avoid creating journal/WAL files
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as exc:
        return [{"clause": "db", "status": "warn",
                 "detail": f"cannot open DB: {exc}"}]
    try:
        cur = conn.cursor()
        for t in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                n = cur.fetchone()[0]
            except sqlite3.Error:
                continue  # table may not exist in some Builder schemas
            if n > 0:
                non_empty.append({"table": t, "rows": n})
    finally:
        conn.close()
    if non_empty:
        return [{
            "clause": "db.must_be_empty_tables",
            "status": "fail",
            "detail": f"{len(non_empty)} table(s) have stale rows",
            "evidence": non_empty[:8],
            "remediation_hint": "self_heal pattern: seed-db-pollution (auto-DELETE)",
        }]
    return [{"clause": "db.must_be_empty_tables", "status": "pass",
             "detail": f"all {len(tables)} tables empty"}]


def verify_files(seed_dir: pathlib.Path, rules: dict) -> list[dict]:
    """Check no forbidden-pattern files exist in seed."""
    patterns = rules.get("forbidden_path_patterns", [])
    if not patterns:
        return []
    hits: list[str] = []
    for p in patterns:
        # Search seed for any path matching glob pattern
        for found in seed_dir.rglob("*"):
            rel = found.relative_to(seed_dir).as_posix()
            # Skip noise dirs
            if rel.startswith((".venv/", ".git/", "node_modules/", ".claude/")):
                continue
            if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(found.name, p):
                hits.append(rel)
    if hits:
        return [{
            "clause": "files.forbidden_path_patterns",
            "status": "fail",
            "detail": f"{len(hits)} past-agent artifact file(s) in seed",
            "evidence": hits[:10],
            "remediation_hint": "self_heal pattern: seed-forbidden-files (auto-rm)",
        }]
    return [{"clause": "files.forbidden_path_patterns", "status": "pass"}]


def verify_seed(seed_dir: pathlib.Path, manifest: dict) -> dict:
    inv = manifest.get("pristine_invariants", {})
    findings: list[dict] = []
    findings.extend(verify_git(seed_dir, inv.get("git", {})))
    findings.extend(verify_deps(seed_dir, inv.get("deps", {})))
    findings.extend(verify_db(seed_dir, inv.get("db", {})))
    findings.extend(verify_files(seed_dir, inv.get("files", {})))
    overall = "fail" if any(f.get("status") == "fail" for f in findings) else (
        "warn" if any(f.get("status") == "warn" for f in findings) else "pass"
    )
    return {
        "overall": overall,
        "seed_dir": str(seed_dir),
        "manifest": str(DEFAULT_MANIFEST),
        "findings": findings,
        "remediation_summary": [f for f in findings if f.get("status") == "fail"
                                and f.get("remediation_hint")],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed-dir", type=pathlib.Path, default=None,
                   help="defaults to seed_dir from manifest")
    p.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    manifest = _load_manifest(args.manifest)
    seed_dir = args.seed_dir or _expand(manifest["seed_dir"])
    report = verify_seed(seed_dir, manifest)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        glyph = {"pass": "✓", "warn": "⚠", "fail": "✗", "skip": "—"}
        print(f"seed_verify: {glyph[report['overall']]} {report['overall'].upper()}  "
              f"seed={report['seed_dir']}")
        for f in report["findings"]:
            print(f"  [{glyph.get(f.get('status', 'warn'), '?')}] {f['clause']}: "
                  f"{f.get('detail', '')}")
            if f.get("remediation_hint"):
                print(f"      remediation: {f['remediation_hint']}")
    return 0 if report["overall"] != "fail" else 1


if __name__ == "__main__":
    sys.exit(main())
