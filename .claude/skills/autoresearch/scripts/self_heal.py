#!/usr/bin/env python3
"""Self-healing diagnostic + remediation for autoresearch baseline failures.

Triggered by `baseline.py` when an iter's strict per-iter sanity gate fires.
Reads `seed_manifest.json` for the substrate contract; parses
`evidence_dir/feature_check.log` and seed_verify.py output for failure
signatures; applies mechanical fixes; returns a JSON record. Cheap (no
LLM calls), safe (catalogued patterns only auto-apply), observable
(every action logged), and structured (escalates with AskUserQuestion-shaped
`proposed_questions` when nothing matches).

Catalog (deterministic auto-apply):
  - missing-python-module: ModuleNotFoundError → pip-install into seed .venv
  - missing-pytest-plugin: PytestConfigWarning → pip-install plugin
  - seed-uncommitted: dirty seed working tree → commit divergence
  - seed-db-pollution: stale rows in Builder DB → DELETE catalogued tables
  - seed-forbidden-files: past-agent artifact files → rm

Heuristic (model-backed escalation — `applied=False` with `proposed_questions`):
  - seed-history-pollution: forbidden commit subjects in git log
  - unknown-error-signature: any error signature not in catalog
  - contract-drift: Builder CLI/API output shape changed

False fixes are worse than no fix. When the catalog doesn't match, the script
returns structured escalation context — the calling agent uses AskUserQuestion
to surface a bounded decision rather than dumping raw logs.

Usage (from baseline.py):
    res = run_self_heal(evidence_dir, seed_dir)
    if res["applied"]:
        # retry the iter
    elif res.get("proposed_questions"):
        # surface to operator via AskUserQuestion
    else:
        # genuine no-match; investigate manually

Usage (CLI):
    python3 .claude/skills/autoresearch/scripts/self_heal.py --evidence-dir DIR
    # exit 0 if fix applied, 1 if no match, 2 on escalation
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import pathlib
import re
import sqlite3
import subprocess
import sys
from collections.abc import Callable

SKILL_DIR = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = SKILL_DIR / "seed_manifest.json"

# Map pytest config-option names to the plugin packages that own them.
# Extend as patterns surface.
PYTEST_PLUGIN_FOR_OPTION = {
    "asyncio_mode": "pytest-asyncio",
    "anyio_mode": "anyio",
}


def _load_manifest(path: pathlib.Path = DEFAULT_MANIFEST) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _make_seed_writable(seed_dir: pathlib.Path) -> bool:
    try:
        subprocess.run(["chmod", "-R", "u+w", str(seed_dir)], check=True, timeout=10)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def _restore_seed_readonly(seed_dir: pathlib.Path) -> None:
    subprocess.run(["chmod", "-R", "a-w", str(seed_dir)], check=False, timeout=10)


def _pip_install_into_seed(seed_dir: pathlib.Path, packages: list[str]) -> tuple[bool, str]:
    """Install packages into seed `.venv` with chmod dance. Returns (ok, log)."""
    if not _make_seed_writable(seed_dir):
        return False, f"chmod -R u+w {seed_dir} failed"
    try:
        venv_py = seed_dir / ".venv" / "bin" / "python"
        if not venv_py.exists():
            return False, f"seed venv missing at {venv_py}"
        r = subprocess.run(
            [str(venv_py), "-m", "pip", "install", "-q", *packages],
            capture_output=True, text=True, timeout=180,
        )
        if r.returncode != 0:
            return False, f"pip install failed: {(r.stderr or r.stdout)[:400]}"
        return True, f"pip-installed {packages} into seed .venv"
    finally:
        _restore_seed_readonly(seed_dir)


def fix_missing_python_module(
    seed_dir: pathlib.Path, module: str
) -> dict:
    """Install the missing module into seed `.venv`. PyPI name often equals
    import name; map known aliases."""
    pypi_name = {
        "jinja2": "jinja2",
        "pytest_asyncio": "pytest-asyncio",
        # extend as patterns surface
    }.get(module, module)
    ok, log = _pip_install_into_seed(seed_dir, [pypi_name])
    return {
        "applied": ok,
        "pattern": "missing-python-module",
        "module": module,
        "package": pypi_name,
        "detail": log,
    }


def fix_missing_pytest_plugin(
    seed_dir: pathlib.Path, option: str
) -> dict:
    plugin = PYTEST_PLUGIN_FOR_OPTION.get(option)
    if not plugin:
        return {
            "applied": False,
            "pattern": "missing-pytest-plugin",
            "option": option,
            "detail": f"no plugin mapping for pytest option {option!r}; extend PYTEST_PLUGIN_FOR_OPTION",
        }
    ok, log = _pip_install_into_seed(seed_dir, [plugin])
    return {
        "applied": ok,
        "pattern": "missing-pytest-plugin",
        "option": option,
        "plugin": plugin,
        "detail": log,
    }


def fix_seed_uncommitted(seed_dir: pathlib.Path) -> dict:
    """Commit seed working-tree changes for tracked files outside `.venv/`
    and `.claude/`. Caller is responsible for verifying the changes are
    expected (this only auto-applies because the alternative is silently
    losing them on the next `git checkout` inside a Builder task workspace)."""
    if not _make_seed_writable(seed_dir):
        return {"applied": False, "pattern": "seed-uncommitted",
                "detail": f"chmod -R u+w {seed_dir} failed"}
    try:
        r = subprocess.run(
            ["git", "-C", str(seed_dir), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return {"applied": False, "pattern": "seed-uncommitted",
                    "detail": f"git status returned {r.returncode}"}
        dirty = [ln for ln in r.stdout.splitlines()
                 if ln and not ln[3:].startswith(".venv/")
                 and not ln[3:].startswith(".claude/")]
        if not dirty:
            return {"applied": False, "pattern": "seed-uncommitted",
                    "detail": "no tracked-file divergence; nothing to commit"}
        # Stage only the dirty tracked files (not .venv/.claude noise).
        files = [ln[3:].strip() for ln in dirty]
        subprocess.run(
            ["git", "-C", str(seed_dir), "add", *files],
            check=True, timeout=10,
        )
        subprocess.run(
            ["git", "-C", str(seed_dir), "commit",
             "-m", "self_heal: commit seed working-tree divergence"],
            check=True, capture_output=True, timeout=10,
        )
        return {"applied": True, "pattern": "seed-uncommitted",
                "files": files,
                "detail": f"committed {len(files)} file(s): {', '.join(files[:3])}"}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return {"applied": False, "pattern": "seed-uncommitted",
                "detail": f"{type(exc).__name__}: {exc}"}
    finally:
        _restore_seed_readonly(seed_dir)


def fix_seed_db_pollution(seed_dir: pathlib.Path, manifest: dict) -> dict:
    """Wipe Builder execution-state tables declared as must-be-empty in manifest.

    Mirrors run.py:restore_seed but is callable as a standalone remediation when
    seed_verify.py reports db.must_be_empty_tables violation. Deterministic:
    SQL DELETE on a catalogued, manifest-declared list.
    """
    db_rules = (manifest.get("pristine_invariants", {}) or {}).get("db", {})
    rel = db_rules.get("relative_path", ".agent-builder/agent_builder.db")
    tables = db_rules.get("must_be_empty_tables", [])
    db_path = seed_dir / rel
    if not db_path.exists():
        return {"applied": False, "pattern": "seed-db-pollution",
                "detail": f"no DB at {db_path}"}
    if not tables:
        return {"applied": False, "pattern": "seed-db-pollution",
                "detail": "manifest declared no must_be_empty_tables"}
    if not _make_seed_writable(seed_dir):
        return {"applied": False, "pattern": "seed-db-pollution",
                "detail": f"chmod -R u+w {seed_dir} failed"}
    wiped: list[dict] = []
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        try:
            cur = conn.cursor()
            for t in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {t}")
                    n_before = cur.fetchone()[0]
                    if n_before > 0:
                        cur.execute(f"DELETE FROM {t}")
                        wiped.append({"table": t, "rows_deleted": n_before})
                except sqlite3.Error:
                    continue
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {"applied": False, "pattern": "seed-db-pollution",
                "detail": f"DB error: {exc}"}
    finally:
        _restore_seed_readonly(seed_dir)
    if not wiped:
        return {"applied": False, "pattern": "seed-db-pollution",
                "detail": "no stale rows found"}
    return {"applied": True, "pattern": "seed-db-pollution",
            "wiped": wiped,
            "detail": f"DELETE'd {sum(w['rows_deleted'] for w in wiped)} rows across "
                      f"{len(wiped)} table(s)"}


def _git_tracked(seed_dir: pathlib.Path, rel_path: str) -> bool:
    """Returns True if rel_path is tracked in seed's git index."""
    if not (seed_dir / ".git").exists():
        return False
    try:
        r = subprocess.run(
            ["git", "-C", str(seed_dir), "ls-files", "--error-unmatch", rel_path],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def fix_seed_forbidden_files(seed_dir: pathlib.Path, manifest: dict,
                              upstream_source: str = "",
                              re_snapshot_cmd: str = "") -> dict:
    """Remediate forbidden_path_patterns matches in manifest.

    Decision tree (first-principles: never introduce new divergence to fix
    existing divergence):
      - File UNTRACKED: deterministic auto-rm (no git state change).
      - File TRACKED in seed git index: escalate. Removing tracked files
        creates a new working-tree divergence that requires either a new
        commit (further polluting history) or a hard-reset to a clean sha
        (operator decision). Either way, re-snapshot from upstream is the
        clean recovery — surface that as the proposed_question.
    """
    files_rules = (manifest.get("pristine_invariants", {}) or {}).get("files", {})
    patterns = files_rules.get("forbidden_path_patterns", [])
    if not patterns:
        return {"applied": False, "pattern": "seed-forbidden-files",
                "detail": "manifest declared no forbidden patterns"}
    hits: list[pathlib.Path] = []
    for found in seed_dir.rglob("*"):
        if not found.is_file():
            continue
        rel = found.relative_to(seed_dir).as_posix()
        if rel.startswith((".venv/", ".git/", "node_modules/", ".claude/")):
            continue
        for p in patterns:
            if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(found.name, p):
                hits.append(found)
                break
    if not hits:
        return {"applied": False, "pattern": "seed-forbidden-files",
                "detail": "no forbidden files found"}
    # Classify: tracked vs untracked.
    tracked: list[str] = []
    untracked: list[pathlib.Path] = []
    for h in hits:
        rel = h.relative_to(seed_dir).as_posix()
        if _git_tracked(seed_dir, rel):
            tracked.append(rel)
        else:
            untracked.append(h)
    # Auto-rm untracked (safe; no git state change).
    removed: list[str] = []
    if untracked:
        if _make_seed_writable(seed_dir):
            try:
                for h in untracked:
                    try:
                        h.unlink()
                        removed.append(h.relative_to(seed_dir).as_posix())
                    except OSError:
                        continue
            finally:
                _restore_seed_readonly(seed_dir)
    # If any forbidden file is TRACKED, escalate — re-snapshot is the
    # only clean recovery. Returning applied=False with proposed_questions
    # blocks the caller from blindly retrying; it must surface the decision.
    if tracked:
        return {
            "applied": False,
            "pattern": "seed-forbidden-files-tracked",
            "confidence": "high",
            "diagnosis": (
                f"{len(tracked)} forbidden file(s) are tracked in seed git index; "
                f"in-place rm would create new git divergence that must be either "
                f"committed (further pollution) or hard-reset (lost work risk). "
                f"Re-snapshot from upstream is the only clean recovery."
            ),
            "evidence": tracked,
            "untracked_removed": removed,
            "proposed_questions": [
                {
                    "header": "Forbidden file recovery",
                    "question": (
                        f"Seed has tracked forbidden files ({tracked[:3]}…). "
                        f"How should the skill recover?"
                    ),
                    "options": [
                        {
                            "label": ("Recapture from upstream"
                                       + (f" ({upstream_source})" if upstream_source else "")),
                            "description": (
                                (f"Run `{re_snapshot_cmd}`" if re_snapshot_cmd
                                  else "Re-snapshot the seed from the upstream source")
                                + ". Guaranteed pristine if upstream is clean."
                            ),
                        },
                        {
                            "label": "Hard-reset seed to a pre-pollution sha",
                            "description": "Operator picks the last clean sha from "
                                           "seed git log and resets there.",
                        },
                        {
                            "label": "Abort and investigate",
                            "description": "Operator inspects how these tracked files "
                                           "got into the seed.",
                        },
                    ],
                },
            ],
            "detail": "model-backed escalation — tracked files require operator-level recovery",
        }
    if removed:
        return {"applied": True, "pattern": "seed-forbidden-files",
                "removed": removed,
                "detail": f"rm'd {len(removed)} untracked forbidden file(s)"}
    return {"applied": False, "pattern": "seed-forbidden-files",
            "detail": f"found {len(hits)} files but neither tracked nor unlinkable"}


def detect_seed_history_pollution(seed_dir: pathlib.Path, manifest: dict) -> dict | None:
    """Returns escalation record if seed git log has commits matching any
    forbidden_commit_subject_pattern. NO auto-fix — re-snapshot is a model-
    backed decision (which sha is pristine?). Instead, returns structured
    proposed_questions for AskUserQuestion."""
    git_rules = (manifest.get("pristine_invariants", {}) or {}).get("git", {})
    patterns = git_rules.get("forbidden_commit_subject_patterns", [])
    if not patterns or not (seed_dir / ".git").exists():
        return None
    try:
        # HEAD-reachable only (matches seed_verify); stale branches are out
        # of scope for substrate-at-HEAD identity.
        r = subprocess.run(
            ["git", "-C", str(seed_dir), "log", "--format=%h %s", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    matches: list[str] = []
    compiled = [(p, re.compile(p)) for p in patterns]
    for line in (r.stdout or "").splitlines():
        for _, rx in compiled:
            if rx.search(line.split(" ", 1)[-1] if " " in line else line):
                matches.append(line)
                break
    if not matches:
        return None
    upstream = manifest.get("upstream_source", "~/Builder-Workspace/devpulse")
    re_snapshot_cmd = manifest.get("re_snapshot_command",
                                    "bash scripts/autoresearch/setup_seed.sh")
    return {
        "applied": False,
        "pattern": "seed-history-pollution",
        "confidence": "high",
        "diagnosis": f"seed git log contains {len(matches)} past-agent commit(s) "
                     f"matching manifest forbidden patterns",
        "evidence": matches[:8],
        "proposed_questions": [
            {
                "header": "Seed reset path",
                "question": (
                    f"Seed at {seed_dir} has past-agent commits baked into its "
                    f"git history. Pristine substrate is required for valid "
                    f"fixture testing. How should the skill recover?"
                ),
                "options": [
                    {
                        "label": f"Recapture from upstream ({upstream})",
                        "description": f"Run `{re_snapshot_cmd}` to re-snapshot from "
                                       f"{upstream}. Assumes upstream is pristine.",
                    },
                    {
                        "label": "Hard-reset seed to a specific pre-agent sha",
                        "description": "Operator inspects seed git log, picks the "
                                       "last clean sha, runs `git reset --hard <sha>`. "
                                       "Use when upstream itself is also polluted.",
                    },
                    {
                        "label": "Abort baseline and investigate manually",
                        "description": "No safe auto-recovery. Operator inspects "
                                       "seed git log + .seed/devpulse manually.",
                    },
                ],
            },
        ],
        "detail": "model-backed escalation — substrate identity requires operator decision",
    }


def detect_unknown_error_signature(log_path: pathlib.Path) -> dict | None:
    """Generic error-signature scan: ModuleNotFoundError/ImportError/sqlite3.Error/
    FileNotFoundError patterns that don't match a specific catalog entry.

    Returns a proposed-remediation record for the agent to consider; does NOT
    auto-apply (would risk false fixes on lookalike signatures). The agent
    decides via context whether to apply the proposed_action or escalate via
    AskUserQuestion.
    """
    if not log_path.exists():
        return None
    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        return None
    # Generic signatures that suggest a mechanical fix exists but the pattern
    # isn't in the explicit catalog yet.
    generic_signatures = [
        # (regex, hypothesis, confidence)
        (r"FileNotFoundError: \[Errno 2\] No such file or directory: ['\"]([^'\"]+)['\"]",
         "missing file/directory in seed", "medium"),
        (r"sqlite3\.OperationalError: (no such table|database is locked|attempt to write a readonly database): (\w+)",
         "DB schema or permission issue", "medium"),
        (r"ConnectionRefusedError|ConnectionError: .* port (\d+)",
         "service not running on expected port", "low"),
        (r"PermissionError: \[Errno 13\] Permission denied: ['\"]([^'\"]+)['\"]",
         "filesystem permission issue (likely seed chmod -R a-w boundary)", "medium"),
    ]
    matches = []
    for rx, hypothesis, conf in generic_signatures:
        m = re.search(rx, text)
        if m:
            matches.append({"signature": m.group(0)[:200],
                            "hypothesis": hypothesis,
                            "confidence": conf})
    if not matches:
        return None
    return {
        "applied": False,
        "pattern": "unknown-error-signature",
        "confidence": "medium",
        "diagnosis": f"{len(matches)} generic error signature(s) detected in feature_check.log; "
                     f"not in explicit catalog",
        "evidence": matches,
        "proposed_questions": [
            {
                "header": "Add to catalog?",
                "question": (
                    f"Detected error signature(s) not in self_heal catalog: "
                    f"{', '.join(m['hypothesis'] for m in matches[:3])}. "
                    f"Agent should investigate and decide whether to: "
                    f"(a) apply a proposed mechanical fix, "
                    f"(b) extend self_heal.py LOG_PATTERNS with a new entry, "
                    f"(c) escalate to operator."
                ),
                "options": [
                    {
                        "label": "Investigate signature and propose catalog entry",
                        "description": "Agent reads the full feature_check.log, "
                                       "identifies the precise pattern, drafts a "
                                       "new LOG_PATTERNS entry, validates fix is "
                                       "safe, then either applies or asks operator.",
                    },
                    {
                        "label": "Escalate to operator",
                        "description": "Surface the signature + log path to operator "
                                       "via AskUserQuestion. Use when the signature "
                                       "is genuinely ambiguous.",
                    },
                ],
            },
        ],
        "detail": "model-backed: agent should examine context, propose catalog extension, validate safety",
    }


# Regexes ordered by specificity — first match wins.
LOG_PATTERNS: list[tuple[str, str, Callable]] = [
    (
        "missing-python-module",
        r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]",
        lambda seed, match: fix_missing_python_module(seed, match.group(1)),
    ),
    (
        "missing-python-module-import",
        r"ImportError: ([\w_]+) must be installed",
        lambda seed, match: fix_missing_python_module(seed, match.group(1).lower()),
    ),
    (
        "missing-pytest-plugin",
        r"PytestConfigWarning: Unknown config option: (\w+)",
        lambda seed, match: fix_missing_pytest_plugin(seed, match.group(1)),
    ),
]


def diagnose_and_fix_from_log(
    log_path: pathlib.Path, seed_dir: pathlib.Path
) -> dict | None:
    if not log_path.exists():
        return None
    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        return None
    for entry in LOG_PATTERNS:
        regex, fixer = entry[1], entry[2]
        m = re.search(regex, text)
        if m:
            return fixer(seed_dir, m)
    return None


def run_self_heal(
    evidence_dir: pathlib.Path, seed_dir: pathlib.Path,
    manifest_path: pathlib.Path = DEFAULT_MANIFEST,
) -> dict:
    """Top-level remediation. Order of attempt:

    1. Catalogued log patterns (missing module / plugin) — deterministic fixes.
    2. Manifest substrate violations (db pollution, forbidden files) — deterministic.
    3. Seed uncommitted working-tree — deterministic.
    4. Seed history pollution — model-backed escalation (returns proposed_questions).
    5. Unknown error signatures — model-backed escalation (proposed_questions).
    6. Final fallback — return applied=False with bounded diagnosis.

    Always returns a dict with at least {applied: bool, pattern: str|None,
    detail: str}. When applied=False and the cause is non-trivial, includes
    `proposed_questions` (AskUserQuestion-shaped) so the calling agent can
    surface a structured decision instead of dumping logs.
    """
    log_path = evidence_dir / "feature_check.log"
    manifest = _load_manifest(manifest_path)

    # 1. Catalogued log patterns — strongest signal.
    result = diagnose_and_fix_from_log(log_path, seed_dir)
    if result and result.get("applied"):
        return result

    upstream = manifest.get("upstream_source", "")
    re_snap = manifest.get("re_snapshot_command", "")

    # 2. Manifest substrate violations — deterministic remediation where safe.
    db_fix = fix_seed_db_pollution(seed_dir, manifest)
    if db_fix.get("applied"):
        return db_fix
    files_fix = fix_seed_forbidden_files(seed_dir, manifest,
                                          upstream_source=upstream,
                                          re_snapshot_cmd=re_snap)
    # forbidden-files may auto-apply (untracked rm) OR escalate (tracked file).
    # Escalation propagates straight back to the caller.
    if files_fix.get("applied") or files_fix.get("proposed_questions"):
        return files_fix

    # 3. Seed uncommitted working tree — ESCALATE, do not auto-commit.
    # Auto-committing tracked-file changes (especially deletions of e.g.
    # __pycache__/*.pyc that setup_seed.sh strips) silently pollutes the
    # seed's git history with `self_heal: commit ...` commits. That's the
    # opposite of what we want: substrate identity must remain stable.
    # First-principles boundary: any tracked-file divergence requires
    # operator awareness — either re-snapshot (clean recovery) or knowing
    # acceptance of the new state. The previous fix_seed_uncommitted
    # auto-apply was an early heuristic, retired here in favour of the
    # structured escalation contract.
    if (seed_dir / ".git").exists():
        r = subprocess.run(
            ["git", "-C", str(seed_dir), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            dirty = [ln for ln in r.stdout.splitlines()
                     if ln
                     and not ln[3:].startswith(".venv/")
                     and not ln[3:].startswith(".claude/")
                     and "__pycache__/" not in ln[3:]
                     and not ln[3:].endswith(".pyc")]
            if dirty:
                return {
                    "applied": False,
                    "pattern": "seed-uncommitted-divergence",
                    "confidence": "high",
                    "diagnosis": (
                        f"seed has {len(dirty)} tracked file(s) diverging "
                        f"from HEAD. Auto-commit would pollute substrate "
                        f"history; auto-revert risks losing intentional "
                        f"changes. Operator decision required."
                    ),
                    "evidence": dirty[:10],
                    "proposed_questions": [
                        {
                            "header": "Seed divergence",
                            "question": (
                                f"Seed at {seed_dir} has tracked-file "
                                f"divergence ({len(dirty)} files). "
                                f"How to recover?"
                            ),
                            "options": [
                                {
                                    "label": "Re-snapshot from upstream",
                                    "description": (
                                        f"Run `{re_snap}` to recapture from "
                                        f"{upstream}. Cleanest recovery; "
                                        f"loses any intentional edits to seed."
                                    ),
                                },
                                {
                                    "label": "Hard-reset seed to HEAD",
                                    "description": (
                                        "git reset --hard inside seed; "
                                        "discards the divergence. Use when "
                                        "you know the changes are noise."
                                    ),
                                },
                                {
                                    "label": "Commit the divergence into upstream first",
                                    "description": (
                                        "If the changes are intentional, "
                                        "commit them upstream and re-snapshot "
                                        "so the seed's HEAD matches what's "
                                        "actually in working-tree."
                                    ),
                                },
                            ],
                        },
                    ],
                    "detail": "model-backed escalation — substrate divergence requires operator decision",
                }

    # 4. Seed history pollution — model-backed escalation.
    history_esc = detect_seed_history_pollution(seed_dir, manifest)
    if history_esc:
        return history_esc

    # 5. Unknown error signatures — model-backed escalation.
    unknown_esc = detect_unknown_error_signature(log_path)
    if unknown_esc:
        return unknown_esc

    # 6. Final fallback — bounded no-match record.
    return result or {
        "applied": False,
        "pattern": None,
        "confidence": "low",
        "detail": f"no known pattern matched in {log_path}",
        "proposed_questions": [
            {
                "header": "No pattern matched",
                "question": (
                    "self_heal exhausted catalog + manifest + generic signatures. "
                    "Calling agent should inspect evidence_dir and decide next step."
                ),
                "options": [
                    {
                        "label": "Inspect evidence_dir manually",
                        "description": f"Read {evidence_dir}/feature_check.log + "
                                       f"analyze.json + metrics.json + builder logs.",
                    },
                    {
                        "label": "Escalate to operator with full diagnosis",
                        "description": "Use AskUserQuestion to surface the failure "
                                       "with context. Operator picks recovery path.",
                    },
                ],
            },
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence-dir", required=True, type=pathlib.Path)
    p.add_argument("--seed-dir", required=True, type=pathlib.Path)
    p.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST)
    args = p.parse_args()
    res = run_self_heal(args.evidence_dir, args.seed_dir, args.manifest)
    print(json.dumps(res, indent=2))
    # Exit codes:
    #   0 — applied a fix (caller should retry)
    #   1 — no pattern matched (caller aborts)
    #   2 — escalation: structured proposed_questions returned (caller surfaces
    #       via AskUserQuestion rather than aborting)
    if res.get("applied"):
        return 0
    if res.get("proposed_questions"):
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
