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
import os
import pathlib
import re
import shutil
import subprocess
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
    model_graded: bool = False  # True when verdict came from --model-backed pass


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


# -- Model-backed grading -----------------------------------------------------
#
# Some criteria (C3 catalog quality, C4 unknown handling quality, C5 predicate
# discrimination, C9 cascade quality) require judgment that deterministic
# regex cannot perform. For those, the auditor gathers evidence
# deterministically, then optionally calls Claude Code CLI with a narrow
# grading prompt and parses the verdict back into the same Match schema.
#
# This is criterion C11 of the auditor's own audit (LLM-as-diagnoser fallback).
# Without --model-backed, qualitative criteria return `unknown` honestly.

CRITERION_RE = re.compile(r"^## (C\d+) — (.+)$", re.MULTILINE)


def _criterion_text(criterion_id: str) -> str:
    """Extract the entry for criterion_id from references/criteria.md."""
    try:
        text = CRITERIA_FILE.read_text(errors="replace")
    except OSError:
        return ""
    sections = list(CRITERION_RE.finditer(text))
    for i, m in enumerate(sections):
        if m.group(1) == criterion_id:
            start = m.start()
            end = sections[i + 1].start() if i + 1 < len(sections) else len(text)
            return text[start:end].strip()
    return ""


def _call_claude(prompt: str, timeout_s: int = 60) -> str:
    """Invoke `claude -p` and return stdout. Raises on unavailable / error."""
    if not shutil.which("claude"):
        raise RuntimeError("claude CLI not on PATH; install Claude Code or unset --model-backed")
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, timeout=timeout_s,
        env={**os.environ, "CLAUDE_NONINTERACTIVE": "1"},
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI exit {result.returncode}: {result.stderr[:200]}")
    return result.stdout


def _extract_json(text: str) -> dict | None:
    """Find a {verdict: ...} JSON object in the response text."""
    # Try fenced code block first.
    for m in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL):
        try:
            obj = json.loads(m.group(1))
            if "verdict" in obj:
                return obj
        except (ValueError, json.JSONDecodeError):
            continue
    # Try raw object with verdict key.
    for m in re.finditer(r"\{[^{}]*?\"verdict\"[^{}]*?\}", text, re.DOTALL):
        try:
            obj = json.loads(m.group(0))
            return obj
        except (ValueError, json.JSONDecodeError):
            continue
    return None


def _model_grade(
    criterion_id: str,
    name: str,
    bundle: dict,
    cost_ctx: dict,
) -> Match:
    """Grade a qualitative criterion via Claude Code CLI. Bounded by cost cap."""
    if cost_ctx["spent_usd"] >= cost_ctx["cap_usd"]:
        return Match(
            id=criterion_id, name=name,
            verdict="unknown", confidence=0.0,
            evidence=[f"cost cap ${cost_ctx['cap_usd']:.2f} reached; criterion skipped"],
            fix_pointer="rerun with higher --max-cost-usd to grade this criterion",
            model_graded=False,
        )
    criterion_text = _criterion_text(criterion_id) or f"(criterion {criterion_id} text not found)"
    bundle_json = json.dumps(bundle, indent=2)[:8000]  # cap context per call
    prompt = (
        f"You are grading autonomy criterion {criterion_id} for a target system. "
        f"Be strict and honest — return `unknown` if evidence is genuinely "
        f"insufficient to grade, rather than guessing.\n\n"
        f"# CRITERION DEFINITION\n{criterion_text}\n\n"
        f"# EVIDENCE GATHERED (deterministic, from grep/file checks)\n"
        f"```json\n{bundle_json}\n```\n\n"
        f"# YOUR TASK\n"
        f"Read the criterion's narrow predicate and the gathered evidence. "
        f"Decide whether the target satisfies the criterion's QUALITY aspect "
        f"(not just structural presence — quality of the structure).\n\n"
        f"Return strictly this JSON inside a fenced ```json code block, nothing else:\n"
        f"{{\n"
        f"  \"verdict\": \"pass|partial|fail|unknown\",\n"
        f"  \"confidence\": 0.0-1.0,\n"
        f"  \"reason\": \"one paragraph, concrete, evidence-backed\",\n"
        f"  \"fix_pointer\": \"specific file/function/diff suggestion if not pass\"\n"
        f"}}\n"
    )
    try:
        response = _call_claude(prompt, timeout_s=90)
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        return Match(
            id=criterion_id, name=name,
            verdict="unknown", confidence=0.0,
            evidence=[f"model call failed: {type(exc).__name__}: {exc}"],
            fix_pointer="ensure `claude` CLI is on PATH or drop --model-backed",
            model_graded=False,
        )
    # Rough cost estimate: $0.01-0.05 per call depending on prompt size.
    # Real cost tracking requires --output-format json parsing; this is approximate.
    cost_ctx["spent_usd"] += 0.03
    graded = _extract_json(response)
    if not graded or "verdict" not in graded:
        return Match(
            id=criterion_id, name=name,
            verdict="unknown", confidence=0.2,
            evidence=[f"model response unparseable: {response[:200]}"],
            fix_pointer="re-run; if persistent, file as auditor bug",
            model_graded=True,
        )
    return Match(
        id=criterion_id, name=name,
        verdict=str(graded.get("verdict", "unknown")),
        confidence=float(graded.get("confidence", 0.5)),
        evidence=[str(graded.get("reason", ""))[:500]],
        fix_pointer=str(graded.get("fix_pointer", "")),
        model_graded=True,
    )


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


