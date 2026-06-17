#!/usr/bin/env python3
"""
mine_sessions.py — deterministic, structural content-miner for session transcripts.

The COMPLEMENT to cluster.py. cluster.py mines `recent_prompts` (the OPERATOR's
words) for recurring corrections. This script mines AGENT-SIDE evidence —
assistant prose + tool_result text (incl. is_error) — to answer
"where did the agent hit <failure pattern X>?" content-targeted questions.

Why a dedicated tool (lessons paid for, 2026-05-28):
  1. Never load analyze-sessions.mjs's ~900KB aggregate to do content mining —
     that blob is token/cache metrics, ~236K tokens raw. Read transcripts directly.
  2. Parse by MESSAGE STRUCTURE, not raw lines. Raw-line greps match tool-call
     PARAMETERS (e.g. "timeout":30000) and harness strings ("Shell cwd was
     reset"), producing huge noisy dumps. We extract only assistant text +
     tool_result text and skip tool_use input blocks by construction.
  3. Dedup + cap output (top-N). Never emit an unbounded per-project Counter.

Output: compact JSON — {window, scanned_files, sidechain_files, scanned_projects,
lane_coverage (entrypoint→count, the COVERAGE signal — a lane absent here was NOT
scanned), total_hits, unique, truncated, project_counts (top 10),
findings[{project, session, role, sidechain, branch, agent, is_error, snippet}]}.

Usage:
  # Preset (recommended) — curated context+failure regexes, noise pre-filtered:
  python3 mine_sessions.py --preset browser_testing --since 30d

  # Arbitrary pattern (matched against extracted PROSE only):
  python3 mine_sessions.py --pattern "rollback|session is closed" --since 14d

  # Narrow to projects whose dir name contains a substring, cap findings:
  python3 mine_sessions.py --preset browser_testing --project-filter code-autonomous --limit 20

Flags:
  --preset NAME        one of: browser_testing  (see PRESETS below)
  --pattern REGEX      failure regex (case-insensitive); combined with preset if both given
  --context-pattern RE require this regex ALSO match the prose (defaults to preset's, else any)
  --since 30d          time window by transcript mtime (default 30d)
  --project-filter S   only scan projects whose dir name contains S
  --errors-only        only count blocks carrying tool_result is_error=true
  --limit N            max unique findings to emit (default 25)
  --context N          chars of context around the match in each snippet (default 90)
  --projects-root P    default ~/.claude/projects

CAUTION on --pattern: precise phrases ("timed out after", "could not click")
beat bare keywords ("reset", "timeout") — bare keywords over-match harness noise
and tool params. Presets already encode precise regexes.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import time

# Curated presets: (context_regex, failure_regex). Both must match the extracted
# prose for a hit. Regexes are deliberately precise to exclude param/harness noise.
PRESETS: dict[str, dict[str, str]] = {
    "browser_testing": {
        "context": (
            r"(playwright|chrome-?devtools|chrome-?cli|hermes-?chrome|cursor-agent|cdp|"
            r"page\.(click|goto|fill|screenshot)|navigate_page|take_screenshot|new_page|"
            r"webwright|click_selector|click_text|findPointByText)"
        ),
        "failure": (
            r"(timed out after|timeout exceeded|exceeded .*? ?ms|could not (click|find|locate|resolve)|"
            r"element (is )?not (found|visible|clickable)|no such element|clicked (the )?(wrong|hidden|nothing)|"
            r"pointer (events )?intercept|occluded|stale element|frame .*?detach|connection refused|"
            r"ECONNREFUSED|target (page|closed)|websocket .*?(closed|err)|net::ERR|"
            r"cursor (didn'?t|did not|not) (move|show|appear|render)|landed on (nothing|the wrong)|"
            r"screenshot (failed|timed out)|bridge (not available|unreachable|dead)|ready:\s*false|socket error)"
        ),
    },
}

# Harness/noise strings that are genuine tool_result text but never a real finding.
NOISE = (
    "Shell cwd was reset",
    "<system-reminder>",
)

# Builder orchestrated-agent role names. Used for best-effort per-finding role
# attribution: claude-lane builder sessions all share the Claude Code preset
# system prompt ("You are a helpful AI assistant for the project rooted at ..."),
# so the role is NOT in the prompt — it only surfaces as these tokens in task
# content / tool calls. Detection is approximate; isSidechain + gitBranch are the
# reliable structural signals.
BUILDER_AGENTS = (
    "repo-researcher", "browser-verifier", "build-verifier", "security-reviewer",
    "pr-reviewer", "pr-creator", "documentation-agent", "code-gen",
    "gate-remediator", "repo-scout", "session-maintainer", "test-sync-verifier",
    "implementer", "planner",
)
_AGENT_RE = re.compile("|".join(re.escape(a) for a in BUILDER_AGENTS), re.I)
# Explicit lane phrase in an error message ("Denied `Bash` in the chat lane") is a
# stronger, exact attribution than session-wide token frequency.
_LANE_RE = re.compile(r"in the (\w+) lane\b", re.I)


def _project_of(root: str, f: str) -> str:
    """Project dir = the first path component under root, regardless of depth.
    Correct for both depth-1 sessions (proj/sess.jsonl) and subagent transcripts
    (proj/sess/subagents/agent.jsonl) — os.path.dirname would mislabel the latter."""
    rel = os.path.relpath(f, root)
    return rel.split(os.sep)[0]


def extract_prose(content) -> tuple[str, bool]:
    """Return (prose, is_error). Prose = assistant text + tool_result text ONLY.
    tool_use input blocks (which carry params like timeout=30000) are skipped."""
    if isinstance(content, str):
        return content, False
    if not isinstance(content, list):
        return "", False
    parts: list[str] = []
    is_error = False
    for b in content:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "text":
            parts.append(b.get("text", ""))
        elif t == "tool_result":
            if b.get("is_error"):
                is_error = True
            c = b.get("content")
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, list):
                for x in c:
                    if isinstance(x, dict) and x.get("type") == "text":
                        parts.append(x.get("text", ""))
        # tool_use / thinking / image: intentionally skipped (param/internal noise)
    return "\n".join(parts), is_error


def mine(args) -> dict:
    root = os.path.expanduser(args.projects_root)
    cutoff = time.time() - _days(args.since) * 86400

    fail_parts = [p for p in (PRESETS.get(args.preset, {}).get("failure"), args.pattern) if p]
    if not fail_parts:
        raise SystemExit("error: supply --preset and/or --pattern")
    fail_re = re.compile("|".join(f"(?:{p})" for p in fail_parts), re.I)
    ctx_src = args.context_pattern or PRESETS.get(args.preset, {}).get("context")
    ctx_re = re.compile(ctx_src, re.I) if ctx_src else None

    # Sweep BOTH top-level sessions (orchestrator + each per-agent SDK session,
    # which the builder writes as separate depth-1 transcripts) AND nested Task
    # subagent transcripts under <session>/subagents/. The old glob (*/*.jsonl)
    # silently missed every subagents/ file, hiding in-subagent blockers.
    candidates = set(
        glob.glob(os.path.join(root, "*", "*.jsonl"))
        + glob.glob(os.path.join(root, "*", "**", "subagents", "*.jsonl"), recursive=True)
    )
    files = [
        f for f in candidates
        if os.path.getmtime(f) >= cutoff
        and (not args.project_filter or args.project_filter in _project_of(root, f))
    ]

    findings: list[dict] = []
    proj_counts: dict[str, int] = {}
    entrypoint_counts: dict[str, int] = {}
    sidechain_files = 0
    total = 0
    for f in files:
        proj = _project_of(root, f)
        sess = os.path.basename(f)[:8]
        file_sidechain = f"{os.sep}subagents{os.sep}" in f
        if file_sidechain:
            sidechain_files += 1
        file_agent_counts: dict[str, int] = {}
        file_findings: list[dict] = []
        file_entrypoint = ""
        try:
            with open(f, errors="ignore") as fh:
                for line in fh:
                    if "{" not in line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if not file_entrypoint:
                        file_entrypoint = obj.get("entrypoint") or ""
                    msg = obj.get("message") or {}
                    prose, is_err = extract_prose(msg.get("content"))
                    if not prose or any(n in prose for n in NOISE):
                        continue
                    # Tally agent-name tokens across the whole file for a per-session
                    # role guess (claude-lane builder sessions share a generic preset
                    # prompt, so role only surfaces as these tokens in task/tool text).
                    for a in _AGENT_RE.findall(prose):
                        a = a.lower()
                        file_agent_counts[a] = file_agent_counts.get(a, 0) + 1
                    if args.errors_only and not is_err:
                        continue
                    if ctx_re and not ctx_re.search(prose):
                        continue
                    m = fail_re.search(prose)
                    if not m:
                        continue
                    s = max(0, m.start() - args.context)
                    e = min(len(prose), m.end() + args.context)
                    snip = re.sub(r"\s+", " ", prose[s:e]).strip()
                    msg_agents = sorted({a.lower() for a in _AGENT_RE.findall(prose)})
                    file_findings.append({
                        "project": proj, "session": sess,
                        "role": msg.get("role") or obj.get("type", ""),
                        "sidechain": bool(obj.get("isSidechain", file_sidechain)),
                        "branch": obj.get("gitBranch") or "",
                        "_msg_agents": msg_agents,
                        "is_error": is_err, "snippet": snip,
                    })
        except Exception:
            continue
        # Coverage signal: which runtime lane wrote this transcript. The miner only
        # sees ~/.claude/projects JSONL (claude entrypoints, e.g. sdk-py / cli); a
        # codex_sdk build writes nowhere here, so a lane absent from this map is a
        # COVERAGE GAP, not proof of "no blockers". The agent must cross-check this
        # against `builder agent sessions` before reporting any all-clear.
        entrypoint_counts[file_entrypoint or "?"] = entrypoint_counts.get(file_entrypoint or "?", 0) + 1
        # Dominant agent for this session = most-frequent token. Single clean role
        # for per-agent / subagent sessions; for orchestrator sessions this is only
        # the top mention, so it is emitted as an approximate guess (trailing "?").
        file_agent = (
            max(file_agent_counts.items(), key=lambda kv: kv[1])[0]
            if file_agent_counts else ""
        )
        for fp in file_findings:
            msg_agents = fp.pop("_msg_agents")
            # Attribution priority: explicit lane phrase in the error > agent token in
            # the error message > session-frequency guess (marked approximate).
            lane = _LANE_RE.search(fp["snippet"])
            if lane:
                fp["agent"] = f"{lane.group(1).lower()}-lane"
            elif msg_agents:
                fp["agent"] = ",".join(msg_agents)
            elif file_agent:
                fp["agent"] = f"{file_agent}?"
            else:
                fp["agent"] = ""
            total += 1
            proj_counts[proj] = proj_counts.get(proj, 0) + 1
            findings.append(fp)

    # dedup by snippet prefix, cap to --limit
    seen: set[str] = set()
    uniq: list[dict] = []
    for fp in findings:
        key = fp["snippet"][:120]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(fp)
    truncated = len(uniq) > args.limit
    top_projects = sorted(proj_counts.items(), key=lambda kv: -kv[1])[:10]

    return {
        "window": args.since,
        "preset": args.preset,
        "pattern": args.pattern,
        "scanned_files": len(files),
        "sidechain_files": sidechain_files,
        "scanned_projects": len(proj_counts) or len({_project_of(root, f) for f in files}),
        "lane_coverage": dict(sorted(entrypoint_counts.items(), key=lambda kv: -kv[1])),
        "total_hits": total,
        "unique": len(uniq),
        "truncated": truncated,
        "project_counts_top10": [{"project": p, "hits": c} for p, c in top_projects],
        "findings": uniq[: args.limit],
    }


def _days(s: str) -> int:
    try:
        return int(s.rstrip("d")) if s.endswith("d") else int(s)
    except Exception:
        return 30


def main() -> None:
    ap = argparse.ArgumentParser(description="Structural content-miner for session transcripts.")
    ap.add_argument("--preset", choices=sorted(PRESETS))
    ap.add_argument("--pattern")
    ap.add_argument("--context-pattern", dest="context_pattern")
    ap.add_argument("--since", default="30d")
    ap.add_argument("--project-filter", dest="project_filter")
    ap.add_argument("--errors-only", action="store_true")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--context", type=int, default=90)
    ap.add_argument("--projects-root", default="~/.claude/projects")
    args = ap.parse_args()
    print(json.dumps(mine(args), indent=2))


if __name__ == "__main__":
    main()
