#!/usr/bin/env python3
"""Prepare deterministic CI outputs for documentation freshness automation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from autonomous_agent_builder.knowledge.documentation_freshness_ci import (
    prepare_documentation_freshness_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare documentation-freshness CI decisions from builder validation output."
    )
    parser.add_argument(
        "prepare",
        nargs="?",
        default="prepare",
        help="Compatibility positional command. Only `prepare` is supported.",
    )
    parser.add_argument(
        "--validation",
        required=True,
        help="Path to builder knowledge validate --json output.",
    )
    parser.add_argument(
        "--prompt-out",
        required=True,
        help="Where to write the Claude prompt when needed.",
    )
    parser.add_argument(
        "--github-output",
        required=False,
        help=(
            "Optional path to the GitHub Actions output file. When omitted, "
            "JSON is printed to stdout."
        ),
    )
    args = parser.parse_args()

    if args.prepare != "prepare":
        raise SystemExit("Only the `prepare` command is supported.")

    validation_path = Path(args.validation)
    prompt_path = Path(args.prompt_out)
    payload = json.loads(validation_path.read_text(encoding="utf-8"))
    plan = prepare_documentation_freshness_plan(payload, workspace_path=Path.cwd())
    prompt_path.write_text(plan.prompt, encoding="utf-8")

    output = {
        "mode": plan.mode,
        "summary": plan.summary,
        "actionable_doc_ids": ",".join(doc.doc_id for doc in plan.actionable_docs),
        "manual_attention_reasons": " | ".join(plan.manual_attention_reasons),
    }
    if args.github_output:
        _write_github_output(Path(args.github_output), output, plan.prompt)
    else:
        print(json.dumps(output, indent=2))
    return 0


def _write_github_output(path: Path, output: dict[str, str], prompt: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in output.items():
            handle.write(f"{key}={value}\n")
        handle.write("prompt<<__DOC_PROMPT__\n")
        handle.write(prompt)
        handle.write("\n__DOC_PROMPT__\n")


if __name__ == "__main__":
    raise SystemExit(main())
