#!/usr/bin/env python3
"""Diagnose a STUCK dump produced by hang_watchdog.py.

Reads a dump directory and matches its artifacts against
`.claude/skills/autoresearch/KNOWN_PATTERNS.md`. Reports the top match (or
`unknown`) so the autoresearch loop knows which Fix lane to take without
re-running the human diagnostic process.

Each matcher is a small predicate that consults the dump's artifacts:

- `STUCK_DETECTED.json`             — top-level metadata + dual signal times
- `agent_builder.db` + `.db-wal`    — Builder's state at detect time
- `process_threads.txt`             — main + worker thread wchan
- `process_sockets.txt`             — `ss -tnp` snapshot
- `process_fds.txt`                 — open file descriptors
- `builder_logs_error.json`         — recent structured errors
- `builder_sessions.json`           — chat session list

Matchers return a `(confidence: float in [0,1], evidence: list[str])` tuple
when they match, or `None` when they don't. Confidence is a rough belief
score — 1.0 means every evidence predicate fired; 0.5 means partial match.
The diagnoser prints the highest-confidence match, or `unknown` if none
exceed 0.5.

This script is intentionally read-only against the dump. It does not connect
to live builders, mutate state, or call out to external services. Safe to run
on archived dumps days later.

Usage:

    python3 diagnose_hang.py <dump-dir>
    python3 diagnose_hang.py <dump-dir> --json
    python3 diagnose_hang.py <dump-dir> --all   # show every matcher score

The pattern catalog this script encodes is documented in `KNOWN_PATTERNS.md`
at the skill root. Keep them in sync — drift is a freshness-sweep finding.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass


@dataclass
class Match:
    pattern_id: str
    name: str
    confidence: float
    evidence: list[str]
    fix_pointer: str


# -- Artifact loaders ---------------------------------------------------------


def _load_text(dump: pathlib.Path, name: str) -> str:
    p = dump / name
    try:
        return p.read_text(errors="replace") if p.exists() else ""
    except OSError:
        return ""


def _load_json(dump: pathlib.Path, name: str) -> dict | list | None:
    p = dump / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(errors="replace"))
    except (ValueError, OSError):
        return None


def _open_db(dump: pathlib.Path) -> sqlite3.Connection | None:
    db = dump / "agent_builder.db"
    if not db.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        return con
    except sqlite3.Error:
        return None


def _latest_session_id(con: sqlite3.Connection, workspace: str) -> str | None:
    try:
        rows = list(
            con.execute(
                "SELECT id FROM chat_sessions WHERE workspace_cwd=? "
                "ORDER BY updated_at DESC LIMIT 1",
                (workspace,),
            )
        )
        return rows[0]["id"] if rows else None
    except sqlite3.Error:
        return None


# -- Matchers — one per KNOWN_PATTERNS.md entry -------------------------------


def match_p1_contract_drift(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P1: pending ask_user_question never picked up by harness."""
    if con is None:
        return None
    workspace = stuck.get("workspace", "")
    sess = _latest_session_id(con, workspace)
    if sess is None:
        return None
    evidence: list[str] = []
    try:
        pending_q = list(
            con.execute(
                "SELECT id, payload_json FROM chat_events "
                "WHERE session_id=? AND event_type='ask_user_question' "
                "AND status='pending'",
                (sess,),
            )
        )
        answered = list(
            con.execute(
                "SELECT id FROM chat_events "
                "WHERE session_id=? AND event_type='ask_user_question_answer'",
                (sess,),
            )
        )
    except sqlite3.Error:
        return None
    if not pending_q or answered:
        return None
    evidence.append(
        f"chat_events: {len(pending_q)} pending ask_user_question, "
        f"{len(answered)} answers (mismatch — harness never responded)"
    )
    if "do_epoll_wait" in threads:
        evidence.append("main thread idle on do_epoll_wait (asyncio waiting)")
    confidence = 0.85 + (0.15 if "futex_wait_queue" in threads else 0)
    return Match(
        pattern_id="P1",
        name="Harness API contract drift (chat history + respond)",
        confidence=min(confidence, 1.0),
        evidence=evidence,
        fix_pointer=(
            "scripts/autoresearch/run.py:get_pending_question + send_chat_respond; "
            "verify against src/.../embedded/server/agent_api_models.py "
            "(ChatHistoryResponse.items, TimelineItem.status, "
            "ChatRespondRequest.event_id|selected_options|custom_text)"
        ),
    )


