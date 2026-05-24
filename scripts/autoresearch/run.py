#!/usr/bin/env python3
"""Atomic fixture runner for the autoresearch loop.

One fixture, one iteration. Captures all evidence needed for the per-session
and per-prompt TSV rows. Designed to be called by baseline.py and loop.py,
or directly for manual experimentation.

Workflow (see docs/autoresearch/HARNESS.md):
1. Copy immutable seed → fresh workspace; verify sha256.
2. Build OTEL env per SDK-OBSERVABILITY.md.
3. Spawn `builder start --port $PORT` against the workspace.
4. Drive the fixture via POST /api/agent/chat + /api/agent/chat/respond.
5. Wait for board to reach `shipped` phase or timeout.
6. Run `npm run build && npm run test` in workspace/app for correctness.
7. Capture analyze.json, metrics.json, board.json, errors.json.
8. Parse raw API bodies for context breakdown.
9. Append one row to optimize_results.tsv (or baseline_runs.tsv if --baseline).
10. Append N rows to per_prompt_results.tsv.
11. Tear down workspace.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

try:
    import requests
except ImportError:  # pragma: no cover
    print("ERROR: requests not installed. pip install requests", file=sys.stderr)
    sys.exit(2)


FIXTURES: dict[str, dict] = {
    "A": {
        "prompt": "Add a button on the homepage that shows the current time when clicked.",
        "follow_ups": [],
        "timeout_s": 1500,
    },
    "B": {
        "prompt": "I want to add a notes feature so I can write short text notes that persist between visits.",
        "follow_ups": ["recommended", "recommended", "recommended"],
        "timeout_s": 1500,
    },
    "C": {
        "prompt": "Make the app better for power users.",
        "follow_ups": ["recommended", "recommended", "recommended", "recommended"],
        "timeout_s": 1500,
    },
    "D": {
        "prompt": "Improve search.",
        "follow_ups": ["Notes by their text content."],
        "timeout_s": 1500,
    },
    "E": {
        "prompt": "I want to track something on the dashboard.",
        "follow_ups": [
            "Time spent per task this week.",
            "Just a number is fine, no chart needed.",
        ],
        "timeout_s": 1500,
    },
}

DEFAULT_SEED = pathlib.Path("/home/gurusharangupta/.seed/devpulse")
DEFAULT_TSV_ROOT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "autoresearch"


def build_otel_env(run_id: str, fixture_id: str, branch: str, evidence_dir: pathlib.Path) -> dict[str, str]:
    raw_bodies = evidence_dir / "raw_bodies"
    raw_bodies.mkdir(parents=True, exist_ok=True)
    return {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
        "ENABLE_BETA_TRACING_DETAILED": "1",
        "OTEL_TRACES_EXPORTER": "otlp",
        "OTEL_METRICS_EXPORTER": "otlp",
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
        "OTEL_METRIC_EXPORT_INTERVAL": "1000",
        "OTEL_LOGS_EXPORT_INTERVAL": "1000",
        "OTEL_TRACES_EXPORT_INTERVAL": "1000",
        "OTEL_SERVICE_NAME": f"autoresearch-{run_id}",
        "OTEL_RESOURCE_ATTRIBUTES": (
            f"run.id={run_id},fixture.id={fixture_id},branch={branch},autoresearch.iteration=true"
        ),
        "OTEL_LOG_USER_PROMPTS": "1",
        "OTEL_LOG_TOOL_DETAILS": "1",
        "OTEL_LOG_TOOL_CONTENT": "1",
        "OTEL_LOG_RAW_API_BODIES": f"file:{raw_bodies}",
    }


def restore_seed(seed: pathlib.Path, workspace: pathlib.Path) -> None:
    if not seed.exists():
        raise FileNotFoundError(
            f"Seed not found at {seed}. Run scripts/autoresearch/setup_seed.sh first."
        )
    shutil.copytree(seed, workspace)
    # Make the working copy writable (seed is read-only).
    subprocess.run(["chmod", "-R", "u+w", str(workspace)], check=True)
    # The seed (a copy of the devpulse template) uses `master` as its default
    # branch, but Builder's sprint-merge code at
    # `orchestrator/sprint_lifecycle.py:sprint_maybe_ff_merge` runs
    # `git checkout main` against `task.feature.project.repo_url`. That URL
    # was set at original `builder init` time and points at
    # `~/Builder-Workspace/devpulse` (the upstream), NOT this ephemeral copy.
    # Two problems compound:
    #   1. The upstream's default branch is `master`, not `main`, so the merge
    #      step errors with `"could not check out main: pathspec 'main' did
    #      not match"` for every sprint — every fixture A run ended in
    #      phase=blocked even with all tasks done + all gates green.
    #   2. If the merge ever succeeded, Builder would be writing into the
    #      user's real workspace. Autoresearch must not leak there.
    # Fix: (a) repoint the project's repo_url to this ephemeral workspace so
    # sprint merge operates on the ephemeral copy; (b) create `main` from
    # current HEAD as the merge target. Caught 2026-05-23 cycle 6 by the
    # diagnose_hang.py P5 matcher (which initially detected the same symptom
    # cycle 5; the real fix was discovered after re-reading sprint_lifecycle.py
    # to find where repo_root comes from).
    git_env = {"GIT_TERMINAL_PROMPT": "0"}
    try:
        existing = subprocess.run(
            ["git", "-C", str(workspace), "branch", "--list", "main"],
            capture_output=True, text=True, timeout=5, env=git_env,
        )
        if not existing.stdout.strip():
            subprocess.run(
                ["git", "-C", str(workspace), "branch", "main"],
                check=True, timeout=5, env=git_env,
            )
    except (subprocess.SubprocessError, OSError):
        # Seed without git is a setup error elsewhere — let Builder surface it.
        pass

    # Repoint projects.repo_url to the ephemeral workspace so sprint merge
    # operates here (and never on the user's upstream).
    #
    # P18 (2026-05-24): also wipe stale Builder state from prior sessions
    # that the seed snapshot carries forward. Before this, the seed DB still
    # held features/tasks/sprints/chat_sessions from whenever the seed was
    # captured (e.g., a "GitHub authentication UI" task leaked into every B
    # fixture iter, blocking the agent and producing decision_status=incomplete
    # even when pytest passed and feature_correct=True). Result: gate_pass_rate
    # _full=false on every iter, no matter how clean the rest of the substrate.
    # Wiping leaves only the projects row (repo_url-repointed above) so each
    # iter starts from an empty backlog — same product code, fresh execution
    # state. Order respects child→parent deletion to avoid orphan rows even
    # if Builder later enables FK enforcement.
    db_path = workspace / ".agent-builder" / "agent_builder.db"
    if db_path.exists():
        try:
            with sqlite3.connect(str(db_path)) as con:
                con.execute("UPDATE projects SET repo_url=?", (str(workspace),))
                # Wipe stale execution state; preserve projects + zero-row
                # config tables (approvals, quality_gates, etc.).
                for table in (
                    "agent_run_events", "agent_runs",
                    "chat_events", "chat_messages", "chat_sessions",
                    "gate_results", "design_documents",
                    "tasks", "sprints", "workspaces", "features",
                ):
                    con.execute(f"DELETE FROM {table}")
                con.commit()
        except sqlite3.Error:
            # If the DB is locked / schema differs, surface via Builder logs.
            pass

    # Untrack .venv from git AND add it to .gitignore so neither the
    # post-merge "tracked changes" check nor the `git checkout main` step
    # sees .venv as a problem. The devpulse seed commits part of .venv
    # (notably the lib64 symlink); when task code-gen recreates .venv fresh,
    # those tracked entries first appear as deleted (P6 — caught cycle 7),
    # then later as untracked files that block `git checkout main`
    # ("Updating the following directories would lose untracked files",
    # P9 — caught cycle 10). Gitignoring .venv covers both: ignored files
    # neither show as "tracked changes" nor block checkout. Untracking +
    # gitignoring + committing leaves the working tree's .venv alone.
    try:
        # 1. Append .venv/ to .gitignore (idempotent).
        gitignore = workspace / ".gitignore"
        existing = gitignore.read_text() if gitignore.exists() else ""
        if not any(line.strip() in (".venv", ".venv/") for line in existing.splitlines()):
            with gitignore.open("a") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write(".venv/\n")
        # 2. Untrack any .venv entries currently in the index.
        subprocess.run(
            [
                "git", "-C", str(workspace),
                "rm", "-r", "--cached", "--ignore-unmatch", "-q", ".venv",
            ],
            check=False, timeout=10, env=git_env,
        )
        # 3. Stage .gitignore explicitly (rm doesn't pick it up).
        subprocess.run(
            ["git", "-C", str(workspace), "add", ".gitignore"],
            check=False, timeout=5, env=git_env,
        )
        # 4. Commit only if something staged; otherwise git complains.
        diff = subprocess.run(
            ["git", "-C", str(workspace), "diff", "--cached", "--quiet"],
            timeout=5, env=git_env,
        )
        if diff.returncode != 0:
            subprocess.run(
                [
                    "git", "-C", str(workspace), "-c", "user.email=autoresearch@local",
                    "-c", "user.name=autoresearch", "commit",
                    "-m", "autoresearch: gitignore + untrack .venv",
                ],
                check=False, timeout=10, env=git_env,
            )
    except (subprocess.SubprocessError, OSError):
        pass


def wait_for_ready(url: str, timeout_s: int = 60) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code < 500:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise TimeoutError(f"Builder did not become ready at {url} within {timeout_s}s")


def board_active_phase(port: int) -> str:
    r = requests.get(f"http://127.0.0.1:{port}/api/dashboard/board", timeout=10)
    r.raise_for_status()
    payload = r.json() or {}
    sprint = payload.get("current_sprint") or {}
    return str(sprint.get("active_phase") or "")


def send_chat(port: int, prompt: str, session_id: str | None = None) -> str:
    r = requests.post(
        f"http://127.0.0.1:{port}/api/agent/chat",
        json={"message": prompt, "session_id": session_id},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["session_id"]


def get_pending_question(port: int, session_id: str) -> dict | None:
    # The /api/agent/chat/history endpoint returns ChatHistoryResponse with
    # `items: list[TimelineItem]`; each TimelineItem has `type` + `status` +
    # `payload` (see src/autonomous_agent_builder/embedded/server/agent_api_models.py).
    # Earlier revisions of this harness expected `events` + `state` — that
    # contract drift made get_pending_question always return None, blocking
    # all autoresearch runs at the first intake question (caught 2026-05-23
    # by the skill's hang_watchdog after a 47-min silent stall on fixture A).
    # Returns the full TimelineItem dict (id + payload) so the caller can
    # build a contract-compliant ChatRespondRequest without re-fetching.
    r = requests.get(
        f"http://127.0.0.1:{port}/api/agent/chat/history",
        params={"session_id": session_id},
        timeout=30,
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    for item in reversed(items):
        if (
            item.get("type") in ("ask_user_question", "tool_approval_request")
            and item.get("status") == "pending"
        ):
            return item
    return None


def send_chat_respond(port: int, session_id: str, pending_item: dict, answer: str) -> None:
    # ChatRespondRequest contract (agent_api_models.py): session_id, event_id,
    # selected_options (list[str] of option labels), custom_text, decision,
    # reason, updated_input. For ask_user_question with `answer == "recommended"`
    # we extract the option label at `recommended_index` (default 0) and pass it
    # as selected_options=[label]. Free-text answers go in custom_text.
    # P11 (2026-05-23): tool_approval_request events require decision=allow|deny,
    # not selected_options/custom_text. Build the correct payload by event type.
    event_id = pending_item["id"]
    item_type = pending_item.get("type", "")
    payload: dict = {"session_id": session_id, "event_id": event_id}
    if item_type == "tool_approval_request":
        payload["decision"] = "allow"
        payload["reason"] = "autoresearch harness: auto-allow"
    else:
        question_payload = pending_item.get("payload") or {}
        options = question_payload.get("options") or []
        if answer == "recommended":
            idx = int(question_payload.get("recommended_index") or 0)
            if 0 <= idx < len(options):
                label = options[idx].get("label") if isinstance(options[idx], dict) else str(options[idx])
                if label:
                    payload["selected_options"] = [label]
                else:
                    payload["custom_text"] = "recommended"
            else:
                payload["custom_text"] = "recommended"
        else:
            # Try to match `answer` to an option label first (so a fixture's scripted
            # follow-up like "Notes by their text content." selects that option when
            # offered); otherwise pass through as custom_text.
            option_labels = [
                opt.get("label") if isinstance(opt, dict) else str(opt) for opt in options
            ]
            if answer in option_labels:
                payload["selected_options"] = [answer]
            else:
                payload["custom_text"] = answer or "Continue with reasonable defaults."
    r = requests.post(
        f"http://127.0.0.1:{port}/api/agent/chat/respond",
        json=payload,
        timeout=60,
    )
    r.raise_for_status()


def latest_chat_state(port: int, session_id: str) -> dict:
    """Return {'running': bool, 'last_event_type': str | None, 'last_assistant_text': str}.

    Probes /api/agent/chat/history and inspects the latest run_status (for the
    running flag) + the latest assistant_message (for the free-text content).
    Used by wait_for_question_or_ship to distinguish three terminal states:
    pending structured question, shipped, or paused-on-free-text-scoping.
    """
    r = requests.get(
        f"http://127.0.0.1:{port}/api/agent/chat/history",
        params={"session_id": session_id},
        timeout=30,
    )
    r.raise_for_status()
    items = r.json().get("items", []) or []
    last_content_type: str | None = None
    last_assistant_text = ""
    last_assistant_final = False
    # `run_status` events are not in VISIBLE_EVENT_TYPES on the server side
    # (see agent_chat_transcript.py), so the history API never returns them.
    # The reliable "chat is done" signal is `assistant_message.payload.final
    # == True` — set when the model ends_turn. Earlier revisions relied on
    # `run_status.running == false`, which never fired because run_status was
    # invisible. Caught 2026-05-23 cycle 9 (P8 in KNOWN_PATTERNS.md).
    content_event_types = {
        "assistant_message",
        "ask_user_question",
        "user_message",
        "tool_approval_request",
    }
    for item in reversed(items):
        if item.get("type") in content_event_types:
            last_content_type = item.get("type")
            if last_content_type == "assistant_message":
                payload = item.get("payload") or {}
                last_assistant_text = str(payload.get("content") or "")
                last_assistant_final = bool(payload.get("final"))
            break
    # `running` is True unless the latest assistant_message is marked final.
    # This is the harness's proxy for "the chat agent has yielded back to the
    # operator and is awaiting input"; if the latest content event is a
    # tool_use or in-flight assistant message, running stays True.
    running = not (
        last_content_type == "assistant_message" and last_assistant_final
    )
    return {
        "running": running,
        "last_content_event_type": last_content_type,
        "last_assistant_text": last_assistant_text,
        "last_assistant_final": last_assistant_final,
    }


def wait_for_question_or_ship(port: int, session_id: str, timeout_s: int) -> str:
    """Poll until one of: structured question pending, board shipped, OR
    the chat naturally completed without surfacing either (paused on a
    free-text scoping question). The third outcome — "proceed_needed" — is
    new in this revision; the harness's outer loop is expected to push the
    chat forward with a "proceed with reasonable defaults" user_message
    rather than wait the full per-question timeout. Caught 2026-05-23 by
    the hang_watchdog when the chat agent's intake path returned a
    multi-bullet markdown question instead of an ask_user_question event.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if get_pending_question(port, session_id):
                return "question"
            if board_active_phase(port) == "shipped":
                return "shipped"
            state = latest_chat_state(port, session_id)
            if (
                not state["running"]
                and state["last_content_event_type"] == "assistant_message"
            ):
                return "proceed_needed"
        except requests.RequestException:
            pass
        time.sleep(2)
    raise TimeoutError(f"No question or ship within {timeout_s}s")


