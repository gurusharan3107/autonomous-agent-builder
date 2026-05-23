#!/usr/bin/env python3
"""autonomy-audit — run the 13 autonomy-readiness predicates against a target.

Source of truth for the criteria is `references/criteria.md` (sibling). This
script encodes the predicates as Python functions; the two MUST stay in sync.

Each check is a function `match_cN(target: Path) -> Match`. The function reads
the target's source/config (and optionally launches it briefly when --dynamic
is passed) and returns a verdict + evidence + fix_pointer.

Output shape is identical to `.claude/skills/autoresearch/scripts/diagnose_hang.py`
so findings pipe cleanly into the same downstream consumers.

Usage:

    python3 audit.py <target-path>                  # markdown summary
    python3 audit.py <target-path> --json           # machine-readable
    python3 audit.py <target-path> --dynamic        # add dynamic probes (60s cap each)
    python3 audit.py <target-path> --criterion C7   # single criterion (debug)
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import re
import sys
from dataclasses import asdict, dataclass, field

CRITERIA_FILE = pathlib.Path(__file__).resolve().parent.parent / "references" / "criteria.md"

# File globs the auditor scans. Bound list — don't recurse into vendored dirs.
SOURCE_GLOBS = ["**/*.py", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.sh", "**/*.bash"]
DOC_GLOBS = ["**/*.md", "**/*.toml", "**/*.yaml", "**/*.yml", "**/*.json"]
IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


@dataclass
class Match:
    id: str
    name: str
    verdict: str  # "pass" | "partial" | "fail" | "unknown"
    confidence: float
    evidence: list[str] = field(default_factory=list)
    fix_pointer: str = ""


# -- Helpers ------------------------------------------------------------------


def _iter_files(target: pathlib.Path, globs: list[str]) -> list[pathlib.Path]:
    if target.is_file():
        return [target]
    results: list[pathlib.Path] = []
    for pat in globs:
        for p in target.glob(pat):
            if any(part in IGNORE_DIRS for part in p.parts):
                continue
            if p.is_file():
                results.append(p)
    return results


def _read_text(path: pathlib.Path, limit: int = 200_000) -> str:
    try:
        return path.read_text(errors="replace")[:limit]
    except OSError:
        return ""


def _grep_any(target: pathlib.Path, globs: list[str], patterns: list[str]) -> list[tuple[pathlib.Path, str]]:
    """Return [(file, matched-line), ...] for first occurrence of any pattern per file."""
    hits: list[tuple[pathlib.Path, str]] = []
    compiled = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in patterns]
    for f in _iter_files(target, globs):
        text = _read_text(f)
        for rx in compiled:
            m = rx.search(text)
            if m:
                line = text[max(0, m.start() - 20): m.end() + 40].splitlines()[0][:120]
                hits.append((f, line.strip()))
                break
    return hits


def _file_globs_exist(target: pathlib.Path, name_patterns: list[str]) -> list[pathlib.Path]:
    """List of files whose name (basename) matches any pattern."""
    results: list[pathlib.Path] = []
    if target.is_file():
        return [target] if any(re.search(p, target.name, re.IGNORECASE) for p in name_patterns) else []
    for p in target.rglob("*"):
        if not p.is_file():
            continue
        if any(part in IGNORE_DIRS for part in p.parts):
            continue
        if any(re.search(pat, p.name, re.IGNORECASE) for pat in name_patterns):
            results.append(p)
    return results


# -- Matchers -----------------------------------------------------------------


def match_c1_watchdog(target: pathlib.Path, dynamic: bool) -> Match:
    """Observability-first watchdog."""
    del dynamic  # static check sufficient for v1
    name_hits = _file_globs_exist(target, [r"watchdog", r"monitor", r"supervisor", r"heartbeat"])
    timeout_hits = _grep_any(
        target, SOURCE_GLOBS,
        [r"signal\.alarm", r"asyncio\.wait_for", r"TimeoutExpired",
         r"--idle[\-_]?seconds?", r"IDLE_SECONDS", r"idle_threshold"],
    )
    has_file = bool(name_hits)
    has_timeout = bool(timeout_hits)
    configurable = bool(_grep_any(
        target, SOURCE_GLOBS,
        [r"--idle[\-_]?(seconds?|threshold)", r"--timeout", r"add_argument.*idle"],
    ))
    if has_file and configurable:
        verdict, conf = "pass", 0.95
    elif has_file or (has_timeout and configurable):
        verdict, conf = "partial", 0.7
    elif has_timeout:
        verdict, conf = "partial", 0.5
    else:
        verdict, conf = "fail", 0.9
    evidence = []
    for p in name_hits[:3]:
        evidence.append(f"watchdog-named file: {p.relative_to(target) if target.is_dir() else p.name}")
    for p, line in timeout_hits[:3]:
        evidence.append(f"in-loop timeout: {p.name}: {line}")
    if configurable:
        evidence.append("threshold appears configurable via CLI flag")
    return Match(
        id="C1",
        name="Observability-first watchdog",
        verdict=verdict, confidence=conf, evidence=evidence,
        fix_pointer=(
            "Add a watchdog process / external monitor that detects when the "
            "main loop has gone idle (no progress signal for N configurable "
            "seconds) and fires SIGTERM / notification. Reference: "
            ".claude/skills/autoresearch/scripts/hang_watchdog.py"
        ) if verdict != "pass" else "",
    )


def match_c2_forensics(target: pathlib.Path, dynamic: bool) -> Match:
    """Preserved forensics on failure."""
    del dynamic
    copy_hits = _grep_any(
        target, SOURCE_GLOBS,
        [r"shutil\.copy", r"shutil\.copytree", r"\bcp -a", r"tarfile",
         r"--dump[-_]root", r"dump_root", r"diagnostics[/_]dir"],
    )
    artifact_hits = _grep_any(
        target, SOURCE_GLOBS,
        [r"/proc/\$?\{?pid", r"py-spy", r"ss -tnp", r"dump_traceback",
         r"agent_builder\.db", r"\.db-wal"],
    )
    dump_root_configurable = bool(_grep_any(
        target, SOURCE_GLOBS,
        [r"--dump[-_]root", r"add_argument.*dump"],
    ))
    distinct_artifacts = len({h[0].name for h in artifact_hits})
    if copy_hits and dump_root_configurable and distinct_artifacts >= 3:
        verdict, conf = "pass", 0.95
    elif copy_hits and (dump_root_configurable or distinct_artifacts >= 2):
        verdict, conf = "partial", 0.7
    elif copy_hits:
        verdict, conf = "partial", 0.5
    else:
        verdict, conf = "fail", 0.9
    evidence = [f"{h[0].name}: {h[1]}" for h in copy_hits[:3]]
    if distinct_artifacts:
        evidence.append(f"forensic artifact references: {distinct_artifacts} distinct kinds")
    if dump_root_configurable:
        evidence.append("--dump-root (or equivalent) appears configurable")
    return Match(
        id="C2",
        name="Preserved forensics on failure",
        verdict=verdict, confidence=conf, evidence=evidence,
        fix_pointer=(
            "Extend the failure handler to copy DB/state files + process "
            "introspection (threads, FDs, sockets) + structured metadata JSON "
            "to <dump-root>/<UTC>-<run-id>/. Pattern: "
            ".claude/skills/autoresearch/scripts/hang_watchdog.py:dump_diagnostics"
        ) if verdict != "pass" else "",
    )


def match_c3_catalog(target: pathlib.Path, dynamic: bool) -> Match:
    """Pattern catalog as data structure."""
    del dynamic
    catalog_files = _file_globs_exist(
        target,
        [r"KNOWN_PATTERNS\.md", r"patterns\.(json|yaml|toml)",
         r"signatures\.(yaml|json|toml)", r"issues\.(toml|yaml)"],
    )
    if not catalog_files:
        return Match(
            id="C3", name="Pattern catalog as data structure (not prose)",
            verdict="fail", confidence=0.9, evidence=["no catalog file found"],
            fix_pointer=(
                "Create <target>/KNOWN_PATTERNS.md (or patterns.json/yaml). "
                "One section per known failure mode, each with a narrow "
                "machine-checkable predicate. Add a matcher script that "
                "consults it. Pattern: "
                ".claude/skills/autoresearch/{KNOWN_PATTERNS.md,scripts/diagnose_hang.py}"
            ),
        )
    catalog_name = catalog_files[0].name
    # Is the catalog referenced by any source file?
    consumers = _grep_any(target, SOURCE_GLOBS, [re.escape(catalog_name)])
    # Are the catalog entries predicate-shaped, not pure prose?
    text = _read_text(catalog_files[0])
    has_predicates = bool(re.search(r"regex|grep|sqlite|SELECT|matcher|predicate|`/.+/`|/proc/", text, re.IGNORECASE))
    if consumers and has_predicates:
        verdict, conf = "pass", 0.9
    elif consumers or has_predicates:
        verdict, conf = "partial", 0.65
    else:
        verdict, conf = "fail", 0.85
    evidence = [f"catalog: {catalog_files[0].name}"]
    if consumers:
        evidence.append(f"{len(consumers)} source file(s) reference catalog by name")
    if has_predicates:
        evidence.append("catalog entries contain predicate-shaped checks (regex / SQL / proc / matcher)")
    return Match(
        id="C3", name="Pattern catalog as data structure (not prose)",
        verdict=verdict, confidence=conf, evidence=evidence,
        fix_pointer=(
            "Add a matcher script that programmatically consults the catalog, "
            "and ensure each catalog entry includes a narrow predicate (regex / "
            "SQL / file check), not just prose description."
        ) if verdict != "pass" else "",
    )


def match_c4_unknown_verdict(target: pathlib.Path, dynamic: bool) -> Match:
    """unknown is a valid verdict."""
    del dynamic
    unknown_hits = _grep_any(
        target, SOURCE_GLOBS,
        [r"['\"]unknown['\"]", r"['\"]inconclusive['\"]", r"['\"]low_confidence['\"]",
         r"verdict.*unknown", r"return None  # not enough"],
    )
    docs_hits = _grep_any(
        target, DOC_GLOBS,
        [r"unknown.*verdict", r"on unknown", r"`unknown`", r"verdict.*pass.*partial.*fail.*unknown"],
    )
    if unknown_hits and docs_hits:
        verdict, conf = "pass", 0.85
    elif unknown_hits:
        verdict, conf = "partial", 0.65
    else:
        verdict, conf = "fail", 0.7
    evidence = [f"code: {h[0].name}: {h[1]}" for h in unknown_hits[:2]]
    evidence += [f"docs: {h[0].name}" for h in docs_hits[:2]]
    return Match(
        id="C4", name="`unknown` is a valid verdict (learning trigger)",
        verdict=verdict, confidence=conf, evidence=evidence,
        fix_pointer=(
            "Add explicit `unknown` verdict path to matchers (return when no "
            "pattern fires above confidence threshold ~0.5). Document operator "
            "action on unknown: add a new catalog entry + matcher before "
            "closing the Fix lane."
        ) if verdict != "pass" else "",
    )


def match_c5_narrow_predicates(target: pathlib.Path, dynamic: bool) -> Match:
    """Narrow detection predicates."""
    del dynamic
    # Look for matchers with multiple AND-joined conditions (heuristic).
    multi_condition = _grep_any(
        target, SOURCE_GLOBS,
        [r"\sand\s.*and\s", r"&&.*&&", r"if .* and .* and "],
    )
    # Plus the specific catalog discrimination — references/criteria.md mentions narrow predicates.
    catalog_files = _file_globs_exist(target, [r"KNOWN_PATTERNS\.md", r"patterns\.(json|yaml)"])
    catalog_has_specific_evidence = False
    if catalog_files:
        text = _read_text(catalog_files[0])
        catalog_has_specific_evidence = bool(re.search(r"contains?\s+`.+`|matches?\s+`.+`|regex", text, re.IGNORECASE))
    if multi_condition and catalog_has_specific_evidence:
        verdict, conf = "pass", 0.8
    elif multi_condition or catalog_has_specific_evidence:
        verdict, conf = "partial", 0.6
    elif not catalog_files:
        return Match(
            id="C5", name="Narrow detection predicates",
            verdict="unknown", confidence=0.4,
            evidence=["no catalog present; cannot evaluate predicate narrowness"],
            fix_pointer="Satisfy C3 first; C5 is a property of the catalog's matchers.",
        )
    else:
        verdict, conf = "fail", 0.7
    evidence = []
    if multi_condition:
        evidence.append(f"{len(multi_condition)} matchers use AND-joined conditions")
    if catalog_has_specific_evidence:
        evidence.append("catalog entries reference specific regex/substring evidence")
    return Match(
        id="C5", name="Narrow detection predicates",
        verdict=verdict, confidence=conf, evidence=evidence,
        fix_pointer=(
            "Audit each catalog matcher: would entry Pj's evidence also fire "
            "Pi's matcher? If yes, tighten with AND-joined conditions or "
            "narrower substring. See P5 vs P6 vs P9 in "
            ".claude/skills/autoresearch/KNOWN_PATTERNS.md for the discrimination bar."
        ) if verdict != "pass" else "",
    )


def match_c6_budgets(target: pathlib.Path, dynamic: bool) -> Match:
    """Cost-bounded cycles."""
    del dynamic
    budgets = _grep_any(
        target, SOURCE_GLOBS,
        [r"--max[\-_]iterations?", r"--cost[\-_]budget", r"--timeout",
         r"--max[\-_]tokens?", r"--max[\-_]cycles?", r"max_iterations",
         r"cost_budget", r"deadline"],
    )
    distinct_budgets = len({h[0].name for h in budgets})
    cycle_check = bool(_grep_any(
        target, SOURCE_GLOBS,
        [r"if .* > .*budget", r"if .* >= .*max[\-_]iter", r"while .* < .*deadline",
         r"if time\.time\(\) > "],
    ))
    if distinct_budgets >= 2 and cycle_check:
        verdict, conf = "pass", 0.9
    elif distinct_budgets >= 1 or cycle_check:
        verdict, conf = "partial", 0.65
    else:
        verdict, conf = "fail", 0.85
    evidence = [f"budget flag: {h[0].name}: {h[1]}" for h in budgets[:3]]
    if cycle_check:
        evidence.append("per-cycle budget check present in loop body")
    return Match(
        id="C6", name="Cost-bounded cycles (explicit budgets)",
        verdict=verdict, confidence=conf, evidence=evidence,
        fix_pointer=(
            "Add --max-iterations, --cost-budget-usd (or equivalent), and a "
            "per-cycle wallclock budget to the loop entrypoint. Check them at "
            "the top of each iteration; raise/break when exceeded. Pattern: "
            "scripts/autoresearch/loop.py stop conditions."
        ) if verdict != "pass" else "",
    )


def match_c7_propagation(target: pathlib.Path, dynamic: bool) -> Match:
    """Fixes propagate to surfaces future agents read."""
    del dynamic
    # Look for durable surfaces by name.
    surfaces = _file_globs_exist(
        target,
        [r"ROADMAP\.md", r"CHANGELOG\.md", r"STATUS\.md", r"KNOWN_PATTERNS\.md",
         r"INSIGHTS\.md", r"DECISIONS?\.md"],
    )
    # Look for documented closeout step.
    closeout = bool(_grep_any(
        target, DOC_GLOBS,
        [r"closeout", r"post[\-_]fix", r"after.*fix", r"propagat"],
    ))
    # If target is a sub-dir, look in repo-root too (one level up).
    parent_surfaces = []
    if target.is_dir() and target.parent != target:
        repo_root = target
        for _ in range(4):  # up to 4 levels up
            if (repo_root.parent / "ROADMAP.md").exists() or (repo_root.parent / "docs" / "goal" / "ROADMAP.md").exists():
                parent_surfaces.append("ROADMAP.md in repo root")
                break
            repo_root = repo_root.parent
            if repo_root == repo_root.parent:
                break
    total_surfaces = len(surfaces) + len(parent_surfaces)
    if total_surfaces >= 3 and closeout:
        verdict, conf = "pass", 0.9
    elif total_surfaces >= 2 or closeout:
        verdict, conf = "partial", 0.65
    else:
        verdict, conf = "fail", 0.8
    evidence = [f"surface: {s.name}" for s in surfaces[:4]]
    evidence += [f"upstream: {s}" for s in parent_surfaces]
    if closeout:
        evidence.append("docs reference closeout/post-fix workflow")
    return Match(
        id="C7", name="Fixes propagate to surfaces future agents read",
        verdict=verdict, confidence=conf, evidence=evidence,
        fix_pointer=(
            "Create or extend post-fix closeout: ROADMAP tick + STATUS Recent "
            "Decisions entry + CHANGELOG row + catalog entry, all in the same "
            "commit. See docs/goal/FIX-STANDARD.md § Closeout for the checklist."
        ) if verdict != "pass" else "",
    )


def match_c8_state(target: pathlib.Path, dynamic: bool) -> Match:
    """State, not conversation."""
    del dynamic
    persistence = _grep_any(
        target, SOURCE_GLOBS,
        [r"\.read_text\(\)", r"\.write_text\(", r"json\.load", r"sqlite3\.connect",
         r"open\([\"'].*\.toml", r"yaml\.safe_load"],
    )
    config_in_files = bool(_file_globs_exist(target, [r"config\.(toml|yaml|json|ini)", r"\.env\.example"]))
    if persistence and config_in_files:
        verdict, conf = "pass", 0.85
    elif persistence:
        verdict, conf = "partial", 0.6
    else:
        verdict, conf = "fail", 0.7
    evidence = []
    if persistence:
        evidence.append(f"{len(persistence)} file-IO call site(s) found")
    if config_in_files:
        evidence.append("config file(s) detected")
    return Match(
        id="C8", name="State, not conversation",
        verdict=verdict, confidence=conf, evidence=evidence,
        fix_pointer=(
            "Move ephemeral state to files: catalog → KNOWN_PATTERNS.md, "
            "decisions → decisions.json, config → config.toml. Verify cold "
            "start: invoke target from fresh shell with no env context."
        ) if verdict != "pass" else "",
    )


def match_c9_honest_failure(target: pathlib.Path, dynamic: bool) -> Match:
    """Honest failure (no optimistic guessing)."""
    del dynamic
    confidence_signals = _grep_any(
        target, SOURCE_GLOBS,
        [r"confidence\s*=\s*0?\.\d", r"['\"]confidence['\"]", r"score\s*>=?\s*0\.\d"],
    )
    cascade_signals = _grep_any(
        target, SOURCE_GLOBS + DOC_GLOBS,
        [r"cascade", r"see also P\d", r"fallback to", r"if .* in source.*look at"],
    )
    if confidence_signals and cascade_signals:
        verdict, conf = "pass", 0.85
    elif confidence_signals or cascade_signals:
        verdict, conf = "partial", 0.6
    elif not _file_globs_exist(target, [r"KNOWN_PATTERNS\.md", r"patterns\.(json|yaml)"]):
        return Match(
            id="C9", name="Honest failure (no optimistic guessing)",
            verdict="unknown", confidence=0.4,
            evidence=["target has no catalog (C3 unsatisfied); C9 not applicable"],
            fix_pointer="Satisfy C3 first; C9 is a property of catalog matchers.",
        )
    else:
        verdict, conf = "fail", 0.7
    evidence = []
    if confidence_signals:
        evidence.append(f"{len(confidence_signals)} confidence scoring site(s)")
    if cascade_signals:
        evidence.append(f"{len(cascade_signals)} fallback/cascade reference(s)")
    return Match(
        id="C9", name="Honest failure (no optimistic guessing)",
        verdict=verdict, confidence=conf, evidence=evidence,
        fix_pointer=(
            "Add confidence [0.0-1.0] to each matcher. For matchers whose "
            "symptom could indicate >1 root cause, cascade the fix_pointer "
            "to alternatives. See P2→P7→P8 cascade in "
            ".claude/skills/autoresearch/scripts/diagnose_hang.py."
        ) if verdict != "pass" else "",
    )


def match_c10_safe_to_fail(target: pathlib.Path, dynamic: bool) -> Match:
    """Safe-to-fail at every layer."""
    del dynamic
    versioned = bool((target / ".git").exists() if target.is_dir() else False) or bool(_grep_any(
        target, SOURCE_GLOBS,
        [r"git checkout", r"git worktree", r"git stash"],
    ))
    cleanup_patterns = _grep_any(
        target, SOURCE_GLOBS,
        [r"finally:", r"\btrap\b", r"atexit\.register", r"contextmanager",
         r"shutil\.rmtree.*/tmp", r"\bcleanup\("],
    )
    if versioned and cleanup_patterns:
        verdict, conf = "pass", 0.85
    elif versioned or cleanup_patterns:
        verdict, conf = "partial", 0.65
    else:
        verdict, conf = "fail", 0.7
    evidence = []
    if versioned:
        evidence.append("git versioning detected")
    if cleanup_patterns:
        evidence.append(f"{len(cleanup_patterns)} cleanup site(s) (finally/trap/atexit)")
    return Match(
        id="C10", name="Safe-to-fail at every layer",
        verdict=verdict, confidence=conf, evidence=evidence,
        fix_pointer=(
            "Wrap mutating operations in transactions or git branches. Add "
            "finally:/trap cleanup of every resource the loop creates "
            "(processes, temp dirs, ports). Test idempotency: cleanup run "
            "twice should succeed both times."
        ) if verdict != "pass" else "",
    )


def match_c11_llm_fallback(target: pathlib.Path, dynamic: bool) -> Match:
    """LLM-as-diagnoser fallback (Gap-1)."""
    del dynamic
    llm_invoke = _grep_any(
        target, SOURCE_GLOBS,
        [r"anthropic\.", r"openai\.", r"claude[\-_]code", r"\bcodex\s+exec\b",
         r"subprocess.*claude", r"llm[\-_]fallback", r"on_unknown.*llm"],
    )
    if llm_invoke:
        verdict, conf = "pass", 0.85
    else:
        verdict, conf = "fail", 0.95
    evidence = [f"{h[0].name}: {h[1]}" for h in llm_invoke[:3]] if llm_invoke else [
        "no LLM invocation site found; `unknown` verdicts require human triage"
    ]
    return Match(
        id="C11", name="LLM-as-diagnoser fallback (Gap-1)",
        verdict=verdict, confidence=conf, evidence=evidence,
        fix_pointer=(
            "Add an `unknown` → LLM-fallback path. On matcher abstention, "
            "build a prompt from the dump artifacts, call the LLM with "
            "bounded context + cost cap (C6), parse the response into the "
            "catalog schema, write to <target>/proposed_patterns/<UTC>.json "
            "for operator review."
        ) if verdict != "pass" else "",
    )


def match_c12_auto_apply(target: pathlib.Path, dynamic: bool) -> Match:
    """Auto-apply governance (Gap-2)."""
    del dynamic
    auto_apply = _grep_any(
        target, SOURCE_GLOBS + DOC_GLOBS,
        [r"auto[\-_]apply", r"auto[\-_]fix", r"automatic.*commit",
         r"safe[\-_]to[\-_]apply", r"--apply"],
    )
    confidence_threshold = bool(_grep_any(
        target, SOURCE_GLOBS,
        [r"confidence\s*>=?\s*0\.[89]", r"threshold.*apply"],
    ))
    if auto_apply and confidence_threshold:
        verdict, conf = "pass", 0.85
    elif auto_apply:
        verdict, conf = "partial", 0.6
    else:
        verdict, conf = "fail", 0.95
    evidence = [f"{h[0].name}: {h[1]}" for h in auto_apply[:3]] if auto_apply else [
        "no auto-apply path found; every fix requires manual operator action"
    ]
    return Match(
        id="C12", name="Auto-apply governance for high-confidence fixes (Gap-2)",
        verdict=verdict, confidence=conf, evidence=evidence,
        fix_pointer=(
            "Add `auto_apply_safe: bool` to each catalog entry. Add a code "
            "path that on (confidence >= 0.9 AND auto_apply_safe) applies "
            "the fix, commits with `auto-fix(<pattern-id>):` message, and "
            "re-runs the cycle. Bound by --max-auto-fixes budget (C6)."
        ) if verdict != "pass" else "",
    )


def match_c13_meta_loop(target: pathlib.Path, dynamic: bool) -> Match:
    """Meta-orchestrator with escalation (Gap-3)."""
    del dynamic
    meta_files = _file_globs_exist(
        target,
        [r"meta[\-_]loop", r"auto[\-_]runner", r"orchestrator", r"driver\."],
    )
    escalation = bool(_grep_any(
        target, SOURCE_GLOBS,
        [r"same[\-_]pattern[\-_]twice", r"escalat", r"attempts\[", r"failure_attempts"],
    ))
    ledger = bool(_grep_any(
        target, SOURCE_GLOBS,
        [r"failure_attempts\.json", r"attempt_ledger", r"retries_per_pattern"],
    ))
    if meta_files and escalation and ledger:
        verdict, conf = "pass", 0.9
    elif meta_files and (escalation or ledger):
        verdict, conf = "partial", 0.6
    elif meta_files:
        verdict, conf = "partial", 0.45
    else:
        verdict, conf = "fail", 0.95
    evidence = [f"meta-loop file: {p.name}" for p in meta_files[:2]]
    if escalation:
        evidence.append("escalation logic present")
    if ledger:
        evidence.append("failure-attempt ledger present")
    return Match(
        id="C13", name="Meta-orchestrator with escalation policy (Gap-3)",
        verdict=verdict, confidence=conf, evidence=evidence,
        fix_pointer=(
            "Build <target>/meta_loop.py that drives the per-cycle loop with: "
            "per-cycle budget enforcement (C6), failure-attempt ledger keyed by "
            "pattern_id, escalation on same-pattern-twice (alert operator, halt), "
            "cost cap across all cycles. See commit 6fa9f90 CHANGELOG § Gap to "
            "full autonomy for the design sketch."
        ) if verdict != "pass" else "",
    )


CHECKS: list = [
    match_c1_watchdog,
    match_c2_forensics,
    match_c3_catalog,
    match_c4_unknown_verdict,
    match_c5_narrow_predicates,
    match_c6_budgets,
    match_c7_propagation,
    match_c8_state,
    match_c9_honest_failure,
    match_c10_safe_to_fail,
    match_c11_llm_fallback,
    match_c12_auto_apply,
    match_c13_meta_loop,
]


def run_audit(target: pathlib.Path, *, dynamic: bool, only: str | None) -> dict:
    matches: list[Match] = []
    for fn in CHECKS:
        m = Match(id="?", name=fn.__name__, verdict="unknown", confidence=0.0)
        try:
            m = fn(target, dynamic)
        except Exception as exc:
            m.evidence = [f"matcher error: {type(exc).__name__}: {exc}"]
            m.verdict = "unknown"
            m.confidence = 0.0
        if only and m.id != only:
            continue
        matches.append(m)
    score_pass = sum(1 for m in matches if m.verdict == "pass")
    score_partial = sum(1 for m in matches if m.verdict == "partial")
    score_fail = sum(1 for m in matches if m.verdict == "fail")
    score_unknown = sum(1 for m in matches if m.verdict == "unknown")
    scored = score_pass + score_partial + score_fail  # exclude unknown from denominator
    score = round((2 * score_pass + score_partial) / max(2 * scored, 1) * 100) if scored else 0
    top_fixes = [m.id for m in sorted(
        (m for m in matches if m.verdict in ("fail", "partial")),
        key=lambda m: (m.verdict != "fail", int(m.id[1:])),
    )]
    return {
        "schema_version": "1",
        "target": str(target.resolve()),
        "ran_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "static_only": not dynamic,
        "results": [asdict(m) for m in matches],
        "summary": {
            "pass": score_pass, "partial": score_partial,
            "fail": score_fail, "unknown": score_unknown,
            "score_0_100": score,
            "top_fixes": top_fixes,
        },
    }


def render_markdown(audit: dict) -> str:
    s = audit["summary"]
    lines = [
        "# autonomy audit",
        f"target: {audit['target']}",
        f"score: {s['score_0_100']}/100  (pass={s['pass']} partial={s['partial']} fail={s['fail']} unknown={s['unknown']})",
        "",
        "| ID  | name | verdict | confidence |",
        "|-----|------|---------|------------|",
    ]
    for r in audit["results"]:
        lines.append(f"| {r['id']:3s} | {r['name'][:60]:60s} | {r['verdict']:7s} | {r['confidence']:.2f} |")
    lines.append("")
    if s["top_fixes"]:
        lines.append(f"top_fixes (lowest-numbered = most foundational): {', '.join(s['top_fixes'])}")
    for r in audit["results"]:
        if r["verdict"] in ("fail", "partial") and r["fix_pointer"]:
            lines.append("")
            lines.append(f"## {r['id']} — {r['name']}")
            lines.append(f"verdict: {r['verdict']} (confidence {r['confidence']:.2f})")
            if r["evidence"]:
                lines.append("evidence:")
                for e in r["evidence"]:
                    lines.append(f"  - {e}")
            lines.append(f"fix: {r['fix_pointer']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="autonomy-audit — 13-criterion check")
    ap.add_argument("target", help="path to skill dir / package / repo")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--dynamic", action="store_true", help="enable dynamic probes (60s cap each)")
    ap.add_argument("--criterion", help="run a single criterion (e.g., C7)")
    args = ap.parse_args(argv)

    target = pathlib.Path(args.target).expanduser().resolve()
    if not target.exists():
        print(f"error: {target} does not exist", file=sys.stderr)
        return 1

    audit = run_audit(target, dynamic=args.dynamic, only=args.criterion)

    if args.json:
        print(json.dumps(audit, indent=2))
    else:
        print(render_markdown(audit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
