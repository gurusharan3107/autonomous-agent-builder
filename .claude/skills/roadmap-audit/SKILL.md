---
name: roadmap-audit
description: "Revalidate docs/goal/ROADMAP.md against the latest Claude Agent SDK rubric (via `workflow knowledge`) AND the live codebase (via grep src/), then append a verdict to docs/goal/INSIGHTS.md and edit ROADMAP.md with codebase-validated additions. Codebase validation is the non-obvious step: it stops the skill from recommending SDK levers that are already adopted (the prior ad-hoc rubric review recommended G8 `AskUserQuestion` which was already mature in `agent_tool_policy.py` + `agents/definitions.py`). Use this skill whenever the user asks 'revalidate the roadmap', 'audit the roadmap against SDK best practices', 'what SDK levers are we missing?', 'cross-check the roadmap with the rubric', 'is the roadmap aligned with current SDK?', or any variant that pairs ROADMAP and SDK/rubric/best-practice/feature-gap language. ALSO use proactively after every Claude Agent SDK minor release (signature surface shifts between 0.2.x versions), after a `knowledge-base` refresh that touched `claude-agent-sdk-rubric`, or when INSIGHTS gains a new ad-hoc rubric-style entry that has not yet been codebase-grounded. Complements `goal-audit` (transcript→intent→roadmap) and `knowledge-base` (SDK upstream→KB rubric) without overlapping — this is the inverse direction (KB rubric → ROADMAP → live codebase)."
model: sonnet
effort: high
allowed-tools: Read, Edit, Bash
compatibility:
  - python3 >= 3.9
  - workflow CLI at ~/.claude/bin/workflow.py (invoked as `python3 ~/.claude/bin/workflow.py` because the `workflow` shim hard-codes `python` and many WSL/Linux boxes have only `python3`)
  - ripgrep or grep available on PATH
  - ctx7 CLI on PATH (for SDK signature pre-checks cited in each ROADMAP addition)
---

# ROADMAP ↔ SDK Rubric Audit

## ⚠ HARD RULE — FILES THIS SKILL MUST NEVER EDIT

Internalize this list before any tool call. The skill is **active** on `docs/goal/ROADMAP.md` and `docs/goal/INSIGHTS.md` only. Every other file in `docs/goal/` has a single human control owner; recommendations that touch them go in the INSIGHTS verdict, not in those files:

- `docs/goal/STATUS.md`
- `docs/goal/NORTH-STAR.md`
- `docs/goal/EVALUATION.md`
- `docs/goal/FIX-STANDARD.md`
- `docs/goal/OPERATOR-LANGUAGE.md`
- `docs/goal/TUNING.md`
- `docs/goal/RESUME.md`
- `docs/goal/INDEX.md`
- `docs/goal/README.md`
- `docs/IMPROVEMENTS.md`
- `docs/SPRINT-PROGRESS.md`
- `docs/PROGRESS.md`
- `docs/PROMPT.md`
- any file in `src/` (the skill *reads* the codebase via grep — never edits it)

**Why ROADMAP is editable here but not in `goal-audit`:** `goal-audit` derives recommendations from transcript intent, which is subjective. This skill derives recommendations from the cross-product of `workflow knowledge` (objective, dated KB) and `grep src/` (objective, current code state). Drift between those two surfaces is mechanical, not strategic — encoding the closure into the skill is safe.

**Self-check before final report:** the list of files you edited this run must be a subset of `{ROADMAP.md, INSIGHTS.md}`. If it isn't, revert before reporting.

## Purpose

The Claude Agent SDK ships hundreds of options, callbacks, and message types. A coding agent reads the rubric and notices ten "we should be using that" levers per pass. The trap: half of them are already adopted somewhere in `src/`, and recommending them anyway burns user attention and pollutes the ROADMAP backlog with phantom work. The other half are real gaps — but without a codebase check, the rationale ("Current state: …") is guessed instead of cited.

This skill closes that loop deterministically:

1. Pull the canonical SDK rubric from `workflow knowledge` (always the latest, never hardcoded).
2. Walk it lever-by-lever, asking the rubric "do we use this?" *as a grep against `src/`*, not as a vibe check.
3. Bucket each candidate: **confirmed-missing** → add to ROADMAP; **already-present** → withdraw; **partial** → narrow the recommendation and cite the existing implementation by `path:line`.
4. Separately audit closed `[x]` items for SDK-debt — but only flag the debt if no pending `[ ]` item already covers the same lever, since re-opening covered ground is noise.
5. Append a structured verdict entry to INSIGHTS with the full validation table.

