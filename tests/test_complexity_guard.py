"""Tests for the baseline-aware Python complexity ratchet."""

from __future__ import annotations

import json
from pathlib import Path

from autonomous_agent_builder.quality_gates.complexity import (
    ComplexityThresholds,
    build_complexity_report,
)


def test_default_file_complexity_target_is_500_lines() -> None:
    assert ComplexityThresholds().max_file_lines == 500


def _write_fixture(path: Path, extra_branch: bool = False) -> None:
    extra = (
        "\n"
        "    if value == 3:\n"
        "        return 3\n"
        if extra_branch
        else ""
    )
    path.write_text(
        "\n".join(
            [
                "def compact(value):",
                "    if value:",
                "        return 1",
                "    return 0",
                "",
                "def too_complex(value):",
                "    if value > 0:",
                "        if value > 1:",
                "            return 1",
                "    if value == 2:",
                "        return 2",
                f"{extra}    return 0",
            ]
        ),
        encoding="utf-8",
    )


def test_complexity_scanner_reports_unbaselined_function_hotspot(tmp_path):
    _write_fixture(tmp_path / "sample.py")

    report = build_complexity_report(
        tmp_path,
        baseline_path=tmp_path / "missing-baseline.json",
        thresholds=ComplexityThresholds(
            max_file_lines=100,
            max_function_lines=20,
            max_function_branches=2,
        ),
    )

    assert report["passed"] is False
    assert report["summary"]["functions_over_threshold"] == 1
    assert report["violations"] == [
        {
            "kind": "function",
            "path": "sample.py",
            "metric": "branches",
            "observed": 3,
            "threshold": 2,
            "reason": "missing_baseline",
            "qualname": "too_complex",
            "baseline_key": "sample.py::too_complex",
        }
    ]


def test_complexity_baseline_allows_current_hotspot_but_blocks_growth(tmp_path):
    fixture = tmp_path / "sample.py"
    _write_fixture(fixture)
    baseline_path = tmp_path / "complexity-baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": {},
                "functions": {
                    "sample.py::too_complex": {
                        "lines": 7,
                        "branches": 3,
                        "owner": "test owner",
                        "extraction_plan": "split branch policy",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    thresholds = ComplexityThresholds(
        max_file_lines=100,
        max_function_lines=20,
        max_function_branches=2,
    )

    report = build_complexity_report(tmp_path, baseline_path=baseline_path, thresholds=thresholds)

    assert report["passed"] is True

    _write_fixture(fixture, extra_branch=True)
    growth_report = build_complexity_report(
        tmp_path,
        baseline_path=baseline_path,
        thresholds=thresholds,
    )

    assert growth_report["passed"] is False
    assert growth_report["violations"] == [
        {
            "kind": "function",
            "path": "sample.py",
            "metric": "branches",
            "observed": 4,
            "threshold": 2,
            "reason": "baseline_growth",
            "qualname": "too_complex",
            "baseline_key": "sample.py::too_complex",
            "allowed": 3,
            "baseline_owner": "test owner",
            "baseline_extraction_plan": "split branch policy",
        }
    ]


def test_complexity_baseline_must_ratchet_down_when_hotspot_shrinks(tmp_path):
    fixture = tmp_path / "sample.py"
    _write_fixture(fixture)
    baseline_path = tmp_path / "complexity-baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": {},
                "functions": {
                    "sample.py::too_complex": {
                        "lines": 7,
                        "branches": 4,
                        "owner": "test owner",
                        "extraction_plan": "split branch policy",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    report = build_complexity_report(
        tmp_path,
        baseline_path=baseline_path,
        thresholds=ComplexityThresholds(
            max_file_lines=100,
            max_function_lines=20,
            max_function_branches=2,
        ),
    )

    assert report["passed"] is False
    assert report["violations"] == [
        {
            "kind": "function",
            "path": "sample.py",
            "metric": "branches",
            "observed": 3,
            "threshold": 2,
            "reason": "baseline_not_ratcheted_down",
            "qualname": "too_complex",
            "baseline_key": "sample.py::too_complex",
            "allowed": 4,
            "baseline_owner": "test owner",
            "baseline_extraction_plan": "split branch policy",
        }
    ]
