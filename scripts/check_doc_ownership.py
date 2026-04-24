#!/usr/bin/env python3
"""Deterministic ownership checker for reserved doc surfaces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from autonomous_agent_builder.cli.doc_ownership import check_doc_ownership


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether a doc target belongs to an existing owner surface."
    )
    parser.add_argument(
        "--target",
        required=True,
        help="Path to the doc file being created or updated.",
    )
    parser.add_argument(
        "--doc-class",
        default="all",
        choices=["all", "quality-gate", "workflow"],
        help="Reserved doc class to validate.",
    )
    args = parser.parse_args()

    target = Path(args.target)
    doc_class = None if args.doc_class == "all" else args.doc_class
    decision = check_doc_ownership(target, doc_class=doc_class)
    print(json.dumps(decision.to_payload(), indent=2))
    if decision.decision in {"WRONG_SURFACE"}:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
