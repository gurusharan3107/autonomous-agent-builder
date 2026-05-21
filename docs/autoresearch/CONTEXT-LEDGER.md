# Context Ledger — Per-Source Attribution

> **Read [README.md](README.md), [METRICS.md](METRICS.md), and [SDK-OBSERVABILITY.md](SDK-OBSERVABILITY.md) first.**

This file specifies how to capture *where each block of prompt context came from* — the single most important diagnostic for prompt-shape optimization. Without per-source attribution, an idea like "drop board state JSON from the prompt" can be tried but never verified to actually reduce the right tokens.

Two paths are documented. **Path A is executable today and is the default.** Path B is structured but requires Builder source instrumentation; it becomes the long-term replacement once the source change lands.

## The problem

The Builder assembles each prompt by concatenating blocks from several files:

| Block | Source file | Cache-eligible? |
| --- | --- | --- |
| `stable_system_prefix` (role, CLAUDE.md content, tool spec, MCP descriptions) | `agents/execution_policy.py` → `build_system_prompt()` | Yes — should be the stable cached prefix |
| `board_state` (current sprint, lane counts) | `embedded/server/routes/agent.py` → `_general_chat_prompt()` | No — changes per turn |
| `phase_context` (planning/design context for the current phase) | `orchestrator/phase_context.py` | Sometimes — stable within a phase |
| `active_feature_scope` (current feature + sibling ownership) | `orchestrator/active_feature_scope.py` | Sometimes |
| `observability_context` (recommendations / hints) | `embedded/server/agent_observability_context.py` | No — changes per turn |
| `documentation_context` (KB document references for the agent) | `embedded/server/agent_documentation_context.py` | No |
| `gate_feedback` (failed gate output for retry prompts) | `orchestrator/gate_feedback.py` | No |
| `task_workspace_summary` (sanitized workspace state) | `orchestrator/workspace_integration.py` | Yes (stable per task) |
| `tool_reinjection` (compacted tool outputs from prior turns) | runtime, varies | No |
| `operator_message` (the typed prompt) | the user | No |

Builder's `prompts[*].context_budget` field gives the total assembled context tokens. It does **not** break that total down by block. The loop needs the breakdown.

## Path A — Ground-truth OTEL capture (default, executable today)

Use the Claude Agent SDK's raw API body capture per [SDK-OBSERVABILITY.md § Recommended loop setup](SDK-OBSERVABILITY.md#recommended-loop-setup):

```bash
export OTEL_LOG_RAW_API_BODIES=file:${EVIDENCE_DIR}/raw_bodies
```

This causes the Claude Code CLI to write the **exact JSON sent to the Anthropic Messages API** to disk per turn, under `${EVIDENCE_DIR}/raw_bodies/`. Cache breakpoints are visible. This is the ground truth — whatever the loop attributes back to source files, the totals must match what Anthropic actually saw.

### What the raw body contains

Each file is one Anthropic API request payload:

```json
{
  "model": "claude-sonnet-4-6",
  "system": [
    { "type": "text", "text": "<stable_system_prefix>", "cache_control": {"type": "ephemeral"} },
    { "type": "text", "text": "<dynamic_system_addendum>" }
  ],
  "messages": [
    { "role": "user", "content": [
        { "type": "text", "text": "<board_state>\n\n<observability_context>\n\n<operator_message>" }
    ]},
    ...
  ],
  "tools": [ ... ]
}
```

The `cache_control` markers identify cache breakpoints. Content blocks before a breakpoint are cache-eligible; everything from the breakpoint onward is non-cached on a cache hit.

### How the harness turns raw bodies into `context_breakdown_json`

The runner runs an extractor per turn (`scripts/autoresearch/extract_context_breakdown.py` — see [HARNESS.md](HARNESS.md) for spec) that:

1. **Loads the raw body** for the turn (one JSON file per API call; `claude_code.interaction` span attribute `request.id` maps span → file).
2. **Tokenizes each content block** using `tiktoken` for the model's encoding. The harness should pin the encoding to the same one Anthropic uses for billing; the SDK exposes `model_usage[model].contextWindow` but not the encoding directly — pragmatic choice: `tiktoken.encoding_for_model("claude-3-5-sonnet")` is a close approximation and yields stable per-block counts (the relative split is what matters for the loop; absolute alignment with billing is already in `usage` fields).
3. **Anchors blocks back to Builder sources** using known marker strings:

   | Block | Anchor pattern (regex against block text) |
   | --- | --- |
   | `stable_system_prefix` | First content block in `system[]`; matches `## Operating Model\n` from CLAUDE.md |
   | `board_state` | `## Current Board State\n` or `Current sprint:` line |
   | `phase_context` | `## Phase Context\n` header |
   | `active_feature_scope` | `## Active Feature\n` header |
   | `observability_context` | `## Observability\n` header or `Recommended next change:` line |
   | `documentation_context` | `## Knowledge Base References\n` header |
   | `gate_feedback` | `## Latest Gate Failure\n` header |
   | `task_workspace_summary` | `## Workspace Snapshot\n` header |
   | `tool_reinjection` | `tool_result` content blocks in `messages[]` |
   | `operator_message` | Last `role: user` text content block, after the most recent assistant message |

   These anchors are stable as long as the Builder prompt assembly does not rename the headers. If a header changes, the extractor falls back to `other` for that block and writes a warning to `${EVIDENCE_DIR}/extractor_warnings.log`. Headers are intentionally not silent; the rename is a deliberate code change and the extractor is a deliberate part of the loop.

4. **Emits a JSON object** per prompt:

   ```json
   {
     "total_tokens": 28432,
     "cache_breakpoints": [4231],
     "blocks": [
       {"name": "stable_system_prefix", "tokens": 4231, "cache_segment": 0, "source": "agents/execution_policy.py"},
       {"name": "board_state",          "tokens": 1840, "cache_segment": 1, "source": "embedded/server/routes/agent.py"},
       {"name": "active_feature_scope", "tokens":  480, "cache_segment": 1, "source": "orchestrator/active_feature_scope.py"},
       {"name": "observability_context","tokens":  312, "cache_segment": 1, "source": "embedded/server/agent_observability_context.py"},
       {"name": "documentation_context","tokens": 2104, "cache_segment": 1, "source": "embedded/server/agent_documentation_context.py"},
       {"name": "phase_context",        "tokens":    0, "cache_segment": 1, "source": "orchestrator/phase_context.py"},
       {"name": "gate_feedback",        "tokens":    0, "cache_segment": 1, "source": "orchestrator/gate_feedback.py"},
       {"name": "task_workspace_summary","tokens": 1310, "cache_segment": 1, "source": "orchestrator/workspace_integration.py"},
       {"name": "tool_reinjection",     "tokens":18113, "cache_segment": 1, "source": "runtime"},
       {"name": "operator_message",     "tokens":   42, "cache_segment": 1, "source": "operator"}
     ],
     "unattributed_tokens": 0,
     "warning": null
   }
   ```

   `unattributed_tokens` should be 0 in a healthy run. Non-zero means the extractor's anchor set is out of date — fix the anchor before trusting the row.

5. **Writes** this JSON into the `context_breakdown_json` column of the per-prompt TSV row (verbatim, in a single line).

### Strengths and limits of Path A

| Strength | Why it matters |
| --- | --- |
| Ground truth — what Anthropic actually saw, including cache breakpoints | An idea that "moves observability into the cache prefix" can be verified to actually move it. |
| Zero Builder source changes | Works today. The whole loop can run end-to-end without waiting on a code change. |
| Cache breakpoint visibility | Surfaces cache-creation vs cache-read attribution that Builder analyze hides. |
| Works for both runtime lanes | (For Codex, raw bodies come from the Codex app-server log; the same extractor can target that file format.) |

| Limit | Mitigation |
| --- | --- |
| Anchor strings can drift if Builder renames a header | Extractor logs warnings; the loop treats high `unattributed_tokens` as a Tier 1 evaluation failure on the run. |
| Disk cost (~100 MB per ship-cycle) | Rotate `${EVIDENCE_DIR}` per run; archive only the runs the loop kept. |
| Includes operator/tool content verbatim | Acceptable for scripted fixtures; turn off (`=1` instead of `=file:...`) for any fixture with sensitive data. |
| Codex lane doesn't use Anthropic Messages API | Codex extractor parses Codex app-server payloads instead; structurally analogous, but two extractors. |
| Tokenization may not exactly match Anthropic billing | The loop cares about *relative* per-block change between runs, not absolute billing; ~1–2% per-block error is acceptable as long as it's consistent across runs. |

## Path B — Source-level instrumentation (future, structured)

When Builder source changes are scheduled (roadmap M3.5 dependency in [GAPS.md G-2](GAPS.md)), add a `PromptBlockLedger` that the assembly path appends to as each block is added.

