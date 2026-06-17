"""Regression tests for the session miner's transcript coverage + role attribution.

Locks two fixes (2026-06-17): the old glob `root/*/*.jsonl` silently missed every
`<session>/subagents/*.jsonl` transcript (540 files on disk, 0 scanned), and it
mislabelled a subagent's project as "subagents". These tests fail on the old code.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".claude/skills/self-optimize/scripts/mine_sessions.py"
)


def _load_miner():
    spec = importlib.util.spec_from_file_location("mine_sessions", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _err_record(text: str, *, branch: str, sidechain: bool, entrypoint: str = "sdk-py") -> str:
    return json.dumps({
        "type": "user",
        "gitBranch": branch,
        "isSidechain": sidechain,
        "entrypoint": entrypoint,
        "message": {
            "role": "user",
            "content": [{
                "type": "tool_result",
                "is_error": True,
                "content": [{"type": "text", "text": text}],
            }],
        },
    })


def _args(root: Path, **over) -> SimpleNamespace:
    base = dict(
        preset=None, pattern="permission|denied|failed", context_pattern=None,
        since="30d", project_filter=None, errors_only=True, limit=25,
        context=90, projects_root=str(root),
    )
    base.update(over)
    return SimpleNamespace(**base)


def _write(root: Path, rel: str, lines: list[str]) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines))


def test_subagent_transcripts_are_scanned(tmp_path):
    """A blocker living only in <session>/subagents/agent-*.jsonl must be found."""
    miner = _load_miner()
    proj = "-tmp-devpulse-abc"
    # depth-1 top-level session (always scanned, even by the old glob)
    _write(tmp_path, f"{proj}/sess1.jsonl",
           [_err_record("code-gen task: permission denied on Write", branch="sprint/x", sidechain=False)])
    # nested subagent transcript (MISSED by the old glob)
    _write(tmp_path, f"{proj}/sess1/subagents/agent-deadbeef.jsonl",
           [_err_record("build-verifier failed: ModuleNotFound", branch="sprint/x", sidechain=True)])

    res = miner.mine(_args(tmp_path))

    assert res["sidechain_files"] == 1, "subagent transcript was not scanned"
    sidechain_hits = [f for f in res["findings"] if f["sidechain"]]
    assert sidechain_hits, "no finding attributed to the subagent transcript"
    # project must resolve to the top-level dir, not 'subagents'
    assert all(f["project"] == proj for f in res["findings"])


def test_role_attribution_fields(tmp_path):
    """Findings carry branch + best-effort agent; explicit lane phrase wins."""
    miner = _load_miner()
    proj = "-tmp-aab-workspaces-xyz"
    _write(tmp_path, f"{proj}/sess.jsonl", [
        _err_record("Denied `Bash` in the chat lane: the chat agent does not edit",
                    branch="sprint/y", sidechain=False),
        _err_record("code-gen step: command failed", branch="sprint/y", sidechain=False),
    ])

    res = miner.mine(_args(tmp_path))

    chat = next(f for f in res["findings"] if "chat lane" in f["snippet"])
    assert chat["agent"] == "chat-lane", "explicit lane phrase must win over token frequency"
    assert all(f["branch"] == "sprint/y" for f in res["findings"])
    # the non-lane finding falls back to a session token guess (marked approximate)
    other = next(f for f in res["findings"] if "chat lane" not in f["snippet"])
    assert "code-gen" in other["agent"]


def test_lane_coverage_reports_scanned_entrypoints(tmp_path):
    """lane_coverage exposes which runtime lanes were scanned, so a missing lane
    (e.g. codex_sdk, which writes nowhere here) is a visible gap, not silence."""
    miner = _load_miner()
    _write(tmp_path, "-tmp-aab-workspaces-a/s.jsonl",
           [_err_record("permission denied", branch="b", sidechain=False, entrypoint="sdk-py")])
    _write(tmp_path, "-tmp-aab-workspaces-b/s.jsonl",
           [_err_record("permission denied", branch="b", sidechain=False, entrypoint="cli")])

    res = miner.mine(_args(tmp_path))
    assert res["scanned_projects"] == 2
    assert res["lane_coverage"] == {"sdk-py": 1, "cli": 1}
    assert "codex" not in res["lane_coverage"]  # absent lane = uncovered, by design


def test_project_filter_matches_top_level_dir(tmp_path):
    """--project-filter matches the project dir, not an intermediate path segment."""
    miner = _load_miner()
    _write(tmp_path, "-tmp-devpulse-keep/s.jsonl",
           [_err_record("permission denied", branch="b", sidechain=False)])
    _write(tmp_path, "-tmp-other-drop/s.jsonl",
           [_err_record("permission denied", branch="b", sidechain=False)])

    res = miner.mine(_args(tmp_path, project_filter="devpulse"))
    assert res["scanned_files"] == 1
    assert all("devpulse" in f["project"] for f in res["findings"])
