#!/usr/bin/env python3
"""Deterministic content checks for quality-gate docs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from autonomous_agent_builder.cli.doc_contracts import check_quality_gate_wording


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether a quality-gate doc reads like a gate instead of an owner doc."
    )
    parser.add_argument(
        "--target",
        required=True,
        help="Path to the quality-gate markdown file to validate.",
    )
    args = parser.parse_args()

    decision = check_quality_gate_wording(Path(args.target))
    print(json.dumps(decision.to_payload(), indent=2))
    if decision.decision == "CONTENT_DRIFT":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
