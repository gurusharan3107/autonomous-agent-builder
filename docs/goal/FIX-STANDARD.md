# Fix Standard — The Seven Steps

> Read [README.md](README.md) first.

Doctrine for every non-trivial fix. Steps are ordered; skipping/reordering produces regressions and re-litigated decisions.

Diagnose from symptom → builder logs/metrics/session evidence → true owning layer → durable fix.

## The Seven Steps

### Step 0 — Load repo precedent

```bash
builder memory search "<topic>" --tag <tags>
builder memory show <slug>
```

Run from Builder source repo, not managed app. 90+ memories under `.memory/` encode prior decisions; skipping = re-litigation or pattern violation. Memory first so the fix conforms from the start, not retroactively.

### Step 1 — Explore the codebase

Find the actual owning module before proposing a fix. Use Explore / `grep` / `find`. Don't guess by filename.

Traps:
- Filename suggests owner; actual logic in sibling module.
- Multiple candidates; only one mutates canonical state.
- Adapter wraps real owner; patching adapter just paints over.

### Step 2 — Load required triggers

Before touching a file with a required trigger (`CLAUDE.md`, `AGENTS.md`, runtime, CLI, gates):

```bash
builder quality-gate <surface> --json
workflow summary <name>
```

Examples: `CLAUDE.md` → `builder quality-gate claude-md`; Claude SDK runtime → `builder quality-gate claude-agent-sdk`; CLI → `workflow quality-gate cli-for-agents`; phase boundaries → `workflow summary phase-model`; workspaces → `workflow summary task-workspace-isolation`.

### Step 3 — Ground the fix in SDK docs

No workarounds. Cite the SDK feature:

- **Claude Agent SDK:** permissions, hooks, subagents, `AskUserQuestion`, compaction, cache control, session resume/fork, `max_turns`, `effort`, `thinking` budget.
- **Codex SDK:** app-server events, `request_user_input`, MCP elicitations, request permissions, token stream, large-output artifacts.

If the fix needs something the SDK doesn't provide, it's at the wrong layer.

### Step 4 — Apply at the correct layer

Owner layers (top→bottom):

- **Orchestrator** — phase routing, retries, blocked states, progression, follow-up selection.
- **Route layer** — HTTP contract, SSE, event persistence, request routing.
- **Runtime adapter** — sessions, tool execution, hooks, permission callbacks, telemetry.
- **Frontend** — visible state, design-system primitives, inline controls.

Rule: don't patch UI if backend is wrong. Don't patch route if orchestrator owns the transition. Don't patch orchestrator if runtime adapter is the true owner.

### Step 5 — Verify with gates + regression test

Deterministic regression test for the exact failure: reproduces without fix, passes with fix.

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_<area>.py::test_<specific> -q
builder quality-gate <surface> --json
builder lint --complexity-report --json
```

The test is the durable artifact. Without it the fix silently regresses.

### Step 6 — Record in `docs/IMPROVEMENTS.md`

Entry: symptom, root cause, SDK-grounded solution, evidence (session id, command output, board state), status. Follow IMP-001..IMP-005 format.

### Step 7 — Write memory back if durable

Ask: would a future agent benefit? If yes:

```bash
builder memory add --type correction|pattern|decision --tag <tags>
```

**Memory is for:** non-obvious owner boundaries; single-owner patterns; recurring traps; SDK gotchas; reasoning not derivable from code.

**Memory is NOT for:** the symptom itself (→ IMPROVEMENTS.md); one-off bug detail; anything derivable from current code.

Invalidate stale memory: `builder memory invalidate <slug> --reason <one-line>`.

Bidirectional: skip Step 0 → re-litigation. Skip Step 7 → next agent has nothing.

## Explicitly forbidden

- **Symptom-level patches.** Wrong number in UI → fix the backend producer, not the renderer.
- **Workarounds in lieu of SDK grounding.** "Works if I retry three times" = workaround. SDK has retry primitives; use them.
- **Bypassing visible surfaces.** No raw API / DB writes / CLI mutations to "make tests pass" or "fix state." Dashboard can't do it → fix dashboard.
- **Generated-app hand-patches.** Builder produced bad output → fix Builder.
- **Memory writes without learning.** Don't write to mark a step done.

## When to invoke

- Any defect closure (IMP-NNN).
- Any roadmap item marked `bug` / `defect`.
- Any quality-gate failure investigation.
- Any operator-reported issue beyond a cosmetic one-liner.

Cosmetic / typo / format fixes: overkill — use judgment.

## Related

- [README.md § Hard Rules](README.md#hard-rules-non-negotiable) — rule layer.
- [RESUME.md](RESUME.md) — uses this once item identified.
- [docs/IMPROVEMENTS.md](../IMPROVEMENTS.md) — Step 6 evidence.
- [docs/workflows/memory-retrieval-guide.md](../workflows/memory-retrieval-guide.md) — Step 0 detail.
- [docs/workflows/system-improvement-loop.md](../workflows/system-improvement-loop.md) — broader debugging.
- `.memory/` — corpus Step 0 reads, Step 7 writes.