def ship_or_timeout(port: int, timeout_s: int) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if board_active_phase(port) == "shipped":
                return True
        except requests.RequestException:
            pass
        time.sleep(5)
    return False


def capture_evidence(workspace: pathlib.Path, session_id: str, evidence_dir: pathlib.Path) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    cmds = {
        "analyze.json": ["builder", "logs", "analyze", "--session", session_id, "--full", "--json"],
        "metrics.json": ["builder", "metrics", "show", "--json", "--full"],
        "board.json": ["builder", "board", "show", "--json", "--full"],
        "errors.json": ["builder", "logs", "--error", "--compact", "--json"],
    }
    for filename, cmd in cmds.items():
        with (evidence_dir / filename).open("wb") as out:
            subprocess.run(cmd, cwd=str(workspace), stdout=out, check=False)


def run_feature_check(workspace: pathlib.Path, evidence_dir: pathlib.Path | None = None) -> bool:
    """Run the workspace's feature-correctness gate.

    Auto-detect Node (package.json) vs Python (pyproject.toml). Failing
    to detect a known stack returns False so the iteration is recorded
    as a feature-check failure — operator can fix run.py or add a stack.

    P17 (2026-05-23): every subprocess captures stdout+stderr to
    evidence_dir/feature_check.log. Prior shape inherited fds, so a silent
    install failure (pip exit !=0, network blip, lockfile contention) burned
    20+ doomed iterations across fixtures B/C/D/E with feature_correct=False
    and zero forensic trail. Now: every pip/pytest run leaves a phase-tagged
    log line + the subprocess's own output, so the next operator can grep
    feature_check.log instead of re-running by hand.
    """
    app = workspace / "app"
    if not app.exists():
        # Some workspaces keep code at the root (single-package Python repos).
        app = workspace
    log_path = (evidence_dir / "feature_check.log") if evidence_dir else None
    log_fh = log_path.open("ab") if log_path else None

    def _run(phase: str, cmd: list[str], **kwargs) -> None:
        if log_fh:
            log_fh.write(f"\n=== {phase}: {' '.join(cmd)} ===\n".encode())
            log_fh.flush()
            kwargs.setdefault("stdout", log_fh)
            kwargs.setdefault("stderr", subprocess.STDOUT)
        subprocess.run(cmd, check=True, **kwargs)

    try:
        if (app / "package.json").exists():
            _run("npm-build", ["npm", "--prefix", str(app), "run", "build"], timeout=600)
            _run("npm-test", ["npm", "--prefix", str(app), "run", "test", "--", "--watch=false"], timeout=600)
            return True
        if (workspace / "pyproject.toml").exists() or (app / "pyproject.toml").exists():
            # Python stack — run pytest if a tests dir exists; ruff format/check
            # is opt-in via builder's quality gates, not the feature gate here.
            venv_py = workspace / ".venv" / "bin" / "python"
            # P13 (2026-05-23): Builder's workspace_integrated_fast_forward merges
            # the task branch (which has .venv deletions) into the sprint branch.
            # git checkout sprint/* then deletes .venv from the project workspace
            # working tree. If venv_py is gone, recreate a fresh venv so pip
            # install below can proceed without hitting PEP 668 (system-pip block).
            if not venv_py.exists():
                _run("venv-create", [sys.executable, "-m", "venv", str(workspace / ".venv")], timeout=60)
            py = str(venv_py)
            # P12 (2026-05-23): seed .venv is minimal (no jinja2/httpx etc).
            # Install from requirements.txt before running tests so imports
            # don't fail at collection time.
            req_file = workspace / "requirements.txt"
            if req_file.exists():
                _run("pip-install", [py, "-m", "pip", "install", "-q", "-r", str(req_file)], timeout=120)
            tests_dir = next(
                (d for d in (workspace / "tests", app / "tests") if d.exists()),
                None,
            )
            if tests_dir is None:
                # No tests means the feature gate is vacuous — treat as pass
                # so the iteration isn't penalized for the workspace's choice
                # to skip tests. compare.py's other gates still bound the run.
                return True
            _run(
                "pytest",
                [
                    py, "-m", "pytest", str(tests_dir), "-q", "--no-header",
                    # Playwright tests require a live devpulse server.
                    "--ignore-glob=*playwright*",
                    # GitHub service tests require pytest-asyncio + live
                    # credentials — neither available in the harness venv.
                    "--ignore-glob=*test_github*",
                ],
                cwd=str(workspace),
                timeout=600,
            )
            return True
        # Unknown stack — surface as failure so the operator notices
        if log_fh:
            log_fh.write(b"\n=== unknown-stack: no package.json or pyproject.toml found ===\n")
        return False
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        if log_fh:
            log_fh.write(f"\n=== EXCEPTION: {type(exc).__name__}: {exc} ===\n".encode())
        return False
    finally:
        if log_fh:
            log_fh.close()


