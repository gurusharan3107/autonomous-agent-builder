# Fix Standard — The Seven Steps

> **Read [README.md](README.md) first.**

This is the operational doctrine every non-trivial fix must follow. It exists because shortcuts past these steps consistently produce regressions, re-litigated decisions, and wasted memory writes. The steps are ordered — skipping or reordering them is the root cause of most repeat failures.

When something fails: diagnose from first principles, start from the visible symptom, inspect builder-owned logs / metrics / session evidence, identify the true owning layer, and fix the durable product or runtime cause.

## The Seven Steps

### Step 0 — Load repo precedent first

Before exploring code for any non-trivial fix, retrieve repo memory:

```bash
builder memory search "<topic>" --tag <relevant-tags>
builder memory show <slug>     # for each hit
```

Run these commands **from the Builder source repo**, not from a managed app workspace. The 90+ active memories under `.memory/` (corrections, decisions, patterns) encode prior decisions that must shape the fix. Skipping this step risks re-litigating settled questions or violating a single-owner pattern (e.g., `blocked-recovery-has-one-builder-owner`, `keep-agent-page-intent-model-backed-while-optimizing-token`).

Why this is Step 0 and not Step 7: a fix grounded in stale or absent memory creates patches that fight existing patterns. Loading memory first means the fix conforms to repo precedent from the start, not retroactively.

### Step 1 — Explore the codebase

Find the exact owning module, route, or runtime path before proposing a fix. Use the Explore agent or `grep` / `find` to locate the real owner. Do not guess based on filenames.

Common traps:
- File name suggests one owner; actual logic lives in a sibling module imported by it.
- Multiple modules look like the owner; only one has the canonical state mutation.
- An adapter or facade wraps the real owner; patching the adapter only paints over.

### Step 2 — Load required AGENTS.md / CLAUDE.md triggers

Before editing any file with a required trigger (`CLAUDE.md`, `AGENTS.md`, runtime, CLI, quality gates), run the prescribed quality-gate or workflow first:

```bash
builder quality-gate <surface> --json
workflow summary <name>
```

`AGENTS.md` and `CLAUDE.md` list the triggers — follow them. Examples:

- Before editing `CLAUDE.md`: `builder quality-gate claude-md --json`.
- Before editing Claude SDK runtime: `builder quality-gate claude-agent-sdk --json`.
- Before editing Builder CLI: `workflow quality-gate cli-for-agents`.
- Before changing phase boundaries: `workflow summary phase-model`.
- Before changing task workspaces: `workflow summary task-workspace-isolation`.

### Step 3 — Ground the fix in SDK documentation and best practices

Not workarounds. Cite the SDK feature being used:

- **Claude Agent SDK:** permissions, hooks, subagents, `AskUserQuestion`, compaction, cache control, session resume/fork, `max_turns`, `effort`, `thinking` budget.
- **Codex SDK:** app-server events, native `request_user_input` mapping, MCP elicitations, request permissions, token usage stream evidence, large-output artifact storage.

If the fix relies on a feature the SDK does not natively provide, the fix is probably at the wrong layer. Re-evaluate.

### Step 4 — Apply at the correct layer

Not patched at the surface. Owner layers, top to bottom:

- **Orchestrator** owns phase routing, retries, blocked-state handling, progression, and follow-up work selection after explicit product events.
- **Route layer** (embedded server) owns HTTP contract, SSE publication, event persistence, and request routing.
- **Runtime adapter** (Claude SDK / Codex SDK) owns session, tool execution, hook policy, permission callbacks, telemetry capture.
- **Frontend** owns visible state, design-system primitives, inline controls, control ownership reconciliation.

Rule: **do not patch the UI if the backend state is wrong.** Do not patch the route if the orchestrator owns the transition. Do not patch the orchestrator if the runtime adapter is the true owner.

### Step 5 — Verify with builder quality-gate and focused regression tests

