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
    # Category drives how the autoresearch loop reacts when this pattern fires:
    #   transient  — flaky failure mode (DB lock, port race, network blip).
    #                Caller should kill stuck process + retry iter, no operator
    #                involvement required.
    #   persistent — real defect in Builder source or harness contract. Cannot
    #                be retried away; needs Fix-lane code change. Caller should
    #                emit SELF_HEAL_ESCALATION with the pattern's fix_pointer
    #                as the proposed remediation.
    #   substrate  — seed/workspace identity issue. Run self_heal substrate
    #                fixes first; if still stuck, re-snapshot via setup_seed.sh.
    #   unknown    — matched on weak signals; treat as persistent for safety.
    # Default is "persistent" so matchers added before this field landed
    # remain safe (no accidental auto-retry).
    category: str = "persistent"


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


def match_p11_p14_respond_409(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P11/P14: 409 Conflict on /api/agent/chat/respond.

    Both P11 (chained 400→send_chat fallback→409) and P14 (direct 409 race
    with Builder auto-handling the pending item) produce the same crash.log
    line. Both fixes are now in run.py:825-839 — this matcher exists so the
    next session sees "P11/P14 hit again" instead of rediscovering it.
    """
    del stuck, con, threads, sockets  # signature uniform across matchers
    crash_log = (dump / "crash.log") if dump else None
    text = ""
    if crash_log and crash_log.exists():
        try:
            text = crash_log.read_text(errors="replace")
        except OSError:
            text = ""
    if not text or "409" not in text or "chat/respond" not in text:
        return None
    # Distinguish P11 (chained) vs P14 (direct) by scanning the builder
    # stdout/stderr log for a preceding 400 close in time.
    log = ""
    sl = dump / "builder_stdout_stderr.log"
    if sl.exists():
        try:
            log = sl.read_text(errors="replace")[-40_000:]
        except OSError:
            log = ""
    has_prior_400 = '"POST /api/agent/chat/respond HTTP/1.1" 400' in log
    pid = "P11" if has_prior_400 else "P14"
    return Match(
        pattern_id=pid,
        name=(
            "send_chat→409 cascade after 400-respond (P11)"
            if has_prior_400
            else "Direct 409 on /api/agent/chat/respond; pending item auto-handled (P14)"
        ),
        confidence=0.92,
        evidence=[
            f"crash.log: {text.strip()[:200]}",
            (
                "builder_stdout_stderr.log shows prior 400 on /api/agent/chat/respond"
                if has_prior_400
                else "no prior 400 in builder_stdout_stderr.log — direct 409 race"
            ),
        ],
        fix_pointer=(
            "scripts/autoresearch/run.py main loop HTTPError handler — "
            "ensure both `if status_code == 400: break` (P11) and "
            "`elif status_code == 409: continue` (P14) branches exist. "
            "Reserve `break` for 400 (payload rejected), `continue` for 409 "
            "(session busy, poll again)."
        ),
    )


def _repo_root_from_dump(dump: pathlib.Path) -> pathlib.Path:
    """Walk up to find the repo root (has docs/autoresearch/) for substrate-pattern matchers.

    Falls back to the script's own discovered repo if the dump path isn't under one.
    """
    here = pathlib.Path(__file__).resolve()
    # .claude/skills/autoresearch/scripts/diagnose_hang.py → repo at parents[4]
    return here.parents[4]


def match_p15_composite_zero(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P15: composite=0 with non-zero noncached_plus_output_tokens in baseline_runs.tsv."""
    del stuck, con, threads, sockets  # substrate matcher reads repo state, not dump
    repo = _repo_root_from_dump(dump)
    tsv = repo / "docs" / "autoresearch" / "baseline_runs.tsv"
    if not tsv.exists():
        return None
    try:
        lines = tsv.read_text(errors="replace").strip().splitlines()
    except OSError:
        return None
    if len(lines) < 2:
        return None
    header = lines[0].split("\t")
    try:
        idx_comp = header.index("composite")
        idx_nps = header.index("noncached_plus_output_tokens")
    except ValueError:
        return None
    zero_rows = 0
    inspected = 0
    sample = ""
    for row in lines[1:]:
        cols = row.split("\t")
        if len(cols) <= max(idx_comp, idx_nps):
            continue
        inspected += 1
        try:
            comp = int(cols[idx_comp] or 0)
            nps = int(cols[idx_nps] or 0)
        except ValueError:
            continue
        if comp == 0 and nps > 0:
            zero_rows += 1
            if not sample:
                sample = f"{cols[0][:8]}: composite=0 but noncached_tokens={nps}"
    if zero_rows == 0 or inspected == 0:
        return None
    return Match(
        pattern_id="P15",
        name="Composite formula reads wrong metrics key (composite=0)",
        confidence=min(0.7 + 0.1 * zero_rows, 0.98),
        evidence=[
            f"baseline_runs.tsv has {zero_rows}/{inspected} rows with composite=0 and noncached>0",
            sample,
        ],
        fix_pointer=(
            "scripts/autoresearch/run.py composite site — read "
            "metrics['optimization_summary'] (P12 contract), not "
            "metrics['optimization']. Backfill existing rows from each run's "
            "evidence metrics.json without re-running."
        ),
    )


def match_p16_high_cv(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P16: σ/μ > 0.5 in baseline_runs_summary.json → 2σ-floor non-discriminating.

    Guards:
    1. Only fires at high confidence when the composite formula is still the broken
       product formula.  If run.py already uses `noncached_plus_output_tokens` as
       the sole composite (P16's own fix), high CV reflects task-level variance,
       not a formula defect — confidence drops to 0.3 (below match threshold).
    2. When STUCK_DETECTED.json carries a `fixture` key, only the current fixture's
       CV is checked; historical high-CV on other fixtures (e.g. B's outlier iter)
       must not classify an unrelated hang as P16-persistent.
    """
    del con, threads, sockets  # substrate matcher reads repo state, not dump
    current_fixture = (stuck or {}).get("fixture")
    repo = _repo_root_from_dump(dump)

    # Guard 1: if the formula is already fixed, P16 is irrelevant.
    run_py = repo / "scripts" / "autoresearch" / "run.py"
    formula_fixed = False
    if run_py.exists():
        try:
            src = run_py.read_text(encoding="utf-8")
            formula_fixed = (
                'composite = int(opt.get("noncached_plus_output_tokens")' in src
            )
        except OSError:
            pass

    summary = repo / "docs" / "autoresearch" / "baseline_runs_summary.json"
    if not summary.exists():
        return None
    try:
        data = json.loads(summary.read_text())
    except (ValueError, OSError):
        return None
    high_cv = []
    for fid, stats in data.items():
        if not isinstance(stats, dict):
            continue
        # Guard 2: scope to the current fixture when known.
        if current_fixture and fid != current_fixture:
            continue
        mean = stats.get("mean")
        stdev = stats.get("stdev")
        if not mean or stdev is None:
            continue
        cv = stdev / mean
        if cv > 0.5:
            high_cv.append((fid, mean, stdev, cv))
    if not high_cv:
        return None
    high_cv.sort(key=lambda t: -t[3])
    fid, mean, stdev, cv = high_cv[0]
    # Formula already fixed → high CV is task variance, not a source defect.
    confidence = 0.3 if formula_fixed else 0.9
    return Match(
        pattern_id="P16",
        name="Composite formula compounds correlated noise (CV>50%)",
        confidence=confidence,
        evidence=[
            f"baseline_runs_summary.json fixture {fid}: μ={int(mean)} σ={int(stdev)} CV={cv*100:.1f}%",
            (
                f"noise_floor_2sigma={int(mean - 2 * stdev)} "
                f"(negative → 2σ gate useless)"
                if mean - 2 * stdev < 0
                else "noise floor positive but band exceeds μ — gate barely discriminates"
            ),
        ],
        fix_pointer=(
            "If the composite formula is multiplicative across correlated "
            "dimensions (e.g., tokens × turns × wallclock), drop the "
            "non-billed factors. With the fixture held constant, the cost "
            "dimension alone (noncached_plus_output_tokens) is the right "
            "composite. See scripts/autoresearch/run.py + 6 doc sites "
            "(OPTIMIZE.md, METRICS.md, README.md, autoresearch-explainer.html "
            "methodology section, baseline.py docstring, run.py)."
        ),
    )


def match_p17_seed_dep_gap(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P17: fixture-X feature_correct=False on every row of that fixture (seed dep gap)."""
    del stuck, con, threads, sockets  # substrate matcher reads repo state, not dump
    repo = _repo_root_from_dump(dump)
    tsv = repo / "docs" / "autoresearch" / "baseline_runs.tsv"
    if not tsv.exists():
        return None
    try:
        lines = tsv.read_text(errors="replace").strip().splitlines()
    except OSError:
        return None
    if len(lines) < 2:
        return None
    header = lines[0].split("\t")
    try:
        idx_fix = header.index("fixture_id")
        idx_fc = header.index("feature_correct")
        idx_id = header.index("run_id")
    except ValueError:
        return None
    by_fixture: dict[str, list[tuple[str, bool]]] = {}
    for row in lines[1:]:
        cols = row.split("\t")
        if len(cols) <= max(idx_fix, idx_fc, idx_id):
            continue
        fid = cols[idx_fix]
        fc = (cols[idx_fc] or "").strip().lower() in ("true", "1", "yes", "pass")
        by_fixture.setdefault(fid, []).append((cols[idx_id], fc))
    suspects = [
        (fid, rows) for fid, rows in by_fixture.items()
        if len(rows) >= 3 and not any(fc for _, fc in rows)
    ]
    if not suspects:
        return None
    # Look for a "passing" fixture to contrast
    healthy = [fid for fid, rows in by_fixture.items() if any(fc for _, fc in rows)]
    fid, rows = suspects[0]
    return Match(
        pattern_id="P17",
        name=f"Fixture {fid} feature_correct=False on all {len(rows)} runs (seed dep gap)",
        confidence=0.85 if healthy else 0.7,
        evidence=[
            f"baseline_runs.tsv: fixture {fid} has 0/{len(rows)} runs with feature_correct=True",
            (
                f"other fixtures pass: {healthy[:3]} — substrate isn't broken, "
                f"fixture {fid}'s generated tests need a dep the harness can't see"
                if healthy
                else "no healthy fixture to compare; could be substrate-wide"
            ),
        ],
        fix_pointer=(
            "Diff devpulse seed's pyproject.toml [project.optional-dependencies] "
            "dev list against requirements.txt. Anything required by "
            "[tool.pytest.ini_options] (e.g., asyncio_mode=auto ⇒ "
            "pytest-asyncio) MUST be in requirements.txt, not just dev. Builder's "
            "code-gen agent installs ad-hoc in its task workspace; the harness's "
            "clean post-FF venv only sees requirements.txt. Sanity test: "
            "bare-seed pytest passing-count before vs after adding the suspected "
            "plugin should jump (107 → 139 was the signal for pytest-asyncio)."
        ),
    )


def match_p18_db_lock_transient(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P18 (2026-05-24): Builder hangs after `sqlite3.OperationalError: database
    is locked` during `agent_run_events` INSERT (autoflush race).

    Symptom: Builder's agent did its work successfully (tests pass, code shipped),
    but the lifecycle's `INSERT INTO agent_run_events` flush hit a SQLite WAL
    lock contention. The flush raises OperationalError; the state-machine
    doesn't transition past the current phase; Builder sits idle polling
    `/api/dashboard/board` forever. Same root cause class as IMP-010 (SQLAlchemy
    session rollback during long agent runs) but the surface is the new agent_run
    event stream rather than task status.

    Confidence signature:
      - `database is locked` in builder_stdout_stderr.log (or builder_logs_error)
      - `agent_run_lifecycle_flush_error` OR `sdk_query_error cause='database is locked'`
      - Optional: `INSERT INTO agent_run_events` in the offending SQL
      - Optional: thread idle on epoll/futex (Builder waiting for nothing)

    Category: transient. The lock itself is a flake from WAL writer contention;
    a fresh Builder start on a fresh workspace copy typically succeeds. Caller
    should kill stuck process + retry the iter without operator involvement.
    """
    # Probe artifacts available from a watchdog dump
    stderr = _load_text(dump, "builder_stdout_stderr.log")
    if not stderr:
        # Watchdog dumps don't always carry the stdout file; fall back to
        # builder_logs_error.json (also captured by the watchdog).
        errs = _load_json(dump, "builder_logs_error.json")
        if isinstance(errs, dict):
            stderr = json.dumps(errs)
        elif isinstance(errs, list):
            stderr = json.dumps(errs)
    if not stderr:
        return None
    has_lock = "database is locked" in stderr
    has_flush_err = ("agent_run_lifecycle_flush_error" in stderr
                     or "sdk_query_error" in stderr)
    if not (has_lock and has_flush_err):
        return None
    evidence: list[str] = []
    lock_count = stderr.count("database is locked")
    evidence.append(f"'database is locked' appears {lock_count}× in Builder log")
    if "agent_run_lifecycle_flush_error" in stderr:
        evidence.append("agent_run_lifecycle_flush_error logged (lifecycle "
                        "couldn't write event after lock)")
    if "INSERT INTO agent_run_events" in stderr:
        evidence.append("Offending SQL is `INSERT INTO agent_run_events` "
                        "(autoflush race during lifecycle event write)")
    if "do_epoll_wait" in threads or "futex_wait" in threads:
        evidence.append("Process threads idle on epoll/futex (Builder waiting, "
                        "not actively retrying)")
    # High confidence when both the lock AND the lifecycle flush error are
    # present together; partial credit for partial signal.
    confidence = 0.95 if (lock_count >= 2 and "agent_run_lifecycle_flush_error" in stderr) else 0.7
    return Match(
        pattern_id="P18",
        name="SQLite database-locked during agent_run lifecycle flush (transient)",
        confidence=confidence,
        evidence=evidence,
        fix_pointer=(
            "Transient: kill Builder + run.py for this iter, retry on a fresh "
            "workspace copy. The DB lock is from concurrent SQLAlchemy session "
            "autoflush on the same SQLite WAL; clean restart on a fresh "
            "/tmp/devpulse-<uuid>/ usually succeeds. If the same iter hits P18 "
            "twice in a row, escalate as IMP-010-class: needs source fix in "
            "src/autonomous_agent_builder/orchestrator/agent_run_lifecycle.py "
            "(session.no_autoflush block around event INSERT, or queue events "
            "for a single-writer thread). Track under ROADMAP M2.6 typed-retry."
        ),
        category="transient",
    )


def match_p19_tool_not_found_hang(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P19 (2026-05-24): Builder hangs after `tool_not_found_in_registry`
    warnings for tools listed in an agent's allowed_tools but missing from
    `_SDK_BUILTINS` / custom_tools in `agents/tool_registry.py`.

    Symptom: agent's prompt template instructs the model to call a tool (e.g.,
    `AskUserQuestion`, `mcp__builder__task_recover`, `mcp__builder__workspace_scaffold`)
    but the registry silently dropped that tool at build time, logging
    `tool_not_found_in_registry`. The model either emits text instead of
    tool_use (and the lifecycle waits for a tool result that never comes), OR
    the next chat→chat transition triggers a fresh registry build that drops
    the same tool again, and the new agent never makes progress. Builder polls
    `/api/dashboard/board` indefinitely.

    Confidence signature:
      - `tool_not_found_in_registry` warning(s) in builder_stdout_stderr.log
      - Followed by silence (no new agent_phase_start / tool_use events)
      - WAL mtime stale ≥180s (watchdog fired)

    Category: persistent. Auto-retry won't help — the same agent definition
    + missing schemas will re-trigger the warning. Operator (or Fix lane)
    must add the missing schemas to `_SDK_BUILTINS` OR remove the tools from
    the agent's allowed_tools.
    """
    stderr = _load_text(dump, "builder_stdout_stderr.log")
    if not stderr:
        # Watchdog dumps may not include the raw stdout; fall back to errors
        errs = _load_json(dump, "builder_logs_error.json")
        if isinstance(errs, (dict, list)):
            stderr = json.dumps(errs)
    if not stderr:
        return None
    if "tool_not_found_in_registry" not in stderr:
        return None
    # Extract which tools were dropped (regex on the structured log line)
    missing_tools: list[str] = []
    for m in re.finditer(r"tool_not_found_in_registry\s+tool=(\S+)", stderr):
        t = m.group(1)
        if t not in missing_tools:
            missing_tools.append(t)
    if not missing_tools:
        return None
    evidence: list[str] = [
        f"{len(missing_tools)} tool(s) dropped at registry build: {missing_tools[:6]}",
    ]
    # Confidence boost when the hung agent had stop_reason=tool_use just before
    # (lifecycle is waiting for a tool result that won't come)
    if "stop_reason=tool_use" in stderr:
        evidence.append("Last agent phase ended with stop_reason=tool_use "
                        "(lifecycle expecting tool result that will never arrive)")
    if "do_epoll_wait" in threads or "futex_wait" in threads:
        evidence.append("Process threads idle on epoll/futex (waiting silently)")
    confidence = 0.9 if "stop_reason=tool_use" in stderr else 0.7
    return Match(
        pattern_id="P19",
        name="Agent prompt references tools missing from registry (persistent)",
        confidence=confidence,
        evidence=evidence,
        fix_pointer=(
            "src/autonomous_agent_builder/agents/tool_registry.py:_SDK_BUILTINS — "
            f"add ToolSchema entries for the dropped tools: {missing_tools}. "
            "Cross-check src/autonomous_agent_builder/agents/definitions.py to "
            "confirm the agent intentionally needs these tools (don't paper over "
            "by removing the prompt instruction — the agent's product behavior "
            "depends on them). After adding schemas, re-run baseline."
        ),
        category="persistent",
    )


def match_p22_codegen_sonnet_api_latency(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P22 (2026-05-24): code-gen Sonnet agent's LLM API response time exceeds
    the hang_watchdog idle threshold — false-positive watchdog fire.

    Symptom: baseline.py's hang_watchdog fires after 180s of WAL idle while
    the Sonnet model is processing a large implementation prompt. Timeline:
      12:41:37  code-gen agent_phase_start (Sonnet model, effort=high)
      12:43:39  first code-gen tool call (mcp__workspace__list_directory)
                → 122s LLM API wait
      12:44:36  last code-gen tool call; Sonnet processing tool results
      12:48:16  watchdog fires (190s after last WAL write at 12:45:05)

    Idle period close to threshold (150–360s). No agent_phase_complete for
    code-gen. The agent was making progress; it simply waited for Sonnet
    longer than the watchdog allows.

    Root cause: --idle-seconds 180 is shorter than Sonnet's observed first-
    response latency (~120s) and inter-turn latency (~180s+) on large
    implementation prompts.

    Fix: increase --idle-seconds in baseline.py:_spawn_hang_watchdog from
    180 to 600. This accommodates Sonnet's observed latency variance while
    still catching genuine hangs (infinite DB-lock loops, etc.) well within
    the 1500s per-iter timeout.

    Category: api_latency. Not a source bug in Builder — baseline.py
    harness calibration fix only.
    """
    idle_seconds = float(stuck.get("idle_seconds", 0))
    # Only fire if idle is in the "close to threshold" band.
    # True infinite hangs (DB lock loops, etc.) would persist until the
    # 1500s iter timeout fires — we'd see idle_seconds ≫ 360.
    if not (120 <= idle_seconds <= 360):
        return None

    # P22 fires only for real watchdog dumps, not synthetic wall-clock ones.
    if stuck.get("reason") == "wall_clock_budget_exceeded" or stuck.get("synthesized"):
        return None

    # Need builder log to confirm code-gen was active.
    # The dump is at evidence_dir/stuck_dumps/<UTC>-pid<PID>/; the log is in
    # evidence_dir/ (dump.parent.parent). Also check stuck.evidence_dir.
    stderr = _load_text(dump, "builder_stdout_stderr.log")
    if not stderr:
        candidates = [
            dump.parent.parent / "builder_stdout_stderr.log",  # evidence_dir/
        ]
        ed_str = stuck.get("evidence_dir")
        if ed_str:
            candidates.append(pathlib.Path(ed_str) / "builder_stdout_stderr.log")
        for log_file in candidates:
            if log_file.exists():
                try:
                    stderr = log_file.read_text(errors="replace")
                    break
                except OSError:
                    pass
    if not stderr:
        return None

    if "agent=code-gen" not in stderr:
        return None
    # Must not have completed — if it finished, the idle was something else.
    # Check same-line (log lines are single-line structured JSON).
    has_codegen_complete = any(
        "agent_phase_complete" in line and "agent=code-gen" in line
        for line in stderr.splitlines()
    )
    if has_codegen_complete:
        return None

    evidence: list[str] = []
    evidence.append(
        f"idle_seconds={idle_seconds:.1f} — within 120–360s band "
        "(close to 180s watchdog threshold; consistent with Sonnet API latency)"
    )
    evidence.append("'agent=code-gen' found — Sonnet implementation agent was active")
    evidence.append("no 'agent_phase_complete agent=code-gen' — LLM response still in-flight when watchdog fired")

    codegen_calls = (
        stderr.count("mcp__workspace__list_directory")
        + stderr.count("mcp__workspace__run_command")
        + stderr.count("mcp__workspace__run_tests")
        + stderr.count("mcp__workspace__run_linter")
    )
    if codegen_calls > 0:
        evidence.append(
            f"{codegen_calls}× code-gen workspace tool call(s) — agent made progress "
            "before watchdog fired (second Sonnet response timed out)"
        )
        confidence = 0.88
    else:
        evidence.append(
            "no code-gen workspace tool calls — Sonnet first-response latency >180s"
        )
        confidence = 0.80

    return Match(
        pattern_id="P22",
        name="code-gen Sonnet API latency exceeds watchdog idle threshold (api_latency)",
        confidence=confidence,
        evidence=evidence,
        fix_pointer=(
            "False-positive watchdog fire: Sonnet LLM response time exceeded 180s idle "
            "threshold. Fix: increase --idle-seconds from 180 to 600 in "
            "baseline.py:_spawn_hang_watchdog. "
            "Verify no concurrent Sonnet sessions on other ports (9876, 9877) are "
            "consuming API quota/bandwidth and inflating latency."
        ),
        category="api_latency",
    )


def match_p23_sprint_implementation_deadlock(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P23 (2026-05-25): Sprint in 'implementation' state with all active tasks
    failed — orchestrator quiesces and never dispatches remaining/recovery work.

    Symptom: baseline.py's hang_watchdog fires after 600s+ of WAL idle.
    Timeline:
      19:52:02  dispatch_background_start → _phase_build_verify for task X
      19:52:12  task X transitions to status=failed phase=integration (DB write)
      20:02:18  watchdog fires (605.7s after last WAL activity)

    Builder kept responding to GET /api/dashboard/board polls but made no
    further dispatch attempts. Sprint remains in status='implementation' with
    3/5 tasks failed and 2/5 pending (blocked by failed deps). Never transitions
    to blocked/shipped/failed.

    Root cause: Orchestrator has no handler for "all in-flight sprint tasks
    reached failed state while sprint still shows implementation." It exits the
    dispatch loop and waits for a signal that never comes.

    Confidence signature:
      - idle_seconds >= 550 (above the 600s watchdog threshold; P22 covers 120-360s)
      - Real watchdog dump (not synthetic wall-clock budget)
      - DB: sprint with status='implementation'
      - DB: ≥1 task status='failed', ≥1 task status='pending', 0 tasks in-progress
      - Builder log: last dispatch_phase was _phase_build_verify; board poll flood after

    Category: persistent. Source fix needed in orchestrator.
    """
    idle_seconds = float(stuck.get("idle_seconds", 0))
    # P23 fires at 550+s. P22 covers 120-360s. Both are mutually exclusive.
    if idle_seconds < 550:
        return None
    # Real watchdog dump only — not synthetic wall-clock abort (P21 covers that).
    if stuck.get("reason") == "wall_clock_budget_exceeded" or stuck.get("synthesized"):
        return None
    if con is None:
        return None

    try:
        # Sprint table uses 'phase' (not 'status') — shipped/implementation/blocked
        sprints = list(con.execute(
            "SELECT id, phase FROM sprints WHERE phase='implementation' LIMIT 1"
        ))
    except sqlite3.Error:
        return None
    if not sprints:
        return None

    try:
        tasks = list(con.execute("SELECT id, status, title FROM tasks ORDER BY created_at"))
    except sqlite3.Error:
        return None
    if not tasks:
        return None

    failed_tasks = [t for t in tasks if t["status"] == "failed"]
    pending_tasks = [t for t in tasks if t["status"] == "pending"]
    done_tasks = [t for t in tasks if t["status"] == "done"]
    in_progress = [t for t in tasks
                   if t["status"] not in ("failed", "pending", "done")]

    if not failed_tasks or in_progress:
        return None
    if not pending_tasks:
        return None

    evidence: list[str] = [
        f"sprint phase=implementation (never transitioned to blocked/shipped/failed)",
        f"{len(failed_tasks)} task(s) status=failed: "
        f"{[t['title'][:40] for t in failed_tasks[:3]]}",
        f"{len(pending_tasks)} task(s) status=pending (blocked by failed deps)",
        f"{len(done_tasks)} task(s) done — partial sprint progress before stall",
        f"idle_seconds={idle_seconds:.1f} (watchdog fired at 600s threshold)",
    ]

    # Check builder log for the quiescence signature
    stderr = _load_text(dump, "builder_stdout_stderr.log")
    if not stderr:
        candidates = [dump.parent.parent / "builder_stdout_stderr.log"]
        ed_str = stuck.get("evidence_dir")
        if ed_str:
            candidates.append(pathlib.Path(ed_str) / "builder_stdout_stderr.log")
        for log_file in candidates:
            if log_file.exists():
                try:
                    stderr = log_file.read_text(errors="replace")
                    break
                except OSError:
                    pass

    log_confidence_boost = False
    if stderr:
        has_build_verify = any(
            "dispatch_phase" in line and "_phase_build_verify" in line
            for line in stderr.splitlines()
        )
        if has_build_verify:
            evidence.append("last dispatch_phase was _phase_build_verify")
            log_confidence_boost = True
        board_flood = stderr.count("GET /api/dashboard/board") > 20
        if board_flood:
            evidence.append(
                "board poll flood after quiescence "
                "(harness polling; orchestrator making no dispatches)"
            )
            log_confidence_boost = True

    confidence = 0.90 if log_confidence_boost else 0.75
    return Match(
        pattern_id="P23",
        name="Sprint implementation deadlock — orchestrator quiesces after tasks fail (persistent)",
        confidence=confidence,
        evidence=evidence,
        fix_pointer=(
            "Builder product bug: when all in-flight sprint tasks reach "
            "status=failed and remaining tasks are pending/blocked, the "
            "orchestrator makes no further dispatch attempt and no terminal "
            "sprint transition. Fix options: "
            "(1) Post-dispatch check in "
            "src/autonomous_agent_builder/orchestrator/orchestrator.py — "
            "after a task transitions to failed, if sprint.status='implementation' "
            "and no tasks are in_progress, transition sprint to status='blocked' "
            "with blocked_reason='all_active_tasks_failed'; "
            "(2) Or: task_recovery.py detects failed/integration tasks in an "
            "implementation sprint and re-dispatches with incremented retry_count. "
            "Either way, the sprint must reach a terminal state so the harness "
            "can evaluate the gate and not wait forever."
        ),
        category="persistent",
    )


def match_p21_hook_stream_closed(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P21 (2026-05-24): Builder server graceful-shutdown hook flood after
    wall-clock budget SIGTERM.

    Symptom: baseline.py sends SIGTERM when the 1800s iter budget expires.
    Uvicorn starts graceful shutdown (`INFO: Shutting down` / `INFO: Waiting
    for background tasks to complete`). In-flight Claude Code CLI subprocesses
    still have pending hook permission requests; their control stream closes on
    shutdown, producing: `Error in hook callback hook_N: ... error: Stream
    closed` or `error: Tool permission stream closed before response received`.
    These flood the builder log (100+ occurrences) while uvicorn awaits all
    background tasks. Iter aborts via `wall_clock_budget_exceeded`. No watchdog
    dump (watchdog detects silent stall; active-logging Builder doesn't stall).

    Category: budget_exhausted. Not a true hang — Builder was making progress
    throughout. The iter simply ran longer than the 1800s budget. Check for
    earlier P18b DB lock errors (`dispatch_background_error database is locked`)
    in the same log; those cause tasks to fail and restart, adding time.

    Source-fixed 2026-05-24: baseline.py now writes a synthetic STUCK_DETECTED.json
    to evidence_dir when wall_clock budget fires with no watchdog dump, allowing
    this matcher to run.
    """
    stderr = _load_text(dump, "builder_stdout_stderr.log")
    if not stderr:
        evidence_dir = stuck.get("evidence_dir") or stuck.get("workspace")
        if evidence_dir:
            ed = pathlib.Path(evidence_dir)
            log_file = ed / "builder_stdout_stderr.log"
            if log_file.exists():
                try:
                    stderr = log_file.read_text(errors="replace")
                except OSError:
                    stderr = ""
    if not stderr:
        return None

    # P21 fires only for the wall-clock-budget path (synthetic STUCK_DETECTED.json
    # written by baseline.py). P22 covers watchdog-triggered SIGTERM where the
    # code-gen Sonnet response was just slow.
    if stuck.get("reason") != "wall_clock_budget_exceeded" and not stuck.get("synthesized"):
        return None

    has_shutdown = "INFO:     Shutting down" in stderr
    has_hook_stream = (
        "Error in hook callback hook_" in stderr
        and ("error: Stream closed" in stderr
             or "Tool permission stream closed" in stderr)
    )
    if not (has_shutdown and has_hook_stream):
        return None

    evidence: list[str] = []
    stream_closed_count = stderr.count("error: Stream closed") + stderr.count(
        "Tool permission stream closed"
    )
    evidence.append(
        f"'INFO: Shutting down' found — Builder received SIGTERM from baseline.py"
        " wall-clock budget enforcement"
    )
    evidence.append(
        f"{stream_closed_count}× hook-stream error(s) after shutdown "
        "('Stream closed' / 'Tool permission stream closed before response received')"
    )
    if "dispatch_background_error" in stderr and "database is locked" in stderr:
        lock_count = stderr.count("database is locked")
        evidence.append(
            f"P18b precursor: {lock_count}× 'database is locked' in "
            "dispatch_background_error — tasks failed early, extending iter time"
        )
    confidence = 0.92 if stream_closed_count >= 5 else 0.7
    return Match(
        pattern_id="P21",
        name="Builder graceful-shutdown hook flood after wall-clock SIGTERM (budget_exhausted)",
        confidence=confidence,
        evidence=evidence,
        fix_pointer=(
            "Iter exceeded 1800s budget → SIGTERM → hook stream closed. "
            "Not a source bug in Builder. Investigate WHY the iter ran long: "
            "(1) Check for 'dispatch_background_error database is locked' earlier "
            "in the log — P18b DB lock in the dispatch phase transition commit "
            "causes tasks to fail and restart (fix: add retry in "
            "src/autonomous_agent_builder/api/routes/dispatch.py:_run_dispatch_step "
            "for OperationalError, same pattern as P18's persist_realtime_run_update fix); "
            "(2) The task may be genuinely complex for this fixture — consider "
            "increasing DEFAULT_ITER_WALL_CLOCK_SECONDS in baseline.py if P18b is fixed "
            "and the iter still times out."
        ),
        category="budget_exhausted",
    )


def match_p20_orchestrator_livelock(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P20 (2026-05-24): Orchestrator infinite recovery loop after agent
    failure / hook-blocked polling. Distinct from P18/P19 silent-hang class —
    Builder *is* writing the DB actively (watchdog correctly does NOT fire).
    Stuck signal comes from the wall-clock budget instead.

    Symptom: many short `agent_phase_complete agent=chat` events back-to-back
    with `stop_reason=end_turn`, interspersed with `hook_blocked_bash`
    warnings. Multiple `embedded_dispatch_followup_selected` for the same
    task_id. Possibly a `Control request timeout: initialize` or other
    `agent_unexpected_error` somewhere. Lifecycle bounces between phases
    (planning ↔ implementation ↔ pr_creation ↔ build_verify) without
    converging to `done`. ~$0.5–2 burned per iter.

    Root cause: when a Builder agent fails (timeout, hook block, unrecoverable
    error), the orchestrator's recovery path dispatches another chat agent to
    "figure out what to do" — but that agent has no way to actually unblock
    the underlying issue (hook is enforced; SDK error is transient but not
    retried; etc.), so it ends with stop_reason=end_turn (no useful action)
    and the orchestrator dispatches yet another chat. Infinite chat→chat
    recovery loop bounded only by wall-clock budget.

    Confidence signature:
      - `reason: wall_clock_budget_exceeded` in stuck metadata (watchdog
        explicitly did not fire — WAL was active)
      - ≥5 `agent_phase_complete agent=chat` events in the same iter
      - ≥3 occurrences of the same (followup_task_id, reason) pair — i.e. the
        same task dispatched to the same phase 3+ times (livelock). Threshold is
        max_retries+1 (default 2+1=3): gate_feedback allows up to 2 QG retries,
        so count=2 is normal; count≥3 means remediation isn't converging. NOTE:
        a task appearing with different reasons (impl→QG→PR→build) is normal
        lifecycle — matcher counts (task_id, reason) pairs not raw task_id counts
        to avoid false-positives on high-task-count runs that exhaust wall_clock.
      - hook_blocked_bash warnings present (chat agent kept trying blocked ops)
      - Possibly `Control request timeout` or `agent_unexpected_error`

    Category: persistent. Source-fixed 2026-05-24: _phase_quality_gates now
    caps at 3*max_retries total gate-retry attempts; exceeding the cap
    transitions the task to BLOCKED (quality_gate_cap_exceeded) rather than
    re-dispatching indefinitely. If still firing, investigate prompt/tool
    contract drift in the remediator (P19 pattern).
    """
    stderr = _load_text(dump, "builder_stdout_stderr.log")
    if not stderr:
        # Fall back to evidence directory if dump doesn't have the log
        # (watchdog dumps include partial state; wall-clock-aborts dump zero
        # forensics because the watchdog didn't fire). For wall-clock-only
        # stuck, the matcher reads the evidence_dir's main builder log.
        evidence_dir = stuck.get("evidence_dir") or stuck.get("workspace")
        if evidence_dir:
            ed = pathlib.Path(evidence_dir)
            log_file = ed / "builder_stdout_stderr.log"
            if log_file.exists():
                try:
                    stderr = log_file.read_text(errors="replace")
                except OSError:
                    stderr = ""
    if not stderr:
        return None
    # Wall-clock-budget reason is the strongest livelock indicator; without
    # it, this is probably a different class
    reason = stuck.get("reason") or ""
    wall_clock_hit = (reason == "wall_clock_budget_exceeded")
    # structlog formats events with column padding (`agent_phase_complete<11 spaces>agent=chat`),
    # so a literal-space match misses. Regex tolerates any whitespace between
    # the event name and the agent= key.
    chat_completes = len(re.findall(
        r"agent_phase_complete\s+agent=chat", stderr
    ))
    # Extract (task_id, reason) pairs. Normal lifecycle has each task appear once per
    # phase (impl→QG→PR→build — all different reasons), so counting raw task_id
    # appearances produces false positives on high-task-count runs. Count
    # (task_id, reason) pairs instead: a livelock shows the same phase dispatched
    # 2+ times for the same task; normal progression has each pair appear exactly once.
    followup_pairs = re.findall(
        r"embedded_dispatch_followup_selected followup_task_id=(\S+) reason=(\S+)", stderr
    )
    from collections import Counter
    same_task_dispatches = max(Counter(followup_pairs).values()) if followup_pairs else 0
    hook_blocks = stderr.count("hook_blocked_bash")
    sdk_errors = ("Control request timeout" in stderr
                  or "agent_unexpected_error" in stderr)
    # wall_clock_hit alone is not sufficient — a run with many tasks (each progressing
    # normally through up to max_retries=2 gate retries) can exhaust the budget without
    # any livelock. Require same-phase re-dispatch ≥ 3 (one beyond max_retries boundary)
    # or an SDK error. ≥ 2 is normal: gate_feedback allows 2 retries per task.
    _LIVELOCK_THRESHOLD = 3
    primary = (wall_clock_hit and (same_task_dispatches >= _LIVELOCK_THRESHOLD or sdk_errors)) or (
        chat_completes >= 5 and same_task_dispatches >= _LIVELOCK_THRESHOLD
    )
    if not primary:
        return None
    if chat_completes < 5 and same_task_dispatches < _LIVELOCK_THRESHOLD and hook_blocks == 0:
        return None
    evidence: list[str] = [f"{chat_completes} `agent_phase_complete agent=chat` events"]
    if same_task_dispatches >= _LIVELOCK_THRESHOLD:
        evidence.append(f"same (task, phase) pair dispatched {same_task_dispatches}× via "
                        f"`embedded_dispatch_followup_selected` (same phase repeated)")
    if hook_blocks > 0:
        evidence.append(f"{hook_blocks} `hook_blocked_bash` warnings "
                        "(chat agent retrying blocked operations)")
    if sdk_errors:
        evidence.append("SDK error or agent_unexpected_error logged "
                        "(orchestrator recovery path likely triggered)")
    if wall_clock_hit:
        evidence.append("wall_clock_budget_exceeded (watchdog correctly did "
                        "NOT fire — Builder was writing DB actively, just churning)")
    confidence = 0.9 if (wall_clock_hit and chat_completes >= 5 and same_task_dispatches >= 2) else 0.7
    return Match(
        pattern_id="P20",
        name="Orchestrator infinite recovery loop / agent livelock (persistent)",
        confidence=confidence,
        evidence=evidence,
        fix_pointer=(
            "SOURCE-FIXED (2026-05-24): _phase_quality_gates in "
            "src/autonomous_agent_builder/orchestrator/orchestrator.py now checks "
            "retry_count >= 3*max_retries before invoking the gate runner; "
            "transitions to BLOCKED with blocked_reason='quality_gate_cap_exceeded:...' "
            "when cap is hit. task_recovery.py recovers this state to IMPLEMENTATION "
            "with retry_count reset to 0. If P20 still fires after deploying this fix, "
            "investigate: WHY did remediation keep claiming success without converging? "
            "`hook_blocked_bash` suggests chat agent prompt/tool contract drift (P19 "
            "pattern); `Control request timeout: initialize` suggests Claude SDK init "
            "timing."
        ),
        category="persistent",
    )


def match_p25_build_verify_silent_dispatch(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P25 (2026-05-25): build_verify phase dispatched but agent never starts.

    Symptom: `dispatch_phase=build_verify` (+ `dispatch_background_start`) fires
    but `agent_phase_start` never follows for that phase.  Builder idles until
    watchdog fires (~600s).  py_spy dump is 0 bytes (process dead or unreachable).
    `sprint_branch_ff_merged_to_main` absent.

    Two observed variants:
    - Orchestrator path (E/run-2): code-gen → QG → pr_creation → build_verify →
      silence → process dies.
    - Chat-agent path (C/run-1): chat calls task_dispatch → dispatch_background_start
      + dispatch_phase=build_verify in background → chat completes its own turn →
      silence (build_verify subprocess never launches).

    Confidence signature:
      - `dispatch_phase.*build_verify` present
      - No `agent_phase_start` after the last such line
      - `sprint_branch_ff_merged_to_main` absent
      - idle_seconds ≥ 450
      - py_spy dump file is 0 bytes (optional; strengthens confidence)

    Category: persistent.  Root cause unknown (silent background-task launch failure
    in the Builder's async dispatch layer).  Use --allow-imperfect-iter until source
    fixed.  Observed ~12% incidence on multi-task fixtures C and E.
    """
    del threads, sockets
    # Load builder log: try dump dir, then evidence_dir from stuck metadata,
    # then dump.parent.parent (evidence dir for real watchdog dumps where
    # workspace= is the devpulse dir, not the harness evidence dir).
    stderr = _load_text(dump, "builder_stdout_stderr.log")
    if not stderr:
        candidates = []
        evidence_dir = stuck.get("evidence_dir") or stuck.get("workspace")
        if evidence_dir:
            candidates.append(pathlib.Path(evidence_dir) / "builder_stdout_stderr.log")
        # dump is <evidence_dir>/stuck_dumps/<timestamp>/; grandparent is evidence_dir
        candidates.append(dump.parent.parent / "builder_stdout_stderr.log")
        for log_file in candidates:
            if log_file.exists():
                try:
                    stderr = log_file.read_text(errors="replace")
                    break
                except OSError:
                    continue
    if not stderr:
        return None

    # Must have at least one build_verify dispatch
    if not re.search(r"dispatch_phase\s+phase=_phase_build_verify", stderr):
        return None

    # Find position of last dispatch_phase=build_verify
    last_bv_match = None
    for m in re.finditer(r"dispatch_phase\s+phase=_phase_build_verify", stderr):
        last_bv_match = m
    if last_bv_match is None:
        return None

    tail = stderr[last_bv_match.end():]

    # Core check: no agent_phase_start after the last build_verify dispatch
    if re.search(r"agent_phase_start", tail):
        return None  # build_verify agent did start — different hang class

    # Sprint never merged AFTER the last build_verify dispatch.
    # (Earlier tasks may have merged normally — check tail only.)
    if "sprint_branch_ff_merged_to_main" in tail:
        return None

    # Idle long enough for a full watchdog window
    idle = stuck.get("idle_seconds", 0)
    if idle < 450:
        return None

    # Optional: py_spy dump empty (strengthens confidence)
    py_spy_empty = False
    py_spy = dump / "py_spy_dump.txt"
    if py_spy.exists():
        try:
            py_spy_empty = py_spy.stat().st_size == 0
        except OSError:
            pass

    evidence: list[str] = [
        "dispatch_phase=build_verify present in log",
        "no agent_phase_start after last build_verify dispatch",
        f"idle_seconds={idle:.0f}s — full watchdog window expired",
        "sprint_branch_ff_merged_to_main absent — sprint never completed",
    ]
    if py_spy_empty:
        evidence.append("py_spy_dump.txt is 0 bytes — process unreachable at dump time")

    confidence = 0.85 if py_spy_empty else 0.75

    return Match(
        pattern_id="P25",
        name="build_verify silent dispatch failure — agent never starts after phase dispatched",
        confidence=confidence,
        evidence=evidence,
        fix_pointer=(
            "Root cause: Builder's background-task runner silently fails to spawn the "
            "build_verify agent subprocess (OOM, SDK init failure, worker thread crash). "
            "Two investigation paths: "
            "(1) Background dispatch entrypoint — add explicit error logging + "
            "fail-fast when dispatch_background_start completes without "
            "agent_phase_start within ~60s. "
            "(2) orchestrator.py follow-up logic — when chat agent calls task_dispatch "
            "for build_verify but background start fails, surface BLOCKED state instead "
            "of silently waiting. "
            "Workaround: --allow-imperfect-iter in baseline runs."
        ),
        category="persistent",
    )


def match_p24_stale_port_session_mismatch(
    dump: pathlib.Path,
    stuck: dict,
    con: sqlite3.Connection | None,
    threads: str,
    sockets: str,
) -> Match | None:
    """P24: stale builder on port → run.py tracks session_id from wrong instance.

    Symptom: a previous builder process was occupying the baseline port when the
    current iter started.  run.py connected, obtained a session_id from the old
    builder, then started polling that session against the fresh builder that
    replaced it.  The fresh builder has no chat sessions (DB shows chat_sessions=0,
    builder_sessions.json shows sessions=[]), so every history poll returns an
    empty response indefinitely.  No agent runs are ever dispatched; idle timer
    expires and watchdog fires.

    Confidence signature:
      - builder_sessions.json shows sessions=[]  (fresh builder, no session yet)
      - agent_builder.db chat_sessions table has 0 rows
      - idle_seconds > 500 (full watchdog window burned waiting for missing session)

    Category: transient.  Kill any builder still on the target port and re-run
    the iter; run.py will get a fresh session_id from the correct instance.
    Fix: `ss -tlnp 'sport = :<port>'` → kill the PID → rerun baseline.
    """
    del threads, sockets
    # Check builder_sessions.json for empty sessions list
    sessions_data = _load_json(dump, "builder_sessions.json")
    if not isinstance(sessions_data, dict):
        return None
    if sessions_data.get("sessions") or sessions_data.get("count", 0) != 0:
        return None  # sessions exist — different hang
    # Check DB chat_sessions = 0
    if con is not None:
        try:
            row = con.execute("SELECT count(*) FROM chat_sessions").fetchone()
            if row and row[0] != 0:
                return None
        except Exception:
            pass
    # Check idle_seconds long enough that port contention is plausible
    idle = stuck.get("idle_seconds", 0)
    if idle < 400:
        return None
    port = stuck.get("builder_port", "?")
    return Match(
        pattern_id="P24",
        name="Stale-port session mismatch — run.py tracked wrong builder instance",
        confidence=0.88,
        evidence=[
            f"builder_sessions.json: sessions=[] (no active session on this builder)",
            f"chat_sessions table: 0 rows — builder never received a valid session",
            f"idle_seconds={idle:.0f}s — full watchdog window burned on empty polls",
            f"port={port} — likely occupied by a prior builder at baseline start",
        ],
        fix_pointer=(
            f"Kill any builder still on port {port}: "
            f"`ss -tlnp 'sport = :{port}'` → kill the PID. "
            "Then re-run: `python3 scripts/autoresearch/baseline.py --fixtures <X> --n 5`. "
            "Preflight warns when ports are in use; treat that as a hard blocker."
        ),
    )


MATCHERS = [
    match_p24_stale_port_session_mismatch,  # check FIRST: sessions=0 + long idle → port conflict
    match_p18_db_lock_transient,      # very specific signature; check early so
                                       # the transient-retry path fires before
                                       # any persistent fallback misclassifies it
    match_p19_tool_not_found_hang,    # also very specific; check before generic
    match_p25_build_verify_silent_dispatch,   # build_verify dispatched, agent never starts
    match_p23_sprint_implementation_deadlock,  # 600+s idle: sprint=implementation, all tasks failed
    match_p22_codegen_sonnet_api_latency,      # watchdog false-positive: Sonnet latency 120-360s idle
    match_p21_hook_stream_closed,              # wall-clock SIGTERM → hook flood (budget_exhausted)
    match_p20_orchestrator_livelock,       # wall-clock-budget livelock signature
    match_p11_p14_respond_409,        # very specific — check next
    match_p10_respond_400,
    match_p9_sprint_merge_untracked_venv,
    match_p6_sprint_merge_venv,
    match_p5_sprint_merge_main,
    match_p4_pipe_deadlock,
    match_p1_contract_drift,
    match_p2_free_text_scoping,
    match_p3_watchdog_false_positive,
    # Substrate-state matchers (read repo TSVs + summary, not dump dir).
    # Always check last so a real hang-dump match wins on confidence ordering.
    match_p15_composite_zero,
    match_p16_high_cv,
    match_p17_seed_dep_gap,
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