def evaluate_hard_gates(
    analyze: dict, metrics: dict, board: dict, feature_correct: bool, shipped: bool
) -> tuple[str, dict[str, bool]]:
    # Tier-1 bar is a single session-scoped number: `cache_ratio > 5x after
    # turn 2`. With `_runtime_aggregates(session_id=...)` honestly scoped to
    # this run, `analyze["cache_ratio"]` is the session aggregate. Prior shape
    # walked `prompts[]` which is operator-chat-turn-scoped and produced 1
    # entry for autoresearch fixture-A runs — the test was trivially true.
    runtime_aggs = analyze.get("runtime_aggregates") or {}
    totals = runtime_aggs.get("totals") or {}
    has_agent_runs = int(totals.get("runs") or 0) > 0
    session_cache_ratio = float(analyze.get("cache_ratio") or 0)
    gate_cache = has_agent_runs and session_cache_ratio > 5.0
    # P12 (2026-05-23): metrics response uses "optimization_summary" key, not "optimization".
    optimization = (metrics.get("optimization_summary") or metrics.get("optimization") or {}) if isinstance(metrics, dict) else {}
    chunk_pressure = optimization.get("chunk_pressure") or {}
    gate_chunk = chunk_pressure.get("risk") is False or chunk_pressure.get("chunk_pressure_risk") is False
    gate_flags = (optimization.get("active_avoidable_cost_flags") or []) == []
    # board show schema: tasks in section lists (done/pending/active/review/blocked).
    # Legacy backlog-task-list schema: flat "tasks" list with status field.
    if isinstance(board, dict) and "tasks" not in board:
        non_done = sum(
            len(board.get(s) or []) for s in ("pending", "active", "review", "blocked")
        )
        done_tasks = board.get("done") or []
        gate_rate = bool(done_tasks) and non_done == 0
    else:
        tasks = board.get("tasks") if isinstance(board, dict) else []
        gate_rate = bool(tasks) and all(t.get("status") == "done" for t in tasks)
    gates = {
        "cache_ratio_gt_5x_after_turn_2": gate_cache,
        "chunk_pressure_risk_false": gate_chunk,
        "avoidable_cost_flags_empty": gate_flags,
        "gate_pass_rate_full": gate_rate,
        "feature_correct": feature_correct,
        "fully_shipped": shipped,
    }
    passed = sum(1 for v in gates.values() if v)
    return f"{passed}/{len(gates)}", gates


