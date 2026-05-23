# OPTIMIZE_IDEAS

Living backlog of optimization hypotheses for the loop in [`OPTIMIZE.md`](OPTIMIZE.md).

Each idea has: **category**, **hypothesis** (what to try and what should improve), **SDK basis** (which Claude Agent SDK feature this leverages), **attempt log** (filled by the loop).

Order roughly by expected impact / cost — agent reads top-down.

---

## 1. Stable system-prompt header for cache hits

- **Category**: cache strategy
- **Hypothesis**: Move all stable Builder runtime guidance (CLAUDE.md content, agent role, tool list) into the first prompt block, separated from per-turn variable context. Should raise `cache_ratio` and lower `noncached_plus_output_tokens`.
- **SDK basis**: Claude Agent SDK prompt caching — cache hits are prefix-bound; any per-turn variation in the prefix kills caching.
- **Files**: `agents/execution_policy.py`, agent route prompt assembly.
- **Attempts**: none.

---

## 2. Drop Board state JSON from prompt; replace with bounded tool

- **Category**: context bloat
- **Hypothesis**: Stop injecting full Board JSON into the prompt at every turn. Expose `builder.board.get()` as a bounded MCP tool the agent calls only when needed. Should cut per-turn `noncached` tokens significantly.
- **SDK basis**: Bounded tool use + AskUserQuestion. SDK docs recommend tools over prompt-stuffing for state that changes per-turn.
- **Files**: `embedded/server/routes/agent.py` prompt-assembly.
- **Attempts**: none.

---

## 3. AskUserQuestion for intake instead of free-text 3-question dump

- **Category**: operator UX + tokens
- **Hypothesis**: The current 3-question intake (see IMP-001 context-loss bug) burns turns and tokens. Replace with `AskUserQuestion` structured 3-option cards. Should reduce `operator_turns` AND solve the multi-turn context-loss problem.
- **SDK basis**: `AskUserQuestion` tool — designed for structured product questions, not free-text dumps.
- **Files**: `agents/execution_policy.py`, agent route forward-engineering prompt.
- **Dependency**: Track A fix for IMP-001 should land first or be combined with this.
- **Attempts**: none.

---

## 4. Compact KB summary instead of full document injection

- **Category**: context bloat
- **Hypothesis**: When the agent references KB documents, only the relevant section + a 200-token summary header should enter the prompt, not full documents. Should lower `noncached` tokens on documentation-heavy turns.
- **SDK basis**: Subagent pattern — delegate KB summarization to a `repo-researcher` subagent that returns structured evidence rather than raw text.
- **Files**: `embedded/server/agent_documentation_context.py`.
- **Attempts**: none.

---

## 5. Per-turn observability context: only inject when there's a relevant signal

- **Category**: context bloat
- **Hypothesis**: Builder injects observability hints into every turn. Most turns don't need it. Inject only when the metrics surface has an active recommendation. Should lower baseline non-cached tokens.
- **SDK basis**: Bounded context + cache control — conditional injection preserves the stable prefix on turns where no signal exists.
- **Files**: `embedded/server/agent_observability_context.py`.
- **Attempts**: none.

---

## 6. Cap tool-output reinjection at 2K tokens with builder artifact pointer

- **Category**: chunk pressure + context bloat
- **Hypothesis**: Large tool outputs already become Builder artifacts. Reinject only a 2K-token head + pointer (`see builder artifact <id>`). Should keep `chunk_pressure_risk: false` and lower tokens on tool-heavy turns.
- **SDK basis**: Tool result compaction — SDK supports bounded reinjection patterns.
- **Files**: `orchestrator/agent_run_lifecycle.py`.
- **Attempts**: none.

---

## 7. Delete inactive phase-context blocks from implementation prompts

- **Category**: context bloat (deletion)
- **Hypothesis**: Implementation prompts include planning context and design context blocks even when phases are stable. Delete blocks where the phase is already complete and stored as evidence elsewhere.
- **SDK basis**: Simpler-wins-ties — autoresearch's deletion preference. Pure subtraction.
- **Files**: `orchestrator/phase_context.py`, `orchestrator/active_feature_scope.py`.
- **Attempts**: none.

---

## 8. Subagent for code-gen instead of inline tool loop

- **Category**: inefficient agent use
- **Hypothesis**: Code-gen task currently uses the main loop. Delegate to a Claude Agent SDK subagent with restricted tool scope (Read, Edit, Write only). Should reduce token cost per task and improve cache hits on the parent.
- **SDK basis**: Subagents with restricted permissions and tool allowlists.
- **Files**: subagent definitions, `agents/execution_policy.py`.
- **Attempts**: none.

---

## 9. Compact gate-feedback block: failures only, not full gate output

- **Category**: context bloat
- **Hypothesis**: Gate feedback currently injects full gate output. Inject only the failed assertions + file:line — drop passing checks and full stack traces. Pointer to artifact for the full log.
- **SDK basis**: Compact tool output pattern.
- **Files**: `orchestrator/gate_feedback.py`.
- **Attempts**: none.

---

## 10. Cache the system prompt header per-runtime-lane separately

- **Category**: cache strategy
- **Hypothesis**: Claude and Codex lanes share parts of the system prompt but diverge in tool specs. Split into a shared stable head + lane-specific cached suffix. Should improve cache_ratio on cross-lane sessions.
- **SDK basis**: Anthropic prompt caching — multiple cache breakpoints supported.
- **Files**: `agents/execution_policy.py`.
- **Attempts**: none.

---

## 11. After-fix sibling search

- **Category**: quality / regression prevention
- **Hypothesis**: After a bug-fix task closes, a bounded `repo-researcher` subagent scans for sibling files and tests that exhibit the same anti-pattern and flags them before the sprint ends. Should reduce recurring same-pattern regressions across the codebase.
- **SDK basis**: Claude Agent SDK bounded subagent (`repo-researcher`) returning structured evidence to the parent run; does not own lifecycle state.
- **Files**: `orchestrator/orchestrator.py`, `agents/definitions.py` (repo-researcher subagent), `services/task_dispatch_policy.py`.
- **Activation condition**: promote to active loop only when runtime evidence shows ≥2 recurring same-pattern regressions in consecutive sprints.
- **Attempts**: none.

---

## How to use this file

- The loop reads top-down and picks the first idea with `attempts: none`.
- After an iteration, append a result row in the idea's section: `- Attempted YYYY-MM-DD branch:<id> result:keep|discard composite_delta:<%> notes:<one line>`.
- New ideas can be added anywhere. Update the rough impact ordering when wins/losses reshape expectations.
- Ideas that produce stable wins move to `docs/autoresearch/PROGRESS.md` as completed work.
- Ideas that fail 3 attempts get marked `exhausted` and stop appearing in the loop.