The validation table is the durable artifact: even if the skill is re-run a week later, the prior entry shows exactly what was checked, what was added, and what was deliberately withdrawn.

## When To Use

Trigger whenever:

- The user asks meta-direction questions that pair ROADMAP with SDK terminology: "revalidate the roadmap", "audit roadmap vs SDK", "what SDK features are we not using?", "cross-check the rubric against the roadmap", "is the roadmap behind on SDK best practices?".
- A `knowledge-base` refresh just modified the `claude-agent-sdk-rubric` article (the rubric is the input — when it changes, the audit is stale).
- A Claude Agent SDK minor version landed (`0.2.85 → 0.2.86+`) and the prior audit was against the older version.
- INSIGHTS gains a new ad-hoc rubric-style entry (manual, not from `goal-audit`) that the author didn't codebase-ground. Re-run this skill to ground it.

Do NOT trigger for:

- Routine intent/alignment questions ("are we aligned?", "what's next?") — that's `goal-audit`.
- Pulling new SDK features INTO the KB — that's `knowledge-base` (`refresh` operation).
- Implementing one specific item from the ROADMAP — that's normal development work; the skill's output is the input to that work, not a substitute for it.

## Workflow

### Step 1 — Bootstrap

Read in this order (single pass, no second reads):

1. `docs/goal/ROADMAP.md` — full file. You need every `[ ]` and `[x]` item plus milestone outcomes to know where each candidate lever would land.
2. `docs/goal/INSIGHTS.md` — full file (or just the most recent ad-hoc rubric entry if INSIGHTS is large). Prior audits' withdrawals and partial-coverage notes prevent re-litigating.
3. The latest SDK rubric:

```bash
# Find the latest rubric article (don't hardcode the date — the file is regenerated)
python3 ~/.claude/bin/workflow.py knowledge search "claude agent sdk rubric"
# Then read the dated slug it returns:
python3 ~/.claude/bin/workflow.py knowledge read <slug>
```

If `workflow knowledge` is unavailable (no network, no python3), abort with a clear error — this skill cannot do the audit from training data because SDK signatures shift between releases.

### Step 2 — Build the candidate list

Walk every "When you need to… / Reach for…" row in the rubric and extract the SDK lever name(s). Typical fields: option flag (e.g. `include_partial_messages`), callback (`can_use_tool`), message type (`StreamEvent`), hook spec (`PostToolUseHookSpecificOutput.updatedToolOutput`).

Also include cross-cutting candidates the rubric calls out:

- `async with ClaudeSDKClient(...)` context-manager adoption
- `setting_sources` shape and `exclude_dynamic_sections` flag
- Typed error catch surface (`CLINotFoundError`, `ProcessError`, `CLIJSONDecodeError`, `AssistantMessageError`, `api_error_status`)
- `AgentDefinition.maxTurns`, per-phase `allowed_tools`
- `SessionStore` adapter
- File checkpointing
- `StopFailure` hook (rubric § Hooks)
- `permissionDecision="defer"` + `DeferredToolUse`
- `include_hook_events=True` → `HookEventMessage`
- `strict_mcp_config`
- `effort:"xhigh"`, `thinking_display`
- `AskUserQuestion` built-in adoption
- `skills` option + `disable_mode`

Skip anything explicitly TS-only unless the codebase has a TS surface — note as "N/A on current lane" rather than dropping silently.

### Step 3 — Codebase validation (the core step)

For each candidate, grep `src/`. The grep is the **evidence**, not a sanity check — every entry in the validation table cites either the absence (zero hits) or the implementation (`path:line`).

Run greps in parallel batches. Useful patterns:

```bash
# Exact SDK identifiers
grep -rn "SessionStore\|session_store" src/ --include="*.py"
grep -rn "permissionDecision\|DeferredToolUse" src/ --include="*.py"
grep -rn "include_hook_events\|HookEventMessage" src/ --include="*.py"
grep -rn "exclude_dynamic_sections\|include_partial_messages\|strict_mcp_config" src/ --include="*.py"
grep -rn "updatedToolOutput\|updated_tool_output" src/ --include="*.py"
grep -rn "can_use_tool\|CanUseTool\|PermissionResultDeny" src/ --include="*.py"
grep -rn "AskUserQuestion" src/ --include="*.py"
grep -rn "CLINotFoundError\|CLIJSONDecodeError\|ProcessError\|AssistantMessageError" src/ --include="*.py"
grep -rn "ClaudeSDKClient" src/ --include="*.py"
grep -rn "setting_sources\|SystemPromptPreset" src/ --include="*.py"

# Hook registrations  
grep -rn "StopFailure\|stop_failure\|stopFailure" src/ --include="*.py"
```

