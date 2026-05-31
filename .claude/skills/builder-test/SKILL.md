---
name: builder-test
description: >
  Use when the user says "test the builder", "verify my fix",
  "run builder tests", "run builder test", "did my change work",
  "check agent behavior", "verify the builder", "test my change",
  "check if the fix worked", or "did the agent behave correctly after my change". Runs a 6-phase verification loop against the
  running builder: preconditions → static (Pyright + bad-string grep) → unit
  (behavioral assertions on pure functions) → integration (REST API smoke
  tests) → E2E (submit operator instruction, observe session behavior, verify
  side-effects) → verdict. Produces a PASS/WARN/FAIL table with cited evidence
  per phase. Optional scope: /test <phase> (e.g. "static", "unit",
  "integration", "e2e") to run a single phase only.
allowed-tools: Read, Bash, Write, AskUserQuestion
---

# builder-test — verify a builder source change actually works

> **Self-validate after edits.** Any change to this skill's files (SKILL.md, scripts/, references/, templates/, assets/) must be followed by `./scripts/validate.sh` from the skill directory. Hard findings → create-skill Optimize lane.

7-phase loop: test → fix root causes → self-evolve. Phases 0–5 run
assertions and produce a FAIL/WARN/PASS verdict. Phase 5b fixes every FAIL
at its root cause (builder source, test data, or skill procedure) and
re-verifies before moving on — never patches symptoms. Phase 6 CLOSEOUT
encodes new failure modes and removes stale assertions so the skill stays
accurate without operator maintenance.

## Modes

- **Full run** (default): all 7 phases including CLOSEOUT. Use after any multi-file change.
- **Scoped run**: `/test <phase>` — runs only that phase + CLOSEOUT. Use for fast
  iteration on a specific fix (e.g. `/test unit` after editing intent
  classifier, `/test e2e "implement X"` after changing the chat agent).

## Prerequisites

Builder must be importable from the source repo. Builder server is started
automatically in Phase 0 if not already running on port 9876.

Workspace root: `/home/gurusharangupta/Builder-Workspace/devpulse`
Source repo: the autonomous-agent-builder source checked out here.

## Workflow

1. **PRECONDITIONS** — verify builder is running on :9876; start if not;
   confirm project loads. Abort on failure.
2. **STATIC** — Pyright diagnostics for new warnings; grep source for known
   bad strings. Flag findings, continue.
3. **UNIT** — behavioral assertions on pure functions (intent classifier,
   tool registry, prompt content). Per-function verdict.
4. **INTEGRATION** — REST API smoke tests; builder CLI round-trips. Abort
   E2E if any endpoint unreachable.
5. **E2E** — drive the dashboard via **hermes-chrome** (preflight `diagnose`
   first; agent types the operator instruction + clicks Send with a visible
   cursor); observe session (turns, tool calls, dispatch reached, output type);
   sweep EVERY surface (Backlog/Board/Metrics/Observability) via the bridge;
   verify side-effects (backlog item, no duplicates, status correct); cross-check
   issues with builder CLI logs/analyze/metrics **from the app workspace**.
6. **VERDICT** — PASS/WARN/FAIL table per phase with cited evidence. For each
   FAIL: diagnose root cause, apply surgical fix where the issue lives
   (builder source, test data, or skill procedure), re-run the affected phase
   to confirm. Do not move on until every FAIL is resolved or explicitly
   accepted as a known limitation.
7. **CLOSEOUT** — staleness scan (cross-refs, assertions, bad-string patterns);
   encode new failure modes; write introspection.md; apply fixes; delete it.
   Mandatory — never skip, even on PASS runs. This is what prevents drift.

See `reference/workflow.md` for the full phase procedure.
See `reference/assertions.md` for the assertion catalog and known bad patterns.

## Hard Rules