SESSION_HEADERS = [
    # Must match docs/autoresearch/optimize_results.tsv + baseline_runs.tsv
    # header exactly. Drift here silently corrupts every downstream consumer
    # (compare.py, render_iterations.py, introspect.py). The introspection
    # script auto-detects this drift and surfaces it as the top recommendation.
    "run_id", "timestamp", "branch", "idea_ref",
    "files_touched", "lines_added", "lines_deleted",
    "fixture_id", "noncached_plus_output_tokens", "cache_ratio",
    "chunk_pressure_risk", "avoidable_cost_flags", "gate_pass_rate",
    "feature_correct", "wallclock_s", "operator_turns",
    "composite", "composite_delta_pct", "gates_passed",
    "decision", "notes",
]

PROMPT_HEADERS = [
    "run_id", "prompt_index", "turn_role", "agent_name", "phase",
    "context_budget_tokens", "tokens_input", "tokens_cached", "cache_creation_tokens",
    "tokens_output", "noncached_plus_output_tokens", "cache_ratio",
    "tool_calls_count", "tool_names_json", "stop_reason", "duration_ms",
    "cost_usd", "runtime_sdk", "model", "effort", "context_breakdown_json",
]


def append_session_row(
    *, tsv_path: pathlib.Path, run_id: str, fixture_id: str, branch: str,
    analyze: dict, metrics: dict, gates_passed: str, composite: int,
    wallclock_s: float, feature_correct: bool, decision_status: str,
    idea_ref: str = "", diff_stats: dict | None = None,
) -> None:
    opt = (metrics.get("optimization_summary") or metrics.get("optimization") or {}) if isinstance(metrics, dict) else {}
    chunk = opt.get("chunk_pressure") or {}
    diff_stats = diff_stats or {}
    row = [
        run_id,
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        branch,
        idea_ref,
        diff_stats.get("files_touched", 0),
        diff_stats.get("lines_added", 0),
        diff_stats.get("lines_deleted", 0),
        fixture_id,
        opt.get("noncached_plus_output_tokens") or 0,
        opt.get("cache_ratio") or 0,
        chunk.get("chunk_pressure_risk", chunk.get("risk")),
        json.dumps(opt.get("active_avoidable_cost_flags") or []),
        # gate_pass_rate is computed by the harness's evaluate_hard_gates;
        # surface 1.0 if all 6 passed, else the fractional pass count
        _gate_pass_rate_value(gates_passed),
        feature_correct,
        round(wallclock_s, 2),
        analyze.get("prompt_count") or len(analyze.get("prompts") or []),
        composite,
        "",  # composite_delta_pct — patched by compare.py
        gates_passed,
        "",  # decision — patched by compare.py
        f"sha={git_main_sha()} status={decision_status}",
    ]
    write_tsv_row(tsv_path, SESSION_HEADERS, row)