def _gather_c3(target: pathlib.Path) -> dict:
    """Deterministic evidence gather for C3 (catalog quality)."""
    catalog_files = _file_globs_exist(
        target,
        [r"KNOWN_PATTERNS\.md", r"patterns\.(json|yaml|toml)",
         r"signatures\.(yaml|json|toml)", r"issues\.(toml|yaml)"],
    )
    bundle: dict = {"catalog_files": [str(p.name) for p in catalog_files]}
    if not catalog_files:
        return bundle
    catalog = catalog_files[0]
    bundle["catalog_path"] = str(catalog.relative_to(target) if target.is_dir() and catalog.is_relative_to(target) else catalog.name)
    bundle["catalog_excerpt"] = _read_text(catalog)[:4000]
    consumers = _grep_any(target, SOURCE_GLOBS, [re.escape(catalog.name)])
    bundle["consumer_files"] = sorted({h[0].name for h in consumers})[:5]
    if consumers:
        bundle["consumer_excerpt"] = _read_text(consumers[0][0])[:2500]
    return bundle


def match_c3_catalog(target: pathlib.Path, dynamic: bool, *, model_backed: bool = False, cost_ctx: dict | None = None) -> Match:
    """Pattern catalog as data structure (qualitative — uses model when --model-backed)."""
    del dynamic
    bundle = _gather_c3(target)
    if not bundle["catalog_files"]:
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
    if model_backed:
        return _model_grade(
            "C3", "Pattern catalog as data structure (not prose)",
            bundle, cost_ctx or {"spent_usd": 0.0, "cap_usd": 0.50},
        )
    # Deterministic path returns `unknown` honestly — the QUALITY of catalog
    # entries (are they predicates or prose?) requires judgment.
    return Match(
        id="C3", name="Pattern catalog as data structure (not prose)",
        verdict="unknown", confidence=0.4,
        evidence=[
            f"catalog found: {bundle.get('catalog_path', bundle['catalog_files'][0])}",
            f"{len(bundle.get('consumer_files', []))} consumer file(s) reference it",
            "qualitative grade (entries are predicates vs prose) requires --model-backed",
        ],
        fix_pointer="Run audit.py with --model-backed to grade catalog entry quality.",
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
    # Look specifically in code (.py/.ts/.js — not shell scripts where these
    # strings often appear in error messages) for budget flag DEFINITIONS
    # (add_argument / Click option / dataclass field), not random mentions.
    # Shell scripts excluded because cycle 9 false-positive matched the word
    # "reachable" containing "ach" → "max-iterations" substring fragment.
    code_globs = ["**/*.py", "**/*.ts", "**/*.tsx", "**/*.js"]
    budget_flags = _grep_any(
        target, code_globs,
        [r"add_argument\([\"']--max[\-_]iter",
         r"add_argument\([\"']--cost[\-_]budget",
         r"add_argument\([\"']--timeout",
         r"add_argument\([\"']--max[\-_]tokens?",
         r"add_argument\([\"']--max[\-_]cycles?",
         r"add_argument\([\"']--max[\-_]auto[\-_]fixes?",
         r"\.option\([\"']--max[\-_]iter",  # Click
         r"\.option\([\"']--cost[\-_]budget"],
    )
    distinct_files = {h[0].name for h in budget_flags}
    cycle_check = bool(_grep_any(
        target, code_globs,
        [r"if\s+.*>\s*.*max[\-_]iter",
         r"if\s+.*cost.*>\s*.*budget",
         r"if\s+time\.time\(\)\s*>\s*deadline",
         r"if\s+iterations?\s*>=?\s*max",
         r"while\s+.*<\s*deadline"],
    ))
    if len(distinct_files) >= 2 and cycle_check:
        verdict, conf = "pass", 0.9
    elif len(distinct_files) >= 2 or (len(distinct_files) >= 1 and cycle_check):
        verdict, conf = "pass", 0.8
    elif len(distinct_files) >= 1 or cycle_check:
        verdict, conf = "partial", 0.65
    else:
        verdict, conf = "fail", 0.85
    evidence = [f"budget flag: {h[0].name}: {h[1][:80]}" for h in budget_flags[:3]]
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
    surface_patterns = {
        "ROADMAP": [r"^ROADMAP\.md$"],
        "STATUS": [r"^STATUS\.md$"],
        "CHANGELOG": [r"^CHANGELOG\.md$"],
        "KNOWN_PATTERNS": [r"^KNOWN_PATTERNS\.md$"],
        "INSIGHTS": [r"^INSIGHTS\.md$"],
        "DECISIONS": [r"^DECISIONS?\.md$"],
    }
    # Find each distinct surface type, searching target + walking up to repo root.
    found_kinds: set[str] = set()
    found_paths: list[pathlib.Path] = []

    def _check_dir(d: pathlib.Path) -> None:
        if not d.is_dir():
            return
        for kind, pats in surface_patterns.items():
            if kind in found_kinds:
                continue
            for child in d.rglob("*.md"):
                if any(part in IGNORE_DIRS for part in child.parts):
                    continue
                if any(re.match(p, child.name) for p in pats):
                    found_kinds.add(kind)
                    found_paths.append(child)
                    break

    # Walk from target up to repo root (.git boundary or 6 levels).
    search_root: pathlib.Path = target if target.is_dir() else target.parent
    for _ in range(6):
        _check_dir(search_root)
        if (search_root / ".git").exists():
            break
        if search_root.parent == search_root:
            break
        search_root = search_root.parent
    # Also peek inside common doc locations.
    for sub in ("docs", "docs/goal"):
        candidate = search_root / sub
        if candidate.exists():
            _check_dir(candidate)

    # Look for documented closeout step in target docs.
    closeout = bool(_grep_any(
        target, DOC_GLOBS,
        [r"closeout", r"post[\-_]fix", r"propagat", r"after.*fix.*commit"],
    ))

    n = len(found_kinds)
    if n >= 4 and closeout:
        verdict, conf = "pass", 0.9
    elif n >= 4 or (n >= 3 and closeout):
        verdict, conf = "pass", 0.8
    elif n >= 2:
        verdict, conf = "partial", 0.65
    elif n >= 1 or closeout:
        verdict, conf = "partial", 0.5
    else:
        verdict, conf = "fail", 0.8
    evidence = [f"surface kinds found: {sorted(found_kinds)}"]
    for p in found_paths[:5]:
        try:
            evidence.append(f"  {p.relative_to(search_root)}")
        except ValueError:
            evidence.append(f"  {p.name}")
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
    # Persistent state is broader than "has a config.toml". Accept ANY of:
    # structured data files (TSV/CSV/JSONL/Parquet), SQLite DBs, JSON snapshots,
    # config files, evidence dumps, append-only logs the target writes itself.
    persistence_code = _grep_any(
        target, SOURCE_GLOBS,
        [r"\.write_text\(", r"\.read_text\(\)", r"json\.dump", r"json\.load",
         r"sqlite3\.connect", r"csv\.writer", r"csv\.DictWriter",
         r"tomli?\.load", r"yaml\.safe_(load|dump)",
         r"with open\([^)]*[\"']w"],
    )
    # Persistent data artifact files (the actual state on disk that survives).
    data_artifacts = _file_globs_exist(
        target,
        [r"\.tsv$", r"\.csv$", r"\.jsonl$", r"\.sqlite$", r"\.db$",
         r"_summary\.json$", r"_history\.json$", r"_runs\.json$",
         r"^config\.(toml|yaml|json|ini)$", r"^\.env\.example$",
         r"KNOWN_PATTERNS\.md", r"baseline.*\.json"],
    )
    if persistence_code and data_artifacts:
        verdict, conf = "pass", 0.85
    elif persistence_code or data_artifacts:
        verdict, conf = "partial", 0.6
    else:
        verdict, conf = "fail", 0.7
    evidence = []
    if persistence_code:
        evidence.append(f"{len(persistence_code)} file-IO call site(s)")
    if data_artifacts:
        kinds = sorted({a.suffix or a.name for a in data_artifacts})[:5]
        evidence.append(f"{len(data_artifacts)} data artifact(s) on disk ({', '.join(kinds)})")
    return Match(
        id="C8", name="State, not conversation",
        verdict=verdict, confidence=conf, evidence=evidence,
        fix_pointer=(
            "Move ephemeral state to files: catalog → KNOWN_PATTERNS.md, "
            "decisions → decisions.json, config → config.toml, "
            "evidence rows → results.tsv. Verify cold start: invoke target "
            "from fresh shell with no env context and confirm identical behavior."
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
    # Match ACTUAL LLM client construction / subprocess call, not env vars
    # (CLAUDE_CODE_ENABLE_TELEMETRY style false-positive caught 2026-05-23).
    code_globs = ["**/*.py", "**/*.ts", "**/*.tsx", "**/*.js"]
    llm_invoke = _grep_any(
        target, code_globs,
        [r"\bAnthropic\(",
         r"\banthropic\.Anthropic\(",
         r"\bopenai\.(OpenAI|ChatCompletion|Completion)\(",
         r"\bclient\.messages\.create\(",
         r"subprocess\.(run|Popen)\(\[?[\"']claude[\"']",
         r"subprocess\.(run|Popen)\(\[?[\"']codex[\"']",
         r"\bllm[\-_]fallback\b",
         r"on_unknown.*llm",
         r"@anthropic-ai/sdk"],
    )
    if llm_invoke:
        verdict, conf = "pass", 0.85
    else:
        verdict, conf = "fail", 0.95
    evidence = [f"{h[0].name}: {h[1][:80]}" for h in llm_invoke[:3]] if llm_invoke else [
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
    # Match ACTUAL auto-apply code, not docs that mention the concept.
    # Requires: a code path that programmatically commits AND gates on a
    # confidence/safety flag. Mere "auto-apply" prose isn't evidence — the
    # C12 description itself contains the phrase and would otherwise match
    # every target that audits this very skill (false positive).
    code_globs = ["**/*.py", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.sh"]
    commit_calls = _grep_any(
        target, code_globs,
        [r"subprocess\.run\(\[?[\"']git[\"'],\s*[\"']commit",
         r"git\s+commit\s+-m\s+[\"']auto[\-_]?fix",
         r"call_git\([\"']commit"],
    )
    safety_gate = _grep_any(
        target, code_globs,
        [r"auto_apply_safe", r"safe_to_auto_apply", r"auto_apply\s*=\s*True",
         r"if\s+.*confidence\s*>=?\s*0\.[89]"],
    )
    dedicated_file = _file_globs_exist(
        target, [r"^auto[\-_]apply\.", r"^auto[\-_]fix\.", r"^apply[\-_]fixes?\."],
    )
    if (commit_calls and safety_gate) or dedicated_file:
        verdict, conf = "pass", 0.85
    elif commit_calls or safety_gate:
        verdict, conf = "partial", 0.6
    else:
        verdict, conf = "fail", 0.95
    evidence = []
    if commit_calls:
        evidence.append(f"{len(commit_calls)} programmatic git-commit call site(s)")
    if safety_gate:
        evidence.append(f"{len(safety_gate)} safety-gate site(s)")
    if dedicated_file:
        evidence.append(f"dedicated auto-apply script: {dedicated_file[0].name}")
    if not evidence:
        evidence.append("no auto-apply code path found; fixes require manual operator action")
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


def run_audit(target: pathlib.Path, *, dynamic: bool, only: str | None, model_backed: bool = False, max_cost_usd: float = 0.50) -> dict:
    matches: list[Match] = []
    cost_ctx = {"spent_usd": 0.0, "cap_usd": max_cost_usd}
    for fn in CHECKS:
        m = Match(id="?", name=fn.__name__, verdict="unknown", confidence=0.0)
        try:
            # Matchers that accept model_backed/cost_ctx get them; others fall back.
            try:
                m = fn(target, dynamic, model_backed=model_backed, cost_ctx=cost_ctx)
            except TypeError:
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
    ap.add_argument(
        "--model-backed", action="store_true",
        help="invoke `claude` CLI to grade qualitative criteria (C3, C4, C5, C9). "
             "Without this flag, qualitative criteria return `unknown` honestly. "
             "Each call bounded by --max-cost-usd.",
    )
    ap.add_argument(
        "--max-cost-usd", type=float, default=0.50,
        help="cap aggregate LLM cost across all model-backed criteria (default $0.50). "
             "Hit the cap → remaining qualitative criteria return `unknown`.",
    )
    args = ap.parse_args(argv)

    target = pathlib.Path(args.target).expanduser().resolve()
    if not target.exists():
        print(f"error: {target} does not exist", file=sys.stderr)
        return 1

    audit = run_audit(
        target, dynamic=args.dynamic, only=args.criterion,
        model_backed=args.model_backed, max_cost_usd=args.max_cost_usd,
    )

    if args.json:
        print(json.dumps(audit, indent=2))
    else:
        print(render_markdown(audit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