- **Keep each trigger phrase on one line in the description.** YAML folded
  scalar (`>`) folds newlines to spaces when parsed, but raw-text grep on
  the file will miss phrases split across lines. Never break a quoted phrase
  across a YAML line break.
- **NEVER skip Phase 0.** Health check gates everything — a builder on the
  wrong port or wrong workspace makes all other phases meaningless.
- **hermes-chrome is the E2E driver — checking AND triggering go through it.**
  The agent drives the real browser (visible cursor) for every UI action, like
  an operator: submit the instruction, navigate, sweep all surfaces. Run
  `python3 .claude/plugin/hermes_chrome/scripts/diagnose.py` first; abort E2E if
  not READY. `curl`/REST is for *observing* state only, never for triggering UI.
- **Assert output TYPE, not content.** Check "was AskUserQuestion emitted?"
  not the exact question text. Content assertions break on any prompt
  wording change.
- **ALWAYS verify side-effects.** A session that completes is not a pass.
  Check: backlog item created? no duplicates? status correct?
- **Grep for bad strings BEFORE E2E.** Catch hardcoded phrases and known
  anti-patterns in source before any session runs — saves a full E2E cycle.
- **FAIL FAST only at blockers.** Phase 0 + Phase 4 failures abort downstream.
  Static and unit failures are informational — log them and continue.
- **Fix FAILs at root cause, not in the skill.** When a phase produces a FAIL,
  find and fix the underlying issue where it lives — builder source code, test
  data, or skill procedure. Never add a workaround or gotcha to the skill when
  the actual cause can be fixed. Patching symptoms hides real problems and
  degrades the skill over time.
- **Never declare PASS without Phase 6 evidence table populated.**
- **CLOSEOUT (Phase 7) is mandatory on every run including PASS.** A run
  without CLOSEOUT leaves stale assertions, broken cross-references, and
  undiscovered failure modes silently accumulating. The skill self-evolves
  only through CLOSEOUT — skip it and the skill becomes a historical
  document within a few weeks.

## Gotchas

- **builder CLI JSON result keys VARY PER COMMAND — always check `ok` first,
  then the command-specific key. Never assume `data`.** A naive `d.get("data")`
  / `d.get("items")` silently returns `None`/`[]` and looks like "0 results" or
  "command returned nothing" — a false alarm, not a product bug. Confirmed
  shapes: `backlog item list` → `data: [...]`; `logs --error` → `results: [...]`
  + `count: N`; `logs analyze` → fields at **top level** (no wrapper, e.g.
  `recommended_next_change`, `total_cost_usd`); `metrics show` → fields at
  **top level** too (e.g. `optimization_summary`, `recent_runs`, `run_count`,
  `voice_ledger`, `context_budget`) — NOT under `data`. When a value looks
  empty/missing, re-check the key and `ok`/`error` BEFORE concluding anything
  is broken.
- **`builder logs` / `logs analyze` are workspace-local — run them from the
  generated-app workspace**, not the source repo (source repo returns
  `project_not_initialized` / `logs_unavailable`). `metrics show` and `backlog`
  route via `AAB_API_URL` and work from any cwd.
- **Dashboard labels backlog items "IMPROVEMENT" / "PLANNED IMPROVEMENTS" even
  when `type=feature`.** All current devpulse items are `type=feature` but render
  under the Improvements view. Treat the type from REST/CLI as truth; the badge
  is an operator-facing grouping, not the stored type. Don't flag this as a
  data bug without inspecting the badge-rendering component.
- Builder runs from `/home/gurusharangupta/Builder-Workspace/devpulse`, NOT
  from the source repo. Starting it from the wrong directory returns
  `{"error": "No .agent-builder/ directory found"}` on health — looks like
  a pass but the project won't load.
- Builder CLI defaults to port 8000. Always prefix with `AAB_API_URL=http://localhost:9876`
  when running `builder` commands against the devpulse instance.
  `AAB_PORT=9876` is ignored by the client — it only sets the server start port.