**Distinguish three states per candidate:**

| State | What the grep shows | Action |
|---|---|---|
| Confirmed missing | Zero hits, or only docstring/comment mentions with no actual registration | Add to ROADMAP under the milestone whose outcome the lever serves |
| Already present | Real call site(s) in code paths that actually execute | **Do not** add; record withdrawal in INSIGHTS |
| Partial | Some related code (e.g. CLI typed errors caught, but not `AssistantMessageError`) | Narrow recommendation; cite the existing impl by `path:line`; refine the language on any existing ROADMAP item |

**Important — read the surrounding code before classifying as "present":**
A `grep` hit on `"AskUserQuestion"` could be (a) the tool listed in `allowed_tools=[...]`, (b) prose in a prompt template instructing a subagent to use it, or (c) an inert string in a docstring. (a) and (b) count as real adoption; (c) does not. Open the file at the hit line if it's ambiguous.

### Step 4 — Completed-item SDK-debt audit (separate pass)

Walk every `[x]` item in ROADMAP M1.1's IMP list (and any other closed milestone that fixed a bug). For each one, ask: *if this defect happened today, would the SDK-native fix be cleaner than what shipped?*

Example mapping from the canonical session (commit `2613dc6`):

| Closed item | Shipped fix | SDK-native version | Already covered by a pending item? |
|---|---|---|---|
| IMP-003 (0 tokens in-progress) | `dashboard_metrics.py` diagnostic note | `include_partial_messages=True` → `StreamEvent` deltas | Yes — M2.3 § G1 |
| IMP-006 (Bash heredoc) | Prompt constraint in `agents/definitions.py` | `can_use_tool` returning `PermissionResultDeny` | Yes — M2.6 `can_use_tool` item |
| IMP-010 (SQLAlchemy rollback) | `try/finally` + flush-error structlog | `async with ClaudeSDKClient` `__aexit__` | Yes — M1.5 `ClaudeSDKClient` migration |

**Rule:** if the debt is already covered by a pending `[ ]` item, list it in the INSIGHTS table but do **not** add a new ROADMAP item — that would duplicate work. Only add new ROADMAP entries for debts with no pending coverage.

### Step 5 — Map confirmed-missing items to ROADMAP milestones

The mapping is judgment, not lookup. Match the SDK lever's *purpose* to the milestone's *outcome*. Some heuristics:

