#!/usr/bin/env python3
"""Regression tests for introspect.py — guards the self-report invariants that
broke once (2026-05-29): contradictory iteration counts, a dead idea-velocity
regex, and a false "all gates non-discriminating" claim at n=1.

Run:
  python3 -m pytest .claude/skills/autoresearch/scripts/test_introspect.py -q
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location("introspect", _HERE / "introspect.py")
assert _SPEC and _SPEC.loader
introspect = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(introspect)


# ── source-consistency invariant ───────────────────────────────────────────────
# The bug: verdict_distribution read iterations.json while token_economics read
# optimize_results.tsv, so §1 said "1 iteration" while raw stats said total:0.
# The contract: a row in the authoritative TSV is one iteration, full stop.


def _row(
    decision="discard", composite=30594, delta="2.46", gates="6/6", gates_json="", idea="idea3"
):
    return {
        "decision": decision,
        "composite": str(composite),
        "composite_delta_pct": delta,
        "gates_passed": gates,
        "gates_json": gates_json,
        "idea_ref": idea,
        "notes": "sha=abc status=shipped",
    }


def test_iter_count_matches_optimize_rows():
    rows = [_row(), _row(decision="keep")]
    iters = [introspect._iter_from_optimize_row(r) for r in rows]
    vd = introspect.analyze_verdict_distribution(iters)
    assert vd["total"] == len(rows) == 2
    assert vd["discarded"] == 1
    assert vd["kept"] == 1


def test_iter_from_optimize_row_maps_decision_to_verdict():
    it = introspect._iter_from_optimize_row(_row(decision="KEEP"))
    assert it["verdict"] == "keep"  # normalized lower-case
    assert it["composite"] == 30594
    assert it["delta_pct"] == pytest.approx(2.46)


def test_empty_decision_is_unknown_not_crash():
    it = introspect._iter_from_optimize_row(_row(decision=""))
    assert it["verdict"] == "unknown"


# ── idea-velocity parses the CURRENT OPTIMIZE_IDEAS.md format ───────────────────
# The bug: regex matched `N. **slug**` list-items; the file uses `## N. Title`
# headers + `- Attempted` lines, so it reported "0 of 0" against 11 ideas.


def test_idea_velocity_current_format(tmp_path):
    md = tmp_path / "OPTIMIZE_IDEAS.md"
    md.write_text(
        "# OPTIMIZE_IDEAS\n\n"
        "## 1. First idea\n- **Attempts**: none.\n\n"
        "## 2. Second idea\n- **Attempts**:\n  - Attempted 2026-05-26 branch:x result:discard\n\n"
        "## 3. Third idea\n- **Attempts**: none.\n"
    )
    v = introspect.analyze_idea_velocity(md)
    assert v["applicable"] is True
    assert v["total_ideas"] == 3
    assert v["attempted"] == 1  # only idea 2 has an Attempted line
    assert v["remaining"] == 2


def test_idea_velocity_real_file_nonzero():
    """The repo's live OPTIMIZE_IDEAS.md must parse to >0 ideas — a 0 here means
    the file format drifted away from the parser again."""
    real = introspect.IDEAS_MD
    if not real.exists():
        pytest.skip("OPTIMIZE_IDEAS.md not present in this checkout")
    v = introspect.analyze_idea_velocity(real)
    assert v["total_ideas"] > 0


# ── gate discrimination is unknown (not False) when unmeasurable ────────────────
# The bug: with the N/6 aggregate only, every gate reported discriminating=False,
# which §5 rendered as "all 6 gates never discriminated" — an n=1 artifact.


def test_gate_utility_unmeasurable_without_gates_json():
    iters = [introspect._iter_from_optimize_row(_row(gates_json=""))]
    gu = introspect.analyze_gate_utility(iters)
    assert gu["_measurable"] is False
    for name in introspect.GATE_NAMES:
        assert gu[name]["discriminating"] is None  # unknown, never a bare False


def test_gate_utility_measurable_with_gates_json():
    gj = (
        '{"cache_ratio_gt_5x_after_turn_2": true, "chunk_pressure_risk_false": true, '
        '"avoidable_cost_flags_empty": true, "gate_pass_rate_full": true, '
        '"feature_correct": true, "fully_shipped": false}'
    )
    iters = [introspect._iter_from_optimize_row(_row(gates_json=gj))]
    gu = introspect.analyze_gate_utility(iters)
    assert gu["_measurable"] is True
    assert gu["_measured_n"] == 1
    # introspect.GATE_NAMES are short labels mapped positionally to run.py's full
    # gate names; the 6th value (fully_shipped=false) lands on "ship".
    # n=1 → every gate is all-pass or all-fail → none discriminate yet (False,
    # not None: data exists, it just doesn't discriminate at this sample size).
    assert gu["ship"]["discriminating"] is False
    assert gu["cache"]["discriminating"] is False


def test_per_gate_bools_returns_none_for_aggregate_string():
    assert introspect._per_gate_bools({"gates": "6/6"}) is None
    assert introspect._per_gate_bools({"gates_passed": "5/6"}) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
