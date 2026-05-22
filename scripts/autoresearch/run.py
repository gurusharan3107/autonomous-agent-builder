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
import shutil
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


def send_chat(port: int, prompt: str) -> str:
    r = requests.post(
        f"http://127.0.0.1:{port}/api/agent/chat",
        json={"message": prompt, "session_id": None},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["session_id"]


def get_pending_question(port: int, session_id: str) -> str | None:
    r = requests.get(
        f"http://127.0.0.1:{port}/api/agent/chat/history",
        params={"session_id": session_id},
        timeout=30,
    )
    r.raise_for_status()
    events = r.json().get("events", [])
    for event in reversed(events):
        if event.get("type") in ("ask_user_question", "tool_approval_request") and event.get("state") == "pending":
            return event["id"]
    return None


def send_chat_respond(port: int, session_id: str, request_id: str, answer: str) -> None:
    payload: dict = {"session_id": session_id, "request_id": request_id}
    if answer == "recommended":
        payload["decision"] = "allow"
        payload["option_index"] = 0
    else:
        payload["text"] = answer
    r = requests.post(
        f"http://127.0.0.1:{port}/api/agent/chat/respond",
        json=payload,
        timeout=60,
    )
    r.raise_for_status()


def wait_for_question_or_ship(port: int, session_id: str, timeout_s: int) -> str:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if get_pending_question(port, session_id):
                return "question"
            if board_active_phase(port) == "shipped":
                return "shipped"
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
        "board.json": ["builder", "backlog", "task", "list", "--json"],
        "errors.json": ["builder", "logs", "--error", "--compact", "--json"],
    }
    for filename, cmd in cmds.items():
        with (evidence_dir / filename).open("wb") as out:
            subprocess.run(cmd, cwd=str(workspace), stdout=out, check=False)


def run_feature_check(workspace: pathlib.Path) -> bool:
    app = workspace / "app"
    if not app.exists():
        return False
    try:
        subprocess.run(["npm", "--prefix", str(app), "run", "build"], check=True, timeout=600)
        subprocess.run(
            ["npm", "--prefix", str(app), "run", "test", "--", "--watch=false"],
            check=True,
            timeout=600,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def evaluate_hard_gates(
    analyze: dict, metrics: dict, board: dict, feature_correct: bool, shipped: bool
) -> tuple[str, dict[str, bool]]:
    prompts = analyze.get("prompts") or []
    gate_cache = (
        all(float(p.get("cache_ratio") or 0) > 5.0 for p in prompts[2:])
        if len(prompts) > 2
        else True
    )
    optimization = (metrics.get("optimization") or {}) if isinstance(metrics, dict) else {}
    chunk_pressure = optimization.get("chunk_pressure") or {}
    gate_chunk = chunk_pressure.get("risk") is False or chunk_pressure.get("chunk_pressure_risk") is False
    gate_flags = (optimization.get("active_avoidable_cost_flags") or []) == []
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
    "run_id", "timestamp", "main_sha", "fixture_id",
    "noncached_plus_output_tokens", "cache_ratio", "chunk_pressure_risk",
    "avoidable_cost_flags", "gate_pass_rate", "feature_correct",
    "wallclock_s", "operator_turns", "composite", "gates_passed", "notes",
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
) -> None:
    opt = (metrics.get("optimization") or {}) if isinstance(metrics, dict) else {}
    chunk = opt.get("chunk_pressure") or {}
    sha = git_main_sha()
    row = [
        run_id,
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        sha,
        fixture_id,
        opt.get("noncached_plus_output_tokens") or 0,
        opt.get("cache_ratio") or 0,
        chunk.get("chunk_pressure_risk", chunk.get("risk")),
        json.dumps(opt.get("active_avoidable_cost_flags") or []),
        gates_passed,
        feature_correct,
        round(wallclock_s, 2),
        analyze.get("prompt_count") or len(analyze.get("prompts") or []),
        composite,
        gates_passed,
        f"branch={branch} status={decision_status}",
    ]
    write_tsv_row(tsv_path, SESSION_HEADERS, row)


def append_prompt_rows(
    *, tsv_path: pathlib.Path, run_id: str, analyze: dict, breakdown: dict
) -> None:
    prompts = analyze.get("prompts") or []
    runs_idx = {r.get("id"): r for r in (analyze.get("agent_run_evidence") or [])}
    rows: list[list] = []
    for i, p in enumerate(prompts):
        run_meta = runs_idx.get(p.get("agent_run_id"), {})
        tools = p.get("tool_calls") or []
        rows.append([
            run_id,
            i,
            p.get("role") or "user" if i == 0 else "assistant",
            p.get("agent_name") or run_meta.get("agent_name") or "",
            p.get("phase") or run_meta.get("phase") or "",
            p.get("context_budget_tokens") or 0,
            p.get("tokens_input") or 0,
            p.get("tokens_cached") or 0,
            p.get("cache_creation_tokens") or 0,
            p.get("tokens_output") or 0,
            (p.get("tokens_input") or 0) - (p.get("tokens_cached") or 0) + (p.get("tokens_output") or 0),
            p.get("cache_ratio") or 0,
            len(tools),
            json.dumps([t.get("name", "") for t in tools]),
            p.get("stop_reason") or "",
            p.get("duration_ms") or 0,
            p.get("cost_usd") or 0,
            run_meta.get("runtime_sdk") or "",
            p.get("model") or run_meta.get("model") or "",
            p.get("effort") or run_meta.get("effort") or "",
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

    builder_proc = subprocess.Popen(
        ["builder", "start", "--port", str(args.port), "--force"],
        cwd=str(workspace), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    decision_status = "incomplete"
    session_id: str | None = None
    t0 = time.time()
    try:
        wait_for_ready(f"http://127.0.0.1:{args.port}/api/dashboard/board", timeout_s=120)
        session_id = send_chat(args.port, fixture["prompt"])
        wait_for_question_or_ship(args.port, session_id, timeout_s=600)
        for answer in fixture["follow_ups"]:
            question_id = get_pending_question(args.port, session_id)
            if question_id is None:
                break
            send_chat_respond(args.port, session_id, question_id, answer)
            wait_for_question_or_ship(args.port, session_id, timeout_s=600)
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
        time.sleep(3)

    capture_evidence(workspace, session_id or "", evidence_dir)
    feature_correct = run_feature_check(workspace)

    analyze = _read_json(evidence_dir / "analyze.json")
    metrics = _read_json(evidence_dir / "metrics.json")
    board = _read_json(evidence_dir / "board.json")
    breakdown = extract_context_breakdown(evidence_dir)

    prompts = analyze.get("prompts") or []
    composite = int(
        ((metrics.get("optimization") or {}).get("noncached_plus_output_tokens") or 0)
        * max(len(prompts), 1)
        * max(int(wallclock_s), 1)
    )
    gates_str, _ = evaluate_hard_gates(analyze, metrics, board, feature_correct, decision_status == "shipped")

    tsv_path = tsv_root / ("baseline_runs.tsv" if args.baseline else "optimize_results.tsv")
    append_session_row(
        tsv_path=tsv_path, run_id=run_id, fixture_id=args.fixture, branch=args.branch,
        analyze=analyze, metrics=metrics, gates_passed=gates_str, composite=composite,
        wallclock_s=wallclock_s, feature_correct=feature_correct, decision_status=decision_status,
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