Add a **deterministic regression test** for the exact failure. The test must reproduce the symptom without the fix, and pass with it.

```bash
# Targeted regression run
PYTHONPATH=src .venv/bin/python -m pytest tests/test_<area>.py::test_<specific> -q

# Touched-surface gates
builder quality-gate <surface> --json
builder lint --complexity-report --json
```

The regression test is the durable artifact; the fix without it will silently regress in three sprints.

### Step 6 — Record in `docs/IMPROVEMENTS.md`

Each entry: symptom, root cause, SDK-grounded solution, evidence (session id, command output, board state), status. See existing IMP-001 to IMP-005 entries for the canonical format.

### Step 7 — Write memory back if the learning is durable

After the fix lands, ask: would a future agent doing similar work benefit from knowing this? If yes, run:

```bash
# From the Builder source repo, not a managed app workspace
builder memory add --type correction|pattern|decision --tag <relevant-tags>
```

**Memory is for:**
- Non-obvious owner boundaries.
- Single-control-owner patterns (e.g., `blocked-recovery-has-one-builder-owner`).
- Recurring traps (e.g., memory scope confusion in IMP-005).
- SDK-specific gotchas.
- Reasoning that wasn't obvious from code alone.

**Memory is NOT for:**
- The symptom itself (that lives in IMPROVEMENTS.md).
- One-off bug details.
- Anything the next agent could derive by reading current code.

**Invalidate stale memory.** If the fix proved an existing memory wrong, run:

```bash
builder memory invalidate <slug> --reason <one-line>
```

## Memory is bidirectional

This is the single rule that compounds: the 90+ memories in `.memory/` exist because past agents wrote them after fixes. Future agents read them in Step 0. Skipping either side breaks the loop:

- Skip Step 0 (read) → re-litigate settled decisions, violate patterns.
- Skip Step 7 (write) → next agent has nothing to load.

A fix that loads precedent in Step 0 and writes back in Step 7 makes the next similar fix faster. A fix that does neither makes the system worse over time even if the immediate change is correct.

## What this standard explicitly forbids

- **Symptom-level patches.** If the UI shows a wrong number, do not fix the UI rendering — fix the backend that produced the wrong number. If the message is wrong, fix the producer, not the renderer.
- **Workarounds in lieu of SDK grounding.** "It works if I retry three times" is a workaround. The SDK has retry primitives; use them.
- **Bypassing visible product surfaces.** Do not use raw API, database writes, or CLI mutations to "make the test pass" or "fix the state." If the dashboard can't do it, the dashboard is wrong; fix the dashboard.
- **Generated-app hand-patches.** Do not patch generated apps by hand to satisfy Builder validation. The Builder produced the bad output; fix the Builder.
- **Memory write without learning.** Don't write a memory entry just to mark a step done. Write it only when there is durable, non-obvious learning.

## When to invoke this standard

- Any defect closure (IMP-NNN in IMPROVEMENTS.md).
- Any roadmap item in [ROADMAP.md](ROADMAP.md) marked `bug` or `defect`.
- Any quality-gate failure investigation.
- Any operator-reported issue that requires investigation beyond a one-line cosmetic fix.

For purely cosmetic / typo / format fixes, the standard is overkill — use judgment.

## Related

- [README.md § Hard Rules](README.md#hard-rules-non-negotiable-for-every-agent-in-every-session) — the procedural rule that this standard applies to every non-trivial fix.
- [RESUME.md](RESUME.md) — the resume protocol uses this standard once an item is identified.
- [docs/IMPROVEMENTS.md](../IMPROVEMENTS.md) — where Step 6 evidence lives.
- [docs/workflows/memory-retrieval-guide.md](../workflows/memory-retrieval-guide.md) — Step 0 procedural detail.
- [docs/workflows/system-improvement-loop.md](../workflows/system-improvement-loop.md) — broader debugging workflow that wraps this standard.
- `.memory/` (via `builder memory`) — the corpus that Step 0 reads and Step 7 writes.
