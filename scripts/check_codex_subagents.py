#!/usr/bin/env python3
"""Validate project-scoped Codex custom agents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from autonomous_agent_builder.codex_subagents import validate_project_codex_subagents


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check .codex/agents project custom-agent contracts."
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root containing .codex/config.toml and .codex/agents/.",
    )
    args = parser.parse_args()

    result = validate_project_codex_subagents(Path(args.repo_root).resolve())
    print(json.dumps(result.to_payload(), indent=2))
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
