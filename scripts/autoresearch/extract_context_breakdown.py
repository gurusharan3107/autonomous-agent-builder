#!/usr/bin/env python3
"""Path A context breakdown extractor for the autoresearch loop.

Reads raw API request bodies dumped by ``OTEL_LOG_RAW_API_BODIES=file:<dir>``,
tokenizes each prompt content block with tiktoken, and assigns tokens to named
Builder source blocks via anchor regex (per docs/autoresearch/CONTEXT-LEDGER.md).

Emits a JSON map ``{<prompt_index>: {<breakdown>}}`` to stdout for run.py to
embed in per_prompt_results.tsv.context_breakdown_json.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any

try:
    import tiktoken
except ImportError:  # pragma: no cover
    tiktoken = None


ANCHORS: list[tuple[str, re.Pattern, str]] = [
    ("stable_system_prefix", re.compile(r"##\s+Operating Model", re.IGNORECASE),
     "agents/execution_policy.py"),
    ("board_state",
     re.compile(r"##\s+Current Board State|Current sprint:", re.IGNORECASE),
     "embedded/server/routes/agent.py"),
    ("phase_context", re.compile(r"##\s+Phase Context", re.IGNORECASE),
     "orchestrator/phase_context.py"),
    ("active_feature_scope", re.compile(r"##\s+Active Feature", re.IGNORECASE),
     "orchestrator/active_feature_scope.py"),
    ("observability_context",
     re.compile(r"##\s+Observability|Recommended next change:", re.IGNORECASE),
     "embedded/server/agent_observability_context.py"),
    ("documentation_context",
     re.compile(r"##\s+Knowledge Base References", re.IGNORECASE),
     "embedded/server/agent_documentation_context.py"),
    ("gate_feedback", re.compile(r"##\s+Latest Gate Failure", re.IGNORECASE),
     "orchestrator/gate_feedback.py"),
    ("task_workspace_summary", re.compile(r"##\s+Workspace Snapshot", re.IGNORECASE),
     "orchestrator/workspace_integration.py"),
]


def get_encoder() -> Any:
    if tiktoken is None:
        return None
    try:
        return tiktoken.encoding_for_model("claude-3-5-sonnet")
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, encoder: Any) -> int:
    if not text:
        return 0
    if encoder is None:
        return max(len(text) // 4, 0)
    try:
        return len(encoder.encode(text))
    except Exception:
        return max(len(text) // 4, 0)


def split_text_into_blocks(text: str, encoder: Any) -> dict[str, int]:
    """Partition `text` by anchor matches. Each anchor's region runs from its
    match offset until the next anchor's match offset; residual goes to
    `unattributed`."""
    matches: list[tuple[int, str, str]] = []
    for name, pat, source in ANCHORS:
        m = pat.search(text)
        if m:
            matches.append((m.start(), name, source))
    matches.sort()
    blocks: dict[str, int] = {}
    if not matches:
        blocks["unattributed"] = count_tokens(text, encoder)
        return blocks
    # Leading slice (before first anchor) → unattributed
    if matches[0][0] > 0:
        blocks["unattributed"] = blocks.get("unattributed", 0) + count_tokens(
            text[: matches[0][0]], encoder
        )
    for i, (off, name, _source) in enumerate(matches):
        end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        blocks[name] = blocks.get(name, 0) + count_tokens(text[off:end], encoder)
    return blocks


def process_raw_body(body: dict, encoder: Any) -> dict:
    """Process one raw API request body. Returns a breakdown dict."""
    total_tokens = 0
    block_tokens: dict[str, int] = {}

    # 1. system[] blocks → typically stable prefix + possibly board/operator additions
    for block in (body.get("system") or []):
        text = block.get("text", "") if isinstance(block, dict) else str(block)
        sub = split_text_into_blocks(text, encoder)
        for k, v in sub.items():
            block_tokens[k] = block_tokens.get(k, 0) + v
        total_tokens += count_tokens(text, encoder)

    # 2. messages[]: tool_result blocks → tool_reinjection; last user → operator_message
    messages = body.get("messages") or []
    operator_tokens = 0
    tool_tokens = 0
    last_user_idx = None
    for i, msg in enumerate(messages):
        if msg.get("role") == "user":
            last_user_idx = i
    for i, msg in enumerate(messages):
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                text = block.get("text") or ""
                if btype == "tool_result":
                    tool_text = (
                        json.dumps(block.get("content")) if block.get("content") else text
                    )
                    tool_tokens += count_tokens(tool_text, encoder)
                    total_tokens += count_tokens(tool_text, encoder)
                elif btype == "text":
                    if msg.get("role") == "user" and i == last_user_idx:
                        operator_tokens += count_tokens(text, encoder)
                    else:
                        sub = split_text_into_blocks(text, encoder)
                        for k, v in sub.items():
                            block_tokens[k] = block_tokens.get(k, 0) + v
                    total_tokens += count_tokens(text, encoder)
        elif isinstance(content, str):
            if msg.get("role") == "user" and i == last_user_idx:
                operator_tokens += count_tokens(content, encoder)
            total_tokens += count_tokens(content, encoder)

    block_tokens["tool_reinjection"] = block_tokens.get("tool_reinjection", 0) + tool_tokens
    block_tokens["operator_message"] = block_tokens.get("operator_message", 0) + operator_tokens

    blocks_list = []
    attributed = 0
    for name, source in [(n, s) for n, _p, s in ANCHORS] + [
        ("tool_reinjection", "runtime"),
        ("operator_message", "operator"),
    ]:
        t = block_tokens.get(name, 0)
        attributed += t
        blocks_list.append({"name": name, "tokens": t, "source": source})

    unattributed = max(total_tokens - attributed, 0)
    return {
        "total_tokens": total_tokens,
        "blocks": blocks_list,
        "unattributed_tokens": unattributed,
        "warning": "anchor_drift" if unattributed > total_tokens * 0.1 else None,
    }


def match_bodies_to_prompts(raw_bodies_dir: pathlib.Path, prompts: list[dict]) -> dict[int, dict]:
    """Walk raw_bodies_dir/*.jsonl in timestamp order, match to prompts[] by index."""
    files = sorted(raw_bodies_dir.glob("*.jsonl"))
    bodies: list[dict] = []
    for f in files:
        try:
            for line in f.read_text().splitlines():
                if not line.strip():
                    continue
                bodies.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            continue

    encoder = get_encoder()
    breakdown_by_prompt: dict[int, dict] = {}
    for i, body in enumerate(bodies):
        if i >= len(prompts) and prompts:
            break
        breakdown_by_prompt[i] = process_raw_body(body, encoder)
    return breakdown_by_prompt


def main() -> int:
    args = parse_args()
    raw_dir = pathlib.Path(args.raw_bodies_dir)
    analyze_path = pathlib.Path(args.analyze_json)
    if not raw_dir.exists() or not analyze_path.exists():
        # Emit empty mapping; harness treats as no-attribution-available.
        print("{}")
        return 0
    try:
        analyze = json.loads(analyze_path.read_text())
    except json.JSONDecodeError:
        print("{}")
        return 0
    prompts = analyze.get("prompts") or []
    breakdown = match_bodies_to_prompts(raw_dir, prompts)
    # Use string keys so JSON consumers can index by prompt_index.
    print(json.dumps({str(k): v for k, v in breakdown.items()}, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Path A context breakdown extractor.")
    p.add_argument("--raw-bodies-dir", required=True)
    p.add_argument("--analyze-json", required=True)
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())