def _gate_pass_rate_value(gates_passed: str) -> float:
    """Parse '5/6' → 5/6. Returns 0.0 on malformed input."""
    try:
        num, denom = gates_passed.split("/", 1)
        denom_n = int(denom)
        return round(int(num) / denom_n, 4) if denom_n else 0.0
    except (ValueError, AttributeError):
        return 0.0


def append_prompt_rows(
    *, tsv_path: pathlib.Path, run_id: str, analyze: dict, breakdown: dict
) -> None:
    """Emit one TSV row per session-scoped agent (code-gen, scaffold, …).

    `analyze.prompts[]` is operator-chat-turn-scoped (one entry per
    `user_message` chat event) and never carries per-agent-run attribution.
    Per-agent telemetry lives in `analyze.runtime_aggregates.by_agent` which
    `_runtime_aggregates(session_id=...)` now scopes to this chat session via
    `tasks.chat_session_id`. That's the honest source for autoresearch's
    σ-floor + 2σ inputs.
    """
    aggs = analyze.get("runtime_aggregates") or {}
    by_agent = aggs.get("by_agent") or []
    by_runtime_idx = {
        str(r.get("runtime_sdk") or ""): r for r in (aggs.get("by_runtime") or [])
    }
    runtime_default = next(iter(by_runtime_idx)) if by_runtime_idx else ""
    rows: list[list] = []
    for i, agent in enumerate(by_agent):
        tokens_input = int(agent.get("input_tokens") or 0)
        tokens_cached = int(agent.get("cached_tokens") or 0)
        tokens_output = int(agent.get("output_tokens") or 0)
        noncached_plus_output = max(tokens_input - tokens_cached + tokens_output, 0)
        cache_ratio = (
            tokens_cached / max(noncached_plus_output, 1) if tokens_cached else 0.0
        )
        rows.append([
            run_id,
            i,
            "agent",
            agent.get("agent_name") or "",
            "",
            0,
            tokens_input,
            tokens_cached,
            0,
            tokens_output,
            noncached_plus_output,
            cache_ratio,
            0,
            "[]",
            "",
            int(agent.get("duration_ms") or 0),
            float(agent.get("cost_usd") or 0.0),
            runtime_default,
            "",
            "",
            json.dumps(breakdown.get(str(i)) or {}),
        ])
    for row in rows:
        write_tsv_row(tsv_path, PROMPT_HEADERS, row)


