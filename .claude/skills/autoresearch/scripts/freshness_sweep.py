#!/usr/bin/env python3
"""Freshness sweep for `docs/autoresearch/`.

Hard Rule 2 of the autoresearch skill: the skill is the sole agent
responsible for keeping every file under `docs/autoresearch/` consistent
with current code, current loop contract, and current measurements. This
script is the enforcement layer — every lane's closeout calls it as the
final step. Non-zero exit means drift; the lane refuses to close until
the drift is fixed (typically by switching to Fix lane).

Mirrors the `preflight.py` pattern: discipline through a script, not prose.

Checks (each isolated; one drift doesn't short-circuit the rest):

  - METRICS.md documents `runtime_aggregates.session_scoped` (contract
    landed 2026-05-23 with ROADMAP M2.3).
  - logs_runtime_aggregates.py still emits `session_scoped` in the analyze payload.
  - `Task.chat_session_id` column still defined in `db/models.py`.
  - TSV headers (`baseline_runs.tsv`, `optimize_results.tsv`,
    `per_prompt_results.tsv`) match `run.py:SESSION_HEADERS` /
    `PROMPT_HEADERS` exactly. Drift here silently corrupts every
    downstream consumer.
  - README.md activation block still mentions the 2026-05-23
    telemetry-honesty line.
  - METRICS.md `prompt_count` row clarifies "operator turns" (not model
    calls) — the post-fix semantic.
  - HARNESS.md asserts `runtime_aggregates.session_scoped is True`.
  - iterations.html data-block markers (__ITERATIONS_DATA_START__ /
    __ITERATIONS_DATA_END__) intact — the regenerator depends on them.
  - `baseline_runs_summary.json`, if present, is no older than 14 days
    (warn only — soft drift).

Exit codes:
  0 — clean (or warn-only drift in soft checks)
  1 — hard drift found; closeout MUST NOT proceed

Usage:
  python3 .claude/skills/autoresearch/scripts/freshness_sweep.py
  python3 .claude/skills/autoresearch/scripts/freshness_sweep.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SCRIPT = Path(__file__).resolve()
SKILL_DIR = SCRIPT.parent.parent
REPO_ROOT = SKILL_DIR.parent.parent.parent
DOCS = REPO_ROOT / "docs" / "autoresearch"
SRC = REPO_ROOT / "src" / "autonomous_agent_builder"
SCRIPTS = REPO_ROOT / "scripts" / "autoresearch"


@dataclass
class Finding:
    check: str
    severity: str  # "hard" or "soft"
    message: str
    fix: str

    def to_dict(self) -> dict:
        return {
            "check": self.check,
            "severity": self.severity,
            "message": self.message,
            "fix": self.fix,
        }


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def check_metrics_documents_session_scoped() -> Finding | None:
    text = _read(DOCS / "METRICS.md")
    if "session_scoped" not in text:
        return Finding(
            "metrics_documents_session_scoped",
            "hard",
            "METRICS.md missing `runtime_aggregates.session_scoped` flag.",
            "Restore the 2026-05-23 contract note in METRICS.md describing "
            "session_scoped: true assertion. See ROADMAP M2.3.",
        )
    return None


def check_logs_emits_session_scoped() -> Finding | None:
    text = _read(SRC / "cli" / "commands" / "logs_runtime_aggregates.py")
    if '"session_scoped"' not in text:
        return Finding(
            "logs_emits_session_scoped",
            "hard",
            "src/.../cli/commands/logs_runtime_aggregates.py no longer emits "
            "`session_scoped` key in analyze payload.",
            "The M2.3 fix was reverted or shadowed. Restore the key in "
            "runtime_aggregates() payload dict. See commit a3354c2.",
        )
    return None


def check_task_chat_session_id_column() -> Finding | None:
    text = _read(SRC / "db" / "models.py")
    if "chat_session_id" not in text:
        return Finding(
            "task_chat_session_id_column",
            "hard",
            "src/.../db/models.py no longer defines `chat_session_id` on Task.",
            "The 2026-05-23 FK was removed. Without it, `_session_task_filter` "
            "is inert and aggregates fall back to global. Restore the column.",
        )
    return None


def _extract_python_list(text: str, name: str) -> list[str] | None:
    pattern = rf"{re.escape(name)}\s*=\s*\[(.*?)\]"
    match = re.search(pattern, text, re.DOTALL)
    if match is None:
        return None
    body = match.group(1)
    return [token.strip().strip("\"'") for token in re.findall(r'"[^"]+"|\'[^\']+\'', body)]


def check_tsv_headers_match_writer() -> list[Finding]:
    findings: list[Finding] = []
    run_py = _read(SCRIPTS / "run.py")
    session_headers = _extract_python_list(run_py, "SESSION_HEADERS")
    prompt_headers = _extract_python_list(run_py, "PROMPT_HEADERS")
    targets = [
        ("baseline_runs.tsv", session_headers, "SESSION_HEADERS"),
        ("optimize_results.tsv", session_headers, "SESSION_HEADERS"),
        ("per_prompt_results.tsv", prompt_headers, "PROMPT_HEADERS"),
    ]
    for filename, expected, source in targets:
        path = DOCS / filename
        if not path.exists():
            findings.append(
                Finding(
                    f"tsv_present_{filename}",
                    "hard",
                    f"{filename} missing.",
                    f"Restore the file with the {source} header row.",
                )
            )
            continue
        if expected is None:
            findings.append(
                Finding(
                    f"writer_schema_{source}",
                    "hard",
                    f"Could not extract {source} from run.py.",
                    "Confirm scripts/autoresearch/run.py still defines the list literal.",
                )
            )
            continue
        first_line = path.read_text(encoding="utf-8").split("\n", 1)[0]
        actual = first_line.split("\t") if first_line else []
        if actual != expected:
            preview_actual = ",".join(actual[:4]) + ("..." if len(actual) > 4 else "")
            preview_expected = ",".join(expected[:4]) + ("..." if len(expected) > 4 else "")
            findings.append(
                Finding(
                    f"tsv_header_drift_{filename}",
                    "hard",
                    f"{filename} header drifted from {source}. tsv=[{preview_actual}] writer=[{preview_expected}]",
                    f"Align {filename} header to {source} exactly (no extra/missing columns, "
                    "no reordering). Then truncate data rows that were written under the drifted schema.",
                )
            )
    return findings


def check_readme_telemetry_honesty_line() -> Finding | None:
    text = _read(DOCS / "README.md")
    if "2026-05-23" not in text or "session-scoped" not in text:
        return Finding(
            "readme_telemetry_honesty_line",
            "hard",
            "README.md activation block missing the 2026-05-23 telemetry-honesty line.",
            "The Fix lane that landed 2026-05-23 requires its dated line in the "
            "activation block so future agents see why σ-floor is now reliable.",
        )
    return None


def check_metrics_prompt_count_semantic() -> Finding | None:
    text = _read(DOCS / "METRICS.md")
    if "operator chat turns" not in text and "operator turns" not in text:
        return Finding(
            "metrics_prompt_count_semantic",
            "hard",
            "METRICS.md no longer clarifies that `prompt_count` = operator chat turns.",
            "Post-2026-05-23 `prompts[]` is operator-chat-turn-scoped; per-agent attribution "
            "is in `runtime_aggregates.by_agent`. Restore the clarification.",
        )
    return None


def check_harness_asserts_session_scoped() -> Finding | None:
    text = _read(DOCS / "HARNESS.md")
    if "session_scoped" not in text:
        return Finding(
            "harness_asserts_session_scoped",
            "hard",
            "HARNESS.md no longer references the `session_scoped` assertion.",
            "Per Hard Rule 10, the harness MUST assert session_scoped is True "
            "before trusting σ-floor inputs. Restore the assertion in HARNESS.md.",
        )
    return None


def check_iterations_html_markers() -> Finding | None:
    path = DOCS / "iterations.html"
    if not path.exists():
        return None  # OK; gets regenerated by render_iterations.py.
    text = _read(path)
    missing = [m for m in ("__ITERATIONS_DATA_START__", "__ITERATIONS_DATA_END__") if m not in text]
    if missing:
        return Finding(
            "iterations_html_markers",
            "hard",
            f"iterations.html missing markers: {', '.join(missing)}",
            "render_iterations.py rewrites the embedded data block between these markers. "
            "Without them, the visual map cannot be regenerated. Restore the markers from "
            "the canonical template.",
        )
    return None


def check_baseline_summary_age() -> Finding | None:
    path = DOCS / "baseline_runs_summary.json"
    if not path.exists():
        return None  # OK; not yet baselined.
    age_days = (time.time() - path.stat().st_mtime) / 86400.0
    if age_days > 14.0:
        return Finding(
            "baseline_summary_age",
            "soft",
            f"baseline_runs_summary.json is {age_days:.0f} days old (>14).",
            "Re-baseline via the Baseline lane. Past 14 days the σ-floor stops "
            "reflecting current prompt shape + runtime policy.",
        )
    return None


def check_changelog_recent_lane_activity() -> Finding | None:
    """Soft: warn if no autoresearch entry in the last 30 days of CHANGELOG.

    This is a hint that the skill may have been bypassed (operators editing
    docs/autoresearch/ directly without going through a lane). Not a hard
    drift — the loop may simply be quiet — but worth surfacing.
    """
    path = REPO_ROOT / "CHANGELOG.md"
    if not path.exists():
        return None
    text = _read(path)
    # Find the first occurrence of "autoresearch" — its date heading.
    first_idx = text.lower().find("autoresearch")
    if first_idx < 0:
        return None  # No mention at all; this is fine — skill may be new.
    # Look backward for the nearest "## YYYY-MM-DD" heading.
    head = text[:first_idx]
    match = re.findall(r"##\s+(\d{4}-\d{2}-\d{2})", head)
    if not match:
        return None
    last_entry = match[-1]
    try:
        last_ts = time.mktime(time.strptime(last_entry, "%Y-%m-%d"))
    except ValueError:
        return None
    age_days = (time.time() - last_ts) / 86400.0
    if age_days > 30.0:
        return Finding(
            "changelog_lane_activity",
            "soft",
            f"Last autoresearch CHANGELOG entry is {age_days:.0f} days old.",
            "If the loop has been active, every kept iteration + every Fix lane "
            "closeout should land a CHANGELOG entry. A long silence may mean the "
            "skill is being bypassed.",
        )
    return None


CHECKS = [
    check_metrics_documents_session_scoped,
    check_logs_emits_session_scoped,
    check_task_chat_session_id_column,
    check_readme_telemetry_honesty_line,
    check_metrics_prompt_count_semantic,
    check_harness_asserts_session_scoped,
    check_iterations_html_markers,
    check_baseline_summary_age,
    check_changelog_recent_lane_activity,
]


def run_all() -> list[Finding]:
    findings: list[Finding] = []
    for check in CHECKS:
        result = check()
        if result is not None:
            findings.append(result)
    findings.extend(check_tsv_headers_match_writer())
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    findings = run_all()
    hard = [f for f in findings if f.severity == "hard"]
    soft = [f for f in findings if f.severity == "soft"]
    status = "drift" if hard else ("warn" if soft else "ok")
    exit_code = 1 if hard else 0

    if args.json:
        print(
            json.dumps(
                {
                    "status": status,
                    "exit_code": exit_code,
                    "hard_count": len(hard),
                    "soft_count": len(soft),
                    "findings": [f.to_dict() for f in findings],
                },
                indent=2,
            )
        )
        return exit_code

    if not findings:
        print("docs/autoresearch/ freshness: OK")
        return 0

    if hard:
        print(f"docs/autoresearch/ freshness: DRIFT ({len(hard)} hard, {len(soft)} soft)")
    else:
        print(f"docs/autoresearch/ freshness: warn-only ({len(soft)} soft)")
    print()
    for finding in findings:
        marker = "✗" if finding.severity == "hard" else "!"
        print(f"  {marker} [{finding.severity}] {finding.check}")
        print(f"      {finding.message}")
        print(f"      fix: {finding.fix}")
        print()
    if hard:
        print("Next: switch to Fix lane and address each hard finding before closing the current lane.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