def match_p2_free_text_scoping(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P2: chat ended with markdown clarifying question, no ask_user_question."""
    if con is None:
        return None
    sess = _latest_session_id(con, stuck.get("workspace", ""))
    if sess is None:
        return None
    try:
        # Filter to content events — every chat ends with `run_status` which
        # is telemetry, not the model's actual response. P7-style fix mirrored
        # in the matcher so it doesn't repeat the run.py bug.
        latest_evt = list(
            con.execute(
                "SELECT event_type, payload_json FROM chat_events "
                "WHERE session_id=? AND event_type IN "
                "('assistant_message','ask_user_question','user_message',"
                "'tool_approval_request') "
                "ORDER BY created_at DESC LIMIT 1",
                (sess,),
            )
        )
        run_status = list(
            con.execute(
                "SELECT payload_json FROM chat_events "
                "WHERE session_id=? AND event_type='run_status' "
                "ORDER BY created_at DESC LIMIT 1",
                (sess,),
            )
        )
        pending = list(
            con.execute(
                "SELECT id FROM chat_events "
                "WHERE session_id=? AND event_type='ask_user_question' "
                "AND status='pending'",
                (sess,),
            )
        )
        tasks = list(
            con.execute(
                "SELECT id FROM tasks WHERE chat_session_id=?",
                (sess,),
            )
        )
    except sqlite3.Error:
        return None
    if not latest_evt or latest_evt[0]["event_type"] != "assistant_message":
        return None
    if pending:
        return None  # P1, not P2
    if tasks:
        return None  # tasks were created → scoping completed
    try:
        msg_payload = json.loads(latest_evt[0]["payload_json"] or "{}")
        content = str(msg_payload.get("content") or "")
    except ValueError:
        content = ""
    # Note: we used to require an interrogative ("?" / numbered list) here to
    # distinguish "model paused asking" from "model finished a task". Dropped
    # 2026-05-23 cycle 8 — model said "I'll proceed with reasonable defaults"
    # (no `?`) but didn't actually proceed (no task created). The harness
    # still needs the continuation. Symptoms above already imply the chat is
    # stuck, regardless of the content's grammar.
    _ = content
    running_false = False
    if run_status:
        try:
            rs_payload = json.loads(run_status[0]["payload_json"] or "{}")
            running_false = rs_payload.get("running") is False
        except ValueError:
            running_false = False
    if not running_false:
        return None
    evidence = [
        "latest content event is assistant_message (chat agent's response)",
        "no ask_user_question event with status=pending",
        "no tasks created for this chat_session (scoping never completed)",
        "latest run_status.running = false",
    ]
    return Match(
        pattern_id="P2",
        name="Builder chat agent ended in free-text scoping",
        confidence=0.9,
        evidence=evidence,
        fix_pointer=(
            "scripts/autoresearch/run.py — THREE cascading fixes, all must be "
            "present: (1) wait_for_question_or_ship returns 'proceed_needed' and "
            "main loop continues via send_chat (P2 original). (2) latest_chat_state "
            "tracks last_content_event_type filtered to {assistant_message, "
            "ask_user_question, user_message, tool_approval_request} (P7 refinement, "
            "cycle 8). (3) `running` is derived from assistant_message.payload.final, "
            "NOT from run_status events (P8 refinement, cycle 9 — run_status is not "
            "in VISIBLE_EVENT_TYPES on the server, so it never reaches the harness). "
            "If P2 matches but fix is in source, cascade through P7 → P8 — see "
            "KNOWN_PATTERNS.md."
        ),
    )


def match_p3_watchdog_false_positive(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P3: WAL stale but raw_bodies kept growing — model loop was alive."""
    wal_mt = float(stuck.get("wal_last_mtime_epoch") or 0)
    raw_mt = float(stuck.get("raw_bodies_last_mtime_epoch") or 0)
    if wal_mt <= 0 or raw_mt <= 0:
        return None  # old-format dump, cannot decide
    # If raw_bodies advanced > 30s past WAL, watchdog should not have fired.
    # (Dual-signal logic now prevents this — pattern still useful for archived
    # dumps and as a regression check.)
    if raw_mt - wal_mt < 30:
        return None
    evidence = [
        f"wal_last_mtime_iso = {stuck.get('wal_last_mtime_iso')}",
        f"raw_bodies_last_mtime_iso = {stuck.get('raw_bodies_last_mtime_iso')}",
        f"raw_bodies advanced {raw_mt - wal_mt:.0f}s past WAL "
        "(model loop was alive)",
    ]
    return Match(
        pattern_id="P3",
        name="Hang-watchdog single-signal false positive (pre-dual-signal)",
        confidence=0.95,
        evidence=evidence,
        fix_pointer=(
            ".claude/skills/autoresearch/scripts/hang_watchdog.py — "
            "_raw_bodies_max_mtime + live_mt = max(WAL, raw_bodies) dual signal"
        ),
    )


def match_p4_pipe_deadlock(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P4: subprocess pipe buffer full, main thread blocked on pipe_write."""
    if "wchan=pipe_write" not in threads:
        return None
    evidence = ["main thread wchan=pipe_write (asyncio loop blocked on pipe)"]
    port = stuck.get("builder_port")
    close_wait_with_data = 0
    if port:
        for line in sockets.splitlines():
            if "CLOSE-WAIT" in line and f":{port}" in line:
                m = re.search(r"\s(\d+)\s+0\s+127\.0\.0\.1:" + str(port), line)
                if m and int(m.group(1)) > 0:
                    close_wait_with_data += 1
    if close_wait_with_data >= 3:
        evidence.append(
            f"{close_wait_with_data} CLOSE-WAIT sockets on port {port} "
            "with non-zero Recv-Q (HTTP requests piled up)"
        )
    confidence = 0.85 + (0.1 if close_wait_with_data >= 3 else 0)
    return Match(
        pattern_id="P4",
        name="subprocess pipe deadlock (run.py captured stdout/stderr without draining)",
        confidence=min(confidence, 1.0),
        evidence=evidence,
        fix_pointer=(
            "scripts/autoresearch/run.py:main — redirect Popen stdout/stderr "
            "to evidence_dir/builder_stdout_stderr.log (file handle, not PIPE)"
        ),
    )


def match_p5_sprint_merge_main(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P5: sprint completes, merge fails on `git checkout main`."""
    if con is None:
        return None
    workspace = stuck.get("workspace", "")
    sess = _latest_session_id(con, workspace)
    if sess is None:
        return None
    try:
        tasks = list(
            con.execute(
                "SELECT status FROM tasks WHERE chat_session_id=?",
                (sess,),
            )
        )
        sprints = list(
            con.execute(
                "SELECT phase, verification_status, verification_evidence "
                "FROM sprints ORDER BY updated_at DESC LIMIT 1"
            )
        )
    except sqlite3.Error:
        return None
    if not tasks or not sprints:
        return None
    if not all(t["status"] == "done" for t in tasks):
        return None
    sprint = sprints[0]
    if sprint["phase"] != "blocked":
        return None
    if not sprint["verification_evidence"]:
        return None
    try:
        ve = json.loads(sprint["verification_evidence"])
    except ValueError:
        return None
    merge_err = str(ve.get("sprint_merge_error") or "")
    if "could not check out main" not in merge_err:
        return None
    evidence = [
        f"all {len(tasks)} tasks status=done",
        f"latest sprint phase=blocked verification_status="
        f"{sprint['verification_status']}",
        f"sprint_merge_error: {merge_err[:120]}",
    ]
    return Match(
        pattern_id="P5",
        name="Sprint merge fails on `git checkout main` "
        "(seed default branch is `master`)",
        confidence=0.95,
        evidence=evidence,
        fix_pointer=(
            "scripts/autoresearch/run.py:restore_seed — create `main` branch "
            "from HEAD after copying the seed (cheap skill-side workaround); "
            "proper Builder fix in services/sprint_execution.py tracked under M2.3"
        ),
    )


def match_p6_sprint_merge_venv(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P6: sprint completes but post-merge check fails on tracked .venv entries."""
    if con is None:
        return None
    workspace = stuck.get("workspace", "")
    sess = _latest_session_id(con, workspace)
    if sess is None:
        return None
    try:
        tasks = list(
            con.execute(
                "SELECT status FROM tasks WHERE chat_session_id=?",
                (sess,),
            )
        )
        sprints = list(
            con.execute(
                "SELECT phase, verification_status, verification_evidence "
                "FROM sprints ORDER BY updated_at DESC LIMIT 1"
            )
        )
    except sqlite3.Error:
        return None
    if not tasks or not sprints:
        return None
    if not all(t["status"] == "done" for t in tasks):
        return None
    sprint = sprints[0]
    if sprint["phase"] != "blocked" or not sprint["verification_evidence"]:
        return None
    try:
        ve = json.loads(sprint["verification_evidence"])
    except ValueError:
        return None
    merge_err = str(ve.get("sprint_merge_error") or "")
    venv_pattern = re.compile(
        r"tracked non-guidance changes after sprint merge.*\.venv",
        re.DOTALL,
    )
    if not venv_pattern.search(merge_err):
        return None
    evidence = [
        f"all {len(tasks)} tasks status=done",
        "sprint phase=blocked",
        f"sprint_merge_error mentions tracked .venv changes: "
        f"{merge_err[:160]}",
    ]
    return Match(
        pattern_id="P6",
        name="Sprint merge post-check fails on tracked .venv entries",
        confidence=0.95,
        evidence=evidence,
        fix_pointer=(
            "scripts/autoresearch/run.py:restore_seed — `git rm -r --cached "
            "--ignore-unmatch .venv` + commit, after seed copy. Working tree "
            "stays intact; index stops tracking .venv so post-merge clean "
            "check passes."
        ),
    )


def match_p9_sprint_merge_untracked_venv(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P9: sprint merge aborts because untracked .venv files would be overwritten."""
    if con is None:
        return None
    try:
        sprints = list(
            con.execute(
                "SELECT verification_evidence FROM sprints "
                "WHERE verification_evidence IS NOT NULL "
                "ORDER BY updated_at DESC LIMIT 1"
            )
        )
    except sqlite3.Error:
        return None
    if not sprints:
        return None
    try:
        ve = json.loads(sprints[0]["verification_evidence"])
    except ValueError:
        return None
    merge_err = str(ve.get("sprint_merge_error") or "")
    if "Updating the following directories would lose untracked files" not in merge_err:
        return None
    if ".venv" not in merge_err:
        return None
    return Match(
        pattern_id="P9",
        name="Sprint merge `git checkout main` overwrites untracked .venv files",
        confidence=0.95,
        evidence=[
            f"sprint_merge_error: untracked-overwrite on .venv: "
            f"{merge_err[:160]}",
        ],
        fix_pointer=(
            "scripts/autoresearch/run.py:restore_seed — append `.venv/` to "
            "the workspace's .gitignore (idempotent), then commit. Ignored "
            "files don't trigger the untracked-overwrite check. Combined with "
            "the P6 `git rm --cached .venv` step."
        ),
    )


def match_p10_respond_400(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P10: 400 Bad Request on /api/agent/chat/respond crashes the iteration."""
    crash_log = (dump / "crash.log") if dump else None
    text = ""
    if crash_log and crash_log.exists():
        try:
            text = crash_log.read_text(errors="replace")
        except OSError:
            text = ""
    if not text or "400" not in text or "chat/respond" not in text:
        return None
    return Match(
        pattern_id="P10",
        name="/api/agent/chat/respond 400 Bad Request crashes iteration",
        confidence=0.95,
        evidence=[
            f"crash.log: {text.strip()[:200]}",
        ],
        fix_pointer=(
            "scripts/autoresearch/run.py main loop — wrap `send_chat_respond` "
            "in try/except for requests.HTTPError with status 400; fall back "
            "to send_chat('Continue with reasonable defaults.', "
            "session_id=session_id). Iteration progresses to shipped instead "
            "of crashing."
        ),
    )


MATCHERS = [
    match_p10_respond_400,            # very specific — check first
    match_p9_sprint_merge_untracked_venv,
    match_p6_sprint_merge_venv,
    match_p5_sprint_merge_main,
    match_p4_pipe_deadlock,
    match_p1_contract_drift,
    match_p2_free_text_scoping,
    match_p3_watchdog_false_positive,
]


# -- Driver -------------------------------------------------------------------


def diagnose(dump: pathlib.Path) -> dict:
    raw_stuck = _load_json(dump, "STUCK_DETECTED.json")
    stuck: dict = raw_stuck if isinstance(raw_stuck, dict) else {}
    threads = _load_text(dump, "process_threads.txt")
    sockets = _load_text(dump, "process_sockets.txt")
    con = _open_db(dump)
    matches: list[Match] = []
    try:
        for matcher in MATCHERS:
            try:
                m = matcher(dump, stuck, con, threads, sockets)
            except Exception as exc:
                m = Match(
                    pattern_id=matcher.__name__,
                    name="matcher error",
                    confidence=0.0,
                    evidence=[f"{type(exc).__name__}: {exc}"],
                    fix_pointer="",
                )
            if m is not None:
                matches.append(m)
    finally:
        if con is not None:
            con.close()
    matches.sort(key=lambda m: m.confidence, reverse=True)
    top = matches[0] if matches and matches[0].confidence >= 0.5 else None
    return {
        "dump": str(dump),
        "stuck_metadata": stuck,
        "top_match": asdict(top) if top else None,
        "all_matches": [asdict(m) for m in matches],
        "verdict": "matched" if top else "unknown",
        "guidance": (
            "Apply the fix at fix_pointer and re-run baseline."
            if top else
            "No known pattern matched. Diagnose by hand, then add an entry to "
            ".claude/skills/autoresearch/KNOWN_PATTERNS.md and a matcher to "
            "diagnose_hang.py so the next session benefits."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="autoresearch hang diagnoser")
    ap.add_argument("dump", help="path to a STUCK dump directory")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument(
        "--all",
        action="store_true",
        help="show every matcher result, not just the top match",
    )
    args = ap.parse_args(argv)
    dump = pathlib.Path(args.dump)
    if not dump.is_dir():
        print(f"error: {dump} is not a directory", file=sys.stderr)
        return 2
    if not (dump / "STUCK_DETECTED.json").exists():
        print(
            f"error: {dump}/STUCK_DETECTED.json missing — not a watchdog dump",
            file=sys.stderr,
        )
        return 2

    result = diagnose(dump)

    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if result["verdict"] == "matched" else 1

    print(f"# autoresearch hang diagnosis")
    print(f"dump: {result['dump']}")
    print(f"verdict: {result['verdict']}")
    print()
    top = result["top_match"]
    if top:
        print(f"## top match: {top['pattern_id']} — {top['name']}")
        print(f"confidence: {top['confidence']:.2f}")
        print(f"fix: {top['fix_pointer']}")
        print(f"evidence:")
        for ev in top["evidence"]:
            print(f"  - {ev}")
    else:
        print(result["guidance"])
    if args.all and len(result["all_matches"]) > 1:
        print()
        print(f"## all candidates (sorted by confidence)")
        for m in result["all_matches"]:
            print(f"- {m['pattern_id']}: {m['confidence']:.2f} — {m['name']}")
    return 0 if top else 1


if __name__ == "__main__":
    sys.exit(main())