def write_tsv_row(tsv_path: pathlib.Path, header: list[str], row: list) -> None:
    exists = tsv_path.exists()
    with tsv_path.open("a", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        if not exists or tsv_path.stat().st_size == 0:
            w.writerow(header)
        w.writerow(row)


def git_main_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()[:12]
    except Exception:
        return ""


def compute_branch_diff_stats(branch: str) -> dict:
    """Run `git diff --shortstat main...<branch>` to get the edit size of an
    iteration. Used by compare.py's `simpler wins ties` rule and surfaced in
    the autoresearch-explainer.html iterations table. Returns zeros on any git failure."""
    base = "main"
    out = {"files_touched": 0, "lines_added": 0, "lines_deleted": 0}
    try:
        text = subprocess.check_output(
            ["git", "diff", "--shortstat", f"{base}...{branch}"],
            stderr=subprocess.DEVNULL, timeout=10,
        ).decode()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return out
    files = re.search(r"(\d+) files? changed", text)
    added = re.search(r"(\d+) insertions?", text)
    deleted = re.search(r"(\d+) deletions?", text)
    if files:
        out["files_touched"] = int(files.group(1))
    if added:
        out["lines_added"] = int(added.group(1))
    if deleted:
        out["lines_deleted"] = int(deleted.group(1))
    return out


def extract_context_breakdown(evidence_dir: pathlib.Path) -> dict:
    extractor = pathlib.Path(__file__).resolve().parent / "extract_context_breakdown.py"
    if not extractor.exists():
        return {}
    try:
        out = subprocess.check_output(
            [
                sys.executable, str(extractor),
                "--raw-bodies-dir", str(evidence_dir / "raw_bodies"),
                "--analyze-json", str(evidence_dir / "analyze.json"),
            ],
            timeout=60,
        )
        return json.loads(out.decode())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}