- Telemetry / cost / cache levers → M2.3 (Cost-aware execution)
- Operator-visible UX / hook events / approval rendering → M2.4 (Operator UX polish)
- Autopilot preconditions / permission gates / typed retry → M2.6 (Autopilot mode)
- Subagent boundary / definition rubric / `maxTurns` / file checkpointing → M2.5 (Architecture rubrics)
- Session persistence / multi-machine / long-horizon → M3.2 (Long-horizon continuity) — usually as HARD prerequisites
- Multi-operator → M3.3 (depends on M3.2's SessionStore)
- Long-lived run mechanics (context manager, drain pattern) → M1.5 (Voice parity) or M2.1 (Lifecycle proof)

If a lever doesn't fit any existing milestone outcome, propose a new milestone in the INSIGHTS verdict — don't shove it into the nearest semi-relevant slot.

### Step 6 — Edit ROADMAP.md

For each confirmed-missing item, add a `[ ]` entry under the right milestone. **Each entry MUST include:**

1. A short, distinct identifier — use the same `G<n>` label the rubric / prior INSIGHTS uses if one exists, or coin a new one (e.g. `G17`).
2. The SDK lever name in backticks.
3. **Current state** — one sentence citing the grep evidence: either "Verified absent in `src/`" or "Today `<path:line>` does X (partial); Y is missing".
4. **Payoff** — what milestone bar this unblocks or what cost / UX failure it prevents.
5. **Pre-requisite** — the literal `ctx7 docs` query that the implementer must run before writing code, against the pinned SDK version. SDK signatures move between minor releases; without this, the implementer reads stale training data.
6. A trailing source reference — usually `*(SDK rubric § <section>; INSIGHTS <entry date>.)*`.

Template:

```markdown
- [ ] **<G-id> — `<sdk_lever>` <one-line summary>.** <current state with grep evidence>. <payoff>. Pre-requisite: `ctx7 docs /anthropics/claude-agent-sdk-python "<feature query>"` against SDK <version>. *(SDK rubric § <section>; INSIGHTS <date>.)*
```

For "partial" candidates, prefer **augmenting** an existing `[ ]` item with a parenthetical that points to the partial implementation, rather than adding a duplicate bullet. Example: M2.6's typed-retry item already exists; the canonical session added `*(... agents/runner.py:818-845 already catches CLINotFoundError/ProcessError/CLIJSONDecodeError; extend to AssistantMessageError/api_error_status.)*` instead of creating a new bullet.

### Step 7 — Append INSIGHTS verdict entry

INSIGHTS is append-only. Add a new dated entry at the end with this structure:

```markdown
---

## <YYYY-MM-DD> — Codebase-grounded revalidation of <rubric slug>
<!-- collected_at: <ISO datetime> (manual entry; roadmap-audit skill) -->

Source: `workflow knowledge read <slug>` cross-referenced against `grep -rn <lever> src/`.

### Validation table

| Gap | Codebase state | Action |
|---|---|---|
| <G-id> <lever> | <one-line evidence> | <Added to M<x>/Withdrawn/Narrowed/etc> |
…

### Completed-item SDK-debt audit (no new ROADMAP entries needed)

| Closed item | Current implementation | SDK-native version | Covered by |
|---|---|---|---|
…

### Verdict

Codebase validation reduced the open SDK-lever surface from <N> rubric candidates to <M> net additions. Withdrew <K>: <list>. Narrowed <L>: <list>. <One-line system-state summary.>

### Suggested ROADMAP.md change

All validated additions landed in ROADMAP this session: <bulleted summary>. No further changes pending from this revalidation.
```

The verdict line is the durable signal — future agents read INSIGHTS to know what was checked recently and skip re-checking it.

### Step 8 — Final report

Tell the user:

- Number of net additions to ROADMAP and which milestones received them.
- Number of withdrawals and the rationale (cite the grep hit for each).
- Number of partial refinements (existing items augmented, not new).
- Number of completed-item debts found, with the count already covered by pending items.
- Whether STATUS.md should get a Recent Decisions one-liner (advise; do not write — that's outside this skill's edit scope).

Keep it under 200 words. The INSIGHTS entry has the detail; the chat is the signal.

## Output Examples

The canonical reference is the INSIGHTS entry at `docs/goal/INSIGHTS.md` titled "2026-05-22 — Codebase-grounded revalidation of the ad-hoc rubric pass" (added by commit `2613dc6`), and the ROADMAP additions in the same commit. Open them before drafting a new run's output — they show the exact shape, tone, and level of grep-citation expected.

## Failure Modes To Avoid

These are real mistakes made in the unvalidated ad-hoc review that landed in INSIGHTS earlier:

1. **Recommending a lever from the rubric without grepping `src/`.** The prior review flagged `AskUserQuestion` audit as P2 work; one grep would have shown it was already across seven sites. Always grep first.
2. **Counting a docstring or prose mention as adoption.** `services/provider_limits.py` mentions `StopFailure` in a 5-line docstring; no hook is actually registered. Read the surrounding code, not just the grep hit.
3. **Re-opening closed `[x]` items because the SDK-native version looks cleaner.** Closed work stays closed. The SDK-debt audit is for *future* prevention via pending items, not for second-guessing shipped fixes.
4. **Hardcoding the rubric date in commands.** The rubric slug includes a date (`2026-05-22-claude-agent-sdk-rubric`) that rolls forward when `knowledge-base` refreshes. Always `search` first, then `read` the returned slug.
5. **Adding an item without a `ctx7 docs` pre-requisite.** SDK signatures move between `0.2.x` minor versions. An item without the pre-requisite is a trap for the future implementer.
6. **Editing STATUS.md, NORTH-STAR.md, or any other goal/ file.** See the HARD RULE block at the top.

## Compatibility Notes

- **`workflow` shim on Linux/WSL:** the global `workflow` shim hardcodes `python` which is often absent. Always invoke as `python3 ~/.claude/bin/workflow.py <subcommand>` from this skill.
- **`grep` vs `rg`:** either works. If `rg` is available, prefer it for speed on large `src/` trees. The skill body uses plain `grep -rn` for portability.
- **Without `workflow knowledge`:** abort. The rubric is the input; there is no fallback that's safe enough to ship a ROADMAP edit from.