### Proposed contract

```python
# src/autonomous_agent_builder/agents/prompt_block_ledger.py (new file)
from dataclasses import dataclass, field

@dataclass
class PromptBlock:
    name: str                  # e.g. "board_state"
    tokens: int                # tiktoken count of the block's text
    cache_eligible: bool       # would this block stay in cache across turns?
    source_file: str           # e.g. "embedded/server/routes/agent.py"
    source_function: str       # e.g. "_general_chat_prompt"
    note: str | None = None    # optional one-line reason for inclusion this turn

@dataclass
class PromptBlockLedger:
    blocks: list[PromptBlock] = field(default_factory=list)
    def add(self, name, text, cache_eligible, source_file, source_function, note=None):
        ...  # token-count text, append PromptBlock

    def as_dict(self) -> dict:
        ...  # serialize to context_breakdown_json shape from Path A above
```

### Where the ledger is constructed

The prompt-assembly entrypoints — `agents/execution_policy.build_system_prompt`, `embedded/server/routes/agent._general_chat_prompt`, the chat-runtime path that finalizes the assistant turn — instantiate one `PromptBlockLedger` per turn and call `ledger.add(...)` for each block they append. At turn finalization the ledger is serialized and persisted as a new chat event type `prompt_block_ledger` on the same chat session that already carries `context_budget`.

### How Builder CLI exposes it

`builder logs analyze --session <id> --full --json` adds one field to each prompt:

```json
"prompts": [
  {
    "prompt_index": 0,
    "tokens_input": 28432,
    "tokens_cached": 26100,
    "context_budget": {...existing fields...},
    "prompt_block_ledger": { "total_tokens": 28432, "blocks": [ ... ], "cache_breakpoints": [4231] }
  }
]
```

### Strengths and limits of Path B

| Strength | Why it matters |
| --- | --- |
| Structured at source — no anchor drift | The block name is provided by the source, not regex-matched. Renames are impossible to miss. |
| Cheap per run | No 100 MB raw-body capture; the ledger is small JSON. |
| Source-traceable | `source_file` and `source_function` make it trivial to navigate from a row to the code that emitted it. |
| Cross-lane uniform | Codex runtime can write the same ledger shape from its Python side. |

| Limit | Mitigation |
| --- | --- |
| Requires Builder source change touching the assembly path | Tracked as [GAPS.md G-2](GAPS.md). |
| Drift risk: source ledger may say 1840 tokens but Anthropic billed something different if the assembly mutates the text after `ledger.add(...)` | The ledger contract requires `add` to be called with the *final* text — after any sanitization, before serialization to the API request. A unit test pins this invariant. |
| Adds a small per-turn cost (tokenization happens twice: once for the ledger, once by Anthropic) | Negligible (~5 ms per turn at Sonnet prompt sizes). |

## How the two paths relate

Both paths produce the same JSON shape (the example under Path A § step 4). The harness consumes one or the other; the per-prompt TSV column `context_breakdown_json` is identical in either case. This means the loop, comparison, and downstream tooling are unchanged when Builder migrates from Path A to Path B — only the *producer* changes.

While both paths are live, the loop should prefer the source-level ledger (Path B) for the `context_breakdown_json` value and use OTEL raw bodies (Path A) as a cross-check. A `path_b_vs_path_a_delta_pct` field on the per-prompt row catches the drift case where the source ledger says one thing and the raw body says another — if delta exceeds 5%, the run is flagged for investigation.

## Recommended migration

1. **v1 of the loop:** Path A only. Executable now. Gets the loop running. Anchor strings are stable enough for the current Builder prompt assembly.
2. **After loop produces first 5–10 wins:** evaluate whether Path A's anchor-string drift is becoming an operational tax. If yes, schedule Path B as a source change.
3. **v2 of the loop:** Path B is the producer; Path A is the cross-check. Drift > 5% blocks the run.
4. **Long term:** Path A capture remains available for forensic analysis (full prompt body when something weird happens), but is off by default to save disk.

## Related

- [SDK-OBSERVABILITY.md](SDK-OBSERVABILITY.md) for how to turn on raw-body capture (Path A).
- [GAPS.md G-2](GAPS.md) for the Path B source change scope and effort estimate.
- [HARNESS.md](HARNESS.md) for the extractor script and where it slots into the runner.
- [METRICS.md per_prompt_results.tsv](METRICS.md#per-prompt-tsv-per_prompt_resultstsv--new-in-this-framework) for the column definition.