def main() -> int:
    args = parse_args()
    if args.fixture not in FIXTURES:
        print(f"Unknown fixture: {args.fixture}", file=sys.stderr)
        return 2

    run_id = str(uuid.uuid4())
    evidence_dir = pathlib.Path(args.evidence_dir or f"/tmp/autoresearch/{run_id}")
    workspace = pathlib.Path(f"/tmp/devpulse-{run_id}")
    seed = pathlib.Path(args.seed) if args.seed else DEFAULT_SEED
    tsv_root = pathlib.Path(args.tsv_root) if args.tsv_root else DEFAULT_TSV_ROOT

    if args.dry_run:
        print(json.dumps({
            "dry_run": True, "run_id": run_id, "fixture": args.fixture,
            "branch": args.branch, "port": args.port,
            "evidence_dir": str(evidence_dir), "workspace": str(workspace),
            "seed": str(seed), "would_run": "see HARNESS.md workflow",
        }, indent=2))
        return 0

    fixture = FIXTURES[args.fixture]
    restore_seed(seed, workspace)
    otel_env = build_otel_env(run_id, args.fixture, args.branch, evidence_dir)
    env = {**os.environ, **otel_env}

    # Critical: do NOT use subprocess.PIPE without a draining thread. Builder's
    # code-gen agents produce ~MB of stdout during long runs; once the 64KB
    # pipe buffer fills, builder's main asyncio thread blocks on the next
    # log write and the entire event loop freezes. Manifested 2026-05-23
    # cycle 4 as a true (dual-signal) hang after 153 API calls — `process_threads`
    # showed the main thread in `wchan=pipe_write` plus 6 CLOSE-WAIT sockets
    # with 216 bytes each stuck in Recv-Q because builder couldn't read them.
    # Redirect to a log file in the evidence dir so it doesn't block, but is
    # still inspectable post-mortem.
    builder_log_path = evidence_dir / "builder_stdout_stderr.log"
    builder_log_fh = builder_log_path.open("wb")
    builder_proc = subprocess.Popen(
        ["builder", "start", "--port", str(args.port), "--force"],
        cwd=str(workspace), env=env,
        stdout=builder_log_fh, stderr=subprocess.STDOUT,
    )

    decision_status = "incomplete"
    session_id: str | None = None
    t0 = time.time()
    # Cap how many questions we'll auto-answer before bailing — protects
    # against an unbounded intake loop if builder keeps surfacing prompts.
    max_questions = 25
    default_answer = fixture.get("default_answer", "recommended")
    try:
        wait_for_ready(f"http://127.0.0.1:{args.port}/api/dashboard/board", timeout_s=120)
        session_id = send_chat(args.port, fixture["prompt"])
        follow_ups = list(fixture.get("follow_ups") or [])
        follow_up_idx = 0
        questions_answered = 0

        # Drive the chat lifecycle: keep alternating wait → answer until the
        # board reaches shipped OR we hit the question cap OR fixture-specific
        # timeout. Each iteration of this loop is one operator response cycle.
        while questions_answered < max_questions:
            try:
                outcome = wait_for_question_or_ship(
                    args.port, session_id, timeout_s=fixture["timeout_s"]
                )
            except TimeoutError:
                break  # board still not shipped and no pending question
            if outcome == "shipped":
                break
            if outcome == "proceed_needed":
                # Chat completed but no structured question + no ship — model
                # asked free-text scoping questions in an assistant_message.
                # Push the conversation forward with a default "proceed"
                # message so the chat agent finalizes scope and creates a Task.
                # Bounded by max_questions to prevent infinite loops if the
                # model keeps asking. Pattern caught 2026-05-23 (fixture A:
                # multi-bullet markdown scoping question, no ask_user_question
                # event surfaced).
                send_chat(
                    args.port,
                    "Proceed with reasonable defaults for any clarifying "
                    "questions. Pick the first sensible option for each, "
                    "create the Task, and start building.",
                    session_id=session_id,
                )
                questions_answered += 1
                continue
            pending_item = get_pending_question(args.port, session_id)
            if pending_item is None:
                break  # neither shipped nor pending — escape hatch
            # Use the scripted follow-up if one exists for this question index;
            # otherwise default to the fixture's auto-answer (typically
            # "recommended"). This is the v1 intake-polling pattern — builder
            # often surfaces multiple intake/approval questions for a single
            # feature, and an empty follow_ups list shouldn't stall the run.
            if follow_up_idx < len(follow_ups):
                answer = follow_ups[follow_up_idx]
                follow_up_idx += 1
            else:
                answer = default_answer
            # P10 (2026-05-23, cycle 10): `/api/agent/chat/respond` 400 when
            # the harness builds a payload the server rejects (options empty,
            # wrong type contract). P11 (2026-05-23): the original P10 fallback
            # called send_chat(), which causes a 409 Conflict because the session
            # still has an active reserved run waiting for the respond. Correct
            # fix: handle all known interaction types inside send_chat_respond
            # so a 400 should not occur in practice; if an unknown type surfaces,
            # break out of the loop cleanly (incomplete, not crash) rather than
            # sending a new chat turn that will 409.
            try:
                send_chat_respond(args.port, session_id, pending_item, answer)
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else 0
                if status_code == 400:
                    # Unknown payload format — no pending question to respond to.
                    break
                elif status_code == 409:
                    # P14 (2026-05-23): 409 directly on respond means the pending
                    # item was already handled (auto-approved tool_approval, race
                    # condition). Re-enter the poll loop instead of crashing so
                    # wait_for_question_or_ship can reassess the session state.
                    continue
                else:
                    raise
            questions_answered += 1

        shipped = ship_or_timeout(args.port, fixture["timeout_s"])
        decision_status = "shipped" if shipped else "incomplete"
    except Exception as exc:
        decision_status = "crash"
        (evidence_dir / "crash.log").parent.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "crash.log").write_text(f"{type(exc).__name__}: {exc}\n")
        shipped = False
    finally:
        wallclock_s = time.time() - t0
        try:
            builder_proc.terminate()
            builder_proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            builder_proc.kill()
        try:
            builder_log_fh.close()
        except OSError:
            pass
        time.sleep(3)

    capture_evidence(workspace, session_id or "", evidence_dir)
    feature_correct = run_feature_check(workspace, evidence_dir)

    analyze = _read_json(evidence_dir / "analyze.json")
    metrics = _read_json(evidence_dir / "metrics.json")
    board = _read_json(evidence_dir / "board.json")
    breakdown = extract_context_breakdown(evidence_dir)

    # P16 (2026-05-23): composite := noncached_plus_output_tokens only.
    # Previous formula multiplied this by operator_turns × wallclock_seconds,
    # but those three dimensions are correlated (longer fixture runs produce
    # more of each), so the product compounded variance instead of averaging
    # it (N=3 fixture-A ships: CV=77.5%, 2σ-floor=-3.19e9 — gate useless).
    # turns + wallclock aren't billed; they measure "conversation length,"
    # not "agent efficiency." Fixture is held constant across runs, so the
    # right cost comparison is "tokens to complete this fixture" — exactly
    # noncached_plus_output_tokens. New fixture-A CV: 14.7% (gateable).
    # P15 (2026-05-23): key is `optimization_summary` not `optimization`
    # (mirrors evaluate_hard_gates P12 fix).
    opt = (metrics.get("optimization_summary") or metrics.get("optimization") or {}) if isinstance(metrics, dict) else {}
    composite = int(opt.get("noncached_plus_output_tokens") or 0)
    gates_str, _ = evaluate_hard_gates(analyze, metrics, board, feature_correct, decision_status == "shipped")

    tsv_path = tsv_root / ("baseline_runs.tsv" if args.baseline else "optimize_results.tsv")
    # Idea ref is parsed out of the branch name when this run is an iteration
    # under loop.py (e.g., autoresearch/iter-3-stable-prompt-header → "stable-prompt-header").
    # Otherwise empty (smoke tests, manual one-offs, baseline N=5 runs).
    idea_ref = ""
    m = re.match(r"^autoresearch/iter-\d+-(.+)$", args.branch or "")
    if m:
        idea_ref = m.group(1)
    diff_stats = compute_branch_diff_stats(args.branch) if args.branch else {}
    append_session_row(
        tsv_path=tsv_path, run_id=run_id, fixture_id=args.fixture, branch=args.branch,
        analyze=analyze, metrics=metrics, gates_passed=gates_str, composite=composite,
        wallclock_s=wallclock_s, feature_correct=feature_correct, decision_status=decision_status,
        idea_ref=idea_ref, diff_stats=diff_stats,
    )
    append_prompt_rows(
        tsv_path=tsv_root / "per_prompt_results.tsv",
        run_id=run_id, analyze=analyze, breakdown=breakdown,
    )

    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)

    print(json.dumps({
        "run_id": run_id,
        "evidence_dir": str(evidence_dir),
        "composite": composite,
        "gates_passed": gates_str,
        "feature_correct": feature_correct,
        "decision_status": decision_status,
        "wallclock_s": round(wallclock_s, 2),
        "session_id": session_id,
    }))
    return 0


def _read_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Autoresearch atomic fixture runner.")
    p.add_argument("--fixture", required=True, choices=list(FIXTURES))
    p.add_argument("--branch", required=True)
    p.add_argument("--port", type=int, default=9876)
    p.add_argument("--evidence-dir", default=None)
    p.add_argument("--seed", default=None)
    p.add_argument("--tsv-root", default=None)
    p.add_argument("--baseline", action="store_true", help="Write to baseline_runs.tsv instead of optimize_results.tsv")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())
