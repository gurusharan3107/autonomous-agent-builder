# Harness — Runner Contract

> **Read [README.md](README.md), [OPTIMIZE.md](OPTIMIZE.md), and [METRICS.md](METRICS.md) first.**

> **Note (2026-05-29 lean cut):** The OTEL/Jaeger raw-body capture + `extract_context_breakdown.py` context-attribution subsystem was removed — the composite metric is read directly from `builder analyze`. Steps below that mention OTEL / raw_bodies / context-ledger are historical and pending a deeper rewrite.

This file specifies the runnable harness that turns the [OPTIMIZE.md](OPTIMIZE.md) loop contract into executable Python. It is pseudo-code level — the implementation is itself a roadmap item ([docs/goal/ROADMAP.md § M3.5](../goal/ROADMAP.md#m35--optimization-loop-activation-autoresearch-track-b)) — but the contract here is precise: every input, every output, every command call, every TSV column.

The harness uses only:
- Existing Builder CLI commands (verified in `src/autonomous_agent_builder/cli/commands/`).
- Existing Builder HTTP endpoints (verified at `src/autonomous_agent_builder/embedded/server/routes/agent.py:1316-1632`).
- The Claude Agent SDK env-var surface (verified per SDK-OBSERVABILITY.md).

No new CLI commands or HTTP endpoints are required for v1. The harness is executable today against the existing source.

## Scripts overview

The harness lives at `scripts/autoresearch/` (created by the implementing PR). Four entry points:

| Script | Role | Inputs | Outputs |
| --- | --- | --- | --- |
| `run.py` | One fixture, one iteration. The atomic unit. | `--fixture A`, `--branch optim/idea-3`, `--port 9876`, `--evidence-dir /tmp/autoresearch/<run-id>` | One row in `optimize_results.tsv`, N rows in `per_prompt_results.tsv`, full evidence under `${evidence_dir}/` |
| `baseline.py` | N runs of each fixture on `main`. Establishes σ. | `--fixtures A,B,C,D,E`, `--n 5`, `--evidence-root /tmp/autoresearch/baseline` | Rows in `baseline_runs.tsv`; computed σ written to `baseline_variance.md` § Recorded baselines |
| `compare.py` | Diff two runs of the same fixture. Outputs `keep`/`discard`/`crash`. | `--baseline-run <run-id>`, `--candidate-run <run-id>` | Verdict JSON to stdout; updates `optimize_results.tsv` `decision` column for the candidate |
| `loop.py` | Karpathy-style continuous loop. Picks ideas, branches, runs, compares, advances or rewinds. | `--max-iterations 50`, `--cost-budget-usd 100` | TSV rows; commits on success; `git reset` on failure |

`extract_context_breakdown.py` is a helper invoked by `run.py` per turn — it parses raw API bodies into the `context_breakdown_json` column per CONTEXT-LEDGER.md Path A.

## `run.py` — the atomic iteration

```python
# scripts/autoresearch/run.py
"""
One fixture, one iteration. Captures all evidence required for the per-session and
per-prompt TSV rows. Designed to be called by baseline.py and loop.py, or directly
for manual experimentation.
"""

import argparse, json, os, shutil, subprocess, time, uuid, csv, pathlib, requests

FIXTURES = {  # mirrors docs/autoresearch/fixtures.md
    "A": {"prompt": "Add a button on the homepage that shows the current time when clicked.",
          "follow_ups": [], "expected_phase": "shipped", "timeout_s": 1500},
    "B": {"prompt": "I want to add a notes feature so I can write short text notes that persist between visits.",
          "follow_ups": ["recommended", "recommended", "recommended"], "expected_phase": "shipped", "timeout_s": 1500},
    "C": {"prompt": "Make the app better for power users.",
          "follow_ups": ["recommended", "recommended", "recommended", "recommended"], "expected_phase": "shipped", "timeout_s": 1500},
    "D": {"prompt": "Improve search.",
          "follow_ups": ["Notes by their text content."], "expected_phase": "shipped", "timeout_s": 1500},
    "E": {"prompt": "I want to track something on the dashboard.",
          "follow_ups": ["Time spent per task this week.", "Just a number is fine, no chart needed."], "expected_phase": "shipped", "timeout_s": 1500},
}

SEED = pathlib.Path("/home/gurusharangupta/.seed/devpulse")  # immutable starting state

def main():
    args = parse_args()
    run_id = str(uuid.uuid4())
    evidence_dir = pathlib.Path(args.evidence_dir or f"/tmp/autoresearch/{run_id}")
    workspace = pathlib.Path(f"/tmp/devpulse-{run_id}")
    port = args.port

    # 1. Fresh workspace from seed (.seed never mutated)
    shutil.copytree(SEED, workspace)

    # 2. Prepare OTEL env per SDK-OBSERVABILITY.md § Recommended loop setup
    otel_env = build_otel_env(run_id, args.fixture, args.branch, evidence_dir)
    env = {**os.environ, **otel_env}

    # 3. Start builder in the workspace on the given port
    builder = subprocess.Popen(
        ["builder", "start", "--port", str(port), "--force"],
        cwd=workspace, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    wait_for_ready(f"http://127.0.0.1:{port}/api/dashboard/board", timeout_s=60)

    t0 = time.time()
    try:
        # 4. Drive the fixture via the existing POST /api/agent/chat endpoint
        fixture = FIXTURES[args.fixture]
        session_id = send_chat(port, fixture["prompt"])
        # Wait for first question or ship
        wait_for_question_or_ship(port, session_id, timeout_s=600)
        # Answer follow-ups in order
        for answer in fixture["follow_ups"]:
            question_id = get_pending_question(port, session_id)
            if question_id is None:
                break  # no question expected; carry on
            send_chat_respond(port, session_id, question_id, answer)
            wait_for_question_or_ship(port, session_id, timeout_s=600)
        # Wait for the board to reach shipped or fixture timeout
        ship_or_timeout(port, fixture["timeout_s"])
        decision_status = "shipped" if board_active_phase(port) == "shipped" else "incomplete"
    except subprocess.CalledProcessError as e:
        decision_status = "crash"
    finally:
        wallclock_s = time.time() - t0
        # 5. Stop builder, allow OTEL flush
        subprocess.run(["builder", "server", "stop", "--port", str(port)])
        time.sleep(3)

    # 6. Capture Builder-side evidence
    capture_builder_evidence(session_id, port, evidence_dir, workspace)

    # 7. Run feature correctness check
    feature_correct = run_feature_check(workspace)

    # 8. Parse raw API bodies for context breakdown (CONTEXT-LEDGER.md Path A)
    breakdown_by_prompt = subprocess.check_output([
        "python3", "scripts/autoresearch/extract_context_breakdown.py",
        "--raw-bodies-dir", str(evidence_dir / "raw_bodies"),
        "--analyze-json", str(evidence_dir / "analyze.json"),
    ]).decode()
    breakdown_by_prompt = json.loads(breakdown_by_prompt)  # {prompt_index: <breakdown json>}

    # 9. Read Builder analyze, metrics, board JSON
    analyze = json.loads((evidence_dir / "analyze.json").read_text())
    metrics = json.loads((evidence_dir / "metrics.json").read_text())
    board = json.loads((evidence_dir / "board.json").read_text())

    # 10. Compute composite, evaluate hard gates
    # `prompt_count` = operator chat turns (one per user_message event). For
    # model-call count use `runtime_aggregates.totals.runs`. The composite
    # intentionally weights operator turns (Bar 1 UX cost), not model calls.
    # `analyze["cache_ratio"]` / `noncached_plus_output_tokens` are
    # session-scoped (post-2026-05-23) when
    # `runtime_aggregates.session_scoped is True` — the harness MUST assert
    # this flag is true before trusting σ-floor inputs.
    assert analyze.get("runtime_aggregates", {}).get("session_scoped") is True, (
        "analyze.runtime_aggregates.session_scoped is False — DB predates "
        "the `tasks.chat_session_id` migration (ROADMAP M2.3). Aggregates "
        "have fallen back to global scope and will poison σ-floor."
    )
    composite = (
        int(analyze.get("noncached_plus_output_tokens") or 0)
        * int(analyze.get("prompt_count") or 0)
        * int(wallclock_s)
    )
    gates_passed, gate_detail = evaluate_hard_gates(analyze, metrics, board, feature_correct, decision_status)

    # 11. Append per-session row
    append_session_row(
        run_id=run_id, args=args, analyze=analyze, metrics=metrics, board=board,
        composite=composite, wallclock_s=wallclock_s,
        feature_correct=feature_correct, gates_passed=gates_passed,
        decision_status=decision_status,
    )

    # 12. Append per-agent rows.
    # NB: post-2026-05-23, this emits one row per session-scoped agent
    # (`analyze.runtime_aggregates.by_agent[*]`), NOT one per chat prompt.
    # `analyze.prompts[]` is operator-chat-turn-scoped (length 1 for
    # autoresearch fixture-A intake) and never carries `agent_name`. Per-agent
    # attribution comes from `by_agent`, which is session-scoped via
    # `tasks.chat_session_id`. Headers in per_prompt_results.tsv are unchanged
    # but each row now represents one agent's aggregate, not one chat turn.
    append_prompt_rows(run_id, analyze, breakdown_by_prompt)

    # 13. Cleanup workspace (keep evidence_dir until comparison decides keep/discard)
    shutil.rmtree(workspace)

    print(json.dumps({
        "run_id": run_id, "evidence_dir": str(evidence_dir),
        "composite": composite, "gates_passed": gates_passed,
        "feature_correct": feature_correct, "decision_status": decision_status,
    }))


def build_otel_env(run_id, fixture_id, branch, evidence_dir):
    raw_bodies = pathlib.Path(evidence_dir) / "raw_bodies"
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
        "OTEL_RESOURCE_ATTRIBUTES":
            f"run.id={run_id},fixture.id={fixture_id},branch={branch},autoresearch.iteration=true",
        "OTEL_LOG_USER_PROMPTS": "1",
        "OTEL_LOG_TOOL_DETAILS": "1",
        "OTEL_LOG_TOOL_CONTENT": "1",
        "OTEL_LOG_RAW_API_BODIES": f"file:{raw_bodies}",
    }


def send_chat(port, prompt):
    """POST /api/agent/chat with the operator prompt; returns session_id."""
    r = requests.post(
        f"http://127.0.0.1:{port}/api/agent/chat",
        json={"message": prompt, "session_id": None},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["session_id"]


def send_chat_respond(port, session_id, request_id, answer):
    """POST /api/agent/chat/respond — answers a pending question or approval inline."""
    # The 'answer' is a label like 'recommended' (resolved to first option index) or free text.
    payload = {"session_id": session_id, "request_id": request_id}
    if answer == "recommended":
        payload["option_index"] = 0  # the first option is always the (Recommended) one in fixtures
    else:
        payload["text"] = answer
    r = requests.post(
        f"http://127.0.0.1:{port}/api/agent/chat/respond",
        json=payload, timeout=60,
    )
    r.raise_for_status()


def get_pending_question(port, session_id):
    """GET /api/agent/chat/history; find the most recent pending question request_id."""
    r = requests.get(
        f"http://127.0.0.1:{port}/api/agent/chat/history",
        params={"session_id": session_id}, timeout=30,
    )
    r.raise_for_status()
    for event in reversed(r.json()["events"]):
        if event["type"] in ("ask_user_question", "tool_approval_request") and event.get("state") == "pending":
            return event["id"]
    return None


def wait_for_question_or_ship(port, session_id, timeout_s):
    """Poll history until a pending question appears or the board reaches shipped."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if get_pending_question(port, session_id):
            return "question"
        if board_active_phase(port) == "shipped":
            return "shipped"
        time.sleep(2)
    raise TimeoutError(f"No question or ship within {timeout_s}s")


def ship_or_timeout(port, timeout_s):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if board_active_phase(port) == "shipped":
            return
        time.sleep(5)
    raise TimeoutError(f"Did not ship within {timeout_s}s")


def board_active_phase(port):
    r = requests.get(f"http://127.0.0.1:{port}/api/dashboard/board", timeout=10)
    r.raise_for_status()
    return (((r.json() or {}).get("current_sprint") or {}).get("active_phase")) or ""


def capture_builder_evidence(session_id, port, evidence_dir, workspace):
    evidence_dir = pathlib.Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    # All three CLI commands target the workspace cwd
    cmds = {
        "analyze.json": ["builder", "logs", "analyze", "--session", session_id, "--full", "--json"],
        "metrics.json": ["builder", "metrics", "show", "--json", "--full"],
        "board.json":   ["builder", "board", "show", "--json"],
        "errors.json":  ["builder", "logs", "--error", "--compact", "--json"],
    }
    for filename, cmd in cmds.items():
        with (evidence_dir / filename).open("wb") as out:
            subprocess.run(cmd, cwd=workspace, stdout=out, check=True)


def run_feature_check(workspace):
    """npm run build && npm run test in the workspace. Returns True on exit 0."""
    try:
        subprocess.run(["npm", "run", "build"], cwd=workspace, check=True)
        subprocess.run(["npm", "run", "test", "--", "--watch=false"], cwd=workspace, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def evaluate_hard_gates(analyze, metrics, board, feature_correct, decision_status):
    """Returns ('5/6', {gate_name: bool})."""
    prompts = analyze.get("prompts") or []
    gate_cache_ratio = all(
        float(p.get("cache_ratio") or 0) > 5.0
        for p in prompts[2:]   # skip first two turns per OPTIMIZE.md
    ) if len(prompts) > 2 else True
    optimization = metrics.get("optimization") or {}
    chunk_pressure = optimization.get("chunk_pressure") or {}
    gate_chunk = bool(chunk_pressure.get("risk") is False)
    gate_flags = (optimization.get("active_avoidable_cost_flags") or []) == []
    # Gate pass rate from board
    tasks = (((board or {}).get("current_sprint") or {}).get("tasks") or [])
    gate_pass_rate = (sum(1 for t in tasks if t.get("status") == "done") == len(tasks)) if tasks else False
    gates = {
        "cache_ratio_gt_5x_after_turn_2": gate_cache_ratio,
        "chunk_pressure_risk_false": gate_chunk,
        "avoidable_cost_flags_empty": gate_flags,
        "gate_pass_rate_full": gate_pass_rate,
        "feature_correct": feature_correct,
        "fully_shipped": decision_status == "shipped",
    }
    passed = sum(1 for v in gates.values() if v)
    return f"{passed}/{len(gates)}", gates


def append_session_row(**kw):
    """Append a row to docs/autoresearch/optimize_results.tsv per the METRICS.md schema."""
    tsv = pathlib.Path("docs/autoresearch/optimize_results.tsv")
    row = build_session_row(**kw)
    with tsv.open("a", newline="") as f:
        csv.writer(f, delimiter="\t").writerow(row)


def append_prompt_rows(run_id, analyze, breakdown_by_prompt):
    """Append N rows to docs/autoresearch/per_prompt_results.tsv, one per prompt."""
    tsv = pathlib.Path("docs/autoresearch/per_prompt_results.tsv")
    prompts = analyze.get("prompts") or []
    runs = {r["id"]: r for r in (analyze.get("agent_run_evidence") or [])}
    with tsv.open("a", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        for i, p in enumerate(prompts):
            w.writerow(build_prompt_row(run_id, i, p, runs, breakdown_by_prompt.get(str(i)) or {}))


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--fixture", required=True, choices=list(FIXTURES))
    p.add_argument("--branch", required=True)
    p.add_argument("--port", type=int, default=9876)
    p.add_argument("--evidence-dir", default=None)
    return p.parse_args()


if __name__ == "__main__":
    main()
```

> **Production hardening notes** (do not write into v1 — track as polish items):
> - Concurrency: parallel runs on the same machine need port allocation, OTEL endpoint per-run, and separate `${EVIDENCE_DIR}` roots. Start serial; parallelize later.
> - Resilience: `wait_for_*` should treat 5xx from the dashboard as transient and retry up to 3×.
> - Disk hygiene: rotate `raw_bodies/` to compressed tarballs older than 7 days.
> - Failure forensics: on `decision_status == "crash"`, capture `builder logs --error --json` and any Python traceback into `${EVIDENCE_DIR}/crash.log` so the loop has something to learn from.

## `baseline.py` — establish σ

```python
# scripts/autoresearch/baseline.py
"""
Run each fixture N times on main to establish the noise floor per baseline_variance.md.
"""

import argparse, statistics, pathlib, csv, subprocess, json

def main():
    args = parse_args()
    fixtures = args.fixtures.split(",")
    rows_by_fixture = {f: [] for f in fixtures}
    for fixture in fixtures:
        for i in range(args.n):
            run_id = subprocess.check_output([
                "python3", "scripts/autoresearch/run.py",
                "--fixture", fixture,
                "--branch", "main",
                "--port", str(9876 + i),
                "--evidence-dir", f"{args.evidence_root}/{fixture}/run-{i}",
            ]).decode()
            row = json.loads(run_id)
            rows_by_fixture[fixture].append(row)

    # Compute σ per metric per fixture
    summary = {}
    for fixture, runs in rows_by_fixture.items():
        composites = [r["composite"] for r in runs if r["gates_passed"].startswith("6/6")]
        if len(composites) < 3:
            summary[fixture] = {"status": "unstable", "stable_runs": len(composites)}
            continue
        summary[fixture] = {
            "mean": statistics.mean(composites),
            "stdev": statistics.stdev(composites),
            "min": min(composites),
            "max": max(composites),
            "noise_floor_2sigma": statistics.mean(composites) - 2 * statistics.stdev(composites),
            "stable_runs": len(composites),
        }

    # Append to baseline_runs.tsv (already done by run.py per row) and write summary
    out = pathlib.Path("docs/autoresearch/baseline_runs_summary.json")
    out.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    # Also append a human section to baseline_variance.md § Recorded baselines


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--fixtures", default="A,B,C,D,E")
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--evidence-root", default="/tmp/autoresearch/baseline")
    return p.parse_args()


if __name__ == "__main__":
    main()
```

## `compare.py` — keep / discard verdict

See [COMPARE.md](COMPARE.md) for the detailed protocol. The script wraps that protocol.

```python
# scripts/autoresearch/compare.py
"""
Compare a candidate run against the baseline-of-record for the same fixture.
Outputs: keep / discard / crash with reasoning.
"""

import argparse, json, pathlib, csv

def main():
    args = parse_args()
    baseline = load_baseline_for_fixture(args.fixture)  # from baseline_runs_summary.json
    candidate = load_row("docs/autoresearch/optimize_results.tsv", args.candidate_run)

    # Hard gates first
    if not candidate["all_gates_passed"]:
        return verdict("discard", reason="hard_gate_failed", detail=candidate["gates_detail"])

    # 2σ test on composite
    if candidate["composite"] >= baseline["mean"] - 2 * baseline["stdev"]:
        return verdict("discard", reason="composite_within_2sigma_of_baseline",
                       detail={"candidate": candidate["composite"], "noise_floor": baseline["noise_floor_2sigma"]})

    # Per-prompt analysis (see COMPARE.md § Per-prompt diff)
    diff = per_prompt_diff(args.baseline_run, args.candidate_run)
    return verdict("keep", reason="composite_below_2sigma_noise_floor", detail={"diff": diff})


def verdict(decision, reason, detail):
    print(json.dumps({"decision": decision, "reason": reason, "detail": detail}, indent=2))
    return decision

# ... helpers omitted for brevity; see COMPARE.md for the diff and verdict shape ...

if __name__ == "__main__":
    main()
```

## `loop.py` — Karpathy-style continuous loop

```python
# scripts/autoresearch/loop.py
"""
Continuous loop. Picks ideas from OPTIMIZE_IDEAS.md, branches, runs run.py, runs compare.py,
keeps or rewinds. Stops on iteration cap, cost budget, or operator interrupt.
"""

import subprocess, json, time, signal, sys

STOP = False
def stop_handler(*_): 
    global STOP; STOP = True
signal.signal(signal.SIGINT, stop_handler)

def main():
    args = parse_args()
    iteration, cumulative_cost = 0, 0.0
    while not STOP and iteration < args.max_iterations and cumulative_cost < args.cost_budget_usd:
        idea = pick_next_idea()  # parse OPTIMIZE_IDEAS.md for top unattempted
        if idea is None:
            print("No unattempted ideas left. Stopping."); break

        branch = f"optim/{idea['ref']}-{int(time.time())}"
        subprocess.run(["git", "checkout", "-b", branch, "main"], check=True)
        # The agent (this script's caller, typically a Claude/Codex session) edits files per idea['files'].
        # In autonomous mode, agent_edit() invokes the model with the idea + allowlist context.
        agent_edit(idea)
        if not has_diff():
            log(f"Idea {idea['ref']} produced no diff. Skipping."); subprocess.run(["git", "checkout", "main"]); continue
        subprocess.run(["git", "commit", "-am", f"autoresearch: {idea['description']}"], check=True)

        # Run candidate on Fixture A first (cheap proxy)
        candidate = subprocess.check_output([
            "python3", "scripts/autoresearch/run.py",
            "--fixture", "A", "--branch", branch,
        ])
        candidate = json.loads(candidate)
        cumulative_cost += candidate.get("cost_usd", 0)

        verdict = subprocess.check_output([
            "python3", "scripts/autoresearch/compare.py",
            "--fixture", "A", "--candidate-run", candidate["run_id"],
        ])
        verdict = json.loads(verdict)

        if verdict["decision"] != "keep":
            subprocess.run(["git", "checkout", "main"], check=True)
            subprocess.run(["git", "branch", "-D", branch], check=True)
            mark_idea_attempted(idea, "discard", verdict["reason"])
            iteration += 1
            continue

        # Promotion: run on all fixtures
        for fixture in ["B", "C", "D", "E"]:
            candidate = json.loads(subprocess.check_output([
                "python3", "scripts/autoresearch/run.py",
                "--fixture", fixture, "--branch", branch,
            ]))
            cumulative_cost += candidate.get("cost_usd", 0)
            verdict = json.loads(subprocess.check_output([
                "python3", "scripts/autoresearch/compare.py",
                "--fixture", fixture, "--candidate-run", candidate["run_id"],
            ]))
            if verdict["decision"] != "keep":
                subprocess.run(["git", "checkout", "main"], check=True)
                subprocess.run(["git", "branch", "-D", branch], check=True)
                mark_idea_attempted(idea, "discard", f"regressed_on_fixture_{fixture}")
                break
        else:
            # All fixtures passed
            mark_idea_attempted(idea, "keep", "all_fixtures_pass")
            # The branch is left for human review and merge to main
            print(f"WIN: branch {branch} passed all fixtures. Review and merge.")

        iteration += 1

    print(f"Loop finished. Iterations: {iteration}, cumulative cost: ${cumulative_cost:.2f}")

# ... helpers ...

if __name__ == "__main__":
    main()
```

> **`agent_edit(idea)`** is the model-driven step. In manual operation, the human edits the files for the idea between `git checkout -b` and `git commit`. In fully autonomous operation, this function invokes a Claude or Codex session with the idea's description and allowlist as the prompt; the model edits and the script proceeds. v1 of the loop is manual; v2 is autonomous.

## How the harness reads existing Builder surfaces

### Builder CLI commands used (no source changes)

| Command | Purpose | Output consumed |
| --- | --- | --- |
| `builder start --port <p> --force` | Start dashboard against the seeded workspace | spawned process |
| `builder server stop --port <p>` | Clean shutdown | exit status |
| `builder logs analyze --session <id> --full --json` | Session telemetry | analyze.json |
| `builder metrics show --json --full` | Aggregate metrics + cost flags | metrics.json |
| `builder board show --json` | Sprint state + tasks + lanes | board.json |
| `builder logs --error --compact --json` | Error timeline | errors.json |

### Builder HTTP endpoints used (no source changes)

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/agent/chat` | POST | Send a typed operator message; returns session_id |
| `/api/agent/chat/respond` | POST | Respond to pending question/approval inline |
| `/api/agent/chat/history` | GET | Read full event stream; find pending requests |
| `/api/dashboard/board` | GET | Lane counts and active_phase polling |
| `/api/dashboard/board/stream` | GET (SSE) | Optional live stream (harness uses polling for simplicity) |

### SDK env vars used

Per SDK-OBSERVABILITY.md § Recommended loop setup. Exported in the shell that runs `builder start`; inherited by the SDK child process.

## What this harness does NOT do today (gaps)

- **Does not handle the agent-edit step autonomously.** v1 is human-in-the-loop for the `agent_edit(idea)` step; v2 makes it autonomous. See GAPS.md G-7.
- **Does not collect MCP server status.** Polling `get_mcp_status()` requires either a direct Python SDK call (works today) or an MCP-status HTTP endpoint (doesn't exist). See GAPS.md G-1.
- **Does not collect per-model breakdown.** Requires either OTEL `claude_code.token.usage` metric parsing (works with collector) or surfacing `ResultMessage.model_usage` in Builder analyze (source change). See GAPS.md G-4.
- **Does not handle Codex lane's raw-body capture.** Codex app-server produces logs of its own; needs a Codex-specific extractor. See GAPS.md G-8.

These do not block v1 of the loop — they limit its diagnostic resolution. The loop can run, keep, discard, and learn without any of them.

## End-to-end smoke test (v1 validation)

Before declaring the harness usable, run this against `main` (no edits):

```bash
# 1. One-time: snapshot devpulse seed
cp -r /home/gurusharangupta/Builder-Workspace/devpulse /home/gurusharangupta/.seed/devpulse

# 2. One-time: start a local OTLP collector (Jaeger all-in-one)
docker run --rm -d -p 4318:4318 -p 16686:16686 jaegertracing/all-in-one

# 3. One run, Fixture A, main branch
python3 scripts/autoresearch/run.py --fixture A --branch main --port 9876

# 4. Verify the outputs
test -s docs/autoresearch/optimize_results.tsv && echo "session row written"
test -s docs/autoresearch/per_prompt_results.tsv && echo "prompt rows written"
test -d /tmp/autoresearch/*/raw_bodies && echo "raw bodies captured"
test -f /tmp/autoresearch/*/analyze.json && echo "analyze captured"
test -f /tmp/autoresearch/*/metrics.json && echo "metrics captured"

# 5. Verify context_breakdown_json has real data
python3 -c "
import csv, json
with open('docs/autoresearch/per_prompt_results.tsv') as f:
    rows = list(csv.DictReader(f, delimiter='\t'))
print('rows:', len(rows))
if rows:
    cb = json.loads(rows[0]['context_breakdown_json'])
    print('blocks captured for prompt 0:', [b['name'] for b in cb['blocks']])
    print('unattributed_tokens:', cb['unattributed_tokens'])
"
```

A successful smoke test means: all four "captured" lines print, the TSVs have at least one row each, and `unattributed_tokens` is below 5% of total context tokens. If any of those fails, GAPS.md is where the cause lives.

## Related

- [OPTIMIZE.md](OPTIMIZE.md) — the loop contract this harness implements
- [METRICS.md](METRICS.md) — TSV column definitions
- SDK-OBSERVABILITY.md — OTEL setup the harness exports
- CONTEXT-LEDGER.md — how `extract_context_breakdown.py` works
- [COMPARE.md](COMPARE.md) — comparison protocol `compare.py` implements
- GAPS.md — what source changes would simplify or improve the harness
