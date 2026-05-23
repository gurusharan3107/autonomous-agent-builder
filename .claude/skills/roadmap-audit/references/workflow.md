# Roadmap-audit workflow — 10 steps (Step 0 → Step 9)

> Loaded on demand from [roadmap-audit SKILL.md](../SKILL.md).

## Workflow

### Step 0 — SDK-delta early-exit gate

Before doing anything else, check whether the rubric has actually changed since the last audit. If not, skip the run and return a no-op message.

```bash
# 1. Read the most-recent rubric-updated marker written by knowledge-base
python3 -c "
import json, pathlib
p = pathlib.Path('.claude/skills/knowledge-base/state.json')
if not p.exists():
    print(''); raise SystemExit
d = json.loads(p.read_text() or '{}')
last = d.get('last_rubric_update', {}).get('claude-agent-sdk-rubric', '')
print(last)
" > /tmp/roadmap-audit-rubric-date.txt

# 2. Read the date of the last roadmap-audit INSIGHTS entry
grep -m 1 'Codebase-grounded revalidation' docs/goal/INSIGHTS.md | head -1 > /tmp/roadmap-audit-last-run.txt
```

**Decision:**

- If `last_rubric_update` ≤ the date of the most-recent INSIGHTS roadmap-audit entry → **skip**. Print: `"No SDK rubric delta since last audit (rubric: <date>, last audit: <date>). Skipping."` Exit cleanly. Self-schedule a 60-day heartbeat fallback (see Step 8).
- If `last_rubric_update` > the last audit date, OR the knowledge-base state file is absent (first-ever run), OR the operator explicitly invoked with `--force` → proceed to Step 1.
- If the rubric has never been ingested (`last_rubric_update` empty) → run `knowledge-base` REFRESH first, then come back. Report this to the operator instead of running blind.

This gate prevents the most common waste of this skill: re-running against an unchanged rubric and generating an identical INSIGHTS entry. The KB-side rubric date is the canonical signal of "is there anything new to audit?".

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

### Step 9 — Self-schedule the heartbeat fallback

After Step 8 reports back, call `CronCreate` to schedule a 60-day heartbeat fallback. This is the safety net for cases where `knowledge-base` REFRESH doesn't fire (e.g. operator skipping the monthly cron) — the audit still runs at least every 2 months.

```
CronCreate(
  schedule: "every 60 days at 10:00",
  prompt: "roadmap-audit heartbeat — check for SDK rubric delta and revalidate ROADMAP if changed",
  description: "Auto-scheduled by roadmap-audit Step 9. Heartbeat fallback; the primary trigger is knowledge-base REFRESH detecting a rubric delta."
)
```

Skip when:
- `CronCreate` unavailable (report in chat).
- A roadmap-audit cron is already scheduled (check `CronList`; refuse duplicates).
- The Step 0 gate already exited early ("no rubric delta") — the next-firing 24-hour cron set by `knowledge-base` is the primary path; only re-schedule the heartbeat if the audit actually ran.
- Operator passed `--no-schedule`.

The 60-day cadence is deliberately longer than knowledge-base's 30-day REFRESH cadence so the heartbeat fires only when KB cadence has clearly skipped — not as a primary trigger.
