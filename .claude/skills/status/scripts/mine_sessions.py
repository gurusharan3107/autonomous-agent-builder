#!/usr/bin/env python3
"""Thin shim — the canonical session miner lives in
`.claude/skills/self-optimize/scripts/mine_sessions.py`.

Deduped 2026-06-17: the two copies were byte-identical and had drifted once
(the subagent-glob/lane-coverage fix landed in one copy before re-sync). Single
source of truth now; this shim forwards argv to the canonical script so callers
that invoke `status/scripts/mine_sessions.py` keep working unchanged.
"""
from __future__ import annotations

import pathlib
import runpy

_canonical = (
    pathlib.Path(__file__).resolve().parents[2]
    / "self-optimize" / "scripts" / "mine_sessions.py"
)
runpy.run_path(str(_canonical), run_name="__main__")
