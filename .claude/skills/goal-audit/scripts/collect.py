#!/usr/bin/env python3
"""
goal-audit data collector.

Gathers two independent data streams into one unified JSON blob:

  1. Claude Code session-report data (user intent signal). Source: the bundled
     analyze-sessions.mjs from the session-report skill in
     ~/.claude/plugins/cache/. Filtered to Builder-related projects only.

  2. Builder runtime signal (autoresearch focus signal). Sourced by running
     `builder agent sessions` and `builder logs analyze --session <id> --full
     --json` against each Builder-related workspace path.

Output: a single JSON object to stdout. The goal-audit skill then synthesizes
INSIGHTS.md and optionally reorders OPTIMIZE_IDEAS.md from this blob.

Usage:
  python3 collect.py --since 7d [--top-sessions 5] [--cwd <path>]
  python3 collect.py --since-run                   # window = since last INSIGHTS entry

Args:
  --since         Time window for session-report. 24h, 7d, 30d, all, or ISO.
                  Default: 7d.
  --since-run     Set --since automatically to the collected_at timestamp of the
                  last INSIGHTS.md entry. Mutually exclusive with --since.
                  Falls back to 7d if no prior entry is found.
  --top-sessions  Max Builder-runtime sessions to inspect per workspace.
                  Default: 5.
  --cwd           Project root for reading docs/goal/*. Default: $PWD.

Exit codes:
  0 = success (data on stdout)
  1 = session-report analyzer not found or failed (no usable data)
  2 = malformed analyzer output (parser bug or version skew)

Stderr is used for non-fatal warnings (workspaces that failed to query, etc).
The skill should read both stderr and exit code.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone


# Name patterns identifying Builder-related Claude Code project keys.
# A project key is the encoded path like `-home-gurusharangupta-Builder-Workspace-devpulse`.
BUILDER_PROJECT_PATTERNS = [
    "builder-workspace",
    "autonomous-agent-builder",
    "aab-workspaces",
    "devpulse",
    "todo-app",
]

# Candidate filesystem paths to attempt Builder CLI queries against.
# The script tries each; silent skip if not a directory or `builder` not initialized.
BUILDER_WORKSPACE_CANDIDATES = [
    "/home/gurusharangupta/Builder-Workspace/devpulse",
    "/home/gurusharangupta/Workspace/todo-app",
]


def bundled_analyzer_path():
    """Return the absolute path to the bundled analyzer next to this script.

    The analyzer is vendored from session-report so the skill is self-contained.
    See analyze-sessions.mjs header for source and tailoring notes.
    """
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "analyze-sessions.mjs")


def run_analyzer(since, filter_pattern):
    analyzer = bundled_analyzer_path()
    if not os.path.isfile(analyzer):
        return None, f"bundled analyze-sessions.mjs missing at {analyzer}"
    cmd = ["node", analyzer, "--json", "--since", since]
    if filter_pattern:
        cmd.extend(["--filter-pattern", filter_pattern])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return None, f"analyzer execution failed (is node installed?): {e}"
    if result.returncode != 0:
        return None, f"analyzer exit {result.returncode}: {result.stderr[:500]}"
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError as e:
        return None, f"analyzer stdout is not valid JSON: {e}"


def is_builder_related(project_key):
    lower = (project_key or "").lower()
    return any(p in lower for p in BUILDER_PROJECT_PATTERNS)


def decode_project_path(project_key):
    """Decode a Claude Code project key into a filesystem path candidate.

    The encoding is `/` -> `-`; this is ambiguous because real paths may contain
    `-`. Try common known prefixes; return the first that exists on disk.
    """
    if not project_key or not project_key.startswith("-"):
        return None
    # Try simple decode
    naive = "/" + project_key[1:].replace("-", "/")
    if os.path.isdir(naive):
        return naive
    # Try with hyphen restored in directory names
    parts = project_key[1:].split("-")
    # Known prefixes — try longest match first
    prefixes = [
        ("/home/gurusharangupta/code", ["home", "gurusharangupta", "code"]),
        ("/home/gurusharangupta/Builder-Workspace", ["home", "gurusharangupta", "Builder", "Workspace"]),
        ("/home/gurusharangupta/Workspace", ["home", "gurusharangupta", "Workspace"]),
        ("/home/gurusharangupta", ["home", "gurusharangupta"]),
        ("/tmp", ["tmp"]),
    ]
    for fs_prefix, key_parts in prefixes:
        if [p.lower() for p in parts[: len(key_parts)]] == [k.lower() for k in key_parts]:
            remaining = parts[len(key_parts):]
            # Try increasingly merged remainder (last N parts joined with -)
            for i in range(len(remaining), 0, -1):
                head = remaining[:-i] + ["-".join(remaining[-i:])]
                candidate = os.path.join(fs_prefix, *head)
                if os.path.isdir(candidate):
                    return candidate
            # Fall back to all parts as separate dirs
            candidate = os.path.join(fs_prefix, *remaining)
            if os.path.isdir(candidate):
                return candidate
    return None


def try_builder_signals(workspace_path, top_n=5, warnings=None):
    """Query Builder CLI inside the given workspace. Returns None if not usable."""
    if not os.path.isdir(workspace_path):
        return None
    # Check if builder is initialized (look for .agent-builder or similar markers)
    # Be tolerant: just try the CLI; if it returns degraded/empty, fall back to None.
    try:
        sessions = subprocess.run(
            ["builder", "agent", "sessions", "--limit", str(top_n * 4), "--json"],
            cwd=workspace_path, capture_output=True, text=True, timeout=20,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        if warnings is not None:
            warnings.append(f"{workspace_path}: builder agent sessions failed ({e})")
        return None
    if sessions.returncode != 0:
        if warnings is not None:
            warnings.append(f"{workspace_path}: builder agent sessions exit {sessions.returncode}")
        return None
    try:
        sessions_data = json.loads(sessions.stdout)
    except json.JSONDecodeError as e:
        if warnings is not None:
            warnings.append(f"{workspace_path}: sessions stdout not JSON ({e})")
        return None

    results = sessions_data.get("results") or []
    if not results:
        return {"sessions": [], "analyze": [], "degraded": sessions_data.get("degraded", False)}

    out = {
        "sessions": results[:top_n],
        "analyze": [],
        "degraded": sessions_data.get("degraded", False),
    }

    for sess in results[:top_n]:
        sid = sess.get("id") or sess.get("session_id")
        if not sid:
            continue
        try:
            r = subprocess.run(
                ["builder", "logs", "analyze", "--session", sid, "--full", "--json"],
                cwd=workspace_path, capture_output=True, text=True, timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            if warnings is not None:
                warnings.append(f"{workspace_path}/{sid}: analyze failed ({e})")
            continue
        if r.returncode != 0:
            continue
        try:
            a = json.loads(r.stdout)
        except json.JSONDecodeError:
            continue
        # Extract only what the skill needs (keep blob small)
        out["analyze"].append({
            "session_id": sid,
            "started_at": sess.get("created_at") or sess.get("started_at"),
            "runtime_sdk": a.get("agent_run_evidence", {}).get("runtime_sdk"),
            "model": a.get("agent_run_evidence", {}).get("model"),
            "prompt_count": a.get("prompt_count"),
            "raw_token_total": a.get("raw_token_total"),
            "cached_tokens": a.get("cached_tokens"),
            "noncached_plus_output_tokens": a.get("noncached_plus_output_tokens"),
            "cache_ratio": a.get("cache_ratio"),
            "phase_ceremony_tokens": a.get("phase_ceremony_tokens"),
            "avoidable_token_estimate": a.get("avoidable_token_estimate"),
            "top_cost_drivers": a.get("top_cost_drivers", []),
            "recommended_next_change": a.get("recommended_next_change"),
            "optimization_decision": a.get("optimization_decision"),
            "deterministic_recommendations": a.get("deterministic_recommendations", []),
            "context_budget": a.get("context_budget"),
        })
    return out


def read_goal_snapshot(cwd):
    """Read docs/goal/* and docs/autoresearch/OPTIMIZE_IDEAS.md if present."""
    snap = {}
    goal_dir = os.path.join(cwd, "docs", "goal")
    if os.path.isdir(goal_dir):
        for name in ("STATUS.md", "ROADMAP.md", "NORTH-STAR.md", "INSIGHTS.md"):
            p = os.path.join(goal_dir, name)
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        snap[name] = f.read()
                except OSError:
                    pass
    optim = os.path.join(cwd, "docs", "autoresearch", "OPTIMIZE_IDEAS.md")
    if os.path.isfile(optim):
        try:
            with open(optim, encoding="utf-8") as f:
                snap["OPTIMIZE_IDEAS.md"] = f.read()
        except OSError:
            pass
    return snap


def _record(counter, key, workspace_key, sid):
    rec = counter.setdefault(key, {"sessions": 0, "workspaces": set(), "examples": []})
    rec["sessions"] += 1
    rec["workspaces"].add(workspace_key)
    if len(rec["examples"]) < 3:
        rec["examples"].append(sid)


def _drivers_jsonable(d):
    for v in d.values():
        v["workspaces"] = sorted(v["workspaces"])
    return d


def aggregate_drivers(builder_signals):
    """Across all builder_signals.*.analyze[], count each signal's recurrence.

    Real builder output shape (verified against `builder logs analyze --full --json`):

      analyze entry = {
        "recommended_next_change": "maintain_current_flow" | "truncate_tool_output..." | ...,
        "optimization_decision": {
          "avoidable_cost_flags": ["large_command_output", "repeated_retrieval", ...],
          ...
        },
        "top_cost_drivers": [
          {"agent_name": "code-gen", "runs": 3, "raw_tokens": ..., "avoidable_token_estimate": 0},
          ...
        ],
        ...
      }

    Three independent signal streams aggregate here, each keyed by driver-like string:

      1. recommended_next_change          — single string per session
      2. avoidable_cost_flags             — flag strings inside optimization_decision
      3. agent_name_with_avoidable_tokens — agent_name from top_cost_drivers entries
                                            where avoidable_token_estimate > 0
                                            (entries with 0 avoidable are healthy attribution,
                                             not optimization candidates)

    For backward compatibility the result also supports string-driver entries
    (in case future Builder versions return ["large_command_output", ...] form).
    """
    rec_counts = {}                # recommended_next_change str -> int
    flag_counts = {}               # avoidable_cost_flag str -> {sessions, workspaces, examples}
    agent_counts = {}              # agent_name (only when avoidable>0) -> {...}
    string_driver_counts = {}      # fallback for unknown-shape string drivers

    for workspace_key, sigs in (builder_signals or {}).items():
        if not sigs:
            continue
        for entry in sigs.get("analyze", []) or []:
            sid = entry.get("session_id") or "?"

            # Stream 1: recommended_next_change
            rec_next = entry.get("recommended_next_change")
            if rec_next:
                rec_counts[rec_next] = rec_counts.get(rec_next, 0) + 1

            # Stream 2: avoidable_cost_flags inside optimization_decision
            opt = entry.get("optimization_decision") or {}
            flags = opt.get("avoidable_cost_flags") or opt.get("active_avoidable_cost_flags") or []
            for f in flags:
                if isinstance(f, dict):
                    f = f.get("name") or f.get("flag") or f.get("kind")
                if isinstance(f, str) and f:
                    _record(flag_counts, f, workspace_key, sid)

            # Stream 3: top_cost_drivers — agent_name attribution (only when avoidable > 0)
            #            AND fallback for legacy string-driver shape
            for d in entry.get("top_cost_drivers") or []:
                if isinstance(d, dict):
                    if (d.get("avoidable_token_estimate") or 0) > 0:
                        an = d.get("agent_name") or d.get("name")
                        if an:
                            _record(agent_counts, an, workspace_key, sid)
                    # Also handle the upstream string-name shape if some version returns it
                    legacy_name = d.get("name") or d.get("driver") or d.get("kind")
                    if legacy_name and not d.get("agent_name"):
                        _record(string_driver_counts, str(legacy_name), workspace_key, sid)
                elif isinstance(d, str) and d:
                    _record(string_driver_counts, d, workspace_key, sid)

    return {
        "recommended_next_change": rec_counts,
        "avoidable_cost_flags": _drivers_jsonable(flag_counts),
        "agent_names_with_avoidable_tokens": _drivers_jsonable(agent_counts),
        "top_cost_drivers": _drivers_jsonable(string_driver_counts),
    }


def read_last_insights_timestamp(cwd):
    """Return the collected_at ISO timestamp from the last INSIGHTS.md entry.

    Each entry written by the skill embeds a HTML comment immediately after the
    ## header line:
        <!-- collected_at: 2026-05-21T16:27:09.123456+00:00 -->

    Falls back to parsing the YYYY-MM-DD date from the last ## header if the
    comment is absent (handles entries written before this feature landed).
    Returns None if INSIGHTS.md does not exist or has no entries.
    """
    insights_path = os.path.join(cwd, "docs", "goal", "INSIGHTS.md")
    if not os.path.isfile(insights_path):
        return None
    try:
        with open(insights_path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None

    # Prefer the embedded comment (most precise)
    comment_matches = list(re.finditer(r"<!-- collected_at: ([\d\-T:Z+.]+) -->", content))
    if comment_matches:
        return comment_matches[-1].group(1)

    # Fallback: date from last ## 20xx-MM-DD header → midnight UTC of that day
    date_matches = list(re.finditer(r"^## (20\d\d-\d\d-\d\d)", content, re.MULTILINE))
    if date_matches:
        return date_matches[-1].group(1) + "T00:00:00Z"

    return None


def main():
    ap = argparse.ArgumentParser(
        description=(
            "goal-audit data collector. Joins Claude Code session-report data "
            "(user intent signal) with builder CLI signals (autoresearch focus signal) "
            "into one JSON blob on stdout. Designed for non-interactive agent use."
        ),
        epilog=(
            "Examples:\n"
            "  scripts/collect.py --since 7d                    # default window\n"
            "  scripts/collect.py --since 24h                   # recent activity only\n"
            "  scripts/collect.py --since 30d --top-sessions 10 # wider window, more sessions per workspace\n"
            "  scripts/collect.py --since all --cwd /repo       # everything, override project root\n\n"
            "Exit codes:\n"
            "  0  success; JSON written to stdout, warnings to stderr\n"
            "  1  bundled analyzer missing or fatal error\n"
            "  2  analyzer output is not valid JSON\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--since", default="7d",
        help="Time window for session-report. Accepts 24h, 7d, 30d, all, or an ISO timestamp. Default: 7d.",
    )
    ap.add_argument(
        "--since-run", action="store_true",
        help=(
            "Derive --since from the collected_at timestamp of the last INSIGHTS.md entry. "
            "Produces a 'deltas since last run' view instead of a full re-analysis. "
            "Mutually exclusive with --since; --since-run takes precedence when both given."
        ),
    )
    ap.add_argument(
        "--top-sessions", type=int, default=5,
        help="Max Builder-runtime sessions to inspect per workspace via 'builder logs analyze'. Default: 5.",
    )
    ap.add_argument(
        "--cwd", default=os.getcwd(),
        help="Project root for reading docs/goal/* and docs/autoresearch/OPTIMIZE_IDEAS.md. Default: current working directory.",
    )
    args = ap.parse_args()

    # Resolve --since-run before anything else so downstream code always sees args.since
    since_run_mode = False
    if args.since_run:
        ts = read_last_insights_timestamp(args.cwd)
        if ts:
            args.since = ts
            since_run_mode = True
        else:
            print(
                "WARNING: --since-run specified but no prior INSIGHTS entry found; falling back to --since 7d",
                file=sys.stderr,
            )

    warnings = []
    out = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "since": args.since,
        "since_run_mode": since_run_mode,
        "cwd": args.cwd,
        "warnings": warnings,
    }

    # 1. session-report data (analyzer applies the Builder-project filter inline)
    filter_pattern = ",".join(BUILDER_PROJECT_PATTERNS)
    sr, err = run_analyzer(args.since, filter_pattern)
    if err:
        print(f"FATAL: {err}", file=sys.stderr)
        sys.exit(1)
    out["session_report"] = sr

    # 2. Builder CLI signals per workspace
    out["builder_signals"] = {}

    # Candidates: known fixed paths + decoded project paths from session-report
    candidates = set(BUILDER_WORKSPACE_CANDIDATES)
    candidates.add(args.cwd)
    sr_blob = out.get("session_report") or {}
    for project_key in (sr_blob.get("by_project") or {}):
        decoded = decode_project_path(project_key)
        if decoded:
            candidates.add(decoded)

    for path in sorted(candidates):
        sigs = try_builder_signals(path, args.top_sessions, warnings)
        if sigs and (sigs.get("sessions") or sigs.get("analyze")):
            out["builder_signals"][path] = sigs

    # 3. Aggregate drivers across all signals
    out["aggregated_drivers"] = aggregate_drivers(out["builder_signals"])

    # 4. docs/goal/ snapshot from cwd
    out["goal_snapshot"] = read_goal_snapshot(args.cwd)

    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