- `assistant_requests_delivery_permission()` text-match patterns are in
  `agent_chat_transcript.py:51-64`. If you add a new trigger phrase, update
  that list or Phase 3 unit tests will diverge from runtime behavior.
- A session that hits `max_turns` emits `stop_reason: max_turns`, not an
  error. Check `stop_reason` in logs, not just session status.
- Duplicate backlog items are a silent failure — the session looks clean but
  the same improvement was created twice. Always `builder backlog item list`
  after E2E and check for duplicates by title.
- **Chat agent model is `haiku` in `definitions.py:205` but overridden by
  `execution_policy.py`.** `definitions.py` `model=` is a fallback — the
  actual model comes from `_model_for_agent()` in `execution_policy.py`. If
  chat sessions use Haiku despite the config showing Sonnet, check that
  `"chat"` is present in the `implementation_model` set (lines ~252–261 of
  `execution_policy.py`). Haiku does not reliably follow complex tool-use
  instructions and will produce plain-text responses instead of dispatching.
- **Chat runtime prompt is `_general_chat_prompt()` in `agent_prompt_builders.py`,
  NOT `prompt_template` in `definitions.py`.** The `prompt_template` field in
  `definitions.py` is used by orchestrator agents only. Chat sessions are built
  by `build_chat_turn_prompt_plan()` → `_general_chat_prompt()`. Any behavioral
  change for the chat agent (backlog lookup, dispatch discipline, question rules)
  must go into `agent_prompt_builders.py`, not `definitions.py`.
- **A new MCP tool needs THREE places in sync or it is SILENTLY DROPPED at
  runtime** (`tool_not_found_in_registry` → tool absent from the agent's resolved
  tools, model gets nothing back): (1) `@tool` handler in `agents/tools/sdk_mcp.py`
  (+ `_to_mcp()` content envelope — a plain dict returns an empty result),
  (2) the agent's `allowed_tools` / subagent tools, (3) a `ToolSchema` in
  `agents/tool_registry.py` `_SDK_BUILTINS`. Unit tests and the
  `agent-sdk-verifier-py` audit do NOT catch a missing registry schema — only a
  live run does. **Phase 2/5 must grep the run log for `tool_not_found_in_registry`
  and FAIL on any hit**; `agent_phase_start ... tools=[...]` should contain every
  tool the agent declares. Guard each new tool family with a unit assertion that
  its names ⊆ `tool_registry._SDK_BUILTINS`. *(IMP-019 registry gap — caught only
  by a live feature-verifier run, 2026-05-30.)*

## Reference Files

- `reference/workflow.md` — full phase-by-phase procedure with exact commands
- `reference/assertions.md` — assertion catalog + known bad-string patterns;
  load when Phase 1 or Phase 3 assertions need domain context

## Cross-references

- `src/autonomous_agent_builder/embedded/server/agent_message_intent.py` —
  intent classifier (Phase 3 unit assertions)
- `src/autonomous_agent_builder/embedded/server/agent_chat_result_publisher.py` —
  publisher hardcoded strings (Phase 1 bad-string grep target)
- `src/autonomous_agent_builder/embedded/server/agent_chat_transcript.py:51` —
  delivery permission trigger patterns (Phase 3 unit assertions)
- `src/autonomous_agent_builder/agents/definitions.py` — chat agent tool list
  and max_turns (Phase 3 unit assertions); `model="haiku"` at line 205 is the
  fallback — actual model is resolved by execution_policy.py
- `src/autonomous_agent_builder/agents/execution_policy.py` — chat agent model
  routing; `"chat"` must be in `implementation_model` set for Sonnet (Phase 3
  unit assertions)
- `src/autonomous_agent_builder/embedded/server/agent_prompt_builders.py` —
  `_general_chat_prompt()` is the RUNTIME chat system prompt (NOT `definitions.py`
  `prompt_template`); behavioral E2E fixes go here
